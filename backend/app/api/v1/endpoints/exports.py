"""API router for exporting verification reports (CSV and XLSX)."""

from __future__ import annotations

from typing import Optional
import uuid
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.export_service import export_verification_report

router = APIRouter()


@router.get(
    "/projects/{project_id}/runs/{run_id}/export",
    status_code=status.HTTP_200_OK,
    summary="Download verification report",
    description="Generates and streams a downloadable reconciliation report in CSV, JSON, or XLSX format.",
)
def export_run_report_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    format: str = Query("csv", description="Report format: 'csv', 'json', or 'xlsx'"),
    discrepancy_category: Optional[str] = Query(None, description="Optional category filter"),
    match_status: Optional[str] = Query(None, description="Optional match status filter"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download verification report in CSV, JSON, or XLSX format."""
    content, media_type, filename = export_verification_report(
        db=db,
        project_id=project_id,
        run_id=run_id,
        report_format=format,
        discrepancy_category=discrepancy_category,
        match_status=match_status,
        current_user=current_user,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
