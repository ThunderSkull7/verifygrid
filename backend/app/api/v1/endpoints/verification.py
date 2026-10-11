"""API router for data verification, matching, and reconciliation."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.result import VerificationRequest, VerificationResponse
from app.services.verification_engine import verify_project_files

router = APIRouter()


@router.post(
    "/projects/{project_id}/verify",
    response_model=VerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconcile and verify two datasets in a project",
    description=(
        "Executes core verification engine comparing two source files belonging to an "
        "authorized project. Identifies matching records, missing records, duplicate keys, "
        "and field-level discrepancies."
    ),
)
def verify_project_files_endpoint(
    project_id: uuid.UUID,
    request: VerificationRequest,
    db: Session = Depends(get_db),
) -> VerificationResponse:
    """Trigger dataset verification for two project source files."""
    return verify_project_files(
        db=db,
        project_id=project_id,
        request=request,
    )
