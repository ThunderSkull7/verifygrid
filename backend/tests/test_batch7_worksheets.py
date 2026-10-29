"""Batch 7 tests: explicit XLSX worksheet selection.

Coverage:
- Workbook metadata: sheet names in workbook order; corrupt workbooks error.
- Selection & parsing: exact named worksheet parsed; non-first sheets; Unicode /
  spaced names; per-file independent selections; invalid selections rejected.
- Execution consistency: preview and persisted runs parse the same sheet; the
  persisted configuration records the per-source sheet.
- Compatibility: CSV ingestion unchanged; legacy requests without sheet_name
  keep working (documented legacy behavior: active sheet, not user-verified).
"""

import io
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas.preprocessing import PreprocessingConfig
from app.services.preprocessing import extract_dataset_records, list_worksheet_names

import tests.test_multisource_wizard as wizard

create_project = wizard.create_project
upload_csv = wizard.upload_csv
upload_storage = wizard.upload_storage

MULTI_SOURCE_RUN = "/runs/multi-source"
MULTI_SOURCE_VERIFY = "/verify/multi-source"


def make_multisheet_xlsx(sheets: dict[str, list[list]]) -> bytes:
    """Build an XLSX with named worksheets in insertion order."""
    wb = openpyxl.Workbook()
    del wb["Sheet"]  # remove the default sheet so only requested sheets remain
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def upload_file(client: TestClient, project_id: str, filename: str, content: bytes, content_type: str) -> dict:
    res = client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": (filename, content, content_type)},
    )
    assert res.status_code == 201, res.text
    return res.json()


def preprocess(client: TestClient, project_id: str, file_id: str, config: dict | None = None) -> dict:
    res = client.post(
        f"/api/v1/projects/{project_id}/files/{file_id}/preprocess",
        json=config,
    )
    return res


SHEETS = {
    "Summary": [["id", "val"], ["ignored-1", "never-parsed"]],
    "Detailed Data": [["id", "val"], ["S-1", "10"], ["S-2", "20"]],
    "Élèves 🎓 2024": [["id", "val"], ["U-1", "30"]],
}


# ==============================================================================
# Workbook metadata
# ==============================================================================


