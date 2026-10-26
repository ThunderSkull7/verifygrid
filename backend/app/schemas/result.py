"""Pydantic schemas for verification engine, reconciliation, and comparison results."""

from __future__ import annotations

import uuid
from datetime import datetime
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
    NEEDS_REVIEW = "needs_review"
    PARTIAL_PAYMENT = "partial_payment"
    OVERPAYMENT = "overpayment"
    UNMATCHED_SPLIT_RECORD = "unmatched_split_record"
    DUPLICATE_RECEIPT = "duplicate_receipt"


class DiscrepancyCategory(str, Enum):
    """High-level classification of discrepancies."""

    NONE = "none"
    FIELD_MISMATCH = "field_mismatch"
    MISSING_RECORD = "missing_record"
    DUPLICATE_KEY = "duplicate_key"
    SCHEMA_MISMATCH = "schema_mismatch"
    NEEDS_REVIEW = "needs_review"
    AGGREGATION_MISMATCH = "aggregation_mismatch"
    RULE_VIOLATION = "rule_violation"


class ReasonCode(str, Enum):
    """Explicit machine- and human-readable decision reason codes."""

    EXACT_MATCH = "EXACT_MATCH"
    FIELD_MISMATCH = "FIELD_MISMATCH"
    FUZZY_NAME_REVIEW = "FUZZY_NAME_REVIEW"
    STATUS_MISMATCH = "STATUS_MISMATCH"
    ID_CONFLICT = "ID_CONFLICT"
    AMOUNT_TOLERANCE_EXCEEDED = "AMOUNT_TOLERANCE_EXCEEDED"
    MISSING_IN_TARGET = "MISSING_IN_TARGET"
    MISSING_IN_SOURCE = "MISSING_IN_SOURCE"
    DUPLICATE_KEY_SOURCE = "DUPLICATE_KEY_SOURCE"
    DUPLICATE_KEY_TARGET = "DUPLICATE_KEY_TARGET"
    DUPLICATE_KEY_BOTH = "DUPLICATE_KEY_BOTH"
    AMBIGUOUS_DUPLICATE = "AMBIGUOUS_DUPLICATE"
    NULL_KEY = "NULL_KEY"
    DATE_WINDOW_EXCEEDED = "DATE_WINDOW_EXCEEDED"
    PERCENTAGE_TOLERANCE_EXCEEDED = "PERCENTAGE_TOLERANCE_EXCEEDED"
    PREDICATE_VIOLATION = "PREDICATE_VIOLATION"
    STATUS_TRANSITION_VIOLATION = "STATUS_TRANSITION_VIOLATION"
    PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
    OVERPAYMENT = "OVERPAYMENT"
    UNMATCHED_SPLIT_RECORD = "UNMATCHED_SPLIT_RECORD"
    DUPLICATE_RECEIPT = "DUPLICATE_RECEIPT"


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
        description="'value_mismatch', 'type_mismatch', 'null_mismatch', 'fuzzy_name_review', 'status_mismatch'",
    )
    reason_code: Optional[ReasonCode] = Field(
        default=None, description="Specific reason code for this field difference"
    )
    confidence_score: Optional[float] = Field(
        default=None, description="Similarity score (0.0 - 1.0) if fuzzy compared"
    )
    message: Optional[str] = Field(default=None, description="Explanation of difference")


