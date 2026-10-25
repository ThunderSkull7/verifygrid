"""Unit and integration test suite for data profiling, pre-flight validation, and quarantine pipeline."""

import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas.profiling import (
    QuarantineReasonCode,
    QuarantineSeverity,
    ResolutionAction,
)
from app.services.profiling_service import profile_dataset_records


@pytest.fixture
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


def create_project(client: TestClient, name: str = "Profiling Test Project") -> str:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def upload_file(client: TestClient, project_id: str, filename: str, content: bytes, content_type: str = "text/csv") -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201
    return response.json()


def test_column_type_inference_and_metrics():
    """Verify inference of integers, floats, dates, booleans, and null/uniqueness calculations."""
    records = [
        (1, {"id": 1, "score": 98.5, "is_active": True, "joined_on": "2023-01-15", "notes": "first"}),
        (2, {"id": 2, "score": 85.0, "is_active": False, "joined_on": "2023-02-20", "notes": "second"}),
        (3, {"id": 3, "score": None, "is_active": True, "joined_on": "2023-03-25", "notes": "third"}),
        (4, {"id": 4, "score": 72.4, "is_active": None, "joined_on": None, "notes": None}),
    ]
    raw_headers = ["id", "score", "is_active", "joined_on", "notes"]
    mapping = {h: h for h in raw_headers}

    summary, quarantined = profile_dataset_records(
        file_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        filename="test_inference.csv",
        file_type="csv",
        records=records,
        raw_headers=raw_headers,
        column_mapping=mapping,
        null_set={"none", "null", ""},
    )

    assert summary.total_rows == 4
    col_dict = {c.column_name: c for c in summary.columns}

    # ID column: integer, 100% unique, zero nulls, candidate key
    assert col_dict["id"].inferred_type == "integer"
    assert col_dict["id"].null_count == 0
    assert col_dict["id"].uniqueness_ratio == 1.0
    assert col_dict["id"].is_candidate_key is True

    # Score column: float, 1 null (25%)
    assert col_dict["score"].inferred_type == "float"
    assert col_dict["score"].null_count == 1
    assert col_dict["score"].null_percentage == 25.0

    # is_active column: boolean
    assert col_dict["is_active"].inferred_type == "boolean"
    assert col_dict["is_active"].null_count == 1

    # joined_on: date
    assert col_dict["joined_on"].inferred_type == "date"
    assert col_dict["joined_on"].null_count == 1


def test_malformed_date_and_invalid_number_detection():
    """Verify malformed timestamps and non-numeric strings in numeric columns trigger quarantine."""
    records = [
        (1, {"account_id": "A101", "balance": "1050.25", "tx_date": "2023-05-01"}),
        (2, {"account_id": "A102", "balance": "NOT_A_NUMBER", "tx_date": "2023-05-02"}),  # Invalid number
        (3, {"account_id": "A103", "balance": "250.00", "tx_date": "INVALID_DATE_STR"}),   # Malformed date
    ]
    raw_headers = ["account_id", "balance", "tx_date"]
    mapping = {h: h for h in raw_headers}

    summary, quarantined = profile_dataset_records(
        file_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        filename="corrupt_samples.csv",
        file_type="csv",
        records=records,
        raw_headers=raw_headers,
        column_mapping=mapping,
        null_set={"none", "null", ""},
    )

    reasons = [q.quarantine_reason for q in quarantined]
    assert QuarantineReasonCode.INVALID_NUMBER in reasons
    assert QuarantineReasonCode.MALFORMED_DATE in reasons

    invalid_num_q = next(q for q in quarantined if q.quarantine_reason == QuarantineReasonCode.INVALID_NUMBER)
    assert invalid_num_q.source_row_index == 2
    assert invalid_num_q.column_name == "balance"
    assert invalid_num_q.severity == QuarantineSeverity.BLOCKING

    malformed_date_q = next(q for q in quarantined if q.quarantine_reason == QuarantineReasonCode.MALFORMED_DATE)
    assert malformed_date_q.source_row_index == 3
    assert malformed_date_q.column_name == "tx_date"
    assert malformed_date_q.severity == QuarantineSeverity.WARNING


