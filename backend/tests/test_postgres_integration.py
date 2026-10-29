"""Isolated PostgreSQL integration tests (opt-in, loopback-only).

Safety contract:
- Importing this module never opens a connection.
- Tests skip unless ``VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS`` is explicitly
  enabled. When enabled, ``VERIFYGRID_TEST_DATABASE_URL`` is mandatory and is
  validated as a dedicated loopback test database; the application
  ``DATABASE_URL`` is never used as a fallback.
- The schema is created from the application's current model metadata inside a
  per-session, uniquely named PostgreSQL schema. The schema is dropped at the
  end of the session. No public/development tables are touched.
- The committed Alembic migrations are NOT used to create this schema; see
  ``docs/POSTGRES_INTEGRATION_TESTING.md`` and the Neon reconciliation plan for
  the known migration/model drift.
"""

from __future__ import annotations

import ipaddress
import json
import os
import uuid
from pathlib import Path
from typing import Generator, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.source_file import SourceFile
from app.models.user import User
from app.models.verification_run import VerificationDiscrepancy, VerificationRun
from app.models.verification_template import VerificationTemplate

from tests.pg_test_target import (
    POSTGRES_INTEGRATION_ENV,
    TEST_DATABASE_URL_ENV,
    TargetCheck,
    integration_tests_enabled,
    safe_schema_name,
    validate_test_database_url,
)

import tests.test_batch14_college_pilot_audit as pilot


pytestmark = pytest.mark.skipif(
    not integration_tests_enabled(),
    reason=(
        "PostgreSQL integration tests are opt-in. Set "
        f"{POSTGRES_INTEGRATION_ENV}=1 and {TEST_DATABASE_URL_ENV} to an "
        "explicitly isolated loopback test database. The application "
        "DATABASE_URL is never used as a fallback."
    ),
)


# =============================================================================
# Target / engine safety
# =============================================================================


def _require_safe_target() -> TargetCheck:
    """Re-validate at fixture time; fail loudly instead of falling back."""
    check = validate_test_database_url(
        os.getenv(TEST_DATABASE_URL_ENV),
        application_url=settings.database_url,
    )
    if not check.ok:
        pytest.fail(
            "Refusing to run PostgreSQL integration tests: " + " ".join(check.errors),
            pytrace=False,
        )
    assert check.url is not None
    return check


def _verify_connected_target(conn, check: TargetCheck) -> None:
    """Verify the server we actually reached is the validated test target."""
    database, username, address = conn.execute(
        text(
            "SELECT current_database(), current_user, host(inet_server_addr())"
        )
    ).one()
    assert database == check.database
    assert username == check.username
    if address is not None:
        assert ipaddress.ip_address(address).is_loopback, (
            "Connected PostgreSQL server address is not loopback."
        )


@pytest.fixture(scope="session")
def pg_target() -> TargetCheck:
    return _require_safe_target()


