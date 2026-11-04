from pathlib import Path
from uuid import uuid4
import openpyxl

from app.schemas.preprocessing import PreprocessingConfig
from app.services.preprocessing import (
    analyze_header_candidates,
    extract_dataset_records,
    preprocess_file_data,
)
from app.services.profiling_service import (
    _is_descriptive_title_header,
)
from app.schemas.multisource import SourceDefinition
from app.services.verification_engine import verify_multisource_datasets


def test_analyze_header_candidates_title_in_row_1():
    """Row 1 is a merged/wide title banner; Row 2 has table headers."""
    sample_rows = [
        (1, ["CAMPUS ACADEMIC ENROLLMENT REGISTER - SPRING 2026", None, None, None]),
        (2, ["student_id", "first_name", "email", "status"]),
        (3, ["S1001", "Alice", "alice@example.com", "enrolled"]),
        (4, ["S1002", "Bob", "bob@example.com", "enrolled"]),
    ]
    detected_row, raw_headers, candidates, auto = analyze_header_candidates(sample_rows)
    assert detected_row == 2
    assert auto is True
    assert raw_headers == ["student_id", "first_name", "email", "status"]
    assert len(candidates) >= 1
    candidate_rows = [c.row_number for c in candidates]
    assert 2 in candidate_rows
    # Check that candidate 2 is marked as likely header
    cand_2 = next(c for c in candidates if c.row_number == 2)
    assert cand_2.is_likely_header is True


def test_analyze_header_candidates_standard_row_1():
    """Standard table with headers starting at row 1."""
    sample_rows = [
        (1, ["student_id", "first_name", "email", "status"]),
        (2, ["S1001", "Alice", "alice@example.com", "enrolled"]),
        (3, ["S1002", "Bob", "bob@example.com", "enrolled"]),
    ]
    detected_row, raw_headers, candidates, auto = analyze_header_candidates(sample_rows)
    assert detected_row == 1
    assert auto is False
    assert raw_headers == ["student_id", "first_name", "email", "status"]


def test_analyze_header_candidates_blank_leading_rows():
    """Empty or whitespace rows preceding the header row."""
    sample_rows = [
        (1, ["", "  ", None]),
        (2, [None, None, None]),
        (3, ["roll_no", "department", "hostel_room"]),
        (4, ["R001", "CS", "A-101"]),
        (5, ["R002", "EE", "B-204"]),
    ]
    detected_row, raw_headers, candidates, auto = analyze_header_candidates(sample_rows)
    assert detected_row == 3
    assert raw_headers == ["roll_no", "department", "hostel_room"]


def test_analyze_header_candidates_explicit_override():
    """Explicit user selection overrides automatic heuristic detection."""
    sample_rows = [
        (1, ["Header Row Candidate A", "Col2"]),
        (2, ["Header Row Candidate B", "Col2"]),
        (3, ["1", "2"]),
    ]
    detected_row, raw_headers, _, auto = analyze_header_candidates(sample_rows, explicit_header_row=1)
    assert detected_row == 1
    assert auto is False
    assert raw_headers == ["Header Row Candidate A", "Col2"]

    detected_row_b, raw_headers_b, _, auto_b = analyze_header_candidates(sample_rows, explicit_header_row=2)
    assert detected_row_b == 2
    assert auto_b is False
    assert raw_headers_b == ["Header Row Candidate B", "Col2"]


def test_read_csv_with_title_banner_in_row_1(tmp_path: Path):
    """CSV file having a title row followed by column headers."""
    csv_file = tmp_path / "hostel.csv"
    csv_file.write_text(
        "Hostel Allocation Report - Confidential\n"
        "student_id,room_no,block,monthly_fee\n"
        "S101,102,North,4500\n"
        "S102,103,South,4800\n",
        encoding="utf-8",
    )

    result = extract_dataset_records(csv_file, "csv", PreprocessingConfig())
    records, columns_meta, col_map, _, _, issues, total_rows = result

    assert result.detected_header_row == 2
    col_names = [c.original_name for c in columns_meta]
    assert col_names == ["student_id", "room_no", "block", "monthly_fee"]
    assert len(records) == 2
    assert records[0][1]["student_id"] == "S101"
    assert records[0][1]["room_no"] == 102 or records[0][1]["room_no"] == "102"
    assert total_rows == 4


