"""Pydantic schemas for data preprocessing, normalization, and validation."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PreprocessingConfig(BaseModel):
    """Configurable normalization and validation rules."""

    strip_whitespace: bool = Field(
        default=True,
        description="Strip leading and trailing whitespace from string values.",
    )
    normalize_column_names: bool = Field(
        default=True,
        description="Convert column names to lower_snake_case while preserving original headers.",
    )
    null_values: List[str] = Field(
        default_factory=lambda: [
            "",
            "null",
            "none",
            "nil",
            "n/a",
            "na",
            "nan",
            "-",
            "--",
            "undefined",
            "#n/a",
        ],
        description="List of string representations to treat as null/empty values (case-insensitive).",
    )
    normalize_dates: bool = Field(
        default=True,
        description="Attempt to parse and normalize recognized date strings to ISO-8601 YYYY-MM-DD.",
    )
    normalize_numbers: bool = Field(
        default=True,
        description="Standardize numeric values (strip grouping commas/currency signs, parse floats/ints).",
    )
    identifier_columns: List[str] = Field(
        default_factory=list,
        description="List of column names (original or normalized) that must strictly be preserved as identifiers with leading zeros intact.",
    )
    max_rows: int = Field(
        default=100000,
        ge=1,
        le=500000,
        description="Safety row count limit for in-memory preprocessing.",
    )
    selected_worksheet: Optional[str] = Field(
        default=None,
        description=(
            "Batch 7: exact worksheet name to parse for XLSX workbooks. When omitted, "
            "legacy behavior applies (the workbook's active sheet is used). Never "
            "silently substituted: an unknown name fails with an actionable error."
        ),
    )

    model_config = ConfigDict(extra="ignore")


class ValidationIssue(BaseModel):
    """Validation issue, warning, or error generated during preprocessing."""

    level: str = Field(..., description="'error', 'warning', or 'info'")
    issue_type: str = Field(..., description="Machine-readable code, e.g. 'duplicate_header', 'type_mismatch'")
    message: str = Field(..., description="Human-readable description of the issue")
    row_number: Optional[int] = Field(default=None, description="1-based row number in original source file")
    column_name: Optional[str] = Field(default=None, description="Affected column name (original or normalized)")


class ColumnMetadata(BaseModel):
    """Metadata describing a single column after parsing and normalization."""

    original_name: str
    normalized_name: str
    detected_type: str = Field(
        ...,
        description="'identifier', 'integer', 'float', 'date', 'boolean', 'string', 'empty', or 'mixed'",
    )
    null_count: int = 0
    non_null_count: int = 0
    sample_values: List[Any] = Field(default_factory=list)


class PreprocessingResultResponse(BaseModel):
    """Structured response returned by the preprocessing pipeline."""

    source_file_id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    file_type: str
    total_source_rows: int
    data_rows_count: int
    empty_rows_count: int
    duplicate_rows_count: int
    columns: List[ColumnMetadata]
    column_mapping: Dict[str, str] = Field(
        description="Mapping of original column header -> normalized column name"
    )
    duplicate_record_row_numbers: List[List[int]] = Field(
        default_factory=list,
        description="Groups of 1-based source row numbers that contain identical records",
    )
    issues: List[ValidationIssue]
    preview_rows: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sample normalized data records (first 10 rows) with source_row_number included",
    )
    sheet_names: Optional[List[str]] = Field(
        default=None,
        description=(
            "Batch 7: for XLSX workbooks only — available worksheet names in workbook "
            "order, for explicit worksheet selection. None for CSV files."
        ),
    )
    selected_worksheet: Optional[str] = Field(
        default=None,
        description="Batch 7: the worksheet this preprocessing run parsed (XLSX only; None = active sheet).",
    )

    model_config = ConfigDict(from_attributes=True)
