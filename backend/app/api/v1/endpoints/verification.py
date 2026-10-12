"""API router for data verification, matching, and reconciliation."""

from __future__ import annotations

from typing import Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.result import (
    DiscrepancyItemResponse,
    DiscrepancyListResponse,
    VerificationRequest,
    VerificationResponse,
    VerificationRunListResponse,
    VerificationRunResponse,
)
from app.services.verification_engine import (
    create_and_execute_verification_run,
    get_verification_run,
    list_run_discrepancies,
    list_verification_runs,
    verify_project_files,
)

router = APIRouter()


@router.post(
    "/projects/{project_id}/verify",
    response_model=VerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconcile and verify two datasets in a project (in-memory)",
    description=(
        "Executes core verification engine comparing two source files belonging to an "
        "authorized project. Identifies matching records, missing records, duplicate keys, "
        "and field-level discrepancies."
    ),
)
def verify_project_files_endpoint(
    project_id: uuid.UUID,
    request: VerificationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VerificationResponse:
    """Trigger on-demand dataset verification for two project source files."""
    return verify_project_files(
        db=db,
        project_id=project_id,
        request=request,
        current_user=current_user,
    )


@router.post(
    "/projects/{project_id}/runs",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and execute a persistent verification run",
    description="Creates a persistent verification run, reconciles datasets, and persists summary metrics and discrepancies.",
)
def create_verification_run_endpoint(
    project_id: uuid.UUID,
    request: VerificationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VerificationRunResponse:
    """Create and execute a persistent verification run."""
    run = create_and_execute_verification_run(
        db=db,
        project_id=project_id,
        request=request,
        current_user=current_user,
    )
    return VerificationRunResponse.model_validate(run)


@router.get(
    "/projects/{project_id}/runs",
    response_model=VerificationRunListResponse,
    status_code=status.HTTP_200_OK,
    summary="List verification runs for a project",
    description="Retrieves a paginated list of verification runs belonging to an authorized project.",
)
def list_verification_runs_endpoint(
    project_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VerificationRunListResponse:
    """List verification runs with pagination."""
    total, items = list_verification_runs(
        db=db,
        project_id=project_id,
        current_user=current_user,
        skip=skip,
        limit=limit,
        status_filter=status_filter,
    )
    return VerificationRunListResponse(
        total=total,
        items=[VerificationRunResponse.model_validate(r) for r in items],
        skip=skip,
        limit=limit,
    )


@router.get(
    "/projects/{project_id}/runs/{run_id}",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get verification run details",
    description="Retrieves metadata, status, and summary metrics for a specific verification run.",
)
def get_verification_run_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VerificationRunResponse:
    """Get run details."""
    run = get_verification_run(db=db, project_id=project_id, run_id=run_id, current_user=current_user)
    return VerificationRunResponse.model_validate(run)


@router.get(
    "/projects/{project_id}/runs/{run_id}/results",
    response_model=DiscrepancyListResponse,
    status_code=status.HTTP_200_OK,
    summary="Paginate and filter verification run discrepancies",
    description="Retrieves paginated discrepancy results with optional category and match status filtering.",
)
def list_run_discrepancies_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    discrepancy_category: Optional[str] = Query(None),
    match_status: Optional[str] = Query(None),
    sort_by: str = Query("source_row_number", description="Field to sort by"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$", description="'asc' or 'desc'"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiscrepancyListResponse:
    """Paginate, filter, and sort run discrepancies."""
    total, items = list_run_discrepancies(
        db=db,
        project_id=project_id,
        run_id=run_id,
        current_user=current_user,
        skip=skip,
        limit=limit,
        discrepancy_category=discrepancy_category,
        match_status=match_status,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return DiscrepancyListResponse(
        total=total,
        items=[DiscrepancyItemResponse.model_validate(d) for d in items],
        skip=skip,
        limit=limit,
    )


@router.get(
    "/projects/{project_id}/runs/{run_id}/summary",
    status_code=status.HTTP_200_OK,
    summary="Get verification run summary metrics",
    description="Retrieves summary metrics dictionary for a specific verification run.",
)
def get_run_summary_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get run summary metrics."""
    run = get_verification_run(db=db, project_id=project_id, run_id=run_id, current_user=current_user)
    return run.summary or {}


