"""Pydantic schemas for data profiling, pre-flight validation, and quarantine pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class QuarantineReasonCode(str, Enum):
    """Explicit reasons why a record is placed into quarantine."""

    MALFORMED_DATE = "MALFORMED_DATE"
    INVALID_NUMBER = "INVALID_NUMBER"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    UNEXPECTED_NEGATIVE_AMOUNT = "UNEXPECTED_NEGATIVE_AMOUNT"
    SHIFTED_ROW = "SHIFTED_ROW"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"
    TYPE_INCONSISTENCY = "TYPE_INCONSISTENCY"


class QuarantineSeverity(str, Enum):
    """Severity level of the quarantine issue."""

    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class ResolutionAction(str, Enum):
    """Pre-flight resolution action taken by the user."""

    PENDING = "PENDING"
    EXCLUDE = "EXCLUDE"
    ACCEPT_AS_VALID = "ACCEPT_AS_VALID"


class QuarantinedRecord(BaseModel):
    """A record flagged by pre-flight profiling and held in quarantine."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_row_index: int = Field(description="1-based original row index in source file")
    column_name: Optional[str] = Field(default=None, description="Affected column name, if column-specific")
    raw_value: Any = Field(default=None, description="Raw value that triggered the flag")
    quarantine_reason: QuarantineReasonCode = Field(description="Machine-readable quarantine reason")
    severity: QuarantineSeverity = Field(description="WARNING (advisory) or BLOCKING (must resolve or exclude)")
    message: str = Field(description="Human-readable description of why this record was quarantined")
    resolution_action: ResolutionAction = Field(
        default=ResolutionAction.PENDING,
        description="Action to take during reconciliation: PENDING, EXCLUDE, or ACCEPT_AS_VALID",
    )
    resolution_note: Optional[str] = Field(default=None, description="Optional auditor notes explaining decision")
    raw_record: Optional[Dict[str, Any]] = Field(default=None, description="Full raw source record dictionary")


class ColumnProfile(BaseModel):
    """Detailed profile statistics for a single column."""

    column_name: str
    original_name: str
    inferred_type: str = Field(
        description="'integer', 'float', 'date', 'boolean', 'string', 'identifier', or 'empty'"
    )
    total_count: int
    null_count: int
    null_percentage: float = Field(description="0.0 to 100.0")
    distinct_count: int
    uniqueness_ratio: float = Field(description="distinct_count / total_count (0.0 to 1.0)")
    is_candidate_key: bool = Field(description="True if uniqueness is 100% and null_count is 0")
    sample_values: List[Any] = Field(default_factory=list)
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    anomalies_count: int = 0


class CandidateKeyQuality(BaseModel):
    """Assessment of whether a column can safely serve as a reconciliation key."""

    column_name: str
    uniqueness_ratio: float
    duplicate_count: int
    null_count: int
    is_viable_key: bool
    recommendation: str


class PreFlightImpactPreview(BaseModel):
    """Impact summary showing total eligible vs. excluded rows before reconciliation execution."""

    total_source_rows: int
    eligible_rows_count: int
    excluded_rows_count: int
    quarantined_rows_count: int
    blocking_count: int
    warning_count: int


class FileProfileSummary(BaseModel):
    """Comprehensive profiling report for an uploaded source file."""

    file_id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    file_type: str
    total_rows: int
    total_columns: int
    columns: List[ColumnProfile]
    candidate_keys: List[CandidateKeyQuality]
    detected_anomalies_count: int
    quarantine_count: int
    impact_preview: PreFlightImpactPreview

    model_config = ConfigDict(from_attributes=True)


class QuarantineListResponse(BaseModel):
    """List of quarantined records for a file with impact preview."""

    file_id: uuid.UUID
    total_quarantined: int
    records: List[QuarantinedRecord]
    impact_preview: PreFlightImpactPreview


class QuarantineResolutionItem(BaseModel):
    """Individual resolution decision for a quarantined row."""

    source_row_index: int
    quarantine_reason: Optional[str] = None
    action: ResolutionAction
    note: Optional[str] = None


class QuarantineResolutionRequest(BaseModel):
    """Request payload to resolve one or more quarantined records."""

    resolutions: List[QuarantineResolutionItem]


class QuarantineResolutionResponse(BaseModel):
    """Response after applying pre-flight quarantine resolutions."""

    file_id: uuid.UUID
    resolved_count: int
    excluded_row_indices: List[int]
    accepted_row_indices: List[int]
    impact_preview: PreFlightImpactPreview
    quarantined_records: List[QuarantinedRecord]
