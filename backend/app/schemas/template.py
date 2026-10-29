"""Batch 11: reusable verification template schemas.

Templates store a versioned, validated configuration snapshot. The schema is
strict (`extra="forbid"`) so invalid or unexpected fields can never be silently
discarded. Per-upload state (file IDs, row indices, quarantine resolutions,
records, credentials) has no field to occupy — leakage is impossible by shape.

Organization sharing is DISABLED in this release: the application has no
Organization entity or membership/authorization model, so `visibility` accepts
only 'personal' and rejects anything else (deny-by-default for the dormant
shared state).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.schemas.preprocessing import PreprocessingConfig  # re-exported context only


SUPPORTED_TEMPLATE_MODES = ("organization",)
SUPPORTED_CONFIG_VERSIONS = (1,)
DISABLED_VISIBILITIES = ("organization_shared",)


class TemplateSourceSlot(BaseModel):
    """Reusable per-source slot of a template. No file binding is stored."""

    model_config = ConfigDict(extra="forbid")

    alias: str = Field(..., min_length=1, max_length=80)
    label: Optional[str] = Field(default=None, max_length=120)
    is_primary: bool = False
    key_columns: List[str] = Field(..., min_length=1)
    field_mapping: Dict[str, str] = Field(default_factory=dict)
    sheet_name: Optional[str] = Field(
        default=None,
        description="Batch 7 worksheet selection, revalidated against every new XLSX upload.",
    )

    @field_validator("label", "sheet_name", "alias")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("key_columns")
    @classmethod
    def _clean_key_columns(cls, v: List[str]) -> List[str]:
        cleaned = [c.strip() for c in v if c and c.strip()]
        if not cleaned:
            raise ValueError("key_columns must contain at least one non-empty column name.")
        return cleaned


class TemplateConfigurationBase(BaseModel):
    """Common fields of a template configuration snapshot (organization mode)."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(
        ...,
        description="Configuration schema version. Must be one of the supported versions.",
    )
    sources: List[TemplateSourceSlot] = Field(..., min_length=2)
    unified_keys: List[str] = Field(..., min_length=1)
    compare_attributes: Optional[List[str]] = None
    ignore_attributes: List[str] = Field(default_factory=list)
    numeric_tolerance: float = Field(default=0.0, ge=0.0)
    ignore_whitespace: bool = True
    ignore_case: bool = False
    include_identical: bool = True
    fallback_keys: Optional[List[List[str]]] = None
    multi_primary: bool = False
    field_ownership: Optional[Dict[str, str]] = None

    @field_validator("unified_keys")
    @classmethod
    def _clean_unified_keys(cls, v: List[str]) -> List[str]:
        cleaned = [k.strip() for k in v if k and k.strip()]
        if not cleaned:
            raise ValueError("unified_keys must contain at least one non-empty attribute name.")
        return cleaned

    @field_validator("fallback_keys")
    @classmethod
    def _clean_fallback_keys(cls, v: Optional[List[List[str]]]) -> Optional[List[List[str]]]:
        if v is None:
            return None
        cleaned: List[List[str]] = []
        for fk in v:
            attrs = [a.strip() for a in fk if a and a.strip()]
            if not attrs:
                raise ValueError("Each fallback key must contain at least one attribute.")
            if attrs in cleaned:
                raise ValueError(f"Duplicate fallback key definition: {attrs}.")
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
    def _validate_structure(self) -> "TemplateConfigurationBase":
        aliases = [s.alias for s in self.sources]
        # Role invariants (mirrors MultiSourceVerificationRequest, Batch 5).
        primary_aliases = [s.alias for s in self.sources if s.is_primary]
        if len(primary_aliases) == 0:
            raise ValueError(
                "A template requires at least one primary source, but none was marked primary."
            )
        if len(primary_aliases) > 1 and not self.multi_primary:
            raise ValueError(
                "Multiple primary sources require enabling multi-primary mode, but it was not enabled."
            )
        if len(set(aliases)) != len(aliases):
            raise ValueError("Source aliases must be unique within a template.")
        if len(set(k.strip() for k in self.unified_keys)) != len(self.unified_keys):
            raise ValueError("unified_keys must be unique within a template.")
        # Per-source mapping sanity: no two columns mapping to the same attribute
        # (mirrors the Batch 3 request invariant).
        for s in self.sources:
            attrs = list(s.field_mapping.values())
            duplicates = sorted({a for a in attrs if attrs.count(a) > 1})
            if duplicates:
                raise ValueError(
                    f"Ambiguous column mapping in source '{s.alias}': multiple columns map "
                    f"to the same attribute(s) {duplicates}."
                )
        # Every unified key must be mapped in every source (identity requires it).
        mapped_keys = set(self.unified_keys)
        for s in self.sources:
            missing = mapped_keys - set(s.field_mapping.values())
            if missing:
                raise ValueError(
                    f"Source '{s.alias}' does not map identity key attribute(s) "
                    f"{sorted(missing)}; every source must map the identity keys."
                )
        # Fallback invariants (Batch 4/5).
        if self.fallback_keys:
            key_set = tuple(sorted(k.strip() for k in self.unified_keys))
            for fb in self.fallback_keys:
                if tuple(sorted(fb)) == key_set:
                    raise ValueError(
                        f"Fallback key {fb} is identical to the primary matching key; "
                        "remove it or choose different attributes."
                    )
        if self.field_ownership and not self.multi_primary:
            raise ValueError("field_ownership requires multi_primary=true.")
        if self.multi_primary:
            if self.fallback_keys:
                raise ValueError(
                    "Fallback matching is not supported together with multi-primary mode."
                )
            alias_set = set(aliases)
            key_attrs = {k.strip() for k in self.unified_keys}
            for attr, owner in (self.field_ownership or {}).items():
                if owner not in alias_set:
                    raise ValueError(
                        f"Field ownership for '{attr}' references unknown source alias '{owner}'."
                    )
                if attr in key_attrs:
                    raise ValueError(
                        f"Identity key attribute '{attr}' cannot have a field owner."
                    )
                owner_slot = next(s for s in self.sources if s.alias == owner)
                if attr not in owner_slot.field_mapping.values():
                    raise ValueError(
                        f"Field ownership for '{attr}' is invalid: source '{owner}' does not map it."
                    )
        # Compare attributes must be mapped somewhere they can be compared.
        if self.compare_attributes:
            key_attrs = {k.strip() for k in self.unified_keys}
            overlap = set(self.compare_attributes) & key_attrs
            if overlap:
                raise ValueError(
                    f"compare_attributes must not include identity keys: {sorted(overlap)}."
                )
        return self


