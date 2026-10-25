"""Unit and integration test suite for Versioned Rule Engine & Split-Payment Aggregation (Batch 4)."""

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas.result import MatchStatus, ReasonCode
from app.schemas.rule import (
    AggregationConfig,
    CompoundRule,
    DateWindowRule,
    NumericToleranceRule,
    PredicateOperator,
    RuleConjunction,
    RuleSeverity,
    StatusTransitionRule,
    ToleranceMode,
    VersionedRuleConfig,
    WhereCondition,
)
from app.services.aggregation_engine import reconcile_split_payments
from app.services.rule_engine import (
    evaluate_compound_rule,
    evaluate_date_window,
    evaluate_numeric_tolerance,
    evaluate_predicate,
    evaluate_status_transition,
    validate_rule_config,
)


@pytest.fixture
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


def create_project(client: TestClient, name: str = "Rule Engine Test Project") -> str:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def upload_csv(client: TestClient, project_id: str, filename: str, csv_data: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": (filename, io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 201
    return response.json()


# ==============================================================================
# Unit Tests: Structured Predicates & Compound Filter Evaluation
# ==============================================================================


def test_structured_predicates():
    """Verify evaluation of equality, inequality, membership, numeric, between, and regex predicates."""
    rec = {
        "status": "COMPLETED",
        "amount": "150.75",
        "category": "ELECTRONICS",
        "currency": "USD",
        "notes": "Order INV-2026-X confirmed",
        "discount": None,
    }

    # Equality
    assert evaluate_predicate(rec, WhereCondition(field="status", operator=PredicateOperator.EQUAL, value="completed"))
    assert not evaluate_predicate(rec, WhereCondition(field="status", operator=PredicateOperator.EQUAL, value="PENDING"))

    # Inequality
    assert evaluate_predicate(rec, WhereCondition(field="currency", operator=PredicateOperator.NOT_EQUAL, value="EUR"))

    # IN / NOT IN
    assert evaluate_predicate(rec, WhereCondition(field="category", operator=PredicateOperator.IN, value=["BOOKS", "ELECTRONICS"]))
    assert not evaluate_predicate(rec, WhereCondition(field="category", operator=PredicateOperator.NOT_IN, value=["ELECTRONICS"]))

    # Greater than / Less than / Between
    assert evaluate_predicate(rec, WhereCondition(field="amount", operator=PredicateOperator.GREATER_THAN, value=100.0))
    assert evaluate_predicate(rec, WhereCondition(field="amount", operator=PredicateOperator.LESS_THAN, value=200.0))
    assert evaluate_predicate(rec, WhereCondition(field="amount", operator=PredicateOperator.BETWEEN, value=[100.0, 200.0]))
    assert not evaluate_predicate(rec, WhereCondition(field="amount", operator=PredicateOperator.BETWEEN, value=[200.0, 300.0]))

    # Regex
    assert evaluate_predicate(rec, WhereCondition(field="notes", operator=PredicateOperator.REGEX, value=r"INV-\d{4}-[A-Z]"))
    assert not evaluate_predicate(rec, WhereCondition(field="notes", operator=PredicateOperator.REGEX, value=r"^REF-\d+"))

    # Null checks
    assert evaluate_predicate(rec, WhereCondition(field="discount", operator=PredicateOperator.IS_NULL))
    assert evaluate_predicate(rec, WhereCondition(field="amount", operator=PredicateOperator.IS_NOT_NULL))


def test_compound_rules():
    """Verify compound rules with AND/OR conjunctions."""
    rec = {"tier": "GOLD", "spend": 5000, "active": True}

    # Compound AND: True AND True -> True
    rule_and = CompoundRule(
        name="High Spender",
        conjunction=RuleConjunction.AND,
        conditions=[
            WhereCondition(field="tier", operator=PredicateOperator.EQUAL, value="gold"),
            WhereCondition(field="spend", operator=PredicateOperator.GREATER_EQUAL, value=1000),
        ],
    )
    assert evaluate_compound_rule(rec, rule_and)

    # Compound AND with one failing condition -> False
    rule_and_fail = CompoundRule(
        name="Ultra VIP",
        conjunction=RuleConjunction.AND,
        conditions=[
            WhereCondition(field="tier", operator=PredicateOperator.EQUAL, value="gold"),
            WhereCondition(field="spend", operator=PredicateOperator.GREATER_THAN, value=10000),
        ],
    )
    assert not evaluate_compound_rule(rec, rule_and_fail)

    # Compound OR: False OR True -> True
    rule_or = CompoundRule(
        name="VIP or High Spender",
        conjunction=RuleConjunction.OR,
        conditions=[
            WhereCondition(field="tier", operator=PredicateOperator.EQUAL, value="PLATINUM"),
            WhereCondition(field="spend", operator=PredicateOperator.GREATER_THAN, value=2000),
        ],
    )
    assert evaluate_compound_rule(rec, rule_or)


# ==============================================================================
# Unit Tests: Date Window Rules
# ==============================================================================


def test_date_window_settlement_lag():
    """Verify settlement lag: target date inside window passes; outside window fails."""
    rule = DateWindowRule(
        source_date_field="order_date",
        target_date_field="settlement_date",
        lag_days_before=1,
        lag_days_after=3,
    )

    # Exact same date: 0 days lag -> Pass
    passed, _ = evaluate_date_window("2026-05-10", "2026-05-10", rule)
    assert passed

    # 2 days after: inside [ -1, +3 ] -> Pass
    passed, _ = evaluate_date_window("2026-05-10", "2026-05-12", rule)
    assert passed

    # 1 day before: inside [ -1, +3 ] -> Pass
    passed, _ = evaluate_date_window("2026-05-10", "2026-05-09", rule)
    assert passed

    # 5 days after: exceeds +3 days -> Fail
    passed, msg = evaluate_date_window("2026-05-10", "2026-05-15", rule)
    assert not passed
    assert "exceeds window" in msg

    # 3 days before: exceeds -1 days -> Fail
    passed, msg = evaluate_date_window("2026-05-10", "2026-05-07", rule)
    assert not passed
    assert "exceeds window" in msg


# ==============================================================================
# Unit Tests: Numeric Tolerance (Absolute & Percentage)
# ==============================================================================


def test_numeric_tolerance_modes():
    """Verify absolute and percentage tolerance evaluation modes."""
    # Absolute mode: within 0.50
    rule_abs = NumericToleranceRule(
        source_amount_field="amt1",
        target_amount_field="amt2",
        absolute_tolerance=0.50,
        tolerance_mode=ToleranceMode.ABSOLUTE,
    )
    passed, _ = evaluate_numeric_tolerance("100.00", "100.35", rule_abs)
    assert passed
    passed, _ = evaluate_numeric_tolerance("100.00", "100.75", rule_abs)
    assert not passed

    # Percentage mode: within 1.0%
    rule_pct = NumericToleranceRule(
        source_amount_field="amt1",
        target_amount_field="amt2",
        percentage_tolerance=1.0,
        tolerance_mode=ToleranceMode.PERCENTAGE,
    )
    passed, _ = evaluate_numeric_tolerance("5000.00", "5040.00", rule_pct)  # 0.8% diff
    assert passed
    passed, _ = evaluate_numeric_tolerance("5000.00", "5100.00", rule_pct)  # 2.0% diff
    assert not passed

    # Both_OR mode: passes if either absolute or percentage is satisfied
    rule_or = NumericToleranceRule(
        source_amount_field="amt1",
        target_amount_field="amt2",
        absolute_tolerance=0.10,
        percentage_tolerance=5.0,
        tolerance_mode=ToleranceMode.BOTH_OR,
    )
    passed, _ = evaluate_numeric_tolerance("10.00", "10.40", rule_or)  # 4% diff (passes pct)
    assert passed


# ==============================================================================
# Unit Tests: Status Transition Rules
# ==============================================================================


def test_status_transition_rules():
    """Verify state mapping whitelist across sources."""
    rule = StatusTransitionRule(
        source_field="status",
        target_field="status",
        allowed_transitions={
            "PAID": ["SETTLED", "CLEARED"],
            "PENDING": ["PROCESSING"],
        },
        case_sensitive=False,
    )

    # Allowed transitions
    passed, _ = evaluate_status_transition("paid", "settled", rule)
    assert passed
    passed, _ = evaluate_status_transition("PAID", "CLEARED", rule)
    assert passed

    # Disallowed transition
    passed, msg = evaluate_status_transition("PAID", "REJECTED", rule)
    assert not passed
    assert "not allowed" in msg


# ==============================================================================
# Unit Tests: Split-Payment / Aggregation (1:N Matching)
# ==============================================================================


def test_split_payment_exact_sum():
    """Verify 1:N reconciliation matching a single invoice against multiple installments."""
    parents = [
        (1, {"invoice_id": "INV-100", "amount": 1000.00, "date": "2026-06-01"}),
    ]
    children = [
        (1, {"invoice_id": "INV-100", "amount": 400.00, "receipt_id": "REC-01", "date": "2026-06-02"}),
        (2, {"invoice_id": "INV-100", "amount": 350.00, "receipt_id": "REC-02", "date": "2026-06-03"}),
        (3, {"invoice_id": "INV-100", "amount": 250.00, "receipt_id": "REC-03", "date": "2026-06-04"}),
    ]

    config = AggregationConfig(
        enabled=True,
        parent_source_alias="invoices",
        child_source_alias="payments",
        parent_key="invoice_id",
        child_grouping_key="invoice_id",
        parent_amount_field="amount",
        child_amount_field="amount",
        child_receipt_id_field="receipt_id",
        numeric_tolerance=0.0,
    )

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=config,
    )

    assert summary.identical_matches == 1
    assert summary.field_mismatches == 0
    assert len(discrepancies) == 0

    item = results[0]
    assert item.match_status == MatchStatus.IDENTICAL
    assert item.aggregated_amount == 1000.00
    assert item.expected_amount == 1000.00
    assert len(item.child_records) == 3
    assert item.child_records[0]["receipt_id"] == "REC-01"
    assert item.child_records[1]["amount"] == 350.00


