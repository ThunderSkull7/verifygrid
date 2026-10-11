"""Core Verification Engine for VerifyGrid.

Compares two datasets, identifies matching records, missing records,
duplicate matching keys, and field-level discrepancies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.source_file import SourceFile
from app.models.verification_run import VerificationRun, VerificationDiscrepancy
from app.schemas.preprocessing import ColumnMetadata, PreprocessingConfig, ValidationIssue
from app.schemas.result import (
    DiscrepancyCategory,
    FieldDifference,
    MatchStatus,
    VerificationRequest,
    VerificationResponse,
    VerificationResultItem,
    VerificationSummary,
)
from app.services.preprocessing import extract_dataset_records
from app.services.project_service import get_project_by_id
from app.utils.normalization import (
    clean_whitespace,
    is_boolean,
    is_null_value,
    normalize_column_name,
    parse_date,
    parse_numeric,
    LEADING_ZERO_REGEX,
)


def normalize_key_value(
    val: Any,
    null_set: Set[str],
    ignore_whitespace: bool = True,
    ignore_case: bool = False,
) -> Any:
    """Normalize a key value for deterministic matching."""
    if is_null_value(val, null_set):
        return None

    if isinstance(val, (int, float)):
        if isinstance(val, float) and val.is_integer():
            return int(val)
        return val

    val_str = str(val)
    if ignore_whitespace:
        val_str = val_str.strip()

    # Preserve leading zero identifiers as exact strings
    if LEADING_ZERO_REGEX.match(val_str):
        return val_str

    if ignore_case:
        val_str = val_str.lower()

    # If it parses to a clean integer or float, normalize to numeric
    num_val, _ = parse_numeric(val_str)
    if num_val is not None:
        return num_val

    return val_str


def compare_field_values(
    src_val: Any,
    tgt_val: Any,
    null_set: Set[str],
    numeric_tolerance: float = 0.0,
    ignore_whitespace: bool = True,
    ignore_case: bool = False,
) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Compare two field values considering null semantics, types, and formatting.
    Returns:
        (is_match, difference_type, src_type, tgt_type)
        where difference_type is None if match, else 'null_mismatch', 'value_mismatch', 'type_mismatch'.
    """
    src_is_null = is_null_value(src_val, null_set)
    tgt_is_null = is_null_value(tgt_val, null_set)

    # 1. Null handling
    if src_is_null and tgt_is_null:
        return True, None, "null", "null"
    if src_is_null != tgt_is_null:
        src_type = "null" if src_is_null else type(src_val).__name__
        tgt_type = "null" if tgt_is_null else type(tgt_val).__name__
        return False, "null_mismatch", src_type, tgt_type

    # 2. String representation for leading zero preservation
    src_str = str(src_val).strip() if ignore_whitespace and isinstance(src_val, str) else str(src_val)
    tgt_str = str(tgt_val).strip() if ignore_whitespace and isinstance(tgt_val, str) else str(tgt_val)

    # If either value has leading zeros (identifier), strictly compare strings
    if LEADING_ZERO_REGEX.match(src_str) or LEADING_ZERO_REGEX.match(tgt_str):
        if src_str == tgt_str:
            return True, None, "identifier", "identifier"
        return False, "value_mismatch", "identifier", "identifier"

    # 3. Boolean normalization
    bool_src, is_bool_src = is_boolean(src_val)
    bool_tgt, is_bool_tgt = is_boolean(tgt_val)
    if is_bool_src and is_bool_tgt:
        if bool_src == bool_tgt:
            return True, None, "boolean", "boolean"
        return False, "value_mismatch", "boolean", "boolean"
    if is_bool_src != is_bool_tgt:
        src_type = "boolean" if is_bool_src else type(src_val).__name__
        tgt_type = "boolean" if is_bool_tgt else type(tgt_val).__name__
        return False, "type_mismatch", src_type, tgt_type

    # 4. Numeric normalization
    num_src, num_t_src = parse_numeric(src_val)
    num_tgt, num_t_tgt = parse_numeric(tgt_val)
    if num_src is not None and num_tgt is not None:
        if numeric_tolerance > 0.0:
            diff = abs(float(num_src) - float(num_tgt))
            if diff <= numeric_tolerance:
                return True, None, num_t_src, num_t_tgt
            return False, "value_mismatch", num_t_src, num_t_tgt
        else:
            if num_src == num_tgt:
                return True, None, num_t_src, num_t_tgt
            return False, "value_mismatch", num_t_src, num_t_tgt
    if (num_src is not None) != (num_tgt is not None):
        src_type = num_t_src or type(src_val).__name__
        tgt_type = num_t_tgt or type(tgt_val).__name__
        return False, "type_mismatch", src_type, tgt_type

    # 5. Date normalization
    d_src, dt_src = parse_date(src_val)
    d_tgt, dt_tgt = parse_date(tgt_val)
    if d_src is not None and d_tgt is not None:
        if d_src == d_tgt:
            return True, None, dt_src, dt_tgt
        return False, "value_mismatch", dt_src, dt_tgt
    if (d_src is not None) != (d_tgt is not None):
        src_type = dt_src or type(src_val).__name__
        tgt_type = dt_tgt or type(tgt_val).__name__
        return False, "type_mismatch", src_type, tgt_type

    # 6. String / whitespace / case normalization
    s_src = clean_whitespace(src_val) if ignore_whitespace else src_val
    s_tgt = clean_whitespace(tgt_val) if ignore_whitespace else tgt_val
    if isinstance(s_src, str) and isinstance(s_tgt, str):
        if ignore_case:
            match = s_src.lower() == s_tgt.lower()
        else:
            match = s_src == s_tgt
        if match:
            return True, None, "string", "string"
        return False, "value_mismatch", "string", "string"

    # 7. Fallback standard equality
    if src_val == tgt_val:
        return True, None, type(src_val).__name__, type(tgt_val).__name__

    diff_type = "type_mismatch" if type(src_val) != type(tgt_val) else "value_mismatch"
    return False, diff_type, type(src_val).__name__, type(tgt_val).__name__


