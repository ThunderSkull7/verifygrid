"""Automated test suite for data preprocessing and normalization layer."""

import io
import uuid
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


@pytest.fixture
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


def create_project(client: TestClient, name: str = "Test Project") -> str:
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


def create_xlsx_bytes(rows: list[list]) -> bytes:
    """Helper to generate in-memory XLSX file content."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# 1. Valid CSV and XLSX files
# ---------------------------------------------------------------------------

def test_preprocess_valid_csv(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    csv_content = (
        'Employee ID, Full Name , Department , Salary , Start Date \n'
        '00101,  Alice Smith , Engineering , "$85,000.50" , 2023-01-15 \n'
        '00102, Bob Jones , Sales , 62000 , 2022-06-01 \n'
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "employees.csv", csv_content)
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    assert data["source_file_id"] == file_id
    assert data["project_id"] == project_id
    assert data["original_filename"] == "employees.csv"
    assert data["file_type"] == "csv"
    assert data["data_rows_count"] == 2
    assert data["empty_rows_count"] == 0
    assert data["duplicate_rows_count"] == 0

    # Column mappings
    mapping = data["column_mapping"]
    assert mapping["Employee ID"] == "employee_id"
    assert mapping["Full Name"] == "full_name"
    assert mapping["Department"] == "department"
    assert mapping["Salary"] == "salary"
    assert mapping["Start Date"] == "start_date"

    # Leading zeros preserved as identifier
    col_dict = {c["normalized_name"]: c for c in data["columns"]}
    assert col_dict["employee_id"]["detected_type"] == "identifier"
    assert col_dict["salary"]["detected_type"] in ["float", "integer"]
    assert col_dict["start_date"]["detected_type"] == "date"

    # Preview rows
    assert len(data["preview_rows"]) == 2
    row0 = data["preview_rows"][0]
    assert row0["source_row_number"] == 2
    assert row0["employee_id"] == "00101"
    assert row0["full_name"] == "Alice Smith"
    assert row0["salary"] == 85000.5
    assert row0["start_date"] == "2023-01-15"


def test_preprocess_valid_xlsx(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    xlsx_bytes = create_xlsx_bytes([
        ["Product Code", "Unit Price", "In Stock"],
        ["0099", 19.99, "true"],
        ["0100", 45.00, "false"],
    ])

    file_info = upload_file(
        client,
        project_id,
        "inventory.xlsx",
        xlsx_bytes,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    assert data["file_type"] == "xlsx"
    assert data["data_rows_count"] == 2
    col_dict = {c["normalized_name"]: c for c in data["columns"]}
    assert col_dict["product_code"]["detected_type"] == "identifier"
    assert col_dict["in_stock"]["detected_type"] == "boolean"

    preview = data["preview_rows"]
    assert preview[0]["product_code"] == "0099"
    assert preview[0]["in_stock"] is True
    assert preview[1]["product_code"] == "0100"
    assert preview[1]["in_stock"] is False


# ---------------------------------------------------------------------------
# 2. Empty files and missing headers
# ---------------------------------------------------------------------------

def test_preprocess_empty_file(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    file_info = upload_file(client, project_id, "empty.csv", b"")
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    # Should report an error issue
    error_issues = [i for i in data["issues"] if i["level"] == "error"]
    assert len(error_issues) > 0
    assert any(i["issue_type"] == "empty_file" for i in error_issues)


def test_preprocess_missing_headers_whitespace_only(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    file_info = upload_file(client, project_id, "blank_lines.csv", b"   \n\n\t\n  \n")
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    error_issues = [i for i in data["issues"] if i["level"] == "error"]
    assert len(error_issues) > 0
    assert any(i["issue_type"] in ["empty_file", "missing_headers"] for i in error_issues)


# ---------------------------------------------------------------------------
# 3. Duplicate column names
# ---------------------------------------------------------------------------

def test_preprocess_duplicate_column_names(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    csv_content = (
        "id,name,id,address,name\n"
        "1,Alice,X1,123 Main,Ali\n"
        "2,Bob,X2,456 Oak,Bobby\n"
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "dups.csv", csv_content)
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    col_names = [c["normalized_name"] for c in data["columns"]]
    # Duplicate names must be deduplicated with suffix
    assert col_names == ["id", "name", "id_1", "address", "name_1"]

    dup_warnings = [i for i in data["issues"] if i["issue_type"] == "duplicate_header"]
    assert len(dup_warnings) >= 2


# ---------------------------------------------------------------------------
# 4. Empty rows and whitespace normalization
# ---------------------------------------------------------------------------

def test_preprocess_empty_rows_and_whitespace(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    csv_content = (
        "code,label\n"
        "  A10  ,  First Item  \n"
        "   ,   \n"  # Completely empty row
        "  B20  ,  Second Item  \n"
        ",\n"          # Another empty row
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "items.csv", csv_content)
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    assert data["empty_rows_count"] == 2
    assert data["data_rows_count"] == 2

    # Check whitespace trimming
    preview = data["preview_rows"]
    assert preview[0]["code"] == "A10"
    assert preview[0]["label"] == "First Item"
    assert preview[1]["code"] == "B20"
    assert preview[1]["label"] == "Second Item"

    empty_warnings = [i for i in data["issues"] if i["issue_type"] == "empty_rows"]
    assert len(empty_warnings) == 1


# ---------------------------------------------------------------------------
# 5. Null values and date/number handling
# ---------------------------------------------------------------------------

def test_preprocess_custom_null_values(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    csv_content = (
        "id,status,score\n"
        "1,N/A,100\n"
        "2,Active,null\n"
        "3,UNKNOWN,-\n"
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "custom_nulls.csv", csv_content)
    file_id = file_info["id"]

    # Configure custom null representation including 'UNKNOWN'
    config = {
        "null_values": ["n/a", "null", "-", "unknown"],
        "normalize_numbers": True,
    }
    response = client.post(
        f"/api/v1/projects/{project_id}/files/{file_id}/preprocess",
        json=config,
    )
    assert response.status_code == 200
    data = response.json()

    preview = data["preview_rows"]
    assert preview[0]["status"] is None
    assert preview[0]["score"] == 100
    assert preview[1]["status"] == "Active"
    assert preview[1]["score"] is None
    assert preview[2]["status"] is None
    assert preview[2]["score"] is None


def test_preprocess_accounting_numbers_and_currency(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    csv_content = (
        'transaction_id,amount,balance\n'
        'T1,"$1,250.75",(50.25)\n'
        'T2,€500.00,1000\n'
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "finance.csv", csv_content)
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    preview = data["preview_rows"]
    assert preview[0]["amount"] == 1250.75
    assert preview[0]["balance"] == -50.25
    assert preview[1]["amount"] == 500.0
    assert preview[1]["balance"] == 1000


# ---------------------------------------------------------------------------
# 6. Identifiers containing leading zeros
# ---------------------------------------------------------------------------

def test_preprocess_preserves_leading_zeros(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    csv_content = (
        "zip_code,roll_number,numeric_val\n"
        "02138,0001,42\n"
        "00501,0045,100\n"
        "08000,0999,0\n"
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "students.csv", csv_content)
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    preview = data["preview_rows"]
    # Identifiers MUST keep their leading zeros as strings
    assert preview[0]["zip_code"] == "02138"
    assert preview[0]["roll_number"] == "0001"
    assert preview[0]["numeric_val"] == 42

    assert preview[1]["zip_code"] == "00501"
    assert preview[1]["roll_number"] == "0045"
    assert preview[1]["numeric_val"] == 100

    col_dict = {c["normalized_name"]: c for c in data["columns"]}
    assert col_dict["zip_code"]["detected_type"] == "identifier"
    assert col_dict["roll_number"]["detected_type"] == "identifier"
    assert col_dict["numeric_val"]["detected_type"] == "integer"


def test_preprocess_configured_identifier_columns(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    # Column has no leading zeros, but caller explicitly registers it as an identifier
    csv_content = (
        "account_num,amount\n"
        "12345678,500\n"
        "87654321,250\n"
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "accounts.csv", csv_content)
    file_id = file_info["id"]

    config = {
        "identifier_columns": ["account_num"],
        "normalize_numbers": True,
    }
    response = client.post(
        f"/api/v1/projects/{project_id}/files/{file_id}/preprocess",
        json=config,
    )
    assert response.status_code == 200
    data = response.json()

    preview = data["preview_rows"]
    assert preview[0]["account_num"] == "12345678"
    assert isinstance(preview[0]["account_num"], str)
    assert preview[0]["amount"] == 500

    col_dict = {c["normalized_name"]: c for c in data["columns"]}
    assert col_dict["account_num"]["detected_type"] == "identifier"


# ---------------------------------------------------------------------------
# 7. Duplicate records detection without auto-deleting
# ---------------------------------------------------------------------------

def test_preprocess_detects_duplicate_records_without_deleting(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    csv_content = (
        "id,name,dept\n"
        "1,Alice,HR\n"
        "2,Bob,IT\n"
        "1,Alice,HR\n"  # Exact duplicate of row 2 (source row 4)
        "3,Charlie,Finance\n"
        "1,Alice,HR\n"  # Another duplicate of row 2 (source row 6)
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "records.csv", csv_content)
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    # All 5 records are preserved in data rows
    assert data["data_rows_count"] == 5
    assert data["duplicate_rows_count"] == 3

    dup_groups = data["duplicate_record_row_numbers"]
    assert len(dup_groups) == 1
    # 1-based source row numbers: header is 1, so row 2, 4, 6 are identical
    assert dup_groups[0] == [2, 4, 6]

    dup_warnings = [i for i in data["issues"] if i["issue_type"] == "duplicate_records"]
    assert len(dup_warnings) == 1


# ---------------------------------------------------------------------------
# 8. Type mismatch / inconsistency detection
# ---------------------------------------------------------------------------

def test_preprocess_inconsistent_column_types(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    # Column 'amount' has numeric values except on row 4 which has string 'invalid_text'
    csv_content = (
        "id,amount\n"
        "1,100\n"
        "2,200\n"
        "3,CORRUPT_VALUE\n"
        "4,400\n"
        "5,500\n"
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "corrupt.csv", csv_content)
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    type_warnings = [i for i in data["issues"] if i["issue_type"] == "type_mismatch"]
    assert len(type_warnings) >= 1
    mismatch = type_warnings[0]
    assert mismatch["row_number"] == 4
    assert mismatch["column_name"] == "amount"
    assert "CORRUPT_VALUE" in mismatch["message"]


# ---------------------------------------------------------------------------
# 9. Project isolation & 404 security checks
# ---------------------------------------------------------------------------

def test_preprocess_project_isolation(client: TestClient, upload_storage: Path):
    p1 = create_project(client, "Project 1")
    p2 = create_project(client, "Project 2")

    file_info = upload_file(client, p1, "p1_data.csv", b"id,val\n1,A\n")
    file_id = file_info["id"]

    # Attempting to access p1 file via p2 URL must return 404
    response = client.post(f"/api/v1/projects/{p2}/files/{file_id}/preprocess")
    assert response.status_code == 404
    assert response.json()["detail"] == "Source file not found for this project."


def test_preprocess_nonexistent_project(client: TestClient):
    random_project = str(uuid.uuid4())
    random_file = str(uuid.uuid4())
    response = client.post(f"/api/v1/projects/{random_project}/files/{random_file}/preprocess")
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."


def test_preprocess_no_path_leakage_in_errors(client: TestClient, upload_storage: Path):
    # Ensure error messages never leak filesystem paths like "C:\Users" or "/storage"
    project_id = create_project(client)
    file_info = upload_file(client, project_id, "empty_leak_check.csv", b"")
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    for issue in data["issues"]:
        assert "storage" not in issue["message"].lower()
        assert "\\" not in issue["message"]
        assert "users" not in issue["message"].lower()


def test_preprocess_malformed_csv_row_field_count(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    # Row 3 has 3 fields instead of 2
    csv_content = (
        "id,name\n"
        "1,Alice\n"
        "2,Bob,ExtraField\n"
        "3,Charlie\n"
    ).encode("utf-8")

    file_info = upload_file(client, project_id, "malformed.csv", csv_content)
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    malformed_issues = [i for i in data["issues"] if i["issue_type"] == "malformed_row"]
    assert len(malformed_issues) == 1
    assert malformed_issues[0]["row_number"] == 3


def test_preprocess_corrupted_xlsx(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    corrupted_bytes = b"not a valid zip or excel archive"

    file_info = upload_file(
        client,
        project_id,
        "corrupt.xlsx",
        corrupted_bytes,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    file_id = file_info["id"]

    response = client.post(f"/api/v1/projects/{project_id}/files/{file_id}/preprocess")
    assert response.status_code == 200
    data = response.json()

    errors = [i for i in data["issues"] if i["level"] == "error"]
    assert len(errors) == 1
    assert errors[0]["issue_type"] == "corrupted_file"


def test_preprocess_max_rows_limit(client: TestClient, upload_storage: Path):
    project_id = create_project(client)
    lines = ["id,val"] + [f"{i},v{i}" for i in range(10)]
    csv_content = "\n".join(lines).encode("utf-8")

    file_info = upload_file(client, project_id, "limit.csv", csv_content)
    file_id = file_info["id"]

    config = {"max_rows": 5}
    response = client.post(
        f"/api/v1/projects/{project_id}/files/{file_id}/preprocess",
        json=config,
    )
    assert response.status_code == 200
    data = response.json()

    assert data["data_rows_count"] == 5
    warnings = [i for i in data["issues"] if i["issue_type"] == "row_limit_reached"]
    assert len(warnings) == 1

