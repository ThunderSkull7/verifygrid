"""Automated test suite for the Core Verification Engine."""

import io
import uuid
from pathlib import Path
from typing import Any, Dict, List

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas.result import (
    DiscrepancyCategory,
    MatchStatus,
    VerificationRequest,
)
from app.services.verification_engine import (
    compare_field_values,
    verify_datasets,
)


@pytest.fixture
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


def create_project(client: TestClient, name: str = "Verification Test Project") -> str:
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


def create_xlsx_bytes(rows: List[List[Any]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ==============================================================================
# 1. Unit Tests for compare_field_values
# ==============================================================================

def test_compare_field_values_null_handling():
    null_set = {"", "null", "none", "n/a", "na", "-"}

    # Both null representations
    match, diff_type, s_t, t_t = compare_field_values(None, "", null_set)
    assert match is True
    assert diff_type is None

    match, diff_type, s_t, t_t = compare_field_values("N/A", "null", null_set)
    assert match is True
    assert diff_type is None

    # One null, one value
    match, diff_type, s_t, t_t = compare_field_values(None, "Active", null_set)
    assert match is False
    assert diff_type == "null_mismatch"

    match, diff_type, s_t, t_t = compare_field_values("Active", "-", null_set)
    assert match is False
    assert diff_type == "null_mismatch"


def test_compare_field_values_numeric_and_currency():
    null_set = {""}

    # Integer and float equality
    match, diff_type, _, _ = compare_field_values(100, 100.0, null_set)
    assert match is True

    # Currency format with commas
    match, diff_type, _, _ = compare_field_values("$1,250.50", 1250.5, null_set)
    assert match is True

    # Accounting negative parenthesis format
    match, diff_type, _, _ = compare_field_values("(50.00)", -50.0, null_set)
    assert match is True

    # Numeric tolerance
    match, diff_type, _, _ = compare_field_values(100.005, 100.000, null_set, numeric_tolerance=0.01)
    assert match is True

    match, diff_type, _, _ = compare_field_values(100.005, 100.000, null_set, numeric_tolerance=0.0)
    assert match is False
    assert diff_type == "value_mismatch"


def test_compare_field_values_identifier_leading_zeros():
    null_set = {""}

    # Leading zeros should be preserved as strings and not coerced to numbers
    match, diff_type, s_t, t_t = compare_field_values("00123", "00123", null_set)
    assert match is True
    assert s_t == "identifier"

    match, diff_type, s_t, t_t = compare_field_values("00123", 123, null_set)
    assert match is False
    assert diff_type in ["value_mismatch", "type_mismatch"]


def test_compare_field_values_dates_and_booleans():
    null_set = {""}

    # Date normalization
    match, diff_type, _, _ = compare_field_values("2023-01-15", "2023-01-15 00:00:00", null_set)
    assert match is True

    # Booleans
    match, diff_type, _, _ = compare_field_values(True, "true", null_set)
    assert match is True

    match, diff_type, _, _ = compare_field_values(False, "no", null_set)
    assert match is True

    match, diff_type, _, _ = compare_field_values(True, False, null_set)
    assert match is False


# ==============================================================================
# 2. Service Layer Tests for verify_datasets
# ==============================================================================

def test_verify_fully_matching_datasets():
    source = [
        (1, {"id": "1", "name": "Alice", "dept": "Eng", "salary": 80000}),
        (2, {"id": "2", "name": "Bob", "dept": "Sales", "salary": 60000}),
    ]
    target = [
        (1, {"id": "1", "name": "Alice", "dept": "Eng", "salary": 80000}),
        (2, {"id": "2", "name": "Bob", "dept": "Sales", "salary": 60000}),
    ]

    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["id"],
    )

    assert summary.total_source_records == 2
    assert summary.total_target_records == 2
    assert summary.matched_records == 2
    assert summary.identical_matches == 2
    assert summary.field_mismatches == 0
    assert summary.unmatched_source_records == 0
    assert summary.unmatched_target_records == 0
    assert summary.duplicate_source_records == 0
    assert summary.duplicate_target_records == 0
    assert summary.total_discrepancies == 0
    assert len(results) == 2
    assert len(discrepancies) == 0
    assert results[0].match_status == MatchStatus.IDENTICAL
    assert results[0].discrepancy_category == DiscrepancyCategory.NONE


def test_verify_records_missing_from_either_dataset():
    source = [
        (1, {"id": "1", "name": "Alice"}),
        (2, {"id": "2", "name": "Bob"}),
    ]
    target = [
        (1, {"id": "2", "name": "Bob"}),
        (2, {"id": "3", "name": "Charlie"}),
    ]

    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["id"],
    )

    assert summary.total_source_records == 2
    assert summary.total_target_records == 2
    assert summary.matched_records == 1
    assert summary.identical_matches == 1
    assert summary.unmatched_source_records == 1  # id 1
    assert summary.unmatched_target_records == 1  # id 3
    assert summary.total_discrepancies == 2

    # Check discrepancies details
    disc_map = {d.key_values["id"]: d for d in discrepancies}
    assert "1" in disc_map
    assert disc_map["1"].match_status == MatchStatus.MISSING_IN_TARGET
    assert disc_map["1"].discrepancy_category == DiscrepancyCategory.MISSING_RECORD
    assert disc_map["1"].source_row_number == 1
    assert disc_map["1"].target_row_number is None

    assert "3" in disc_map
    assert disc_map["3"].match_status == MatchStatus.MISSING_IN_SOURCE
    assert disc_map["3"].discrepancy_category == DiscrepancyCategory.MISSING_RECORD
    assert disc_map["3"].source_row_number is None
    assert disc_map["3"].target_row_number == 2


