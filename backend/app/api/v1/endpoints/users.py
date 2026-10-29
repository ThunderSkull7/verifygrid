"""Admin-only user administration endpoints.

Role elevation is deliberately separate from registration. Only an
authenticated user whose authoritative ``users.role`` is ``ADMIN`` may change
another account's role; the target role is constrained by the
``UserRoleUpdateRequest`` literal so invalid, null, empty, or case-variant
values are rejected with 422.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_authoritative_role, require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import UserResponse, UserRoleUpdateRequest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Change a user's role (ADMIN only)",
    description=(
        "Elevates or changes an account role. Requires an authenticated ADMIN; "
        "the target role must be exactly MAKER, CHECKER, ADMIN, or VIEWER."
    ),
)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Persist an admin-authorized role change.

    ``audit_events.project_id`` is non-null and role changes are not scoped to
    a project, so the change is recorded in the structured application audit
    log rather than the per-run hash chain. Database-level role auditing
    requires a schema change outside Batch 26A.
    """
    target_user = db.query(User).filter(User.id == user_id).first()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    previous_role = str(getattr(target_user, "role", "") or "")
    actor_role = get_authoritative_role(current_user)

    target_user.role = payload.role
    db.commit()
    db.refresh(target_user)

    logger.info(
        "role_change actor_id=%s actor_role=%s target_id=%s previous_role=%s new_role=%s",
        current_user.id,
        actor_role,
        target_user.id,
        previous_role,
        target_user.role,
    )

    return UserResponse.model_validate(target_user)
