"""Pydantic schemas for verification engine, reconciliation, and comparison results."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.preprocessing import PreprocessingConfig, ValidationIssue


class MatchStatus(str, Enum):
    """Status indicating how records matched or failed to match on keys."""

    IDENTICAL = "identical"
    FIELD_MISMATCH = "field_mismatch"
    MISSING_IN_TARGET = "missing_in_target"
    MISSING_IN_SOURCE = "missing_in_source"
    DUPLICATE_KEY_SOURCE = "duplicate_key_source"
    DUPLICATE_KEY_TARGET = "duplicate_key_target"
    DUPLICATE_KEY_BOTH = "duplicate_key_both"
    AMBIGUOUS_DUPLICATE = "ambiguous_duplicate"


class DiscrepancyCategory(str, Enum):
    """High-level classification of discrepancies."""

    NONE = "none"
    FIELD_MISMATCH = "field_mismatch"
    MISSING_RECORD = "missing_record"
    DUPLICATE_KEY = "duplicate_key"
    SCHEMA_MISMATCH = "schema_mismatch"


class FieldDifference(BaseModel):
    """Detailed difference between two corresponding fields in matched records."""

    field_name: str = Field(description="Logical field name (normalized or primary)")
    source_field: str = Field(description="Original column name in source dataset")
    target_field: str = Field(description="Corresponding column name in target dataset")
    source_value: Any = Field(description="Value in source dataset")
    target_value: Any = Field(description="Value in target dataset")
    source_type: Optional[str] = Field(default=None, description="Inferred type of source value")
    target_type: Optional[str] = Field(default=None, description="Inferred type of target value")
    difference_type: str = Field(
        default="value_mismatch",
        description="'value_mismatch', 'type_mismatch', 'null_mismatch'",
    )
    message: Optional[str] = Field(default=None, description="Explanation of difference")


class VerificationResultItem(BaseModel):
    """Single verification comparison entry representing a matched pair or discrepancy."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key_values: Dict[str, Any] = Field(description="Values of the matching key columns")
    match_status: MatchStatus
    discrepancy_category: DiscrepancyCategory
    source_row_number: Optional[int] = Field(
        default=None, description="Primary source row number (1-based), if applicable"
    )
    target_row_number: Optional[int] = Field(
        default=None, description="Primary target row number (1-based), if applicable"
    )
    source_row_numbers: List[int] = Field(
        default_factory=list,
        description="All source row numbers sharing this key (useful for duplicate keys)",
    )
    target_row_numbers: List[int] = Field(
        default_factory=list,
        description="All target row numbers sharing this key (useful for duplicate keys)",
    )
    source_record: Optional[Dict[str, Any]] = Field(
        default=None, description="Data record from source dataset"
    )
    target_record: Optional[Dict[str, Any]] = Field(
        default=None, description="Data record from target dataset"
    )
    field_differences: List[FieldDifference] = Field(
        default_factory=list,
        description="List of detected differences across compared fields",
    )
    message: Optional[str] = Field(
        default=None, description="Human-readable outcome or explanation"
    )


class VerificationSummary(BaseModel):
    """Aggregated metrics and counts for the verification run."""

    total_source_records: int = Field(description="Total data records in source dataset")
    total_target_records: int = Field(description="Total data records in target dataset")

    # Matched metrics
    matched_records: int = Field(
        description="Total 1-to-1 matched records (identical_matches + field_mismatches)"
    )
    identical_matches: int = Field(
        description="Records matching on key with zero field differences"
    )
    field_mismatches: int = Field(
        description="Records matching on key with one or more field differences"
    )
    records_with_differences: int = Field(
        default=0,
        description="Alias for field_mismatches: count of records having field-level differences",
    )

    # Missing metrics
    unmatched_source_records: int = Field(
        description="Source records whose keys do not exist in the target dataset"
    )
    unmatched_target_records: int = Field(
        description="Target records whose keys do not exist in the source dataset"
    )

    # Duplicate key metrics
    duplicate_source_records: int = Field(
        description="Total source records belonging to duplicate matching keys in source"
    )
    duplicate_target_records: int = Field(
        description="Total target records belonging to duplicate matching keys in target"
    )
    duplicate_source_keys_count: int = Field(
        description="Number of distinct keys that appear multiple times in source"
    )
    duplicate_target_keys_count: int = Field(
        description="Number of distinct keys that appear multiple times in target"
    )
    conflicting_duplicate_records: int = Field(
        default=0,
        description="Records where a key is unique on one side but duplicated on the other",
    )

    # Overall totals
    total_discrepancies: int = Field(
        description="Total count of all discrepant records (field mismatches, missing, duplicates)"
    )
    status: str = Field(default="completed", description="'completed', 'failed', 'completed_with_warnings'")


