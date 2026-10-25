"""API endpoints for Versioned Rule Engine and Preview (Batch 4)."""

import uuid
from pathlib import Path
from typing import Dict, List, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.project import Project
from app.models.source_file import SourceFile
from app.models.user import User
from app.schemas.preprocessing import PreprocessingConfig
from app.schemas.rule import (
    RulePreviewRequest,
    RulePreviewResponse,
    RuleValidateRequest,
    RuleValidateResponse,
)
from app.services.preprocessing import extract_dataset_records
from app.services.profiling_service import get_excluded_row_indices_for_file
from app.services.project_service import get_project_by_id
from app.services.rule_engine import preview_rule_impact, validate_rule_config

router = APIRouter()


@router.post(
    "/projects/{project_id}/rules/validate",
    response_model=RuleValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate rule syntax and dataset column existence",
    description="Validates JSON rule syntax and verifies that referenced column names exist in uploaded project files.",
)
def validate_rules_endpoint(
    project_id: uuid.UUID,
    request: RuleValidateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleValidateResponse:
    """Validate rule syntax and verify field existence against datasets."""
    project = get_project_by_id(db, project_id, current_user=current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    # Resolve column names for requested files
    source_schemas: Dict[str, List[str]] = {}
    cfg = PreprocessingConfig()
    storage_root_resolved = settings.storage_root.resolve()

    # If source definitions provided
    if request.sources:
        for s in request.sources:
            sf = db.query(SourceFile).filter(
                SourceFile.id == s.file_id,
                SourceFile.project_id == project_id,
            ).first()
            if sf:
                p = Path(sf.storage_path).resolve()
                if p.exists() and str(p).startswith(str(storage_root_resolved)):
                    try:
                        _, cols, _, _, _, _, _ = extract_dataset_records(p, sf.file_type, cfg)
                        col_names = []
                        for c in cols:
                            if hasattr(c, "original_name"):
                                col_names.append(c.original_name)
                                if hasattr(c, "normalized_name") and c.normalized_name:
                                    col_names.append(c.normalized_name)
                            else:
                                col_names.append(str(c))
                        source_schemas[s.alias] = col_names
                    except Exception:
                        pass

    # If file_ids provided
    elif request.file_ids:
        for fid in request.file_ids:
            sf = db.query(SourceFile).filter(
                SourceFile.id == fid,
                SourceFile.project_id == project_id,
            ).first()
            if sf:
                p = Path(sf.storage_path).resolve()
                if p.exists() and str(p).startswith(str(storage_root_resolved)):
                    try:
                        _, cols, _, _, _, _, _ = extract_dataset_records(p, sf.file_type, cfg)
                        col_names = []
                        for c in cols:
                            if hasattr(c, "original_name"):
                                col_names.append(c.original_name)
                                if hasattr(c, "normalized_name") and c.normalized_name:
                                    col_names.append(c.normalized_name)
                            else:
                                col_names.append(str(c))
                        source_schemas[str(fid)] = col_names
                    except Exception:
                        pass

    return validate_rule_config(request.rules, source_schemas=source_schemas)


@router.post(
    "/projects/{project_id}/rules/preview",
    response_model=RulePreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Dry-run rule impact preview on sampled records",
    description="Simulates rule execution against uploaded files to return passing vs exception projections.",
)
def preview_rules_endpoint(
    project_id: uuid.UUID,
    request: RulePreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RulePreviewResponse:
    """Perform a dry-run rule preview across datasets."""
    project = get_project_by_id(db, project_id, current_user=current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    cfg = PreprocessingConfig()
    storage_root_resolved = settings.storage_root.resolve()
    sources_data: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}

    for s in request.sources:
        sf = db.query(SourceFile).filter(
            SourceFile.id == s.file_id,
            SourceFile.project_id == project_id,
        ).first()
        if sf is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source file {s.file_id} ({s.alias}) not found.",
            )

        p = Path(sf.storage_path).resolve()
        if not str(p).startswith(str(storage_root_resolved)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access to file path for {s.alias} is restricted.",
            )
        if not p.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File content for {s.alias} not found on disk.",
            )

        if not s.excluded_row_indices:
            s.excluded_row_indices = get_excluded_row_indices_for_file(p)

        ex_rows = set(s.excluded_row_indices or [])
        recs, _, _, _, _, _, _ = extract_dataset_records(p, sf.file_type, cfg)
        sources_data[s.alias] = [
            (r_idx, r) for r_idx, r in recs if r_idx not in ex_rows
        ]

    # If aggregation is configured and enabled, use aggregation engine for the preview
    if request.rules.aggregation_config and request.rules.aggregation_config.enabled:
        from app.services.aggregation_engine import reconcile_split_payments
        ac = request.rules.aggregation_config
        p_recs = sources_data.get(ac.parent_source_alias, [])
        c_recs = sources_data.get(ac.child_source_alias, [])

        summary, results, discrepancies = reconcile_split_payments(
            parent_records=p_recs[:request.sample_size],
            child_records=c_recs[:request.sample_size],
            config=ac,
            date_window_rules=request.rules.date_window_rules,
            include_identical=True,
        )

        sample_disc_list = [
            {
                "key": d.key_values,
                "status": d.match_status.value,
                "reason": d.reason_code.value if d.reason_code else None,
                "message": d.message,
                "aggregated_amount": d.aggregated_amount,
                "expected_amount": d.expected_amount,
            }
            for d in discrepancies[:10]
        ]

        exceptions_by_rule = {}
        for d in discrepancies:
            st = d.match_status.value
            exceptions_by_rule[st] = exceptions_by_rule.get(st, 0) + 1

        return RulePreviewResponse(
            total_evaluated=min(len(p_recs), request.sample_size),
            passed_count=summary.identical_matches,
            exception_count=summary.total_discrepancies,
            exceptions_by_rule=exceptions_by_rule,
            exceptions_by_severity={"BLOCKING": summary.total_discrepancies, "WARNING": 0, "INFO": 0},
            sample_discrepancies=sample_disc_list,
        )

    return preview_rule_impact(
        config=request.rules,
        sources_data=sources_data,
        sample_size=request.sample_size,
    )
