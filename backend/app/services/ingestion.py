import os
import shutil
import uuid
from pathlib import Path

from typing import Optional
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.source_file import SourceFile
from app.models.user import User
from app.services.project_service import get_project_by_id

ALLOWED_FILE_TYPES = {".csv": "csv", ".xlsx": "xlsx"}
CHUNK_SIZE = 1024 * 1024


import zipfile

MAX_UNCOMPRESSED_XLSX_BYTES = 250 * 1024 * 1024  # 250MB
MAX_COMPRESSION_RATIO = 100
MAX_ZIP_ENTRIES = 10000


def _validate_decompression_safety(destination: Path, suffix: str) -> None:
    """Validate file content to prevent zip/decompression bombs and malicious binaries."""
    if suffix == ".xlsx":
        if zipfile.is_zipfile(str(destination)):
            try:
                with zipfile.ZipFile(str(destination), "r") as zf:
                    infolist = zf.infolist()
                    if len(infolist) > MAX_ZIP_ENTRIES:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Upload rejected: Excel archive contains too many files (decompression safety threshold exceeded).",
                        )
                    total_uncompressed = 0
                    total_compressed = 0
                    for info in infolist:
                        total_uncompressed += info.file_size
                        total_compressed += info.compress_size
                        if total_uncompressed > MAX_UNCOMPRESSED_XLSX_BYTES:
                            raise HTTPException(
                                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                detail="Upload rejected: Uncompressed content exceeds 250MB safety limit (decompression bomb protection).",
                            )
                    if total_compressed > 0 and (total_uncompressed / total_compressed) > MAX_COMPRESSION_RATIO:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Upload rejected: Suspicious compression ratio exceeds 100:1 (decompression bomb protection).",
                        )
            except zipfile.BadZipFile:
                pass
    elif suffix == ".csv":
        with destination.open("rb") as f:
            sample = f.read(512)
        if sample.startswith(b"MZ") or sample.startswith(b"\x7fELF") or sample.startswith(b"\xca\xfe\xba\xbe"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Upload rejected: Executable binary file detected.",
            )


def _validated_filename(upload: UploadFile) -> tuple[str, str]:
    filename = Path(upload.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only CSV and XLSX files are supported.",
        )
    return filename, suffix


def create_source_file(
    db: Session,
    project_id: uuid.UUID,
    upload: UploadFile,
    current_user: Optional[User] = None,
) -> SourceFile:
    """Persist a project-scoped CSV/XLSX upload and its metadata."""
    if get_project_by_id(db, project_id, current_user=current_user) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    filename, suffix = _validated_filename(upload)
    source_id = uuid.uuid4()
    project_directory = settings.storage_root / str(project_id)
    destination = project_directory / f"{source_id}{suffix}"
    temporary_destination = destination.with_suffix(f"{suffix}.uploading")
    bytes_written = 0

    try:
        project_directory.mkdir(parents=True, exist_ok=True)
        with temporary_destination.open("xb") as target:
            while chunk := upload.file.read(CHUNK_SIZE):
                bytes_written += len(chunk)
                if bytes_written > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Upload exceeds the {settings.max_upload_bytes} byte limit.",
                    )
                target.write(chunk)
        os.replace(temporary_destination, destination)
        _validate_decompression_safety(destination, suffix)

        source_file = SourceFile(
            id=source_id,
            project_id=project_id,
            original_filename=filename,
            storage_path=str(destination),
            file_type=ALLOWED_FILE_TYPES[suffix],
            file_size=bytes_written,
            status="uploaded",
        )
        db.add(source_file)
        db.commit()
        db.refresh(source_file)
        return source_file
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        temporary_destination.unlink(missing_ok=True)
        if project_directory.exists() and not any(project_directory.iterdir()):
            shutil.rmtree(project_directory)
        raise
    finally:
        upload.file.close()