def test_split_payment_partial_and_overpayment():
    """Verify underpayment triggers PARTIAL_PAYMENT and excess triggers OVERPAYMENT."""
    parents = [
        (1, {"inv_id": "INV-A", "total": 500.00}),
        (2, {"inv_id": "INV-B", "total": 300.00}),
    ]
    children = [
        # INV-A: 200 + 250 = 450 (short by 50) -> PARTIAL_PAYMENT
        (1, {"inv_id": "INV-A", "amount": 200.00}),
        (2, {"inv_id": "INV-A", "amount": 250.00}),
        # INV-B: 200 + 150 = 350 (excess of 50) -> OVERPAYMENT
        (3, {"inv_id": "INV-B", "amount": 200.00}),
        (4, {"inv_id": "INV-B", "amount": 150.00}),
    ]

    config = AggregationConfig(
        enabled=True,
        parent_source_alias="invoices",
        child_source_alias="payments",
        parent_key="inv_id",
        child_grouping_key="inv_id",
        parent_amount_field="total",
        child_amount_field="amount",
        numeric_tolerance=0.0,
    )

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=config,
    )

    assert summary.identical_matches == 0
    assert summary.field_mismatches == 2

    # Check INV-A
    inv_a = next(d for d in discrepancies if d.key_values["inv_id"] == "INV-A")
    assert inv_a.match_status == MatchStatus.PARTIAL_PAYMENT
    assert inv_a.reason_code == ReasonCode.PARTIAL_PAYMENT
    assert inv_a.aggregated_amount == 450.00
    assert inv_a.expected_amount == 500.00

    # Check INV-B
    inv_b = next(d for d in discrepancies if d.key_values["inv_id"] == "INV-B")
    assert inv_b.match_status == MatchStatus.OVERPAYMENT
    assert inv_b.reason_code == ReasonCode.OVERPAYMENT
    assert inv_b.aggregated_amount == 350.00
    assert inv_b.expected_amount == 300.00


