import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="The unique or display name of the project.",
        examples=["Q1 Financial Audit"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Detailed description or context for this project.",
        examples=["Reconciliation of ledger vs transaction records"],
    )


class ProjectCreate(ProjectBase):
    """
    Schema for creating a new project.
    Note: In this development stage prior to authentication, owner_id is not accepted
    from client payloads to prevent arbitrary owner injection.
    """
    pass


class ProjectResponse(ProjectBase):
    """
    Schema returned for project queries and creation responses.
    """
    id: uuid.UUID
    owner_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
