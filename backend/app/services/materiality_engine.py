"""Financial Materiality, Monetary Exposure Metrics, and Side-by-Side Record Inspection Engine.

Provides precise accounting semantics, gross exception exposure, net variance,
claimed/verified/outstanding totals, currency-aware aggregation, 2-decimal rounding,
and detailed field-level raw vs. normalized side-by-side inspection payloads.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.result import (
    DiscrepancyCategory,
    FieldComparisonDiff,
    FieldDifference,
    MatchStatus,
    ReasonCode,
    SideBySideInspectionResponse,
    VerificationResultItem,
    VerificationSummary,
)
from app.utils.normalization import (
    clean_whitespace,
    is_boolean,
    parse_date,
    parse_numeric,
    PAREN_NEGATIVE_REGEX,
)

DEFAULT_NULL_VALUES = {"", "nan", "none", "null", "n/a", "na", "-", "."}


def _enum_value(val: Any) -> Optional[str]:
    """Return a plain string for enum / string reason codes."""
    if val is None:
        return None
    value = getattr(val, "value", val)
    return str(value)


def check_null(val: Any) -> bool:
    """Check if value represents null/empty."""
    if val is None:
        return True
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return True
    return str(val).strip().lower() in DEFAULT_NULL_VALUES

# Common keywords for detecting monetary amounts
CURRENCY_AMOUNT_KEYWORDS = {
    "amount",
    "total_amount",
    "gross_amount",
    "net_amount",
    "balance",
    "total",
    "price",
    "fee",
    "cost",
    "salary",
    "payment",
    "remuneration",
    "premium",
    "revenue",
    "tuition",
    "installment_amount",
    "due_amount",
    "subtotal",
}

CURRENCY_SYMBOL_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "¥": "JPY",
    "C$": "CAD",
    "A$": "AUD",
    "CHF": "CHF",
}


def detect_currency(val: Any, record: Optional[Dict[str, Any]] = None) -> str:
    """Detect ISO currency code from explicit record fields or currency symbols."""
    if record:
        for k, v in record.items():
            if str(k).strip().lower() in {"currency", "curr", "iso_currency", "currency_code"} and v:
                clean_curr = str(v).strip().upper()
                if len(clean_curr) == 3:
                    return clean_curr

    if isinstance(val, str):
        for sym, code in CURRENCY_SYMBOL_MAP.items():
            if sym in val:
                return code

    return "USD"


def extract_amount_and_currency(
    record: Optional[Dict[str, Any]],
    preferred_field: Optional[str] = None,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Tuple[float, str]:
    """Extract primary monetary amount and currency from a record with accounting format support."""
    if not record or not isinstance(record, dict):
        return 0.0, "USD"

    # 1. Preferred field if specified or mapped
    target_field = preferred_field
    if column_mapping and preferred_field and preferred_field in column_mapping:
        target_field = column_mapping[preferred_field]

    if target_field and target_field in record:
        val = record[target_field]
        curr = detect_currency(val, record)
        parsed = _parse_monetary_value(val)
        if parsed is not None:
            return round(parsed, 2), curr

    # 2. Look for exact matches in CURRENCY_AMOUNT_KEYWORDS
    for col, val in record.items():
        col_clean = str(col).strip().lower()
        if col_clean in CURRENCY_AMOUNT_KEYWORDS:
            parsed = _parse_monetary_value(val)
            if parsed is not None:
                return round(parsed, 2), detect_currency(val, record)

    # 3. Look for substring matches
    for col, val in record.items():
        col_clean = str(col).strip().lower()
        if any(kw in col_clean for kw in ["amount", "total", "balance", "price", "fee", "cost", "salary", "payment"]):
            parsed = _parse_monetary_value(val)
            if parsed is not None:
                return round(parsed, 2), detect_currency(val, record)

    # 4. Check for formatted currency string values
    for col, val in record.items():
        if isinstance(val, str) and any(sym in val for sym in ["$", "€", "£", "₹"]):
            parsed = _parse_monetary_value(val)
            if parsed is not None:
                return round(parsed, 2), detect_currency(val, record)

    return 0.0, detect_currency(None, record)


def _parse_monetary_value(val: Any) -> Optional[float]:
    """Parse numeric / monetary value handling integers, floats, parenthetical accounting negatives, and formatted strings."""
    if val is None or check_null(val):
        return None

    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)

    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None

        # Parenthetical negative accounting: "(500.00)" -> -500.00
        paren = PAREN_NEGATIVE_REGEX.match(s)
        if paren:
            inner = paren.group(1).strip()
            num = _parse_monetary_value(inner)
            if num is not None:
                return -abs(num)

        # Standard numeric parsing with currency sign/comma stripping
        parsed, _ = parse_numeric(s)
        if parsed is not None:
            return float(parsed)

    return None


def normalize_value_for_display(val: Any) -> Any:
    """Normalize value for readable comparison and inspection."""
    if val is None or check_null(val):
        return None

    # Boolean normalization
    is_b, b_val = is_boolean(val)
    if is_b:
        return b_val

    # Date normalization
    parsed_d, _ = parse_date(val)
    if parsed_d is not None:
        return parsed_d

    # Numeric normalization
    parsed_n = _parse_monetary_value(val)
    if parsed_n is not None:
        # If integer equivalent, format cleanly or keep float
        return int(parsed_n) if parsed_n.is_integer() else round(parsed_n, 4)

    # Clean whitespace string
    return clean_whitespace(val)


def normalize_record_dict(rec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Produce normalized dictionary representation of record."""
    if not rec or not isinstance(rec, dict):
        return {}
    return {k: normalize_value_for_display(v) for k, v in rec.items()}