def test_unexpected_negative_currency_amount():
    """Verify unexpected negative currency values are flagged with UNEXPECTED_NEGATIVE_AMOUNT."""
    records = [
        (1, {"item_id": "ITM-1", "price": 45.0, "salary": 50000}),
        (2, {"item_id": "ITM-2", "price": -15.5, "salary": 60000}),  # Suspicious negative price
        (3, {"item_id": "ITM-3", "price": 10.0, "salary": -12000}), # Suspicious negative salary
    ]
    raw_headers = ["item_id", "price", "salary"]
    mapping = {h: h for h in raw_headers}

    summary, quarantined = profile_dataset_records(
        file_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        filename="negative_amounts.csv",
        file_type="csv",
        records=records,
        raw_headers=raw_headers,
        column_mapping=mapping,
        null_set={"none", "null", ""},
    )

    neg_recs = [q for q in quarantined if q.quarantine_reason == QuarantineReasonCode.UNEXPECTED_NEGATIVE_AMOUNT]
    assert len(neg_recs) == 2
    flagged_cols = set(q.column_name for q in neg_recs)
    assert "price" in flagged_cols
    assert "salary" in flagged_cols


def test_shifted_row_detection():
    """Verify raw rows with mismatched delimiter counts are classified as SHIFTED_ROW."""
    records = [
        (1, {"col_a": "1", "col_b": "2", "col_c": "3"}),
    ]
    raw_headers = ["col_a", "col_b", "col_c"]
    mapping = {h: h for h in raw_headers}

    # Simulate CSV parse issue where row 2 had 4 columns instead of 3
    shifted_mismatches = [(2, 3, 4)]

    summary, quarantined = profile_dataset_records(
        file_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        filename="shifted.csv",
        file_type="csv",
        records=records,
        raw_headers=raw_headers,
        column_mapping=mapping,
        null_set={"none", "null", ""},
        raw_rows_with_mismatch=shifted_mismatches,
    )

    shifted_q = next((q for q in quarantined if q.quarantine_reason == QuarantineReasonCode.SHIFTED_ROW), None)
    assert shifted_q is not None
    assert shifted_q.source_row_index == 2
    assert shifted_q.severity == QuarantineSeverity.BLOCKING
    assert "row has 4 columns but header defines 3" in shifted_q.message


def test_candidate_key_collision_identification():
    """Verify duplicate candidate keys are identified and classified into quarantine."""
    records = [
        (1, {"emp_id": "E101", "name": "Alice"}),
        (2, {"emp_id": "E102", "name": "Bob"}),
        (3, {"emp_id": "E101", "name": "Alice Duplicate"}),  # Collision on E101
    ]
    raw_headers = ["emp_id", "name"]
    mapping = {h: h for h in raw_headers}

    summary, quarantined = profile_dataset_records(
        file_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        filename="key_dupes.csv",
        file_type="csv",
        records=records,
        raw_headers=raw_headers,
        column_mapping=mapping,
        null_set={"none", "null", ""},
    )

    dupe_key_records = [q for q in quarantined if q.quarantine_reason == QuarantineReasonCode.DUPLICATE_KEY]
    assert len(dupe_key_records) == 2
    flagged_rows = {q.source_row_index for q in dupe_key_records}
    assert flagged_rows == {1, 3}

    # Check CandidateKeyQuality recommendation
    key_eval = next(k for k in summary.candidate_keys if k.column_name == "emp_id")
    assert key_eval.is_viable_key is False
    assert key_eval.duplicate_count == 2


