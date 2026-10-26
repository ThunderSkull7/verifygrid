"""Bulk Human Review, Decision Persistence, Safeguards & Assignment Service.

Handles granular and cluster-level review decisions (APPROVE, REJECT, FORCE_MATCH, ESCALATE, REOPEN),
enforces justification notes, financial exposure barriers, individual audit trail entries,
and reviewer assignments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy.orm import Session

from app.models.verification_run import (
    DiscrepancyReviewDecision,
    VerificationDiscrepancy,
    VerificationRun,
)
from app.schemas.review import (
    AssignmentRequest,
    AssignmentResponse,
    BulkReviewRequest,
    BulkReviewResponse,
    ReviewDecisionItem,
    ReviewDecisionRequest,
)

# Standard decision status transitions
DECISION_TO_STATUS = {
    "APPROVE": "APPROVED",
    "REJECT": "REJECTED",
    "FORCE_MATCH": "FORCE_MATCHED",
    "ESCALATE": "ESCALATED",
    "REOPEN": "PENDING_REVIEW",
}


def _validate_decision_and_justification(decision: str, justification: Optional[str]) -> str:
    """Validate decision keyword and ensure non-empty justification."""
    dec_upper = str(decision).strip().upper()
    if dec_upper not in DECISION_TO_STATUS:
        valid_opts = ", ".join(DECISION_TO_STATUS.keys())
        raise ValueError(f"Invalid decision '{decision}'. Must be one of: {valid_opts}")

    if not justification or not justification.strip():
        raise ValueError("A justification note is required for manual overrides and review decisions.")

    return dec_upper


def apply_single_review(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    discrepancy_id: uuid.UUID,
    request: ReviewDecisionRequest,
    current_user: Optional[Any] = None,
) -> ReviewDecisionItem:
    """
    Applies a review decision to an individual discrepancy and logs an audit decision.
    """
    decision = _validate_decision_and_justification(request.decision, request.justification)
    new_status = DECISION_TO_STATUS[decision]

    # Verify run and discrepancy exist within project
    run = (
        db.query(VerificationRun)
        .filter(
            VerificationRun.id == run_id,
            VerificationRun.project_id == project_id,
        )
        .first()
    )
    if not run:
        raise ValueError(f"Verification run {run_id} not found in project {project_id}")

    disc: Optional[VerificationDiscrepancy] = (
        db.query(VerificationDiscrepancy)
        .filter(
            VerificationDiscrepancy.id == discrepancy_id,
            VerificationDiscrepancy.run_id == run_id,
        )
        .first()
    )
    if not disc:
        raise ValueError(f"Discrepancy {discrepancy_id} not found in run {run_id}")

    reviewer_id = (
        request.reviewer_id
        or (str(current_user.id) if current_user and hasattr(current_user, "id") else "system")
    )
    reviewer_email = (
        request.reviewer_email
        or (current_user.email if current_user and hasattr(current_user, "email") else None)
    )

    prev_status = disc.resolution_status or "unresolved"
    now_utc = datetime.now(timezone.utc)

    # 1. Create individual audit decision entry
    audit_entry = DiscrepancyReviewDecision(
        discrepancy_id=disc.id,
        run_id=run_id,
        decision=decision,
        justification=request.justification.strip(),
        reviewer_id=reviewer_id,
        reviewer_email=reviewer_email,
        previous_status=prev_status,
        new_status=new_status,
        is_bulk_action=False,
        cluster_id=disc.cluster_id,
        created_at=now_utc,
    )
    db.add(audit_entry)

    # 2. Update discrepancy resolution state
    disc.resolution_status = new_status
    disc.resolution_note = request.justification.strip()
    disc.resolved_by = reviewer_email or reviewer_id
    disc.resolved_at = now_utc

    db.commit()
    db.refresh(audit_entry)

    return ReviewDecisionItem(
        id=str(audit_entry.id),
        discrepancy_id=str(disc.id),
        run_id=str(run_id),
        decision=audit_entry.decision,
        justification=audit_entry.justification,
        reviewer_id=audit_entry.reviewer_id,
        reviewer_email=audit_entry.reviewer_email,
        previous_status=audit_entry.previous_status,
        new_status=audit_entry.new_status,
        is_bulk_action=audit_entry.is_bulk_action,
        cluster_id=audit_entry.cluster_id,
        created_at=audit_entry.created_at,
    )


def apply_bulk_review(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    request: BulkReviewRequest,
    current_user: Optional[Any] = None,
) -> BulkReviewResponse:
    """
    Executes a bulk review decision across records in a cluster or an explicit list of IDs.
    Enforces justification, checks financial exposure barriers, prevents silent approval
    of blocking records, and records an individual audit decision entry for every affected record.
    """
    decision = _validate_decision_and_justification(request.decision, request.justification)
    new_status = DECISION_TO_STATUS[decision]

    # Verify run exists and belongs to project
    run = (
        db.query(VerificationRun)
        .filter(
            VerificationRun.id == run_id,
            VerificationRun.project_id == project_id,
        )
        .first()
    )
    if not run:
        raise ValueError(f"Verification run {run_id} not found in project {project_id}")

    # Build query for target discrepancies
    query = db.query(VerificationDiscrepancy).filter(
        VerificationDiscrepancy.run_id == run_id
    )

    if request.cluster_id:
        query = query.filter(VerificationDiscrepancy.cluster_id == request.cluster_id)
    elif request.discrepancy_ids:
        try:
            target_uuids = [uuid.UUID(d_id) for d_id in request.discrepancy_ids]
            query = query.filter(VerificationDiscrepancy.id.in_(target_uuids))
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid discrepancy UUID list: {exc}")
    else:
        raise ValueError("Either cluster_id or discrepancy_ids must be specified for bulk review.")

    records: List[VerificationDiscrepancy] = query.all()
    total_requested = len(records)

    reviewer_id = (
        str(current_user.id) if current_user and hasattr(current_user, "id") else "reviewer"
    )
    reviewer_email = (
        current_user.email if current_user and hasattr(current_user, "email") else None
    )

    succeeded_ids: List[str] = []
    failed_records: List[Dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc)

    # Financial Exposure Safeguard: default to provided threshold or None
    max_thresh = request.max_exposure_threshold

    for disc in records:
        disc_id_str = str(disc.id)
        exposure = disc.exposure_amount or 0.0
        severity = (disc.severity or "medium").upper()

        # Check Eligibility Barriers for APPROVE and FORCE_MATCH
        if decision in ("APPROVE", "FORCE_MATCH"):
            # Barrier 1: Exposure Threshold
            if max_thresh is not None and exposure > max_thresh:
                failed_records.append(
                    {
                        "id": disc_id_str,
                        "reason": (
                            f"Exposure of {disc.currency or 'USD'} {exposure:,.2f} exceeds "
                            f"bulk approval threshold limit of {max_thresh:,.2f}."
                        ),
                    }
                )
                continue

            # Barrier 2: Hard BLOCKING Rule Failure
            if severity == "BLOCKING" and not request.allow_blocking_override:
                failed_records.append(
                    {
                        "id": disc_id_str,
                        "reason": "Hard BLOCKING rule failure cannot be bulk approved without explicit override.",
                    }
                )
                continue

        # If eligible, persist individual review decision entry
        prev_status = disc.resolution_status or "unresolved"
        audit_entry = DiscrepancyReviewDecision(
            discrepancy_id=disc.id,
            run_id=run_id,
            decision=decision,
            justification=request.justification.strip(),
            reviewer_id=reviewer_id,
            reviewer_email=reviewer_email,
            previous_status=prev_status,
            new_status=new_status,
            is_bulk_action=True,
            cluster_id=disc.cluster_id,
            created_at=now_utc,
        )
        db.add(audit_entry)

        # Update record state
        disc.resolution_status = new_status
        disc.resolution_note = request.justification.strip()
        disc.resolved_by = reviewer_email or reviewer_id
        disc.resolved_at = now_utc
        succeeded_ids.append(disc_id_str)

    db.commit()

    succeeded_count = len(succeeded_ids)
    ineligible_count = len(failed_records)
    failed_count = ineligible_count

    if ineligible_count > 0:
        msg = (
            f"Bulk review partially applied: {succeeded_count} succeeded, "
            f"{ineligible_count} blocked by eligibility safeguards."
        )
    else:
        msg = f"Bulk review successfully applied to all {succeeded_count} records."

    return BulkReviewResponse(
        total_requested=total_requested,
        succeeded_count=succeeded_count,
        failed_count=failed_count,
        ineligible_count=ineligible_count,
        succeeded_ids=succeeded_ids,
        failed_records=failed_records,
        message=msg,
    )


def assign_discrepancies(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    request: AssignmentRequest,
    current_user: Optional[Any] = None,
) -> AssignmentResponse:
    """
    Assigns designated records or an entire cluster to a specific reviewer.
    """
    if not request.reviewer_id or not request.reviewer_id.strip():
        raise ValueError("Reviewer ID or email is required for assignment.")

    run = (
        db.query(VerificationRun)
        .filter(
            VerificationRun.id == run_id,
            VerificationRun.project_id == project_id,
        )
        .first()
    )
    if not run:
        raise ValueError(f"Verification run {run_id} not found in project {project_id}")

    query = db.query(VerificationDiscrepancy).filter(
        VerificationDiscrepancy.run_id == run_id
    )

    if request.cluster_id:
        query = query.filter(VerificationDiscrepancy.cluster_id == request.cluster_id)
    elif request.discrepancy_ids:
        try:
            target_uuids = [uuid.UUID(d_id) for d_id in request.discrepancy_ids]
            query = query.filter(VerificationDiscrepancy.id.in_(target_uuids))
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid discrepancy UUID list: {exc}")
    else:
        raise ValueError("Either cluster_id or discrepancy_ids must be specified for assignment.")

    records = query.all()
    target_assignee = request.reviewer_email or request.reviewer_id.strip()
    now_utc = datetime.now(timezone.utc)
    assigned_ids: List[str] = []

    for r in records:
        r.assigned_to = target_assignee
        r.assigned_at = now_utc
        assigned_ids.append(str(r.id))

    db.commit()

    return AssignmentResponse(
        assigned_count=len(assigned_ids),
        reviewer_id=target_assignee,
        discrepancy_ids=assigned_ids,
        message=f"Successfully assigned {len(assigned_ids)} records to {target_assignee}.",
    )