def build_side_by_side_payload(
    item: Any,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Generate detailed side-by-side inspection structure comparing raw vs. normalized values across sources."""
    raw_source = getattr(item, "source_record", None) or {}
    raw_target = getattr(item, "target_record", None) or {}

    norm_source = normalize_record_dict(raw_source)
    norm_target = normalize_record_dict(raw_target)

    # Map target columns if mapping provided
    col_map = column_mapping or {}
    reverse_map = {v: k for k, v in col_map.items()}

    field_diffs = getattr(item, "field_differences", []) or []
    diff_by_field: Dict[str, Any] = {}
    for d in field_diffs:
        fname = getattr(d, "field_name", None) or (d.get("field_name") if isinstance(d, dict) else None)
        if fname:
            diff_by_field[fname.lower()] = d

    # Gather all unique fields across source and target
    all_fields: List[str] = []
    seen_fields: Set[str] = set()

    # Prioritize source fields
    for k in raw_source.keys():
        kl = str(k).lower()
        if kl not in seen_fields:
            all_fields.append(str(k))
            seen_fields.add(kl)

    # Add unmapped target fields
    for k in raw_target.keys():
        s_alias = reverse_map.get(k, k)
        kl = str(s_alias).lower()
        if kl not in seen_fields:
            all_fields.append(str(s_alias))
            seen_fields.add(kl)

    comparisons: List[Dict[str, Any]] = []

    for f in all_fields:
        source_key = f
        target_key = col_map.get(f, f)

        raw_s = raw_source.get(source_key) if raw_source else None
        norm_s = norm_source.get(source_key) if norm_source else None

        raw_t = raw_target.get(target_key) if raw_target else None
        norm_t = norm_target.get(target_key) if norm_target else None

        diff_obj = diff_by_field.get(f.lower()) or diff_by_field.get(target_key.lower())

        is_match = True
        diff_type = None
        reason_code_val = None
        msg = None

        if diff_obj:
            is_match = False
            diff_type = getattr(diff_obj, "difference_type", None) or (
                diff_obj.get("difference_type") if isinstance(diff_obj, dict) else "value_mismatch"
            )
            reason_code_val = getattr(diff_obj, "reason_code", None) or (
                diff_obj.get("reason_code") if isinstance(diff_obj, dict) else None
            )
            reason_code_val = _enum_value(reason_code_val)
            msg = getattr(diff_obj, "message", None) or (
                diff_obj.get("message") if isinstance(diff_obj, dict) else None
            )
        else:
            # Check normalized equality
            if norm_s != norm_t:
                is_match = False
                diff_type = "value_mismatch"
                msg = f"Normalized mismatch: '{norm_s}' != '{norm_t}'"

        comparisons.append({
            "field_name": f,
            "source_field": source_key,
            "target_field": target_key,
            "raw_source_value": raw_s,
            "normalized_source_value": norm_s,
            "raw_target_value": raw_t,
            "normalized_target_value": norm_t,
            "is_match": is_match,
            "difference_type": diff_type,
            "reason_code": str(reason_code_val) if reason_code_val else None,
            "message": msg,
        })

    # Failed rule descriptions
    failed_rules: List[Dict[str, Any]] = []
    reason_code = _enum_value(getattr(item, "reason_code", None))
    if reason_code and reason_code != "EXACT_MATCH":
        failed_rules.append({
            "rule": reason_code,
            "description": getattr(item, "message", None) or f"Exception flagged with reason code {reason_code}",
            "discrepancy_category": _enum_value(getattr(item, "discrepancy_category", "field_mismatch")),
        })

    for cd in comparisons:
        if not cd["is_match"] and cd["message"] and cd["message"] not in [r["description"] for r in failed_rules]:
            failed_rules.append({
                "rule": cd["reason_code"] or "FIELD_DIFFERENCE",
                "field": cd["field_name"],
                "description": cd["message"],
            })

    return {
        "raw_source_record": raw_source,
        "normalized_source_record": norm_source,
        "raw_target_record": raw_target,
        "normalized_target_record": norm_target,
        "field_comparisons": comparisons,
        "failed_rules": failed_rules,
    }


def compute_record_materiality(
    item: VerificationResultItem,
    column_mapping: Optional[Dict[str, str]] = None,
) -> VerificationResultItem:
    """Calculate precise accounting amounts, signed variance, and absolute gross exposure for a single record."""
    status = item.match_status

    # 1. Split payment reconciliation with explicit expected and aggregated amounts
    if item.expected_amount is not None or item.aggregated_amount is not None:
        source_amt = round(float(item.expected_amount or 0.0), 2)
        target_amt = round(float(item.aggregated_amount or 0.0), 2)
        curr = "USD"
    # 2. Identical match: both sides equal
    elif status == MatchStatus.IDENTICAL:
        s_amt, curr = extract_amount_and_currency(item.source_record, column_mapping=column_mapping)
        source_amt = s_amt
        target_amt = s_amt
    # 3. Missing in target: only source amount exists
    elif status == MatchStatus.MISSING_IN_TARGET:
        s_amt, curr = extract_amount_and_currency(item.source_record, column_mapping=column_mapping)
        source_amt = s_amt
        target_amt = 0.0
    # 4. Missing in source: only target amount exists
    elif status == MatchStatus.MISSING_IN_SOURCE:
        t_amt, curr = extract_amount_and_currency(item.target_record, column_mapping=column_mapping)
        source_amt = 0.0
        target_amt = t_amt
    # 5. Field mismatch / Duplicate key / Needs review
    else:
        s_amt, curr_s = extract_amount_and_currency(item.source_record, column_mapping=column_mapping)
        t_amt, curr_t = extract_amount_and_currency(item.target_record, column_mapping=column_mapping)

        # If a specific field difference exists on an amount column, use its parsed values
        if item.field_differences:
            for fd in item.field_differences:
                fname = (fd.field_name or "").lower()
                if fname in CURRENCY_AMOUNT_KEYWORDS or "amount" in fname:
                    p_s = _parse_monetary_value(fd.source_value)
                    p_t = _parse_monetary_value(fd.target_value)
                    if p_s is not None:
                        s_amt = round(p_s, 2)
                    if p_t is not None:
                        t_amt = round(p_t, 2)
                    break

        source_amt = s_amt
        target_amt = t_amt
        curr = curr_s or curr_t or "USD"

    # Compute variance and exposure with strict 2-decimal rounding
    variance_amt = round(source_amt - target_amt, 2)
    exposure_amt = round(abs(source_amt - target_amt), 2)

    # Discrepancy severity classification
    if status == MatchStatus.IDENTICAL:
        severity = "info"
    elif exposure_amt >= 1000.0 or status in {
        MatchStatus.MISSING_IN_TARGET,
        MatchStatus.MISSING_IN_SOURCE,
        MatchStatus.AMBIGUOUS_DUPLICATE,
        MatchStatus.DUPLICATE_KEY_BOTH,
    }:
        severity = "high"
    elif exposure_amt > 0.0 or status in {
        MatchStatus.FIELD_MISMATCH,
        MatchStatus.PARTIAL_PAYMENT,
        MatchStatus.OVERPAYMENT,
    }:
        severity = "medium"
    else:
        severity = "low"

    # Populate item fields
    item.source_amount = source_amt
    item.target_amount = target_amt
    item.variance_amount = variance_amt
    item.exposure_amount = exposure_amt
    item.currency = curr
    item.severity = severity
    item.resolution_status = "unresolved" if status != MatchStatus.IDENTICAL else "resolved"

    # Build side-by-side comparison payload
    item.side_by_side = build_side_by_side_payload(item, column_mapping=column_mapping)

    return item


def compute_summary_materiality(
    results: List[VerificationResultItem],
    discrepancies: List[VerificationResultItem],
    summary: VerificationSummary,
) -> VerificationSummary:
    """Calculate aggregated accounting summary metrics across all reconciliation results."""
    # 1. Gross Exception Exposure: Absolute monetary sum of all discrepancies and variances (|source - target| across exception rows)
    gross_exposure = round(sum(float(d.exposure_amount or 0.0) for d in discrepancies), 2)

    # 2. Net Variance: Signed directional variance (sum(source_amount) - sum(target_amount))
    net_variance = round(
        sum(float(r.source_amount or 0.0) - float(r.target_amount or 0.0) for r in results),
        2,
    )

    # 3. Claimed Total: Total monetary value submitted in source records (excluding records missing in source)
    claimed_amount = round(
        sum(
            float(r.source_amount or 0.0)
            for r in results
            if r.match_status != MatchStatus.MISSING_IN_SOURCE
        ),
        2,
    )

    # 4. Verified Total: Total monetary value successfully reconciled with zero variance
    verified_amount = round(
        sum(
            float(r.source_amount or 0.0)
            for r in results
            if r.match_status == MatchStatus.IDENTICAL and float(r.exposure_amount or 0.0) == 0.0
        ),
        2,
    )

    # 5. Outstanding Total: Total monetary value currently unreconciled / disputed
    # In accounting, this equals gross exception exposure across all discrepant items
    outstanding_amount = round(gross_exposure, 2)

    # Determine primary currency and per-currency breakdown
    currency_counts: Dict[str, int] = {}
    currency_metrics: Dict[str, Dict[str, float]] = {}

    for r in results:
        curr = r.currency or "USD"
        currency_counts[curr] = currency_counts.get(curr, 0) + 1

        if curr not in currency_metrics:
            currency_metrics[curr] = {
                "gross_exposure": 0.0,
                "net_variance": 0.0,
                "claimed_amount": 0.0,
                "verified_amount": 0.0,
                "outstanding_amount": 0.0,
            }

        s_amt = float(r.source_amount or 0.0)
        t_amt = float(r.target_amount or 0.0)
        exp_amt = float(r.exposure_amount or 0.0)

        currency_metrics[curr]["net_variance"] += s_amt - t_amt
        if r.match_status != MatchStatus.MISSING_IN_SOURCE:
            currency_metrics[curr]["claimed_amount"] += s_amt
        if r.match_status == MatchStatus.IDENTICAL and exp_amt == 0.0:
            currency_metrics[curr]["verified_amount"] += s_amt
        if r.match_status != MatchStatus.IDENTICAL:
            currency_metrics[curr]["gross_exposure"] += exp_amt
            currency_metrics[curr]["outstanding_amount"] += exp_amt

    # Round currency breakdown
    exposure_by_currency = {
        curr: {k: round(v, 2) for k, v in m.items()}
        for curr, m in currency_metrics.items()
    }

    primary_currency = "USD"
    if currency_counts:
        primary_currency = max(currency_counts.items(), key=lambda x: x[1])[0]

    # Update summary
    summary.gross_exposure = gross_exposure
    summary.net_variance = net_variance
    summary.claimed_amount = claimed_amount
    summary.verified_amount = verified_amount
    summary.outstanding_amount = outstanding_amount
    summary.currency = primary_currency
    summary.exposure_by_currency = exposure_by_currency if len(exposure_by_currency) > 1 else None

    return summary
