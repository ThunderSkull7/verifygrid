"""Append-only, tamper-evident audit event model.

Mapped to the ``audit_events`` table created by
``0004_enterprise_governance``. Batch 26A does not create or alter schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AuditEvent(Base):
    """Append-only tamper-evident audit event log with SHA-256 hash chaining."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        index=True,
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    user_role: Mapped[str] = mapped_column(
        String(50),
        default="MAKER",
        server_default="MAKER",
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    timestamp_str: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    event_payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    previous_event_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    current_event_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    # Relationships
    run = relationship("VerificationRun", backref="audit_events", lazy="selectin")
    project = relationship("Project", backref="audit_events", lazy="selectin")
    user = relationship("User", backref="audit_events", lazy="selectin")