def test_split_payment_duplicate_receipts_and_orphans():
    """Verify duplicate receipt ID detection and orphan child installment detection."""
    parents = [
        (1, {"inv_id": "INV-10", "total": 200.00}),
    ]
    children = [
        # Duplicate receipt REC-DUP in same order
        (1, {"inv_id": "INV-10", "amount": 100.00, "rec_id": "REC-DUP"}),
        (2, {"inv_id": "INV-10", "amount": 100.00, "rec_id": "REC-DUP"}),
        # Orphan child: references non-existent order INV-GHOST
        (3, {"inv_id": "INV-GHOST", "amount": 75.00, "rec_id": "REC-99"}),
    ]

    config = AggregationConfig(
        enabled=True,
        parent_source_alias="invoices",
        child_source_alias="payments",
        parent_key="inv_id",
        child_grouping_key="inv_id",
        parent_amount_field="total",
        child_amount_field="amount",
        child_receipt_id_field="rec_id",
    )

    summary, results, discrepancies = reconcile_split_payments(
        parent_records=parents,
        child_records=children,
        config=config,
    )

    assert summary.field_mismatches == 1  # Duplicate receipt
    assert summary.unmatched_target_records == 1  # Orphan

    # Check duplicate receipt
    dup = next(d for d in discrepancies if d.key_values["inv_id"] == "INV-10")
    assert dup.match_status == MatchStatus.DUPLICATE_RECEIPT
    assert dup.reason_code == ReasonCode.DUPLICATE_RECEIPT

    # Check orphan
    orphan = next(d for d in discrepancies if d.key_values.get("inv_id") == "INV-GHOST")
    assert orphan.match_status == MatchStatus.UNMATCHED_SPLIT_RECORD
    assert orphan.reason_code == ReasonCode.UNMATCHED_SPLIT_RECORD
    assert orphan.source_row_indices["invoices"] is None
    assert orphan.source_row_indices["payments"] == 3