def test_workbook_metadata_returns_all_sheets_in_order(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Sheet Metadata Project")
    f = upload_file(client, proj_id, "multi.xlsx", make_multisheet_xlsx(SHEETS),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    res = preprocess(client, proj_id, f["id"])
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["file_type"] == "xlsx"
    # Workbook order preserved, including Unicode and spaced names.
    assert data["sheet_names"] == list(SHEETS.keys())
    # Legacy preprocess (no selection) does not silently claim a user-verified sheet.
    assert data["selected_worksheet"] is None


def test_single_sheet_workbook_metadata(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Single Sheet Project")
    f = upload_file(client, proj_id, "one.xlsx",
                    make_multisheet_xlsx({"Only Sheet": [["id"], ["1"]]}),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    data = preprocess(client, proj_id, f["id"]).json()
    assert data["sheet_names"] == ["Only Sheet"]


def test_corrupt_xlsx_metadata_actionable(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Corrupt Sheet Project")
    f = upload_file(client, proj_id, "corrupt.xlsx", b"this is not a real xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    res = preprocess(client, proj_id, f["id"])
    assert res.status_code in (200, 422)
    data = res.json()
    # Either an actionable 422 or a failed preprocessing with a corrupted_file issue.
    if res.status_code == 200:
        assert any(i["issue_type"] == "corrupted_file" for i in data["issues"])
    else:
        assert "corrupt" in str(data).lower() or "read" in str(data).lower()


def test_empty_workbook_metadata_is_explicit(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Empty Workbook Project")
    # Workbook whose sheet has no data at all -> missing headers, explicit error.
    f = upload_file(client, proj_id, "empty.xlsx",
                    make_multisheet_xlsx({"Blank": []}),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    data = preprocess(client, proj_id, f["id"]).json()
    assert data["sheet_names"] == ["Blank"]
    issue_types = {i["issue_type"] for i in data["issues"]}
    assert "missing_headers" in issue_types


# ==============================================================================
# Selection and parsing
# ==============================================================================


def _source_payload(f, alias, sheet=None, primary=True):
    return {
        "alias": alias,
        "file_id": f["id"],
        "is_primary": primary,
        "key_columns": ["id"],
        "field_mapping": {"id": "id", "val": "val"},
        **({"sheet_name": sheet} if sheet is not None else {}),
    }


def test_select_non_first_worksheet_parses_that_sheet(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Non-First Sheet Project")
    f = upload_file(client, proj_id, "multi.xlsx", make_multisheet_xlsx(SHEETS),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    fc = upload_csv(client, proj_id, "copy.csv", "id,val\nS-1,10\nS-2,20\n")
    payload = {
        "sources": [
            _source_payload(f, "data", sheet="Detailed Data"),
            _source_payload(fc, "copy", primary=False),
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    # The 'Detailed Data' sheet's rows (S-1, S-2) were parsed — not 'Summary' —
    # and both matched the identical CSV copy.
    assert data["summary"]["total_source_records"] == 2
    assert data["summary"]["matched_records"] == 2
    assert data["summary"]["identical_matches"] == 2


def test_select_unicode_and_spaced_worksheet_name(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Unicode Sheet Project")
    f = upload_file(client, proj_id, "multi.xlsx", make_multisheet_xlsx(SHEETS),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    fc = upload_csv(client, proj_id, "copy.csv", "id,val\nU-1,30\n")
    payload = {
        "sources": [
            _source_payload(f, "eleves", sheet="Élèves 🎓 2024"),
            _source_payload(fc, "copy", primary=False),
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 201, res.text
    summary = res.json()["summary"]
    assert summary["matched_records"] == 1
    assert summary["identical_matches"] == 1


def test_invalid_worksheet_selection_rejected_actionably(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Invalid Sheet Project")
    f = upload_file(client, proj_id, "multi.xlsx", make_multisheet_xlsx(SHEETS),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    fc = upload_csv(client, proj_id, "copy.csv", "id,val\nS-1,10\n")
    payload = {
        "sources": [
            _source_payload(f, "data", sheet="Renamed Or Deleted"),
            _source_payload(fc, "copy", primary=False),
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 422, res.text
    detail = str(res.json()["detail"])
    assert "Renamed Or Deleted" in detail
    assert "Detailed Data" in detail  # actionable: lists available worksheets


def test_worksheet_selection_on_csv_source_rejected(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "CSV Sheet Rejection Project")
    f = upload_csv(client, proj_id, "plain.csv", "id,val\n1,10\n")
    f2 = upload_csv(client, proj_id, "plain2.csv", "id,val\n1,10\n")
    payload = {
        "sources": [
            _source_payload(f, "csv_src", sheet="Detailed Data"),
            _source_payload(f2, "other", primary=False),
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 422, res.text
    assert "CSV" in str(res.json()["detail"])


def test_different_files_use_different_worksheets(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Per-File Sheets Project")
    f1 = upload_file(client, proj_id, "one.xlsx", make_multisheet_xlsx(SHEETS),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    f2 = upload_file(client, proj_id, "two.xlsx", make_multisheet_xlsx(SHEETS),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    payload = {
        "sources": [
            _source_payload(f1, "alpha", sheet="Detailed Data"),
            _source_payload(f2, "beta", sheet="Élèves 🎓 2024", primary=False),
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    # alpha sheet has S-1/S-2; beta sheet has U-1 -> only the cross-file key match
    # survives; repeated sheet names across workbooks must not cross-select.
    assert data["summary"]["matched_records"] == 0
    assert data["summary"]["unmatched_target_records"] == 2  # S-1, S-2 only in alpha
    assert data["summary"]["unmatched_source_records"] == 1  # U-1 only in beta


def test_extract_dataset_records_selects_exact_sheet(tmp_path: Path):
    path = tmp_path / "m.xlsx"
    path.write_bytes(make_multisheet_xlsx(SHEETS))
    cfg = PreprocessingConfig()
    recs, _, _, _, _, issues, _ = extract_dataset_records(path, "xlsx", cfg, sheet_name="Detailed Data")
    assert not any(i.level == "error" for i in issues)
    assert [r[1]["id"] for r in recs] == ["S-1", "S-2"]

    recs_u, _, _, _, _, _, _ = extract_dataset_records(path, "xlsx", cfg, sheet_name="Élèves 🎓 2024")
    assert [r[1]["id"] for r in recs_u] == ["U-1"]

    # Unknown sheet -> fatal error, never a fallback to another sheet.
    recs_bad, _, _, _, _, issues_bad, _ = extract_dataset_records(path, "xlsx", cfg, sheet_name="Nope")
    assert recs_bad == []
    assert any(i.issue_type == "worksheet_not_found" for i in issues_bad)

    # Metadata helper: order preserved.
    assert list_worksheet_names(path) == list(SHEETS.keys())


# ==============================================================================
# Execution consistency & compatibility
# ==============================================================================


def test_preview_and_persisted_use_same_worksheet(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Sheet Consistency Project")
    f = upload_file(client, proj_id, "multi.xlsx", make_multisheet_xlsx(SHEETS),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    fc = upload_csv(client, proj_id, "copy.csv", "id,val\nS-1,10\nS-2,20\n")
    payload = {
        "sources": [
            _source_payload(f, "data", sheet="Detailed Data"),
            _source_payload(fc, "copy", primary=False),
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    v_res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}", json=payload)
    assert v_res.status_code == 200, v_res.text
    v_data = v_res.json()
    assert [r["key_values"]["id"] for r in v_data["results"]] == ["S-1", "S-2"]

    r_res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert r_res.status_code == 201, r_res.text
    r_data = r_res.json()
    assert r_data["summary"]["matched_records"] == 2

    # The persisted run configuration records the selected worksheet per source.
    persisted = client.get(f"/api/v1/projects/{proj_id}/runs/{r_data['id']}").json()
    assert persisted["configuration"]["sources"][0]["sheet_name"] == "Detailed Data"
    assert persisted["status"] == "completed"


def test_legacy_request_without_sheet_name_still_works(client: TestClient, upload_storage: Path):
    """Legacy omission keeps working: active-sheet behavior, unchanged results."""
    proj_id = create_project(client, "Legacy No-Sheet Project")
    f = upload_file(client, proj_id, "multi.xlsx", make_multisheet_xlsx(SHEETS),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    fc = upload_csv(client, proj_id, "copy.csv", "id,val\nS-1,10\nS-2,20\n")
    payload = {
        "sources": [
            _source_payload(f, "data"),  # no sheet_name
            _source_payload(fc, "copy", primary=False),
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 201, res.text
    # Active sheet = 'Summary' (first created) with only the header row... openpyxl
    # keeps insertion order, active defaults to index 0 -> 'Summary' has no data
    # rows beyond the header, so the xlsx contributes zero source records rather
    # than silently parsing a different sheet's data. The CSV copy still matches.
    data = res.json()
    # Active sheet = 'Summary' (index 0): its single data row ('ignored-1') was
    # parsed — legacy behavior unchanged; no other sheet's data was silently used.
    assert data["summary"]["total_source_records"] == 1
    assert data["summary"]["matched_records"] == 0  # 'ignored-1' matches nothing


def test_csv_ingestion_unchanged_by_worksheet_feature(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "CSV Regression Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,val\n1,10\n2,20\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,val\n1,10\n2,25\n")
    payload = {
        "sources": [
            {"alias": "a", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"],
             "field_mapping": {"id": "id", "val": "val"}},
            {"alias": "b", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"],
             "field_mapping": {"id": "id", "val": "val"}},
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["summary"]["matched_records"] == 2
    assert data["summary"]["identical_matches"] == 1
    assert data["summary"]["field_mismatches"] == 1
    assert data["configuration"]["sources"][0].get("sheet_name") is None
