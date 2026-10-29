"""Pydantic schemas for authentication and user accounts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserRegisterRequest(BaseModel):
    """Payload to register a new user account."""

    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="User email address")
    password: str = Field(min_length=8, max_length=128, description="Plaintext password (min 8 chars)")
    full_name: Optional[str] = Field(default=None, max_length=255, description="User full display name")

    # P0-1: role is never accepted from the registration payload. Rejecting
    # unknown fields makes escalation attempts fail closed with 422.
    model_config = ConfigDict(extra="forbid")


class UserRoleUpdateRequest(BaseModel):
    """Admin-only role elevation payload (exact uppercase role required)."""

    role: Literal["MAKER", "CHECKER", "ADMIN", "VIEWER"] = Field(
        description="Target role; must be one of MAKER, CHECKER, ADMIN, VIEWER.",
    )


class UserLoginRequest(BaseModel):
    """Payload to authenticate and retrieve access token."""

    email: str = Field(min_length=3, max_length=255, description="User email address")
    password: str = Field(min_length=1, max_length=128, description="User password")


class UserResponse(BaseModel):
    """User account details."""

    id: uuid.UUID
    email: str
    full_name: Optional[str] = None
    role: str = "MAKER"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Authentication bearer token response."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse
