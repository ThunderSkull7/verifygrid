from __future__ import annotations

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_project_access
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.audit import (
    AuditTrailResponse,
    AuditVerificationResponse,
)
from app.services.audit_service import (
    get_audit_trail,
    verify_audit_chain,
)

router = APIRouter(tags=["audit"])


@router.get(
    "/projects/{project_id}/runs/{run_id}/audit-trail",
    response_model=AuditTrailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get paginated append-only audit trail",
    description="Retrieve cryptographic append-only audit events with hash chaining for a verification run.",
)
def get_run_audit_trail_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuditTrailResponse:
    """Retrieve audit events."""
    return get_audit_trail(
        db=db,
        project_id=project_id,
        run_id=run_id,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/projects/{project_id}/runs/{run_id}/audit-trail/verify",
    response_model=AuditVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify cryptographic audit chain integrity",
    description="Recalculates SHA-256 hash chaining from genesis to head and detects broken links or tampering.",
)
def verify_run_audit_chain_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuditVerificationResponse:
    """Verify cryptographic audit chain."""
    return verify_audit_chain(
        db=db,
        project_id=project_id,
        run_id=run_id,
    )
