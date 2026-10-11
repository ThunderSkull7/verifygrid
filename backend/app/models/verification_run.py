from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class VerificationRun(Base):
    __tablename__ = "verification_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("source_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("source_files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )
    key_columns: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
    )
    column_mapping: Mapped[Optional[Dict[str, str]]] = mapped_column(
        JSON,
        nullable=True,
    )
    configuration: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="verification_runs",
    )
    source_file: Mapped[Optional["SourceFile"]] = relationship(
        "SourceFile",
        foreign_keys=[source_file_id],
    )
    target_file: Mapped[Optional["SourceFile"]] = relationship(
        "SourceFile",
        foreign_keys=[target_file_id],
    )
    discrepancies: Mapped[List["VerificationDiscrepancy"]] = relationship(
        "VerificationDiscrepancy",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="VerificationDiscrepancy.created_at",
    )


class VerificationDiscrepancy(Base):
    __tablename__ = "verification_discrepancies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    discrepancy_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    key_values: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )
    source_row_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    target_row_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    source_row_numbers: Mapped[Optional[List[int]]] = mapped_column(
        JSON,
        nullable=True,
    )
    target_row_numbers: Mapped[Optional[List[int]]] = mapped_column(
        JSON,
        nullable=True,
    )
    source_record: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    target_record: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    field_differences: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    run: Mapped["VerificationRun"] = relationship(
        "VerificationRun",
        back_populates="discrepancies",
    )
