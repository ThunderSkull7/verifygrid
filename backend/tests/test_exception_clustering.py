"""Unit and integration tests for Exception Clustering, Signatures, and Bulk Review (Batch 6).

Tests:
- Exception signature generation and deterministic cluster grouping.
- Aggregate exposure calculation and root-cause explanations per cluster.
- Bulk review execution, individual audit decision record creation, and mandatory justification enforcement.
- Financial exposure barriers and hard blocking rule eligibility safeguards.
- Reviewer assignment and assigned_to filtering endpoints.
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
from app.models.verification_run import (
    DiscrepancyReviewDecision,
    VerificationDiscrepancy,
    VerificationRun,
)
from app.schemas.result import (
    DiscrepancyCategory,
    FieldDifference,
    MatchStatus,
    ReasonCode,
    VerificationResultItem,
)
from app.schemas.review import (
    AssignmentRequest,
    BulkReviewRequest,
    ReviewDecisionRequest,
)
from app.services.clustering_service import (
    cluster_discrepancies_in_memory,
    compute_exception_signature,
    generate_cluster_id,
    generate_cluster_name,
    generate_root_cause_explanation,
    get_cluster_records,
    get_run_clusters,
)
from app.services.review_service import (
    apply_bulk_review,
    apply_single_review,
    assign_discrepancies,
)


def test_exception_signature_generation_and_cluster_grouping():
    """Test deterministic signature hashing and human-readable cluster naming."""
    # 1. Whitespace mismatch
    item_ws = VerificationResultItem(
        key_values={"id": "EMP-01"},
        match_status=MatchStatus.FIELD_MISMATCH,
        discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
        reason_code=ReasonCode.TRAILING_WHITESPACE,
        field_differences=[
            FieldDifference(
                field_name="employee_id",
                source_field="employee_id",
                target_field="employee_id",
                source_value="EMP-01 ",
                target_value="EMP-01",
                difference_type="whitespace",
                reason_code=ReasonCode.TRAILING_WHITESPACE,
            )
        ],
        exposure_amount=150.0,
    )
    sig_ws = compute_exception_signature(item_ws)
    cid_ws = generate_cluster_id(sig_ws)
    name_ws = generate_cluster_name(sig_ws, item_ws)

    assert sig_ws[0] == "TRAILING_WHITESPACE"
    assert "employee_id" in sig_ws[2]
    assert cid_ws.startswith("c_")
    assert "Trailing Whitespace Mismatch in Employee Id" in name_ws

    # 2. Date Lag Exceeded on Gateway Settlement
    item_date = {
        "match_status": "field_mismatch",
        "discrepancy_category": "field_mismatch",
        "reason_code": "DATE_WINDOW_EXCEEDED",
        "side_by_side": {
            "failed_rules": [
                {
                    "rule_id": "rule_date_lag",
                    "source_alias": "gateway",
                    "reason_code": "DATE_WINDOW_EXCEEDED",
                    "description": "Date Lag Exceeded (>3 Days) on Gateway Settlement",
                }
            ],
            "field_comparisons": [
                {"field_name": "settlement_date", "is_match": False}
            ],
        },
        "exposure_amount": 2500.0,
    }
    sig_date = compute_exception_signature(item_date)
    cid_date = generate_cluster_id(sig_date)
    name_date = generate_cluster_name(sig_date, item_date)

    assert sig_date[0] == "DATE_WINDOW_EXCEEDED"
    assert sig_date[1] == "rule_date_lag"
    assert sig_date[3] == "gateway"
    assert name_date == "Date Lag Exceeded (>3 Days) on Gateway Settlement"


def test_aggregate_exposure_and_explanations_per_cluster():
    """Test multi-record exposure aggregation and status counts in cluster engine."""
    records = [
        VerificationResultItem(
            id=str(uuid.uuid4()),
            key_values={"id": f"TX-{i}"},
            match_status=MatchStatus.FIELD_MISMATCH,
            discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
            reason_code=ReasonCode.VALUE_MISMATCH,
            field_differences=[
                FieldDifference(
                    field_name="tax_code",
                    source_field="tax_code",
                    target_field="tax_code",
                    source_value="VAT20",
                    target_value="VAT0",
                    difference_type="value",
                    reason_code=ReasonCode.VALUE_MISMATCH,
                )
            ],
            exposure_amount=100.50,
            resolution_status="unresolved",
        )
        for i in range(5)
    ]
    # Add a 6th record with same root cause but already approved
    records.append(
        VerificationResultItem(
            id=str(uuid.uuid4()),
            key_values={"id": "TX-99"},
            match_status=MatchStatus.FIELD_MISMATCH,
            discrepancy_category=DiscrepancyCategory.FIELD_MISMATCH,
            reason_code=ReasonCode.VALUE_MISMATCH,
            field_differences=[
                FieldDifference(
                    field_name="tax_code",
                    source_field="tax_code",
                    target_field="tax_code",
                    source_value="VAT20",
                    target_value="VAT0",
                    difference_type="value",
                    reason_code=ReasonCode.VALUE_MISMATCH,
                )
            ],
            exposure_amount=50.25,
            resolution_status="APPROVED",
        )
    )

    clusters = cluster_discrepancies_in_memory(records)
    assert len(clusters) == 1
    cl = clusters[0]
    assert cl.total_records == 6
    # 5 * 100.50 + 50.25 = 502.50 + 50.25 = 552.75
    assert cl.total_exposure == 552.75
    assert cl.status_counts["unresolved"] == 5
    assert cl.status_counts["APPROVED"] == 1
    assert "tax_code" in cl.failed_field_names
    assert "Cumulative exposure is $552.75" in cl.root_cause_explanation


def test_bulk_review_execution_and_individual_audit_records(db_session: Session, default_user: User):
    """
    Test bulk review decisions:
    - Verifies justification is required.
    - Verifies every affected record persists an individual DiscrepancyReviewDecision row.
    - Verifies status updates on discrepancy records.
    """
    project = Project(name="Bulk Review Project", owner_id=default_user.id)
    db_session.add(project)
    db_session.commit()

    run = VerificationRun(project_id=project.id, key_columns=["id"], status="completed")
    db_session.add(run)
    db_session.commit()

    # Create 3 discrepancies in cluster 'c_test1'
    disc_list = []
    for i in range(3):
        d = VerificationDiscrepancy(
            run_id=run.id,
            match_status="field_mismatch",
            discrepancy_category="field_mismatch",
            key_values={"id": f"INV-{i}"},
            exposure_amount=200.0,
            resolution_status="unresolved",
            cluster_id="c_test1",
            cluster_name="Missing Tax Code",
        )
        db_session.add(d)
        disc_list.append(d)
    db_session.commit()

    # 1. Whitespace justification raises ValueError
    with pytest.raises(ValueError, match="justification note is required"):
        apply_bulk_review(
            db=db_session,
            project_id=project.id,
            run_id=run.id,
            request=BulkReviewRequest(
                decision="APPROVE",
                justification="   ",
                cluster_id="c_test1",
            ),
            current_user=default_user,
        )

    # 2. Valid bulk review execution
    resp = apply_bulk_review(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        request=BulkReviewRequest(
            decision="APPROVE",
            justification="Auditor approval: tax code difference authorized under 2026 concession policy.",
            cluster_id="c_test1",
        ),
        current_user=default_user,
    )

    assert resp.total_requested == 3
    assert resp.succeeded_count == 3
    assert resp.ineligible_count == 0
    assert len(resp.succeeded_ids) == 3

    # Check that each record updated to APPROVED
    for d in disc_list:
        db_session.refresh(d)
        assert d.resolution_status == "APPROVED"
        assert "concession policy" in (d.resolution_note or "")

    # Check granular audit persistence: 3 individual review decision rows must exist!
    audit_rows = (
        db_session.query(DiscrepancyReviewDecision)
        .filter(DiscrepancyReviewDecision.run_id == run.id)
        .all()
    )
    assert len(audit_rows) == 3
    for ar in audit_rows:
        assert ar.decision == "APPROVE"
        assert ar.new_status == "APPROVED"
        assert ar.previous_status == "unresolved"
        assert ar.is_bulk_action is True
        assert ar.cluster_id == "c_test1"
        assert ar.reviewer_email == default_user.email


def test_bulk_review_eligibility_barriers(db_session: Session, default_user: User):
    """
    Test safeguards preventing ineligible records from silent bulk approval:
    - High financial exposure threshold barrier.
    - Hard BLOCKING rule failure barrier.
    - Partial success reporting.
    """
    project = Project(name="Barrier Project", owner_id=default_user.id)
    db_session.add(project)
    db_session.commit()

    run = VerificationRun(project_id=project.id, key_columns=["id"], status="completed")
    db_session.add(run)
    db_session.commit()

    # Disc 1: Low exposure, medium severity -> Eligible
    d1 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="field_mismatch",
        discrepancy_category="field_mismatch",
        key_values={"id": "D-01"},
        exposure_amount=150.0,
        severity="medium",
        resolution_status="unresolved",
        cluster_id="c_mixed",
    )
    # Disc 2: High exposure ($8,000) -> Ineligible if threshold is $5,000
    d2 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="field_mismatch",
        discrepancy_category="field_mismatch",
        key_values={"id": "D-02"},
        exposure_amount=8000.0,
        severity="medium",
        resolution_status="unresolved",
        cluster_id="c_mixed",
    )
    # Disc 3: Hard BLOCKING severity -> Ineligible without override
    d3 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="field_mismatch",
        discrepancy_category="field_mismatch",
        key_values={"id": "D-03"},
        exposure_amount=300.0,
        severity="BLOCKING",
        resolution_status="unresolved",
        cluster_id="c_mixed",
    )
    db_session.add_all([d1, d2, d3])
    db_session.commit()

    # Execute bulk review with max_exposure_threshold = 5000 and allow_blocking_override = False
    resp = apply_bulk_review(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        request=BulkReviewRequest(
            decision="APPROVE",
            justification="Bulk approved routine variances",
            cluster_id="c_mixed",
            max_exposure_threshold=5000.0,
            allow_blocking_override=False,
        ),
        current_user=default_user,
    )

    assert resp.total_requested == 3
    assert resp.succeeded_count == 1
    assert resp.ineligible_count == 2
    assert str(d1.id) in resp.succeeded_ids

    # Check failure reasons
    reasons = [f["reason"] for f in resp.failed_records]
    assert any("exceeds bulk approval threshold" in r for r in reasons)
    assert any("BLOCKING rule failure" in r for r in reasons)

    # d1 is APPROVED, d2 and d3 remain unresolved
    db_session.refresh(d1)
    db_session.refresh(d2)
    db_session.refresh(d3)
    assert d1.resolution_status == "APPROVED"
    assert d2.resolution_status == "unresolved"
    assert d3.resolution_status == "unresolved"


def test_api_clusters_review_and_assignment_endpoints(
    client: TestClient, db_session: Session, default_user: User, auth_headers: dict
):
    """
    Test full HTTP API flows:
    - GET /clusters
    - GET /clusters/{cluster_id}/records
    - POST /reviews/bulk
    - POST /reviews/{discrepancy_id}
    - POST /assignments and ASSIGNED_TO_ME filtering.
    """
    # Create project and run
    project = Project(name="API Review Project", owner_id=default_user.id)
    db_session.add(project)
    db_session.commit()

    run = VerificationRun(project_id=project.id, key_columns=["id"], status="completed")
    db_session.add(run)
    db_session.commit()

    # Create test discrepancies
    d1 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="field_mismatch",
        discrepancy_category="field_mismatch",
        key_values={"id": "API-01"},
        exposure_amount=500.0,
        resolution_status="unresolved",
        cluster_id="c_api_test",
        cluster_name="API Cluster Test",
        _reason_code="FIELD_MISMATCH",
    )
    d2 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="field_mismatch",
        discrepancy_category="field_mismatch",
        key_values={"id": "API-02"},
        exposure_amount=750.0,
        resolution_status="unresolved",
        cluster_id="c_api_test",
        cluster_name="API Cluster Test",
        _reason_code="FIELD_MISMATCH",
    )
    db_session.add_all([d1, d2])
    db_session.commit()

    # 1. GET /clusters
    r_clusters = client.get(
        f"/api/v1/projects/{project.id}/runs/{run.id}/clusters",
        headers=auth_headers,
    )
    assert r_clusters.status_code == 200
    c_data = r_clusters.json()
    assert c_data["total_clusters"] >= 1
    assert c_data["total_cluster_exposure"] == 1250.0

    target_cid = c_data["clusters"][0]["cluster_id"]

    # 2. GET /clusters/{cluster_id}/records
    r_records = client.get(
        f"/api/v1/projects/{project.id}/runs/{run.id}/clusters/{target_cid}/records",
        headers=auth_headers,
    )
    assert r_records.status_code == 200
    rec_data = r_records.json()
    assert rec_data["total"] == 2
    assert len(rec_data["items"]) == 2

    # 3. POST /assignments
    r_assign = client.post(
        f"/api/v1/projects/{project.id}/runs/{run.id}/assignments",
        json={
            "reviewer_id": str(default_user.id),
            "reviewer_email": default_user.email,
            "cluster_id": target_cid,
        },
        headers=auth_headers,
    )
    assert r_assign.status_code == 200
    assert r_assign.json()["assigned_count"] == 2

    # 4. Filter by ASSIGNED_TO_ME
    r_filtered = client.get(
        f"/api/v1/projects/{project.id}/runs/{run.id}/results?assigned_to=ASSIGNED_TO_ME",
        headers=auth_headers,
    )
    assert r_filtered.status_code == 200
    assert r_filtered.json()["total"] == 2

    # 5. POST /reviews/{discrepancy_id} (single record)
    r_single = client.post(
        f"/api/v1/projects/{project.id}/runs/{run.id}/reviews/{d1.id}",
        json={
            "decision": "ESCALATE",
            "justification": "Escalated to senior controller for secondary signoff.",
        },
        headers=auth_headers,
    )
    assert r_single.status_code == 200
    assert r_single.json()["decision"] == "ESCALATE"
    assert r_single.json()["new_status"] == "ESCALATED"

    # 6. POST /reviews/bulk
    r_bulk = client.post(
        f"/api/v1/projects/{project.id}/runs/{run.id}/reviews/bulk",
        json={
            "decision": "APPROVE",
            "justification": "Bulk approval of remaining records in cluster.",
            "cluster_id": target_cid,
        },
        headers=auth_headers,
    )
    assert r_bulk.status_code == 200
    b_data = r_bulk.json()
    assert b_data["succeeded_count"] == 2