def test_api_profile_and_quarantine_endpoints(client: TestClient, upload_storage: Path):
    """Integration test for /profile, /quarantine, and /quarantine/resolve routes."""
    project_id = create_project(client, "Profile Endpoints Test")

    csv_data = (
        "id,tx_date,amount\n"
        "1,2023-01-01,100.00\n"
        "2,INVALID_DATE,250.00\n"  # Row 3 in CSV (header is line 1)
        "3,2023-01-03,-50.00\n"    # Row 4 in CSV: unexpected negative amount
    ).encode("utf-8")

    f_info = upload_file(client, project_id, "data.csv", csv_data)
    file_id = f_info["id"]

    # 1. GET /profile
    p_resp = client.get(f"/api/v1/projects/{project_id}/files/{file_id}/profile")
    assert p_resp.status_code == 200
    p_body = p_resp.json()
    assert p_body["file_id"] == file_id
    assert p_body["total_rows"] == 3
    assert len(p_body["columns"]) == 3
    assert p_body["impact_preview"]["total_source_rows"] == 3
    assert p_body["impact_preview"]["quarantined_rows_count"] >= 2

    # 2. GET /quarantine
    q_resp = client.get(f"/api/v1/projects/{project_id}/files/{file_id}/quarantine")
    assert q_resp.status_code == 200
    q_body = q_resp.json()
    assert q_body["file_id"] == file_id
    assert q_body["total_quarantined"] >= 2
    assert any(r["source_row_index"] == 3 for r in q_body["records"])
    assert any(r["source_row_index"] == 4 for r in q_body["records"])

    # 3. POST /quarantine/resolve -> EXCLUDE row 3, ACCEPT_AS_VALID row 4
    res_resp = client.post(
        f"/api/v1/projects/{project_id}/files/{file_id}/quarantine/resolve",
        json={
            "resolutions": [
                {"source_row_index": 3, "action": "EXCLUDE", "note": "Corrupt date"},
                {"source_row_index": 4, "action": "ACCEPT_AS_VALID", "note": "Legitimate refund"},
            ]
        },
    )
    assert res_resp.status_code == 200
    res_body = res_resp.json()
    assert res_body["resolved_count"] == 2
    assert 3 in res_body["excluded_row_indices"]
    assert 4 in res_body["accepted_row_indices"]

    # Verify impact preview updated
    impact = res_body["impact_preview"]
    assert impact["excluded_rows_count"] == 1
    assert impact["eligible_rows_count"] == 2  # Total 3 - 1 excluded = 2 eligible


def test_quarantine_exclusion_impact_on_reconciliation(client: TestClient, upload_storage: Path):
    """
    Integration test: Excluded quarantined rows must be omitted from reconciliation,
    directly reducing discrepancies and eligible record counts.
    """
    project_id = create_project(client, "Quarantine Reconciliation Test")

    # Source dataset has 3 data rows: row 3 (id=102) has corrupt amount
    src_csv = (
        "id,name,amount\n"
        "101,Alpha,500\n"
        "102,Beta,CORRUPT_NUM\n"
        "103,Gamma,700\n"
    ).encode("utf-8")

    # Target dataset has clean matching rows
    tgt_csv = (
        "id,name,amount\n"
        "101,Alpha,500\n"
        "102,Beta,600\n"
        "103,Gamma,700\n"
    ).encode("utf-8")

    f_src = upload_file(client, project_id, "src.csv", src_csv)
    f_tgt = upload_file(client, project_id, "tgt.csv", tgt_csv)

    # 1. Resolve source file quarantine: EXCLUDE row 3 (id=102)
    resolve_resp = client.post(
        f"/api/v1/projects/{project_id}/files/{f_src['id']}/quarantine/resolve",
        json={
            "resolutions": [
                {"source_row_index": 3, "action": "EXCLUDE", "note": "Exclude corrupt number"}
            ]
        },
    )
    assert resolve_resp.status_code == 200
    assert 3 in resolve_resp.json()["excluded_row_indices"]

    # 2. Run reconciliation without explicit excluded rows (auto-loaded from sidecar)
    verify_resp = client.post(
        f"/api/v1/projects/{project_id}/verify",
        json={
            "source_file_id": f_src["id"],
            "target_file_id": f_tgt["id"],
            "key_columns": ["id"],
        },
    )
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    summary = v_data["summary"]

    # Total source records should be 2 (row 3 was excluded before comparison!)
    assert summary["total_source_records"] == 2
    assert summary["matched_records"] == 2
    assert summary["identical_matches"] == 2
    # Row 102 was present in target but excluded in source -> missing in source
    assert summary["unmatched_target_records"] == 1
