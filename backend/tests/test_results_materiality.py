"""Unit and integration tests for Results Grid, Financial Materiality, and Record Inspector (Batch 5).

Tests:
- Gross Exception Exposure vs. Net Variance calculations (positive, negative, zero differences).
- Currency rounding and multi-record exposure aggregation.
- Amount-based filtering (min_amount, max_amount) and exposure sorting API queries.
- Side-by-side inspection payload correctness, raw vs. normalized fields, and diff highlighting.
- Integration tests with persistent runs and multi-source workflows.
"""

from __future__ import annotations

import io
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.project import Project
from app.models.source_file import SourceFile
from app.models.verification_run import VerificationRun, VerificationDiscrepancy
from app.schemas.result import (
    MatchStatus,
    DiscrepancyCategory,
    ReasonCode,
    VerificationRequest,
    VerificationResultItem,
    VerificationSummary,
)
from app.services.verification_engine import (
    verify_datasets,
    create_and_execute_verification_run,
    list_run_discrepancies,
    get_discrepancy_inspection,
)
from app.services.materiality_engine import (
    compute_record_materiality,
    compute_summary_materiality,
    extract_amount_and_currency,
    build_side_by_side_payload,
)


def test_gross_exposure_vs_net_variance_directional_calculations():
    """
    Test Gross Exception Exposure (|source - target|) vs. Net Variance (source - target).
    Includes positive variance (under-reconciled), negative variance (over-reconciled),
    and exact match (zero variance).
    """
    # Item 1: Source = 1000.00, Target = 800.00 -> Diff = +200.00 (under-paid/source higher)
    item1 = VerificationResultItem(
        key_values={"id": "TX-01"},
        match_status=MatchStatus.FIELD_MISMATCH,
        discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
        source_record={"id": "TX-01", "amount": 1000.00, "status": "settled"},
        target_record={"id": "TX-01", "amount": 800.00, "status": "settled"},
    )
    compute_record_materiality(item1)
    assert item1.source_amount == 1000.00
    assert item1.target_amount == 800.00
    assert item1.variance_amount == 200.00
    assert item1.exposure_amount == 200.00

    # Item 2: Source = 500.00, Target = 700.00 -> Diff = -200.00 (over-paid/target higher)
    item2 = VerificationResultItem(
        key_values={"id": "TX-02"},
        match_status=MatchStatus.FIELD_MISMATCH,
        discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
        source_record={"id": "TX-02", "amount": 500.00, "status": "settled"},
        target_record={"id": "TX-02", "amount": 700.00, "status": "settled"},
    )
    compute_record_materiality(item2)
    assert item2.source_amount == 500.00
    assert item2.target_amount == 700.00
    assert item2.variance_amount == -200.00
    assert item2.exposure_amount == 200.00

    # Item 3: Source = 300.00, Target = 300.00 (Identical) -> Variance = 0, Exposure = 0
    item3 = VerificationResultItem(
        key_values={"id": "TX-03"},
        match_status=MatchStatus.IDENTICAL,
        discrepancy_category=DiscrepancyCategory.NONE,
        source_record={"id": "TX-03", "amount": 300.00, "status": "settled"},
        target_record={"id": "TX-03", "amount": 300.00, "status": "settled"},
    )
    compute_record_materiality(item3)
    assert item3.source_amount == 300.00
    assert item3.target_amount == 300.00
    assert item3.variance_amount == 0.00
    assert item3.exposure_amount == 0.00

    # Aggregate into summary
    results = [item1, item2, item3]
    discrepancies = [item1, item2]

    base_summary = VerificationSummary(
        total_source_records=3,
        total_target_records=3,
        matched_records=3,
        identical_matches=1,
        field_mismatches=2,
        records_with_differences=2,
        unmatched_source_records=0,
        unmatched_target_records=0,
        duplicate_source_records=0,
        duplicate_target_records=0,
        duplicate_source_keys_count=0,
        duplicate_target_keys_count=0,
        total_discrepancies=2,
        status="completed",
    )

    summary = compute_summary_materiality(results, discrepancies, base_summary)

    # Gross Exposure = |+200| + |-200| = 400.00
    assert summary.gross_exposure == 400.00
    # Net Variance = +200 + (-200) + 0 = 0.00
    assert summary.net_variance == 0.00
    # Claimed = 1000 + 500 + 300 = 1800.00
    assert summary.claimed_amount == 1800.00
    # Verified = 300.00
    assert summary.verified_amount == 300.00
    # Outstanding = 400.00
    assert summary.outstanding_amount == 400.00