# ==============================================================================
# Integration Tests: Rule Validation & Preview Endpoints
# ==============================================================================


def test_rule_validate_endpoint(client: TestClient, upload_storage: Path):
    """Test POST /api/v1/projects/{project_id}/rules/validate."""
    proj_id = create_project(client, "Rule Validate Project")

    f1 = upload_csv(client, proj_id, "orders.csv", "order_id,amount,order_date\nO-1,100,2026-01-01\n")
    f2 = upload_csv(client, proj_id, "bank.csv", "order_id,settled_amount,settled_date\nO-1,100,2026-01-02\n")

    rules = {
        "version": "1.0.0",
        "name": "Custom Audit Rules",
        "where_conditions": [
            {"field": "amount", "operator": "greater_than", "value": 0},
            {"field": "non_existent_column", "operator": "is_not_null"},
        ],
        "date_window_rules": [
            {
                "source_date_field": "order_date",
                "target_date_field": "settled_date",
                "lag_days_before": 0,
                "lag_days_after": 2,
            }
        ],
        "numeric_tolerance_rules": [
            {
                "source_amount_field": "amount",
                "target_amount_field": "settled_amount",
                "absolute_tolerance": 0.05,
                "tolerance_mode": "absolute",
            }
        ],
    }

    res = client.post(
        f"/api/v1/projects/{proj_id}/rules/validate",
        json={
            "rules": rules,
            "sources": [
                {"alias": "orders", "file_id": f1["id"], "key_columns": ["order_id"]},
                {"alias": "bank", "file_id": f2["id"], "key_columns": ["order_id"]},
            ],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["total_rules_checked"] == 4
    # Field resolution check
    assert data["field_resolutions"]["amount"] is True
    assert data["field_resolutions"]["non_existent_column"] is False
    assert any("non_existent_column" in w for w in data["warnings"])


def test_rule_preview_endpoint(client: TestClient, upload_storage: Path):
    """Test POST /api/v1/projects/{project_id}/rules/preview."""
    proj_id = create_project(client, "Rule Preview Project")

    f1 = upload_csv(
        client,
        proj_id,
        "erp.csv",
        "id,amount,status,date\n"
        "1,100,PAID,2026-03-01\n"
        "2,200,PAID,2026-03-01\n"
        "3,300,PAID,2026-03-01\n"
    )
    f2 = upload_csv(
        client,
        proj_id,
        "bank.csv",
        "id,amount,status,date\n"
        "1,100,SETTLED,2026-03-02\n"  # Pass lag & status
        "2,250,SETTLED,2026-03-02\n"  # Fail amount tolerance (250 vs 200)
        "3,300,FAILED,2026-03-15\n"   # Fail lag & status transition
    )

    rules = {
        "version": "1.0.0",
        "date_window_rules": [
            {"source_date_field": "date", "target_date_field": "date", "lag_days_before": 0, "lag_days_after": 3}
        ],
        "numeric_tolerance_rules": [
            {"source_amount_field": "amount", "target_amount_field": "amount", "absolute_tolerance": 1.0}
        ],
        "status_transition_rules": [
            {"source_field": "status", "target_field": "status", "allowed_transitions": {"PAID": ["SETTLED"]}}
        ],
    }

    res = client.post(
        f"/api/v1/projects/{proj_id}/rules/preview",
        json={
            "rules": rules,
            "sources": [
                {"alias": "erp", "file_id": f1["id"], "key_columns": ["id"]},
                {"alias": "bank", "file_id": f2["id"], "key_columns": ["id"]},
            ],
            "sample_size": 10,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_evaluated"] == 3
    assert data["passed_count"] == 1  # Row 1 passes all rules
    assert data["exception_count"] == 2  # Rows 2 and 3 fail rules
    assert len(data["sample_discrepancies"]) == 2


def test_split_payment_persistent_run(client: TestClient, upload_storage: Path):
    """Test full multi-source run execution with split payment aggregation config."""
    proj_id = create_project(client, "Split Payment Run Project")

    # Invoices (1)
    f1 = upload_csv(
        client,
        proj_id,
        "invoices.csv",
        "inv_no,total\nINV-900,1000.00\n",
    )
    # Payments (N)
    f2 = upload_csv(
        client,
        proj_id,
        "payments.csv",
        "inv_no,paid_amt,rec_no\n"
        "INV-900,600.00,R-1\n"
        "INV-900,400.00,R-2\n",
    )

    rule_config = {
        "version": "1.0.0",
        "aggregation_config": {
            "enabled": True,
            "parent_source_alias": "invoices",
            "child_source_alias": "payments",
            "parent_key": "inv_no",
            "child_grouping_key": "inv_no",
            "parent_amount_field": "total",
            "child_amount_field": "paid_amt",
            "child_receipt_id_field": "rec_no",
            "numeric_tolerance": 0.0,
        },
    }

    run_res = client.post(
        f"/api/v1/projects/{proj_id}/runs/multi-source",
        json={
            "sources": [
                {"alias": "invoices", "file_id": f1["id"], "is_primary": True, "key_columns": ["inv_no"]},
                {"alias": "payments", "file_id": f2["id"], "is_primary": False, "key_columns": ["inv_no"]},
            ],
            "unified_keys": ["inv_no"],
            "rule_config": rule_config,
            "include_identical": True,
        },
    )
    assert run_res.status_code == 201
    run_data = run_res.json()
    assert run_data["status"] == "completed"
    assert run_data["summary"]["identical_matches"] == 1
    assert run_data["summary"]["field_mismatches"] == 0
