import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VerificationTemplate(Base):
    """
    Batch 11: reusable verification template (personal-only launch).

    Stores a versioned, validated configuration snapshot — never uploaded
    records, discrepancy data, file paths, row indices, quarantine
    resolutions, or credentials. Per design doc §2/§3.

    Ownership is per user (the application has no Organization entity yet).
    The `visibility` column is retained for future organization sharing but is
    DORMANT and deny-by-default: only 'personal' is accepted while sharing is
    disabled (enforced at the API boundary).
    """

    __tablename__ = "verification_templates"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_verification_templates_owner_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    # 'organization' | 'financial' — validated at the API boundary. In this
    # release only 'organization' templates can be created (see template schema).
    mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="personal",
        server_default="personal",
    )
    config_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    configuration: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