def test_verify_field_level_mismatches():
    source = [
        (1, {"id": "100", "status": "Pending", "amount": 1500.0, "currency": "USD"}),
    ]
    target = [
        (1, {"id": "100", "status": "Approved", "amount": 1600.0, "currency": "USD"}),
    ]

    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["id"],
    )

    assert summary.matched_records == 1
    assert summary.identical_matches == 0
    assert summary.field_mismatches == 1
    assert summary.records_with_differences == 1
    assert summary.total_discrepancies == 1
    assert len(discrepancies) == 1

    disc = discrepancies[0]
    assert disc.match_status == MatchStatus.FIELD_MISMATCH
    assert disc.discrepancy_category == DiscrepancyCategory.FIELD_MISMATCH
    assert len(disc.field_differences) == 2

    diff_map = {f.field_name: f for f in disc.field_differences}
    assert diff_map["status"].source_value == "Pending"
    assert diff_map["status"].target_value == "Approved"
    assert diff_map["amount"].source_value == 1500.0
    assert diff_map["amount"].target_value == 1600.0


def test_verify_duplicate_keys_detection_without_discarding():
    # Source has key 'dup' on rows 1 and 2
    # Target has key 'dup' on row 1
    source = [
        (1, {"id": "dup", "val": "A"}),
        (2, {"id": "dup", "val": "B"}),
        (3, {"id": "unique_src", "val": "C"}),
    ]
    target = [
        (1, {"id": "dup", "val": "A"}),
        (2, {"id": "unique_tgt", "val": "D"}),
    ]

    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["id"],
    )

    assert summary.duplicate_source_records == 2
    assert summary.duplicate_source_keys_count == 1
    assert summary.conflicting_duplicate_records == 1
    assert summary.matched_records == 0  # No 1-to-1 match because 'dup' is duplicated!

    # Verify duplicate is reported with all source row references
    dup_disc = [d for d in discrepancies if d.key_values["id"] == "dup"][0]
    assert dup_disc.match_status == MatchStatus.AMBIGUOUS_DUPLICATE
    assert dup_disc.discrepancy_category == DiscrepancyCategory.DUPLICATE_KEY
    assert dup_disc.source_row_numbers == [1, 2]
    assert dup_disc.target_row_numbers == [1]


def test_verify_composite_matching_keys():
    source = [
        (1, {"company": "ACME", "dept": "HR", "budget": 1000}),
        (2, {"company": "ACME", "dept": "ENG", "budget": 5000}),
        (3, {"company": "BETA", "dept": "HR", "budget": 2000}),
    ]
    target = [
        (1, {"company": "ACME", "dept": "HR", "budget": 1000}),
        (2, {"company": "ACME", "dept": "ENG", "budget": 5500}),  # mismatch in budget
        (3, {"company": "GAMMA", "dept": "HR", "budget": 2000}), # missing in source
    ]

    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["company", "dept"],
    )

    assert summary.matched_records == 2
    assert summary.identical_matches == 1  # ACME / HR
    assert summary.field_mismatches == 1   # ACME / ENG
    assert summary.unmatched_source_records == 1  # BETA / HR
    assert summary.unmatched_target_records == 1  # GAMMA / HR
    assert summary.total_discrepancies == 3


def test_verify_column_mapping_with_different_headers():
    source = [
        (1, {"src_id": "01", "base_salary": 5000}),
    ]
    target = [
        (1, {"tgt_id": "01", "remuneration": 5000}),
    ]

    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["src_id"],
        column_mapping={
            "src_id": "tgt_id",
            "base_salary": "remuneration",
        },
    )

    assert summary.matched_records == 1
    assert summary.identical_matches == 1
    assert summary.field_mismatches == 0
    assert summary.total_discrepancies == 0


