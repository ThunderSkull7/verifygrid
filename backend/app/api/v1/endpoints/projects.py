from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services import project_service

router = APIRouter()


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
    description="Create a project scoped to the authenticated user.",
)
def create_project_endpoint(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """
    Endpoint for creating a project scoped to current user.
    """
    return project_service.create_project(db=db, payload=payload, current_user=current_user)


@router.get(
    "",
    response_model=List[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="List projects",
    description="Retrieve a paginated list of projects owned by the authenticated user.",
)
def list_projects_endpoint(
    skip: int = Query(0, ge=0, description="Number of projects to skip for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of projects to return"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ProjectResponse]:
    """
    Endpoint for querying projects owned by current user.
    """
    return project_service.get_projects(db=db, current_user=current_user, skip=skip, limit=limit)
