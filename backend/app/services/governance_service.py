from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.models.user import User
from app.models.verification_run import VerificationRun
from app.schemas.governance import (
    ApproveSignOffRequest,
    ProposeSignOffRequest,
    RejectSignOffRequest,
    SignOffDetailsResponse,
    SignOffStatus,
    UserRole,
)
from app.schemas.audit import AuditEventType
from app.services.audit_service import log_audit_event


def get_effective_user_role(user: User, role_override: Optional[str] = None) -> str:
    """
    Return user's effective role, honoring valid header overrides if present.
    """
    if role_override:
        norm = role_override.strip().upper()
        if norm in (UserRole.MAKER.value, UserRole.CHECKER.value, UserRole.ADMIN.value, UserRole.VIEWER.value):
            return norm
    return getattr(user, "role", UserRole.MAKER.value) or UserRole.MAKER.value


def propose_run_sign_off(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User,
    request: ProposeSignOffRequest,
    role_override: Optional[str] = None,
) -> SignOffDetailsResponse:
    """
    Maker proposes run sign-off with optional notes.
    Transitions run to AWAITING_SIGN_OFF.
    """
    effective_role = get_effective_user_role(user, role_override)

    # Viewers cannot propose sign-off
    if effective_role == UserRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers do not have permission to propose sign-offs.",
        )

    # Checkers without maker privileges cannot propose sign-off
    if effective_role not in (UserRole.MAKER.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only users with role MAKER or ADMIN can propose reconciliation sign-off.",
        )

    # Find verification run within project
    run = db.execute(
        select(VerificationRun).where(
            and_(VerificationRun.id == run_id, VerificationRun.project_id == project_id)
        )
    ).scalar_one_or_none()

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification run {run_id} not found in project {project_id}.",
        )

    maker_name = request.proposed_by_name or getattr(user, "full_name", None) or user.email
    now = datetime.now(timezone.utc)

    run.sign_off_status = SignOffStatus.AWAITING_SIGN_OFF.value
    run.sign_off_proposed_by = user.id
    run.sign_off_proposed_by_name = maker_name
    run.sign_off_proposal_note = request.note
    run.sign_off_proposed_at = now

    # Reset any prior checker decision
    run.sign_off_approved_by = None
    run.sign_off_approved_by_name = None
    run.sign_off_decision_note = None
    run.sign_off_decided_at = None

    db.flush()

    # Append tamper-evident audit event
    log_audit_event(
        db=db,
        project_id=project_id,
        run_id=run_id,
        event_type=AuditEventType.RUN_SIGN_OFF_PROPOSED.value,
        event_payload={
            "action": "PROPOSE_SIGN_OFF",
            "proposed_by": str(user.id),
            "maker_name": maker_name,
            "note": request.note,
            "previous_status": "DRAFT",
            "new_status": SignOffStatus.AWAITING_SIGN_OFF.value,
        },
        user_id=user.id,
        user_email=user.email,
        user_role=effective_role,
        timestamp_utc=now,
    )

    return get_sign_off_details(db, project_id, run_id, user, role_override)


def approve_run_sign_off(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User,
    request: ApproveSignOffRequest,
    role_override: Optional[str] = None,
) -> SignOffDetailsResponse:
    """
    Checker countersigns and approves run sign-off.
    Enforces strict Maker-Checker Separation of Duties (user != maker).
    """
    effective_role = get_effective_user_role(user, role_override)

    # Role authorization check: only CHECKER or ADMIN can approve
    if effective_role not in (UserRole.CHECKER.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{effective_role}' lacks authority to approve sign-offs; requires CHECKER or ADMIN.",
        )

    run = db.execute(
        select(VerificationRun).where(
            and_(VerificationRun.id == run_id, VerificationRun.project_id == project_id)
        )
    ).scalar_one_or_none()

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification run {run_id} not found in project {project_id}.",
        )

    # SEPARATION OF DUTIES ENFORCEMENT:
    # A user who proposed/created the action CANNOT approve or countersign their own proposal.
    if run.sign_off_proposed_by is not None and run.sign_off_proposed_by == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Separation of Duties violation: The Maker who proposed sign-off cannot countersign or approve their own submission.",
        )

    checker_name = request.approved_by_name or getattr(user, "full_name", None) or user.email
    now = datetime.now(timezone.utc)

    run.sign_off_status = SignOffStatus.APPROVED.value
    run.sign_off_approved_by = user.id
    run.sign_off_approved_by_name = checker_name
    run.sign_off_decision_note = request.note
    run.sign_off_decided_at = now

    db.flush()

    # Append CHECKER_COUNTERSIGNED and RUN_SIGN_OFF_APPROVED audit events
    log_audit_event(
        db=db,
        project_id=project_id,
        run_id=run_id,
        event_type=AuditEventType.CHECKER_COUNTERSIGNED.value,
        event_payload={
            "action": "COUNTERSIGN_APPROVE",
            "approved_by": str(user.id),
            "checker_name": checker_name,
            "note": request.note,
            "proposed_by": str(run.sign_off_proposed_by) if run.sign_off_proposed_by else None,
        },
        user_id=user.id,
        user_email=user.email,
        user_role=effective_role,
        timestamp_utc=now,
    )

    log_audit_event(
        db=db,
        project_id=project_id,
        run_id=run_id,
        event_type=AuditEventType.RUN_SIGN_OFF_APPROVED.value,
        event_payload={
            "status": SignOffStatus.APPROVED.value,
            "final_approved_by": str(user.id),
            "checker_name": checker_name,
            "note": request.note,
        },
        user_id=user.id,
        user_email=user.email,
        user_role=effective_role,
        timestamp_utc=now,
    )

    return get_sign_off_details(db, project_id, run_id, user, role_override)


