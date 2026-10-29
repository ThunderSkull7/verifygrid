"""API endpoints for reusable recipe standards (.verifygrid.json)."""

from __future__ import annotations

import json
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.recipe import (
    RecipeApplyRequest,
    RecipeApplyValidationResult,
    VerificationRecipe,
)
from app.services.recipe_service import apply_recipe_to_files, export_recipe_from_run

router = APIRouter(tags=["recipes"])


@router.get(
    "/projects/{project_id}/runs/{run_id}/recipe",
    response_model=VerificationRecipe,
    status_code=status.HTTP_200_OK,
    summary="Export run configuration as recipe standard (.verifygrid.json)",
    description="Generates a reusable recipe (.verifygrid.json) capturing source schemas, key columns, tolerances, and rule definitions.",
)
def export_recipe_endpoint(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    download: bool = Query(False, description="Whether to prompt browser file download"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export recipe configuration standard."""
    recipe = export_recipe_from_run(
        db=db,
        project_id=project_id,
        run_id=run_id,
        current_user=current_user,
    )
    if download:
        clean_name = recipe.recipe_name.lower().replace(" ", "_").replace("-", "_")
        filename = f"{clean_name}_{run_id.hex[:8]}.verifygrid.json"
        content = json.dumps(recipe.model_dump(mode="json"), indent=2).encode("utf-8")
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return recipe


@router.post(
    "/projects/{project_id}/recipes/apply",
    response_model=RecipeApplyValidationResult,
    status_code=status.HTTP_200_OK,
    summary="Validate and apply recipe to uploaded project files",
    description="Validates schema compatibility of a .verifygrid.json recipe against uploaded source files and returns pre-populated wizard blueprint settings.",
)
def apply_recipe_endpoint(
    project_id: uuid.UUID,
    request: RecipeApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeApplyValidationResult:
    """Validate and apply recipe to project files."""
    return apply_recipe_to_files(
        db=db,
        project_id=project_id,
        request=request,
        current_user=current_user,
    )