@pytest.fixture(scope="session")
def pg_engine(pg_target: TargetCheck) -> Generator[Engine, None, None]:
    """Create a unique schema in the dedicated test database for this session."""
    assert pg_target.url is not None
    schema = safe_schema_name(f"verifygrid_it_{uuid.uuid4().hex[:12]}")
    admin_engine = create_engine(
        pg_target.url,
        connect_args={"connect_timeout": 5},
    )
    test_engine: Optional[Engine] = None
    try:
        with admin_engine.begin() as conn:
            _verify_connected_target(conn, pg_target)
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))

        # Every pooled connection resolves unqualified table names inside the
        # per-session schema, never in public.
        test_engine = create_engine(
            pg_target.url,
            connect_args={
                "connect_timeout": 5,
                "options": f"-csearch_path={schema}",
            },
            pool_pre_ping=True,
        )
        with test_engine.begin() as conn:
            _verify_connected_target(conn, pg_target)
        Base.metadata.create_all(bind=test_engine)
        yield test_engine
    finally:
        if test_engine is not None:
            test_engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def _truncate_all(engine: Engine) -> None:
    tables = [table for table in Base.metadata.sorted_tables]
    if not tables:
        return
    names = ", ".join(f'"{table.name}"' for table in tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture()
def pg_session(pg_engine: Engine) -> Generator[Session, None, None]:
    """Fresh, isolated session per test; all test tables are cleaned first."""
    _truncate_all(pg_engine)
    session_factory = sessionmaker(
        bind=pg_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "PostgreSQL Integration User",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


@pytest.fixture()
def pg_client(
    pg_session: Session,
    upload_storage: Path,
) -> Generator[TestClient, None, None]:
    """FastAPI client bound to the isolated PostgreSQL session."""
    def override_get_db() -> Generator[Session, None, None]:
        yield pg_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            token = _register(client, f"pg-{uuid.uuid4().hex[:10]}@example.com")
            client.headers.update({"Authorization": f"Bearer {token}"})
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


# =============================================================================
# Helpers
# =============================================================================


def _create_template(
    client: TestClient,
    name: str,
    *,
    description: Optional[str] = None,
    configuration: Optional[dict] = None,
) -> dict:
    payload = {
        "name": name,
        "mode": "organization",
        "configuration": configuration or pilot._template_config(),
    }
    if description is not None:
        payload["description"] = description
    response = client.post("/api/v1/templates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_project(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload_csv(client: TestClient, project_id: str, name: str, content: str) -> dict:
    import io

    response = client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": (name, io.BytesIO(content.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _run_results(client: TestClient, project_id: str, run_id: str) -> list[dict]:
    response = client.get(
        f"/api/v1/projects/{project_id}/runs/{run_id}/results",
        params={"limit": 200},
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _get_run(client: TestClient, project_id: str, run_id: str) -> dict:
    response = client.get(f"/api/v1/projects/{project_id}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _simple_payload(primary_id: str, secondary_id: str) -> dict:
    return {
        "sources": [
            {
                "alias": "primary",
                "file_id": primary_id,
                "is_primary": True,
                "key_columns": ["student_id"],
                "field_mapping": {"student_id": "student_id", "name": "name"},
            },
            {
                "alias": "secondary",
                "file_id": secondary_id,
                "is_primary": False,
                "key_columns": ["student_id"],
                "field_mapping": {"student_id": "student_id", "name": "name"},
            },
        ],
        "unified_keys": ["student_id"],
        "compare_attributes": ["name"],
        "include_identical": True,
    }


# =============================================================================
# 1-3: Templates and authorization
# =============================================================================


def test_template_create_and_retrieve_postgres(pg_client: TestClient, pg_session: Session):
    template = _create_template(pg_client, "PostgreSQL Retrieval", description="Round trip")
    assert template["source_count"] == 3
    assert template["config_version"] == 1
    assert template["visibility"] == "personal"

    fetched = pg_client.get(f"/api/v1/templates/{template['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["configuration"] == template["configuration"]
    assert fetched.json()["description"] == "Round trip"

    listed = pg_client.get("/api/v1/templates")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [template["id"]]

    row = pg_session.get(VerificationTemplate, uuid.UUID(template["id"]))
    assert row is not None
    assert row.name == "PostgreSQL Retrieval"
    assert row.owner_id is not None
    assert row.configuration["version"] == 1


def test_template_configuration_json_round_trips_postgres(
    pg_client: TestClient,
    pg_session: Session,
):
    configuration = pilot._template_config()
    configuration["numeric_tolerance"] = 0.25
    configuration["ignore_case"] = True
    configuration["ignore_whitespace"] = False
    configuration["fallback_keys"] = [["enrollment_no"]]
    configuration["sources"][1]["sheet_name"] = "Roster"

    template = _create_template(
        pg_client,
        "PostgreSQL JSON",
        description="Nested configuration",
        configuration=configuration,
    )
    assert template["configuration"] == configuration

    fetched = pg_client.get(f"/api/v1/templates/{template['id']}").json()
    assert fetched["configuration"] == configuration
    assert fetched["configuration"]["sources"][1]["sheet_name"] == "Roster"
    assert fetched["configuration"]["fallback_keys"] == [["enrollment_no"]]

    replacement = pilot._template_config()
    replacement["sources"][0]["label"] = "Replaced Label"
    replacement["compare_attributes"] = ["name"]
    updated = pg_client.put(
        f"/api/v1/templates/{template['id']}",
        json={"configuration": replacement},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["configuration"] == replacement
    assert body["name"] == "PostgreSQL JSON"
    assert body["description"] == "Nested configuration"

    pg_session.expire_all()
    row = pg_session.get(VerificationTemplate, uuid.UUID(template["id"]))
    assert row is not None
    assert row.configuration == replacement
    assert row.name == "PostgreSQL JSON"
    assert row.description == "Nested configuration"


def test_template_ownership_and_authorization_postgres(pg_client: TestClient):
    template = _create_template(pg_client, "PostgreSQL Private")

    other_token = _register(pg_client, f"pg-other-{uuid.uuid4().hex[:10]}@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    assert (
        pg_client.get(
            f"/api/v1/templates/{template['id']}", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        pg_client.put(
            f"/api/v1/templates/{template['id']}",
            headers=other_headers,
            json={"name": "Hijacked"},
        ).status_code
        == 404
    )
    assert (
        pg_client.delete(
            f"/api/v1/templates/{template['id']}", headers=other_headers
        ).status_code
        == 404
    )
    assert pg_client.get("/api/v1/templates", headers=other_headers).json() == []

    invalid = pg_client.get(
        f"/api/v1/templates/{template['id']}",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert invalid.status_code == 401

    owner_view = pg_client.get(f"/api/v1/templates/{template['id']}")
    assert owner_view.status_code == 200
    assert owner_view.json()["name"] == "PostgreSQL Private"


# =============================================================================
# 4: Template apply and execution separation
# =============================================================================


def test_template_apply_without_verification_execution_postgres(
    pg_client: TestClient,
    pg_session: Session,
):
    project_id, files = pilot._upload_college_project(
        pg_client, "PostgreSQL Apply Target", reverse_order=True
    )
    template = _create_template(pg_client, "PostgreSQL Apply Template")

    bindings = [
        {"slot": "library", "file_id": files["library"]["id"]},
        {"slot": "academic", "file_id": files["academic"]["id"]},
        {"slot": "hostel", "file_id": files["hostel"]["id"]},
    ]
    response = pg_client.post(
        f"/api/v1/templates/{template['id']}/apply",
        json={"project_id": project_id, "sources": bindings},
    )
    assert response.status_code == 200, response.text
    applied = response.json()
    assert applied["validation_report"] == {
        "blocking": False,
        "issues": [],
        "warnings": [],
    }

    effective = applied["effective_request"]
    by_alias = {source["alias"]: source for source in effective["sources"]}
    assert by_alias["academic"]["file_id"] == files["academic"]["id"]
    assert by_alias["hostel"]["file_id"] == files["hostel"]["id"]
    assert by_alias["library"]["file_id"] == files["library"]["id"]
    assert by_alias["hostel"]["sheet_name"] == "Roster"
    assert by_alias["academic"]["is_primary"] is True
    assert effective["fallback_keys"] == [["enrollment_no"]]

    runs = pg_client.get(f"/api/v1/projects/{project_id}/runs")
    assert runs.status_code == 200
    assert runs.json()["total"] == 0
    assert pg_session.query(VerificationRun).count() == 0


# =============================================================================
# 5: Multi-source verification and persisted results
# =============================================================================


def test_multisource_verification_and_persisted_results_postgres(
    pg_client: TestClient,
    pg_session: Session,
):
    project_id, files = pilot._upload_college_project(
        pg_client, "PostgreSQL Multi Source"
    )
    payload = pilot._legacy_payload(files)

    preview = pg_client.post(
        f"/api/v1/projects/{project_id}/verify/multi-source", json=payload
    )
    assert preview.status_code == 200, preview.text
    preview_summary = preview.json()["summary"]

    run_response = pg_client.post(
        f"/api/v1/projects/{project_id}/runs/multi-source", json=payload
    )
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()
    assert run["status"] == "completed"
    assert [source["alias"] for source in run["sources"]] == [
        "academic",
        "hostel",
        "library",
    ]
    assert (
        next(source for source in run["sources"] if source["alias"] == "hostel")[
            "sheet_name"
        ]
        == "Roster"
    )

    persisted = _get_run(pg_client, project_id, run["id"])
    assert persisted["status"] == "completed"
    for field in (
        "total_source_records",
        "total_target_records",
        "matched_records",
        "identical_matches",
        "field_mismatches",
        "invalid_key_records",
        "fallback_matched_records",
        "unmatched_source_records",
        "unmatched_target_records",
        "duplicate_source_records",
        "duplicate_target_records",
        "duplicate_source_keys_count",
        "duplicate_target_keys_count",
        "total_discrepancies",
        "attribute_comparisons_completed",
        "attributes_not_checked",
    ):
        assert persisted["summary"][field] == preview_summary[field], field

    items = _run_results(pg_client, project_id, run["id"])
    assert len(items) == preview_summary["total_discrepancies"] == 8

    db_run = pg_session.get(VerificationRun, uuid.UUID(run["id"]))
    assert db_run is not None
    assert db_run.status == "completed"
    assert db_run.summary["total_discrepancies"] == 8
    assert db_run.sources is not None
    assert [source["alias"] for source in db_run.sources] == [
        "academic",
        "hostel",
        "library",
    ]
    discrepancy_count = (
        pg_session.query(VerificationDiscrepancy)
        .filter(VerificationDiscrepancy.run_id == db_run.id)
        .count()
    )
    assert discrepancy_count == len(items) == 8


# =============================================================================
# 6: Blank and null identity keys
# =============================================================================


def test_blank_and_null_identity_keys_postgres(
    pg_client: TestClient,
    pg_session: Session,
):
    project_id = _create_project(pg_client, "PostgreSQL Blank Keys")
    primary = _upload_csv(
        pg_client,
        project_id,
        "primary.csv",
        "student_id,name\n,Blank Student\nS-1,Alice\n",
    )
    secondary = _upload_csv(
        pg_client,
        project_id,
        "secondary.csv",
        "student_id,name\nS-1,Alice\n",
    )

    run_response = pg_client.post(
        f"/api/v1/projects/{project_id}/runs/multi-source",
        json=_simple_payload(primary["id"], secondary["id"]),
    )
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()
    assert run["summary"]["invalid_key_records"] == 1
    assert run["summary"]["needs_review_records"] == 0

    items = _run_results(pg_client, project_id, run["id"])
    invalid = [item for item in items if item["match_status"] == "needs_review"]
    assert len(invalid) == 1
    assert invalid[0]["reason_code"] == "NULL_KEY"
    assert invalid[0]["key_values"]["student_id"] is None
    assert invalid[0]["source_records"]["primary"]["student_id"] is None

    db_row = (
        pg_session.query(VerificationDiscrepancy)
        .filter(VerificationDiscrepancy.match_status == "needs_review")
        .one()
    )
    assert db_row.reason_code == "NULL_KEY"
    assert db_row.key_values["student_id"] is None
    assert db_row.source_row_indices is not None


# =============================================================================
# 7: Duplicate-key handling
# =============================================================================


def test_duplicate_key_handling_postgres(
    pg_client: TestClient,
    pg_session: Session,
):
    project_id, files = pilot._upload_college_project(
        pg_client, "PostgreSQL Duplicate Keys"
    )
    run_response = pg_client.post(
        f"/api/v1/projects/{project_id}/runs/multi-source",
        json=pilot._legacy_payload(files),
    )
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()
    summary = run["summary"]
    assert summary["duplicate_source_keys_count"] == 1
    assert summary["duplicate_source_records"] == 2
    assert summary["duplicate_target_keys_count"] == 2
    assert summary["duplicate_target_records"] == 4

    items = _run_results(pg_client, project_id, run["id"])
    duplicate_items = [
        item for item in items if item["match_status"] == "duplicate_key_source"
    ]
    assert len(duplicate_items) == 3
    assert {item["key_values"]["student_id"] for item in duplicate_items} == {
        "S002",
        "S006",
        "S011",
    }
    assert all(
        item["reason_code"] == "DUPLICATE_KEY_SOURCE" for item in duplicate_items
    )
    assert all(item["source_row_indices"] for item in duplicate_items)

    db_rows = (
        pg_session.query(VerificationDiscrepancy)
        .filter(VerificationDiscrepancy.match_status == "duplicate_key_source")
        .all()
    )
    assert len(db_rows) == 3
    assert all(row.reason_code == "DUPLICATE_KEY_SOURCE" for row in db_rows)
    assert all(row.source_row_indices for row in db_rows)


# =============================================================================
# 8-9: Worksheet-specific quarantine resolutions
# =============================================================================

SIDECAR_SHEETS = {
    "Roster": [["student_id", "amount"], ["S-1", 100], ["S-2", -50]],
    "Archive": [["student_id", "amount"], ["A-1", 200], ["A-2", -999]],
}


def _upload_sidecar_workbook(client: TestClient, project_id: str, name: str) -> dict:
    return pilot.upload_file(
        client,
        project_id,
        name,
        pilot.make_multisheet_xlsx(SIDECAR_SHEETS),
        pilot.XLSX_CONTENT_TYPE,
    )


def _quarantine(
    client: TestClient,
    project_id: str,
    file_id: str,
    worksheet: str,
) -> dict:
    response = client.get(
        f"/api/v1/projects/{project_id}/files/{file_id}/quarantine",
        params={"worksheet": worksheet},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _resolve(
    client: TestClient,
    project_id: str,
    file_id: str,
    worksheet: str,
    row: int,
) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/files/{file_id}/quarantine/resolve",
        params={"worksheet": worksheet},
        json={"resolutions": [{"source_row_index": row, "action": "EXCLUDE"}]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _row3(response: dict) -> dict:
    return next(
        record for record in response["records"] if record["source_row_index"] == 3
    )


def test_worksheet_specific_quarantine_resolution_postgres(
    pg_client: TestClient,
    pg_session: Session,
):
    project_id = _create_project(pg_client, "PostgreSQL Quarantine Scope")
    workbook = _upload_sidecar_workbook(pg_client, project_id, "scope.xlsx")

    resolved = _resolve(pg_client, project_id, workbook["id"], "Roster", 3)
    assert resolved["excluded_row_indices"] == [3]

    archive = _quarantine(pg_client, project_id, workbook["id"], "Archive")
    assert _row3(archive)["resolution_action"] != "EXCLUDE"
    assert archive["impact_preview"]["excluded_rows_count"] == 0

    roster = _quarantine(pg_client, project_id, workbook["id"], "Roster")
    assert _row3(roster)["resolution_action"] == "EXCLUDE"
    assert roster["impact_preview"]["excluded_rows_count"] == 1

    source_file = pg_session.get(SourceFile, uuid.UUID(workbook["id"]))
    assert source_file is not None
    path = Path(source_file.storage_path)
    sidecar = path.with_name(path.name + ".quarantine.json")
    assert sidecar.exists()
    archive_data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert archive_data["worksheet_resolutions"]["Roster"]["resolutions"] == {
        "3": "EXCLUDE"
    }


def test_independent_resolutions_for_multiple_worksheets_postgres(
    pg_client: TestClient,
    pg_session: Session,
):
    project_id = _create_project(pg_client, "PostgreSQL Quarantine Archive")
    workbook = _upload_sidecar_workbook(pg_client, project_id, "archive.xlsx")
    file_id = workbook["id"]

    _resolve(pg_client, project_id, file_id, "Roster", 3)
    _resolve(pg_client, project_id, file_id, "Archive", 3)

    roster = _quarantine(pg_client, project_id, file_id, "Roster")
    archive = _quarantine(pg_client, project_id, file_id, "Archive")
    assert _row3(roster)["resolution_action"] == "EXCLUDE"
    assert _row3(archive)["resolution_action"] == "EXCLUDE"
    assert roster["impact_preview"]["excluded_rows_count"] == 1
    assert archive["impact_preview"]["excluded_rows_count"] == 1

    # A run on Roster must exclude only S-2; Archive excludes only A-2.
    def run_for(sheet: str) -> tuple[dict, dict]:
        payload = {
            "sources": [
                {
                    "alias": "primary",
                    "file_id": file_id,
                    "is_primary": True,
                    "key_columns": ["student_id"],
                    "field_mapping": {
                        "student_id": "student_id",
                        "amount": "amount",
                    },
                    "sheet_name": sheet,
                },
                {
                    "alias": "secondary",
                    "file_id": file_id,
                    "is_primary": False,
                    "key_columns": ["student_id"],
                    "field_mapping": {
                        "student_id": "student_id",
                        "amount": "amount",
                    },
                    "sheet_name": sheet,
                },
            ],
            "unified_keys": ["student_id"],
            "compare_attributes": ["amount"],
            "include_identical": True,
        }
        preview = pg_client.post(
            f"/api/v1/projects/{project_id}/verify/multi-source",
            json=payload,
        )
        assert preview.status_code == 200, preview.text
        response = pg_client.post(
            f"/api/v1/projects/{project_id}/runs/multi-source",
            json=payload,
        )
        assert response.status_code == 201, response.text
        return preview.json(), response.json()

    roster_preview, roster_run = run_for("Roster")
    archive_preview, archive_run = run_for("Archive")
    # Both worksheets have their own exclusion, so each contributes one
    # eligible record. The IDs prove no row crossed between worksheets.
    assert roster_run["summary"]["total_source_records"] == 1
    assert archive_run["summary"]["total_source_records"] == 1

    roster_ids = {
        record.get("student_id")
        for item in roster_preview["results"]
        for record in (item.get("source_records") or {}).values()
    }
    archive_ids = {
        record.get("student_id")
        for item in archive_preview["results"]
        for record in (item.get("source_records") or {}).values()
    }
    assert roster_ids == {"S-1"}
    assert archive_ids == {"A-1"}
    assert "S-2" not in roster_ids
    assert "A-2" not in archive_ids

    source_file = pg_session.get(SourceFile, uuid.UUID(file_id))
    assert source_file is not None
    path = Path(source_file.storage_path)
    sidecar = path.with_name(path.name + ".quarantine.json")
    archive_data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert set(archive_data["worksheet_resolutions"]) >= {"Roster", "Archive"}
    assert archive_data["worksheet_resolutions"]["Roster"]["resolutions"] == {
        "3": "EXCLUDE"
    }
    assert archive_data["worksheet_resolutions"]["Archive"]["resolutions"] == {
        "3": "EXCLUDE"
    }


# =============================================================================
# 10: Persisted discrepancy reason codes
# =============================================================================


def test_persisted_discrepancy_reason_codes_postgres(
    pg_client: TestClient,
    pg_session: Session,
):
    project_id, files = pilot._upload_college_project(
        pg_client, "PostgreSQL Reason Codes"
    )
    run_response = pg_client.post(
        f"/api/v1/projects/{project_id}/runs/multi-source",
        json=pilot._legacy_payload(files),
    )
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()
    items = _run_results(pg_client, project_id, run["id"])
    codes = {item["reason_code"] for item in items}
    assert {"MISSING_IN_TARGET", "DUPLICATE_KEY_SOURCE", "NULL_KEY"} <= codes

    missing = next(
        item for item in items if item["key_values"].get("student_id") == "S004"
    )
    assert missing["reason_code"] == "MISSING_IN_TARGET"
    duplicate = next(
        item for item in items if item["key_values"].get("student_id") == "S002"
    )
    assert duplicate["reason_code"] == "DUPLICATE_KEY_SOURCE"
    invalid = next(item for item in items if item["match_status"] == "needs_review")
    assert invalid["reason_code"] == "NULL_KEY"

    # A field mismatch is persisted with a distinct reason code.
    mismatch_project = _create_project(pg_client, "PostgreSQL Field Mismatch")
    primary = _upload_csv(
        pg_client,
        mismatch_project,
        "primary.csv",
        "student_id,name\nS-1,Alice\n",
    )
    secondary = _upload_csv(
        pg_client,
        mismatch_project,
        "secondary.csv",
        "student_id,name\nS-1,Alicia\n",
    )
    mismatch_run = pg_client.post(
        f"/api/v1/projects/{mismatch_project}/runs/multi-source",
        json=_simple_payload(primary["id"], secondary["id"]),
    )
    assert mismatch_run.status_code == 201, mismatch_run.text
    mismatch_items = _run_results(
        pg_client, mismatch_project, mismatch_run.json()["id"]
    )
    assert len(mismatch_items) == 1
    assert mismatch_items[0]["reason_code"] == "FIELD_MISMATCH"
    assert mismatch_items[0]["field_differences"]

    db_row = (
        pg_session.query(VerificationDiscrepancy)
        .join(
            VerificationRun,
            VerificationDiscrepancy.run_id == VerificationRun.id,
        )
        .filter(VerificationRun.project_id == uuid.UUID(mismatch_project))
        .one()
    )
    assert db_row.reason_code == "FIELD_MISMATCH"


# =============================================================================
# 11: Summary counters and persisted-result consistency
# =============================================================================


def test_summary_counters_match_persisted_results_postgres(
    pg_client: TestClient,
    pg_session: Session,
):
    project_id, files = pilot._upload_college_project(
        pg_client, "PostgreSQL Summary Consistency"
    )
    payload = pilot._legacy_payload(files)

    preview_response = pg_client.post(
        f"/api/v1/projects/{project_id}/verify/multi-source", json=payload
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_body = preview_response.json()
    preview_summary = preview_body["summary"]

    run_response = pg_client.post(
        f"/api/v1/projects/{project_id}/runs/multi-source", json=payload
    )
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()
    items = _run_results(pg_client, project_id, run["id"])

    for key in (
        "total_source_records",
        "total_target_records",
        "matched_records",
        "identical_matches",
        "field_mismatches",
        "invalid_key_records",
        "fallback_matched_records",
        "unmatched_source_records",
        "unmatched_target_records",
        "duplicate_source_records",
        "duplicate_target_records",
        "duplicate_source_keys_count",
        "duplicate_target_keys_count",
        "total_discrepancies",
        "attribute_comparisons_completed",
        "attributes_not_checked",
    ):
        assert run["summary"][key] == preview_summary[key], key
    assert run["summary"]["records_by_source"] == preview_body["records_by_source"]
    assert run["summary"]["total_discrepancies"] == len(items) == 8
    assert run["summary"]["matched_records"] == 5
    assert run["summary"]["invalid_key_records"] == 3
    assert run["summary"]["fallback_matched_records"] == 2

    status_counts: dict[str, int] = {}
    for item in items:
        status_counts[item["match_status"]] = status_counts.get(item["match_status"], 0) + 1
    assert sum(status_counts.values()) == len(items)

    db_run_id = uuid.UUID(run["id"])
    db_count = (
        pg_session.query(VerificationDiscrepancy)
        .filter(VerificationDiscrepancy.run_id == db_run_id)
        .count()
    )
    assert db_count == len(items)
    db_by_status = {
        status: count
        for status, count in (
            pg_session.query(
                VerificationDiscrepancy.match_status,
                func.count(),
            )
            .filter(VerificationDiscrepancy.run_id == db_run_id)
            .group_by(VerificationDiscrepancy.match_status)
            .all()
        )
    }
    assert db_by_status == status_counts


# =============================================================================
# 12: Transaction rollback and cleanup
# =============================================================================


def test_transaction_rollback_and_cleanup_postgres(pg_session: Session):
    # The fixture starts from a clean schema; this also proves cross-test cleanup.
    assert pg_session.query(VerificationTemplate).count() == 0

    user = User(
        email=f"pg-rollback-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Rollback User",
    )
    pg_session.add(user)
    pg_session.commit()
    pg_session.refresh(user)

    template = VerificationTemplate(
        owner_id=user.id,
        name="Rollback Template",
        mode="organization",
        configuration=pilot._template_config(),
    )
    pg_session.add(template)
    pg_session.flush()
    assert pg_session.query(VerificationTemplate).count() == 1

    pg_session.rollback()
    assert pg_session.query(VerificationTemplate).count() == 0
    assert pg_session.query(User).filter(User.id == user.id).count() == 1

    first = VerificationTemplate(
        owner_id=user.id,
        name="Unique Template",
        mode="organization",
        configuration=pilot._template_config(),
    )
    pg_session.add(first)
    pg_session.commit()

    duplicate = VerificationTemplate(
        owner_id=user.id,
        name="Unique Template",
        mode="organization",
        configuration=pilot._template_config(),
    )
    pg_session.add(duplicate)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

    assert pg_session.query(VerificationTemplate).count() == 1
    assert pg_session.query(VerificationTemplate).one().name == "Unique Template"