def reject_run_sign_off(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User,
    request: RejectSignOffRequest,
    role_override: Optional[str] = None,
) -> SignOffDetailsResponse:
    """
    Checker rejects sign-off package with mandatory justification.
    """
    effective_role = get_effective_user_role(user, role_override)

    if effective_role not in (UserRole.CHECKER.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{effective_role}' lacks authority to reject sign-offs; requires CHECKER or ADMIN.",
        )

    if not request.note or not request.note.strip():
        raise HTTPException(
            status_code=422,
            detail="Mandatory justification note is required to reject a sign-off proposal.",
        )

    run = db.execute(
        select(VerificationRun).where(
            and_(VerificationRun.id == run_id, VerificationRun.project_id == project_id)
        )
    ).scalar_one_or_none()

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification run {run_id} not found in project {project_id}.",
        )

    # Separation of duties: proposer cannot reject their own proposal to masquerade as checker
    if run.sign_off_proposed_by is not None and run.sign_off_proposed_by == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Separation of Duties violation: The Maker cannot review or reject their own sign-off proposal.",
        )

    checker_name = getattr(user, "full_name", None) or user.email
    now = datetime.now(timezone.utc)

    run.sign_off_status = SignOffStatus.REJECTED.value
    run.sign_off_decision_note = request.note.strip()
    run.sign_off_decided_at = now

    db.flush()

    log_audit_event(
        db=db,
        project_id=project_id,
        run_id=run_id,
        event_type=AuditEventType.RUN_SIGN_OFF_REJECTED.value,
        event_payload={
            "action": "REJECT_WITH_REASON",
            "rejected_by": str(user.id),
            "checker_name": checker_name,
            "rejection_reason": request.note.strip(),
            "proposed_by": str(run.sign_off_proposed_by) if run.sign_off_proposed_by else None,
        },
        user_id=user.id,
        user_email=user.email,
        user_role=effective_role,
        timestamp_utc=now,
    )

    return get_sign_off_details(db, project_id, run_id, user, role_override)


def get_sign_off_details(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User,
    role_override: Optional[str] = None,
) -> SignOffDetailsResponse:
    """
    Retrieve current sign-off status and evaluate whether the user can approve.
    """
    effective_role = get_effective_user_role(user, role_override)

    run = db.execute(
        select(VerificationRun).where(
            and_(VerificationRun.id == run_id, VerificationRun.project_id == project_id)
        )
    ).scalar_one_or_none()

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification run {run_id} not found in project {project_id}.",
        )

    is_maker = bool(run.sign_off_proposed_by and run.sign_off_proposed_by == user.id)
    can_approve = bool(
        effective_role in (UserRole.CHECKER.value, UserRole.ADMIN.value)
        and not is_maker
        and run.sign_off_status == SignOffStatus.AWAITING_SIGN_OFF.value
    )

    return SignOffDetailsResponse(
        run_id=run.id,
        project_id=run.project_id,
        sign_off_status=run.sign_off_status or SignOffStatus.DRAFT.value,
        sign_off_proposed_by=run.sign_off_proposed_by,
        sign_off_proposed_by_name=run.sign_off_proposed_by_name,
        sign_off_proposal_note=run.sign_off_proposal_note,
        sign_off_proposed_at=run.sign_off_proposed_at,
        sign_off_approved_by=run.sign_off_approved_by,
        sign_off_approved_by_name=run.sign_off_approved_by_name,
        sign_off_decision_note=run.sign_off_decision_note,
        sign_off_decided_at=run.sign_off_decided_at,
        can_approve=can_approve,
        is_maker=is_maker,
    )
