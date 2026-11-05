"""Comprehensive Regression Test Suite for Financial Aggregation Corrections (Batches A-D).

Verifies:
- Batch A1: Duplicate Parent Keys (detection, preservation, unallocated children)
- Batch A2: Missing & Invalid Amounts (distinguishing valid zero from unparseable/null, preventing false IDENTICAL)
- Batch A3: Elimination of Orphan Sentinel (null/blank key isolation, real '__ORPHAN__' key safety)
- Batch B1: Dataset-Wide Duplicate Receipt Registry (cross-parent, intra-parent, 3+ occurrences, null/blank ignored)
- Batch B2: Missing Child/Parent Dates in Date-Window Rules (missing dates flagged, no false passes)
- Batch C1: Partial-Payment & Overpayment Flags (non-fatal warning policy vs discrepancy, tolerances)
- Batch C2: Summary Duplicate Metric Counters (duplicate source/target records, distinct keys, consistency)
"""

import pytest

from app.schemas.result import (
    DiscrepancyCategory,
    MatchStatus,
    ReasonCode,
)
from app.schemas.rule import AggregationConfig, DateWindowRule
from app.services.aggregation_engine import reconcile_split_payments


@pytest.fixture
def base_config() -> AggregationConfig:
    return AggregationConfig(
        enabled=True,
        parent_source_alias="invoices",
        child_source_alias="payments",
        parent_key="inv_id",
        child_grouping_key="inv_id",
        parent_amount_field="total",
        child_amount_field="amount",
        child_receipt_id_field="rec_id",
        numeric_tolerance=0.0,
        percentage_tolerance=0.0,
        allow_partial_payment=False,
        allow_overpayment=False,
    )


# ==============================================================================
# Batch A1 — Duplicate Parent Keys
# ==============================================================================


def test_two_parents_sharing_same_key(base_config: AggregationConfig):
    """Two parent records share the same normalized key; both must be preserved and flagged."""
    parents = [
        (1, {"inv_id": "INV-100", "total": 500.00}),
        (2, {"inv_id": "INV-100", "total": 300.00}),
    ]
    children = []

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.duplicate_source_records == 2
    assert summary.duplicate_source_keys_count == 1
    assert summary.unmatched_source_records == 0

    # Both parent rows are preserved in results and discrepancies
    parent_items = [r for r in results if r.match_status == MatchStatus.DUPLICATE_KEY_SOURCE]
    assert len(parent_items) == 2
    rows_reported = {item.source_row_number for item in parent_items}
    assert rows_reported == {1, 2}
    for item in parent_items:
        assert item.source_row_numbers == [1, 2]
        assert item.discrepancy_category == DiscrepancyCategory.DUPLICATE_KEY
        assert item.reason_code == ReasonCode.DUPLICATE_KEY_SOURCE


def test_three_or_more_parents_sharing_same_key(base_config: AggregationConfig):
    """Three parent records share the same key; all three rows preserved with full lineage."""
    parents = [
        (1, {"inv_id": "INV-999", "total": 100.00}),
        (2, {"inv_id": "INV-999", "total": 200.00}),
        (5, {"inv_id": "INV-999", "total": 300.00}),
    ]
    children = []

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.duplicate_source_records == 3
    assert summary.duplicate_source_keys_count == 1
    dup_items = [r for r in results if r.match_status == MatchStatus.DUPLICATE_KEY_SOURCE]
    assert len(dup_items) == 3
    assert {d.source_row_number for d in dup_items} == {1, 2, 5}


