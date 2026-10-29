"""Application behavior on an Alembic-built PostgreSQL schema (opt-in).

This suite closes the gap between two kinds of PostgreSQL evidence:

- ``test_postgres_integration.py`` proves application behavior on a schema
  created from ``Base.metadata``.
- ``test_alembic_migration_parity.py`` proves the committed migration graph
  builds a schema matching that metadata.

The tests below run real API persistence and retrieval against the schema that
the committed Alembic graph actually creates. The schema is never created from
model metadata; ``Base.metadata`` is used only to truncate test tables between
cases.

Safety contract:
- Importing this module never opens a database connection.
- Tests skip unless ``VERIFYGRID_RUN_POSTGRES_INTEGRATION_TESTS`` is enabled.
- ``VERIFYGRID_TEST_DATABASE_URL`` is mandatory and validated by the shared
  fail-closed guard; the application ``DATABASE_URL`` is never a fallback.
- Alembic receives an already-validated connection explicitly.
- A unique schema is created in the dedicated test database and dropped after
  the session. No public/development tables are touched.
"""

from __future__ import annotations

import ipaddress
import io
import os
import uuid
from pathlib import Path
from typing import Generator, Optional

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.models.verification_run import DiscrepancyReviewDecision, VerificationDiscrepancy, VerificationRun
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
        "Alembic-built application tests are opt-in. Set "
        f"{POSTGRES_INTEGRATION_ENV}=1 and {TEST_DATABASE_URL_ENV} to an "
        "explicitly isolated loopback test database. The application "
        "DATABASE_URL is never used as a fallback."
    ),
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
EXPECTED_HEAD = "0006_discrepancy_review_decisions"


def _require_safe_target() -> TargetCheck:
    check = validate_test_database_url(
        os.getenv(TEST_DATABASE_URL_ENV),
        application_url=settings.database_url,
    )
    if not check.ok:
        pytest.fail(
            "Refusing to run Alembic-built application tests: "
            + " ".join(check.errors),
            pytrace=False,
        )
    assert check.url is not None
    return check


def _verify_connected_target(conn: Connection, check: TargetCheck) -> None:
    database, username, address = conn.execute(
        text("SELECT current_database(), current_user, host(inet_server_addr())")
    ).one()
    assert database == check.database
    assert username == check.username
    if address is not None:
        assert ipaddress.ip_address(address).is_loopback, (
            "Connected PostgreSQL server address is not loopback."
        )


def _alembic_config(connection: Connection) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["connection"] = connection
    return config


def _run_alembic(
    engine: Engine,
    check: TargetCheck,
    action: str,
    revision: str,
) -> None:
    with engine.connect() as connection:
        _verify_connected_target(connection, check)
        connection.rollback()
        config = _alembic_config(connection)
        if action == "upgrade":
            command.upgrade(config, revision)
        elif action == "downgrade":
            command.downgrade(config, revision)
        else:
            raise ValueError(f"Unsupported Alembic action: {action}")
        connection.rollback()


@pytest.fixture(scope="session")
def migration_pg_target() -> TargetCheck:
    return _require_safe_target()


@pytest.fixture(scope="session")
def migration_engine(
    migration_pg_target: TargetCheck,
) -> Generator[Engine, None, None]:
    """Build the schema exclusively by upgrading the committed migration graph."""
    assert migration_pg_target.url is not None
    schema = safe_schema_name(f"verifygrid_migapp_{uuid.uuid4().hex[:12]}")
    admin_engine = create_engine(
        migration_pg_target.url,
        connect_args={"connect_timeout": 5},
    )
    test_engine: Optional[Engine] = None
    try:
        with admin_engine.begin() as conn:
            _verify_connected_target(conn, migration_pg_target)
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))

        test_engine = create_engine(
            migration_pg_target.url,
            connect_args={
                "connect_timeout": 5,
                "options": f"-csearch_path={schema}",
            },
            pool_pre_ping=True,
        )
        with test_engine.connect() as conn:
            _verify_connected_target(conn, migration_pg_target)

        _run_alembic(test_engine, migration_pg_target, "upgrade", "head")
        with test_engine.connect() as conn:
            revision = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert revision == EXPECTED_HEAD, revision
        yield test_engine
    finally:
        if test_engine is not None:
            test_engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def _truncate_all(engine: Engine) -> None:
    names = ", ".join(
        f'"{table.name}"' for table in Base.metadata.sorted_tables
    )
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture()
def migration_session(migration_engine: Engine) -> Generator[Session, None, None]:
    _truncate_all(migration_engine)
    session = sessionmaker(
        bind=migration_engine,
        autoflush=False,
        expire_on_commit=False,
    )()
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
            "full_name": "Alembic Application User",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