def _resolve_column(
    col_name: str,
    available_cols: List[str],
) -> Optional[str]:
    """Resolve a requested column against available dataset columns."""
    col_name_clean = col_name.strip()
    # 1. Exact match
    if col_name_clean in available_cols:
        return col_name_clean

    # 2. Case-insensitive match
    for c in available_cols:
        if c.lower() == col_name_clean.lower():
            return c

    # 3. Normalized snake_case match
    norm_name = normalize_column_name(col_name_clean)
    for c in available_cols:
        if normalize_column_name(c) == norm_name:
            return c

    return None


def verify_datasets(
    source_records: List[Tuple[int, Dict[str, Any]]],
    target_records: List[Tuple[int, Dict[str, Any]]],
    key_columns: List[str],
    column_mapping: Optional[Dict[str, str]] = None,
    compare_columns: Optional[List[str]] = None,
    ignore_columns: Optional[List[str]] = None,
    numeric_tolerance: float = 0.0,
    ignore_whitespace: bool = True,
    ignore_case: bool = False,
    null_values: Optional[List[str]] = None,
    include_identical: bool = True,
) -> Tuple[VerificationSummary, List[VerificationResultItem], List[VerificationResultItem], List[ValidationIssue], List[str]]:
    """
    Core record matching and field-level comparison engine.

    Returns:
        - summary: VerificationSummary
        - results: List[VerificationResultItem] (all comparisons or discrepancies)
        - discrepancies: List[VerificationResultItem] (only discrepancies)
        - warnings: List[ValidationIssue]
        - errors: List[str]
    """
    if not key_columns or not any(k.strip() for k in key_columns):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one non-empty matching key column must be specified.",
        )

    clean_key_columns = [k.strip() for k in key_columns if k.strip()]
    column_mapping = column_mapping or {}
    ignore_cols_set = {c.strip() for c in (ignore_columns or [])}
    null_set = {
        v.strip().lower()
        for v in (
            null_values
            if null_values is not None
            else ["", "null", "none", "nil", "n/a", "na", "nan", "-", "--", "undefined", "#n/a"]
        )
    }

    warnings: List[ValidationIssue] = []
    errors: List[str] = []

    # 1. Inspect available columns
    src_available_cols: List[str] = []
    if source_records:
        src_available_cols = list(source_records[0][1].keys())

    tgt_available_cols: List[str] = []
    if target_records:
        tgt_available_cols = list(target_records[0][1].keys())

    # Handle completely empty datasets
    if not source_records and not target_records:
        warnings.append(
            ValidationIssue(
                level="warning",
                issue_type="empty_datasets",
                message="Both source and target datasets are empty.",
            )
        )
        empty_summary = VerificationSummary(
            total_source_records=0,
            total_target_records=0,
            matched_records=0,
            identical_matches=0,
            field_mismatches=0,
            records_with_differences=0,
            unmatched_source_records=0,
            unmatched_target_records=0,
            duplicate_source_records=0,
            duplicate_target_records=0,
            duplicate_source_keys_count=0,
            duplicate_target_keys_count=0,
            conflicting_duplicate_records=0,
            total_discrepancies=0,
            status="completed_with_warnings",
        )
        return empty_summary, [], [], warnings, errors

    # 2. Resolve source key columns
    resolved_src_key_cols: List[str] = []
    resolved_tgt_key_cols: List[str] = []

    for k in clean_key_columns:
        # Resolve in source
        if source_records:
            resolved_s = _resolve_column(k, src_available_cols)
            if resolved_s is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Key column '{k}' does not exist in source dataset. Available columns: {src_available_cols}",
                )
            resolved_src_key_cols.append(resolved_s)
        else:
            resolved_src_key_cols.append(k)

        # Resolve in target (check column_mapping first, then exact/normalized name)
        mapped_target_name = column_mapping.get(k, k)
        if target_records:
            resolved_t = _resolve_column(mapped_target_name, tgt_available_cols)
            if resolved_t is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        f"Key column '{mapped_target_name}' (mapped from '{k}') does not exist in target dataset. "
                        f"Available columns: {tgt_available_cols}"
                    ),
                )
            resolved_tgt_key_cols.append(resolved_t)
        else:
            resolved_tgt_key_cols.append(mapped_target_name)

    # 3. Validate explicit column mappings
    for s_map, t_map in column_mapping.items():
        if source_records and _resolve_column(s_map, src_available_cols) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Mapped column '{s_map}' does not exist in source dataset. Available columns: {src_available_cols}",
            )
        if target_records and _resolve_column(t_map, tgt_available_cols) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Mapped column '{t_map}' does not exist in target dataset. Available columns: {tgt_available_cols}",
            )

    # 4. Determine field comparison pairs: List of (source_col, target_col)
    field_pairs: List[Tuple[str, str]] = []
    key_src_set = set(resolved_src_key_cols)

    if compare_columns is not None:
        for c in compare_columns:
            c_clean = c.strip()
            if c_clean in ignore_cols_set:
                continue
            src_col = _resolve_column(c_clean, src_available_cols) if source_records else c_clean
            tgt_name = column_mapping.get(c_clean, c_clean)
            tgt_col = _resolve_column(tgt_name, tgt_available_cols) if target_records else tgt_name
            if src_col and tgt_col and src_col not in key_src_set:
                field_pairs.append((src_col, tgt_col))
    else:
        # Default: all intersecting columns (mapped or matching name) excluding keys and ignore_columns
        for s_col in src_available_cols:
            if s_col in key_src_set or s_col in ignore_cols_set:
                continue
            t_col_name = column_mapping.get(s_col, s_col)
            t_col = _resolve_column(t_col_name, tgt_available_cols)
            if t_col and t_col not in ignore_cols_set:
                field_pairs.append((s_col, t_col))
            else:
                warnings.append(
                    ValidationIssue(
                        level="info",
                        issue_type="unmapped_column",
                        message=f"Source column '{s_col}' was excluded from field comparison (no corresponding target column).",
                        column_name=s_col,
                    )
                )

    # 5. Group source and target records by normalized key tuple
    # Key tuple -> list of (row_number, record)
    source_key_groups: Dict[Tuple[Any, ...], List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    target_key_groups: Dict[Tuple[Any, ...], List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    key_display_dicts: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

    for row_num, rec in source_records:
        k_tuple_vals = []
        k_disp = {}
        for s_col in resolved_src_key_cols:
            val = rec.get(s_col)
            k_disp[s_col] = val
            k_norm = normalize_key_value(val, null_set, ignore_whitespace, ignore_case)
            if k_norm is None:
                warnings.append(
                    ValidationIssue(
                        level="warning",
                        issue_type="null_key",
                        row_number=row_num,
                        column_name=s_col,
                        message=f"Source row {row_num} has null value for key column '{s_col}'.",
                    )
                )
            k_tuple_vals.append(k_norm)
        k_tuple = tuple(k_tuple_vals)
        source_key_groups[k_tuple].append((row_num, rec))
        if k_tuple not in key_display_dicts:
            key_display_dicts[k_tuple] = k_disp

    for row_num, rec in target_records:
        k_tuple_vals = []
        k_disp = {}
        for idx, t_col in enumerate(resolved_tgt_key_cols):
            val = rec.get(t_col)
            s_col_name = resolved_src_key_cols[idx]
            k_disp[s_col_name] = val
            k_norm = normalize_key_value(val, null_set, ignore_whitespace, ignore_case)
            if k_norm is None:
                warnings.append(
                    ValidationIssue(
                        level="warning",
                        issue_type="null_key",
                        row_number=row_num,
                        column_name=t_col,
                        message=f"Target row {row_num} has null value for key column '{t_col}'.",
                    )
                )
            k_tuple_vals.append(k_norm)
        k_tuple = tuple(k_tuple_vals)
        target_key_groups[k_tuple].append((row_num, rec))
        if k_tuple not in key_display_dicts:
            key_display_dicts[k_tuple] = k_disp

    # 6. Execute comparison across all distinct key tuples
    all_keys = list(set(source_key_groups.keys()) | set(target_key_groups.keys()))
    # Deterministic sorting
    all_keys.sort(key=lambda x: str(x))

    results: List[VerificationResultItem] = []
    discrepancies: List[VerificationResultItem] = []

    # Counters
    identical_matches = 0
    field_mismatches = 0
    unmatched_source_records = 0
    unmatched_target_records = 0
    duplicate_source_records = 0
    duplicate_target_records = 0
    duplicate_source_keys_count = 0
    duplicate_target_keys_count = 0
    conflicting_duplicate_records = 0

    for k_tuple in all_keys:
        s_list = source_key_groups.get(k_tuple, [])
        t_list = target_key_groups.get(k_tuple, [])
        k_dict = key_display_dicts[k_tuple]

        s_count = len(s_list)
        t_count = len(t_list)

        # Case 1: Unique 1-to-1 match
        if s_count == 1 and t_count == 1:
            s_row_num, s_rec = s_list[0]
            t_row_num, t_rec = t_list[0]

            diffs: List[FieldDifference] = []
            for s_col, t_col in field_pairs:
                s_val = s_rec.get(s_col)
                t_val = t_rec.get(t_col)

                is_match, diff_type, s_type, t_type = compare_field_values(
                    src_val=s_val,
                    tgt_val=t_val,
                    null_set=null_set,
                    numeric_tolerance=numeric_tolerance,
                    ignore_whitespace=ignore_whitespace,
                    ignore_case=ignore_case,
                )
                if not is_match:
                    diffs.append(
                        FieldDifference(
                            field_name=s_col,
                            source_field=s_col,
                            target_field=t_col,
                            source_value=s_val,
                            target_value=t_val,
                            source_type=s_type,
                            target_type=t_type,
                            difference_type=diff_type or "value_mismatch",
                            message=f"Difference in '{s_col}': '{s_val}' vs '{t_val}'",
                        )
                    )

            if not diffs:
                identical_matches += 1
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.IDENTICAL,
                    discrepancy_category=DiscrepancyCategory.NONE,
                    source_row_number=s_row_num,
                    target_row_number=t_row_num,
                    source_row_numbers=[s_row_num],
                    target_row_numbers=[t_row_num],
                    source_record=s_rec,
                    target_record=t_rec,
                    field_differences=[],
                    message="Records match identically.",
                )
                if include_identical:
                    results.append(item)
            else:
                field_mismatches += 1
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.FIELD_MISMATCH,
                    discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
                    source_row_number=s_row_num,
                    target_row_number=t_row_num,
                    source_row_numbers=[s_row_num],
                    target_row_numbers=[t_row_num],
                    source_record=s_rec,
                    target_record=t_rec,
                    field_differences=diffs,
                    message=f"{len(diffs)} field difference(s) detected.",
                )
                results.append(item)
                discrepancies.append(item)

        # Case 2: Only in source (unique key in source, absent in target)
        elif s_count == 1 and t_count == 0:
            s_row_num, s_rec = s_list[0]
            unmatched_source_records += 1
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.MISSING_IN_TARGET,
                discrepancy_category=DiscrepancyCategory.MISSING_RECORD,
                source_row_number=s_row_num,
                target_row_number=None,
                source_row_numbers=[s_row_num],
                target_row_numbers=[],
                source_record=s_rec,
                target_record=None,
                field_differences=[],
                message="Record present in source dataset but missing in target dataset.",
            )
            results.append(item)
            discrepancies.append(item)

        # Case 3: Only in target (unique key in target, absent in source)
        elif s_count == 0 and t_count == 1:
            t_row_num, t_rec = t_list[0]
            unmatched_target_records += 1
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.MISSING_IN_SOURCE,
                discrepancy_category=DiscrepancyCategory.MISSING_RECORD,
                source_row_number=None,
                target_row_number=t_row_num,
                source_row_numbers=[],
                target_row_numbers=[t_row_num],
                source_record=None,
                target_record=t_rec,
                field_differences=[],
                message="Record present in target dataset but missing in source dataset.",
            )
            results.append(item)
            discrepancies.append(item)

        # Case 4: Duplicate in source, absent in target
        elif s_count > 1 and t_count == 0:
            s_row_nums = [r[0] for r in s_list]
            duplicate_source_records += s_count
            duplicate_source_keys_count += 1
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.DUPLICATE_KEY_SOURCE,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                source_row_number=s_row_nums[0],
                target_row_number=None,
                source_row_numbers=s_row_nums,
                target_row_numbers=[],
                source_record=s_list[0][1],
                target_record=None,
                field_differences=[],
                message=f"Duplicate matching key in source across {s_count} rows {s_row_nums}; missing in target.",
            )
            results.append(item)
            discrepancies.append(item)

        # Case 5: Duplicate in target, absent in source
        elif s_count == 0 and t_count > 1:
            t_row_nums = [r[0] for r in t_list]
            duplicate_target_records += t_count
            duplicate_target_keys_count += 1
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.DUPLICATE_KEY_TARGET,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                source_row_number=None,
                target_row_number=t_row_nums[0],
                source_row_numbers=[],
                target_row_numbers=t_row_nums,
                source_record=None,
                target_record=t_list[0][1],
                field_differences=[],
                message=f"Duplicate matching key in target across {t_count} rows {t_row_nums}; missing in source.",
            )
            results.append(item)
            discrepancies.append(item)

        # Case 6: Duplicate in source, single row in target
        elif s_count > 1 and t_count == 1:
            s_row_nums = [r[0] for r in s_list]
            t_row_num = t_list[0][0]
            duplicate_source_records += s_count
            duplicate_source_keys_count += 1
            conflicting_duplicate_records += 1
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.AMBIGUOUS_DUPLICATE,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                source_row_number=s_row_nums[0],
                target_row_number=t_row_num,
                source_row_numbers=s_row_nums,
                target_row_numbers=[t_row_num],
                source_record=s_list[0][1],
                target_record=t_list[0][1],
                field_differences=[],
                message=(
                    f"Ambiguous match: key is duplicated across {s_count} source rows {s_row_nums} "
                    f"for target row {t_row_num}."
                ),
            )
            results.append(item)
            discrepancies.append(item)

        # Case 7: Single row in source, duplicate in target
        elif s_count == 1 and t_count > 1:
            s_row_num = s_list[0][0]
            t_row_nums = [r[0] for r in t_list]
            duplicate_target_records += t_count
            duplicate_target_keys_count += 1
            conflicting_duplicate_records += 1
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.AMBIGUOUS_DUPLICATE,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                source_row_number=s_row_num,
                target_row_number=t_row_nums[0],
                source_row_numbers=[s_row_num],
                target_row_numbers=t_row_nums,
                source_record=s_list[0][1],
                target_record=t_list[0][1],
                field_differences=[],
                message=(
                    f"Ambiguous match: key is duplicated across {t_count} target rows {t_row_nums} "
                    f"for source row {s_row_num}."
                ),
            )
            results.append(item)
            discrepancies.append(item)

        # Case 8: Duplicate in both source and target
        elif s_count > 1 and t_count > 1:
            s_row_nums = [r[0] for r in s_list]
            t_row_nums = [r[0] for r in t_list]
            duplicate_source_records += s_count
            duplicate_target_records += t_count
            duplicate_source_keys_count += 1
            duplicate_target_keys_count += 1
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.DUPLICATE_KEY_BOTH,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                source_row_number=s_row_nums[0],
                target_row_number=t_row_nums[0],
                source_row_numbers=s_row_nums,
                target_row_numbers=t_row_nums,
                source_record=s_list[0][1],
                target_record=t_list[0][1],
                field_differences=[],
                message=(
                    f"Duplicate matching key in both datasets: {s_count} source rows {s_row_nums}, "
                    f"{t_count} target rows {t_row_nums}."
                ),
            )
            results.append(item)
            discrepancies.append(item)

    total_discrepancies = len(discrepancies)
    status_str = "completed_with_warnings" if warnings else "completed"

    summary = VerificationSummary(
        total_source_records=len(source_records),
        total_target_records=len(target_records),
        matched_records=identical_matches + field_mismatches,
        identical_matches=identical_matches,
        field_mismatches=field_mismatches,
        records_with_differences=field_mismatches,
        unmatched_source_records=unmatched_source_records,
        unmatched_target_records=unmatched_target_records,
        duplicate_source_records=duplicate_source_records,
        duplicate_target_records=duplicate_target_records,
        duplicate_source_keys_count=duplicate_source_keys_count,
        duplicate_target_keys_count=duplicate_target_keys_count,
        conflicting_duplicate_records=conflicting_duplicate_records,
        total_discrepancies=total_discrepancies,
        status=status_str,
    )

    return summary, results, discrepancies, warnings, errors