def test_currency_rounding_and_accounting_parens():
    """Test accounting negative parentheses '(50.25)', currency symbols, and 2-decimal rounding."""
    rec1 = {"id": "1", "amount": "$1,250.556"}
    amt1, curr1 = extract_amount_and_currency(rec1)
    assert amt1 == 1250.56
    assert curr1 == "USD"

    rec2 = {"id": "2", "balance": "(140.40)"}
    amt2, curr2 = extract_amount_and_currency(rec2)
    assert amt2 == -140.40
    assert curr2 == "USD"

    rec3 = {"id": "3", "price": "€500.00"}
    amt3, curr3 = extract_amount_and_currency(rec3)
    assert amt3 == 500.00
    assert curr3 == "EUR"


def test_verify_datasets_materiality_integration():
    """Test end-to-end dataset verification calculating gross exposure and net variance."""
    source = [
        (1, {"order_id": "ORD-1", "amount": "100.00", "status": "PAID"}),
        (2, {"order_id": "ORD-2", "amount": "250.50", "status": "PAID"}),
        (3, {"order_id": "ORD-3", "amount": "50.00", "status": "PENDING"}),
    ]
    target = [
        (1, {"order_id": "ORD-1", "amount": "100.00", "status": "PAID"}),  # Identical
        (2, {"order_id": "ORD-2", "amount": "200.00", "status": "PAID"}),  # Mismatch: 50.50 variance
        (3, {"order_id": "ORD-4", "amount": "75.00", "status": "PAID"}),   # Missing in source, ORD-3 missing in target
    ]

    summary, results, discrepancies, warnings, errors = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["order_id"],
    )

    # Discrepancies: ORD-2 (50.50 diff), ORD-3 (missing in target, 50.00 exposure), ORD-4 (missing in source, 75.00 exposure)
    # Gross Exposure = 50.50 + 50.00 + 75.00 = 175.50
    assert summary.gross_exposure == 175.50
    # Net Variance = (100 - 100) + (250.50 - 200) + (50 - 0) + (0 - 75) = 0 + 50.50 + 50 - 75 = 25.50
    assert summary.net_variance == 25.50
    # Claimed = 100 + 250.50 + 50 = 400.50
    assert summary.claimed_amount == 400.50
    # Verified = 100.00
    assert summary.verified_amount == 100.00


def test_side_by_side_payload_and_field_diff_highlighting():
    """Test raw vs. normalized side-by-side payload structure and mismatch tagging."""
    item = VerificationResultItem(
        key_values={"order_id": "ORD-99"},
        match_status=MatchStatus.FIELD_MISMATCH,
        discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
        reason_code=ReasonCode.FIELD_MISMATCH,
        source_record={"order_id": "ORD-99", "amount": "  $1,000.00  ", "customer": "ACME Corp", "active": "yes"},
        target_record={"order_id": "ORD-99", "amount": "900.00", "customer": "ACME INC", "active": "true"},
    )
    compute_record_materiality(item)

    assert item.side_by_side is not None
    sbs = item.side_by_side

    # Raw values preserved
    assert sbs["raw_source_record"]["amount"] == "  $1,000.00  "
    assert sbs["raw_target_record"]["amount"] == "900.00"

    # Normalized values cleaned
    assert sbs["normalized_source_record"]["amount"] == 1000
    assert sbs["normalized_target_record"]["amount"] == 900

    # Booleans normalized
    assert sbs["normalized_source_record"]["active"] is True
    assert sbs["normalized_target_record"]["active"] is True

    # Field comparisons array
    comparisons = {c["field_name"]: c for c in sbs["field_comparisons"]}
    assert "amount" in comparisons
    assert comparisons["amount"]["is_match"] is False
    assert comparisons["amount"]["normalized_source_value"] == 1000
    assert comparisons["amount"]["normalized_target_value"] == 900

    assert "customer" in comparisons
    assert comparisons["customer"]["is_match"] is False

    assert "active" in comparisons
    assert comparisons["active"]["is_match"] is True


