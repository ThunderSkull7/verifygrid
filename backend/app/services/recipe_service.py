"""Recipe service for exporting and applying reusable reconciliation blueprints (.verifygrid.json)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.source_file import SourceFile
from app.models.user import User
from app.models.verification_run import VerificationRun
from app.schemas.preprocessing import PreprocessingConfig
from app.schemas.recipe import (
    ExpectedSourceSchema,
    RecipeApplyRequest,
    RecipeApplyValidationResult,
    RecipeQuarantineDefaults,
    RecipeSourceMatch,
    VerificationRecipe,
)
from app.services.preprocessing import extract_dataset_records
from app.services.project_service import get_project_by_id
from app.services.verification_engine import get_verification_run


def _get_file_columns(file_path: Path, file_type: str) -> List[str]:
    """Inspect dataset headers without processing full records."""
    try:
        cfg = PreprocessingConfig()
        recs, _, _, _, _, _, _ = extract_dataset_records(file_path, file_type, cfg)
        if recs:
            return list(recs[0][1].keys())
        return []
    except Exception:
        return []


def export_recipe_from_run(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: Optional[User] = None,
) -> VerificationRecipe:
    """
    Export a reusable reconciliation recipe standard (.verifygrid.json)
    from a persistent verification run.
    """
    project = get_project_by_id(db, project_id, current_user=current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    run = get_verification_run(db, project_id, run_id, current_user=current_user)
    config = run.configuration or {}
    storage_root = settings.storage_root.resolve()

    sources_list: List[ExpectedSourceSchema] = []
    run_sources = run.sources or []

    # If run has rich sources array
    if run_sources:
        for idx, s in enumerate(run_sources):
            alias = s.get("alias") or f"source_{idx + 1}"
            file_id_str = s.get("file_id")
            expected_cols: List[str] = []
            if file_id_str:
                try:
                    f_uuid = uuid.UUID(file_id_str)
                    sf = db.query(SourceFile).filter(SourceFile.id == f_uuid, SourceFile.project_id == project_id).first()
                    if sf and sf.storage_path:
                        p = Path(sf.storage_path).resolve()
                        if p.exists() and str(p).startswith(str(storage_root)):
                            expected_cols = _get_file_columns(p, sf.file_type)
                except Exception:
                    pass

            sources_list.append(
                ExpectedSourceSchema(
                    alias=alias,
                    expected_columns=expected_cols,
                    key_columns=s.get("key_columns") or run.key_columns or [],
                    field_mapping=s.get("field_mapping") or {},
                    is_primary=s.get("is_primary", idx == 0),
                )
            )
    else:
        # Fall back to source_file / target_file
        src_cols: List[str] = []
        tgt_cols: List[str] = []
        if run.source_file and run.source_file.storage_path:
            p = Path(run.source_file.storage_path).resolve()
            if p.exists():
                src_cols = _get_file_columns(p, run.source_file.file_type)
        if run.target_file and run.target_file.storage_path:
            p = Path(run.target_file.storage_path).resolve()
            if p.exists():
                tgt_cols = _get_file_columns(p, run.target_file.file_type)

        sources_list.append(
            ExpectedSourceSchema(
                alias="source",
                expected_columns=src_cols,
                key_columns=run.key_columns or [],
                field_mapping=run.column_mapping or {},
                is_primary=True,
            )
        )
        sources_list.append(
            ExpectedSourceSchema(
                alias="target",
                expected_columns=tgt_cols,
                key_columns=run.key_columns or [],
                field_mapping={v: k for k, v in (run.column_mapping or {}).items()},
                is_primary=False,
            )
        )

    recipe = VerificationRecipe(
        version="1.0.0",
        recipe_name=f"{project.name} - Reconciliation Recipe",
        description=f"Generated from Verification Run {run.id.hex[:8]} on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}",
        created_at=datetime.now(timezone.utc).isoformat(),
        sources=sources_list,
        unified_keys=run.key_columns or config.get("unified_keys") or [],
        numeric_tolerance=float(config.get("numeric_tolerance", 0.0)),
        ignore_whitespace=bool(config.get("ignore_whitespace", True)),
        ignore_case=bool(config.get("ignore_case", True)),
        include_identical=bool(config.get("include_identical", True)),
        status_rules=config.get("status_rules"),
        rule_config=config.get("rule_config"),
        quarantine_defaults=RecipeQuarantineDefaults(
            quarantine_resolution_policy="EXCLUDE_UNRESOLVED",
            auto_accept_minor_warnings=False,
        ),
        metadata={
            "run_id": str(run.id),
            "project_id": str(project_id),
            "project_name": project.name,
            "engine_version": "VerifyGrid 2.0.0",
        },
    )
    return recipe


def apply_recipe_to_files(
    db: Session,
    project_id: uuid.UUID,
    request: RecipeApplyRequest,
    current_user: Optional[User] = None,
) -> RecipeApplyValidationResult:
    """
    Validate uploaded files against a .verifygrid.json recipe and generate
    suggested wizard blueprint configurations.
    """
    project = get_project_by_id(db, project_id, current_user=current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    recipe = request.recipe
    file_ids = request.file_ids
    if not file_ids:
        all_files = db.query(SourceFile).filter(SourceFile.project_id == project_id).all()
        file_ids = [f.id for f in all_files]

    files = db.query(SourceFile).filter(
        SourceFile.project_id == project_id,
        SourceFile.id.in_(file_ids),
    ).all()

    storage_root = settings.storage_root.resolve()
    file_cols_map: Dict[uuid.UUID, List[str]] = {}
    file_obj_map: Dict[uuid.UUID, SourceFile] = {f.id: f for f in files}

    for f in files:
        if f.storage_path:
            p = Path(f.storage_path).resolve()
            if p.exists() and str(p).startswith(str(storage_root)):
                file_cols_map[f.id] = _get_file_columns(p, f.file_type)
            else:
                file_cols_map[f.id] = []
        else:
            file_cols_map[f.id] = []

    explicit_mappings = request.file_mappings or {}
    assigned_file_ids: Set[uuid.UUID] = set()
    source_matches: List[RecipeSourceMatch] = []
    suggested_source_aliases: Dict[str, str] = {}
    suggested_file_key_columns: Dict[str, List[str]] = {}
    warnings: List[str] = []
    errors: List[str] = []

    # Map each recipe source alias to an uploaded file
    for src in recipe.sources:
        matched_file: Optional[SourceFile] = None

        # 1. Check explicit mapping first
        if src.alias in explicit_mappings:
            target_id = explicit_mappings[src.alias]
            if target_id in file_obj_map:
                matched_file = file_obj_map[target_id]

        # 2. Heuristic match: filename match or column set overlap
        if not matched_file:
            best_score = -1.0
            best_candidate: Optional[SourceFile] = None
            for f in files:
                if f.id in assigned_file_ids:
                    continue
                score = 0.0
                fname = f.original_filename.lower()
                if src.alias.lower() in fname:
                    score += 5.0
                actual_cols = set(c.lower() for c in file_cols_map.get(f.id, []))
                expected_cols = set(c.lower() for c in src.expected_columns)
                if expected_cols:
                    overlap = len(actual_cols.intersection(expected_cols)) / len(expected_cols)
                    score += overlap * 10.0
                key_cols = set(k.lower() for k in src.key_columns)
                if key_cols and key_cols.issubset(actual_cols):
                    score += 15.0

                if score > best_score and score > 0:
                    best_score = score
                    best_candidate = f

            matched_file = best_candidate

        if matched_file:
            assigned_file_ids.add(matched_file.id)
            actual_cols = file_cols_map.get(matched_file.id, [])
            actual_cols_lower = {c.lower(): c for c in actual_cols}

            matched_cols: List[str] = []
            missing_cols: List[str] = []
            for col in src.expected_columns:
                if col.lower() in actual_cols_lower:
                    matched_cols.append(actual_cols_lower[col.lower()])
                else:
                    missing_cols.append(col)

            if not actual_cols:
                keys_present = True
                file_keys = list(src.key_columns)
                matched_cols = list(src.expected_columns)
                missing_cols = []
                warnings.append(
                    f"Source file '{matched_file.original_filename}' content not read on disk; assumed schema compatible."
                )
            else:
                keys_present = True
                file_keys = []
                for k in src.key_columns:
                    if k.lower() in actual_cols_lower:
                        file_keys.append(actual_cols_lower[k.lower()])
                    else:
                        keys_present = False

                if not keys_present:
                    errors.append(
                        f"Source '{src.alias}' mapped to '{matched_file.original_filename}' is missing key column(s): {', '.join(src.key_columns)}"
                    )

                if missing_cols:
                    warnings.append(
                        f"Source '{src.alias}' in '{matched_file.original_filename}' is missing {len(missing_cols)} non-key columns from recipe: {', '.join(missing_cols[:5])}"
                    )

            source_matches.append(
                RecipeSourceMatch(
                    alias=src.alias,
                    file_id=matched_file.id,
                    filename=matched_file.original_filename,
                    matched_columns=matched_cols,
                    missing_columns=missing_cols,
                    key_columns_present=keys_present,
                )
            )
            suggested_source_aliases[str(matched_file.id)] = src.alias
            suggested_file_key_columns[str(matched_file.id)] = file_keys or src.key_columns
        else:
            errors.append(f"Could not find a matching uploaded file for recipe source '{src.alias}'.")
            source_matches.append(
                RecipeSourceMatch(
                    alias=src.alias,
                    file_id=None,
                    filename=None,
                    matched_columns=[],
                    missing_columns=src.expected_columns,
                    key_columns_present=False,
                )
            )

    is_valid = len(errors) == 0

    return RecipeApplyValidationResult(
        valid=is_valid,
        recipe_name=recipe.recipe_name,
        version=recipe.version,
        source_matches=source_matches,
        suggested_unified_keys=recipe.unified_keys,
        suggested_source_aliases=suggested_source_aliases,
        suggested_file_key_columns=suggested_file_key_columns,
        rule_config=recipe.rule_config,
        numeric_tolerance=recipe.numeric_tolerance,
        status_rules=recipe.status_rules,
        ignore_whitespace=recipe.ignore_whitespace,
        ignore_case=recipe.ignore_case,
        warnings=warnings,
        errors=errors,
    )
