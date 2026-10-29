"""Batch 11: reusable verification template service.

Personal-only launch: every operation is scoped to the authenticated owner
(404 on cross-user access, consistent with project handling). Organization
sharing is disabled — the visibility column is dormant and deny-by-default.

Applying a template VALIDATES configuration against newly uploaded files and
returns the effective verification request. It never executes verification;
execution continues through the existing verification endpoints.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.source_file import SourceFile
from app.models.user import User
from app.models.verification_template import VerificationTemplate
from app.schemas.multisource import MultiSourceVerificationRequest, SourceDefinition
from app.schemas.template import (
    SUPPORTED_TEMPLATE_MODES,
    TemplateApplyRequest,
    TemplateApplyResponse,
    TemplateConfigurationV1,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
    ValidationIssue,
    build_configuration,
)
from app.services.preprocessing import (
    extract_dataset_records,
    list_worksheet_names,
)
from app.schemas.preprocessing import PreprocessingConfig


# =============================================================================
# Persistence helpers (ownership-scoped)
# =============================================================================


def _get_owned_template(
    db: Session,
    template_id: uuid.UUID,
    current_user: User,
) -> VerificationTemplate:
    """Ownership-scoped lookup. Cross-user access yields 404 (never 403) so the
    existence of another user's template is never revealed."""
    template = (
        db.query(VerificationTemplate)
        .filter(
            VerificationTemplate.id == template_id,
            VerificationTemplate.owner_id == current_user.id,
        )
        .first()
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found.",
        )
    return template


