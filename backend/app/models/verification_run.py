from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    false,
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

    # Maker-Checker Governance & Sign-off Lifecycle (0004_enterprise_governance)
    sign_off_status: Mapped[str] = mapped_column(
        String(50),
        default="DRAFT",
        server_default="DRAFT",
        nullable=False,
        index=True,
    )
    sign_off_proposed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sign_off_proposed_by_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    sign_off_proposal_note: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    sign_off_proposed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sign_off_approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sign_off_approved_by_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    sign_off_decision_note: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    sign_off_decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
    # Financial materiality, clustering, assignment, and review state
    # (0004_enterprise_governance).
    source_amount: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    target_amount: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    variance_amount: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    exposure_amount: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        index=True,
    )
    currency: Mapped[Optional[str]] = mapped_column(
        String(10),
        default="USD",
        server_default="USD",
        nullable=True,
    )
    severity: Mapped[Optional[str]] = mapped_column(
        String(20),
        default="medium",
        server_default="medium",
        nullable=True,
        index=True,
    )
    resolution_status: Mapped[Optional[str]] = mapped_column(
        String(30),
        default="unresolved",
        server_default="unresolved",
        nullable=True,
        index=True,
    )
    resolution_note: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cluster_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    cluster_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    side_by_side: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
    )
    _reason_code: Mapped[Optional[str]] = mapped_column(
        "reason_code",
        String(100),
        nullable=True,
        index=True,
    )
    _confidence_score: Mapped[Optional[float]] = mapped_column(
        "confidence_score",
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
    review_decisions: Mapped[List["DiscrepancyReviewDecision"]] = relationship(
        "DiscrepancyReviewDecision",
        back_populates="discrepancy",
        cascade="all, delete-orphan",
        order_by="DiscrepancyReviewDecision.created_at.desc()",
    )

    @property
    def source_row_index(self) -> Optional[int]:
        return self.source_row_number

    @property
    def target_row_index(self) -> Optional[int]:
        return self.target_row_number

    @property
    def reason_code(self) -> Optional[str]:
        # Persisted reason code wins for new rows; the derived fallbacks keep
        # pre-governance rows and the Batch 8 NULL_KEY outcome readable.
        if self._reason_code:
            return self._reason_code
        if self.field_differences:
            for fd in self.field_differences:
                rc = fd.get("reason_code")
                if rc:
                    return rc.value if hasattr(rc, "value") else rc
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
        # Batch 14: persists the Batch 8 invalid-key outcome. Such records are
        # stored as needs_review with a blank component in key_values; fuzzy
        # review candidates always carry complete, valid keys.
        if self.match_status == "needs_review" and any(
            value is None or (isinstance(value, str) and not value.strip())
            for value in (self.key_values or {}).values()
        ):
            return "NULL_KEY"
        return status_to_reason.get(self.match_status, "FIELD_MISMATCH")

    @reason_code.setter
    def reason_code(self, val: Optional[str]) -> None:
        self._reason_code = val

    @property
    def confidence_score(self) -> Optional[float]:
        if self._confidence_score is not None:
            return self._confidence_score
        if self.field_differences:
            for fd in self.field_differences:
                cs = fd.get("confidence_score")
                if cs is not None:
                    return float(cs)
        if self.match_status == "identical":
            return 1.0
        return 0.0

    @confidence_score.setter
    def confidence_score(self, val: Optional[float]) -> None:
        self._confidence_score = val


class DiscrepancyReviewDecision(Base):
    """Immutable human-review decision for a discrepancy.

    Foreign keys intentionally use ``ON DELETE RESTRICT`` (Batch 24 D8): review
    decisions are evidence and must not be silently destroyed by a cascade.
    The table is created by the pending ``0006_discrepancy_review_decisions``
    migration; Batch 26A only maps it.
    """

    __tablename__ = "discrepancy_review_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    discrepancy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("verification_discrepancies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("verification_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    justification: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    reviewer_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    reviewer_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    previous_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    new_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    is_bulk_action: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    cluster_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    discrepancy: Mapped["VerificationDiscrepancy"] = relationship(
        "VerificationDiscrepancy",
        back_populates="review_decisions",
    )
    run: Mapped["VerificationRun"] = relationship(
        "VerificationRun",
    )