def test_verify_empty_and_single_empty_datasets():
    # Both empty
    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=[],
        target_records=[],
        key_columns=["id"],
    )
    assert summary.total_source_records == 0
    assert summary.total_target_records == 0
    assert summary.total_discrepancies == 0

    # Source has data, target is empty
    source = [(1, {"id": "1", "val": "X"})]
    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=source,
        target_records=[],
        key_columns=["id"],
    )
    assert summary.total_source_records == 1
    assert summary.total_target_records == 0
    assert summary.unmatched_source_records == 1
    assert summary.total_discrepancies == 1


def test_verify_invalid_key_columns_raises_422():
    source = [(1, {"id": "1", "val": "A"})]
    target = [(1, {"id": "1", "val": "A"})]

    # Empty key column
    with pytest.raises(Exception):
        verify_datasets(source, target, key_columns=[])

    # Non-existent key column in source
    with pytest.raises(Exception) as exc_info:
        verify_datasets(source, target, key_columns=["non_existent_key"])
    assert "non_existent_key" in str(exc_info.value)


# ==============================================================================
# 3. End-to-End API Tests with FastAPI TestClient
# ==============================================================================

def test_api_verify_csv_and_xlsx_end_to_end(client: TestClient, upload_storage: Path):
    project_id = create_project(client, "End-to-End Verification Project")

    # Upload source CSV
    csv_bytes = (
        "emp_id, full_name, department, salary\n"
        "001, Alice Smith, Engineering, 80000\n"
        "002, Bob Jones, Sales, 60000\n"
        "003, Charlie Brown, Marketing, 55000\n"
    ).encode("utf-8")
    src_upload = upload_file(client, project_id, "primary.csv", csv_bytes, "text/csv")

    # Upload target XLSX with:
    # 001 identical
    # 002 salary mismatch (65000)
    # 004 new employee (missing in source)
    xlsx_bytes = create_xlsx_bytes([
        ["emp_id", "full_name", "department", "salary"],
        ["001", "Alice Smith", "Engineering", 80000],
        ["002", "Bob Jones", "Sales", 65000],
        ["004", "David Clark", "Finance", 70000],
    ])
    tgt_upload = upload_file(client, project_id, "secondary.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # Trigger verification
    payload = {
        "source_file_id": src_upload["id"],
        "target_file_id": tgt_upload["id"],
        "key_columns": ["emp_id"],
    }
    response = client.post(f"/api/v1/projects/{project_id}/verify", json=payload)
    assert response.status_code == 200
    data = response.json()

    summary = data["summary"]
    assert summary["total_source_records"] == 3
    assert summary["total_target_records"] == 3
    assert summary["matched_records"] == 2
    assert summary["identical_matches"] == 1
    assert summary["field_mismatches"] == 1
    assert summary["unmatched_source_records"] == 1  # 003
    assert summary["unmatched_target_records"] == 1  # 004
    assert summary["total_discrepancies"] == 3

    # Discrepancies check
    discrepancies = data["discrepancies"]
    assert len(discrepancies) == 3

    # Check 002 mismatch
    mismatch_002 = [d for d in discrepancies if d["key_values"]["emp_id"] == "001" or d["key_values"].get("emp_id") == "002"][0]
    assert mismatch_002["match_status"] == "field_mismatch"
    assert mismatch_002["discrepancy_category"] == "field_mismatch"
    diff = mismatch_002["field_differences"][0]
    assert diff["field_name"] == "salary"
    assert diff["source_value"] == 60000
    assert diff["target_value"] == 65000


def test_api_verify_project_isolation(client: TestClient, upload_storage: Path):
    proj_a = create_project(client, "Project A")
    proj_b = create_project(client, "Project B")

    csv_bytes = "id,name\n1,Alice\n".encode("utf-8")
    file_a = upload_file(client, proj_a, "file_a.csv", csv_bytes)
    file_b = upload_file(client, proj_b, "file_b.csv", csv_bytes)

    # Attempt to verify file_b (Project B) under Project A -> 404
    payload = {
        "source_file_id": file_a["id"],
        "target_file_id": file_b["id"],
        "key_columns": ["id"],
    }
    response = client.post(f"/api/v1/projects/{proj_a}/verify", json=payload)
    assert response.status_code == 404
    assert "Source file not found" in response.json()["detail"] or "Target file not found" in response.json()["detail"]


def test_api_verify_invalid_key_returns_422(client: TestClient, upload_storage: Path):
    proj = create_project(client, "Project Keys")
    csv_bytes = "id,name\n1,Alice\n".encode("utf-8")
    file_1 = upload_file(client, proj, "f1.csv", csv_bytes)
    file_2 = upload_file(client, proj, "f2.csv", csv_bytes)

    # Missing key column
    payload = {
        "source_file_id": file_1["id"],
        "target_file_id": file_2["id"],
        "key_columns": ["non_existent_col"],
    }
    response = client.post(f"/api/v1/projects/{proj}/verify", json=payload)
    assert response.status_code == 422
    assert "non_existent_col" in response.json()["detail"]


def test_api_verify_empty_keys_returns_422(client: TestClient, upload_storage: Path):
    proj = create_project(client, "Project Empty Keys")
    csv_bytes = "id,name\n1,Alice\n".encode("utf-8")
    f1 = upload_file(client, proj, "f1.csv", csv_bytes)
    f2 = upload_file(client, proj, "f2.csv", csv_bytes)

    payload = {
        "source_file_id": f1["id"],
        "target_file_id": f2["id"],
        "key_columns": [],
    }
    response = client.post(f"/api/v1/projects/{proj}/verify", json=payload)
    assert response.status_code == 422


def test_verify_duplicate_in_both_and_target_only():
    # Target only duplicate
    source_1 = [(1, {"id": "1", "val": "A"})]
    target_1 = [(1, {"id": "1", "val": "A"}), (2, {"id": "1", "val": "B"})]

    summary_1, _, disc_1, _, _ = verify_datasets(
        source_records=source_1,
        target_records=target_1,
        key_columns=["id"],
    )
    assert summary_1.duplicate_target_records == 2
    assert summary_1.duplicate_target_keys_count == 1
    assert summary_1.conflicting_duplicate_records == 1
    assert disc_1[0].match_status == MatchStatus.AMBIGUOUS_DUPLICATE

    # Duplicate in both source and target
    source_2 = [(1, {"id": "1", "val": "A"}), (2, {"id": "1", "val": "B"})]
    target_2 = [(1, {"id": "1", "val": "C"}), (2, {"id": "1", "val": "D"})]

    summary_2, _, disc_2, _, _ = verify_datasets(
        source_records=source_2,
        target_records=target_2,
        key_columns=["id"],
    )
    assert summary_2.duplicate_source_records == 2
    assert summary_2.duplicate_target_records == 2
    assert summary_2.duplicate_source_keys_count == 1
    assert summary_2.duplicate_target_keys_count == 1
    assert disc_2[0].match_status == MatchStatus.DUPLICATE_KEY_BOTH


def test_verify_ignore_columns_and_compare_columns():
    source = [(1, {"id": "1", "salary": 5000, "notes": "source note", "bonus": 500})]
    target = [(1, {"id": "1", "salary": 5000, "notes": "different note", "bonus": 999})]

    # If notes is ignored and bonus is ignored
    summary, results, discrepancies, _, _ = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["id"],
        ignore_columns=["notes", "bonus"],
    )
    assert summary.identical_matches == 1
    assert summary.field_mismatches == 0
    assert len(discrepancies) == 0

    # If only salary is compared
    summary2, results2, discrepancies2, _, _ = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["id"],
        compare_columns=["salary"],
    )
    assert summary2.identical_matches == 1
    assert summary2.field_mismatches == 0


