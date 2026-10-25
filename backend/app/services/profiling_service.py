"""Data profiling, pre-flight validation, and quarantine service.

Profiles uploaded source files before reconciliation, detects data types,
nulls, uniqueness, duplicate keys, malformed values, negative currency amounts,
and shifted rows. Manages immutable quarantine classifications and pre-flight
impact previews.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.source_file import SourceFile
from app.models.user import User
from app.schemas.preprocessing import PreprocessingConfig
from app.schemas.profiling import (
    CandidateKeyQuality,
    ColumnProfile,
    FileProfileSummary,
    PreFlightImpactPreview,
    QuarantineListResponse,
    QuarantineReasonCode,
    QuarantineResolutionItem,
    QuarantineResolutionRequest,
    QuarantineResolutionResponse,
    QuarantineSeverity,
    QuarantinedRecord,
    ResolutionAction,
)
from app.services.preprocessing import extract_dataset_records, read_csv_rows, read_xlsx_rows
from app.services.project_service import get_project_by_id
from app.utils.normalization import (
    is_boolean,
    is_null_value,
    parse_date,
    parse_numeric,
    LEADING_ZERO_REGEX,
)

CURRENCY_AMOUNT_KEYWORDS = {
    "amount",
    "salary",
    "remuneration",
    "price",
    "fee",
    "cost",
    "premium",
    "revenue",
    "payment",
    "tuition",
    "balance",
    "total_amount",
    "gross_amount",
    "net_amount",
}

DATE_KEYWORDS = {
    "date",
    "timestamp",
    "created_at",
    "updated_at",
    "dob",
    "birth_date",
    "hire_date",
    "enrollment_date",
    "due_date",
    "effective_date",
    "transaction_date",
}

ID_KEYWORDS = {
    "id",
    "key",
    "code",
    "identifier",
    "ssn",
    "uuid",
    "emp_id",
    "student_id",
    "employee_id",
    "customer_id",
    "user_id",
    "client_id",
    "account_number",
}


def _get_profile_sidecar_path(storage_path: Path) -> Path:
    return storage_path.with_name(storage_path.name + ".profile.json")


def _get_quarantine_sidecar_path(storage_path: Path) -> Path:
    return storage_path.with_name(storage_path.name + ".quarantine.json")


def get_excluded_row_indices_for_file(storage_path: Path) -> List[int]:
    """Retrieve 1-based row indices marked for exclusion in quarantine sidecar."""
    q_path = _get_quarantine_sidecar_path(storage_path)
    if not q_path.exists():
        return []
    try:
        data = json.loads(q_path.read_text(encoding="utf-8"))
        resolutions = data.get("resolutions", {})
        return [
            int(row_idx)
            for row_idx, action in resolutions.items()
            if action == ResolutionAction.EXCLUDE.value
        ]
    except Exception:
        return []


def is_amount_column(col_name: str) -> bool:
    c = col_name.strip().lower()
    return c in CURRENCY_AMOUNT_KEYWORDS or any(kw in c for kw in ["amount", "salary", "price", "fee", "cost"])


def is_date_column_name(col_name: str) -> bool:
    c = col_name.strip().lower()
    return c in DATE_KEYWORDS or c.endswith("_date") or c.startswith("date_")


def is_candidate_key_name(col_name: str) -> bool:
    c = col_name.strip().lower()
    return c in ID_KEYWORDS or c.endswith("_id") or c.endswith("_key") or c.endswith("_code")


def profile_dataset_records(
    file_id: uuid.UUID,
    project_id: uuid.UUID,
    filename: str,
    file_type: str,
    records: List[Tuple[int, Dict[str, Any]]],
    raw_headers: List[str],
    column_mapping: Dict[str, str],
    null_set: Set[str],
    raw_rows_with_mismatch: Optional[List[Tuple[int, int, int]]] = None,
) -> Tuple[FileProfileSummary, List[QuarantinedRecord]]:
    """
    Profile dataset records, infer types, calculate nulls & uniqueness,
    evaluate candidate key viability, and flag quarantined records.
    """
    total_data_rows = len(records)
    cols = list(column_mapping.values()) if column_mapping else (list(records[0][1].keys()) if records else [])

    column_profiles: List[ColumnProfile] = []
    quarantined: List[QuarantinedRecord] = []
    quarantined_by_row: Dict[int, List[QuarantinedRecord]] = {}

    # 1. Flag shifted rows if any raw rows deviated in field counts
    if raw_rows_with_mismatch:
        for row_num, expected_count, actual_count in raw_rows_with_mismatch:
            q_rec = QuarantinedRecord(
                source_row_index=row_num,
                column_name=None,
                raw_value=f"Row has {actual_count} columns (expected {expected_count})",
                quarantine_reason=QuarantineReasonCode.SHIFTED_ROW,
                severity=QuarantineSeverity.BLOCKING,
                message=f"Shifted row: row has {actual_count} columns but header defines {expected_count}.",
            )
            quarantined.append(q_rec)

    # 2. Inspect each column
    candidate_keys: List[CandidateKeyQuality] = []

    for col in cols:
        orig_name = next((k for k, v in column_mapping.items() if v == col), col)

        values = [rec.get(col) for _, rec in records]
        null_count = sum(1 for v in values if is_null_value(v, null_set))
        null_pct = round((null_count / total_data_rows * 100.0), 2) if total_data_rows > 0 else 0.0

        non_null_values = [v for v in values if not is_null_value(v, null_set)]
        distinct_vals = set(str(v).strip() for v in non_null_values)
        distinct_count = len(distinct_vals)
        uniqueness_ratio = (
            round(distinct_count / total_data_rows, 4) if total_data_rows > 0 else 0.0
        )

        # Type inference tracking
        type_counts: Dict[str, int] = {
            "identifier": 0,
            "integer": 0,
            "float": 0,
            "date": 0,
            "boolean": 0,
            "string": 0,
        }
        numeric_values: List[float] = []

        for row_idx, (src_row_num, rec) in enumerate(records):
            val = rec.get(col)
            if is_null_value(val, null_set):
                continue

            s_val = str(val).strip()

            # Leading zero identifier check
            if LEADING_ZERO_REGEX.match(s_val):
                type_counts["identifier"] += 1
                continue

            # Boolean check
            b_val, is_b = is_boolean(val)
            if is_b:
                type_counts["boolean"] += 1
                continue

            # Numeric check
            num_val, num_type = parse_numeric(val)
            if num_val is not None:
                type_counts[num_type] += 1
                numeric_values.append(float(num_val))

                # Check for unexpected negative amounts in currency/financial columns
                if is_amount_column(col) and float(num_val) < 0:
                    q_rec = QuarantinedRecord(
                        source_row_index=src_row_num,
                        column_name=col,
                        raw_value=val,
                        quarantine_reason=QuarantineReasonCode.UNEXPECTED_NEGATIVE_AMOUNT,
                        severity=QuarantineSeverity.WARNING,
                        message=(
                            f"Unexpected negative amount ({val}) in currency column '{orig_name}'. "
                            f"Verify if this represents an inverted credit, refund, or data corruption."
                        ),
                        raw_record=rec,
                    )
                    quarantined.append(q_rec)
                continue

            # Date check
            d_str, d_type = parse_date(val)
            if d_str is not None:
                type_counts["date"] += 1
                continue

            # Otherwise string
            type_counts["string"] += 1

        # Determine dominant inferred type
        non_null_total = len(non_null_values)
        if non_null_total == 0:
            inferred_type = "empty"
        elif type_counts["identifier"] > 0 and (type_counts["identifier"] + type_counts["string"] == non_null_total):
            inferred_type = "identifier"
        elif (type_counts["integer"] + type_counts["float"]) / non_null_total >= 0.5:
            inferred_type = "float" if type_counts["float"] > 0 else "integer"
        elif type_counts["date"] / non_null_total >= 0.5 or (is_date_column_name(col) and type_counts["date"] > 0):
            inferred_type = "date"
        elif type_counts["boolean"] / non_null_total >= 0.5:
            inferred_type = "boolean"
        else:
            inferred_type = "string"

        # Check for malformed numbers / dates based on dominant type or column semantics
        if inferred_type in ("integer", "float") or is_amount_column(col):
            for src_row_num, rec in records:
                val = rec.get(col)
                if is_null_value(val, null_set):
                    continue
                num_val, _ = parse_numeric(val)
                if num_val is None:
                    q_rec = QuarantinedRecord(
                        source_row_index=src_row_num,
                        column_name=col,
                        raw_value=val,
                        quarantine_reason=QuarantineReasonCode.INVALID_NUMBER,
                        severity=QuarantineSeverity.BLOCKING,
                        message=f"Malformed number '{val}' in numeric column '{orig_name}' cannot be parsed.",
                        raw_record=rec,
                    )
                    quarantined.append(q_rec)

        if inferred_type == "date" or is_date_column_name(col):
            for src_row_num, rec in records:
                val = rec.get(col)
                if is_null_value(val, null_set):
                    continue
                d_val, _ = parse_date(val)
                if d_val is None:
                    q_rec = QuarantinedRecord(
                        source_row_index=src_row_num,
                        column_name=col,
                        raw_value=val,
                        quarantine_reason=QuarantineReasonCode.MALFORMED_DATE,
                        severity=QuarantineSeverity.WARNING,
                        message=f"Malformed or non-standard date format '{val}' in date column '{orig_name}'.",
                        raw_record=rec,
                    )
                    quarantined.append(q_rec)

        # Min / Max / Samples
        min_v = min(numeric_values) if numeric_values else None
        max_v = max(numeric_values) if numeric_values else None
        sample_vals = non_null_values[:5]

        is_cand_key = (null_count == 0 and distinct_count == total_data_rows and total_data_rows > 0)

        # Candidate key quality assessment
        val_counts: Dict[str, List[int]] = {}
        for src_row_num, rec in records:
            v_str = str(rec.get(col)).strip()
            if v_str not in val_counts:
                val_counts[v_str] = []
            val_counts[v_str].append(src_row_num)

        dupe_rows_count = sum(len(row_nums) for row_nums in val_counts.values() if len(row_nums) > 1)

        if is_cand_key:
            rec_text = "Primary candidate key: 100% unique, zero nulls."
        elif is_candidate_key_name(col) or uniqueness_ratio >= 0.8:
            if null_count > 0:
                rec_text = f"Unsuitable key: contains {null_count} null value(s)."
            elif dupe_rows_count > 0:
                rec_text = f"Key candidate with collisions: {dupe_rows_count} row(s) share duplicate keys."
                # Flag duplicate key records
                for key_val, row_nums in val_counts.items():
                    if len(row_nums) > 1 and not is_null_value(key_val, null_set):
                        for r_num in row_nums:
                            q_rec = QuarantinedRecord(
                                source_row_index=r_num,
                                column_name=col,
                                raw_value=key_val,
                                quarantine_reason=QuarantineReasonCode.DUPLICATE_KEY,
                                severity=QuarantineSeverity.BLOCKING,
                                message=f"Duplicate candidate key value '{key_val}' across rows {row_nums}.",
                            )
                            quarantined.append(q_rec)
            else:
                rec_text = "Viable candidate key."
        else:
            rec_text = f"Non-key attribute (uniqueness {uniqueness_ratio * 100:.1f}%)."

        if is_candidate_key_name(col) or uniqueness_ratio >= 0.5:
            candidate_keys.append(
                CandidateKeyQuality(
                    column_name=col,
                    uniqueness_ratio=uniqueness_ratio,
                    duplicate_count=dupe_rows_count,
                    null_count=null_count,
                    is_viable_key=(null_count == 0 and dupe_rows_count == 0 and total_data_rows > 0),
                    recommendation=rec_text,
                )
            )

        col_anomalies = sum(1 for q in quarantined if q.column_name == col)

        column_profiles.append(
            ColumnProfile(
                column_name=col,
                original_name=orig_name,
                inferred_type=inferred_type,
                total_count=total_data_rows,
                null_count=null_count,
                null_percentage=null_pct,
                distinct_count=distinct_count,
                uniqueness_ratio=uniqueness_ratio,
                is_candidate_key=is_cand_key,
                sample_values=sample_vals,
                min_value=min_v,
                max_value=max_v,
                anomalies_count=col_anomalies,
            )
        )

    # 3. Calculate impact preview
    quarantine_row_set = set(q.source_row_index for q in quarantined)
    blocking_count = sum(1 for q in quarantined if q.severity == QuarantineSeverity.BLOCKING)
    warning_count = sum(1 for q in quarantined if q.severity == QuarantineSeverity.WARNING)

    impact_preview = PreFlightImpactPreview(
        total_source_rows=total_data_rows,
        eligible_rows_count=total_data_rows,  # initially all eligible until excluded
        excluded_rows_count=0,
        quarantined_rows_count=len(quarantine_row_set),
        blocking_count=blocking_count,
        warning_count=warning_count,
    )

    summary = FileProfileSummary(
        file_id=file_id,
        project_id=project_id,
        filename=filename,
        file_type=file_type,
        total_rows=total_data_rows,
        total_columns=len(cols),
        columns=column_profiles,
        candidate_keys=candidate_keys,
        detected_anomalies_count=len(quarantined),
        quarantine_count=len(quarantine_row_set),
        impact_preview=impact_preview,
    )

    return summary, quarantined


def profile_and_persist_source_file(
    db: Session,
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: Optional[User] = None,
) -> Tuple[FileProfileSummary, List[QuarantinedRecord]]:
    """Extract records from source file, execute profiling, and persist profile sidecar."""
    project = get_project_by_id(db, project_id, current_user=current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    source_file = db.query(SourceFile).filter(
        SourceFile.id == file_id,
        SourceFile.project_id == project_id,
    ).first()
    if source_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file not found for this project.",
        )

    path_resolved = Path(source_file.storage_path).resolve()
    if not path_resolved.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file content not found on disk.",
        )

    cfg = PreprocessingConfig()
    null_set = set(v.strip().lower() for v in cfg.null_values)

    (
        records,
        cols,
        mapping,
        dup_rows,
        empty_rows,
        issues,
        total_count,
    ) = extract_dataset_records(path_resolved, source_file.file_type, cfg)

    # Check for shifted rows in CSV if raw rows had mismatched delimiters
    shifted_rows: List[Tuple[int, int, int]] = []
    if source_file.file_type.lower() == "csv":
        try:
            raw_h, raw_rows, _ = read_csv_rows(path_resolved, max_rows=cfg.max_rows)
            expected_len = len(raw_h)
            for r_num, row_cells in raw_rows:
                if len(row_cells) != expected_len:
                    shifted_rows.append((r_num, expected_len, len(row_cells)))
        except Exception:
            pass

    summary, quarantined = profile_dataset_records(
        file_id=source_file.id,
        project_id=project_id,
        filename=source_file.original_filename,
        file_type=source_file.file_type,
        records=records,
        raw_headers=cols,
        column_mapping=mapping,
        null_set=null_set,
        raw_rows_with_mismatch=shifted_rows,
    )

    # Apply existing quarantine resolutions if already saved
    q_path = _get_quarantine_sidecar_path(path_resolved)
    if q_path.exists():
        try:
            q_data = json.loads(q_path.read_text(encoding="utf-8"))
            resolutions = q_data.get("resolutions", {})
            notes = q_data.get("notes", {})
            for q in quarantined:
                r_key = str(q.source_row_index)
                if r_key in resolutions:
                    q.resolution_action = ResolutionAction(resolutions[r_key])
                    q.resolution_note = notes.get(r_key)
        except Exception:
            pass

    # Recalculate impact preview based on current resolution actions
    excluded_rows = set(
        q.source_row_index for q in quarantined if q.resolution_action == ResolutionAction.EXCLUDE
    )
    summary.impact_preview.excluded_rows_count = len(excluded_rows)
    summary.impact_preview.eligible_rows_count = max(0, summary.total_rows - len(excluded_rows))

    # Persist profile sidecar
    profile_path = _get_profile_sidecar_path(path_resolved)
    profile_path.write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    return summary, quarantined


def get_file_profile(
    db: Session,
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: Optional[User] = None,
) -> FileProfileSummary:
    """Retrieve or compute file profile summary."""
    summary, _ = profile_and_persist_source_file(db, project_id, file_id, current_user)
    return summary


def get_file_quarantine(
    db: Session,
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: Optional[User] = None,
) -> QuarantineListResponse:
    """Retrieve list of quarantined records with current resolutions and impact."""
    summary, quarantined = profile_and_persist_source_file(db, project_id, file_id, current_user)
    return QuarantineListResponse(
        file_id=file_id,
        total_quarantined=len(quarantined),
        records=quarantined,
        impact_preview=summary.impact_preview,
    )


def resolve_quarantine_records(
    db: Session,
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    request: QuarantineResolutionRequest,
    current_user: Optional[User] = None,
) -> QuarantineResolutionResponse:
    """
    Persist resolution decisions ('EXCLUDE' vs 'ACCEPT_AS_VALID') for quarantined records.
    Updates the impact preview and returns updated counts.
    """
    source_file = db.query(SourceFile).filter(
        SourceFile.id == file_id,
        SourceFile.project_id == project_id,
    ).first()
    if source_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file not found for this project.",
        )

    path_resolved = Path(source_file.storage_path).resolve()
    q_path = _get_quarantine_sidecar_path(path_resolved)

    existing_resolutions: Dict[str, str] = {}
    existing_notes: Dict[str, str] = {}
    if q_path.exists():
        try:
            q_data = json.loads(q_path.read_text(encoding="utf-8"))
            existing_resolutions = q_data.get("resolutions", {})
            existing_notes = q_data.get("notes", {})
        except Exception:
            pass

    for item in request.resolutions:
        r_key = str(item.source_row_index)
        existing_resolutions[r_key] = item.action.value
        if item.note:
            existing_notes[r_key] = item.note

    # Save to quarantine sidecar (raw source file is untouched / immutable)
    q_path.write_text(
        json.dumps(
            {
                "file_id": str(file_id),
                "resolutions": existing_resolutions,
                "notes": existing_notes,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Re-fetch profile & quarantine with updated resolutions applied
    summary, quarantined = profile_and_persist_source_file(db, project_id, file_id, current_user)

    excluded = [
        int(k) for k, v in existing_resolutions.items() if v == ResolutionAction.EXCLUDE.value
    ]
    accepted = [
        int(k) for k, v in existing_resolutions.items() if v == ResolutionAction.ACCEPT_AS_VALID.value
    ]

    return QuarantineResolutionResponse(
        file_id=file_id,
        resolved_count=len(request.resolutions),
        excluded_row_indices=sorted(excluded),
        accepted_row_indices=sorted(accepted),
        impact_preview=summary.impact_preview,
        quarantined_records=quarantined,
    )