@pytest.fixture()
def migration_client(
    migration_session: Session,
    upload_storage: Path,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield migration_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            token = _register(
                client, f"migapp-{uuid.uuid4().hex[:10]}@example.com"
            )
            client.headers.update({"Authorization": f"Bearer {token}"})
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _create_project(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload_csv(client: TestClient, project_id: str, name: str, content: str) -> dict:
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


# =============================================================================
# Phase D: application operations on the Alembic-built schema
# =============================================================================


def test_multisource_run_persists_and_reads_lineage_on_migrated_schema(
    migration_client: TestClient,
    migration_session: Session,
):
    project_id, files = pilot._upload_college_project(
        migration_client, "Alembic Multi Source"
    )
    payload = pilot._legacy_payload(files)

    response = migration_client.post(
        f"/api/v1/projects/{project_id}/runs/multi-source", json=payload
    )
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "completed"
    assert [source["alias"] for source in run["sources"]] == [
        "academic",
        "hostel",
        "library",
    ]

    persisted = migration_client.get(
        f"/api/v1/projects/{project_id}/runs/{run['id']}"
    )
    assert persisted.status_code == 200, persisted.text
    persisted_run = persisted.json()
    assert persisted_run["sources"] == run["sources"]
    assert persisted_run["summary"]["total_discrepancies"] == 8

    items = _run_results(migration_client, project_id, run["id"])
    assert len(items) == 8

    s002 = next(item for item in items if item["key_values"].get("student_id") == "S002")
    assert s002["match_status"] == "duplicate_key_source"
    assert s002["source_row_indices"]["hostel"] == 3
    assert s002["source_records"]["hostel"]["student_id"] == "S002"

    # Direct column evidence, independent of response serialization.
    db_run = migration_session.get(VerificationRun, uuid.UUID(run["id"]))
    assert db_run is not None
    assert db_run.sources == run["sources"]
    db_discrepancies = (
        migration_session.query(VerificationDiscrepancy)
        .filter(VerificationDiscrepancy.run_id == db_run.id)
        .all()
    )
    assert len(db_discrepancies) == 8
    db_s002 = next(
        row for row in db_discrepancies
        if (row.key_values or {}).get("student_id") == "S002"
    )
    assert db_s002.source_row_indices["hostel"] == 3
    assert db_s002.source_records["hostel"]["student_id"] == "S002"


def test_split_payment_aggregation_persists_lineage_on_migrated_schema(
    migration_client: TestClient,
    migration_session: Session,
):
    project_id = _create_project(migration_client, "Alembic Split Payment")
    invoices = _upload_csv(
        migration_client,
        project_id,
        "invoices.csv",
        "inv_no,total\nINV-900,1000.00\n",
    )
    payments = _upload_csv(
        migration_client,
        project_id,
        "payments.csv",
        "inv_no,paid_amt,rec_no\n"
        "INV-900,600.00,R-1\n"
        "INV-900,300.00,R-2\n",
    )

    rule_config = {
        "version": "1.0.0",
        "aggregation_config": {
            "enabled": True,
            "parent_source_alias": "invoices",
            "child_source_alias": "payments",
            "parent_key": "inv_no",
            "child_grouping_key": "inv_no",
            "parent_amount_field": "total",
            "child_amount_field": "paid_amt",
            "child_receipt_id_field": "rec_no",
            "numeric_tolerance": 0.0,
        },
    }

    response = migration_client.post(
        f"/api/v1/projects/{project_id}/runs/multi-source",
        json={
            "sources": [
                {
                    "alias": "invoices",
                    "file_id": invoices["id"],
                    "is_primary": True,
                    "key_columns": ["inv_no"],
                },
                {
                    "alias": "payments",
                    "file_id": payments["id"],
                    "is_primary": False,
                    "key_columns": ["inv_no"],
                },
            ],
            "unified_keys": ["inv_no"],
            "rule_config": rule_config,
            "include_identical": True,
        },
    )
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "completed"
    assert run["summary"]["identical_matches"] == 0
    assert run["summary"]["field_mismatches"] == 1
    assert run["summary"]["total_discrepancies"] == 1

    items = _run_results(migration_client, project_id, run["id"])
    assert len(items) == 1
    item = items[0]
    assert item["match_status"] == "partial_payment"
    assert item["source_row_indices"] == {"invoices": 2, "payments": 2}
    assert item["aggregated_amount"] == 900.0
    assert item["expected_amount"] == 1000.0
    assert item["child_records"] == [
        {
            "source_row": 2,
            "receipt_id": "R-1",
            "amount": 600.0,
            "record": {
                "inv_no": "INV-900",
                "paid_amt": 600.0,
                "rec_no": "R-1",
            },
        },
        {
            "source_row": 3,
            "receipt_id": "R-2",
            "amount": 300.0,
            "record": {
                "inv_no": "INV-900",
                "paid_amt": 300.0,
                "rec_no": "R-2",
            },
        },
    ]

    db_rows = (
        migration_session.query(VerificationDiscrepancy)
        .filter(VerificationDiscrepancy.run_id == uuid.UUID(run["id"]))
        .all()
    )
    assert len(db_rows) == 1
    db_row = db_rows[0]
    assert [child["receipt_id"] for child in db_row.child_records] == ["R-1", "R-2"]
    assert db_row.aggregated_amount == 900.0
    assert db_row.expected_amount == 1000.0
    assert db_row.source_row_indices == {"invoices": 2, "payments": 2}
    assert db_row.source_records["payments"]["rec_no"] == "R-1"


def test_template_lifecycle_and_uniqueness_on_migrated_schema(
    migration_client: TestClient,
    migration_session: Session,
):
    template = _create_template(
        migration_client, "Alembic Template", description="Migrated schema"
    )
    assert template["source_count"] == 3
    assert template["config_version"] == 1
    assert template["visibility"] == "personal"

    fetched = migration_client.get(f"/api/v1/templates/{template['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["configuration"] == template["configuration"]
    assert fetched.json()["description"] == "Migrated schema"

    listed = migration_client.get("/api/v1/templates")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [template["id"]]

    duplicate = migration_client.post(
        "/api/v1/templates",
        json={
            "name": template["name"],
            "mode": "organization",
            "configuration": pilot._template_config(),
        },
    )
    assert duplicate.status_code == 409, duplicate.text

    # Prove the unique constraint itself exists in the Alembic-built schema,
    # independent of the service's friendly conflict check.
    row = migration_session.get(VerificationTemplate, uuid.UUID(template["id"]))
    assert row is not None
    migration_session.add(
        VerificationTemplate(
            owner_id=row.owner_id,
            name=template["name"],
            mode="organization",
            configuration=pilot._template_config(),
        )
    )
    with pytest.raises(IntegrityError):
        migration_session.commit()
    migration_session.rollback()

    deleted = migration_client.delete(f"/api/v1/templates/{template['id']}")
    assert deleted.status_code == 204, deleted.text
    assert migration_client.get("/api/v1/templates").json() == []


def test_transaction_rollback_and_uniqueness_on_migrated_schema(
    migration_session: Session,
):
    assert migration_session.query(VerificationTemplate).count() == 0

    user = User(
        email=f"migapp-rollback-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Rollback User",
    )
    migration_session.add(user)
    migration_session.commit()
    migration_session.refresh(user)

    template = VerificationTemplate(
        owner_id=user.id,
        name="Rollback Template",
        mode="organization",
        configuration=pilot._template_config(),
    )
    migration_session.add(template)
    migration_session.flush()
    assert migration_session.query(VerificationTemplate).count() == 1

    migration_session.rollback()
    assert migration_session.query(VerificationTemplate).count() == 0
    assert (
        migration_session.query(User).filter(User.id == user.id).count() == 1
    )

    first = VerificationTemplate(
        owner_id=user.id,
        name="Unique Template",
        mode="organization",
        configuration=pilot._template_config(),
    )
    migration_session.add(first)
    migration_session.commit()

    migration_session.add(
        VerificationTemplate(
            owner_id=user.id,
            name="Unique Template",
            mode="organization",
            configuration=pilot._template_config(),
        )
    )
    with pytest.raises(IntegrityError):
        migration_session.commit()
    migration_session.rollback()

    remaining = migration_session.query(VerificationTemplate).all()
    assert len(remaining) == 1
    assert remaining[0].name == "Unique Template"


def test_review_decision_workflow_and_retention_on_migrated_schema(
    migration_client: TestClient,
    migration_session: Session,
):
    project_id, files = pilot._upload_college_project(
        migration_client, "Review Retention Project"
    )
    payload = pilot._legacy_payload(files)
    run_resp = migration_client.post(
        f"/api/v1/projects/{project_id}/runs/multi-source", json=payload
    )
    assert run_resp.status_code == 201, run_resp.text
    run_id = run_resp.json()["id"]

    results = _run_results(migration_client, project_id, run_id)
    assert len(results) > 0
    disc = results[0]
    disc_id = disc["id"]

    # Apply single review decision
    rev_resp = migration_client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/reviews/{disc_id}",
        json={
            "decision": "APPROVE",
            "justification": "Approved valid variance per audit policy",
        },
    )
    assert rev_resp.status_code == 200, rev_resp.text
    review_data = rev_resp.json()
    assert review_data["decision"] == "APPROVE"
    assert review_data["new_status"] == "APPROVED"

    # Query DB directly for DiscrepancyReviewDecision
    dec_row = (
        migration_session.query(DiscrepancyReviewDecision)
        .filter(DiscrepancyReviewDecision.discrepancy_id == uuid.UUID(disc_id))
        .first()
    )
    assert dec_row is not None
    assert dec_row.decision == "APPROVE"
    assert dec_row.new_status == "APPROVED"
    assert dec_row.is_bulk_action is False

    # Verify retention: attempting to delete parent discrepancy must fail with RESTRICT FK violation
    with pytest.raises(IntegrityError):
        migration_session.execute(
            text('DELETE FROM verification_discrepancies WHERE id = :id'),
            {"id": uuid.UUID(disc_id)},
        )
        migration_session.commit()
    migration_session.rollback()

    # Verify audit event was created
    audit_resp = migration_client.get(
        f"/api/v1/projects/{project_id}/runs/{run_id}/audit-trail"
    )
    assert audit_resp.status_code == 200, audit_resp.text
    assert audit_resp.json()["is_chain_valid"] is True
    assert len(audit_resp.json()["items"]) >= 1

    # Verify cryptographic hash chain via verification endpoint
    verify_resp = migration_client.get(
        f"/api/v1/projects/{project_id}/runs/{run_id}/audit-trail/verify"
    )
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["is_valid"] is True
    assert verify_resp.json()["status"] == "VALID"


def test_governance_sign_off_lifecycle_on_migrated_schema(
    migration_client: TestClient,
    migration_session: Session,
):
    project_id, files = pilot._upload_college_project(
        migration_client, "Governance Sign-off Project"
    )
    payload = pilot._legacy_payload(files)
    run_resp = migration_client.post(
        f"/api/v1/projects/{project_id}/runs/multi-source", json=payload
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    # Propose sign-off
    prop_resp = migration_client.post(
        f"/api/v1/projects/{project_id}/runs/{run_id}/sign-off/propose",
        json={"note": "Ready for countersigning"},
    )
    assert prop_resp.status_code == 200, prop_resp.text
    assert prop_resp.json()["sign_off_status"] == "AWAITING_SIGN_OFF"

    # Verify run in DB
    db_run = migration_session.get(VerificationRun, uuid.UUID(run_id))
    assert db_run.sign_off_status == "AWAITING_SIGN_OFF"
    assert db_run.sign_off_proposed_by is not None

