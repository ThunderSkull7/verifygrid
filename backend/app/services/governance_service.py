"""Maker-checker sign-off governance service.

Security boundary (Batch 24 D3): the effective role is resolved only from the
authenticated ``users.role`` value. There is no header, query, body, or JWT
role override. Missing, null, or unrecognized roles fail closed with 403.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.verification_run import VerificationRun
from app.schemas.audit import AuditEventType
from app.schemas.governance import (
    ApproveSignOffRequest,
    ProposeSignOffRequest,
    RejectSignOffRequest,
    SignOffDetailsResponse,
    SignOffStatus,
    UserRole,
)
from app.services.audit_service import log_audit_event

VALID_ROLES = {role.value for role in UserRole}


def get_effective_user_role(user: User) -> str:
    """Return the authoritative server-side role or fail closed.

    No override parameter exists. This is intentionally stricter than the
    deployed helper that trusted ``X-User-Role``.
    """
    raw = getattr(user, "role", None)
    norm = str(raw).strip().upper() if raw is not None else ""
    if norm not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Authenticated user has no recognized role; governance actions "
                "are denied."
            ),
        )
    return norm


def _get_run(db: Session, project_id: uuid.UUID, run_id: uuid.UUID) -> VerificationRun:
    run = db.execute(
        select(VerificationRun).where(
            and_(
                VerificationRun.id == run_id,
                VerificationRun.project_id == project_id,
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification run {run_id} not found in project {project_id}.",
        )
    return run


def _display_name(user: User) -> str:
    return getattr(user, "full_name", None) or user.email


def propose_run_sign_off(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User,
    request: ProposeSignOffRequest,
) -> SignOffDetailsResponse:
    """Maker proposes run sign-off and transitions to AWAITING_SIGN_OFF."""
    effective_role = get_effective_user_role(user)

    if effective_role == UserRole.VIEWER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers do not have permission to propose sign-offs.",
        )
    if effective_role not in (UserRole.MAKER.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only users with role MAKER or ADMIN can propose reconciliation sign-off.",
        )

    run = _get_run(db, project_id, run_id)
    previous_status = run.sign_off_status or SignOffStatus.DRAFT.value
    maker_name = _display_name(user)
    now = datetime.now(timezone.utc)

    run.sign_off_status = SignOffStatus.AWAITING_SIGN_OFF.value
    run.sign_off_proposed_by = user.id
    run.sign_off_proposed_by_name = maker_name
    run.sign_off_proposal_note = request.note
    run.sign_off_proposed_at = now

    # Reset any prior checker decision.
    run.sign_off_approved_by = None
    run.sign_off_approved_by_name = None
    run.sign_off_decision_note = None
    run.sign_off_decided_at = None

    db.flush()
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
            "previous_status": previous_status,
            "new_status": SignOffStatus.AWAITING_SIGN_OFF.value,
        },
        user_id=user.id,
        user_email=user.email,
        user_role=effective_role,
        timestamp_utc=now,
    )
    # The deployed implementation forgot to commit, so its sign-off writes were
    # rolled back when the request session closed. Commit explicitly.
    db.commit()

    return get_sign_off_details(db, project_id, run_id, user)


def approve_run_sign_off(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User,
    request: ApproveSignOffRequest,
) -> SignOffDetailsResponse:
    """Checker countersigns and approves a pending run sign-off."""
    effective_role = get_effective_user_role(user)

    if effective_role not in (UserRole.CHECKER.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{effective_role}' lacks authority to approve sign-offs; "
                "requires CHECKER or ADMIN."
            ),
        )

    run = _get_run(db, project_id, run_id)
    if run.sign_off_status != SignOffStatus.AWAITING_SIGN_OFF.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Sign-off can only be approved while status is "
                "AWAITING_SIGN_OFF."
            ),
        )

    # Separation of duties: the maker cannot countersign their own proposal.
    if run.sign_off_proposed_by is not None and run.sign_off_proposed_by == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Separation of Duties violation: The Maker who proposed sign-off "
                "cannot countersign or approve their own submission."
            ),
        )

    checker_name = _display_name(user)
    now = datetime.now(timezone.utc)

    run.sign_off_status = SignOffStatus.APPROVED.value
    run.sign_off_approved_by = user.id
    run.sign_off_approved_by_name = checker_name
    run.sign_off_decision_note = request.note
    run.sign_off_decided_at = now
    db.flush()

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
            "proposed_by": (
                str(run.sign_off_proposed_by) if run.sign_off_proposed_by else None
            ),
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
    db.commit()

    return get_sign_off_details(db, project_id, run_id, user)


def reject_run_sign_off(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User,
    request: RejectSignOffRequest,
) -> SignOffDetailsResponse:
    """Checker rejects a pending sign-off with mandatory justification."""
    effective_role = get_effective_user_role(user)

    if effective_role not in (UserRole.CHECKER.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{effective_role}' lacks authority to reject sign-offs; "
                "requires CHECKER or ADMIN."
            ),
        )

    if not request.note or not request.note.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mandatory justification note is required to reject a sign-off proposal.",
        )

    run = _get_run(db, project_id, run_id)
    if run.sign_off_status != SignOffStatus.AWAITING_SIGN_OFF.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Sign-off can only be rejected while status is AWAITING_SIGN_OFF."
            ),
        )

    if run.sign_off_proposed_by is not None and run.sign_off_proposed_by == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Separation of Duties violation: The Maker cannot review or reject "
                "their own sign-off proposal."
            ),
        )

    checker_name = _display_name(user)
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
            "proposed_by": (
                str(run.sign_off_proposed_by) if run.sign_off_proposed_by else None
            ),
        },
        user_id=user.id,
        user_email=user.email,
        user_role=effective_role,
        timestamp_utc=now,
    )
    db.commit()

    return get_sign_off_details(db, project_id, run_id, user)


def get_sign_off_details(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user: User,
) -> SignOffDetailsResponse:
    """Retrieve sign-off state and evaluate approval eligibility."""
    effective_role = get_effective_user_role(user)
    run = _get_run(db, project_id, run_id)

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
