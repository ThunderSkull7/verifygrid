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
    MultiSourceVerificationRequest,
    MultiSourceVerificationResponse,
    SideBySideInspectionResponse,
    VerificationRequest,
    VerificationResponse,
    VerificationRunListResponse,
    VerificationRunResponse,
)
from app.services.verification_engine import (
    create_and_execute_multisource_run,
    create_and_execute_verification_run,
    get_discrepancy_inspection,
    get_verification_run,
    list_run_discrepancies,
    list_verification_runs,
    verify_multisource_project_files,
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


@router.post(
    "/projects/{project_id}/verify/multi-source",
    response_model=MultiSourceVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconcile 2, 3, or more datasets in a project (in-memory)",
    description="Multi-source reconciliation aligning arbitrary datasets with source-row index lineage.",
)
def verify_multisource_files_endpoint(
    project_id: uuid.UUID,
    request: MultiSourceVerificationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MultiSourceVerificationResponse:
    """Trigger on-demand multi-source reconciliation."""
    return verify_multisource_project_files(
        db=db,
        project_id=project_id,
        request=request,
        current_user=current_user,
    )


@router.post(
    "/projects/{project_id}/runs/multi-source",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and execute a persistent multi-source verification run",
    description="Creates a persistent multi-source verification run across 2, 3, or more sources.",
)
def create_multisource_run_endpoint(
    project_id: uuid.UUID,
    request: MultiSourceVerificationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VerificationRunResponse:
    """Create and execute a persistent multi-source verification run."""
    run = create_and_execute_multisource_run(
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
    description="Retrieves paginated discrepancy results with financial exposure sorting and range filtering.",
)
def list_run_discrepancies_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    discrepancy_category: Optional[str] = Query(None),
    match_status: Optional[str] = Query(None),
    min_amount: Optional[float] = Query(None, description="Minimum monetary exposure/amount"),
    max_amount: Optional[float] = Query(None, description="Maximum monetary exposure/amount"),
    reason_code: Optional[str] = Query(None, description="Decision reason code"),
    source_alias: Optional[str] = Query(None, description="Multi-source participating alias"),
    rule_failure_type: Optional[str] = Query(None, description="Rule violation or failure type"),
    resolution_status: Optional[str] = Query(None, description="Resolution status ('resolved', 'unresolved')"),
    assigned_to: Optional[str] = Query(None, description="Filter by assigned reviewer or 'ASSIGNED_TO_ME' or 'UNASSIGNED'"),
    cluster_id: Optional[str] = Query(None, description="Filter by exception cluster ID"),
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
        min_amount=min_amount,
        max_amount=max_amount,
        reason_code=reason_code,
        source_alias=source_alias,
        rule_failure_type=rule_failure_type,
        resolution_status=resolution_status,
        assigned_to=assigned_to,
        cluster_id=cluster_id,
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
    "/projects/{project_id}/runs/{run_id}/results/{discrepancy_id}/inspect",
    response_model=SideBySideInspectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get side-by-side record inspection and field-level diffs",
    description="Retrieves raw vs. normalized side-by-side comparison, field mismatches, and rule failure details for a discrepancy.",
)
def get_discrepancy_inspection_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    discrepancy_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SideBySideInspectionResponse:
    """Get detailed side-by-side inspection for a discrepancy."""
    return get_discrepancy_inspection(
        db=db,
        project_id=project_id,
        run_id=run_id,
        discrepancy_id=discrepancy_id,
        current_user=current_user,
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


