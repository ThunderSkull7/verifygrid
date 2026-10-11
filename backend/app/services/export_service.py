"""Report generation service for verification runs and discrepancies.

Supports streaming CSV and multi-sheet XLSX report exports.
"""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.models.verification_run import VerificationRun, VerificationDiscrepancy
from app.services.verification_engine import get_verification_run


def _safe_filename(prefix: str, identifier: str, ext: str) -> str:
    """Generate a sanitized, injection-safe attachment filename."""
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(identifier))
    clean_prefix = re.sub(r"[^a-zA-Z0-9_-]", "", prefix)
    return f"{clean_prefix}_{clean_id}.{ext}"


def _format_field_differences(diff_list: Optional[List[Dict[str, Any]]]) -> str:
    """Format field differences into human-readable text."""
    if not diff_list:
        return ""
    items = []
    for d in diff_list:
        field = d.get("field_name") or d.get("source_field") or "unknown"
        s_val = d.get("source_value")
        t_val = d.get("target_value")
        diff_type = d.get("difference_type", "diff")
        items.append(f"{field} [{diff_type}]: '{s_val}' vs '{t_val}'")
    return "; ".join(items)


def generate_csv_report(
    run: VerificationRun,
    discrepancies: List[VerificationDiscrepancy],
) -> bytes:
    """Generate a clean CSV report containing summary headers and discrepancy rows."""
    output = io.StringIO()
    writer = csv.writer(output)

    # 1. Summary metadata block
    writer.writerow(["# VerifyGrid Verification Report"])
    writer.writerow(["# Run ID", str(run.id)])
    writer.writerow(["# Project ID", str(run.project_id)])
    writer.writerow(["# Status", run.status])
    writer.writerow(["# Started At", run.started_at.isoformat() if run.started_at else ""])
    writer.writerow(["# Completed At", run.completed_at.isoformat() if run.completed_at else ""])
    writer.writerow(["# Key Columns", ", ".join(run.key_columns or [])])

    summary = run.summary or {}
    writer.writerow(["# Total Source Records", summary.get("total_source_records", 0)])
    writer.writerow(["# Total Target Records", summary.get("total_target_records", 0)])
    writer.writerow(["# Matched Records", summary.get("matched_records", 0)])
    writer.writerow(["# Identical Matches", summary.get("identical_matches", 0)])
    writer.writerow(["# Field Mismatches", summary.get("field_mismatches", 0)])
    writer.writerow(["# Unmatched Source Records", summary.get("unmatched_source_records", 0)])
    writer.writerow(["# Unmatched Target Records", summary.get("unmatched_target_records", 0)])
    writer.writerow(["# Duplicate Source Records", summary.get("duplicate_source_records", 0)])
    writer.writerow(["# Duplicate Target Records", summary.get("duplicate_target_records", 0)])
    writer.writerow(["# Total Discrepancies", summary.get("total_discrepancies", 0)])
    writer.writerow([])

    # 2. Discrepancies table
    headers = [
        "Category",
        "Match Status",
        "Source Row",
        "Target Row",
        "Key Values",
        "Field Differences",
        "Message",
    ]
    writer.writerow(headers)

    for item in discrepancies:
        key_vals_str = json.dumps(item.key_values) if item.key_values else ""
        src_row = item.source_row_number
        if src_row is None and item.source_row_numbers:
            src_row = ", ".join(str(r) for r in item.source_row_numbers)
        tgt_row = item.target_row_number
        if tgt_row is None and item.target_row_numbers:
            tgt_row = ", ".join(str(r) for r in item.target_row_numbers)

        diffs_str = _format_field_differences(item.field_differences)

        writer.writerow([
            item.discrepancy_category,
            item.match_status,
            src_row if src_row is not None else "",
            tgt_row if tgt_row is not None else "",
            key_vals_str,
            diffs_str,
            item.message or "",
        ])

    return output.getvalue().encode("utf-8")