def verify_project_files(
    db: Session,
    project_id: uuid.UUID,
    request: VerificationRequest,
) -> VerificationResponse:
    """
    Execute full verification between two uploaded source files belonging to a project.
    Validates project authorization, source file isolation, parses and normalizes
    datasets, and runs core comparison engine.
    """
    # 1. Project existence & authorization check
    project = get_project_by_id(db, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    # 2. Source files isolation & project scoping check
    source_file = db.query(SourceFile).filter(
        SourceFile.id == request.source_file_id,
        SourceFile.project_id == project_id,
    ).first()
    if source_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file not found for this project.",
        )

    target_file = db.query(SourceFile).filter(
        SourceFile.id == request.target_file_id,
        SourceFile.project_id == project_id,
    ).first()
    if target_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target file not found for this project.",
        )

    # 3. Path safety and existence
    storage_root_resolved = settings.storage_root.resolve()
    for f_obj, role in [(source_file, "Source"), (target_file, "Target")]:
        try:
            path_resolved = Path(f_obj.storage_path).resolve()
            if not str(path_resolved).startswith(str(storage_root_resolved)):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access to {role.lower()} file path is restricted.",
                )
            if not path_resolved.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"{role} file content not found on disk.",
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{role} file storage path could not be resolved.",
            )

    # 4. Extract preprocessed records from both files
    cfg = request.preprocessing_config or PreprocessingConfig()
    src_path = Path(source_file.storage_path).resolve()
    tgt_path = Path(target_file.storage_path).resolve()

    (
        src_records,
        src_cols,
        src_mapping,
        src_dup_rows,
        src_empty_rows,
        src_issues,
        src_total,
    ) = extract_dataset_records(src_path, source_file.file_type, cfg)

    (
        tgt_records,
        tgt_cols,
        tgt_mapping,
        tgt_dup_rows,
        tgt_empty_rows,
        tgt_issues,
        tgt_total,
    ) = extract_dataset_records(tgt_path, target_file.file_type, cfg)

    # 5. Run verification engine
    summary, results, discrepancies, comp_warnings, comp_errors = verify_datasets(
        source_records=src_records,
        target_records=tgt_records,
        key_columns=request.key_columns,
        column_mapping=request.column_mapping,
        compare_columns=request.compare_columns,
        ignore_columns=request.ignore_columns,
        numeric_tolerance=request.numeric_tolerance,
        ignore_whitespace=request.ignore_whitespace,
        ignore_case=request.ignore_case,
        null_values=cfg.null_values,
        include_identical=request.include_identical,
    )

    all_warnings = src_issues + tgt_issues + comp_warnings

    return VerificationResponse(
        project_id=project_id,
        source_file_id=source_file.id,
        target_file_id=target_file.id,
        key_columns=request.key_columns,
        column_mapping=request.column_mapping or {},
        summary=summary,
        results=results,
        discrepancies=discrepancies,
        warnings=all_warnings,
        errors=comp_errors,
    )


