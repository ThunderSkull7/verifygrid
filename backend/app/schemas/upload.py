import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SourceFileResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
