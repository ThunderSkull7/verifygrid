"""Multi-source verification, ingestion, and alignment schemas."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
        max_length=80,
        description="Unique identifier alias for this source (e.g. 'erp', 'bank', 'gateway', 'source_a')",
    )
    file_id: uuid.UUID = Field(
        ...,
        description="UUID of the uploaded source file",
    )
    is_primary: bool = Field(
        default=False,
        description="Whether this dataset serves as the primary/golden baseline. "
        "This is the single source of truth for source roles.",
    )
    label: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Optional user-editable display label for the source (e.g. 'Academic Records'). "
        "Purely descriptive; never used for matching.",
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
    sheet_name: Optional[str] = Field(
        default=None,
        description=(
            "Batch 7: exact worksheet name to parse for XLSX source files. When set, "
            "the named worksheet (and only it) is ingested; an unknown name fails with "
            "an actionable error. When omitted, legacy behavior applies (active sheet) "
            "and the used sheet is not user-verified. Ignored for CSV sources."
        ),
    )

    @field_validator("label")
    @classmethod
    def _clean_label(cls, v: Optional[str]) -> Optional[str]:
        """Trim and normalize empty labels to None; constrain length."""
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("sheet_name")
    @classmethod
    def _clean_sheet_name(cls, v: Optional[str]) -> Optional[str]:
        """Trim; empty strings normalize to None (legacy active-sheet behavior)."""
        if v is None:
            return None
        v = v.strip()
        return v or None


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
    rule_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional versioned rule configuration and 1:N aggregation settings.",
    )
    preprocessing_config: Optional[PreprocessingConfig] = Field(
        default=None,
        description="Optional preprocessing config overrides.",
    )
    fallback_keys: Optional[List[List[str]]] = Field(
        default=None,
        description=(
            "Batch 4: ordered fallback matching keys for records the primary key cannot match. "
            "Each entry is a list of unified attribute names (composite supported), resolved to "
            "per-source columns via field_mapping. Tried in configured order after primary-key "
            "matching; requires exact normalized-value equality and a unique unambiguous candidate."
        ),
    )
    multi_primary: bool = Field(
        default=False,
        description=(
            "Batch 5 opt-in: enable multi-primary comparison with per-field ownership. "
            "When False (default), legacy semantics apply: exactly one primary source is "
            "required and every secondary source is compared against it."
        ),
    )
    field_ownership: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Batch 5 (requires multi_primary): per-attribute authoritative source, "
            "{unified_attribute -> owner source alias}. The owner's mapped column value is "
            "authoritative; every other source carrying the attribute is compared against it. "
            "Attributes without an entry default to the first primary source. Identity "
            "(matching) is unaffected by ownership."
        ),
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("fallback_keys")
    @classmethod
    def _clean_fallback_keys(cls, v: Optional[List[List[str]]]) -> Optional[List[List[str]]]:
        """Trim attribute names, reject empty definitions and duplicates."""
        if v is None:
            return None
        cleaned: List[List[str]] = []
        for fk in v:
            attrs = [a.strip() for a in fk if a and a.strip()]
            if not attrs:
                raise ValueError(
                    "Each fallback key must contain at least one attribute; "
                    "remove empty fallback definitions."
                )
            if attrs in cleaned:
                raise ValueError(f"Duplicate fallback key definition: {attrs}. Each fallback may appear once.")
            cleaned.append(attrs)
        return cleaned or None

    @field_validator("field_ownership")
    @classmethod
    def _clean_field_ownership(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if v is None:
            return None
        cleaned = {a.strip(): o.strip() for a, o in v.items() if a and a.strip() and o and o.strip()}
        return cleaned or None

    @model_validator(mode="after")
    def _validate_primary_role_invariant(self) -> "MultiSourceVerificationRequest":
        """Server-side role invariants (Batch 5).

        Legacy mode (multi_primary=False, default): exactly one primary source —
        zero or multiple primaries are rejected with HTTP 422, never silently
        defaulted. Multi-primary mode (explicit opt-in): at least one primary is
        still required, several are allowed, and per-field ownership governs
        which source is authoritative for each attribute.
        """
        primary_aliases = [s.alias for s in self.sources if s.is_primary]
        if len(primary_aliases) == 0:
            raise ValueError(
                "Verification requires at least one primary source, but none was marked primary. "
                "Mark one source as primary in your file setup."
            )
        if len(primary_aliases) > 1 and not self.multi_primary:
            raise ValueError(
                "Multiple primary sources require enabling multi-primary mode, but it was not enabled. "
                f"{len(primary_aliases)} sources were marked primary: {primary_aliases}. "
                "Keep exactly one primary, or explicitly enable multi-primary comparison."
            )
        if len({s.alias for s in self.sources}) != len(self.sources):
            raise ValueError("Source aliases must be unique within a request.")
        # Batch 3: reject ambiguous duplicate column mappings within a single source.
        # field_mapping is {source_column -> unified_attribute}; if two different source
        # columns map to the same unified attribute the engine could resolve the value
        # non-deterministically, so treat it as a configuration error.
        for s in self.sources:
            attrs = list(s.field_mapping.values())
            duplicates = sorted({a for a in attrs if attrs.count(a) > 1})
            if duplicates:
                raise ValueError(
                    f"Ambiguous column mapping in source '{s.alias}': multiple columns map to the same "
                    f"attribute(s) {duplicates}. Map each attribute to exactly one column per source."
                )
        # Batch 4: fallback keys must differ from the primary matching key (a fallback
        # identical to the unified key is a no-op and signals a configuration mistake).
        if self.fallback_keys:
            key_set = tuple(sorted(k.strip() for k in self.unified_keys))
            for fb in self.fallback_keys:
                if tuple(sorted(fb)) == key_set:
                    raise ValueError(
                        f"Fallback key {fb} is identical to the primary matching key "
                        f"{self.unified_keys}; remove it or choose different attributes."
                    )
        # Batch 5: multi-primary rules.
        if self.field_ownership and not self.multi_primary:
            raise ValueError(
                "field_ownership requires explicitly enabling multi-primary mode (multi_primary=true). "
                "Either remove field_ownership or enable multi-primary comparison."
            )
        if self.multi_primary:
            if self.fallback_keys:
                raise ValueError(
                    "Fallback matching is not yet supported together with multi-primary mode "
                    "(the fallback pre-pass is anchored on a single primary source). "
                    "Remove fallback_keys or disable multi_primary."
                )
            aliases = {s.alias for s in self.sources}
            key_attrs = {k.strip() for k in self.unified_keys}
            for attr, owner in (self.field_ownership or {}).items():
                if owner not in aliases:
                    raise ValueError(
                        f"Field ownership for '{attr}' references unknown source alias '{owner}'. "
                        f"Known sources: {sorted(aliases)}."
                    )
                if attr in key_attrs:
                    raise ValueError(
                        f"Identity key attribute '{attr}' cannot have a field owner; "
                        "ownership applies to compared attributes only."
                    )
                owner_source = next(s for s in self.sources if s.alias == owner)
                if attr not in owner_source.field_mapping.values():
                    raise ValueError(
                        f"Field ownership for '{attr}' is invalid: source '{owner}' does not map "
                        f"that attribute (its column mapping: {owner_source.field_mapping}). "
                        "Map the attribute in the owning source first."
                    )
        return self


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