class VerificationRequest(BaseModel):
    """Request payload to verify two uploaded files in a project."""

    source_file_id: uuid.UUID = Field(
        description="UUID of the baseline/primary source file"
    )
    target_file_id: uuid.UUID = Field(
        description="UUID of the comparison/secondary source file"
    )
    key_columns: List[str] = Field(
        ...,
        min_length=1,
        description="List of column names used as matching keys (single or composite)",
    )
    column_mapping: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Mapping of source column name -> target column name when headers differ",
    )
    compare_columns: Optional[List[str]] = Field(
        default=None,
        description="Specific columns to compare. If None, all common columns are compared.",
    )
    ignore_columns: Optional[List[str]] = Field(
        default_factory=list,
        description="Columns to ignore during field comparison.",
    )
    numeric_tolerance: float = Field(
        default=0.0,
        ge=0.0,
        description="Acceptable absolute difference when comparing floating-point numbers.",
    )
    ignore_whitespace: bool = Field(
        default=True,
        description="Strip whitespace when comparing string values.",
    )
    ignore_case: bool = Field(
        default=False,
        description="Perform case-insensitive string comparisons.",
    )
    preprocessing_config: Optional[PreprocessingConfig] = Field(
        default=None,
        description="Optional custom preprocessing configuration for loading datasets.",
    )
    include_identical: bool = Field(
        default=True,
        description="Whether to include identical matching records in the results array.",
    )

    model_config = ConfigDict(extra="ignore")


class InMemoryVerificationRequest(BaseModel):
    """Request payload for comparing in-memory dataset records directly."""

    source_records: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of row dictionaries representing source dataset",
    )
    target_records: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of row dictionaries representing target dataset",
    )
    key_columns: List[str] = Field(
        ...,
        min_length=1,
        description="List of column names used as matching keys (single or composite)",
    )
    column_mapping: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Mapping of source column name -> target column name when headers differ",
    )
    compare_columns: Optional[List[str]] = Field(
        default=None,
        description="Specific columns to compare. If None, all common columns are compared.",
    )
    ignore_columns: Optional[List[str]] = Field(
        default_factory=list,
        description="Columns to ignore during field comparison.",
    )
    numeric_tolerance: float = Field(
        default=0.0,
        ge=0.0,
        description="Acceptable absolute difference when comparing floating-point numbers.",
    )
    ignore_whitespace: bool = Field(
        default=True,
        description="Strip whitespace when comparing string values.",
    )
    ignore_case: bool = Field(
        default=False,
        description="Perform case-insensitive string comparisons.",
    )
    preprocessing_config: Optional[PreprocessingConfig] = Field(
        default=None,
        description="Optional custom preprocessing configuration for loading datasets.",
    )
    include_identical: bool = Field(
        default=True,
        description="Whether to include identical matching records in the results array.",
    )

    model_config = ConfigDict(extra="ignore")


class VerificationResponse(BaseModel):
    """Complete verification report containing summary, results, discrepancies, and warnings."""

    project_id: Optional[uuid.UUID] = Field(default=None)
    source_file_id: Optional[uuid.UUID] = Field(default=None)
    target_file_id: Optional[uuid.UUID] = Field(default=None)
    key_columns: List[str]
    column_mapping: Dict[str, str] = Field(default_factory=dict)
    summary: VerificationSummary
    results: List[VerificationResultItem] = Field(
        default_factory=list,
        description="All verification records (including identical matches if requested)",
    )
    discrepancies: List[VerificationResultItem] = Field(
        default_factory=list,
        description="Filtered subset of results containing only discrepancies",
    )
    warnings: List[ValidationIssue] = Field(
        default_factory=list,
        description="Data quality warnings encountered during preprocessing or verification",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Non-fatal processing errors encountered during verification",
    )

    model_config = ConfigDict(from_attributes=True)