def generate_xlsx_report(
    run: VerificationRun,
    discrepancies: List[VerificationDiscrepancy],
) -> bytes:
    """Generate an Excel workbook with formatted Summary and Discrepancies sheets."""
    wb = openpyxl.Workbook()

    # Sheet 1: Summary
    ws_summary = wb.active
    ws_summary.title = "Summary"

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    title_font = Font(name="Calibri", size=14, bold=True, color="1F4E79")

    ws_summary["A1"] = "VerifyGrid Reconciliation Summary Report"
    ws_summary["A1"].font = title_font

    summary = run.summary or {}
    metadata_rows = [
        ("Run ID", str(run.id)),
        ("Project ID", str(run.project_id)),
        ("Status", run.status),
        ("Key Columns", ", ".join(run.key_columns or [])),
        ("Started At", run.started_at.isoformat() if run.started_at else ""),
        ("Completed At", run.completed_at.isoformat() if run.completed_at else ""),
        ("Total Source Records", summary.get("total_source_records", 0)),
        ("Total Target Records", summary.get("total_target_records", 0)),
        ("1-to-1 Matched Records", summary.get("matched_records", 0)),
        ("Identical Matches", summary.get("identical_matches", 0)),
        ("Field-Level Differences", summary.get("field_mismatches", 0)),
        ("Unmatched Source Records (Missing in Target)", summary.get("unmatched_source_records", 0)),
        ("Unmatched Target Records (Missing in Source)", summary.get("unmatched_target_records", 0)),
        ("Duplicate Source Records", summary.get("duplicate_source_records", 0)),
        ("Duplicate Target Records", summary.get("duplicate_target_records", 0)),
        ("Total Discrepancies", summary.get("total_discrepancies", len(discrepancies))),
    ]

    ws_summary["A3"] = "Metric"
    ws_summary["B3"] = "Value"
    ws_summary["A3"].font = header_font
    ws_summary["A3"].fill = header_fill
    ws_summary["B3"].font = header_font
    ws_summary["B3"].fill = header_fill

    for r_idx, (label, val) in enumerate(metadata_rows, start=4):
        ws_summary.cell(row=r_idx, column=1, value=label)
        ws_summary.cell(row=r_idx, column=2, value=val)

    ws_summary.column_dimensions["A"].width = 45
    ws_summary.column_dimensions["B"].width = 40

    # Sheet 2: Discrepancies
    ws_disc = wb.create_sheet(title="Discrepancies")
    headers = [
        "Category",
        "Match Status",
        "Source Row",
        "Target Row",
        "Key Values",
        "Field Differences",
        "Message",
    ]

    for c_idx, h in enumerate(headers, start=1):
        cell = ws_disc.cell(row=1, column=c_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for r_idx, item in enumerate(discrepancies, start=2):
        key_vals_str = json.dumps(item.key_values) if item.key_values else ""
        src_row = item.source_row_number
        if src_row is None and item.source_row_numbers:
            src_row = ", ".join(str(r) for r in item.source_row_numbers)
        tgt_row = item.target_row_number
        if tgt_row is None and item.target_row_numbers:
            tgt_row = ", ".join(str(r) for r in item.target_row_numbers)

        diffs_str = _format_field_differences(item.field_differences)

        ws_disc.cell(row=r_idx, column=1, value=item.discrepancy_category)
        ws_disc.cell(row=r_idx, column=2, value=item.match_status)
        ws_disc.cell(row=r_idx, column=3, value=str(src_row) if src_row is not None else "")
        ws_disc.cell(row=r_idx, column=4, value=str(tgt_row) if tgt_row is not None else "")
        ws_disc.cell(row=r_idx, column=5, value=key_vals_str)
        ws_disc.cell(row=r_idx, column=6, value=diffs_str)
        ws_disc.cell(row=r_idx, column=7, value=item.message or "")

    for col in ws_disc.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_disc.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 60)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def export_verification_report(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    report_format: str = "csv",
    discrepancy_category: Optional[str] = None,
    match_status: Optional[str] = None,
) -> Tuple[bytes, str, str]:
    """
    Generate downloadable report file bytes, MIME type, and safe filename.
    Validates project authorization, run ID, and export format.
    """
    clean_format = report_format.strip().lower()
    if clean_format not in ["csv", "xlsx"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported export format '{report_format}'. Supported formats are 'csv' and 'xlsx'.",
        )

    # 1. Authorize project & fetch run
    run = get_verification_run(db, project_id, run_id)

    # 2. Query discrepancies with optional filters
    query = db.query(VerificationDiscrepancy).filter(VerificationDiscrepancy.run_id == run_id)
    if discrepancy_category:
        query = query.filter(VerificationDiscrepancy.discrepancy_category == discrepancy_category)
    if match_status:
        query = query.filter(VerificationDiscrepancy.match_status == match_status)

    discrepancies = (
        query.order_by(
            VerificationDiscrepancy.source_row_number.asc().nulls_last(),
            VerificationDiscrepancy.target_row_number.asc().nulls_last(),
            VerificationDiscrepancy.created_at.asc(),
        )
        .all()
    )

    # 3. Generate file content
    if clean_format == "csv":
        content = generate_csv_report(run, discrepancies)
        media_type = "text/csv"
        filename = _safe_filename("verification_report", str(run.id), "csv")
    else:
        content = generate_xlsx_report(run, discrepancies)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = _safe_filename("verification_report", str(run.id), "xlsx")

    return content, media_type, filename
