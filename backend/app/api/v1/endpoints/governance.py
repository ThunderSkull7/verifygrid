from __future__ import annotations

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_project_access
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.governance import (
    ApproveSignOffRequest,
    ProposeSignOffRequest,
    RejectSignOffRequest,
    SignOffDetailsResponse,
)
from app.services.governance_service import (
    approve_run_sign_off,
    get_sign_off_details,
    propose_run_sign_off,
    reject_run_sign_off,
)

router = APIRouter(tags=["governance"])


@router.get(
    "/projects/{project_id}/runs/{run_id}/sign-off",
    response_model=SignOffDetailsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get run sign-off governance details",
    description="Retrieve maker proposal and checker decision details for a verification run.",
)
def get_run_sign_off_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> SignOffDetailsResponse:
    """Retrieve sign-off status and approval eligibility."""
    return get_sign_off_details(
        db=db,
        project_id=project_id,
        run_id=run_id,
        user=current_user,
        role_override=x_user_role,
    )


@router.post(
    "/projects/{project_id}/runs/{run_id}/sign-off/propose",
    response_model=SignOffDetailsResponse,
    status_code=status.HTTP_200_OK,
    summary="Propose run sign-off (Maker action)",
    description="Maker submits reconciliation package for sign-off review. Sets state to AWAITING_SIGN_OFF.",
)
def propose_sign_off_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    request: ProposeSignOffRequest,
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> SignOffDetailsResponse:
    """Propose reconciliation sign-off."""
    return propose_run_sign_off(
        db=db,
        project_id=project_id,
        run_id=run_id,
        user=current_user,
        request=request,
        role_override=x_user_role,
    )


@router.post(
    "/projects/{project_id}/runs/{run_id}/sign-off/approve",
    response_model=SignOffDetailsResponse,
    status_code=status.HTTP_200_OK,
    summary="Countersign and approve run sign-off (Checker action)",
    description="Checker countersigns sign-off package. Strictly enforces Maker-Checker separation of duties.",
)
def approve_sign_off_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    request: ApproveSignOffRequest,
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> SignOffDetailsResponse:
    """Approve reconciliation sign-off."""
    return approve_run_sign_off(
        db=db,
        project_id=project_id,
        run_id=run_id,
        user=current_user,
        request=request,
        role_override=x_user_role,
    )


@router.post(
    "/projects/{project_id}/runs/{run_id}/sign-off/reject",
    response_model=SignOffDetailsResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject run sign-off with mandatory reason (Checker action)",
    description="Checker rejects proposed sign-off package with mandatory justification note.",
)
def reject_sign_off_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    request: RejectSignOffRequest,
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> SignOffDetailsResponse:
    """Reject reconciliation sign-off."""
    return reject_run_sign_off(
        db=db,
        project_id=project_id,
        run_id=run_id,
        user=current_user,
        request=request,
        role_override=x_user_role,
    )
