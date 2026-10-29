"""Batch 11: reusable verification template endpoints.

Personal-only templates. Every operation requires authentication and is
scoped to the authenticated owner; cross-user access returns 404 (never 403)
so the existence of another user's template is never revealed.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.template import (
    TemplateApplyRequest,
    TemplateApplyResponse,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
)
from app.services import template_service

router = APIRouter()


@router.get(
    "",
    response_model=List[TemplateOut],
    status_code=status.HTTP_200_OK,
    summary="List the current user's verification templates",
)
def list_templates_endpoint(
    mode: Optional[str] = Query(None, description="Filter by verification mode."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[TemplateOut]:
    return template_service.list_templates(db, current_user, mode=mode)


@router.post(
    "",
    response_model=TemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a personal verification template",
)
def create_template_endpoint(
    payload: TemplateCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TemplateOut:
    try:
        return template_service.create_template(db, payload, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.get(
    "/{template_id}",
    response_model=TemplateOut,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a template",
)
def get_template_endpoint(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TemplateOut:
    return template_service.get_template(db, template_id, current_user)


@router.put(
    "/{template_id}",
    response_model=TemplateOut,
    status_code=status.HTTP_200_OK,
    summary="Update a template",
)
def update_template_endpoint(
    template_id: uuid.UUID,
    payload: TemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TemplateOut:
    try:
        return template_service.update_template(db, template_id, payload, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a template",
)
def delete_template_endpoint(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    template_service.delete_template(db, template_id, current_user)


@router.post(
    "/{template_id}/apply",
    response_model=TemplateApplyResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate a template against newly uploaded files",
    description=(
        "Validates worksheet selections, column availability, identity keys, fallback keys, "
        "multi-primary/ownership settings against the bound files and returns the effective "
        "verification request. Does NOT execute verification — submit the returned "
        "effective_request to the existing verification endpoints."
    ),
)
def apply_template_endpoint(
    template_id: uuid.UUID,
    payload: TemplateApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TemplateApplyResponse:
    return template_service.apply_template(db, template_id, payload, current_user)
