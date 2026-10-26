"""API router for exception clustering, bulk human reviews, and reviewer assignments."""

from __future__ import annotations

from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_project_access
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.review import (
    AssignmentRequest,
    AssignmentResponse,
    BulkReviewRequest,
    BulkReviewResponse,
    ClusterListResponse,
    ClusterRecordsResponse,
    ReviewDecisionItem,
    ReviewDecisionRequest,
)
from app.services.clustering_service import (
    get_cluster_records,
    get_run_clusters,
)
from app.services.review_service import (
    apply_bulk_review,
    apply_single_review,
    assign_discrepancies,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/runs/{run_id}/clusters",
    response_model=ClusterListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get grouped exception clusters for a verification run",
)
def get_run_clusters_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClusterListResponse:
    """
    Returns deterministic root-cause exception clusters with aggregated financial exposure,
    record counts, root-cause explanations, and representative sample records.
    """
    try:
        return get_run_clusters(db, project_id=project_id, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/projects/{project_id}/runs/{run_id}/clusters/{cluster_id}/records",
    response_model=ClusterRecordsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get paginated records belonging to a specific cluster",
)
def get_cluster_records_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    cluster_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    resolution_status: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClusterRecordsResponse:
    """
    Returns records associated with the specified exception cluster ID.
    Supports filtering by resolution status and reviewer assignment.
    """
    try:
        return get_cluster_records(
            db,
            project_id=project_id,
            run_id=run_id,
            cluster_id=cluster_id,
            skip=skip,
            limit=limit,
            resolution_status=resolution_status,
            assigned_to=assigned_to,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    "/projects/{project_id}/runs/{run_id}/reviews/bulk",
    response_model=BulkReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Apply bulk review decision across a cluster or record list",
)
def apply_bulk_review_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    request: BulkReviewRequest,
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BulkReviewResponse:
    """
    Applies review decision (APPROVE, REJECT, FORCE_MATCH, ESCALATE, REOPEN) in bulk.
    Enforces mandatory justification, applies financial exposure barriers and blocking checks,
    and creates individual audit records for every affected row.
    """
    try:
        return apply_bulk_review(
            db=db,
            project_id=project_id,
            run_id=run_id,
            request=request,
            current_user=current_user,
        )
    except ValueError as exc:
        err_str = str(exc)
        if "not found" in err_str.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_str)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_str)


@router.post(
    "/projects/{project_id}/runs/{run_id}/reviews/{discrepancy_id}",
    response_model=ReviewDecisionItem,
    status_code=status.HTTP_200_OK,
    summary="Apply review decision to an individual discrepancy",
)
def apply_single_review_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    discrepancy_id: uuid.UUID,
    request: ReviewDecisionRequest,
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewDecisionItem:
    """
    Resolves an individual exception record with a mandatory justification note and audit trail entry.
    """
    try:
        return apply_single_review(
            db=db,
            project_id=project_id,
            run_id=run_id,
            discrepancy_id=discrepancy_id,
            request=request,
            current_user=current_user,
        )
    except ValueError as exc:
        err_str = str(exc)
        if "not found" in err_str.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_str)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_str)


@router.post(
    "/projects/{project_id}/runs/{run_id}/assignments",
    response_model=AssignmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign discrepancies or clusters to a designated reviewer",
)
def assign_discrepancies_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    request: AssignmentRequest,
    _project: Project = Depends(verify_project_access),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssignmentResponse:
    """
    Assigns designated records or a full cluster to a designated reviewer.
    """
    try:
        return assign_discrepancies(
            db=db,
            project_id=project_id,
            run_id=run_id,
            request=request,
            current_user=current_user,
        )
    except ValueError as exc:
        err_str = str(exc)
        if "not found" in err_str.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err_str)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_str)