def test_verify_string_case_and_whitespace_options():
    source = [(1, {"id": "1", "status": " ACTIVE "})]
    target = [(1, {"id": "1", "status": "active"})]

    # Without ignore_case: should mismatch
    _, _, disc_case_sensitive, _, _ = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["id"],
        ignore_whitespace=True,
        ignore_case=False,
    )
    assert len(disc_case_sensitive) == 1

    # With ignore_case: should match
    summary, _, disc_case_insensitive, _, _ = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["id"],
        ignore_whitespace=True,
        ignore_case=True,
    )
    assert summary.identical_matches == 1
    assert len(disc_case_insensitive) == 0


def test_api_verify_invalid_column_mapping_returns_422(client: TestClient, upload_storage: Path):
    proj = create_project(client, "Project Mapping")
    csv_bytes = "id,name\n1,Alice\n".encode("utf-8")
    f1 = upload_file(client, proj, "f1.csv", csv_bytes)
    f2 = upload_file(client, proj, "f2.csv", csv_bytes)

    # Invalid source column in column_mapping
    payload = {
        "source_file_id": f1["id"],
        "target_file_id": f2["id"],
        "key_columns": ["id"],
        "column_mapping": {"non_existent": "name"},
    }
    response = client.post(f"/api/v1/projects/{proj}/verify", json=payload)
    assert response.status_code == 422
    assert "non_existent" in response.json()["detail"]


def test_api_verify_file_against_itself(client: TestClient, upload_storage: Path):
    proj = create_project(client, "Self Compare Project")
    csv_bytes = "emp_id,score\nE1,95\nE2,88\n".encode("utf-8")
    f1 = upload_file(client, proj, "scores.csv", csv_bytes)

    payload = {
        "source_file_id": f1["id"],
        "target_file_id": f1["id"],
        "key_columns": ["emp_id"],
    }
    response = client.post(f"/api/v1/projects/{proj}/verify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["matched_records"] == 2
    assert data["summary"]["identical_matches"] == 2
    assert data["summary"]["total_discrepancies"] == 0

