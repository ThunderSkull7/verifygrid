"""Multi-source verification, ingestion, and alignment schemas."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.preprocessing import PreprocessingConfig
from app.schemas.result import (
    DiscrepancyCategory,
    FieldDifference,
    MatchStatus,
    ReasonCode,
    VerificationResultItem,
    VerificationSummary,
)


class SourceDefinition(BaseModel):
    """Specification for an individual source participating in a multi-source reconciliation."""

    alias: str = Field(
        ...,
        description="Unique identifier alias for this source (e.g. 'erp', 'bank', 'gateway', 'source_a')",
    )
    file_id: uuid.UUID = Field(
        ...,
        description="UUID of the uploaded source file",
    )
    is_primary: bool = Field(
        default=False,
        description="Whether this dataset serves as the primary/golden baseline",
    )
    key_columns: List[str] = Field(
        ...,
        min_length=1,
        description="Column names in this file used to form the join key (single or composite)",
    )
    field_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from source column name -> unified virtual schema attribute name",
    )
    excluded_row_indices: Optional[List[int]] = Field(
        default_factory=list,
        description="Optional list of 1-based row indices to omit from reconciliation (e.g. quarantine exclusions)",
    )


class MultiSourceVerificationRequest(BaseModel):
    """Execution request for multi-source reconciliation (2, 3, or more datasets)."""

    sources: List[SourceDefinition] = Field(
        ...,
        min_length=2,
        description="List of two or more source definitions participating in the reconciliation",
    )
    unified_keys: List[str] = Field(
        ...,
        min_length=1,
        description="Unified attribute names used as the join/matching keys across all sources",
    )
    compare_attributes: Optional[List[str]] = Field(
        default=None,
        description="Specific unified attributes to compare across sources. If None, all mapped attributes are compared.",
    )
    ignore_attributes: Optional[List[str]] = Field(
        default_factory=list,
        description="Unified attributes to ignore during comparison.",
    )
    numeric_tolerance: float = Field(
        default=0.0,
        ge=0.0,
        description="Acceptable absolute difference when comparing numeric currency/amounts.",
    )
    ignore_whitespace: bool = Field(
        default=True,
        description="Strip whitespace when comparing string values.",
    )
    ignore_case: bool = Field(
        default=False,
        description="Perform case-insensitive string comparisons.",
    )
    include_identical: bool = Field(
        default=True,
        description="Include 100% matched identical records in the results array.",
    )
    status_rules: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional status rules for cross-system state mapping (e.g. settled == completed).",
    )
    preprocessing_config: Optional[PreprocessingConfig] = Field(
        default=None,
        description="Optional preprocessing config overrides.",
    )

    model_config = ConfigDict(extra="ignore")


class MultiSourceKeyRecommendation(BaseModel):
    """Candidate key discovery recommendation across multiple sources."""

    key_name: str = Field(description="Unified logical key name or attribute")
    is_composite: bool = Field(default=False, description="Whether this key requires multiple columns")
    overall_score: float = Field(
        description="Suitability score (0.0 to 1.0) factoring uniqueness, low nulls, and value overlap"
    )
    overlap_score: float = Field(
        description="Cross-source distinct value overlap / Jaccard similarity (0.0 to 1.0)"
    )
    source_columns: Dict[str, List[str]] = Field(
        description="Recommended column(s) for each source alias"
    )
    uniqueness_by_source: Dict[str, float] = Field(
        description="Uniqueness ratio per source (0.0 to 1.0)"
    )
    null_rate_by_source: Dict[str, float] = Field(
        description="Null percentage per source (0.0 to 1.0)"
    )
    recommendation_reason: str = Field(description="Human-readable explanation of why this key is suitable")


class MultiSourceKeyRecommendRequest(BaseModel):
    """Request payload to discover candidate join keys across uploaded files."""

    file_ids: List[uuid.UUID] = Field(
        ...,
        min_length=2,
        description="List of 2 or more file IDs to analyze for candidate join keys",
    )
    aliases: Optional[List[str]] = Field(
        default=None,
        description="Optional explicit alias names for the files (e.g. ['erp', 'bank', 'gateway'])",
    )


class MultiSourceKeyRecommendResponse(BaseModel):
    """Response containing ranked candidate key recommendations."""

    recommendations: List[MultiSourceKeyRecommendation]
    total_evaluated_columns: int


class MultiSourceVerificationResponse(BaseModel):
    """Response for multi-source reconciliation execution."""

    project_id: uuid.UUID
    run_id: Optional[uuid.UUID] = None
    sources: List[SourceDefinition]
    unified_keys: List[str]
    summary: VerificationSummary
    records_by_source: Dict[str, int]
    missing_by_source: Dict[str, int]
    results: List[VerificationResultItem]
    discrepancies: List[VerificationResultItem]
    warnings: List[Any] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
