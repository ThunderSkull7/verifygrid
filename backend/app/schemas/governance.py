"""Pydantic schemas for maker-checker governance and sign-off."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    MAKER = "MAKER"
    CHECKER = "CHECKER"
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"


class SignOffStatus(str, Enum):
    DRAFT = "DRAFT"
    AWAITING_SIGN_OFF = "AWAITING_SIGN_OFF"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProposeSignOffRequest(BaseModel):
    """Maker proposal to sign off on a reconciliation run."""

    note: Optional[str] = Field(default=None, max_length=10000, description="Optional justification note from the maker")
    # Retained for wire compatibility only. The service derives the displayed
    # name from the authenticated principal and never trusts this value.
    proposed_by_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Deprecated: ignored; the authenticated user's name is recorded.",
    )


class ApproveSignOffRequest(BaseModel):
    """Checker countersignature and final sign-off approval."""

    note: Optional[str] = Field(default=None, max_length=10000, description="Optional sign-off approval note")
    # Retained for wire compatibility only; ignored for identity.
    approved_by_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Deprecated: ignored; the authenticated user's name is recorded.",
    )


class RejectSignOffRequest(BaseModel):
    """Checker rejection of proposed sign-off package."""

    note: str = Field(min_length=1, max_length=10000, description="Mandatory rejection reason")


class SignOffDetailsResponse(BaseModel):
    """Full governance sign-off state for a verification run."""

    run_id: uuid.UUID
    project_id: uuid.UUID
    sign_off_status: str
    sign_off_proposed_by: Optional[uuid.UUID] = None
    sign_off_proposed_by_name: Optional[str] = None
    sign_off_proposal_note: Optional[str] = None
    sign_off_proposed_at: Optional[datetime] = None
    sign_off_approved_by: Optional[uuid.UUID] = None
    sign_off_approved_by_name: Optional[str] = None
    sign_off_decision_note: Optional[str] = None
    sign_off_decided_at: Optional[datetime] = None
    can_approve: bool = False
    is_maker: bool = False

    model_config = ConfigDict(from_attributes=True)
