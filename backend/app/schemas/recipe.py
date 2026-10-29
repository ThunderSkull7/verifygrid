"""Pydantic schemas for reusable reconciliation recipes (.verifygrid.json)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExpectedSourceSchema(BaseModel):
    """Schema expectations for a participating source in a recipe."""
    alias: str
    expected_columns: List[str] = Field(default_factory=list)
    key_columns: List[str] = Field(default_factory=list)
    field_mapping: Dict[str, str] = Field(default_factory=dict)
    is_primary: bool = False


class RecipeQuarantineDefaults(BaseModel):
    """Quarantine resolution defaults to apply when loading a recipe."""
    quarantine_resolution_policy: str = "EXCLUDE_UNRESOLVED"
    auto_accept_minor_warnings: bool = False


class VerificationRecipe(BaseModel):
    """Standardized versioned recipe (.verifygrid.json) capturing complete reconciliation configuration."""
    version: str = "1.0.0"
    recipe_name: str
    description: Optional[str] = None
    created_at: Optional[str] = None
    sources: List[ExpectedSourceSchema] = Field(default_factory=list)
    unified_keys: List[str] = Field(default_factory=list)
    numeric_tolerance: float = 0.0
    ignore_whitespace: bool = True
    ignore_case: bool = True
    include_identical: bool = True
    status_rules: Optional[Dict[str, Any]] = None
    rule_config: Optional[Dict[str, Any]] = None
    quarantine_defaults: Optional[RecipeQuarantineDefaults] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RecipeApplyRequest(BaseModel):
    """Request to validate and apply a recipe to uploaded project files."""
    recipe: VerificationRecipe
    file_ids: List[uuid.UUID] = Field(default_factory=list)
    file_mappings: Optional[Dict[str, uuid.UUID]] = None


class RecipeSourceMatch(BaseModel):
    """Match status of a source alias against an uploaded file."""
    alias: str
    file_id: Optional[uuid.UUID] = None
    filename: Optional[str] = None
    matched_columns: List[str] = Field(default_factory=list)
    missing_columns: List[str] = Field(default_factory=list)
    key_columns_present: bool = True


class RecipeApplyValidationResult(BaseModel):
    """Validation report and suggested wizard settings after applying recipe."""
    valid: bool
    recipe_name: str
    version: str = "1.0.0"
    source_matches: List[RecipeSourceMatch] = Field(default_factory=list)
    suggested_unified_keys: List[str] = Field(default_factory=list)
    suggested_source_aliases: Dict[str, str] = Field(default_factory=dict)  # str(file_id) -> alias
    suggested_file_key_columns: Dict[str, List[str]] = Field(default_factory=dict)  # str(file_id) -> key_cols
    rule_config: Optional[Dict[str, Any]] = None
    numeric_tolerance: float = 0.0
    status_rules: Optional[Dict[str, Any]] = None
    ignore_whitespace: bool = True
    ignore_case: bool = True
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
