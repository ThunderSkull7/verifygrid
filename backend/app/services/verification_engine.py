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
from sqlalchemy import cast, func, or_, String
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.source_file import SourceFile
from app.models.user import User
from app.models.verification_run import VerificationRun, VerificationDiscrepancy
from app.schemas.preprocessing import ColumnMetadata, PreprocessingConfig, ValidationIssue
import re
from rapidfuzz import fuzz

from app.schemas.result import (
    DiscrepancyCategory,
    FieldComparisonDiff,
    FieldDifference,
    MatchStatus,
    ReasonCode,
    SideBySideInspectionResponse,
    VerificationRequest,
    VerificationResponse,
    VerificationResultItem,
    VerificationSummary,
)
from app.schemas.multisource import (
    MultiSourceVerificationRequest,
    MultiSourceVerificationResponse,
    SourceDefinition,
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

NAME_COLUMN_KEYWORDS = {
    "name",
    "full_name",
    "first_name",
    "last_name",
    "student_name",
    "customer_name",
    "employee_name",
    "client_name",
    "person_name",
}

STATUS_COLUMN_KEYWORDS = {
    "status",
    "enrollment_status",
    "account_status",
    "state",
    "user_status",
    "membership_status",
}


def normalize_name_tokens(name: Any) -> List[str]:
    """Clean punctuation, normalize whitespace, and extract lowercase word tokens."""
    if name is None:
        return []
    s = str(name).strip()
    cleaned = re.sub(r"[^\w\s]", " ", s.lower())
    return [t for t in cleaned.split() if t]


def check_initials_match(tokens1: List[str], tokens2: List[str]) -> bool:
    """
    Check if one name is an initial variation of the other.
    E.g., ['j', 'doe'] vs ['john', 'doe']
    or ['j', 'f', 'kennedy'] vs ['john', 'f', 'kennedy']
    """
    if len(tokens1) != len(tokens2) or not tokens1:
        return False
    has_initial = any(len(t) == 1 for t in tokens1 + tokens2)
    if not has_initial:
        return False
    for t1, t2 in zip(tokens1, tokens2):
        if t1 == t2:
            continue
        if len(t1) == 1 and len(t2) > 1 and t2.startswith(t1):
            continue
        if len(t2) == 1 and len(t1) > 1 and t1.startswith(t2):
            continue
        return False
    return True


def evaluate_name_similarity(name1: Any, name2: Any) -> Tuple[bool, float, Optional[str]]:
    """
    Evaluate similarity between two name values.
    Returns (is_candidate, score, reason):
      - is_candidate: True if initials, token reorder, or high fuzzy similarity
      - score: 0.0 to 100.0
      - reason: 'exact_case_insensitive', 'token_reorder', 'initials_variation', 'fuzzy_similarity', or None
    """
    if name1 is None or name2 is None:
        return False, 0.0, None
    s1, s2 = str(name1).strip(), str(name2).strip()
    if not s1 or not s2:
        return False, 0.0, None
    if s1.lower() == s2.lower():
        return True, 100.0, "exact_case_insensitive"

    tokens1 = normalize_name_tokens(s1)
    tokens2 = normalize_name_tokens(s2)
    if not tokens1 or not tokens2:
        return False, 0.0, None

    # 1. Token reordering: e.g. "John Doe" vs "Doe, John"
    if sorted(tokens1) == sorted(tokens2):
        return True, 100.0, "token_reorder"

    # 2. Initials variation: e.g. "J. Doe" vs "John Doe", "Doe, J." vs "John Doe"
    if check_initials_match(sorted(tokens1), sorted(tokens2)):
        return True, 90.0, "initials_variation"

    # 3. RapidFuzz token sorting and set ratio
    clean1 = " ".join(tokens1)
    clean2 = " ".join(tokens2)
    sort_score = float(fuzz.token_sort_ratio(clean1, clean2))
    set_score = float(fuzz.token_set_ratio(clean1, clean2))
    score = max(sort_score, set_score)
    if score >= 80.0:
        return True, score, "fuzzy_similarity"

    return False, score, None


def is_status_column(col_name: str, status_rules: Optional[Dict[str, Any]] = None) -> bool:
    """Determine if a column represents a status or lifecycle state."""
    col_clean = col_name.strip().lower()
    if status_rules:
        target_col = status_rules.get("column") or status_rules.get("status_column")
        if target_col and str(target_col).strip().lower() == col_clean:
            return True
    return col_clean in STATUS_COLUMN_KEYWORDS or col_clean.endswith("_status")


def is_name_column(col_name: str, fuzzy_columns: Optional[List[str]] = None) -> bool:
    """Determine if a column represents a personal or entity name."""
    col_clean = col_name.strip().lower()
    if fuzzy_columns:
        if any(c.strip().lower() == col_clean for c in fuzzy_columns):
            return True
    return col_clean in NAME_COLUMN_KEYWORDS or col_clean.endswith("_name")


ID_COLUMN_KEYWORDS = {
    "id",
    "key",
    "uuid",
    "code",
    "identifier",
    "pk",
    "record_id",
    "student_id",
    "employee_id",
    "emp_id",
    "customer_id",
    "user_id",
    "client_id",
    "account_id",
    "account_number",
    "ssn",
    "national_id",
}


def is_id_column(col_name: str, key_columns: Optional[List[str]] = None) -> bool:
    """Determine if a column represents an identifier or primary key."""
    col_clean = col_name.strip().lower()
    if key_columns and any(k.strip().lower() == col_clean for k in key_columns):
        return True
    if col_clean in ID_COLUMN_KEYWORDS:
        return True
    return col_clean.endswith("_id") or col_clean.endswith("_key") or col_clean.endswith("_code")


def evaluate_status_rule(
    src_val: Any,
    tgt_val: Any,
    status_rules: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Evaluate whether src_status and tgt_status are compatible under status rules.
    Returns (is_permitted, reason_if_mismatch).
    If values are equal (case-insensitive, whitespace-trimmed), returns (True, None).
    If values differ:
      - If status_rules allows this pairing, returns (True, None).
      - Otherwise, returns (False, error_message).
    """
    s_clean = str(src_val).strip().lower() if src_val is not None else ""
    t_clean = str(tgt_val).strip().lower() if tgt_val is not None else ""

    if s_clean == t_clean:
        return True, None

    if not status_rules:
        return False, f"Status mismatch: source '{src_val}' vs target '{tgt_val}'"

    if status_rules.get("permit_suspended") is True:
        if t_clean in ("suspended", "dropped", "inactive") or s_clean in ("suspended", "dropped", "inactive"):
            return True, None

    allowed_pairs = (
        status_rules.get("allowed_pairs")
        or status_rules.get("equivalent_pairs")
        or status_rules.get("valid_pairs")
        or []
    )
    for pair in allowed_pairs:
        if len(pair) == 2:
            p0 = str(pair[0]).strip().lower()
            p1 = str(pair[1]).strip().lower()
            if (s_clean == p0 and t_clean == p1) or (s_clean == p1 and t_clean == p0):
                return True, None

    rules_dict = (
        status_rules.get("allowed_transitions")
        or status_rules.get("transitions")
        or status_rules.get("rules")
        or status_rules
    )
    if isinstance(rules_dict, dict):
        allowed = rules_dict.get(s_clean) or rules_dict.get(str(src_val))
        if allowed is not None:
            if isinstance(allowed, (list, tuple, set)):
                allowed_clean = [str(x).strip().lower() for x in allowed]
                if t_clean in allowed_clean:
                    return True, None
            elif str(allowed).strip().lower() == t_clean:
                return True, None

    return False, f"Status rule violation: '{src_val}' cannot transition or match to '{tgt_val}'"


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
    enable_fuzzy_matching: bool = False,
    fuzzy_match_columns: Optional[List[str]] = None,
    fuzzy_threshold: float = 80.0,
    status_rules: Optional[Dict[str, Any]] = None,
    source_file_id: Optional[str] = None,
    target_file_id: Optional[str] = None,
    excluded_source_rows: Optional[List[int]] = None,
    excluded_target_rows: Optional[List[int]] = None,
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

    # Filter out quarantined / excluded rows before matching
    if excluded_source_rows:
        ex_s = set(excluded_source_rows)
        source_records = [r for r in source_records if r[0] not in ex_s]
    if excluded_target_rows:
        ex_t = set(excluded_target_rows)
        target_records = [r for r in target_records if r[0] not in ex_t]

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
            needs_review_records=0,
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
    needs_review_records = 0
    unmatched_source_records = 0
    unmatched_target_records = 0
    duplicate_source_records = 0
    duplicate_target_records = 0
    duplicate_source_keys_count = 0
    duplicate_target_keys_count = 0
    conflicting_duplicate_records = 0

    # Collect single unmatched records for candidate evaluation if enabled
    single_unmatched_src: List[Tuple[Tuple[Any, ...], int, Dict[str, Any]]] = []
    single_unmatched_tgt: List[Tuple[Tuple[Any, ...], int, Dict[str, Any]]] = []

    for k_tuple in all_keys:
        s_list = source_key_groups.get(k_tuple, [])
        t_list = target_key_groups.get(k_tuple, [])
        k_dict = key_display_dicts[k_tuple]

        s_count = len(s_list)
        t_count = len(t_list)

        # Case 1: Unique 1-to-1 match on key
        if s_count == 1 and t_count == 1:
            s_row_num, s_rec = s_list[0]
            t_row_num, t_rec = t_list[0]

            lineage = {
                "source_row_index": s_row_num,
                "target_row_index": t_row_num,
                "source_file_id": source_file_id,
                "target_file_id": target_file_id,
                "key_columns": clean_key_columns,
                "key_values": k_dict,
            }

            diffs: List[FieldDifference] = []
            has_status_mismatch = False
            has_id_conflict = False
            fuzzy_name_scores: List[float] = []

            for s_col, t_col in field_pairs:
                s_val = s_rec.get(s_col)
                t_val = t_rec.get(t_col)

                # 1. State-aware verification for status columns
                if is_status_column(s_col, status_rules):
                    is_permitted, status_msg = evaluate_status_rule(s_val, t_val, status_rules)
                    if not is_permitted:
                        has_status_mismatch = True
                        diffs.append(
                            FieldDifference(
                                field_name=s_col,
                                source_field=s_col,
                                target_field=t_col,
                                source_value=s_val,
                                target_value=t_val,
                                source_type=type(s_val).__name__ if s_val is not None else "null",
                                target_type=type(t_val).__name__ if t_val is not None else "null",
                                difference_type="status_mismatch",
                                reason_code=ReasonCode.STATUS_MISMATCH,
                                message=status_msg or f"Status mismatch in '{s_col}': '{s_val}' vs '{t_val}'",
                            )
                        )
                        continue
                    elif str(s_val).strip().lower() != str(t_val).strip().lower():
                        # Status values differed but were explicitly permitted by rule!
                        continue

                # 2. Conflicting identifier check
                if is_id_column(s_col, clean_key_columns):
                    is_match, diff_type, s_type, t_type = compare_field_values(
                        src_val=s_val,
                        tgt_val=t_val,
                        null_set=null_set,
                        numeric_tolerance=0.0,
                        ignore_whitespace=ignore_whitespace,
                        ignore_case=ignore_case,
                    )
                    if not is_match:
                        has_id_conflict = True
                        diffs.append(
                            FieldDifference(
                                field_name=s_col,
                                source_field=s_col,
                                target_field=t_col,
                                source_value=s_val,
                                target_value=t_val,
                                source_type=s_type,
                                target_type=t_type,
                                difference_type="id_conflict",
                                reason_code=ReasonCode.ID_CONFLICT,
                                message=f"Conflicting identifier in '{s_col}': '{s_val}' vs '{t_val}'",
                            )
                        )
                        continue

                # 3. Name variation handling (initials, token reordering, RapidFuzz score)
                if is_name_column(s_col, fuzzy_match_columns):
                    s_str = str(s_val).strip() if s_val is not None else ""
                    t_str = str(t_val).strip() if t_val is not None else ""
                    if s_str != t_str:
                        is_cand, score, cand_reason = evaluate_name_similarity(s_val, t_val)
                        if is_cand and score >= (fuzzy_threshold if enable_fuzzy_matching else 80.0):
                            fuzzy_name_scores.append(score)
                            diffs.append(
                                FieldDifference(
                                    field_name=s_col,
                                    source_field=s_col,
                                    target_field=t_col,
                                    source_value=s_val,
                                    target_value=t_val,
                                    source_type="string",
                                    target_type="string",
                                    difference_type="fuzzy_name_review",
                                    reason_code=ReasonCode.FUZZY_NAME_REVIEW,
                                    confidence_score=round(score / 100.0, 4),
                                    message=(
                                        f"Name variation in '{s_col}' ({cand_reason}, similarity {score:.1f}%): "
                                        f"'{s_val}' vs '{t_val}'. Review required."
                                    ),
                                )
                            )
                            continue

                # 4. Standard comparison for remaining fields
                is_match, diff_type, s_type, t_type = compare_field_values(
                    src_val=s_val,
                    tgt_val=t_val,
                    null_set=null_set,
                    numeric_tolerance=numeric_tolerance,
                    ignore_whitespace=ignore_whitespace,
                    ignore_case=ignore_case,
                )
                if not is_match:
                    num_s, _ = parse_numeric(s_val)
                    num_t, _ = parse_numeric(t_val)
                    if num_s is not None and num_t is not None:
                        field_reason = ReasonCode.AMOUNT_TOLERANCE_EXCEEDED
                    else:
                        field_reason = ReasonCode.FIELD_MISMATCH

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
                            reason_code=field_reason,
                            message=f"Difference in '{s_col}': '{s_val}' vs '{t_val}'",
                        )
                    )

            if not diffs:
                identical_matches += 1
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.IDENTICAL,
                    discrepancy_category=DiscrepancyCategory.NONE,
                    reason_code=ReasonCode.EXACT_MATCH,
                    confidence_score=1.0,
                    source_row_number=s_row_num,
                    target_row_number=t_row_num,
                    source_row_index=s_row_num,
                    target_row_index=t_row_num,
                    source_row_numbers=[s_row_num],
                    target_row_numbers=[t_row_num],
                    source_file_id=source_file_id,
                    target_file_id=target_file_id,
                    lineage=lineage,
                    source_record=s_rec,
                    target_record=t_rec,
                    field_differences=[],
                    message="Records match identically.",
                )
                if include_identical:
                    results.append(item)
            elif has_status_mismatch:
                field_mismatches += 1
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.FIELD_MISMATCH,
                    discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
                    reason_code=ReasonCode.STATUS_MISMATCH,
                    confidence_score=0.0,
                    source_row_number=s_row_num,
                    target_row_number=t_row_num,
                    source_row_index=s_row_num,
                    target_row_index=t_row_num,
                    source_row_numbers=[s_row_num],
                    target_row_numbers=[t_row_num],
                    source_file_id=source_file_id,
                    target_file_id=target_file_id,
                    lineage=lineage,
                    source_record=s_rec,
                    target_record=t_rec,
                    field_differences=diffs,
                    message="Status mismatch detected: cannot pass as verified.",
                )
                results.append(item)
                discrepancies.append(item)
            elif has_id_conflict:
                needs_review_records += 1
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.NEEDS_REVIEW,
                    discrepancy_category=DiscrepancyCategory.NEEDS_REVIEW,
                    reason_code=ReasonCode.ID_CONFLICT,
                    confidence_score=0.0,
                    source_row_number=s_row_num,
                    target_row_number=t_row_num,
                    source_row_index=s_row_num,
                    target_row_index=t_row_num,
                    source_row_numbers=[s_row_num],
                    target_row_numbers=[t_row_num],
                    source_file_id=source_file_id,
                    target_file_id=target_file_id,
                    lineage=lineage,
                    source_record=s_rec,
                    target_record=t_rec,
                    field_differences=diffs,
                    message="Conflicting identifier detected; cannot auto-verify.",
                )
                results.append(item)
                discrepancies.append(item)
            elif fuzzy_name_scores and all(d.reason_code == ReasonCode.FUZZY_NAME_REVIEW for d in diffs):
                needs_review_records += 1
                avg_score = sum(fuzzy_name_scores) / len(fuzzy_name_scores)
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.NEEDS_REVIEW,
                    discrepancy_category=DiscrepancyCategory.NEEDS_REVIEW,
                    reason_code=ReasonCode.FUZZY_NAME_REVIEW,
                    confidence_score=round(avg_score / 100.0, 4),
                    source_row_number=s_row_num,
                    target_row_number=t_row_num,
                    source_row_index=s_row_num,
                    target_row_index=t_row_num,
                    source_row_numbers=[s_row_num],
                    target_row_numbers=[t_row_num],
                    source_file_id=source_file_id,
                    target_file_id=target_file_id,
                    lineage=lineage,
                    source_record=s_rec,
                    target_record=t_rec,
                    field_differences=diffs,
                    message=f"Name variation detected (score {avg_score:.1f}%): enters NEEDS_REVIEW.",
                )
                results.append(item)
                discrepancies.append(item)
            else:
                field_mismatches += 1
                has_amt = any(d.reason_code == ReasonCode.AMOUNT_TOLERANCE_EXCEEDED for d in diffs)
                rec_reason = ReasonCode.AMOUNT_TOLERANCE_EXCEEDED if has_amt else ReasonCode.FIELD_MISMATCH
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.FIELD_MISMATCH,
                    discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
                    reason_code=rec_reason,
                    confidence_score=0.0,
                    source_row_number=s_row_num,
                    target_row_number=t_row_num,
                    source_row_index=s_row_num,
                    target_row_index=t_row_num,
                    source_row_numbers=[s_row_num],
                    target_row_numbers=[t_row_num],
                    source_file_id=source_file_id,
                    target_file_id=target_file_id,
                    lineage=lineage,
                    source_record=s_rec,
                    target_record=t_rec,
                    field_differences=diffs,
                    message=f"{len(diffs)} field difference(s) detected.",
                )
                results.append(item)
                discrepancies.append(item)

        # Case 2: Only in source (defer to candidate search if fuzzy matching enabled)
        elif s_count == 1 and t_count == 0:
            single_unmatched_src.append((k_tuple, s_list[0][0], s_list[0][1]))

        # Case 3: Only in target (defer to candidate search if fuzzy matching enabled)
        elif s_count == 0 and t_count == 1:
            single_unmatched_tgt.append((k_tuple, t_list[0][0], t_list[0][1]))

        # Case 4: Duplicate in source, absent in target
        elif s_count > 1 and t_count == 0:
            s_row_nums = [r[0] for r in s_list]
            duplicate_source_records += s_count
            duplicate_source_keys_count += 1
            lineage = {
                "source_row_indexes": s_row_nums,
                "source_file_id": source_file_id,
                "key_columns": clean_key_columns,
                "key_values": k_dict,
            }
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.DUPLICATE_KEY_SOURCE,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                reason_code=ReasonCode.DUPLICATE_KEY_SOURCE,
                confidence_score=0.0,
                source_row_number=s_row_nums[0],
                target_row_number=None,
                source_row_index=s_row_nums[0],
                target_row_index=None,
                source_row_numbers=s_row_nums,
                target_row_numbers=[],
                source_file_id=source_file_id,
                target_file_id=target_file_id,
                lineage=lineage,
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
            lineage = {
                "target_row_indexes": t_row_nums,
                "target_file_id": target_file_id,
                "key_columns": clean_key_columns,
                "key_values": k_dict,
            }
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.DUPLICATE_KEY_TARGET,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                reason_code=ReasonCode.DUPLICATE_KEY_TARGET,
                confidence_score=0.0,
                source_row_number=None,
                target_row_number=t_row_nums[0],
                source_row_index=None,
                target_row_index=t_row_nums[0],
                source_row_numbers=[],
                target_row_numbers=t_row_nums,
                source_file_id=source_file_id,
                target_file_id=target_file_id,
                lineage=lineage,
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
            lineage = {
                "source_row_indexes": s_row_nums,
                "target_row_index": t_row_num,
                "source_file_id": source_file_id,
                "target_file_id": target_file_id,
                "key_columns": clean_key_columns,
                "key_values": k_dict,
            }
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.AMBIGUOUS_DUPLICATE,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                reason_code=ReasonCode.AMBIGUOUS_DUPLICATE,
                confidence_score=0.0,
                source_row_number=s_row_nums[0],
                target_row_number=t_row_num,
                source_row_index=s_row_nums[0],
                target_row_index=t_row_num,
                source_row_numbers=s_row_nums,
                target_row_numbers=[t_row_num],
                source_file_id=source_file_id,
                target_file_id=target_file_id,
                lineage=lineage,
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
            lineage = {
                "source_row_index": s_row_num,
                "target_row_indexes": t_row_nums,
                "source_file_id": source_file_id,
                "target_file_id": target_file_id,
                "key_columns": clean_key_columns,
                "key_values": k_dict,
            }
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.AMBIGUOUS_DUPLICATE,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                reason_code=ReasonCode.AMBIGUOUS_DUPLICATE,
                confidence_score=0.0,
                source_row_number=s_row_num,
                target_row_number=t_row_nums[0],
                source_row_index=s_row_num,
                target_row_index=t_row_nums[0],
                source_row_numbers=[s_row_num],
                target_row_numbers=t_row_nums,
                source_file_id=source_file_id,
                target_file_id=target_file_id,
                lineage=lineage,
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
            lineage = {
                "source_row_indexes": s_row_nums,
                "target_row_indexes": t_row_nums,
                "source_file_id": source_file_id,
                "target_file_id": target_file_id,
                "key_columns": clean_key_columns,
                "key_values": k_dict,
            }
            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.DUPLICATE_KEY_BOTH,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                reason_code=ReasonCode.DUPLICATE_KEY_BOTH,
                confidence_score=0.0,
                source_row_number=s_row_nums[0],
                target_row_number=t_row_nums[0],
                source_row_index=s_row_nums[0],
                target_row_index=t_row_nums[0],
                source_row_numbers=s_row_nums,
                target_row_numbers=t_row_nums,
                source_file_id=source_file_id,
                target_file_id=target_file_id,
                lineage=lineage,
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

    # 7. Evaluate unmatched records for candidate similarity & conflicting identifiers
    paired_src_indices: Set[int] = set()
    paired_tgt_indices: Set[int] = set()

    if enable_fuzzy_matching and single_unmatched_src and single_unmatched_tgt:
        all_cols = list(set(src_available_cols) | set(tgt_available_cols))
        name_cols = [c for c in all_cols if is_name_column(c, fuzzy_match_columns)]
        id_cols = [c for c in all_cols if is_id_column(c, clean_key_columns)]

        for s_idx, (s_k_tuple, s_row_num, s_rec) in enumerate(single_unmatched_src):
            best_candidate = None
            best_score = 0.0
            best_cand_reason = None
            best_t_idx = None
            best_t_k_tuple = None
            best_t_row_num = None
            best_t_rec = None

            for t_idx, (t_k_tuple, t_row_num, t_rec) in enumerate(single_unmatched_tgt):
                if t_idx in paired_tgt_indices:
                    continue

                for col in name_cols:
                    s_name = s_rec.get(col)
                    t_col_name = column_mapping.get(col, col)
                    t_name = t_rec.get(t_col_name)
                    if s_name is None or t_name is None:
                        continue
                    is_cand, score, cand_reason = evaluate_name_similarity(s_name, t_name)
                    if is_cand and score >= fuzzy_threshold and score > best_score:
                        best_score = score
                        best_cand_reason = cand_reason
                        best_candidate = col
                        best_t_idx = t_idx
                        best_t_k_tuple = t_k_tuple
                        best_t_row_num = t_row_num
                        best_t_rec = t_rec

            if best_candidate and best_t_idx is not None and best_t_rec is not None:
                # Check for conflicting identifiers
                has_conflicting_id = False
                conflicting_id_details = []
                for id_c in id_cols:
                    s_id_val = s_rec.get(id_c)
                    t_id_c = column_mapping.get(id_c, id_c)
                    t_id_val = best_t_rec.get(t_id_c)
                    if s_id_val is not None and t_id_val is not None:
                        if str(s_id_val).strip() != str(t_id_val).strip():
                            has_conflicting_id = True
                            conflicting_id_details.append(f"{id_c}: '{s_id_val}' vs '{t_id_val}'")

                # Also check key columns themselves
                s_disp = key_display_dicts[s_k_tuple]
                t_disp = key_display_dicts[best_t_k_tuple]
                if s_disp != t_disp:
                    has_conflicting_id = True
                    conflicting_id_details.append(f"keys: {s_disp} vs {t_disp}")

                diffs_cand: List[FieldDifference] = []
                if has_conflicting_id:
                    diffs_cand.append(
                        FieldDifference(
                            field_name="primary_identifier",
                            source_field=clean_key_columns[0] if clean_key_columns else "id",
                            target_field=column_mapping.get(clean_key_columns[0], clean_key_columns[0]) if clean_key_columns else "id",
                            source_value=s_rec.get(clean_key_columns[0]) if clean_key_columns else None,
                            target_value=best_t_rec.get(column_mapping.get(clean_key_columns[0], clean_key_columns[0])) if clean_key_columns else None,
                            difference_type="id_conflict",
                            reason_code=ReasonCode.ID_CONFLICT,
                            message=f"Conflicting identifier: {'; '.join(conflicting_id_details)}",
                        )
                    )
                t_cand_col = column_mapping.get(best_candidate, best_candidate)
                diffs_cand.append(
                    FieldDifference(
                        field_name=best_candidate,
                        source_field=best_candidate,
                        target_field=t_cand_col,
                        source_value=s_rec.get(best_candidate),
                        target_value=best_t_rec.get(t_cand_col),
                        difference_type="fuzzy_name_review",
                        reason_code=ReasonCode.FUZZY_NAME_REVIEW,
                        confidence_score=round(best_score / 100.0, 4),
                        message=f"Name similarity ({best_cand_reason}, score {best_score:.1f}%)",
                    )
                )

                lineage = {
                    "source_row_index": s_row_num,
                    "target_row_index": best_t_row_num,
                    "source_file_id": source_file_id,
                    "target_file_id": target_file_id,
                    "key_columns": clean_key_columns,
                    "source_key_values": s_disp,
                    "target_key_values": t_disp,
                }

                cand_reason_code = ReasonCode.ID_CONFLICT if has_conflicting_id else ReasonCode.FUZZY_NAME_REVIEW
                cand_msg = (
                    f"Fuzzy candidate ({best_cand_reason}, {best_score:.1f}%) with conflicting ID "
                    f"({'; '.join(conflicting_id_details)}): not auto-matched, enters NEEDS_REVIEW."
                    if has_conflicting_id
                    else f"Fuzzy name candidate ({best_cand_reason}, {best_score:.1f}%): enters NEEDS_REVIEW."
                )

                needs_review_records += 1
                cand_item = VerificationResultItem(
                    key_values=s_disp,
                    match_status=MatchStatus.NEEDS_REVIEW,
                    discrepancy_category=DiscrepancyCategory.NEEDS_REVIEW,
                    reason_code=cand_reason_code,
                    confidence_score=round(best_score / 100.0, 4),
                    source_row_number=s_row_num,
                    target_row_number=best_t_row_num,
                    source_row_index=s_row_num,
                    target_row_index=best_t_row_num,
                    source_row_numbers=[s_row_num],
                    target_row_numbers=[best_t_row_num],
                    source_file_id=source_file_id,
                    target_file_id=target_file_id,
                    lineage=lineage,
                    source_record=s_rec,
                    target_record=best_t_rec,
                    field_differences=diffs_cand,
                    message=cand_msg,
                )
                results.append(cand_item)
                discrepancies.append(cand_item)

                paired_src_indices.add(s_idx)
                paired_tgt_indices.add(best_t_idx)

    # 8. Emit remaining unpaired unmatched source records
    for s_idx, (s_k_tuple, s_row_num, s_rec) in enumerate(single_unmatched_src):
        if s_idx in paired_src_indices:
            continue
        unmatched_source_records += 1
        k_dict = key_display_dicts[s_k_tuple]
        lineage = {
            "source_row_index": s_row_num,
            "source_file_id": source_file_id,
            "key_columns": clean_key_columns,
            "key_values": k_dict,
        }
        item = VerificationResultItem(
            key_values=k_dict,
            match_status=MatchStatus.MISSING_IN_TARGET,
            discrepancy_category=DiscrepancyCategory.MISSING_RECORD,
            reason_code=ReasonCode.MISSING_IN_TARGET,
            confidence_score=0.0,
            source_row_number=s_row_num,
            target_row_number=None,
            source_row_index=s_row_num,
            target_row_index=None,
            source_row_numbers=[s_row_num],
            target_row_numbers=[],
            source_file_id=source_file_id,
            target_file_id=target_file_id,
            lineage=lineage,
            source_record=s_rec,
            target_record=None,
            field_differences=[],
            message="Record present in source dataset but missing in target dataset.",
        )
        results.append(item)
        discrepancies.append(item)

    # 9. Emit remaining unpaired unmatched target records
    for t_idx, (t_k_tuple, t_row_num, t_rec) in enumerate(single_unmatched_tgt):
        if t_idx in paired_tgt_indices:
            continue
        unmatched_target_records += 1
        k_dict = key_display_dicts[t_k_tuple]
        lineage = {
            "target_row_index": t_row_num,
            "target_file_id": target_file_id,
            "key_columns": clean_key_columns,
            "key_values": k_dict,
        }
        item = VerificationResultItem(
            key_values=k_dict,
            match_status=MatchStatus.MISSING_IN_SOURCE,
            discrepancy_category=DiscrepancyCategory.MISSING_RECORD,
            reason_code=ReasonCode.MISSING_IN_SOURCE,
            confidence_score=0.0,
            source_row_number=None,
            target_row_number=t_row_num,
            source_row_index=None,
            target_row_index=t_row_num,
            source_row_numbers=[],
            target_row_numbers=[t_row_num],
            source_file_id=source_file_id,
            target_file_id=target_file_id,
            lineage=lineage,
            source_record=None,
            target_record=t_rec,
            field_differences=[],
            message="Record present in target dataset but missing in source dataset.",
        )
        results.append(item)
        discrepancies.append(item)

    total_discrepancies = len(discrepancies)
    status_str = "completed_with_warnings" if warnings else "completed"

    summary = VerificationSummary(
        total_source_records=len(source_records),
        total_target_records=len(target_records),
        matched_records=identical_matches + field_mismatches + needs_review_records,
        identical_matches=identical_matches,
        field_mismatches=field_mismatches,
        records_with_differences=field_mismatches,
        needs_review_records=needs_review_records,
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

    from app.services.materiality_engine import compute_record_materiality, compute_summary_materiality
    for r in results:
        compute_record_materiality(r, column_mapping=column_mapping)
    summary = compute_summary_materiality(results, discrepancies, summary)

    return summary, results, discrepancies, warnings, errors


def verify_project_files(
    db: Session,
    project_id: uuid.UUID,
    request: VerificationRequest,
    current_user: Optional[User] = None,
) -> VerificationResponse:
    """
    Execute full verification between two uploaded source files belonging to a project.
    Validates project authorization, source file isolation, parses and normalizes
    datasets, and runs core comparison engine.
    """
    # 1. Project existence & authorization check
    project = get_project_by_id(db, project_id, current_user=current_user)
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

    from app.services.profiling_service import get_excluded_row_indices_for_file
    ex_src = request.excluded_source_rows or get_excluded_row_indices_for_file(src_path)
    ex_tgt = request.excluded_target_rows or get_excluded_row_indices_for_file(tgt_path)

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
        enable_fuzzy_matching=request.enable_fuzzy_matching,
        fuzzy_match_columns=request.fuzzy_match_columns,
        fuzzy_threshold=request.fuzzy_threshold,
        status_rules=request.status_rules,
        source_file_id=str(source_file.id),
        target_file_id=str(target_file.id),
        excluded_source_rows=ex_src,
        excluded_target_rows=ex_tgt,
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
    current_user: Optional[User] = None,
) -> VerificationRun:
    """
    Create a persistent VerificationRun record, execute reconciliation,
    store summary metrics and individual discrepancy items in a safe transaction.
    """
    # 1. Project existence & authorization check
    project = get_project_by_id(db, project_id, current_user=current_user)
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
        "enable_fuzzy_matching": request.enable_fuzzy_matching,
        "fuzzy_match_columns": request.fuzzy_match_columns,
        "fuzzy_threshold": request.fuzzy_threshold,
        "status_rules": request.status_rules,
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

            from app.services.profiling_service import get_excluded_row_indices_for_file
            ex_src = request.excluded_source_rows or get_excluded_row_indices_for_file(src_path)
            ex_tgt = request.excluded_target_rows or get_excluded_row_indices_for_file(tgt_path)

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
                enable_fuzzy_matching=request.enable_fuzzy_matching,
                fuzzy_match_columns=request.fuzzy_match_columns,
                fuzzy_threshold=request.fuzzy_threshold,
                status_rules=request.status_rules,
                source_file_id=str(source_file.id),
                target_file_id=str(target_file.id),
                excluded_source_rows=ex_src,
                excluded_target_rows=ex_tgt,
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
                    child_records=item.child_records,
                    aggregated_amount=item.aggregated_amount,
                    expected_amount=item.expected_amount,
                    source_amount=item.source_amount,
                    target_amount=item.target_amount,
                    variance_amount=item.variance_amount,
                    exposure_amount=item.exposure_amount,
                    currency=item.currency or "USD",
                    severity=item.severity or "medium",
                    resolution_status=item.resolution_status or "unresolved",
                    side_by_side=item.side_by_side,
                    _reason_code=item.reason_code.value if hasattr(item.reason_code, "value") else (str(item.reason_code) if item.reason_code else None),
                    _confidence_score=item.confidence_score,
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
    current_user: Optional[User] = None,
) -> VerificationRun:
    """Retrieve a verification run with project authorization check."""
    project = get_project_by_id(db, project_id, current_user=current_user)
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
    current_user: Optional[User] = None,
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = None,
) -> Tuple[int, List[VerificationRun]]:
    """List verification runs for a project with pagination and status filtering."""
    project = get_project_by_id(db, project_id, current_user=current_user)
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
    current_user: Optional[User] = None,
    skip: int = 0,
    limit: int = 50,
    discrepancy_category: Optional[str] = None,
    match_status: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    reason_code: Optional[str] = None,
    source_alias: Optional[str] = None,
    rule_failure_type: Optional[str] = None,
    resolution_status: Optional[str] = None,
    sort_by: str = "source_row_number",
    sort_order: str = "asc",
) -> Tuple[int, List[VerificationDiscrepancy]]:
    """Paginate, filter, and sort discrepancy results for an authorized verification run."""
    # Enforce project ownership
    get_verification_run(db, project_id, run_id, current_user=current_user)

    valid_sort_fields = {
        "source_row_number": VerificationDiscrepancy.source_row_number,
        "target_row_number": VerificationDiscrepancy.target_row_number,
        "source_row_index": VerificationDiscrepancy.source_row_number,
        "target_row_index": VerificationDiscrepancy.target_row_number,
        "created_at": VerificationDiscrepancy.created_at,
        "match_status": VerificationDiscrepancy.match_status,
        "discrepancy_category": VerificationDiscrepancy.discrepancy_category,
        "exposure_amount": VerificationDiscrepancy.exposure_amount,
        "exposure": VerificationDiscrepancy.exposure_amount,
        "variance_amount": VerificationDiscrepancy.variance_amount,
        "variance": VerificationDiscrepancy.variance_amount,
        "source_amount": VerificationDiscrepancy.source_amount,
        "target_amount": VerificationDiscrepancy.target_amount,
        "confidence_score": VerificationDiscrepancy._confidence_score,
        "severity": VerificationDiscrepancy.severity,
        "resolution_status": VerificationDiscrepancy.resolution_status,
        "reason_code": VerificationDiscrepancy._reason_code,
    }
    clean_sort_by = sort_by.strip()
    if clean_sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid sort_by field '{sort_by}'. Valid fields are: {list(valid_sort_fields.keys())}",
        )

    clean_sort_order = sort_order.strip().lower()
    if clean_sort_order not in ["asc", "desc"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid sort_order '{sort_order}'. Valid orders are 'asc' and 'desc'.",
        )

    query = db.query(VerificationDiscrepancy).filter(VerificationDiscrepancy.run_id == run_id)
    if discrepancy_category:
        query = query.filter(VerificationDiscrepancy.discrepancy_category == discrepancy_category)
    if match_status:
        query = query.filter(VerificationDiscrepancy.match_status == match_status)
    if min_amount is not None:
        query = query.filter(func.coalesce(VerificationDiscrepancy.exposure_amount, 0.0) >= min_amount)
    if max_amount is not None:
        query = query.filter(func.coalesce(VerificationDiscrepancy.exposure_amount, 0.0) <= max_amount)
    if reason_code:
        query = query.filter(VerificationDiscrepancy._reason_code == reason_code)
    if resolution_status:
        query = query.filter(VerificationDiscrepancy.resolution_status == resolution_status)
    if rule_failure_type:
        query = query.filter(
            or_(
                VerificationDiscrepancy.discrepancy_category == rule_failure_type,
                VerificationDiscrepancy._reason_code == rule_failure_type,
            )
        )
    if source_alias:
        query = query.filter(
            or_(
                cast(VerificationDiscrepancy.source_row_indices, String).like(f'%"{source_alias}"%'),
                cast(VerificationDiscrepancy.source_records, String).like(f'%"{source_alias}"%'),
            )
        )

    total = query.count()

    col = valid_sort_fields[clean_sort_by]
    order_clause = col.desc().nulls_last() if clean_sort_order == "desc" else col.asc().nulls_last()

    items = (
        query.order_by(order_clause, VerificationDiscrepancy.created_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, items


def get_discrepancy_inspection(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    discrepancy_id: uuid.UUID,
    current_user: Optional[User] = None,
) -> SideBySideInspectionResponse:
    """Retrieve detailed side-by-side inspection and normalization diffs for a specific discrepancy."""
    get_verification_run(db, project_id, run_id, current_user=current_user)

    disc = db.query(VerificationDiscrepancy).filter(
        VerificationDiscrepancy.id == discrepancy_id,
        VerificationDiscrepancy.run_id == run_id,
    ).first()
    if disc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discrepancy record not found.",
        )

    side_by_side = disc.side_by_side
    if not side_by_side:
        from app.services.materiality_engine import build_side_by_side_payload
        side_by_side = build_side_by_side_payload(disc)

    field_comparisons = [
        FieldComparisonDiff(**c) for c in (side_by_side.get("field_comparisons") or [])
    ]

    return SideBySideInspectionResponse(
        id=str(disc.id),
        run_id=disc.run_id,
        key_values=disc.key_values,
        match_status=disc.match_status,
        discrepancy_category=disc.discrepancy_category,
        reason_code=disc.reason_code,
        confidence_score=disc.confidence_score,
        severity=disc.severity or "medium",
        source_amount=disc.source_amount,
        target_amount=disc.target_amount,
        variance_amount=disc.variance_amount,
        exposure_amount=disc.exposure_amount,
        currency=disc.currency or "USD",
        source_row_index=disc.source_row_number,
        target_row_index=disc.target_row_number,
        source_row_indices=disc.source_row_indices,
        raw_source_record=side_by_side.get("raw_source_record") or disc.source_record,
        normalized_source_record=side_by_side.get("normalized_source_record"),
        raw_target_record=side_by_side.get("raw_target_record") or disc.target_record,
        normalized_target_record=side_by_side.get("normalized_target_record"),
        field_comparisons=field_comparisons,
        failed_rules=side_by_side.get("failed_rules") or [],
        child_records=disc.child_records,
        message=disc.message,
        resolution_status=disc.resolution_status or "unresolved",
    )


def get_verification_run_summary(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: Optional[User] = None,
) -> Dict[str, Any]:
    """Retrieve only the summary metrics for an authorized verification run."""
    run = get_verification_run(db, project_id, run_id, current_user=current_user)
    return run.summary or {}


def verify_multisource_datasets(
    sources: List[SourceDefinition],
    sources_records: Dict[str, List[Tuple[int, Dict[str, Any]]]],
    unified_keys: List[str],
    compare_attributes: Optional[List[str]] = None,
    ignore_attributes: Optional[List[str]] = None,
    numeric_tolerance: float = 0.0,
    ignore_whitespace: bool = True,
    ignore_case: bool = False,
    null_values: Optional[List[str]] = None,
    include_identical: bool = True,
    status_rules: Optional[Dict[str, Any]] = None,
    rule_config: Optional[Any] = None,
) -> Tuple[
    VerificationSummary,
    List[VerificationResultItem],
    List[VerificationResultItem],
    Dict[str, int],
    Dict[str, int],
]:
    """
    Multi-source reconciliation engine supporting 2, 3, or more datasets.
    Aligns records across sources using primary and composite keys, tracks complete
    source-row index lineage, and categorizes multi-source matches and discrepancies.
    """
    null_set = (
        {v.strip().lower() for v in null_values if v is not None}
        if null_values
        else {"none", "null", "nil", "nan", "n/a", "na", "#n/a", ""}
    )

    primary_source = next((s for s in sources if s.is_primary), sources[0])
    primary_alias = primary_source.alias

    # Apply quarantine exclusions per source
    filtered_records: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
    for s in sources:
        ex_rows = set(s.excluded_row_indices or [])
        filtered_records[s.alias] = [
            (r_num, rec) for r_num, rec in sources_records[s.alias] if r_num not in ex_rows
        ]

    # Check for Split-Payment Aggregation Mode
    from app.schemas.rule import VersionedRuleConfig
    v_rules: Optional[VersionedRuleConfig] = None
    if rule_config:
        if isinstance(rule_config, VersionedRuleConfig):
            v_rules = rule_config
        elif isinstance(rule_config, dict):
            try:
                v_rules = VersionedRuleConfig.model_validate(rule_config)
            except Exception:
                pass

    if v_rules and v_rules.aggregation_config and v_rules.aggregation_config.enabled:
        from app.services.aggregation_engine import reconcile_split_payments
        ac = v_rules.aggregation_config
        p_recs = filtered_records.get(ac.parent_source_alias, [])
        c_recs = filtered_records.get(ac.child_source_alias, [])
        agg_summary, agg_results, agg_discrepancies = reconcile_split_payments(
            parent_records=p_recs,
            child_records=c_recs,
            config=ac,
            date_window_rules=v_rules.date_window_rules,
            include_identical=include_identical,
        )
        records_by_src = {s.alias: len(filtered_records.get(s.alias, [])) for s in sources}
        missing_by_src = {
            ac.parent_source_alias: agg_summary.unmatched_source_records,
            ac.child_source_alias: agg_summary.unmatched_target_records,
        }
        return agg_summary, agg_results, agg_discrepancies, records_by_src, missing_by_src

    # Index records by normalized key tuple per source
    source_key_groups: Dict[str, Dict[Tuple[Any, ...], List[Tuple[int, Dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    key_display_dicts: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

    for s in sources:
        alias = s.alias
        key_cols = s.key_columns
        for r_num, rec in filtered_records[alias]:
            k_tuple_vals = []
            k_disp = {}
            for idx, uk in enumerate(unified_keys):
                col_name = None
                if uk in s.field_mapping:
                    col_name = s.field_mapping[uk]
                elif s.field_mapping:
                    for src_c, uni_a in s.field_mapping.items():
                        if uni_a == uk:
                            col_name = src_c
                            break
                if not col_name:
                    if idx < len(key_cols):
                        col_name = key_cols[idx]
                    elif uk in rec:
                        col_name = uk
                    else:
                        col_name = key_cols[0]

                val = rec.get(col_name)
                k_disp[uk] = val
                k_norm = normalize_key_value(val, null_set, ignore_whitespace, ignore_case)
                k_tuple_vals.append(k_norm)

            k_tuple = tuple(k_tuple_vals)
            source_key_groups[alias][k_tuple].append((r_num, rec))
            if k_tuple not in key_display_dicts:
                key_display_dicts[k_tuple] = k_disp

    all_keys = list(set().union(*(source_key_groups[s.alias].keys() for s in sources)))
    all_keys.sort(key=lambda x: str(x))

    # Resolve attributes to compare
    if compare_attributes is None:
        ignore_set = set(ignore_attributes or []) | set(unified_keys)
        all_attrs = set()
        for s in sources:
            for src_c, uni_a in s.field_mapping.items():
                if uni_a not in ignore_set:
                    all_attrs.add(uni_a)
        if not all_attrs and filtered_records[primary_alias]:
            prim_cols = set(filtered_records[primary_alias][0][1].keys())
            for s in sources[1:]:
                if filtered_records[s.alias]:
                    prim_cols &= set(filtered_records[s.alias][0][1].keys())
            all_attrs = prim_cols - ignore_set
        compare_attrs = sorted(list(all_attrs))
    else:
        compare_attrs = [
            a
            for a in compare_attributes
            if a not in (ignore_attributes or []) and a not in unified_keys
        ]

    results: List[VerificationResultItem] = []
    discrepancies: List[VerificationResultItem] = []

    identical_matches = 0
    field_mismatches = 0
    needs_review_records = 0
    unmatched_source_records = 0
    unmatched_target_records = 0
    duplicate_source_records = 0
    duplicate_target_records = 0
    duplicate_source_keys_count = 0
    duplicate_target_keys_count = 0
    matched_records = 0

    for k_tuple in all_keys:
        presence = {s.alias: (len(source_key_groups[s.alias].get(k_tuple, [])) > 0) for s in sources}
        dupe_counts = {s.alias: len(source_key_groups[s.alias].get(k_tuple, [])) for s in sources}
        row_indices = {
            s.alias: (source_key_groups[s.alias][k_tuple][0][0] if presence[s.alias] else None)
            for s in sources
        }
        source_recs_map = {
            s.alias: (source_key_groups[s.alias][k_tuple][0][1] if presence[s.alias] else None)
            for s in sources
        }
        k_dict = key_display_dicts[k_tuple]

        has_dupes = any(c > 1 for c in dupe_counts.values())

        if has_dupes:
            if dupe_counts.get(primary_alias, 0) > 1:
                duplicate_source_keys_count += 1
                duplicate_source_records += dupe_counts[primary_alias]
            sec_dupes = sum(c for alias, c in dupe_counts.items() if alias != primary_alias and c > 1)
            if sec_dupes > 0:
                duplicate_target_keys_count += 1
                duplicate_target_records += sec_dupes

            item = VerificationResultItem(
                key_values=k_dict,
                match_status=MatchStatus.DUPLICATE_KEY_SOURCE,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                reason_code=ReasonCode.DUPLICATE_KEY_SOURCE,
                source_row_indices=row_indices,
                source_records=source_recs_map,
                missing_in_sources=[s.alias for s in sources if not presence[s.alias]],
                source_presence=presence,
                source_row_number=row_indices.get(primary_alias),
                target_row_number=next(
                    (idx for a, idx in row_indices.items() if a != primary_alias and idx is not None),
                    None,
                ),
                source_record=source_recs_map.get(primary_alias),
                target_record=next(
                    (rec for a, rec in source_recs_map.items() if a != primary_alias and rec is not None),
                    None,
                ),
                message=f"Duplicate key across rows in source(s): {[s for s, c in dupe_counts.items() if c > 1]}",
            )
            results.append(item)
            discrepancies.append(item)
            continue

        if all(presence.values()):
            matched_records += 1
            diffs: List[FieldDifference] = []
            has_status_mismatch = False
            prim_rec = source_recs_map[primary_alias]

            for attr in compare_attrs:
                prim_col = primary_source.field_mapping.get(attr, attr)
                val_prim = prim_rec.get(prim_col)

                for sec_s in sources:
                    if sec_s.alias == primary_alias:
                        continue
                    sec_rec = source_recs_map[sec_s.alias]
                    sec_col = sec_s.field_mapping.get(attr, attr)
                    val_sec = sec_rec.get(sec_col)

                    if is_status_column(attr, status_rules):
                        is_perm, stat_msg = evaluate_status_rule(val_prim, val_sec, status_rules)
                        if not is_perm:
                            has_status_mismatch = True
                            diffs.append(
                                FieldDifference(
                                    field_name=attr,
                                    source_field=f"{primary_alias}.{prim_col}",
                                    target_field=f"{sec_s.alias}.{sec_col}",
                                    source_value=val_prim,
                                    target_value=val_sec,
                                    difference_type="status_mismatch",
                                    reason_code=ReasonCode.STATUS_MISMATCH,
                                    message=stat_msg or f"Status mismatch in '{attr}': '{val_prim}' vs '{val_sec}'",
                                )
                            )
                            continue
                        elif str(val_prim).strip().lower() != str(val_sec).strip().lower():
                            continue

                    is_match, diff_type, s_t, t_t = compare_field_values(
                        src_val=val_prim,
                        tgt_val=val_sec,
                        null_set=null_set,
                        numeric_tolerance=numeric_tolerance,
                        ignore_whitespace=ignore_whitespace,
                        ignore_case=ignore_case,
                    )
                    if not is_match:
                        diffs.append(
                            FieldDifference(
                                field_name=attr,
                                source_field=f"{primary_alias}.{prim_col}",
                                target_field=f"{sec_s.alias}.{sec_col}",
                                source_value=val_prim,
                                target_value=val_sec,
                                source_type=s_t,
                                target_type=t_t,
                                difference_type=diff_type,
                                reason_code=ReasonCode.FIELD_MISMATCH,
                                message=f"Value in '{sec_s.alias}' differs from primary '{primary_alias}'",
                            )
                        )

            # Evaluate Date Window Rules if configured
            if v_rules and v_rules.date_window_rules and prim_rec:
                from app.services.rule_engine import evaluate_date_window
                for dw in v_rules.date_window_rules:
                    s_val = prim_rec.get(dw.source_date_field)
                    for sec_s in sources[1:]:
                        if presence[sec_s.alias]:
                            t_rec = source_recs_map[sec_s.alias]
                            t_val = t_rec.get(dw.target_date_field)
                            if s_val is not None and t_val is not None:
                                passed, d_msg = evaluate_date_window(s_val, t_val, dw)
                                if not passed:
                                    diffs.append(
                                        FieldDifference(
                                            field_name=dw.source_date_field,
                                            source_field=f"{primary_alias}.{dw.source_date_field}",
                                            target_field=f"{sec_s.alias}.{dw.target_date_field}",
                                            source_value=s_val,
                                            target_value=t_val,
                                            difference_type="date_window_exceeded",
                                            reason_code=ReasonCode.DATE_WINDOW_EXCEEDED,
                                            message=d_msg,
                                        )
                                    )

            # Evaluate Status Transition Rules if configured
            if v_rules and v_rules.status_transition_rules and prim_rec:
                from app.services.rule_engine import evaluate_status_transition
                for st in v_rules.status_transition_rules:
                    s_val = prim_rec.get(st.source_field)
                    for sec_s in sources[1:]:
                        if presence[sec_s.alias]:
                            t_rec = source_recs_map[sec_s.alias]
                            t_val = t_rec.get(st.target_field)
                            if s_val is not None and t_val is not None:
                                passed, s_msg = evaluate_status_transition(s_val, t_val, st)
                                if not passed:
                                    diffs.append(
                                        FieldDifference(
                                            field_name=st.source_field,
                                            source_field=f"{primary_alias}.{st.source_field}",
                                            target_field=f"{sec_s.alias}.{st.target_field}",
                                            source_value=s_val,
                                            target_value=t_val,
                                            difference_type="status_transition_violation",
                                            reason_code=ReasonCode.STATUS_TRANSITION_VIOLATION,
                                            message=s_msg,
                                        )
                                    )

            if not diffs:
                identical_matches += 1
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.IDENTICAL,
                    discrepancy_category=DiscrepancyCategory.NONE,
                    reason_code=ReasonCode.EXACT_MATCH,
                    confidence_score=1.0,
                    source_row_indices=row_indices,
                    source_records=source_recs_map,
                    missing_in_sources=[],
                    source_presence=presence,
                    source_row_number=row_indices.get(primary_alias),
                    target_row_number=next(
                        (idx for a, idx in row_indices.items() if a != primary_alias and idx is not None),
                        None,
                    ),
                    source_record=source_recs_map.get(primary_alias),
                    target_record=next(
                        (rec for a, rec in source_recs_map.items() if a != primary_alias and rec is not None),
                        None,
                    ),
                    field_differences=[],
                    message="Records match identically across all sources.",
                )
                if include_identical:
                    results.append(item)
            elif has_status_mismatch:
                field_mismatches += 1
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.FIELD_MISMATCH,
                    discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
                    reason_code=ReasonCode.STATUS_MISMATCH,
                    confidence_score=0.0,
                    source_row_indices=row_indices,
                    source_records=source_recs_map,
                    missing_in_sources=[],
                    source_presence=presence,
                    source_row_number=row_indices.get(primary_alias),
                    target_row_number=next(
                        (idx for a, idx in row_indices.items() if a != primary_alias and idx is not None),
                        None,
                    ),
                    source_record=source_recs_map.get(primary_alias),
                    target_record=next(
                        (rec for a, rec in source_recs_map.items() if a != primary_alias and rec is not None),
                        None,
                    ),
                    field_differences=diffs,
                    message="Status mismatch detected across sources.",
                )
                results.append(item)
                discrepancies.append(item)
            else:
                field_mismatches += 1
                # Check for explicit date window or status transition rule violation
                has_dw = any(d.reason_code == ReasonCode.DATE_WINDOW_EXCEEDED for d in diffs)
                has_st = any(d.reason_code == ReasonCode.STATUS_TRANSITION_VIOLATION for d in diffs)
                item_cat = DiscrepancyCategory.RULE_VIOLATION if (has_dw or has_st) else DiscrepancyCategory.FIELD_MISMATCH
                item_reason = (
                    ReasonCode.DATE_WINDOW_EXCEEDED if has_dw
                    else ReasonCode.STATUS_TRANSITION_VIOLATION if has_st
                    else ReasonCode.FIELD_MISMATCH
                )
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.FIELD_MISMATCH,
                    discrepancy_category=item_cat,
                    reason_code=item_reason,
                    confidence_score=0.0,
                    source_row_indices=row_indices,
                    source_records=source_recs_map,
                    missing_in_sources=[],
                    source_presence=presence,
                    source_row_number=row_indices.get(primary_alias),
                    target_row_number=next(
                        (idx for a, idx in row_indices.items() if a != primary_alias and idx is not None),
                        None,
                    ),
                    source_record=source_recs_map.get(primary_alias),
                    target_record=next(
                        (rec for a, rec in source_recs_map.items() if a != primary_alias and rec is not None),
                        None,
                    ),
                    field_differences=diffs,
                    message=f"{len(diffs)} field difference(s) detected across sources.",
                )
                results.append(item)
                discrepancies.append(item)
        else:
            missing_aliases = [s.alias for s in sources if not presence[s.alias]]
            if presence[primary_alias]:
                unmatched_target_records += 1
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.MISSING_IN_TARGET,
                    discrepancy_category=DiscrepancyCategory.MISSING_RECORD,
                    reason_code=ReasonCode.MISSING_IN_TARGET,
                    source_row_indices=row_indices,
                    source_records=source_recs_map,
                    missing_in_sources=missing_aliases,
                    source_presence=presence,
                    source_row_number=row_indices.get(primary_alias),
                    target_row_number=None,
                    source_record=source_recs_map.get(primary_alias),
                    target_record=None,
                    message=f"Record present in primary '{primary_alias}' but missing in: {', '.join(missing_aliases)}",
                )
            else:
                unmatched_source_records += 1
                present_aliases = [s.alias for s in sources if presence[s.alias]]
                item = VerificationResultItem(
                    key_values=k_dict,
                    match_status=MatchStatus.MISSING_IN_SOURCE,
                    discrepancy_category=DiscrepancyCategory.MISSING_RECORD,
                    reason_code=ReasonCode.MISSING_IN_SOURCE,
                    source_row_indices=row_indices,
                    source_records=source_recs_map,
                    missing_in_sources=[primary_alias],
                    source_presence=presence,
                    source_row_number=None,
                    target_row_number=next(
                        (idx for a, idx in row_indices.items() if a in present_aliases and idx is not None),
                        None,
                    ),
                    source_record=None,
                    target_record=next(
                        (rec for a, rec in source_recs_map.items() if a in present_aliases and rec is not None),
                        None,
                    ),
                    message=f"Record missing in primary '{primary_alias}'; present in: {', '.join(present_aliases)}",
                )
            results.append(item)
            discrepancies.append(item)

    records_by_source = {s.alias: len(filtered_records[s.alias]) for s in sources}
    missing_by_source = {
        s.alias: sum(1 for item in results if s.alias in (item.missing_in_sources or []))
        for s in sources
    }

    summary = VerificationSummary(
        total_source_records=len(filtered_records[primary_alias]),
        total_target_records=sum(
            len(filtered_records[s.alias]) for s in sources if s.alias != primary_alias
        ),
        matched_records=matched_records,
        identical_matches=identical_matches,
        field_mismatches=field_mismatches,
        records_with_differences=field_mismatches,
        needs_review_records=needs_review_records,
        unmatched_source_records=unmatched_source_records,
        unmatched_target_records=unmatched_target_records,
        duplicate_source_records=duplicate_source_records,
        duplicate_target_records=duplicate_target_records,
        duplicate_source_keys_count=duplicate_source_keys_count,
        duplicate_target_keys_count=duplicate_target_keys_count,
        conflicting_duplicate_records=0,
        total_discrepancies=len(discrepancies),
        status="completed",
    )

    from app.services.materiality_engine import compute_record_materiality, compute_summary_materiality
    for r in results:
        compute_record_materiality(r)
    summary = compute_summary_materiality(results, discrepancies, summary)

    return summary, results, discrepancies, records_by_source, missing_by_source


def verify_multisource_project_files(
    db: Session,
    project_id: uuid.UUID,
    request: MultiSourceVerificationRequest,
    current_user: Optional[User] = None,
) -> MultiSourceVerificationResponse:
    """Reconcile multiple uploaded files in a project on-demand."""
    project = get_project_by_id(db, project_id, current_user=current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    cfg = request.preprocessing_config or PreprocessingConfig()
    sources_records: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
    from app.services.profiling_service import get_excluded_row_indices_for_file

    storage_root_resolved = settings.storage_root.resolve()

    for s in request.sources:
        sf = db.query(SourceFile).filter(
            SourceFile.id == s.file_id,
            SourceFile.project_id == project_id,
        ).first()
        if sf is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source file {s.file_id} ({s.alias}) not found for this project.",
            )

        path_resolved = Path(sf.storage_path).resolve()
        if not str(path_resolved).startswith(str(storage_root_resolved)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access to file path for {s.alias} is restricted.",
            )
        if not path_resolved.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Content for {s.alias} not found on disk.",
            )

        if not s.excluded_row_indices:
            s.excluded_row_indices = get_excluded_row_indices_for_file(path_resolved)

        recs, _, _, _, _, _, _ = extract_dataset_records(path_resolved, sf.file_type, cfg)
        sources_records[s.alias] = recs

    summary, results, discrepancies, records_by_src, missing_by_src = verify_multisource_datasets(
        sources=request.sources,
        sources_records=sources_records,
        unified_keys=request.unified_keys,
        compare_attributes=request.compare_attributes,
        ignore_attributes=request.ignore_attributes,
        numeric_tolerance=request.numeric_tolerance,
        ignore_whitespace=request.ignore_whitespace,
        ignore_case=request.ignore_case,
        null_values=cfg.null_values,
        include_identical=request.include_identical,
        status_rules=request.status_rules,
        rule_config=request.rule_config,
    )

    return MultiSourceVerificationResponse(
        project_id=project_id,
        sources=request.sources,
        unified_keys=request.unified_keys,
        summary=summary,
        records_by_source=records_by_src,
        missing_by_source=missing_by_src,
        results=results,
        discrepancies=discrepancies,
        warnings=[],
        errors=[],
    )


def create_and_execute_multisource_run(
    db: Session,
    project_id: uuid.UUID,
    request: MultiSourceVerificationRequest,
    current_user: Optional[User] = None,
) -> VerificationRun:
    """Create a persistent multi-source VerificationRun record and persist discrepancies."""
    project = get_project_by_id(db, project_id, current_user=current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    primary_source = next((s for s in request.sources if s.is_primary), request.sources[0])
    secondary_source = next((s for s in request.sources if s.alias != primary_source.alias), request.sources[-1])

    now_utc = datetime.now(timezone.utc)
    run = VerificationRun(
        project_id=project_id,
        source_file_id=primary_source.file_id,
        target_file_id=secondary_source.file_id,
        key_columns=request.unified_keys,
        column_mapping={s.alias: s.field_mapping for s in request.sources},
        sources=[s.model_dump(mode="json") for s in request.sources],
        configuration=request.model_dump(mode="json"),
        status="running",
        started_at=now_utc,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        with db.begin_nested():
            cfg = request.preprocessing_config or PreprocessingConfig()
            sources_records: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
            from app.services.profiling_service import get_excluded_row_indices_for_file
            storage_root_resolved = settings.storage_root.resolve()

            for s in request.sources:
                sf = db.query(SourceFile).filter(
                    SourceFile.id == s.file_id,
                    SourceFile.project_id == project_id,
                ).first()
                if sf is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Source file {s.file_id} ({s.alias}) not found.",
                    )
                path_resolved = Path(sf.storage_path).resolve()
                if not str(path_resolved).startswith(str(storage_root_resolved)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Access to file path for {s.alias} is restricted.",
                    )
                if not path_resolved.exists():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Content for {s.alias} not found on disk.",
                    )

                if not s.excluded_row_indices:
                    s.excluded_row_indices = get_excluded_row_indices_for_file(path_resolved)

                recs, _, _, _, _, _, _ = extract_dataset_records(path_resolved, sf.file_type, cfg)
                sources_records[s.alias] = recs

            summary, results, discrepancies, records_by_src, missing_by_src = verify_multisource_datasets(
                sources=request.sources,
                sources_records=sources_records,
                unified_keys=request.unified_keys,
                compare_attributes=request.compare_attributes,
                ignore_attributes=request.ignore_attributes,
                numeric_tolerance=request.numeric_tolerance,
                ignore_whitespace=request.ignore_whitespace,
                ignore_case=request.ignore_case,
                null_values=cfg.null_values,
                include_identical=request.include_identical,
                status_rules=request.status_rules,
                rule_config=request.rule_config,
            )

            run.status = "completed"
            summary_dict = summary.model_dump()
            summary_dict["records_by_source"] = records_by_src
            summary_dict["missing_by_source"] = missing_by_src
            run.summary = summary_dict
            run.completed_at = datetime.now(timezone.utc)

            for item in discrepancies:
                disc = VerificationDiscrepancy(
                    run_id=run.id,
                    match_status=item.match_status.value,
                    discrepancy_category=item.discrepancy_category.value,
                    key_values=item.key_values,
                    source_row_number=item.source_row_number,
                    target_row_number=item.target_row_number,
                    source_row_indices=item.source_row_indices,
                    source_records=item.source_records,
                    source_record=item.source_record,
                    target_record=item.target_record,
                    child_records=item.child_records,
                    aggregated_amount=item.aggregated_amount,
                    expected_amount=item.expected_amount,
                    source_amount=item.source_amount,
                    target_amount=item.target_amount,
                    variance_amount=item.variance_amount,
                    exposure_amount=item.exposure_amount,
                    currency=item.currency or "USD",
                    severity=item.severity or "medium",
                    resolution_status=item.resolution_status or "unresolved",
                    side_by_side=item.side_by_side,
                    _reason_code=item.reason_code.value if hasattr(item.reason_code, "value") else (str(item.reason_code) if item.reason_code else None),
                    _confidence_score=item.confidence_score,
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