class VerificationResultItem(BaseModel):
    """Single verification comparison entry representing a matched pair or discrepancy."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key_values: Dict[str, Any] = Field(description="Values of the matching key columns")
    match_status: MatchStatus
    discrepancy_category: DiscrepancyCategory
    reason_code: Optional[ReasonCode] = Field(
        default=None, description="Explicit decision reason code"
    )
    confidence_score: Optional[float] = Field(
        default=None, description="Matching confidence or similarity score (0.0 to 1.0)"
    )
    source_row_number: Optional[int] = Field(
        default=None, description="Primary source row number (1-based), if applicable"
    )
    target_row_number: Optional[int] = Field(
        default=None, description="Primary target row number (1-based), if applicable"
    )
    source_row_index: Optional[int] = Field(
        default=None, description="Lineage index of source record (alias for source_row_number)"
    )
    target_row_index: Optional[int] = Field(
        default=None, description="Lineage index of target record (alias for target_row_number)"
    )
    source_row_numbers: List[int] = Field(
        default_factory=list,
        description="All source row numbers sharing this key (useful for duplicate keys)",
    )
    target_row_numbers: List[int] = Field(
        default_factory=list,
        description="All target row numbers sharing this key (useful for duplicate keys)",
    )
    source_file_id: Optional[str] = Field(
        default=None, description="Lineage reference to source file"
    )
    target_file_id: Optional[str] = Field(
        default=None, description="Lineage reference to target file"
    )
    lineage: Optional[Dict[str, Any]] = Field(
        default=None, description="Detailed record provenance and key trace"
    )
    source_row_indices: Optional[Dict[str, Optional[int]]] = Field(
        default=None,
        description="Lineage row indices across all participating sources: {'source_a': 12, 'source_b': 14, 'source_c': 19}",
    )
    source_records: Optional[Dict[str, Optional[Dict[str, Any]]]] = Field(
        default=None,
        description="Records from each participating source alias",
    )
    missing_in_sources: Optional[List[str]] = Field(
        default=None,
        description="List of source aliases where this record was missing",
    )
    source_presence: Optional[Dict[str, bool]] = Field(
        default=None,
        description="Presence boolean per source alias",
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
    child_records: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Lineage of individual child installment receipts in split-payment reconciliation",
    )
    aggregated_amount: Optional[float] = Field(
        default=None,
        description="Sum of child installment amounts in split-payment reconciliation",
    )
    expected_amount: Optional[float] = Field(
        default=None,
        description="Expected parent total amount in split-payment reconciliation",
    )
    source_amount: Optional[float] = Field(
        default=None,
        description="Reconciled or claimed monetary value from source dataset",
    )
    target_amount: Optional[float] = Field(
        default=None,
        description="Reconciled or matched monetary value from target dataset",
    )
    variance_amount: Optional[float] = Field(
        default=None,
        description="Directional signed variance: source_amount - target_amount",
    )
    exposure_amount: Optional[float] = Field(
        default=None,
        description="Gross exception exposure: |source_amount - target_amount|",
    )
    currency: Optional[str] = Field(
        default="USD",
        description="Monetary currency code",
    )
    severity: Optional[str] = Field(
        default="medium",
        description="Discrepancy severity classification: 'high', 'medium', 'low', 'info'",
    )
    resolution_status: Optional[str] = Field(
        default="unresolved",
        description="Exception resolution workflow status",
    )
    side_by_side: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Detailed side-by-side comparison payload (raw vs normalized values)",
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
    needs_review_records: int = Field(
        default=0,
        description="Records requiring human review (fuzzy name variations or candidates)",
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
        default=0,
        description="Total source records belonging to duplicate matching keys in source",
    )
    duplicate_target_records: int = Field(
        default=0,
        description="Total target records belonging to duplicate matching keys in target",
    )
    duplicate_source_keys_count: int = Field(
        default=0,
        description="Number of distinct keys that appear multiple times in source",
    )
    duplicate_target_keys_count: int = Field(
        default=0,
        description="Number of distinct keys that appear multiple times in target",
    )
    conflicting_duplicate_records: int = Field(
        default=0,
        description="Records where a key is unique on one side but duplicated on the other",
    )

    # Overall totals
    total_discrepancies: int = Field(
        description="Total count of all discrepant records (field mismatches, missing, duplicates)"
    )

    # Financial Materiality & Exposure Metrics
    gross_exposure: float = Field(
        default=0.0,
        description="Gross Exception Exposure: Absolute monetary sum of all discrepancies and variances (|source - target| across exception rows)",
    )
    net_variance: float = Field(
        default=0.0,
        description="Net Variance: Signed directional variance (sum(source_amount) - sum(target_amount))",
    )
    claimed_amount: float = Field(
        default=0.0,
        description="Total monetary value submitted in source records",
    )
    verified_amount: float = Field(
        default=0.0,
        description="Total monetary value successfully reconciled with zero variance",
    )
    outstanding_amount: float = Field(
        default=0.0,
        description="Total monetary value currently unreconciled or disputed",
    )
    currency: str = Field(
        default="USD",
        description="Primary currency code for financial materiality metrics",
    )
    exposure_by_currency: Optional[Dict[str, Dict[str, float]]] = Field(
        default=None,
        description="Per-currency breakdown of financial materiality metrics",
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
    enable_fuzzy_matching: bool = Field(
        default=False,
        description="Enable fuzzy candidate matching and name variation review.",
    )
    fuzzy_match_columns: Optional[List[str]] = Field(
        default=None,
        description="Explicit columns to evaluate for name/fuzzy similarity (e.g. ['name', 'full_name']).",
    )
    fuzzy_threshold: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        description="Similarity threshold for fuzzy candidate matching (0-100).",
    )
    status_rules: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional status rules for state-aware verification (e.g. active vs suspended).",
    )
    excluded_source_rows: Optional[List[int]] = Field(
        default_factory=list,
        description="Optional list of 1-based source row indices to exclude from reconciliation (e.g. from quarantine).",
    )
    excluded_target_rows: Optional[List[int]] = Field(
        default_factory=list,
        description="Optional list of 1-based target row indices to exclude from reconciliation (e.g. from quarantine).",
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
    enable_fuzzy_matching: bool = Field(
        default=False,
        description="Enable fuzzy candidate matching and name variation review.",
    )
    fuzzy_match_columns: Optional[List[str]] = Field(
        default=None,
        description="Explicit columns to evaluate for name/fuzzy similarity (e.g. ['name', 'full_name']).",
    )
    fuzzy_threshold: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        description="Similarity threshold for fuzzy candidate matching (0-100).",
    )
    status_rules: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional status rules for state-aware verification (e.g. active vs suspended).",
    )
    excluded_source_rows: Optional[List[int]] = Field(
        default_factory=list,
        description="Optional list of 1-based source row indices to exclude from reconciliation (e.g. from quarantine).",
    )
    excluded_target_rows: Optional[List[int]] = Field(
        default_factory=list,
        description="Optional list of 1-based target row indices to exclude from reconciliation (e.g. from quarantine).",
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


class VerificationRunResponse(BaseModel):
    """Structured response for a persistent verification run."""

    id: uuid.UUID
    project_id: uuid.UUID
    source_file_id: Optional[uuid.UUID] = None
    target_file_id: Optional[uuid.UUID] = None
    status: str
    key_columns: List[str]
    column_mapping: Optional[Dict[str, Any]] = None
    sources: Optional[List[Dict[str, Any]]] = None
    configuration: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationRunListResponse(BaseModel):
    """Paginated list of verification runs."""

    total: int
    items: List[VerificationRunResponse]
    skip: int
    limit: int


class DiscrepancyItemResponse(BaseModel):
    """Individual discrepancy item belonging to a verification run."""

    id: uuid.UUID
    run_id: uuid.UUID
    match_status: str
    discrepancy_category: str
    key_values: Dict[str, Any]
    source_row_number: Optional[int] = None
    target_row_number: Optional[int] = None
    source_row_index: Optional[int] = None
    target_row_index: Optional[int] = None
    reason_code: Optional[str] = None
    confidence_score: Optional[float] = None
    source_row_numbers: Optional[List[int]] = None
    target_row_numbers: Optional[List[int]] = None
    source_row_indices: Optional[Dict[str, Optional[int]]] = None
    source_records: Optional[Dict[str, Optional[Dict[str, Any]]]] = None
    missing_in_sources: Optional[List[str]] = None
    source_presence: Optional[Dict[str, bool]] = None
    source_record: Optional[Dict[str, Any]] = None
    target_record: Optional[Dict[str, Any]] = None
    field_differences: Optional[List[Dict[str, Any]]] = None
    child_records: Optional[List[Dict[str, Any]]] = None
    aggregated_amount: Optional[float] = None
    expected_amount: Optional[float] = None
    source_amount: Optional[float] = None
    target_amount: Optional[float] = None
    variance_amount: Optional[float] = None
    exposure_amount: Optional[float] = None
    currency: Optional[str] = "USD"
    severity: Optional[str] = "medium"
    resolution_status: Optional[str] = "unresolved"
    side_by_side: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DiscrepancyListResponse(BaseModel):
    """Paginated list of discrepancy results for a verification run."""

    total: int
    items: List[DiscrepancyItemResponse]
    skip: int
    limit: int


class FieldComparisonDiff(BaseModel):
    """Field-level diff between raw source, normalized source, raw target, and normalized target."""

    field_name: str = Field(description="Logical or normalized column name")
    source_field: Optional[str] = Field(default=None, description="Original source column name")
    target_field: Optional[str] = Field(default=None, description="Original target column name")
    raw_source_value: Any = Field(default=None, description="Raw source value before normalization")
    normalized_source_value: Any = Field(default=None, description="Source value after normalization")
    raw_target_value: Any = Field(default=None, description="Raw target value before normalization")
    normalized_target_value: Any = Field(default=None, description="Target value after normalization")
    is_match: bool = Field(default=True, description="True if values match after normalization")
    difference_type: Optional[str] = Field(default=None, description="Type of difference")
    reason_code: Optional[ReasonCode] = Field(default=None, description="Decision reason code")
    message: Optional[str] = Field(default=None, description="Detailed difference message")


class SideBySideInspectionResponse(BaseModel):
    """Detailed side-by-side inspection payload for an individual record or exception."""

    id: str = Field(description="Record / discrepancy identifier")
    run_id: Optional[uuid.UUID] = Field(default=None, description="Associated verification run UUID")
    key_values: Dict[str, Any] = Field(default_factory=dict, description="Reconciliation key values")
    match_status: MatchStatus
    discrepancy_category: DiscrepancyCategory
    reason_code: Optional[ReasonCode] = Field(default=None)
    confidence_score: Optional[float] = Field(default=None)
    severity: str = Field(default="medium", description="'high', 'medium', 'low', 'info'")

    # Financial Materiality Metrics
    source_amount: Optional[float] = Field(default=None, description="Source monetary amount")
    target_amount: Optional[float] = Field(default=None, description="Target monetary amount")
    variance_amount: Optional[float] = Field(default=None, description="Signed variance (source - target)")
    exposure_amount: Optional[float] = Field(default=None, description="Absolute monetary exposure (|source - target|)")
    currency: Optional[str] = Field(default="USD", description="Currency ISO code")

    # Multi-source Lineage Coordinates
    source_row_index: Optional[int] = Field(default=None)
    target_row_index: Optional[int] = Field(default=None)
    source_row_indices: Optional[Dict[str, Optional[int]]] = Field(default=None)
    missing_in_sources: Optional[List[str]] = Field(default=None)
    source_presence: Optional[Dict[str, bool]] = Field(default=None)

    # Records
    raw_source_record: Optional[Dict[str, Any]] = Field(default=None)
    normalized_source_record: Optional[Dict[str, Any]] = Field(default=None)
    raw_target_record: Optional[Dict[str, Any]] = Field(default=None)
    normalized_target_record: Optional[Dict[str, Any]] = Field(default=None)

    # Field-level Diffs & Rule Diagnostics
    field_comparisons: List[FieldComparisonDiff] = Field(default_factory=list)
    failed_rules: List[Dict[str, Any]] = Field(default_factory=list)
    child_records: Optional[List[Dict[str, Any]]] = Field(default=None)
    message: Optional[str] = Field(default=None)
    resolution_status: Optional[str] = Field(default="unresolved")


# Re-export multisource schemas
from app.schemas.multisource import (
    MultiSourceKeyRecommendRequest,
    MultiSourceKeyRecommendResponse,
    MultiSourceKeyRecommendation,
    MultiSourceVerificationRequest,
    MultiSourceVerificationResponse,
    SourceDefinition,
)