def test_read_xlsx_with_merged_title_banner(tmp_path: Path):
    """Excel workbook with merged banner cell on Row 1 and headers on Row 2."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Allocations"

    # Row 1 banner
    ws.merge_cells("A1:D1")
    ws["A1"] = "OFFICIAL REGISTRAR ENROLLMENT ROSTER 2026"

    # Row 2 headers
    headers = ["student_id", "full_name", "department", "active"]
    ws.append(headers)

    # Row 3+ records
    ws.append(["S201", "Charlie Brown", "Physics", "True"])
    ws.append(["S202", "Diana Prince", "Math", "True"])

    xlsx_file = tmp_path / "roster.xlsx"
    wb.save(xlsx_file)

    result = extract_dataset_records(xlsx_file, "xlsx", PreprocessingConfig(selected_worksheet="Allocations"))
    records, columns_meta, col_map, _, _, issues, total_rows = result

    assert result.detected_header_row == 2
    col_names = [c.original_name for c in columns_meta]
    assert col_names == ["student_id", "full_name", "department", "active"]
    assert len(records) == 2
    assert records[0][1]["student_id"] == "S201"
    assert total_rows == 4


def test_read_xlsx_manual_header_row_override(tmp_path: Path):
    """User manually forces header row even if row 1 might look plausible."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Section A", "Unused Note"])
    ws.append(["id", "score"])
    ws.append(["1", "95"])
    ws.append(["2", "88"])

    xlsx_file = tmp_path / "data.xlsx"
    wb.save(xlsx_file)

    result = extract_dataset_records(xlsx_file, "xlsx", PreprocessingConfig(header_row=2))
    records, columns_meta, _, _, _, _, _ = result

    assert result.detected_header_row == 2
    col_names = [c.original_name for c in columns_meta]
    assert col_names == ["id", "score"]
    assert len(records) == 2


def test_descriptive_title_header_filtering():
    """Ensure long report headers and banners are excluded from candidate join keys."""
    assert _is_descriptive_title_header("ACADEMIC ENROLLMENT REPORT 2026 FOR SPRING SEMESTER") is True
    assert _is_descriptive_title_header("Hostel Room Allocations Summary & Audit Trail") is True
    assert _is_descriptive_title_header("Confidential Student Roster for Registrar Office") is True

    # Real column names should not be filtered
    assert _is_descriptive_title_header("student_id") is False
    assert _is_descriptive_title_header("roll_no") is False
    assert _is_descriptive_title_header("email") is False
    assert _is_descriptive_title_header("id") is False


def test_preprocess_file_data_exposes_header_row_metadata(tmp_path: Path):
    """preprocess_file_data returns detected_header_row and header_row_candidates."""
    csv_file = tmp_path / "summary.csv"
    csv_file.write_text(
        "ANNUAL AUDIT SUMMARY\n"
        "account_id,balance,branch\n"
        "ACC-1,5000,Downtown\n",
        encoding="utf-8",
    )

    (
        columns_meta,
        column_mapping,
        preview,
        dup_rows,
        empty_rows,
        issues,
        total_rows,
        data_rows,
        detected_header_row,
        header_row_candidates,
    ) = preprocess_file_data(
        file_path=csv_file,
        file_type="csv",
        config=PreprocessingConfig(),
    )

    assert detected_header_row == 2
    assert header_row_candidates is not None
    assert len(header_row_candidates) >= 2
    assert header_row_candidates[0].row_number == 1
    assert header_row_candidates[1].row_number == 2
    assert header_row_candidates[1].is_likely_header is True
    assert "account_id" in header_row_candidates[1].columns


def test_multisource_verification_with_header_row(tmp_path: Path):
    """End-to-end multisource verification where primary source has header on Row 2."""
    primary_file = tmp_path / "primary.csv"
    primary_file.write_text(
        "REGISTRAR VERIFIED STUDENT DIRECTORY 2026\n"
        "student_id,name,status\n"
        "S101,Alice,enrolled\n"
        "S102,Bob,enrolled\n",
        encoding="utf-8",
    )

    target_file = tmp_path / "target.csv"
    target_file.write_text(
        "student_id,name,status\n"
        "S101,Alice,enrolled\n"
        "S102,Bob,withdrawn\n",
        encoding="utf-8",
    )

    primary_res = extract_dataset_records(primary_file, "csv", PreprocessingConfig(header_row=2))
    target_res = extract_dataset_records(target_file, "csv", PreprocessingConfig(header_row=1))

    primary_recs = primary_res[0]
    target_recs = target_res[0]

    sources = [
        SourceDefinition(
            alias="registrar",
            file_id=uuid4(),
            is_primary=True,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id", "name": "name", "status": "status"},
            header_row=2,
        ),
        SourceDefinition(
            alias="hostel",
            file_id=uuid4(),
            is_primary=False,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id", "name": "name", "status": "status"},
            header_row=1,
        ),
    ]

    sources_records = {
        "registrar": primary_recs,
        "hostel": target_recs,
    }

    summary, discrepancies, inspection, _, _ = verify_multisource_datasets(
        sources=sources,
        sources_records=sources_records,
        unified_keys=["student_id"],
        compare_attributes=["status"],
    )

    assert summary.total_source_records == 2
    assert summary.matched_records == 2
    assert summary.identical_matches == 1
    assert summary.field_mismatches == 1
    mismatches = [d for d in discrepancies if str(d.match_status) != "identical" and d.match_status != "identical"]
    assert len(mismatches) == 1
    assert mismatches[0].key_values == {"student_id": "S102"}
