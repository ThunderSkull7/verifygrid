"""Aggregation and Split-Payment Reconciliation Engine (Batch 4 & PR #3 Remediation).

Supports one-to-many (1:N) and many-to-one (N:1) reconciliation between parent
invoices/orders and child settlement/installment receipts, with receipt-level lineage,
duplicate-aware parent key grouping, dataset-wide receipt collision detection,
strict financial amount validation without silent zero coercion, non-fatal variance
policy handling, comprehensive multi-violation evidence collection, and single-count
summary semantics.
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
    """Executes 1:N split payment reconciliation.

    Groups child installments by parent linking key, compares aggregate sums against
    parent order amounts, detects duplicate parent keys, tracks dataset-wide duplicate
    receipt IDs across parent boundaries, enforces date windows, validates numeric
    monetary fields without silent zero coercion, and supports non-fatal partial
    payment and overpayment policies while preserving independent findings for multi-violation records.
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

    # --------------------------------------------------------------------------
    # 1. Index parent records by parent_key (Duplicate-aware grouping)
    # --------------------------------------------------------------------------
    parents_by_key: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    null_key_parents: List[Tuple[int, Dict[str, Any]]] = []

    for r_num, rec in parent_records:
        k = rec.get(parent_key_col)
        if k is None or str(k).strip() == "":
            null_key_parents.append((r_num, rec))
        else:
            parents_by_key[str(k).strip()].append((r_num, rec))

    # --------------------------------------------------------------------------
    # 2. Group child records by linking parent key & build dataset-wide receipt registry
    # --------------------------------------------------------------------------
    children_by_parent_key: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    null_key_children: List[Tuple[int, Dict[str, Any]]] = []
    # Dataset-wide receipt registry: receipt_id -> list of (parent_norm_key, child_row_number)
    # Blank or NULL receipt IDs are NOT indexed (missing receipt IDs are not collisions).
    global_receipt_registry: Dict[str, List[Tuple[Optional[str], int]]] = defaultdict(list)

    for r_num, rec in child_records:
        k = rec.get(child_group_col)
        rec_id = rec.get(receipt_id_col) if receipt_id_col else None
        rec_id_str = str(rec_id).strip() if rec_id is not None and str(rec_id).strip() != "" else None

        if k is None or str(k).strip() == "":
            null_key_children.append((r_num, rec))
            if rec_id_str:
                global_receipt_registry[rec_id_str].append((None, r_num))
        else:
            norm_k = str(k).strip()
            children_by_parent_key[norm_k].append((r_num, rec))
            if rec_id_str:
                global_receipt_registry[rec_id_str].append((norm_k, r_num))

    # Identify duplicate child receipts across the entire dataset (including orphans and null-keys)
    duplicate_receipt_ids: Dict[str, List[Tuple[Optional[str], int]]] = {
        rid: occ for rid, occ in global_receipt_registry.items() if len(occ) > 1
    }

    # Summary metric counters
    identical_matches = 0
    field_mismatches = 0
    needs_review_records = 0
    unmatched_source_records = 0
    unmatched_target_records = 0
    matched_records = 0
    conflicting_duplicate_records = 0

    duplicate_source_keys = {k: v for k, v in parents_by_key.items() if len(v) > 1}
    duplicate_source_keys_count = len(duplicate_source_keys)
    duplicate_source_records = sum(len(v) for v in duplicate_source_keys.values())

    duplicate_target_keys_count = len(duplicate_receipt_ids)
    duplicate_target_records = sum(len(occ) for occ in duplicate_receipt_ids.values())

    evaluated_parent_keys: Set[str] = set()

    # --------------------------------------------------------------------------
    # 3. Process null-key parent records
    # --------------------------------------------------------------------------
    for p_row, p_rec in null_key_parents:
        unmatched_source_records += 1
        needs_review_records += 1
        raw_p_amt = p_rec.get(parent_amt_col)
        p_amt = clean_numeric(raw_p_amt)
        f_diffs: List[FieldDifference] = []
        if p_amt is None:
            f_diffs.append(
                FieldDifference(
                    field_name=parent_amt_col,
                    source_field=parent_amt_col,
                    target_field=child_amt_col,
                    source_value=raw_p_amt,
                    target_value=None,
                    difference_type="invalid_numeric_amount",
                    message=f"Parent record (row {p_row}) amount '{raw_p_amt}' is missing or invalid numeric value.",
                )
            )

        item = VerificationResultItem(
            key_values={parent_key_col: None},
            match_status=MatchStatus.NEEDS_REVIEW,
            discrepancy_category=DiscrepancyCategory.NEEDS_REVIEW,
            reason_code=ReasonCode.NULL_KEY,
            confidence_score=0.0,
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
            expected_amount=p_amt,
            field_differences=f_diffs,
            message=f"Parent record (row {p_row}) has missing or blank key '{parent_key_col}'.",
        )
        discrepancies.append(item)
        results.append(item)

    # --------------------------------------------------------------------------
    # 4. Process duplicate parent keys (Never silently overwrite or assign children)
    # --------------------------------------------------------------------------
    for norm_k, p_list in duplicate_source_keys.items():
        evaluated_parent_keys.add(norm_k)
        p_row_nums = [r[0] for r in p_list]
        child_group = children_by_parent_key.get(norm_k, [])

        # Emit an item for each parent row sharing this duplicate key
        for p_row, p_rec in p_list:
            raw_amt = p_rec.get(parent_amt_col)
            exp_amt = clean_numeric(raw_amt)
            p_diffs: List[FieldDifference] = []
            if exp_amt is None:
                p_diffs.append(
                    FieldDifference(
                        field_name=parent_amt_col,
                        source_field=parent_amt_col,
                        target_field=child_amt_col,
                        source_value=raw_amt,
                        target_value=None,
                        difference_type="invalid_numeric_amount",
                        message=f"Parent record (row {p_row}) amount '{raw_amt}' is missing or invalid numeric value.",
                    )
                )

            item = VerificationResultItem(
                key_values={parent_key_col: norm_k},
                match_status=MatchStatus.DUPLICATE_KEY_SOURCE,
                discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                reason_code=ReasonCode.DUPLICATE_KEY_SOURCE,
                confidence_score=0.0,
                source_row_indices={p_alias: p_row, c_alias: None},
                source_records={p_alias: p_rec, c_alias: None},
                missing_in_sources=[c_alias] if not child_group else [],
                source_presence={p_alias: True, c_alias: bool(child_group)},
                source_row_number=p_row,
                source_row_numbers=p_row_nums,
                target_row_number=None,
                source_record=p_rec,
                target_record=None,
                child_records=[],
                aggregated_amount=0.0,
                expected_amount=exp_amt,
                field_differences=p_diffs,
                message=(
                    f"Duplicate matching key '{norm_k}' in source across {len(p_list)} rows {p_row_nums}."
                    + (" No child payments found." if not child_group else f" {len(child_group)} child payment(s) cannot be unambiguously allocated.")
                ),
            )
            discrepancies.append(item)
            results.append(item)

        # Never allocate child payments to an ambiguous duplicate parent, but retain receipt & amount evidence
        if child_group:
            for c_row, c_rec in child_group:
                conflicting_duplicate_records += 1
                c_raw_amt = c_rec.get(child_amt_col)
                c_amt = clean_numeric(c_raw_amt)
                rec_id = c_rec.get(receipt_id_col) if receipt_id_col else None
                rec_id_str = str(rec_id).strip() if rec_id is not None and str(rec_id).strip() != "" else None

                c_diffs: List[FieldDifference] = []
                if c_amt is None:
                    c_diffs.append(
                        FieldDifference(
                            field_name=child_amt_col,
                            source_field=parent_amt_col,
                            target_field=child_amt_col,
                            source_value=None,
                            target_value=c_raw_amt,
                            difference_type="invalid_numeric_amount",
                            message=f"Child installment (row {c_row}) amount '{c_raw_amt}' is missing or invalid numeric value.",
                        )
                    )

                if rec_id_str and rec_id_str in duplicate_receipt_ids:
                    occ = duplicate_receipt_ids[rec_id_str]
                    occ_rows = [r for _, r in occ]
                    c_diffs.append(
                        FieldDifference(
                            field_name=receipt_id_col or "receipt_id",
                            source_field=parent_key_col,
                            target_field=receipt_id_col or child_group_col,
                            source_value=norm_k,
                            target_value=f"DUPLICATE_RECEIPT:{rec_id_str}",
                            difference_type="duplicate_receipt",
                            message=f"Receipt ID '{rec_id_str}' on child row {c_row} is duplicated across child rows {occ_rows}.",
                        )
                    )

                if parent_date_col and child_date_col and date_window_rules:
                    c_dt_val = c_rec.get(child_date_col)
                    if c_dt_val is None or str(c_dt_val).strip() == "":
                        c_diffs.append(
                            FieldDifference(
                                field_name=child_date_col,
                                source_field=parent_date_col,
                                target_field=child_date_col,
                                source_value=None,
                                target_value=c_dt_val,
                                difference_type="missing_date",
                                message=f"Child installment (row {c_row}) is missing required date value in '{child_date_col}' for settlement date window validation.",
                            )
                        )

                item = VerificationResultItem(
                    key_values={child_group_col: norm_k},
                    match_status=MatchStatus.AMBIGUOUS_DUPLICATE,
                    discrepancy_category=DiscrepancyCategory.DUPLICATE_KEY,
                    reason_code=ReasonCode.AMBIGUOUS_DUPLICATE,
                    confidence_score=0.0,
                    source_row_indices={p_alias: None, c_alias: c_row},
                    source_records={p_alias: None, c_alias: c_rec},
                    missing_in_sources=[],
                    source_presence={p_alias: True, c_alias: True},
                    source_row_number=None,
                    source_row_numbers=p_row_nums,
                    target_row_number=c_row,
                    target_row_numbers=[c_row],
                    source_record=None,
                    target_record=c_rec,
                    child_records=[{
                        "source_row": c_row,
                        "receipt_id": rec_id_str,
                        "amount": c_amt,
                        "raw_amount": c_raw_amt,
                        "record": c_rec,
                    }],
                    aggregated_amount=c_amt,
                    expected_amount=None,
                    field_differences=c_diffs,
                    message=(
                        f"Child payment installment (row {c_row}) cannot be allocated: parent key '{norm_k}' "
                        f"is duplicated across {len(p_list)} parent rows {p_row_nums}."
                    ),
                )
                discrepancies.append(item)
                results.append(item)

    # --------------------------------------------------------------------------
    # 5. Process unique parent records
    # --------------------------------------------------------------------------
    for norm_k, p_list in parents_by_key.items():
        if len(p_list) != 1:
            continue

        evaluated_parent_keys.add(norm_k)
        p_row, p_rec = p_list[0]

        raw_expected_amt = p_rec.get(parent_amt_col)
        expected_amt = clean_numeric(raw_expected_amt)
        has_invalid_parent_amt = (expected_amt is None)

        child_group = children_by_parent_key.get(norm_k, [])

        if not child_group:
            # Unmatched parent order: zero installments received
            unmatched_source_records += 1
            f_diffs = []
            if has_invalid_parent_amt:
                f_diffs.append(
                    FieldDifference(
                        field_name=parent_amt_col,
                        source_field=parent_amt_col,
                        target_field=child_amt_col,
                        source_value=raw_expected_amt,
                        target_value=None,
                        difference_type="invalid_numeric_amount",
                        message=f"Parent amount '{raw_expected_amt}' is missing or invalid numeric value.",
                    )
                )

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
                field_differences=f_diffs,
                message=f"Parent order '{norm_k}' has no matching payment installments in {c_alias}.",
            )
            discrepancies.append(item)
            results.append(item)
            continue

        matched_records += 1

        # ----------------------------------------------------------------------
        # Multi-violation evidence evaluation across amounts, receipts, and dates
        # ----------------------------------------------------------------------
        child_lineage: List[Dict[str, Any]] = []
        child_sum = 0.0
        has_invalid_child_amt = False
        duplicate_receipt_detected = False
        duplicate_receipt_details: List[str] = []
        date_window_violation = False
        date_window_error = False

        record_field_differences: List[FieldDifference] = []

        # 5.1 Parent Amount Validity
        if has_invalid_parent_amt:
            record_field_differences.append(
                FieldDifference(
                    field_name=parent_amt_col,
                    source_field=parent_amt_col,
                    target_field=child_amt_col,
                    source_value=raw_expected_amt,
                    target_value=None,
                    difference_type="invalid_numeric_amount",
                    message=f"Parent amount '{raw_expected_amt}' is missing or invalid numeric value.",
                )
            )

        # 5.2 Date Window: Parent Date Check
        p_dt_val = p_rec.get(parent_date_col) if parent_date_col else None
        p_dt_blank = (p_dt_val is None or str(p_dt_val).strip() == "")
        if parent_date_col and child_date_col and date_window_rules and p_dt_blank:
            date_window_error = True
            record_field_differences.append(
                FieldDifference(
                    field_name=parent_date_col,
                    source_field=parent_date_col,
                    target_field=child_date_col,
                    source_value=p_dt_val,
                    target_value=None,
                    difference_type="missing_date",
                    message=f"Settlement date-window validation cannot be completed for order '{norm_k}': parent date column '{parent_date_col}' is missing or blank.",
                )
            )

        # 5.3 Iterate Child Installments
        for c_row, c_rec in child_group:
            raw_c_amt = c_rec.get(child_amt_col)
            installment_amt = clean_numeric(raw_c_amt)
            if installment_amt is None:
                has_invalid_child_amt = True
                record_field_differences.append(
                    FieldDifference(
                        field_name=child_amt_col,
                        source_field=parent_amt_col,
                        target_field=child_amt_col,
                        source_value=expected_amt,
                        target_value=raw_c_amt,
                        difference_type="invalid_numeric_amount",
                        message=f"Child installment (row {c_row}) amount '{raw_c_amt}' is missing or invalid numeric value.",
                    )
                )
            else:
                child_sum += installment_amt

            rec_id = c_rec.get(receipt_id_col) if receipt_id_col else None
            rec_id_str = str(rec_id).strip() if rec_id is not None and str(rec_id).strip() != "" else None

            # Dataset-wide duplicate receipt detection
            if rec_id_str and rec_id_str in duplicate_receipt_ids:
                duplicate_receipt_detected = True
                occurrences = duplicate_receipt_ids[rec_id_str]
                parents_sharing = {p for p, _ in occurrences}
                occ_rows = [r for _, r in occurrences]
                if len(parents_sharing) > 1:
                    parents_str = sorted([str(x) for x in parents_sharing])
                    msg_detail = f"Receipt ID '{rec_id_str}' on child row {c_row} is duplicated across multiple parent orders {parents_str} (rows {occ_rows})"
                else:
                    msg_detail = f"Receipt ID '{rec_id_str}' on child row {c_row} is duplicated across child rows {occ_rows} for parent '{norm_k}'"

                duplicate_receipt_details.append(msg_detail)
                record_field_differences.append(
                    FieldDifference(
                        field_name="receipt_id",
                        source_field=parent_key_col,
                        target_field=receipt_id_col or child_group_col,
                        source_value=norm_k,
                        target_value=f"DUPLICATE_RECEIPT:{rec_id_str}",
                        difference_type="duplicate_receipt",
                        message=msg_detail,
                    )
                )

            child_info = {
                "source_row": c_row,
                "receipt_id": rec_id_str,
                "amount": installment_amt,
                "raw_amount": raw_c_amt,
                "record": c_rec,
            }
            child_lineage.append(child_info)

            # Date window check for each installment
            if parent_date_col and child_date_col and date_window_rules:
                c_dt_val = c_rec.get(child_date_col)
                c_dt_blank = (c_dt_val is None or str(c_dt_val).strip() == "")
                if c_dt_blank:
                    date_window_error = True
                    record_field_differences.append(
                        FieldDifference(
                            field_name=child_date_col,
                            source_field=parent_date_col,
                            target_field=child_date_col,
                            source_value=p_dt_val,
                            target_value=c_dt_val,
                            difference_type="missing_date",
                            message=f"Child installment (row {c_row}) is missing required date value in '{child_date_col}' for settlement date window validation.",
                        )
                    )
                elif not p_dt_blank:
                    for dw in date_window_rules:
                        passed, d_msg = evaluate_date_window(p_dt_val, c_dt_val, dw)
                        if not passed:
                            date_window_violation = True
                            record_field_differences.append(
                                FieldDifference(
                                    field_name=child_date_col,
                                    source_field=parent_date_col,
                                    target_field=child_date_col,
                                    source_value=p_dt_val,
                                    target_value=c_dt_val,
                                    difference_type="date_window_exceeded",
                                    message=f"Child installment (row {c_row}): {d_msg}",
                                )
                            )

        child_sum = round(child_sum, 4)
        child_row_indices = [c["source_row"] for c in child_lineage]

        # 5.4 Monetary Amount Tolerance / Variance Check
        amount_mismatch_detected = False
        is_partial = False
        is_permitted_variance = False
        amt_diff_msg = ""

        if not (has_invalid_parent_amt or has_invalid_child_amt):
            abs_diff = abs(expected_amt - child_sum)
            base_denom = max(abs(expected_amt), 1e-9)
            pct_diff = (abs_diff / base_denom) * 100.0

            within_tolerance = (
                abs_diff <= config.numeric_tolerance
                or pct_diff <= config.percentage_tolerance
            )

            if not within_tolerance:
                amount_mismatch_detected = True
                if child_sum < expected_amt:
                    is_partial = True
                    is_permitted_variance = config.allow_partial_payment
                    amt_diff_msg = f"Partial payment: sum of installments {child_sum} is less than order amount {expected_amt} (short by {abs_diff:.2f})."
                else:
                    is_partial = False
                    is_permitted_variance = config.allow_overpayment
                    amt_diff_msg = f"Overpayment: sum of installments {child_sum} exceeds order amount {expected_amt} (excess of {abs_diff:.2f})."

                diff_type = "aggregation_amount_variance" if is_permitted_variance else "aggregation_amount_mismatch"
                record_field_differences.append(
                    FieldDifference(
                        field_name=parent_amt_col,
                        source_field=parent_amt_col,
                        target_field=child_amt_col,
                        source_value=expected_amt,
                        target_value=child_sum,
                        difference_type=diff_type,
                        message=amt_diff_msg,
                    )
                )

        # ----------------------------------------------------------------------
        # Classification & Single-Count Summary Recording
        # ----------------------------------------------------------------------
        if not record_field_differences:
            # Case 1: Exact or Within-Tolerance Match (No differences)
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

        elif len(record_field_differences) == 1 and record_field_differences[0].difference_type == "aggregation_amount_variance":
            # Case 2: Pure Permitted Variance Policy (Non-fatal review item, no other violations)
            needs_review_records += 1
            status = MatchStatus.PARTIAL_PAYMENT if is_partial else MatchStatus.OVERPAYMENT
            reason = ReasonCode.PARTIAL_PAYMENT if is_partial else ReasonCode.OVERPAYMENT
            flag_str = "allow_partial_payment=True" if is_partial else "allow_overpayment=True"
            msg = f"Permitted variance ({flag_str}): {amt_diff_msg}"
            item = VerificationResultItem(
                key_values={parent_key_col: norm_k},
                match_status=status,
                discrepancy_category=DiscrepancyCategory.NEEDS_REVIEW,
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
                field_differences=record_field_differences,
                message=msg,
            )
            results.append(item)

        else:
            # Case 3: Hard Discrepancy (Increments field_mismatches exactly ONCE per record)
            field_mismatches += 1

            # Determine primary status taxonomy while preserving all differences in evidence
            if duplicate_receipt_detected:
                primary_status = MatchStatus.DUPLICATE_RECEIPT
                primary_category = DiscrepancyCategory.AGGREGATION_MISMATCH
                primary_reason = ReasonCode.DUPLICATE_RECEIPT
            elif has_invalid_parent_amt or has_invalid_child_amt:
                primary_status = MatchStatus.FIELD_MISMATCH
                primary_category = DiscrepancyCategory.FIELD_MISMATCH
                primary_reason = ReasonCode.FIELD_MISMATCH
            elif amount_mismatch_detected and not is_permitted_variance:
                primary_status = MatchStatus.PARTIAL_PAYMENT if is_partial else MatchStatus.OVERPAYMENT
                primary_category = DiscrepancyCategory.AGGREGATION_MISMATCH
                primary_reason = ReasonCode.PARTIAL_PAYMENT if is_partial else ReasonCode.OVERPAYMENT
            elif date_window_error or date_window_violation:
                primary_status = MatchStatus.FIELD_MISMATCH
                primary_category = DiscrepancyCategory.RULE_VIOLATION
                primary_reason = ReasonCode.DATE_WINDOW_EXCEEDED
            else:
                primary_status = MatchStatus.FIELD_MISMATCH
                primary_category = DiscrepancyCategory.FIELD_MISMATCH
                primary_reason = ReasonCode.FIELD_MISMATCH

            diff_msgs = [fd.message for fd in record_field_differences if fd.message]
            summary_msg = f"Order '{norm_k}' reconciliation differences: " + "; ".join(diff_msgs)

            item = VerificationResultItem(
                key_values={parent_key_col: norm_k},
                match_status=primary_status,
                discrepancy_category=primary_category,
                reason_code=primary_reason,
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
                aggregated_amount=child_sum if not has_invalid_child_amt else None,
                expected_amount=expected_amt,
                field_differences=record_field_differences,
                message=summary_msg,
            )
            discrepancies.append(item)
            results.append(item)

    # --------------------------------------------------------------------------
    # 6. Process null-key child records (Unlinked records: no magic string sentinel)
    # --------------------------------------------------------------------------
    for c_row, c_rec in null_key_children:
        unmatched_target_records += 1
        needs_review_records += 1
        c_raw_amt = c_rec.get(child_amt_col)
        c_amt = clean_numeric(c_raw_amt)
        rec_id = c_rec.get(receipt_id_col) if receipt_id_col else None
        rec_id_str = str(rec_id).strip() if rec_id is not None and str(rec_id).strip() != "" else None

        f_diffs = []
        if c_amt is None:
            f_diffs.append(
                FieldDifference(
                    field_name=child_amt_col,
                    source_field=parent_amt_col,
                    target_field=child_amt_col,
                    source_value=None,
                    target_value=c_raw_amt,
                    difference_type="invalid_numeric_amount",
                    message=f"Child installment (row {c_row}) amount '{c_raw_amt}' is missing or invalid numeric value.",
                )
            )

        if rec_id_str and rec_id_str in duplicate_receipt_ids:
            all_occ = duplicate_receipt_ids[rec_id_str]
            occ_rows = [r for _, r in all_occ]
            f_diffs.append(
                FieldDifference(
                    field_name=receipt_id_col or "receipt_id",
                    source_field=parent_key_col,
                    target_field=receipt_id_col or child_group_col,
                    source_value=None,
                    target_value=f"DUPLICATE_RECEIPT:{rec_id_str}",
                    difference_type="duplicate_receipt",
                    message=f"Receipt ID '{rec_id_str}' on unlinked child row {c_row} is duplicated across child rows {occ_rows}.",
                )
            )

        if parent_date_col and child_date_col and date_window_rules:
            c_dt_val = c_rec.get(child_date_col)
            if c_dt_val is None or str(c_dt_val).strip() == "":
                f_diffs.append(
                    FieldDifference(
                        field_name=child_date_col,
                        source_field=parent_date_col,
                        target_field=child_date_col,
                        source_value=None,
                        target_value=c_dt_val,
                        difference_type="missing_date",
                        message=f"Child installment (row {c_row}) is missing required date value in '{child_date_col}' for settlement date window validation.",
                    )
                )

        item = VerificationResultItem(
            key_values={child_group_col: None},
            match_status=MatchStatus.NEEDS_REVIEW,
            discrepancy_category=DiscrepancyCategory.NEEDS_REVIEW,
            reason_code=ReasonCode.NULL_KEY,
            confidence_score=0.0,
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
                "receipt_id": rec_id_str,
                "amount": c_amt,
                "raw_amount": c_raw_amt,
                "record": c_rec,
            }],
            aggregated_amount=c_amt,
            expected_amount=None,
            field_differences=f_diffs,
            message=f"Child payment installment (row {c_row}) has missing or blank linking key '{child_group_col}'.",
        )
        discrepancies.append(item)
        results.append(item)

    # --------------------------------------------------------------------------
    # 7. Process orphan child records (Non-empty foreign key referencing nonexistent parent)
    # --------------------------------------------------------------------------
    for c_norm_k, orphan_group in children_by_parent_key.items():
        if c_norm_k not in evaluated_parent_keys:
            unmatched_target_records += len(orphan_group)
            for c_row, c_rec in orphan_group:
                c_raw_amt = c_rec.get(child_amt_col)
                c_amt = clean_numeric(c_raw_amt)
                rec_id = c_rec.get(receipt_id_col) if receipt_id_col else None
                rec_id_str = str(rec_id).strip() if rec_id is not None and str(rec_id).strip() != "" else None

                f_diffs = []
                if c_amt is None:
                    f_diffs.append(
                        FieldDifference(
                            field_name=child_amt_col,
                            source_field=parent_amt_col,
                            target_field=child_amt_col,
                            source_value=None,
                            target_value=c_raw_amt,
                            difference_type="invalid_numeric_amount",
                            message=f"Child installment (row {c_row}) amount '{c_raw_amt}' is missing or invalid numeric value.",
                        )
                    )

                if rec_id_str and rec_id_str in duplicate_receipt_ids:
                    all_occ = duplicate_receipt_ids[rec_id_str]
                    occ_rows = [r for _, r in all_occ]
                    f_diffs.append(
                        FieldDifference(
                            field_name=receipt_id_col or "receipt_id",
                            source_field=parent_key_col,
                            target_field=receipt_id_col or child_group_col,
                            source_value=c_norm_k,
                            target_value=f"DUPLICATE_RECEIPT:{rec_id_str}",
                            difference_type="duplicate_receipt",
                            message=f"Receipt ID '{rec_id_str}' on orphan child row {c_row} is duplicated across child rows {occ_rows}.",
                        )
                    )

                if parent_date_col and child_date_col and date_window_rules:
                    c_dt_val = c_rec.get(child_date_col)
                    if c_dt_val is None or str(c_dt_val).strip() == "":
                        f_diffs.append(
                            FieldDifference(
                                field_name=child_date_col,
                                source_field=parent_date_col,
                                target_field=child_date_col,
                                source_value=None,
                                target_value=c_dt_val,
                                difference_type="missing_date",
                                message=f"Child installment (row {c_row}) is missing required date value in '{child_date_col}' for settlement date window validation.",
                            )
                        )

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
                        "receipt_id": rec_id_str,
                        "amount": c_amt,
                        "raw_amount": c_raw_amt,
                        "record": c_rec,
                    }],
                    aggregated_amount=c_amt,
                    expected_amount=None,
                    field_differences=f_diffs,
                    message=f"Orphan child payment installment (row {c_row}) references non-existent parent order '{c_norm_k}'.",
                )
                discrepancies.append(item)
                results.append(item)

    # --------------------------------------------------------------------------
    # 8. Build accurate VerificationSummary
    # --------------------------------------------------------------------------
    summary = VerificationSummary(
        total_source_records=len(parent_records),
        total_target_records=len(child_records),
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
        conflicting_duplicate_records=conflicting_duplicate_records,
        total_discrepancies=len(discrepancies),
        status="completed",
    )

    from app.services.materiality_engine import compute_record_materiality, compute_summary_materiality
    for r in results:
        compute_record_materiality(r)
    summary = compute_summary_materiality(results, discrepancies, summary)

    return summary, results, discrepancies
