from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    DateTime,
    Float,
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
    sources: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
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
    source_row_indices: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    source_records: Mapped[Optional[Dict[str, Any]]] = mapped_column(
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
    child_records: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        nullable=True,
    )
    aggregated_amount: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    expected_amount: Mapped[Optional[float]] = mapped_column(
        Float,
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

    @property
    def source_row_index(self) -> Optional[int]:
        return self.source_row_number

    @property
    def target_row_index(self) -> Optional[int]:
        return self.target_row_number

    @property
    def reason_code(self) -> Optional[str]:
        if self.field_differences:
            for fd in self.field_differences:
                rc = fd.get("reason_code")
                if rc:
                    return rc
        status_to_reason = {
            "identical": "EXACT_MATCH",
            "field_mismatch": "FIELD_MISMATCH",
            "missing_in_target": "MISSING_IN_TARGET",
            "missing_in_source": "MISSING_IN_SOURCE",
            "duplicate_key_source": "DUPLICATE_KEY_SOURCE",
            "duplicate_key_target": "DUPLICATE_KEY_TARGET",
            "duplicate_key_both": "DUPLICATE_KEY_BOTH",
            "ambiguous_duplicate": "AMBIGUOUS_DUPLICATE",
            "needs_review": "FUZZY_NAME_REVIEW",
            "partial_payment": "PARTIAL_PAYMENT",
            "overpayment": "OVERPAYMENT",
            "unmatched_split_record": "UNMATCHED_SPLIT_RECORD",
            "duplicate_receipt": "DUPLICATE_RECEIPT",
        }
        return status_to_reason.get(self.match_status, "FIELD_MISMATCH")

    @property
    def confidence_score(self) -> Optional[float]:
        if self.field_differences:
            for fd in self.field_differences:
                cs = fd.get("confidence_score")
                if cs is not None:
                    return float(cs)
        if self.match_status == "identical":
            return 1.0
        return 0.0