def create_and_execute_verification_run(
    db: Session,
    project_id: uuid.UUID,
    request: VerificationRequest,
) -> VerificationRun:
    """
    Create a persistent VerificationRun record, execute reconciliation,
    store summary metrics and individual discrepancy items in a safe transaction.
    """
    # 1. Project existence & authorization check
    project = get_project_by_id(db, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    # 2. Source files isolation & project scoping check
    source_file = db.query(SourceFile).filter(
        SourceFile.id == request.source_file_id,
        SourceFile.project_id == project_id,
    ).first()
    if source_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file not found for this project.",
        )

    target_file = db.query(SourceFile).filter(
        SourceFile.id == request.target_file_id,
        SourceFile.project_id == project_id,
    ).first()
    if target_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target file not found for this project.",
        )

    # 3. Path safety and existence
    storage_root_resolved = settings.storage_root.resolve()
    for f_obj, role in [(source_file, "Source"), (target_file, "Target")]:
        try:
            path_resolved = Path(f_obj.storage_path).resolve()
            if not str(path_resolved).startswith(str(storage_root_resolved)):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access to {role.lower()} file path is restricted.",
                )
            if not path_resolved.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"{role} file content not found on disk.",
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{role} file storage path could not be resolved.",
            )

    # 4. Create persistent run in running state
    now_utc = datetime.now(timezone.utc)
    config_dict = {
        "compare_columns": request.compare_columns,
        "ignore_columns": request.ignore_columns,
        "numeric_tolerance": request.numeric_tolerance,
        "ignore_whitespace": request.ignore_whitespace,
        "ignore_case": request.ignore_case,
        "include_identical": request.include_identical,
    }

    run = VerificationRun(
        project_id=project_id,
        source_file_id=source_file.id,
        target_file_id=target_file.id,
        status="running",
        key_columns=request.key_columns,
        column_mapping=request.column_mapping or {},
        configuration=config_dict,
        started_at=now_utc,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # 5. Execute verification safely
    cfg = request.preprocessing_config or PreprocessingConfig()
    src_path = Path(source_file.storage_path).resolve()
    tgt_path = Path(target_file.storage_path).resolve()

    try:
        with db.begin_nested():
            (
                src_records,
                src_cols,
                src_mapping,
                src_dup_rows,
                src_empty_rows,
                src_issues,
                src_total,
            ) = extract_dataset_records(src_path, source_file.file_type, cfg)

            (
                tgt_records,
                tgt_cols,
                tgt_mapping,
                tgt_dup_rows,
                tgt_empty_rows,
                tgt_issues,
                tgt_total,
            ) = extract_dataset_records(tgt_path, target_file.file_type, cfg)

            summary, results, discrepancies, comp_warnings, comp_errors = verify_datasets(
                source_records=src_records,
                target_records=tgt_records,
                key_columns=request.key_columns,
                column_mapping=request.column_mapping,
                compare_columns=request.compare_columns,
                ignore_columns=request.ignore_columns,
                numeric_tolerance=request.numeric_tolerance,
                ignore_whitespace=request.ignore_whitespace,
                ignore_case=request.ignore_case,
                null_values=cfg.null_values,
                include_identical=request.include_identical,
            )

            run.status = "completed"
            run.summary = summary.model_dump()
            run.completed_at = datetime.now(timezone.utc)

            # Bulk save discrepancies (never store full dataset rows, only discrepancies)
            for item in discrepancies:
                disc = VerificationDiscrepancy(
                    run_id=run.id,
                    match_status=item.match_status.value,
                    discrepancy_category=item.discrepancy_category.value,
                    key_values=item.key_values,
                    source_row_number=item.source_row_number,
                    target_row_number=item.target_row_number,
                    source_row_numbers=item.source_row_numbers,
                    target_row_numbers=item.target_row_numbers,
                    source_record=item.source_record,
                    target_record=item.target_record,
                    field_differences=[d.model_dump() for d in item.field_differences] if item.field_differences else None,
                    message=item.message,
                )
                db.add(disc)

        db.commit()
        db.refresh(run)
        return run

    except Exception as exc:
        try:
            run.status = "failed"
            error_detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            run.error_message = error_detail
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            pass
        raise



def get_verification_run(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
) -> VerificationRun:
    """Retrieve a verification run with project authorization check."""
    project = get_project_by_id(db, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    run = db.query(VerificationRun).filter(
        VerificationRun.id == run_id,
        VerificationRun.project_id == project_id,
    ).first()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verification run not found for this project.",
        )
    return run


def list_verification_runs(
    db: Session,
    project_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = None,
) -> Tuple[int, List[VerificationRun]]:
    """List verification runs for a project with pagination and status filtering."""
    project = get_project_by_id(db, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    query = db.query(VerificationRun).filter(VerificationRun.project_id == project_id)
    if status_filter:
        query = query.filter(VerificationRun.status == status_filter)

    total = query.count()
    items = query.order_by(VerificationRun.created_at.desc()).offset(skip).limit(limit).all()
    return total, items


def list_run_discrepancies(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
    discrepancy_category: Optional[str] = None,
    match_status: Optional[str] = None,
) -> Tuple[int, List[VerificationDiscrepancy]]:
    """Paginate and filter discrepancy results for an authorized verification run."""
    # Enforce project ownership
    get_verification_run(db, project_id, run_id)

    query = db.query(VerificationDiscrepancy).filter(VerificationDiscrepancy.run_id == run_id)
    if discrepancy_category:
        query = query.filter(VerificationDiscrepancy.discrepancy_category == discrepancy_category)
    if match_status:
        query = query.filter(VerificationDiscrepancy.match_status == match_status)

    total = query.count()
    items = (
        query.order_by(
            VerificationDiscrepancy.source_row_number.asc().nulls_last(),
            VerificationDiscrepancy.target_row_number.asc().nulls_last(),
            VerificationDiscrepancy.created_at.asc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, items