def test_persistent_run_filtering_and_sorting_api(
    client: TestClient,
    db_session: Session,
    default_user: User,
):
    """Test API query filtering by monetary range (min_amount, max_amount), reason_code, and sorting by exposure."""
    # 1. Create project
    proj = Project(
        name="Materiality Test Project",
        description="Testing financial exposure metrics",
        owner_id=default_user.id,
    )
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    # 2. Create verification run with multiple discrepancies of varying amounts
    run = VerificationRun(
        project_id=proj.id,
        status="completed",
        key_columns=["tx_id"],
        summary={
            "total_source_records": 4,
            "total_target_records": 4,
            "gross_exposure": 1650.00,
            "net_variance": 500.00,
            "claimed_amount": 2500.00,
            "verified_amount": 1000.00,
            "outstanding_amount": 1650.00,
            "currency": "USD",
        },
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # Low exposure discrepancy: $50
    disc1 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="field_mismatch",
        discrepancy_category="field_mismatch",
        key_values={"tx_id": "TX-1"},
        source_amount=150.00,
        target_amount=100.00,
        variance_amount=50.00,
        exposure_amount=50.00,
        severity="low",
        _reason_code="AMOUNT_TOLERANCE_EXCEEDED",
    )
    # High exposure discrepancy: $1200
    disc2 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="missing_in_target",
        discrepancy_category="missing_record",
        key_values={"tx_id": "TX-2"},
        source_amount=1200.00,
        target_amount=0.00,
        variance_amount=1200.00,
        exposure_amount=1200.00,
        severity="high",
        _reason_code="MISSING_IN_TARGET",
    )
    # Medium exposure discrepancy: $400
    disc3 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="field_mismatch",
        discrepancy_category="field_mismatch",
        key_values={"tx_id": "TX-3"},
        source_amount=800.00,
        target_amount=400.00,
        variance_amount=400.00,
        exposure_amount=400.00,
        severity="medium",
        _reason_code="FIELD_MISMATCH",
    )
    db_session.add_all([disc1, disc2, disc3])
    db_session.commit()

    # 3. Test Sorting by Exposure Amount (Descending)
    resp = client.get(
        f"/api/v1/projects/{proj.id}/runs/{run.id}/results?sort_by=exposure_amount&sort_order=desc"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    # Top item should be $1200, followed by $400, then $50
    assert data["items"][0]["exposure_amount"] == 1200.00
    assert data["items"][1]["exposure_amount"] == 400.00
    assert data["items"][2]["exposure_amount"] == 50.00

    # 4. Test Sorting by Exposure Amount (Ascending)
    resp_asc = client.get(
        f"/api/v1/projects/{proj.id}/runs/{run.id}/results?sort_by=exposure_amount&sort_order=asc"
    )
    assert resp_asc.status_code == 200
    data_asc = resp_asc.json()
    assert data_asc["items"][0]["exposure_amount"] == 50.00
    assert data_asc["items"][2]["exposure_amount"] == 1200.00

    # 5. Test Monetary Range Filter: min_amount=100
    resp_min = client.get(
        f"/api/v1/projects/{proj.id}/runs/{run.id}/results?min_amount=100"
    )
    assert resp_min.status_code == 200
    items_min = resp_min.json()["items"]
    assert len(items_min) == 2
    assert all(i["exposure_amount"] >= 100 for i in items_min)

    # 6. Test Monetary Range Filter: max_amount=500
    resp_max = client.get(
        f"/api/v1/projects/{proj.id}/runs/{run.id}/results?max_amount=500"
    )
    assert resp_max.status_code == 200
    items_max = resp_max.json()["items"]
    assert len(items_max) == 2
    assert all(i["exposure_amount"] <= 500 for i in items_max)

    # 7. Test Filter by Reason Code
    resp_rc = client.get(
        f"/api/v1/projects/{proj.id}/runs/{run.id}/results?reason_code=MISSING_IN_TARGET"
    )
    assert resp_rc.status_code == 200
    items_rc = resp_rc.json()["items"]
    assert len(items_rc) == 1
    assert items_rc[0]["key_values"]["tx_id"] == "TX-2"

    # 8. Test Side-by-Side Inspection Endpoint
    inspect_resp = client.get(
        f"/api/v1/projects/{proj.id}/runs/{run.id}/results/{disc2.id}/inspect"
    )
    assert inspect_resp.status_code == 200
    insp_data = inspect_resp.json()
    assert insp_data["id"] == str(disc2.id)
    assert insp_data["exposure_amount"] == 1200.00
    assert insp_data["severity"] == "high"
    assert insp_data["match_status"] == "missing_in_target"