def create_template(
    db: Session,
    payload: TemplateCreate,
    current_user: User,
) -> TemplateOut:
    """Create a personal template from a validated configuration snapshot."""
    # Strict configuration validation (unsupported versions / unexpected fields
    # raise ValueError, surfaced as 422 by the endpoint layer).
    build_configuration(payload.configuration)

    duplicate = (
        db.query(VerificationTemplate)
        .filter(
            VerificationTemplate.owner_id == current_user.id,
            VerificationTemplate.name == payload.name.strip(),
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A template named '{payload.name.strip()}' already exists.",
        )

    template = VerificationTemplate(
        owner_id=current_user.id,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        mode=payload.mode,
        visibility="personal",  # sharing disabled — dormant, deny-by-default
        config_version=1,
        configuration=payload.configuration,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return TemplateOut.model_validate(template)


def list_templates(
    db: Session,
    current_user: User,
    mode: Optional[str] = None,
) -> List[TemplateOut]:
    """List the current user's templates (personal-only scope)."""
    query = db.query(VerificationTemplate).filter(
        VerificationTemplate.owner_id == current_user.id
    )
    if mode:
        query = query.filter(VerificationTemplate.mode == mode)
    templates = query.order_by(VerificationTemplate.created_at.desc()).all()
    return [TemplateOut.model_validate(t) for t in templates]


def get_template(
    db: Session,
    template_id: uuid.UUID,
    current_user: User,
) -> TemplateOut:
    return TemplateOut.model_validate(_get_owned_template(db, template_id, current_user))


def update_template(
    db: Session,
    template_id: uuid.UUID,
    payload: TemplateUpdate,
    current_user: User,
) -> TemplateOut:
    template = _get_owned_template(db, template_id, current_user)

    if payload.name is not None and payload.name.strip() != template.name:
        duplicate = (
            db.query(VerificationTemplate)
            .filter(
                VerificationTemplate.owner_id == current_user.id,
                VerificationTemplate.name == payload.name.strip(),
            )
            .first()
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A template named '{payload.name.strip()}' already exists.",
            )
        template.name = payload.name.strip()

    if payload.description is not None:
        template.description = payload.description.strip() or None

    # visibility: schema validator rejects shared values; the effective value
    # can only ever remain 'personal' (sharing disabled).
    template.visibility = "personal"

    if payload.configuration is not None:
        # Full replacement, atomically re-validated (no partial merge).
        build_configuration(payload.configuration)
        template.configuration = payload.configuration
        template.config_version = int(payload.configuration.get("version", 1))

    db.commit()
    db.refresh(template)
    return TemplateOut.model_validate(template)


def delete_template(
    db: Session,
    template_id: uuid.UUID,
    current_user: User,
) -> None:
    template = _get_owned_template(db, template_id, current_user)
    db.delete(template)
    db.commit()


# =============================================================================
# Apply: validate a template against newly uploaded files
# =============================================================================


def _read_file_columns(
    path: Path,
    file_type: str,
    sheet_name: Optional[str],
) -> Tuple[List[str], Dict[str, str], List[ValidationIssue]]:
    """Parse a file's headers/columns for validation (no verification runs)."""
    issues: List[ValidationIssue] = []
    cfg = PreprocessingConfig()
    if sheet_name is not None:
        cfg = cfg.model_copy(update={"selected_worksheet": sheet_name})
    _, cols_meta, mapping, _, _, parse_issues, _ = extract_dataset_records(path, file_type, cfg)
    fatal = [i for i in parse_issues if getattr(i, "level", None) == "error"]
    for i in fatal:
        issues.append(ValidationIssue(message=i.message))
    # Available names include original and normalized header names plus the
    # normalized keys the engine will actually read from records.
    names: List[str] = list(mapping.keys()) + list(mapping.values())
    names += [c.normalized_name for c in cols_meta]
    return names, mapping, issues


def apply_template(
    db: Session,
    template_id: uuid.UUID,
    request: TemplateApplyRequest,
    current_user: User,
) -> TemplateApplyResponse:
    from app.services.project_service import get_project_by_id

    template = _get_owned_template(db, template_id, current_user)

    project = get_project_by_id(db, request.project_id, current_user=current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    if template.mode not in SUPPORTED_TEMPLATE_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Template mode '{template.mode}' cannot be applied in this release.",
        )

    config = build_configuration(template.configuration)
    assert isinstance(config, TemplateConfigurationV1)  # registry guarantees V1

    issues: List[ValidationIssue] = []
    warnings: List[str] = []

    # --- Slot binding completeness -------------------------------------------
    bindings = {b.slot: b.file_id for b in request.sources}
    slot_aliases = {s.alias for s in config.sources}
    bound_slots = set(bindings.keys())
    if bound_slots != slot_aliases:
        unknown = sorted(bound_slots - slot_aliases)
        missing = sorted(slot_aliases - bound_slots)
        if unknown:
            issues.append(
                ValidationIssue(
                    field="sources",
                    message=f"Unknown template slot(s) {unknown}; template slots are {sorted(slot_aliases)}.",
                )
            )
        if missing:
            issues.append(
                ValidationIssue(
                    field="sources",
                    message=f"Unbound template slot(s) {missing}; every slot must be bound to an uploaded file.",
                )
            )
    if len(bindings) != len(request.sources):
        issues.append(
            ValidationIssue(field="sources", message="Duplicate slot bindings are not allowed.")
        )
    if issues:
        return _blocked(template, request.project_id, issues, warnings)

    # --- Files must belong to the target project ------------------------------
    file_rows = (
        db.query(SourceFile)
        .filter(
            SourceFile.project_id == request.project_id,
            SourceFile.id.in_(list(bindings.values())),
        )
        .all()
    )
    files_by_id = {f.id: f for f in file_rows}
    for slot, file_id in bindings.items():
        if file_id not in files_by_id:
            issues.append(
                ValidationIssue(
                    slot=slot,
                    field="file_id",
                    message="Bound file was not found in this project.",
                )
            )
    if issues:
        return _blocked(template, request.project_id, issues, warnings)

    # --- Per-slot file validation: worksheets and columns ---------------------
    slot_columns: Dict[str, List[str]] = {}
    for slot_def in config.sources:
        source_file = files_by_id[bindings[slot_def.alias]]
        path_resolved = Path(source_file.storage_path).resolve()

        if source_file.file_type.lower() != "xlsx" and slot_def.sheet_name is not None:
            issues.append(
                ValidationIssue(
                    slot=slot_def.alias,
                    field="sheet_name",
                    message=(
                        f"Slot '{slot_def.alias}' specifies worksheet '{slot_def.sheet_name}', "
                        "but the bound file is a CSV. Worksheet selection applies only to XLSX."
                    ),
                )
            )
            slot_columns[slot_def.alias] = []
            continue

        if source_file.file_type.lower() == "xlsx" and slot_def.sheet_name is not None:
            available = list_worksheet_names(path_resolved)
            if slot_def.sheet_name not in available:
                issues.append(
                    ValidationIssue(
                        slot=slot_def.alias,
                        field="sheet_name",
                        message=(
                            f"Slot '{slot_def.alias}': selected worksheet '{slot_def.sheet_name}' "
                            f"was not found in the workbook. Available worksheets: {available}."
                        ),
                    )
                )
                slot_columns[slot_def.alias] = []
                continue

        cols, _, parse_issues = _read_file_columns(
            path_resolved, source_file.file_type, slot_def.sheet_name
        )
        issues.extend(ValidationIssue(slot=slot_def.alias, message=i.message) for i in parse_issues)
        slot_columns[slot_def.alias] = cols

        if not cols:
            continue  # parse errors already reported
        available = set(cols)
        missing_key_cols = [c for c in slot_def.key_columns if c not in available]
        if missing_key_cols:
            issues.append(
                ValidationIssue(
                    slot=slot_def.alias,
                    field="key_columns",
                    message=(
                        f"Slot '{slot_def.alias}': identity key column(s) {missing_key_cols} "
                        f"were not found in the file. Available columns: {sorted(available)}."
                    ),
                )
            )
        missing_mapped = [c for c in slot_def.field_mapping.keys() if c not in available]
        if missing_mapped:
            issues.append(
                ValidationIssue(
                    slot=slot_def.alias,
                    field="field_mapping",
                    message=(
                        f"Slot '{slot_def.alias}': mapped column(s) {missing_mapped} were not found "
                        f"in the file (possibly renamed). Available columns: {sorted(available)}."
                    ),
                )
            )

    if issues:
        return _blocked(template, request.project_id, issues, warnings)

    # --- Build the effective request (reuses ALL request invariants) ----------
    # Placeholder UUIDs are replaced with the real bindings below; the request
    # model's validators (roles, aliases, mapping ambiguity, fallback, ownership)
    # run exactly as they do for a direct verification call.
    source_defs = [
        SourceDefinition(
            alias=s.alias,
            file_id=bindings[s.alias],
            is_primary=s.is_primary,
            label=s.label,
            key_columns=s.key_columns,
            field_mapping=dict(s.field_mapping),
            sheet_name=s.sheet_name,
        )
        for s in config.sources
    ]
    try:
        effective = MultiSourceVerificationRequest(
            sources=source_defs,
            unified_keys=list(config.unified_keys),
            compare_attributes=config.compare_attributes,
            ignore_attributes=list(config.ignore_attributes),
            numeric_tolerance=config.numeric_tolerance,
            ignore_whitespace=config.ignore_whitespace,
            ignore_case=config.ignore_case,
            include_identical=config.include_identical,
            fallback_keys=config.fallback_keys,
            multi_primary=config.multi_primary,
            field_ownership=config.field_ownership,
        )
    except Exception as exc:  # pydantic ValidationError -> actionable 422
        detail = getattr(exc, "errors", lambda: [])()
        messages = [
            " -> ".join(str(loc) for loc in e.get("loc", [])) + f": {e.get('msg')}"
            for e in detail
        ]
        return _blocked(
            template,
            request.project_id,
            [ValidationIssue(field="configuration", message=m) for m in messages] or
            [ValidationIssue(field="configuration", message=str(exc))],
            warnings,
        )

    # compare_attributes must be mapped in at least one source pair to be
    # meaningful; unmapped compare attributes would silently vanish.
    if effective.compare_attributes:
        mapped_attrs = {a for s in effective.sources for a in s.field_mapping.values()}
        unmapped = [a for a in effective.compare_attributes if a not in mapped_attrs]
        if unmapped:
            return _blocked(
                template,
                request.project_id,
                [
                    ValidationIssue(
                        field="compare_attributes",
                        message=f"Compared attribute(s) {unmapped} are not mapped in any source "
                        "slot; map them or remove them from the template.",
                    )
                ],
                warnings,
            )

    return TemplateApplyResponse(
        template_id=template.id,
        project_id=request.project_id,
        mode=template.mode,
        effective_request=effective.model_dump(mode="json"),
        validation_report={"blocking": False, "issues": [], "warnings": warnings},
    )


def _blocked(
    template: VerificationTemplate,
    project_id: uuid.UUID,
    issues: List[ValidationIssue],
    warnings: List[str],
) -> TemplateApplyResponse:
    """Return a 422 with a structured, actionable validation report."""
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "message": "Template application blocked: validation failures must be corrected first.",
            "template_id": str(template.id),
            "project_id": str(project_id),
            "mode": template.mode,
            "validation_report": {
                "blocking": True,
                "issues": [i.model_dump() for i in issues],
                "warnings": warnings,
            },
        },
    )
