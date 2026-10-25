"""Core evaluator and validation engine for Versioned JSON Rules (Batch 4)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.result import (
    DiscrepancyCategory,
    FieldDifference,
    MatchStatus,
    ReasonCode,
    VerificationResultItem,
)
from app.schemas.rule import (
    CompoundRule,
    DateWindowRule,
    NumericToleranceRule,
    PredicateOperator,
    RuleConjunction,
    RulePreviewResponse,
    RuleSeverity,
    RuleValidateResponse,
    StatusTransitionRule,
    ToleranceMode,
    VersionedRuleConfig,
    WhereCondition,
)


# ==============================================================================
# Helper Utilities
# ==============================================================================

COMMON_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%m/%d/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y%m%d",
]


def parse_flexible_date(val: Any, explicit_fmt: Optional[str] = None) -> Optional[datetime]:
    """Parse date from string or datetime object across common accounting formats."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val

    s = str(val).strip()
    if not s:
        return None

    if explicit_fmt:
        try:
            return datetime.strptime(s, explicit_fmt)
        except Exception:
            pass

    for fmt in COMMON_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def clean_numeric(val: Any) -> Optional[float]:
    """Strip currency symbols, commas, and parentheses for robust numeric extraction."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if not s or s.lower() in {"null", "none", "nan", "nil", "n/a", ""}:
        return None

    # Handle accounting negative (123.45)
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    elif s.endswith("-"):
        is_negative = True
        s = s[:-1].strip()

    # Remove currency symbols and formatting commas
    cleaned = re.sub(r"[^\d.-]", "", s)
    if not cleaned:
        return None

    try:
        num = float(cleaned)
        return -num if is_negative else num
    except Exception:
        return None


# ==============================================================================
# Predicate & Rule Evaluators
# ==============================================================================


def evaluate_predicate(
    record: Dict[str, Any],
    condition: WhereCondition,
    other_record: Optional[Dict[str, Any]] = None,
) -> bool:
    """Evaluate a single WhereCondition predicate against a data record."""
    val = record.get(condition.field)

    target_val = condition.value
    if condition.target_field and other_record is not None:
        target_val = other_record.get(condition.target_field)

    op = condition.operator

    # Null checks
    if op == PredicateOperator.IS_NULL:
        return val is None or str(val).strip().lower() in {"null", "none", "nan", "nil", "n/a", ""}
    if op == PredicateOperator.IS_NOT_NULL:
        return val is not None and str(val).strip().lower() not in {"null", "none", "nan", "nil", "n/a", ""}

    if val is None:
        return False

    # Equality & Inequality
    if op == PredicateOperator.EQUAL:
        if isinstance(target_val, (int, float)) or (isinstance(val, (int, float))):
            num_v = clean_numeric(val)
            num_t = clean_numeric(target_val)
            if num_v is not None and num_t is not None:
                return abs(num_v - num_t) < 1e-9
        return str(val).strip().lower() == str(target_val).strip().lower()

    if op == PredicateOperator.NOT_EQUAL:
        if isinstance(target_val, (int, float)) or (isinstance(val, (int, float))):
            num_v = clean_numeric(val)
            num_t = clean_numeric(target_val)
            if num_v is not None and num_t is not None:
                return abs(num_v - num_t) >= 1e-9
        return str(val).strip().lower() != str(target_val).strip().lower()

    # Set membership
    if op == PredicateOperator.IN:
        if not isinstance(target_val, (list, set, tuple)):
            target_list = [str(target_val).strip().lower()]
        else:
            target_list = [str(x).strip().lower() for x in target_val]
        return str(val).strip().lower() in target_list

    if op == PredicateOperator.NOT_IN:
        if not isinstance(target_val, (list, set, tuple)):
            target_list = [str(target_val).strip().lower()]
        else:
            target_list = [str(x).strip().lower() for x in target_val]
        return str(val).strip().lower() not in target_list

    # Numeric & Ordered Comparisons
    num_val = clean_numeric(val)
    if num_val is not None:
        if op == PredicateOperator.GREATER_THAN:
            target_num = clean_numeric(target_val)
            return target_num is not None and num_val > target_num
        if op == PredicateOperator.LESS_THAN:
            target_num = clean_numeric(target_val)
            return target_num is not None and num_val < target_num
        if op == PredicateOperator.GREATER_EQUAL:
            target_num = clean_numeric(target_val)
            return target_num is not None and num_val >= target_num
        if op == PredicateOperator.LESS_EQUAL:
            target_num = clean_numeric(target_val)
            return target_num is not None and num_val <= target_num
        if op == PredicateOperator.BETWEEN:
            if isinstance(target_val, (list, tuple)) and len(target_val) == 2:
                low = clean_numeric(target_val[0])
                high = clean_numeric(target_val[1])
                if low is not None and high is not None:
                    return low <= num_val <= high
            return False

    # Regex
    if op == PredicateOperator.REGEX:
        try:
            return bool(re.search(str(target_val), str(val), re.IGNORECASE))
        except Exception:
            return False

    return False


def evaluate_date_window(
    src_val: Any,
    tgt_val: Any,
    rule: DateWindowRule,
) -> Tuple[bool, Optional[str]]:
    """
    Verify settlement lag: target_date must fall within [source_date - lag_before, source_date + lag_after].
    """
    src_dt = parse_flexible_date(src_val, rule.date_format)
    tgt_dt = parse_flexible_date(tgt_val, rule.date_format)

    if src_dt is None or tgt_dt is None:
        return False, f"Could not parse valid date values: '{src_val}' or '{tgt_val}'"

    diff_days = (tgt_dt.date() - src_dt.date()).days
    if -rule.lag_days_before <= diff_days <= rule.lag_days_after:
        return True, None

    return (
        False,
        f"Settlement date lag of {diff_days} day(s) exceeds window [-{rule.lag_days_before}, +{rule.lag_days_after}] days (source: {src_dt.date()}, target: {tgt_dt.date()})"
    )


def evaluate_numeric_tolerance(
    src_val: Any,
    tgt_val: Any,
    rule: NumericToleranceRule,
) -> Tuple[bool, Optional[str]]:
    """Verify numeric differences against absolute and/or relative percentage tolerance thresholds."""
    src_num = clean_numeric(src_val)
    tgt_num = clean_numeric(tgt_val)

    if src_num is None or tgt_num is None:
        return False, f"Non-numeric values encountered for tolerance check: '{src_val}' vs '{tgt_val}'"

    abs_diff = abs(src_num - tgt_num)
    base = max(abs(src_num), 1e-9)
    pct_diff = (abs_diff / base) * 100.0

    abs_ok = abs_diff <= rule.absolute_tolerance
    pct_ok = pct_diff <= rule.percentage_tolerance

    if rule.tolerance_mode == ToleranceMode.ABSOLUTE:
        passed = abs_ok
    elif rule.tolerance_mode == ToleranceMode.PERCENTAGE:
        passed = pct_ok
    elif rule.tolerance_mode == ToleranceMode.BOTH_OR:
        passed = abs_ok or pct_ok
    else:  # BOTH_AND
        passed = abs_ok and pct_ok

    if passed:
        return True, None

    return (
        False,
        f"Amount difference of {abs_diff:.2f} ({pct_diff:.2f}%) exceeds tolerance ({rule.tolerance_mode.value}: abs={rule.absolute_tolerance}, pct={rule.percentage_tolerance}%)"
    )


def evaluate_status_transition(
    src_val: Any,
    tgt_val: Any,
    rule: StatusTransitionRule,
) -> Tuple[bool, Optional[str]]:
    """Verify that source status maps to an allowed secondary status per explicit whitelist."""
    if src_val is None or tgt_val is None:
        return False, "Null status value encountered"

    src_s = str(src_val).strip()
    tgt_s = str(tgt_val).strip()

    if not rule.case_sensitive:
        src_s = src_s.upper()
        tgt_s = tgt_s.upper()
        allowed = {k.upper(): [v.upper() for v in vals] for k, vals in rule.allowed_transitions.items()}
    else:
        allowed = rule.allowed_transitions

    if src_s in allowed:
        permitted_list = allowed[src_s]
        if tgt_s in permitted_list or tgt_s == src_s:
            return True, None
        return (
            False,
            f"Status transition '{src_val}' -> '{tgt_val}' is not allowed. Permitted targets: {permitted_list}"
        )

    # If source status not in whitelist but values are identical, pass
    if src_s == tgt_s:
        return True, None

    return (
        False,
        f"Source status '{src_val}' has no defined transition to '{tgt_val}' in whitelist"
    )


def evaluate_compound_rule(
    record: Dict[str, Any],
    rule: CompoundRule,
    other_record: Optional[Dict[str, Any]] = None,
) -> bool:
    """Evaluate compound rule with conjunction."""
    if not rule.conditions:
        return True

    results = [
        evaluate_predicate(record, cond, other_record)
        for cond in rule.conditions
    ]

    if rule.conjunction == RuleConjunction.AND:
        return all(results)
    return any(results)


# ==============================================================================
# Validation & Impact Preview APIs
# ==============================================================================


def validate_rule_config(
    config: VersionedRuleConfig,
    source_schemas: Optional[Dict[str, List[str]]] = None,
) -> RuleValidateResponse:
    """Validate rule syntax, operator parameters, and check field existence against source schemas."""
    errors: List[str] = []
    warnings: List[str] = []
    field_resolutions: Dict[str, bool] = {}
    total_rules = 0

    # 1. Version check
    if not config.version.startswith("1."):
        warnings.append(f"Rule schema version '{config.version}' is non-standard. Expected '1.x.x'.")

    all_known_cols: Set[str] = set()
    if source_schemas:
        for alias, cols in source_schemas.items():
            for c in cols:
                all_known_cols.add(c.lower())
                all_known_cols.add(f"{alias.lower()}.{c.lower()}")

    def check_col(field_name: Optional[str], rule_desc: str, alias: Optional[str] = None):
        if not field_name:
            return
        total_rules_checked = True
        if source_schemas:
            normalized = field_name.lower()
            if alias:
                scoped = f"{alias.lower()}.{normalized}"
                exists = (scoped in all_known_cols) or (normalized in all_known_cols)
            else:
                exists = normalized in all_known_cols or any(
                    normalized in [c.lower() for c in cols] for cols in source_schemas.values()
                )
            field_resolutions[field_name] = exists
            if not exists:
                warnings.append(f"{rule_desc}: Field '{field_name}' not found in uploaded dataset columns.")

    # 2. Where conditions
    for idx, cond in enumerate(config.where_conditions):
        total_rules += 1
        check_col(cond.field, f"Where Condition #{idx + 1}", cond.source_alias)
        if cond.target_field:
            check_col(cond.target_field, f"Where Condition #{idx + 1} target", None)
        if cond.operator == PredicateOperator.REGEX:
            try:
                re.compile(str(cond.value))
            except Exception as e:
                errors.append(f"Where Condition #{idx + 1}: Invalid regular expression '{cond.value}': {e}")
        elif cond.operator == PredicateOperator.BETWEEN:
            if not isinstance(cond.value, (list, tuple)) or len(cond.value) != 2:
                errors.append(f"Where Condition #{idx + 1}: 'between' operator requires [min, max] list value.")

    # 3. Date window rules
    for idx, dw in enumerate(config.date_window_rules):
        total_rules += 1
        check_col(dw.source_date_field, f"Date Window #{idx + 1} source", dw.source_alias)
        check_col(dw.target_date_field, f"Date Window #{idx + 1} target", dw.target_alias)
        if dw.lag_days_before < 0 or dw.lag_days_after < 0:
            errors.append(f"Date Window #{idx + 1}: Lag days cannot be negative.")

    # 4. Numeric tolerance rules
    for idx, nt in enumerate(config.numeric_tolerance_rules):
        total_rules += 1
        check_col(nt.source_amount_field, f"Numeric Tolerance #{idx + 1} source", nt.source_alias)
        check_col(nt.target_amount_field, f"Numeric Tolerance #{idx + 1} target", nt.target_alias)
        if nt.absolute_tolerance < 0 or nt.percentage_tolerance < 0:
            errors.append(f"Numeric Tolerance #{idx + 1}: Tolerances cannot be negative.")

    # 5. Status transition rules
    for idx, st in enumerate(config.status_transition_rules):
        total_rules += 1
        check_col(st.source_field, f"Status Transition #{idx + 1} source", st.source_alias)
        check_col(st.target_field, f"Status Transition #{idx + 1} target", st.target_alias)
        if not st.allowed_transitions:
            warnings.append(f"Status Transition #{idx + 1}: Whitelist is empty.")

    # 6. Aggregation config
    if config.aggregation_config and config.aggregation_config.enabled:
        total_rules += 1
        ac = config.aggregation_config
        check_col(ac.parent_key, "Aggregation parent key", ac.parent_source_alias)
        check_col(ac.child_grouping_key, "Aggregation child grouping key", ac.child_source_alias)
        check_col(ac.parent_amount_field, "Aggregation parent amount", ac.parent_source_alias)
        check_col(ac.child_amount_field, "Aggregation child amount", ac.child_source_alias)
        if ac.numeric_tolerance < 0 or ac.percentage_tolerance < 0:
            errors.append("Aggregation Config: Tolerances cannot be negative.")

    return RuleValidateResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        total_rules_checked=total_rules,
        field_resolutions=field_resolutions,
    )


def preview_rule_impact(
    config: VersionedRuleConfig,
    sources_data: Dict[str, List[Tuple[int, Dict[str, Any]]]],
    sample_size: int = 100,
) -> RulePreviewResponse:
    """Run a fast dry-run impact preview on sampled records to project passing counts and exceptions."""
    aliases = list(sources_data.keys())
    if len(aliases) < 2:
        return RulePreviewResponse(
            total_evaluated=0,
            passed_count=0,
            exception_count=0,
            exceptions_by_rule={},
            exceptions_by_severity={},
            sample_discrepancies=[],
        )

    src_alias = aliases[0]
    tgt_alias = aliases[1]

    src_records = sources_data[src_alias][:sample_size]
    tgt_records = sources_data[tgt_alias][:sample_size]

    total_evaluated = len(src_records)
    passed_count = 0
    exception_count = 0
    exceptions_by_rule: Dict[str, int] = {}
    exceptions_by_severity: Dict[str, int] = {
        RuleSeverity.BLOCKING.value: 0,
        RuleSeverity.WARNING.value: 0,
        RuleSeverity.INFO.value: 0,
    }
    sample_discrepancies: List[Dict[str, Any]] = []

    # Fast 1:1 pairwise test on sample
    for idx in range(min(len(src_records), len(tgt_records))):
        s_row, s_rec = src_records[idx]
        t_row, t_rec = tgt_records[idx]

        record_violations: List[Dict[str, Any]] = []

        # 1. Evaluate predicates
        for c_idx, cond in enumerate(config.where_conditions):
            rule_name = f"Predicate: {cond.field} {cond.operator.value}"
            passed = evaluate_predicate(s_rec, cond, t_rec)
            if not passed:
                exceptions_by_rule[rule_name] = exceptions_by_rule.get(rule_name, 0) + 1
                exceptions_by_severity[cond.severity.value] += 1
                record_violations.append({
                    "rule": rule_name,
                    "severity": cond.severity.value,
                    "reason_code": ReasonCode.PREDICATE_VIOLATION.value,
                    "message": f"Field '{cond.field}' failed predicate {cond.operator.value}",
                })

        # 2. Date windows
        for dw in config.date_window_rules:
            rule_name = f"DateWindow: {dw.source_date_field} -> {dw.target_date_field}"
            s_val = s_rec.get(dw.source_date_field)
            t_val = t_rec.get(dw.target_date_field)
            if s_val is not None and t_val is not None:
                passed, msg = evaluate_date_window(s_val, t_val, dw)
                if not passed:
                    exceptions_by_rule[rule_name] = exceptions_by_rule.get(rule_name, 0) + 1
                    exceptions_by_severity[dw.severity.value] += 1
                    record_violations.append({
                        "rule": rule_name,
                        "severity": dw.severity.value,
                        "reason_code": ReasonCode.DATE_WINDOW_EXCEEDED.value,
                        "message": msg,
                    })

        # 3. Numeric tolerances
        for nt in config.numeric_tolerance_rules:
            rule_name = f"Tolerance: {nt.source_amount_field} vs {nt.target_amount_field}"
            s_val = s_rec.get(nt.source_amount_field)
            t_val = t_rec.get(nt.target_amount_field)
            if s_val is not None and t_val is not None:
                passed, msg = evaluate_numeric_tolerance(s_val, t_val, nt)
                if not passed:
                    exceptions_by_rule[rule_name] = exceptions_by_rule.get(rule_name, 0) + 1
                    exceptions_by_severity[nt.severity.value] += 1
                    record_violations.append({
                        "rule": rule_name,
                        "severity": nt.severity.value,
                        "reason_code": ReasonCode.AMOUNT_TOLERANCE_EXCEEDED.value,
                        "message": msg,
                    })

        # 4. Status transitions
        for st in config.status_transition_rules:
            rule_name = f"StatusTransition: {st.source_field} -> {st.target_field}"
            s_val = s_rec.get(st.source_field)
            t_val = t_rec.get(st.target_field)
            if s_val is not None and t_val is not None:
                passed, msg = evaluate_status_transition(s_val, t_val, st)
                if not passed:
                    exceptions_by_rule[rule_name] = exceptions_by_rule.get(rule_name, 0) + 1
                    exceptions_by_severity[st.severity.value] += 1
                    record_violations.append({
                        "rule": rule_name,
                        "severity": st.severity.value,
                        "reason_code": ReasonCode.STATUS_TRANSITION_VIOLATION.value,
                        "message": msg,
                    })

        if not record_violations:
            passed_count += 1
        else:
            exception_count += 1
            if len(sample_discrepancies) < 10:
                sample_discrepancies.append({
                    "source_row": s_row,
                    "target_row": t_row,
                    "source_record": s_rec,
                    "target_record": t_rec,
                    "violations": record_violations,
                })

    return RulePreviewResponse(
        total_evaluated=total_evaluated,
        passed_count=passed_count,
        exception_count=exception_count,
        exceptions_by_rule=exceptions_by_rule,
        exceptions_by_severity=exceptions_by_severity,
        sample_discrepancies=sample_discrepancies,
    )
