"""API router for data preprocessing and normalization."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.preprocessing import PreprocessingConfig, PreprocessingResultResponse
from app.services.preprocessing import preprocess_source_file

router = APIRouter()


@router.post(
    "/projects/{project_id}/files/{file_id}/preprocess",
    response_model=PreprocessingResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Preprocess and normalize an uploaded source file",
    description=(
        "Executes data preprocessing, column normalization, type inference, "
        "and validation issue detection on an uploaded CSV or XLSX file."
    ),
)
def preprocess_file_endpoint(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    config: Optional[PreprocessingConfig] = None,
    db: Session = Depends(get_db),
) -> PreprocessingResultResponse:
    """Trigger preprocessing for a project-scoped source file."""
    return preprocess_source_file(
        db=db,
        project_id=project_id,
        file_id=file_id,
        config=config,
    )
