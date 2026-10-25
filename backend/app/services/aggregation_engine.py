"""Aggregation and Split-Payment Reconciliation Engine (Batch 4).

Supports one-to-many (1:N) and many-to-one (N:1) reconciliation between parent
invoices/orders and child settlement/installment receipts, with receipt-level lineage.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.result import (
    DiscrepancyCategory,
    FieldDifference,
    MatchStatus,
    ReasonCode,
    VerificationResultItem,
    VerificationSummary,
)
from app.schemas.rule import AggregationConfig, DateWindowRule
from app.services.rule_engine import clean_numeric, evaluate_date_window


def reconcile_split_payments(
    parent_records: List[Tuple[int, Dict[str, Any]]],
    child_records: List[Tuple[int, Dict[str, Any]]],
    config: AggregationConfig,
    date_window_rules: Optional[List[DateWindowRule]] = None,
    include_identical: bool = True,
) -> Tuple[VerificationSummary, List[VerificationResultItem], List[VerificationResultItem]]:
    """
    Executes 1:N split payment reconciliation.
    Groups child installments by parent linking key, compares the aggregate sum against
    the parent order amount, detects duplicate receipts, and classifies partial payments,
    overpayments, and orphan child records with receipt-level lineage.
    """
    results: List[VerificationResultItem] = []
    discrepancies: List[VerificationResultItem] = []

    p_alias = config.parent_source_alias
    c_alias = config.child_source_alias
    parent_key_col = config.parent_key
    child_group_col = config.child_grouping_key
    parent_amt_col = config.parent_amount_field
    child_amt_col = config.child_amount_field
    receipt_id_col = config.child_receipt_id_field
    parent_date_col = config.parent_date_field
    child_date_col = config.child_date_field

    # 1. Index parent records by parent_key
    parents_by_key: Dict[str, Tuple[int, Dict[str, Any]]] = {}
    for r_num, rec in parent_records:
        k = rec.get(parent_key_col)
        if k is not None:
            norm_k = str(k).strip()
            parents_by_key[norm_k] = (r_num, rec)

    # 2. Group child records by linking parent key
    children_by_parent_key: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for r_num, rec in child_records:
        k = rec.get(child_group_col)
        norm_k = str(k).strip() if k is not None else "__ORPHAN__"
        children_by_parent_key[norm_k].append((r_num, rec))

    identical_matches = 0
    field_mismatches = 0
    unmatched_source_records = 0
    unmatched_target_records = 0
    matched_records = 0

    evaluated_parent_keys: Set[str] = set()

    # 3. Process each parent record
    for norm_k, (p_row, p_rec) in parents_by_key.items():
        evaluated_parent_keys.add(norm_k)
        expected_amt = clean_numeric(p_rec.get(parent_amt_col)) or 0.0

        child_group = children_by_parent_key.get(norm_k, [])

        if not child_group:
            # Unmatched parent order: zero installments received
            unmatched_source_records += 1
            item = VerificationResultItem(
                key_values={parent_key_col: norm_k},
                match_status=MatchStatus.MISSING_IN_TARGET,
                discrepancy_category=DiscrepancyCategory.MISSING_RECORD,
                reason_code=ReasonCode.MISSING_IN_TARGET,
                confidence_score=1.0,
                source_row_indices={p_alias: p_row, c_alias: None},
                source_records={p_alias: p_rec, c_alias: None},
                missing_in_sources=[c_alias],
                source_presence={p_alias: True, c_alias: False},
                source_row_number=p_row,
                target_row_number=None,
                source_record=p_rec,
                target_record=None,
                child_records=[],
                aggregated_amount=0.0,
                expected_amount=expected_amt,
                field_differences=[],
                message=f"Parent order '{norm_k}' has no matching payment installments in {c_alias}.",
            )
            discrepancies.append(item)
            results.append(item)
            continue

        matched_records += 1

        # Check for duplicate receipts within the child installment group
        duplicate_receipt_detected = False
        seen_receipts: Dict[str, int] = {}
        child_lineage: List[Dict[str, Any]] = []
        child_sum = 0.0
        date_window_violation = False
        date_window_msg: Optional[str] = None

        for c_row, c_rec in child_group:
            installment_amt = clean_numeric(c_rec.get(child_amt_col)) or 0.0
            child_sum += installment_amt
            rec_id = c_rec.get(receipt_id_col) if receipt_id_col else None
            rec_id_str = str(rec_id).strip() if rec_id is not None else None

            if rec_id_str:
                if rec_id_str in seen_receipts:
                    duplicate_receipt_detected = True
                else:
                    seen_receipts[rec_id_str] = c_row

            child_info = {
                "source_row": c_row,
                "receipt_id": rec_id_str,
                "amount": installment_amt,
                "record": c_rec,
            }
            child_lineage.append(child_info)

            # Date window check if configured
            if parent_date_col and child_date_col and date_window_rules:
                p_dt_val = p_rec.get(parent_date_col)
                c_dt_val = c_rec.get(child_date_col)
                if p_dt_val and c_dt_val:
                    for dw in date_window_rules:
                        passed, d_msg = evaluate_date_window(p_dt_val, c_dt_val, dw)
                        if not passed:
                            date_window_violation = True
                            date_window_msg = d_msg

        child_sum = round(child_sum, 4)
        abs_diff = abs(expected_amt - child_sum)
        base_denom = max(abs(expected_amt), 1e-9)
        pct_diff = (abs_diff / base_denom) * 100.0

        within_tolerance = (
            abs_diff <= config.numeric_tolerance
            or pct_diff <= config.percentage_tolerance
        )

        child_row_indices = [c["source_row"] for c in child_lineage]

        # Classification
        if duplicate_receipt_detected:
            field_mismatches += 1
            item = VerificationResultItem(
                key_values={parent_key_col: norm_k},
                match_status=MatchStatus.DUPLICATE_RECEIPT,
                discrepancy_category=DiscrepancyCategory.AGGREGATION_MISMATCH,
                reason_code=ReasonCode.DUPLICATE_RECEIPT,
                confidence_score=0.95,
                source_row_indices={p_alias: p_row, c_alias: child_row_indices[0]},
                source_records={p_alias: p_rec, c_alias: child_lineage[0]["record"]},
                missing_in_sources=[],
                source_presence={p_alias: True, c_alias: True},
                source_row_number=p_row,
                target_row_number=child_row_indices[0],
                target_row_numbers=child_row_indices,
                source_record=p_rec,
                target_record=child_lineage[0]["record"],
                child_records=child_lineage,
                aggregated_amount=child_sum,
                expected_amount=expected_amt,
                field_differences=[
                    FieldDifference(
                        field_name="receipt_id",
                        source_field=parent_key_col,
                        target_field=receipt_id_col or child_group_col,
                        source_value=norm_k,
                        target_value="DUPLICATE_RECEIPT_DETECTED",
                        difference_type="duplicate_receipt",
                    )
                ],
                message=f"Duplicate payment receipt ID detected across installments for order '{norm_k}'.",
            )
            discrepancies.append(item)
            results.append(item)

        elif not within_tolerance:
            field_mismatches += 1
            if child_sum < expected_amt:
                status = MatchStatus.PARTIAL_PAYMENT
                reason = ReasonCode.PARTIAL_PAYMENT
                msg = f"Partial payment: sum of installments {child_sum} is less than order amount {expected_amt} (short by {abs_diff:.2f})."
            else:
                status = MatchStatus.OVERPAYMENT
                reason = ReasonCode.OVERPAYMENT
                msg = f"Overpayment: sum of installments {child_sum} exceeds order amount {expected_amt} (excess of {abs_diff:.2f})."

            item = VerificationResultItem(
                key_values={parent_key_col: norm_k},
                match_status=status,
                discrepancy_category=DiscrepancyCategory.AGGREGATION_MISMATCH,
                reason_code=reason,
                confidence_score=0.9,
                source_row_indices={p_alias: p_row, c_alias: child_row_indices[0]},
                source_records={p_alias: p_rec, c_alias: child_lineage[0]["record"]},
                missing_in_sources=[],
                source_presence={p_alias: True, c_alias: True},
                source_row_number=p_row,
                target_row_number=child_row_indices[0],
                target_row_numbers=child_row_indices,
                source_record=p_rec,
                target_record=child_lineage[0]["record"],
                child_records=child_lineage,
                aggregated_amount=child_sum,
                expected_amount=expected_amt,
                field_differences=[
                    FieldDifference(
                        field_name=parent_amt_col,
                        source_field=parent_amt_col,
                        target_field=child_amt_col,
                        source_value=expected_amt,
                        target_value=child_sum,
                        difference_type="aggregation_amount_mismatch",
                    )
                ],
                message=msg,
            )
            discrepancies.append(item)
            results.append(item)

        elif date_window_violation:
            field_mismatches += 1
            item = VerificationResultItem(
                key_values={parent_key_col: norm_k},
                match_status=MatchStatus.FIELD_MISMATCH,
                discrepancy_category=DiscrepancyCategory.RULE_VIOLATION,
                reason_code=ReasonCode.DATE_WINDOW_EXCEEDED,
                confidence_score=0.85,
                source_row_indices={p_alias: p_row, c_alias: child_row_indices[0]},
                source_records={p_alias: p_rec, c_alias: child_lineage[0]["record"]},
                missing_in_sources=[],
                source_presence={p_alias: True, c_alias: True},
                source_row_number=p_row,
                target_row_number=child_row_indices[0],
                target_row_numbers=child_row_indices,
                source_record=p_rec,
                target_record=child_lineage[0]["record"],
                child_records=child_lineage,
                aggregated_amount=child_sum,
                expected_amount=expected_amt,
                field_differences=[
                    FieldDifference(
                        field_name=parent_date_col or "settlement_date",
                        source_field=parent_date_col or "order_date",
                        target_field=child_date_col or "payment_date",
                        source_value=p_rec.get(parent_date_col),
                        target_value=child_lineage[0]["record"].get(child_date_col),
                        difference_type="date_window_exceeded",
                    )
                ],
                message=date_window_msg or f"Installment payment date for order '{norm_k}' falls outside the allowed settlement lag window.",
            )
            discrepancies.append(item)
            results.append(item)

        else:
            # Exact or within-tolerance aggregate match
            identical_matches += 1
            item = VerificationResultItem(
                key_values={parent_key_col: norm_k},
                match_status=MatchStatus.IDENTICAL,
                discrepancy_category=DiscrepancyCategory.NONE,
                reason_code=ReasonCode.EXACT_MATCH,
                confidence_score=1.0,
                source_row_indices={p_alias: p_row, c_alias: child_row_indices[0]},
                source_records={p_alias: p_rec, c_alias: child_lineage[0]["record"]},
                missing_in_sources=[],
                source_presence={p_alias: True, c_alias: True},
                source_row_number=p_row,
                target_row_number=child_row_indices[0],
                target_row_numbers=child_row_indices,
                source_record=p_rec,
                target_record=child_lineage[0]["record"],
                child_records=child_lineage,
                aggregated_amount=child_sum,
                expected_amount=expected_amt,
                field_differences=[],
                message=f"All {len(child_lineage)} installment(s) sum to {child_sum}, matching parent order amount of {expected_amt}.",
            )
            if include_identical:
                results.append(item)

    # 4. Check for orphan child records (installment referencing non-existent parent order)
    for c_norm_k, orphan_group in children_by_parent_key.items():
        if c_norm_k not in evaluated_parent_keys:
            unmatched_target_records += len(orphan_group)
            for c_row, c_rec in orphan_group:
                c_amt = clean_numeric(c_rec.get(child_amt_col)) or 0.0
                rec_id = c_rec.get(receipt_id_col)
                item = VerificationResultItem(
                    key_values={child_group_col: c_norm_k},
                    match_status=MatchStatus.UNMATCHED_SPLIT_RECORD,
                    discrepancy_category=DiscrepancyCategory.AGGREGATION_MISMATCH,
                    reason_code=ReasonCode.UNMATCHED_SPLIT_RECORD,
                    confidence_score=1.0,
                    source_row_indices={p_alias: None, c_alias: c_row},
                    source_records={p_alias: None, c_alias: c_rec},
                    missing_in_sources=[p_alias],
                    source_presence={p_alias: False, c_alias: True},
                    source_row_number=None,
                    target_row_number=c_row,
                    source_record=None,
                    target_record=c_rec,
                    child_records=[{
                        "source_row": c_row,
                        "receipt_id": str(rec_id) if rec_id is not None else None,
                        "amount": c_amt,
                        "record": c_rec,
                    }],
                    aggregated_amount=c_amt,
                    expected_amount=None,
                    field_differences=[],
                    message=f"Orphan child payment installment (row {c_row}) references non-existent parent order '{c_norm_k}'.",
                )
                discrepancies.append(item)
                results.append(item)

    summary = VerificationSummary(
        total_source_records=len(parent_records),
        total_target_records=len(child_records),
        matched_records=matched_records,
        identical_matches=identical_matches,
        field_mismatches=field_mismatches,
        records_with_differences=field_mismatches,
        needs_review_records=0,
        unmatched_source_records=unmatched_source_records,
        unmatched_target_records=unmatched_target_records,
        duplicate_source_records=0,
        duplicate_target_records=0,
        duplicate_source_keys_count=0,
        duplicate_target_keys_count=0,
        conflicting_duplicate_records=0,
        total_discrepancies=len(discrepancies),
        status="completed",
    )

    return summary, results, discrepancies
