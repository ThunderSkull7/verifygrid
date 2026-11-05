"""Tests for Batch 9 Results, Review Experience, and Export Polish."""

from datetime import datetime, timezone
import io
import json
from unittest.mock import MagicMock
import uuid

import openpyxl
import pytest

from app.models.verification_run import VerificationDiscrepancy, VerificationRun
from app.services.export_service import (
    generate_audit_workbook_xlsx,
    generate_csv_report,
    generate_json_report,
    generate_xlsx_report,
    sanitize_formula_value,
)


@pytest.fixture
def sample_run_and_discrepancies():
    run = MagicMock(spec=VerificationRun)
    run.id = uuid.uuid4()
    run.project_id = uuid.uuid4()
    run.status = "completed"
    run.started_at = datetime(2026, 11, 4, 10, 0, 0, tzinfo=timezone.utc)
    run.completed_at = datetime(2026, 11, 4, 10, 0, 5, tzinfo=timezone.utc)
    run.key_columns = ["student_id", "term"]
    run.sign_off_status = "PROPOSED"
    run.sign_off_proposed_by_name = "Dean Academic"
    run.sign_off_proposed_at = datetime(2026, 11, 4, 10, 5, 0, tzinfo=timezone.utc)
    run.sign_off_proposal_note = "Academic review complete for Fall 2025 cohort."
    run.sign_off_approved_by_name = None
    run.sign_off_decided_at = None
    run.sign_off_decision_note = None
    run.project = MagicMock()
    run.project.name = "Fall 2025 Student Verification"

    run.column_mapping = {}
    run.configuration = {}
    run.source_file_id = None
    run.target_file_id = None
    run.error_message = None

    run.sources = [
        {"alias": "main", "label": "Official Registrar Register", "is_primary": True, "rows_count": 120},
        {"alias": "lms", "label": "LMS Active Roster", "is_primary": False, "rows_count": 118},
    ]

    run.summary = {
        "total_source_records": 120,
        "total_target_records": 118,
        "matched_records": 115,
        "identical_matches": 110,
        "field_mismatches": 5,
        "unmatched_source_records": 5,
        "unmatched_target_records": 3,
        "duplicate_source_records": 0,
        "duplicate_target_records": 0,
        "duplicate_source_keys_count": 0,
        "duplicate_target_keys_count": 0,
        "total_discrepancies": 8,
        "gross_exposure": 0.0,
        "net_variance": 0.0,
    }

    # Create test discrepancies
    d1 = MagicMock(spec=VerificationDiscrepancy)
    d1.id = uuid.uuid4()
    d1.discrepancy_category = "field_mismatch"
    d1.match_status = "field_mismatch"
    d1.source_row_number = 12
    d1.target_row_number = 14
    d1.source_row_numbers = None
    d1.target_row_numbers = None
    d1.key_values = {"student_id": "S101", "term": "Fall 2025"}
    d1.field_differences = [
        {
            "field_name": "major",
            "source_value": "Computer Science",
            "target_value": "Informatics",
            "difference_type": "value_mismatch",
        }
    ]
    d1.message = "Major differs between registrar and LMS."
    d1.exposure_amount = 0.0
    d1.variance_amount = 0.0
    d1.source_amount = None
    d1.target_amount = None
    d1.currency = "USD"
    d1.source_record = {"student_id": "S101", "name": "Aarav Sharma", "major": "Computer Science"}
    d1.target_record = {"student_id": "S101", "name": "Aarav Sharma", "major": "Informatics"}
    d1.cluster_name = "Curriculum Mappings"
    d1.cluster_id = "CL-CURR"
    d1.reason_code = "MAJOR_DISCREPANCY"
    d1.severity = "medium"
    d1.resolution_status = "unresolved"
    d1.resolution_note = None
    d1.resolved_by = None
    d1.resolved_at = None
    d1.created_at = datetime(2026, 11, 4, 10, 1, 0, tzinfo=timezone.utc)

    # Discrepancy with formula trigger characters to verify protection
    d2 = MagicMock(spec=VerificationDiscrepancy)
    d2.id = uuid.uuid4()
    d2.discrepancy_category = "field_mismatch"
    d2.match_status = "field_mismatch"
    d2.source_row_number = 25
    d2.target_row_number = 28
    d2.source_row_numbers = None
    d2.target_row_numbers = None
    d2.key_values = {"student_id": "=cmd|' /C calc'!A0", "term": "+cmd"}
    d2.field_differences = [
        {
            "field_name": "notes",
            "source_value": "@SUM(1+1)",
            "target_value": "-DANGEROUS",
            "difference_type": "value_mismatch",
        }
    ]
    d2.message = "@formula injection test"
    d2.exposure_amount = 0.0
    d2.variance_amount = 0.0
    d2.source_amount = None
    d2.target_amount = None
    d2.currency = "USD"
    d2.source_record = {"student_id": "=cmd", "notes": "@SUM(1+1)"}
    d2.target_record = {"student_id": "=cmd", "notes": "-DANGEROUS"}
    d2.cluster_name = None
    d2.cluster_id = None
    d2.reason_code = None
    d2.severity = "low"
    d2.resolution_status = "unresolved"
    d2.resolution_note = None
    d2.resolved_by = None
    d2.resolved_at = None
    d2.created_at = datetime(2026, 11, 4, 10, 1, 30, tzinfo=timezone.utc)

    return run, [d1, d2]


