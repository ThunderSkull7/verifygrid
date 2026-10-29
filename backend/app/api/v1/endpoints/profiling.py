"""API router for source file profiling, pre-flight validation, and quarantine pipeline."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.multisource import (
    MultiSourceKeyRecommendRequest,
    MultiSourceKeyRecommendResponse,
)
from app.schemas.profiling import (
    FileProfileSummary,
    QuarantineListResponse,
    QuarantineResolutionRequest,
    QuarantineResolutionResponse,
)
from app.services.profiling_service import (
    get_file_profile,
    get_file_quarantine,
    recommend_keys_for_project_files,
    resolve_quarantine_records,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/files/{file_id}/profile",
    response_model=FileProfileSummary,
    status_code=status.HTTP_200_OK,
    summary="Get file profiling summary, statistics, and anomalies",
    description=(
        "Analyzes column data types, null percentages, distinct counts, uniqueness ratios, "
        "detects malformed numbers/dates, unexpected negative amounts, shifted rows, and key quality."
    ),
)
def get_file_profile_endpoint(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    worksheet: Optional[str] = Query(None, description="XLSX worksheet name (exact); defaults to the workbook's active sheet."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileProfileSummary:
    """Retrieve full profiling summary for a project file."""
    return get_file_profile(
        db=db,
        project_id=project_id,
        file_id=file_id,
        worksheet=worksheet,
        current_user=current_user,
    )


@router.get(
    "/projects/{project_id}/files/{file_id}/quarantine",
    response_model=QuarantineListResponse,
    status_code=status.HTTP_200_OK,
    summary="List quarantined records for a source file",
    description="Returns all records flagged during pre-flight profiling with reason, severity, and impact preview.",
)
@router.get(
    "/projects/{project_id}/files/{file_id}/profile/quarantine",
    response_model=QuarantineListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def get_file_quarantine_endpoint(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    worksheet: Optional[str] = Query(None, description="XLSX worksheet name (exact); defaults to the workbook's active sheet."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuarantineListResponse:
    """Retrieve quarantined records for a source file."""
    return get_file_quarantine(
        db=db,
        project_id=project_id,
        file_id=file_id,
        worksheet=worksheet,
        current_user=current_user,
    )


@router.post(
    "/projects/{project_id}/files/{file_id}/quarantine/resolve",
    response_model=QuarantineResolutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve quarantined records with pre-flight actions",
    description="Applies 'EXCLUDE' or 'ACCEPT_AS_VALID' actions to quarantined rows and recalculates impact preview.",
)
@router.post(
    "/projects/{project_id}/files/{file_id}/profile/quarantine/resolve",
    response_model=QuarantineResolutionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def resolve_quarantine_endpoint(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    request: QuarantineResolutionRequest,
    worksheet: Optional[str] = Query(None, description="XLSX worksheet name (exact); defaults to the workbook's active sheet."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuarantineResolutionResponse:
    """Resolve quarantined records with exclude or accept actions."""
    return resolve_quarantine_records(
        db=db,
        project_id=project_id,
        file_id=file_id,
        request=request,
        worksheet=worksheet,
        current_user=current_user,
    )


@router.post(
    "/projects/{project_id}/keys/recommend",
    response_model=MultiSourceKeyRecommendResponse,
    status_code=status.HTTP_200_OK,
    summary="Recommend candidate join keys across uploaded files",
    description="Analyzes multiple files, measures uniqueness, null rates, and value overlaps to recommend join keys.",
)
def recommend_keys_endpoint(
    project_id: uuid.UUID,
    request: MultiSourceKeyRecommendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MultiSourceKeyRecommendResponse:
    """Discover and rank candidate join keys across multiple uploaded datasets."""
    return recommend_keys_for_project_files(
        db=db,
        project_id=project_id,
        file_ids=request.file_ids,
        aliases=request.aliases,
        current_user=current_user,
    )

