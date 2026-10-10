import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.upload import SourceFileResponse
from app.services.ingestion import create_source_file

router = APIRouter()


@router.post(
    "/projects/{project_id}/files",
    response_model=SourceFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CSV or XLSX source file",
)
def upload_source_file(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> SourceFileResponse:
    return create_source_file(db=db, project_id=project_id, upload=file)
