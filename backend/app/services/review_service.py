"""Bulk human review, decision persistence, safeguards, and assignment.

Security boundary: reviewer identity is derived from the authenticated
principal. Client-supplied ``reviewer_id`` / ``reviewer_email`` fields on review
decisions are accepted only for wire compatibility and are ignored.

Schema boundary: ``discrepancy_review_decisions`` is created by the pending
``0006_discrepancy_review_decisions`` migration. Until it exists, review writes
return an explicit 503 instead of leaking a database error.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.verification_run import (
    DiscrepancyReviewDecision,
    VerificationDiscrepancy,
    VerificationRun,
)
from app.schemas.audit import AuditEventType
from app.schemas.review import (
    AssignmentRequest,
    AssignmentResponse,
    BulkReviewRequest,
    BulkReviewResponse,
    ReviewDecisionItem,
    ReviewDecisionRequest,
)
from app.services.audit_service import log_audit_event

# Standard decision status transitions.
DECISION_TO_STATUS = {
    "APPROVE": "APPROVED",
    "REJECT": "REJECTED",
    "FORCE_MATCH": "FORCE_MATCHED",
    "ESCALATE": "ESCALATED",
    "REOPEN": "PENDING_REVIEW",
}

_REVIEW_TABLE = "discrepancy_review_decisions"


def ensure_review_schema(db: Session) -> None:
    """Fail explicitly when the pending 0006 review table is unavailable."""
    bind = db.get_bind()
    if bind is not None and not inspect(bind).has_table(_REVIEW_TABLE):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Review decisions require the discrepancy_review_decisions "
                "table, which is deferred to the Batch 26C migration."
            ),
        )


def _review_identity(current_user: Any) -> tuple[str, Optional[str], str]:
    """Return (reviewer_id, reviewer_email, authoritative_role) from the principal."""
    if current_user is None:
        raise ValueError("An authenticated reviewer is required.")
    reviewer_id = str(getattr(current_user, "id", "") or "").strip()
    if not reviewer_id:
        raise ValueError("An authenticated reviewer is required.")
    reviewer_email = getattr(current_user, "email", None)
    raw_role = getattr(current_user, "role", None)
    role = str(raw_role).strip().upper() if raw_role is not None else "UNKNOWN"
    if role not in {"MAKER", "CHECKER", "ADMIN", "VIEWER"}:
        role = "UNKNOWN"
    return reviewer_id, reviewer_email, role


def _validate_decision_and_justification(
    decision: str,
    justification: Optional[str],
) -> str:
    """Validate the decision keyword and mandatory bounded justification."""
    dec_upper = str(decision).strip().upper()
    if dec_upper not in DECISION_TO_STATUS:
        valid_opts = ", ".join(DECISION_TO_STATUS.keys())
        raise ValueError(f"Invalid decision '{decision}'. Must be one of: {valid_opts}")

    if not justification or not justification.strip():
        raise ValueError(
            "A justification note is required for manual overrides and review decisions."
        )
    if len(justification.strip()) > 10000:
        raise ValueError("Justification must not exceed 10000 characters.")

    return dec_upper


def _get_run(db: Session, project_id: uuid.UUID, run_id: uuid.UUID) -> VerificationRun:
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
    return run


def apply_single_review(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    discrepancy_id: uuid.UUID,
    request: ReviewDecisionRequest,
    current_user: Optional[Any] = None,
) -> ReviewDecisionItem:
    """Apply one review decision and record an immutable audit trail entry."""
    ensure_review_schema(db)
    decision = _validate_decision_and_justification(
        request.decision, request.justification
    )
    new_status = DECISION_TO_STATUS[decision]
    reviewer_id, reviewer_email, user_role = _review_identity(current_user)

    _get_run(db, project_id, run_id)
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

    prev_status = disc.resolution_status or "unresolved"
    now_utc = datetime.now(timezone.utc)
    justification = request.justification.strip()

    audit_entry = DiscrepancyReviewDecision(
        discrepancy_id=disc.id,
        run_id=run_id,
        decision=decision,
        justification=justification,
        reviewer_id=reviewer_id,
        reviewer_email=reviewer_email,
        previous_status=prev_status,
        new_status=new_status,
        is_bulk_action=False,
        cluster_id=disc.cluster_id,
        created_at=now_utc,
    )
    db.add(audit_entry)

    disc.resolution_status = new_status
    disc.resolution_note = justification
    disc.resolved_by = reviewer_email or reviewer_id
    disc.resolved_at = now_utc

    log_audit_event(
        db=db,
        project_id=project_id,
        run_id=run_id,
        event_type=AuditEventType.EXCEPTION_REVIEW_PROPOSED.value,
        event_payload={
            "action": "SINGLE_REVIEW",
            "discrepancy_id": str(disc.id),
            "decision": decision,
            "justification": justification,
            "previous_status": prev_status,
            "new_status": new_status,
            "cluster_id": disc.cluster_id,
        },
        user_id=getattr(current_user, "id", None),
        user_email=reviewer_email,
        user_role=user_role,
        timestamp_utc=now_utc,
    )

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
    """Apply a decision to a cluster or explicit list of discrepancies.

    Financial-exposure and BLOCKING-rule safeguards are retained from the
    deployed implementation.
    """
    ensure_review_schema(db)
    decision = _validate_decision_and_justification(
        request.decision, request.justification
    )
    new_status = DECISION_TO_STATUS[decision]
    reviewer_id, reviewer_email, user_role = _review_identity(current_user)

    _get_run(db, project_id, run_id)
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
        raise ValueError(
            "Either cluster_id or discrepancy_ids must be specified for bulk review."
        )

    records: List[VerificationDiscrepancy] = query.all()
    total_requested = len(records)

    succeeded_ids: List[str] = []
    failed_records: List[Dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc)
    justification = request.justification.strip()
    max_thresh = request.max_exposure_threshold

    for disc in records:
        disc_id_str = str(disc.id)
        exposure = disc.exposure_amount or 0.0
        severity = (disc.severity or "medium").upper()

        if decision in ("APPROVE", "FORCE_MATCH"):
            if max_thresh is not None and exposure > max_thresh:
                failed_records.append(
                    {
                        "id": disc_id_str,
                        "reason": (
                            f"Exposure of {disc.currency or 'USD'} {exposure:,.2f} "
                            f"exceeds bulk approval threshold limit of "
                            f"{max_thresh:,.2f}."
                        ),
                    }
                )
                continue

            if severity == "BLOCKING" and not request.allow_blocking_override:
                failed_records.append(
                    {
                        "id": disc_id_str,
                        "reason": (
                            "Hard BLOCKING rule failure cannot be bulk approved "
                            "without explicit override."
                        ),
                    }
                )
                continue

        prev_status = disc.resolution_status or "unresolved"
        audit_entry = DiscrepancyReviewDecision(
            discrepancy_id=disc.id,
            run_id=run_id,
            decision=decision,
            justification=justification,
            reviewer_id=reviewer_id,
            reviewer_email=reviewer_email,
            previous_status=prev_status,
            new_status=new_status,
            is_bulk_action=True,
            cluster_id=disc.cluster_id,
            created_at=now_utc,
        )
        db.add(audit_entry)

        disc.resolution_status = new_status
        disc.resolution_note = justification
        disc.resolved_by = reviewer_email or reviewer_id
        disc.resolved_at = now_utc
        succeeded_ids.append(disc_id_str)

    if succeeded_ids:
        log_audit_event(
            db=db,
            project_id=project_id,
            run_id=run_id,
            event_type=AuditEventType.EXCEPTION_REVIEW_PROPOSED.value,
            event_payload={
                "action": "BULK_REVIEW",
                "decision": decision,
                "justification": justification,
                "succeeded_count": len(succeeded_ids),
                "ineligible_count": len(failed_records),
                "cluster_id": request.cluster_id,
            },
            user_id=getattr(current_user, "id", None),
            user_email=reviewer_email,
            user_role=user_role,
            timestamp_utc=now_utc,
        )

    db.commit()

    succeeded_count = len(succeeded_ids)
    ineligible_count = len(failed_records)

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
        failed_count=ineligible_count,
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
    """Assign designated records or an entire cluster to a reviewer."""
    if current_user is None:
        raise ValueError("An authenticated user is required to assign records.")

    if not request.reviewer_id or not request.reviewer_id.strip():
        raise ValueError("Reviewer ID or email is required for assignment.")

    target_assignee = (request.reviewer_email or request.reviewer_id).strip()
    if len(target_assignee) > 100:
        raise ValueError(
            "Assignee must not exceed 100 characters (assigned_to column limit)."
        )

    _get_run(db, project_id, run_id)
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
        raise ValueError(
            "Either cluster_id or discrepancy_ids must be specified for assignment."
        )

    records = query.all()
    now_utc = datetime.now(timezone.utc)
    assigned_ids: List[str] = []

    for record in records:
        record.assigned_to = target_assignee
        record.assigned_at = now_utc
        assigned_ids.append(str(record.id))

    db.commit()

    return AssignmentResponse(
        assigned_count=len(assigned_ids),
        reviewer_id=target_assignee,
        discrepancy_ids=assigned_ids,
        message=f"Successfully assigned {len(assigned_ids)} records to {target_assignee}.",
    )