class TemplateConfigurationV1(TemplateConfigurationBase):
    """Configuration snapshot, schema version 1 (the only supported version)."""

    version: Literal[1] = Field(
        1,
        description="Configuration schema version. Only version 1 is supported.",
    )


def build_configuration(data: Dict[str, Any]) -> TemplateConfigurationBase:
    """
    Parse a raw configuration payload, enforcing the version registry.

    Unsupported versions raise ValueError (surfaced as HTTP 422 by the API) —
    they are never silently downgraded or partially loaded.
    """
    if not isinstance(data, dict):
        raise ValueError("Template configuration must be a JSON object.")
    version = data.get("version")
    if version not in SUPPORTED_CONFIG_VERSIONS:
        raise ValueError(
            f"Unsupported template configuration version: {version!r}. "
            f"Supported versions: {list(SUPPORTED_CONFIG_VERSIONS)}."
        )
    # Registry: only V1 exists today; future versions add branches here.
    return TemplateConfigurationV1.model_validate(data)


# =============================================================================
# API payloads
# =============================================================================


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    mode: str = Field(..., description="Verification mode. Only 'organization' is supported.")
    visibility: Optional[str] = Field(
        default="personal",
        description="Template visibility. Organization sharing is disabled; only 'personal'.",
    )
    configuration: Dict[str, Any]

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in SUPPORTED_TEMPLATE_MODES:
            raise ValueError(
                f"Unsupported template mode '{v}'. Supported modes: {list(SUPPORTED_TEMPLATE_MODES)}. "
                "Financial Auditing templates are not supported in this release."
            )
        return v

    @field_validator("visibility")
    @classmethod
    def _validate_visibility(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return "personal"
        v = (v or "").strip()
        if v in DISABLED_VISIBILITIES:
            raise ValueError(
                f"Visibility '{v}' is disabled: organization sharing is not supported because "
                "the application has no Organization membership model yet."
            )
        if v != "personal":
            raise ValueError(f"Unknown visibility '{v}'. Only 'personal' is supported.")
        return v


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    visibility: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None

    @field_validator("visibility")
    @classmethod
    def _validate_visibility(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = (v or "").strip()
        if v in DISABLED_VISIBILITIES:
            raise ValueError(
                f"Visibility '{v}' is disabled: organization sharing is not supported because "
                "the application has no Organization membership model yet."
            )
        if v != "personal":
            raise ValueError(f"Unknown visibility '{v}'. Only 'personal' is supported.")
        return v


class TemplateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    mode: str
    visibility: str
    config_version: int
    created_at: Any
    updated_at: Any


class TemplateOut(TemplateSummary):
    configuration: Dict[str, Any]

    @computed_field(description="Number of source slots in the template configuration.")
    @property
    def source_count(self) -> int:
        return len(self.configuration.get("sources", []))


class TemplateSourceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str = Field(..., description="Template source alias being bound to an uploaded file.")
    file_id: uuid.UUID = Field(..., description="Uploaded file (in the target project) for this slot.")


class TemplateApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    # At least one binding is accepted at the transport layer so that partial
    # bindings reach the service and are reported as structured, slot-level
    # issues (missing slots, unknown slots). Completeness against the template
    # configuration is enforced by the apply service, never inferred here.
    sources: List[TemplateSourceBinding] = Field(..., min_length=1)


class ValidationIssue(BaseModel):
    slot: Optional[str] = None
    field: Optional[str] = None
    message: str


class TemplateApplyResponse(BaseModel):
    template_id: uuid.UUID
    project_id: uuid.UUID
    mode: str
    # Effective MultiSourceVerificationRequest payload (file IDs substituted),
    # ready for POST /projects/{project_id}/verify/multi-source.
    effective_request: Dict[str, Any]
    validation_report: Dict[str, Any]
