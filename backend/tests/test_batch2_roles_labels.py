"""Batch 2 tests: editable labels, explicit source roles, and role invariants."""

import io
from pathlib import Path

from fastapi.testclient import TestClient

from app.schemas.multisource import SourceDefinition
from app.services.profiling_service import (  # noqa: F401  (keeps import parity with wizard suite)
    discover_multisource_candidate_keys,
)


# Reuse the project/upload helpers by importing from the wizard test module.
# (Same helpers, no duplicated fixtures.)
import tests.test_multisource_wizard as wizard  # noqa: E402

create_project = wizard.create_project
upload_csv = wizard.upload_csv
upload_storage = wizard.upload_storage


MULTI_SOURCE_RUN = "/runs/multi-source"
MULTI_SOURCE_VERIFY = "/verify/multi-source"


def _post_both(client: TestClient, project_id: str, payload: dict):
    return [
        client.post(f"/api/v1/projects/{project_id}{MULTI_SOURCE_VERIFY}", json=payload),
        client.post(f"/api/v1/projects/{project_id}{MULTI_SOURCE_RUN}", json=payload),
    ]


def test_legacy_request_without_new_fields_still_accepted(client: TestClient, upload_storage: Path):
    """Existing payloads (no label field) continue to work on both endpoints."""
    proj_id = create_project(client, "Legacy Fields Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,val\n1,10\n2,20\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,val\n1,10\n2,25\n")

    payload = {
        "sources": [
            {"alias": "a", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"]},
            {"alias": "b", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"]},
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    responses = _post_both(client, proj_id, payload)
    for res in responses:
        assert res.status_code in (200, 201), res.text
    assert responses[1].json()["summary"]["field_mismatches"] == 1


def test_labels_accepted_whitespace_trimmed_and_persisted(client: TestClient, upload_storage: Path):
    """New label field is accepted, trimmed, and round-trips through persistence."""
    proj_id = create_project(client, "Labeled Sources Project")

    f1 = upload_csv(client, proj_id, "academic.csv", "enrol,grade\nE-1001,A\nE-1002,B\n")
    f2 = upload_csv(client, proj_id, "idcard.csv", "enrol,grade\nE-1001,A\nE-1002,C\n")

    run_res = client.post(
        f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}",
        json={
            "sources": [
                {"alias": "academic", "label": "  Academic Records  ", "file_id": f1["id"], "is_primary": True, "key_columns": ["enrol"]},
                {"alias": "idcard", "label": "ID Card Records", "file_id": f2["id"], "is_primary": False, "key_columns": ["enrol"]},
            ],
            "unified_keys": ["enrol"],
            "compare_attributes": ["grade"],
            "include_identical": True,
        },
    )
    assert run_res.status_code == 201, run_res.text
    run_data = run_res.json()
    labels = {s["alias"]: s.get("label") for s in run_data["sources"]}
    assert labels["academic"] == "Academic Records"
    assert labels["idcard"] == "ID Card Records"

    persisted = client.get(f"/api/v1/projects/{proj_id}/runs/{run_data['id']}").json()
    assert persisted["sources"] == run_data["sources"]


def test_blank_label_normalizes_to_none():
    definition = SourceDefinition(
        alias="a",
        label="   ",
        file_id="00000000-0000-0000-0000-000000000001",
        key_columns=["id"],
    )
    assert definition.label is None


def test_label_max_length_constrained(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Long Label Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,val\n1,10\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,val\n1,10\n")

    res = client.post(
        f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}",
        json={
            "sources": [
                {"alias": "a", "label": "x" * 121, "file_id": f1["id"], "is_primary": True, "key_columns": ["id"]},
                {"alias": "b", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"]},
            ],
            "unified_keys": ["id"],
        },
    )
    assert res.status_code == 422


def test_zero_primary_sources_rejected_on_every_request(client: TestClient, upload_storage: Path):
    """The server must refuse to run verification with no primary source."""
    proj_id = create_project(client, "Missing Primary Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,val\n1,10\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,val\n1,12\n")

    payload = {
        "sources": [
            {"alias": "a", "file_id": f1["id"], "is_primary": False, "key_columns": ["id"]},
            {"alias": "b", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"]},
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
    }
    for res in _post_both(client, proj_id, payload):
        assert res.status_code == 422, res.text
        assert "primary source" in str(res.json()["detail"])


def test_multiple_primary_sources_rejected_until_batch5(client: TestClient, upload_storage: Path):
    """Multiple primaries are a UI-allowed selection but unsupported by the current engine."""
    proj_id = create_project(client, "Multiple Primary Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,val\n1,10\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,val\n1,10\n")

    payload = {
        "sources": [
            {"alias": "a", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"]},
            {"alias": "b", "file_id": f2["id"], "is_primary": True, "key_columns": ["id"]},
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
    }
    for res in _post_both(client, proj_id, payload):
        assert res.status_code == 422, res.text
        detail = str(res.json()["detail"])
        assert "multi-primary" in detail
        assert "not enabled" in detail


def test_duplicate_aliases_rejected(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Duplicate Alias Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,val\n1,10\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,val\n1,10\n")

    res = client.post(
        f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}",
        json={
            "sources": [
                {"alias": "dup", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"]},
                {"alias": "dup", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"]},
            ],
            "unified_keys": ["id"],
        },
    )
    assert res.status_code == 422
    assert "unique" in str(res.json()["detail"]).lower()


def test_cross_project_file_access_rejected(client: TestClient, upload_storage: Path):
    """A multi-source request cannot reference files owned by another project."""
    proj_a = create_project(client, "Owner Project")
    proj_b = create_project(client, "Unauthorized Project")
    f_other = upload_csv(client, proj_b, "secret.csv", "id,val\n1,99\n")
    f_own1 = upload_csv(client, proj_a, "own1.csv", "id,val\n1,10\n")
    f_own2 = upload_csv(client, proj_a, "own2.csv", "id,val\n1,20\n")

    res = client.post(
        f"/api/v1/projects/{proj_a}{MULTI_SOURCE_VERIFY}",
        json={
            "sources": [
                {"alias": "foreign", "file_id": f_other["id"], "is_primary": True, "key_columns": ["id"]},
                {"alias": "own1", "file_id": f_own1["id"], "is_primary": False, "key_columns": ["id"]},
                {"alias": "own2", "file_id": f_own2["id"], "is_primary": False, "key_columns": ["id"]},
            ],
            "unified_keys": ["id"],
        },
    )
    assert res.status_code == 404
    assert "not found for this project" in str(res.json()["detail"])


def test_upload_type_validation_unchanged(client: TestClient, upload_storage: Path):
    """Unsupported file types are still rejected by the existing ingestion path."""
    proj_id = create_project(client, "Upload Validation Project")
    res = client.post(
        f"/api/v1/projects/{proj_id}/files",
        files={"file": ("evil.exe", io.BytesIO(b"MZ9090"), "application/octet-stream")},
    )
    assert res.status_code == 422
    assert "CSV and XLSX" in str(res.json()["detail"])