def test_csv_export_human_readable_and_sanitized(sample_run_and_discrepancies):
    run, discrepancies = sample_run_and_discrepancies
    csv_bytes = generate_csv_report(run, discrepancies)
    csv_text = csv_bytes.decode("utf-8")

    # 1. Metadata contains friendly source names and roles
    assert "Official Registrar Register (Authoritative, 120 records)" in csv_text
    assert "LMS Active Roster (Comparison, 118 records)" in csv_text

    # 2. Key Values formatted cleanly instead of raw JSON
    assert "student_id: S101 · term: Fall 2025" in csv_text
    assert '{"student_id": "S101"' not in csv_text

    # 3. Formula injection neutralized with leading apostrophe
    assert "'=cmd" in csv_text or "'=cmd|' /C calc'!A0" in csv_text
    assert "'+cmd" in csv_text
    assert "'@SUM(1+1)" in csv_text
    assert "'-DANGEROUS" in csv_text
    assert "'@formula injection test" in csv_text


def test_xlsx_export_structure_and_metrics_agreement(sample_run_and_discrepancies):
    run, discrepancies = sample_run_and_discrepancies
    xlsx_bytes = generate_xlsx_report(run, discrepancies)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))

    # Verify sheets
    assert "Summary" in wb.sheetnames
    assert "Discrepancies" in wb.sheetnames

    # Check Summary sheet matches verification summary numbers
    ws_summary = wb["Summary"]
    summary_dict = {}
    for r in range(4, ws_summary.max_row + 1):
        metric = ws_summary.cell(row=r, column=1).value
        val = ws_summary.cell(row=r, column=2).value
        if metric:
            summary_dict[metric] = val

    assert summary_dict.get("Total Source Records") == 120
    assert summary_dict.get("Total Target Records") == 118
    assert summary_dict.get("1-to-1 Matched Records") == 115
    assert summary_dict.get("Identical Matches") == 110
    assert summary_dict.get("Field-Level Differences") == 5
    assert "Official Registrar Register" in str(summary_dict.get("Participating Sources"))

    # Check Discrepancies sheet formatting
    ws_disc = wb["Discrepancies"]
    row2_key = ws_disc.cell(row=2, column=5).value
    assert "student_id: S101 · term: Fall 2025" == row2_key

    # Check formula neutralization in row 3
    row3_key = ws_disc.cell(row=3, column=5).value
    assert "'=cmd" in str(row3_key)
    row3_msg = ws_disc.cell(row=3, column=7).value
    assert str(row3_msg).startswith("'@")


def test_json_export_preserves_machine_readable_dictionary(sample_run_and_discrepancies):
    run, discrepancies = sample_run_and_discrepancies
    json_bytes = generate_json_report(run, discrepancies)
    data = json.loads(json_bytes.decode("utf-8"))

    assert data["report_type"] == "VerifyGrid Verification Report"
    assert data["summary"]["total_source_records"] == 120
    assert data["discrepancies_count"] == 2

    # Discrepancy key_values must be preserved as dictionary for system integration
    first_item = data["discrepancies"][0]
    assert isinstance(first_item["key_values"], dict)
    assert first_item["key_values"]["student_id"] == "S101"
    assert first_item["key_values"]["term"] == "Fall 2025"


def test_export_formula_injection_sanitization_comprehensive():
    """Verify formula injection neutralization handles all triggers and whitespace variations,

    while strictly preserving genuine negative/positive numbers and empty/None values.
    """
    # 1. Formula triggers with leading whitespace
    assert sanitize_formula_value("   =cmd") == "'   =cmd"
    assert sanitize_formula_value("  +cmd|' /C calc'") == "'  +cmd|' /C calc'"
    assert sanitize_formula_value(" -SUM(A1:A10)") == "' -SUM(A1:A10)"
    assert sanitize_formula_value("   @SUM(B1:B5)") == "'   @SUM(B1:B5)"

    # 2. Leading tabs and carriage returns (with or without subsequent formulas or text)
    assert sanitize_formula_value("\t=cmd") == "'\t=cmd"
    assert sanitize_formula_value("\ttext") == "'\ttext"
    assert sanitize_formula_value("  \ttext") == "'  \ttext"
    assert sanitize_formula_value("\r=calc") == "'\r=calc"
    assert sanitize_formula_value("\rtext") == "'\rtext"
    assert sanitize_formula_value("  \rtext") == "'  \rtext"

    # 3. Numeric values (genuine negative and positive numbers) must remain intact
    assert sanitize_formula_value(-42.50) == -42.50
    assert sanitize_formula_value("-42.50") == "-42.50"
    assert sanitize_formula_value("   -100") == "   -100"
    assert sanitize_formula_value(100) == 100
    assert sanitize_formula_value("+100") == "+100"
    assert sanitize_formula_value("   +250.75") == "   +250.75"
    assert sanitize_formula_value(0) == 0
    assert sanitize_formula_value(0.0) == 0.0

    # 4. Empty and None handling
    assert sanitize_formula_value(None) == ""
    assert sanitize_formula_value("") == ""

    # 5. Safe non-formula text
    assert sanitize_formula_value("Normal Text") == "Normal Text"
    assert sanitize_formula_value("College of Engineering") == "College of Engineering"