def test_duplicate_parent_key_with_child_payments(base_config: AggregationConfig):
    """Duplicate parent key with child payments: children must NOT be allocated to any duplicate parent."""
    parents = [
        (1, {"inv_id": "INV-DUP", "total": 400.00}),
        (2, {"inv_id": "INV-DUP", "total": 400.00}),
    ]
    children = [
        (10, {"inv_id": "INV-DUP", "amount": 200.00, "rec_id": "R1"}),
        (11, {"inv_id": "INV-DUP", "amount": 200.00, "rec_id": "R2"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.duplicate_source_records == 2
    assert summary.duplicate_source_keys_count == 1
    assert summary.conflicting_duplicate_records == 2

    # Children must NOT be matched or allocated
    assert summary.identical_matches == 0
    assert summary.matched_records == 0

    # Ensure children are reported as ambiguous duplicates
    child_items = [r for r in results if r.match_status == MatchStatus.AMBIGUOUS_DUPLICATE]
    assert len(child_items) == 2
    assert {c.target_row_number for c in child_items} == {10, 11}
    for c in child_items:
        assert c.source_row_numbers == [1, 2]
        assert "cannot be allocated" in c.message


def test_duplicate_parent_key_without_child_payments(base_config: AggregationConfig):
    """Duplicate parent key with zero child payments."""
    parents = [
        (1, {"inv_id": "INV-NO-CHILD", "total": 100.00}),
        (2, {"inv_id": "INV-NO-CHILD", "total": 150.00}),
    ]
    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=[],
        config=base_config,
    )

    assert summary.duplicate_source_records == 2
    assert summary.duplicate_source_keys_count == 1
    assert summary.conflicting_duplicate_records == 0
    assert len(discrepancies) == 2


# ==============================================================================
# Batch A2 — Missing & Invalid Amounts
# ==============================================================================


def test_parent_and_child_amount_both_valid_zero(base_config: AggregationConfig):
    """Parent amount is 0.0 and child sum is 0.0: valid zero-to-zero match must succeed."""
    parents = [(1, {"inv_id": "INV-ZERO", "total": "0.00"})]
    children = [(1, {"inv_id": "INV-ZERO", "amount": "0.00", "rec_id": "R0"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 1
    assert summary.field_mismatches == 0
    assert len(discrepancies) == 0
    assert results[0].match_status == MatchStatus.IDENTICAL
    assert results[0].expected_amount == 0.0
    assert results[0].aggregated_amount == 0.0


def test_parent_amount_is_null(base_config: AggregationConfig):
    """Parent amount is NULL: must NOT be coerced to 0.0 and must NOT result in IDENTICAL."""
    parents = [(1, {"inv_id": "INV-P-NULL", "total": None})]
    children = [(1, {"inv_id": "INV-P-NULL", "amount": 0.0, "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 0
    assert summary.field_mismatches == 1
    item = discrepancies[0]
    assert item.match_status == MatchStatus.FIELD_MISMATCH
    assert any(fd.difference_type == "invalid_numeric_amount" for fd in item.field_differences)


def test_child_amount_is_null(base_config: AggregationConfig):
    """Child installment amount is NULL: must NOT be coerced to 0.0."""
    parents = [(1, {"inv_id": "INV-C-NULL", "total": 100.00})]
    children = [
        (1, {"inv_id": "INV-C-NULL", "amount": 100.00, "rec_id": "R1"}),
        (2, {"inv_id": "INV-C-NULL", "amount": None, "rec_id": "R2"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 0
    assert summary.field_mismatches == 1
    item = discrepancies[0]
    assert item.match_status == MatchStatus.FIELD_MISMATCH
    assert any(fd.difference_type == "invalid_numeric_amount" for fd in item.field_differences)


def test_parent_amount_invalid_string(base_config: AggregationConfig):
    """Parent amount is an unparseable string 'N/A'."""
    parents = [(1, {"inv_id": "INV-NA", "total": "N/A"})]
    children = [(1, {"inv_id": "INV-NA", "amount": "0.00", "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 0
    assert summary.field_mismatches == 1
    assert discrepancies[0].match_status == MatchStatus.FIELD_MISMATCH
    fd = discrepancies[0].field_differences[0]
    assert fd.difference_type == "invalid_numeric_amount"
    assert fd.source_value == "N/A"


def test_child_amount_invalid_string_pending(base_config: AggregationConfig):
    """Child amount is 'PENDING': must trigger invalid_numeric_amount discrepancy."""
    parents = [(1, {"inv_id": "INV-PEND", "total": "100.00"})]
    children = [(1, {"inv_id": "INV-PEND", "amount": "PENDING", "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 0
    assert summary.field_mismatches == 1
    item = discrepancies[0]
    assert item.match_status == MatchStatus.FIELD_MISMATCH
    assert any(fd.target_value == "PENDING" for fd in item.field_differences)


def test_both_parent_and_child_amounts_invalid(base_config: AggregationConfig):
    """Both amounts unparseable strings: must NOT produce a false IDENTICAL match on 0.0==0.0."""
    parents = [(1, {"inv_id": "INV-BOTH-ERR", "total": "UNKNOWN"})]
    children = [(1, {"inv_id": "INV-BOTH-ERR", "amount": "CORRUPT", "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 0
    assert summary.field_mismatches == 1
    assert len(discrepancies) == 1
    assert discrepancies[0].match_status == MatchStatus.FIELD_MISMATCH


# ==============================================================================
# Batch A3 — Elimination of Orphan Sentinel
# ==============================================================================


def test_child_record_with_null_grouping_key(base_config: AggregationConfig):
    """Child with NULL grouping key goes to null_key_children with ReasonCode.NULL_KEY."""
    parents = [(1, {"inv_id": "INV-1", "total": 100.00})]
    children = [
        (1, {"inv_id": "INV-1", "amount": 100.00, "rec_id": "R1"}),
        (2, {"inv_id": None, "amount": 25.00, "rec_id": "R2"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 1
    assert summary.unmatched_target_records == 1
    null_key_item = next(d for d in discrepancies if d.reason_code == ReasonCode.NULL_KEY)
    assert null_key_item.match_status == MatchStatus.NEEDS_REVIEW
    assert null_key_item.key_values == {"inv_id": None}
    assert "missing or blank linking key" in null_key_item.message


def test_child_record_with_blank_and_whitespace_grouping_key(base_config: AggregationConfig):
    """Child records with empty and whitespace-only grouping keys are isolated as NULL_KEY."""
    parents = []
    children = [
        (1, {"inv_id": "", "amount": 10.00, "rec_id": "R1"}),
        (2, {"inv_id": "   ", "amount": 20.00, "rec_id": "R2"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.unmatched_target_records == 2
    assert summary.needs_review_records == 2
    for d in discrepancies:
        assert d.reason_code == ReasonCode.NULL_KEY


def test_legitimate_parent_key_named_orphan_safe(base_config: AggregationConfig):
    """Parent key legitimately named '__ORPHAN__' matches valid child and NEVER absorbs null-key child."""
    parents = [
        (1, {"inv_id": "__ORPHAN__", "total": 100.00}),
    ]
    children = [
        # Legitimate child payment for '__ORPHAN__'
        (1, {"inv_id": "__ORPHAN__", "amount": 100.00, "rec_id": "R-REAL"}),
        # Unrelated child with null key
        (2, {"inv_id": None, "amount": 50.00, "rec_id": "R-NULL"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 1
    assert summary.unmatched_target_records == 1

    # Legitimate parent '__ORPHAN__' matched exactly $100.00
    ident = next(r for r in results if r.match_status == MatchStatus.IDENTICAL)
    assert ident.key_values["inv_id"] == "__ORPHAN__"
    assert ident.aggregated_amount == 100.00

    # Null-key child was not absorbed
    orphan_null = next(d for d in discrepancies if d.reason_code == ReasonCode.NULL_KEY)
    assert orphan_null.aggregated_amount == 50.00


def test_child_referencing_nonexistent_parent_distinct_from_null_key(base_config: AggregationConfig):
    """Child referencing non-existent parent order 'INV-GHOST' is distinct from null-key child."""
    parents = [(1, {"inv_id": "INV-EXIST", "total": 50.00})]
    children = [
        (1, {"inv_id": "INV-EXIST", "amount": 50.00, "rec_id": "R1"}),
        (2, {"inv_id": "INV-GHOST", "amount": 30.00, "rec_id": "R2"}),
        (3, {"inv_id": None, "amount": 20.00, "rec_id": "R3"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 1
    assert summary.unmatched_target_records == 2

    ghost_item = next(d for d in discrepancies if d.key_values.get("inv_id") == "INV-GHOST")
    assert ghost_item.match_status == MatchStatus.UNMATCHED_SPLIT_RECORD
    assert ghost_item.reason_code == ReasonCode.UNMATCHED_SPLIT_RECORD

    null_item = next(d for d in discrepancies if d.reason_code == ReasonCode.NULL_KEY)
    assert null_item.match_status == MatchStatus.NEEDS_REVIEW


# ==============================================================================
# Batch B1 — Dataset-Wide Duplicate Receipt Registry
# ==============================================================================


def test_duplicate_receipt_within_single_parent(base_config: AggregationConfig):
    """Duplicate receipt ID within the same parent order."""
    parents = [(1, {"inv_id": "INV-1", "total": 200.00})]
    children = [
        (1, {"inv_id": "INV-1", "amount": 100.00, "rec_id": "REC-DUP"}),
        (2, {"inv_id": "INV-1", "amount": 100.00, "rec_id": "REC-DUP"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.field_mismatches == 1
    assert summary.duplicate_target_records == 2
    assert summary.duplicate_target_keys_count == 1
    assert discrepancies[0].match_status == MatchStatus.DUPLICATE_RECEIPT


def test_duplicate_receipt_across_different_parents(base_config: AggregationConfig):
    """Duplicate receipt ID used across two different parent orders (cross-parent fraud/error)."""
    parents = [
        (1, {"inv_id": "INV-A", "total": 100.00}),
        (2, {"inv_id": "INV-B", "total": 100.00}),
    ]
    children = [
        (1, {"inv_id": "INV-A", "amount": 100.00, "rec_id": "REC-SHARED"}),
        (2, {"inv_id": "INV-B", "amount": 100.00, "rec_id": "REC-SHARED"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.duplicate_target_records == 2
    assert summary.duplicate_target_keys_count == 1
    assert summary.field_mismatches == 2

    # Both parent orders must be flagged with DUPLICATE_RECEIPT
    dup_items = [d for d in discrepancies if d.match_status == MatchStatus.DUPLICATE_RECEIPT]
    assert len(dup_items) == 2
    for item in dup_items:
        assert "duplicated across multiple parent orders" in item.message


def test_duplicate_receipt_three_or_more_occurrences(base_config: AggregationConfig):
    """Receipt ID appearing 3 times across different orders."""
    parents = [
        (1, {"inv_id": "INV-1", "total": 50.00}),
        (2, {"inv_id": "INV-2", "total": 50.00}),
        (3, {"inv_id": "INV-3", "total": 50.00}),
    ]
    children = [
        (1, {"inv_id": "INV-1", "amount": 50.00, "rec_id": "REC-TRIPLE"}),
        (2, {"inv_id": "INV-2", "amount": 50.00, "rec_id": "REC-TRIPLE"}),
        (3, {"inv_id": "INV-3", "amount": 50.00, "rec_id": "REC-TRIPLE"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.duplicate_target_records == 3
    assert summary.duplicate_target_keys_count == 1
    assert summary.field_mismatches == 3


def test_blank_and_null_receipt_ids_not_treated_as_duplicates(base_config: AggregationConfig):
    """Blank and NULL receipt IDs must NOT collide or trigger duplicate receipt discrepancies."""
    parents = [(1, {"inv_id": "INV-OK", "total": 300.00})]
    children = [
        (1, {"inv_id": "INV-OK", "amount": 100.00, "rec_id": None}),
        (2, {"inv_id": "INV-OK", "amount": 100.00, "rec_id": ""}),
        (3, {"inv_id": "INV-OK", "amount": 100.00, "rec_id": "   "}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 1
    assert summary.duplicate_target_records == 0
    assert summary.duplicate_target_keys_count == 0
    assert len(discrepancies) == 0


# ==============================================================================
# Batch B2 — Missing Child / Parent Dates in Date Window
# ==============================================================================


def test_date_window_both_dates_present_within_range(base_config: AggregationConfig):
    """Settlement date window test: dates present and within range passes."""
    base_config.parent_date_field = "order_date"
    base_config.child_date_field = "pay_date"
    rule = DateWindowRule(
        source_date_field="order_date",
        target_date_field="pay_date",
        lag_days_before=0,
        lag_days_after=5,
    )

    parents = [(1, {"inv_id": "INV-DW-1", "total": 100.00, "order_date": "2026-03-01"})]
    children = [(1, {"inv_id": "INV-DW-1", "amount": 100.00, "pay_date": "2026-03-03", "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
        date_window_rules=[rule],
    )

    assert summary.identical_matches == 1
    assert summary.field_mismatches == 0


def test_date_window_child_date_outside_range(base_config: AggregationConfig):
    """Settlement date window test: child date exceeded lag range."""
    base_config.parent_date_field = "order_date"
    base_config.child_date_field = "pay_date"
    rule = DateWindowRule(
        source_date_field="order_date",
        target_date_field="pay_date",
        lag_days_before=0,
        lag_days_after=2,
    )

    parents = [(1, {"inv_id": "INV-DW-2", "total": 100.00, "order_date": "2026-03-01"})]
    children = [(1, {"inv_id": "INV-DW-2", "amount": 100.00, "pay_date": "2026-03-10", "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
        date_window_rules=[rule],
    )

    assert summary.field_mismatches == 1
    assert discrepancies[0].reason_code == ReasonCode.DATE_WINDOW_EXCEEDED


def test_date_window_missing_child_date_flagged(base_config: AggregationConfig):
    """Missing child date must NOT silently pass settlement date window verification."""
    base_config.parent_date_field = "order_date"
    base_config.child_date_field = "pay_date"
    rule = DateWindowRule(
        source_date_field="order_date",
        target_date_field="pay_date",
        lag_days_before=0,
        lag_days_after=5,
    )

    parents = [(1, {"inv_id": "INV-DW-MISS", "total": 100.00, "order_date": "2026-03-01"})]
    children = [(1, {"inv_id": "INV-DW-MISS", "amount": 100.00, "pay_date": None, "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
        date_window_rules=[rule],
    )

    assert summary.identical_matches == 0
    assert summary.field_mismatches == 1
    assert any(fd.difference_type == "missing_date" for fd in discrepancies[0].field_differences)


def test_date_window_missing_parent_date_flagged(base_config: AggregationConfig):
    """Missing parent date must NOT silently pass settlement date window verification."""
    base_config.parent_date_field = "order_date"
    base_config.child_date_field = "pay_date"
    rule = DateWindowRule(
        source_date_field="order_date",
        target_date_field="pay_date",
        lag_days_before=0,
        lag_days_after=5,
    )

    parents = [(1, {"inv_id": "INV-DW-P-MISS", "total": 100.00, "order_date": ""})]
    children = [(1, {"inv_id": "INV-DW-P-MISS", "amount": 100.00, "pay_date": "2026-03-02", "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
        date_window_rules=[rule],
    )

    assert summary.identical_matches == 0
    assert summary.field_mismatches == 1
    assert any(fd.difference_type == "missing_date" for fd in discrepancies[0].field_differences)


def test_date_window_disabled_when_no_rules_configured(base_config: AggregationConfig):
    """When date window rules are not configured, missing dates do not trigger errors."""
    base_config.parent_date_field = "order_date"
    base_config.child_date_field = "pay_date"

    parents = [(1, {"inv_id": "INV-NO-RULES", "total": 100.00, "order_date": None})]
    children = [(1, {"inv_id": "INV-NO-RULES", "amount": 100.00, "pay_date": None, "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
        date_window_rules=None,
    )

    assert summary.identical_matches == 1
    assert summary.field_mismatches == 0


# ==============================================================================
# Batch C1 — Partial-Payment and Overpayment Policy Flags
# ==============================================================================


def test_partial_payment_disallowed_default_triggers_discrepancy(base_config: AggregationConfig):
    """Default allow_partial_payment=False: partial payment triggers field_mismatch discrepancy."""
    base_config.allow_partial_payment = False
    parents = [(1, {"inv_id": "INV-PARTIAL", "total": 500.00})]
    children = [(1, {"inv_id": "INV-PARTIAL", "amount": 400.00, "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.field_mismatches == 1
    assert summary.needs_review_records == 0
    assert len(discrepancies) == 1
    assert discrepancies[0].match_status == MatchStatus.PARTIAL_PAYMENT
    assert discrepancies[0].discrepancy_category == DiscrepancyCategory.AGGREGATION_MISMATCH


def test_partial_payment_allowed_triggers_non_fatal_review(base_config: AggregationConfig):
    """allow_partial_payment=True: partial payment is treated as non-fatal warning/review item."""
    base_config.allow_partial_payment = True
    parents = [(1, {"inv_id": "INV-PARTIAL-PERMIT", "total": 500.00})]
    children = [(1, {"inv_id": "INV-PARTIAL-PERMIT", "amount": 400.00, "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.field_mismatches == 0
    assert summary.needs_review_records == 1
    assert len(discrepancies) == 0  # Not in hard discrepancies
    assert len(results) == 1
    assert results[0].match_status == MatchStatus.PARTIAL_PAYMENT
    assert results[0].discrepancy_category == DiscrepancyCategory.NEEDS_REVIEW
    assert "allow_partial_payment=True" in results[0].message


def test_overpayment_disallowed_default_triggers_discrepancy(base_config: AggregationConfig):
    """Default allow_overpayment=False: overpayment triggers field_mismatch discrepancy."""
    base_config.allow_overpayment = False
    parents = [(1, {"inv_id": "INV-OVER", "total": 300.00})]
    children = [(1, {"inv_id": "INV-OVER", "amount": 350.00, "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.field_mismatches == 1
    assert summary.needs_review_records == 0
    assert len(discrepancies) == 1
    assert discrepancies[0].match_status == MatchStatus.OVERPAYMENT


def test_overpayment_allowed_triggers_non_fatal_review(base_config: AggregationConfig):
    """allow_overpayment=True: overpayment is treated as non-fatal warning/review item."""
    base_config.allow_overpayment = True
    parents = [(1, {"inv_id": "INV-OVER-PERMIT", "total": 300.00})]
    children = [(1, {"inv_id": "INV-OVER-PERMIT", "amount": 350.00, "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.field_mismatches == 0
    assert summary.needs_review_records == 1
    assert len(discrepancies) == 0
    assert len(results) == 1
    assert results[0].match_status == MatchStatus.OVERPAYMENT
    assert results[0].discrepancy_category == DiscrepancyCategory.NEEDS_REVIEW
    assert "allow_overpayment=True" in results[0].message


def test_within_numeric_tolerance_remains_identical(base_config: AggregationConfig):
    """Within numeric tolerance evaluates to IDENTICAL regardless of policy flags."""
    base_config.numeric_tolerance = 5.0
    parents = [(1, {"inv_id": "INV-TOL", "total": 100.00})]
    children = [(1, {"inv_id": "INV-TOL", "amount": 98.00, "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.identical_matches == 1
    assert summary.field_mismatches == 0
    assert len(discrepancies) == 0
    assert results[0].match_status == MatchStatus.IDENTICAL


# ==============================================================================
# Batch C2 — Summary Duplicate Metric Counters Consistency
# ==============================================================================


def test_summary_duplicate_counters_consistency(base_config: AggregationConfig):
    """Mixed test with duplicate parent keys, duplicate receipts, and orphans."""
    parents = [
        (1, {"inv_id": "INV-DUP", "total": 100.00}),
        (2, {"inv_id": "INV-DUP", "total": 100.00}),
        (3, {"inv_id": "INV-UNIQUE", "total": 200.00}),
    ]
    children = [
        # Children for INV-DUP (cannot be allocated)
        (1, {"inv_id": "INV-DUP", "amount": 100.00, "rec_id": "R-1"}),
        # Children for INV-UNIQUE (has intra-parent duplicate receipt R-DUP)
        (2, {"inv_id": "INV-UNIQUE", "amount": 100.00, "rec_id": "R-DUP"}),
        (3, {"inv_id": "INV-UNIQUE", "amount": 100.00, "rec_id": "R-DUP"}),
        # Orphan child
        (4, {"inv_id": "INV-ORPHAN", "amount": 50.00, "rec_id": "R-99"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.total_source_records == 3
    assert summary.total_target_records == 4
    assert summary.duplicate_source_records == 2
    assert summary.duplicate_source_keys_count == 1
    assert summary.conflicting_duplicate_records == 1
    assert summary.duplicate_target_records == 2
    assert summary.duplicate_target_keys_count == 1
    assert summary.unmatched_target_records == 1
    assert summary.total_discrepancies == len(discrepancies)


# ==============================================================================
# Audit Remediation Tests: Findings F-01 through F-05
# ==============================================================================


def test_duplicate_receipt_involving_orphan_records(base_config: AggregationConfig):
    """F-01: Receipt collision involving an orphan child record and a matched child record."""
    parents = [(1, {"inv_id": "INV-1", "total": 100.00})]
    children = [
        (1, {"inv_id": "INV-1", "amount": 100.00, "rec_id": "REC-SHARED-ORPHAN"}),
        # Orphan child has identical receipt ID
        (2, {"inv_id": "INV-GHOST", "amount": 50.00, "rec_id": "REC-SHARED-ORPHAN"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.duplicate_target_records == 2
    assert summary.duplicate_target_keys_count == 1

    # Matched parent has duplicate receipt detected
    parent_item = next(r for r in results if r.key_values.get("inv_id") == "INV-1")
    assert parent_item.match_status == MatchStatus.DUPLICATE_RECEIPT
    assert any(fd.difference_type == "duplicate_receipt" for fd in parent_item.field_differences)

    # Orphan record retains UNMATCHED_SPLIT_RECORD classification while carrying duplicate receipt evidence
    orphan_item = next(r for r in results if r.key_values.get("inv_id") == "INV-GHOST")
    assert orphan_item.match_status == MatchStatus.UNMATCHED_SPLIT_RECORD
    assert any(fd.difference_type == "duplicate_receipt" for fd in orphan_item.field_differences)


def test_duplicate_receipt_involving_null_key_children(base_config: AggregationConfig):
    """F-01: Receipt collision involving an unlinked/null-key child record."""
    parents = [(1, {"inv_id": "INV-1", "total": 100.00})]
    children = [
        (1, {"inv_id": "INV-1", "amount": 100.00, "rec_id": "REC-NULL-COLLIDE"}),
        # Null-key child shares receipt ID
        (2, {"inv_id": None, "amount": 25.00, "rec_id": "REC-NULL-COLLIDE"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.duplicate_target_records == 2
    assert summary.duplicate_target_keys_count == 1

    null_key_item = next(r for r in results if r.reason_code == ReasonCode.NULL_KEY)
    assert null_key_item.match_status == MatchStatus.NEEDS_REVIEW
    assert any(fd.difference_type == "duplicate_receipt" for fd in null_key_item.field_differences)


def test_duplicate_receipt_involving_duplicate_parent_children(base_config: AggregationConfig):
    """F-01: Children under duplicate parent keys with receipt collision."""
    parents = [
        (1, {"inv_id": "INV-DUP", "total": 100.00}),
        (2, {"inv_id": "INV-DUP", "total": 100.00}),
    ]
    children = [
        (1, {"inv_id": "INV-DUP", "amount": 50.00, "rec_id": "REC-COLLIDE"}),
        (2, {"inv_id": "INV-DUP", "amount": 50.00, "rec_id": "REC-COLLIDE"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.duplicate_target_records == 2
    assert summary.duplicate_target_keys_count == 1

    ambig_items = [r for r in results if r.match_status == MatchStatus.AMBIGUOUS_DUPLICATE]
    assert len(ambig_items) == 2
    for item in ambig_items:
        assert any(fd.difference_type == "duplicate_receipt" for fd in item.field_differences)


def test_simultaneous_invalid_amount_and_duplicate_receipt(base_config: AggregationConfig):
    """F-01, F-05: Record with BOTH invalid amount and duplicate receipt preserves both findings."""
    parents = [(1, {"inv_id": "INV-MULTI", "total": "INVALID_AMT"})]
    children = [
        (1, {"inv_id": "INV-MULTI", "amount": 50.00, "rec_id": "R-DUP-MULTI"}),
        (2, {"inv_id": "INV-MULTI", "amount": 50.00, "rec_id": "R-DUP-MULTI"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.field_mismatches == 1
    item = next(r for r in results if r.key_values.get("inv_id") == "INV-MULTI")
    diff_types = {fd.difference_type for fd in item.field_differences}
    assert "invalid_numeric_amount" in diff_types
    assert "duplicate_receipt" in diff_types


def test_unmatched_parent_invalid_amount_no_double_counting(base_config: AggregationConfig):
    """F-02: Unmatched parent with invalid amount increments unmatched_source_records, not field_mismatches."""
    parents = [(1, {"inv_id": "INV-NO-CHILD-INVALID", "total": "N/A"})]
    children = []

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    assert summary.unmatched_source_records == 1
    assert summary.field_mismatches == 0  # No double counting
    assert len(discrepancies) == 1
    assert any(fd.difference_type == "invalid_numeric_amount" for fd in discrepancies[0].field_differences)


def test_orphan_and_null_key_invalid_amount_evidence(base_config: AggregationConfig):
    """F-02: Orphan child and null-key child with unparseable amounts retain raw value evidence."""
    parents = []
    children = [
        (1, {"inv_id": "INV-GHOST", "amount": "CORRUPT_ORPHAN", "rec_id": "R1"}),
        (2, {"inv_id": None, "amount": "CORRUPT_NULL", "rec_id": "R2"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
    )

    orphan = next(r for r in results if r.match_status == MatchStatus.UNMATCHED_SPLIT_RECORD)
    assert any(fd.difference_type == "invalid_numeric_amount" and fd.target_value == "CORRUPT_ORPHAN" for fd in orphan.field_differences)

    null_key = next(r for r in results if r.reason_code == ReasonCode.NULL_KEY)
    assert any(fd.difference_type == "invalid_numeric_amount" and fd.target_value == "CORRUPT_NULL" for fd in null_key.field_differences)


def test_simultaneous_amount_variance_and_date_window_violation(base_config: AggregationConfig):
    """F-03, F-04: Amount variance AND date window exceeded are both retained in field_differences."""
    base_config.parent_date_field = "order_date"
    base_config.child_date_field = "pay_date"
    rule = DateWindowRule(
        source_date_field="order_date",
        target_date_field="pay_date",
        lag_days_before=0,
        lag_days_after=2,
    )

    parents = [(1, {"inv_id": "INV-SIMUL", "total": 500.00, "order_date": "2026-03-01"})]
    # Sum is 450 (underpayment) AND date is 2026-03-10 (exceeded lag of 2 days)
    children = [(1, {"inv_id": "INV-SIMUL", "amount": 450.00, "pay_date": "2026-03-10", "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
        date_window_rules=[rule],
    )

    assert summary.field_mismatches == 1  # Single count
    item = discrepancies[0]
    diff_types = {fd.difference_type for fd in item.field_differences}
    assert "aggregation_amount_mismatch" in diff_types
    assert "date_window_exceeded" in diff_types


def test_multiple_installments_identifies_exact_offending_date_row(base_config: AggregationConfig):
    """F-04: Multiple child installments: identifies the exact row that exceeded lag."""
    base_config.parent_date_field = "order_date"
    base_config.child_date_field = "pay_date"
    rule = DateWindowRule(
        source_date_field="order_date",
        target_date_field="pay_date",
        lag_days_before=0,
        lag_days_after=3,
    )

    parents = [(1, {"inv_id": "INV-MULTI-DATES", "total": 300.00, "order_date": "2026-03-01"})]
    children = [
        # Row 1: On-time (2026-03-02, lag 1)
        (1, {"inv_id": "INV-MULTI-DATES", "amount": 100.00, "pay_date": "2026-03-02", "rec_id": "R1"}),
        # Row 2: Late (2026-03-15, lag 14) -> OFFENDER
        (2, {"inv_id": "INV-MULTI-DATES", "amount": 100.00, "pay_date": "2026-03-15", "rec_id": "R2"}),
        # Row 3: On-time (2026-03-03, lag 2)
        (3, {"inv_id": "INV-MULTI-DATES", "amount": 100.00, "pay_date": "2026-03-03", "rec_id": "R3"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
        date_window_rules=[rule],
    )

    assert summary.field_mismatches == 1
    item = discrepancies[0]
    date_diffs = [fd for fd in item.field_differences if fd.difference_type == "date_window_exceeded"]
    assert len(date_diffs) == 1
    assert "row 2" in date_diffs[0].message
    assert date_diffs[0].target_value == "2026-03-15"
    assert date_diffs[0].source_value == "2026-03-01"


def test_single_record_multiple_violations_no_double_counting(base_config: AggregationConfig):
    """F-02: Record with amount mismatch, duplicate receipt, and date window violation increments field_mismatches exactly once."""
    base_config.parent_date_field = "order_date"
    base_config.child_date_field = "pay_date"
    rule = DateWindowRule(source_date_field="order_date", target_date_field="pay_date", lag_days_after=2)

    parents = [(1, {"inv_id": "INV-TRIPLE-ERR", "total": 1000.00, "order_date": "2026-03-01"})]
    children = [
        # Duplicate receipt + late date + underpayment sum (100+100=200 vs 1000)
        (1, {"inv_id": "INV-TRIPLE-ERR", "amount": 100.00, "pay_date": "2026-03-20", "rec_id": "R-TRIPLE"}),
        (2, {"inv_id": "INV-TRIPLE-ERR", "amount": 100.00, "pay_date": "2026-03-20", "rec_id": "R-TRIPLE"}),
    ]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
        date_window_rules=[rule],
    )

    # Exactly ONE matched record with differences
    assert summary.field_mismatches == 1
    assert summary.records_with_differences == 1
    assert summary.total_discrepancies == 1

    item = discrepancies[0]
    diff_types = {fd.difference_type for fd in item.field_differences}
    assert "duplicate_receipt" in diff_types
    assert "aggregation_amount_mismatch" in diff_types
    assert "date_window_exceeded" in diff_types


def test_permitted_partial_payment_with_date_window_violation_becomes_hard_discrepancy(base_config: AggregationConfig):
    """F-03: allow_partial_payment=True does NOT suppress hard discrepancy if date window is violated."""
    base_config.allow_partial_payment = True
    base_config.parent_date_field = "order_date"
    base_config.child_date_field = "pay_date"
    rule = DateWindowRule(source_date_field="order_date", target_date_field="pay_date", lag_days_after=2)

    parents = [(1, {"inv_id": "INV-PERMIT-BUT-LATE", "total": 500.00, "order_date": "2026-03-01"})]
    # Sum is 400 (permitted partial) BUT date is late (2026-03-10)
    children = [(1, {"inv_id": "INV-PERMIT-BUT-LATE", "amount": 400.00, "pay_date": "2026-03-10", "rec_id": "R1"})]

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=base_config,
        date_window_rules=[rule],
    )

    # Becomes hard discrepancy because of date window violation
    assert summary.field_mismatches == 1
    assert len(discrepancies) == 1
    item = discrepancies[0]
    diff_types = {fd.difference_type for fd in item.field_differences}
    assert "aggregation_amount_variance" in diff_types
    assert "date_window_exceeded" in diff_types
