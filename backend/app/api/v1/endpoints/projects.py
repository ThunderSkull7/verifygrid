from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.project import ProjectCreate, ProjectResponse
from app.services import project_service

router = APIRouter()


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
    description=(
        "Create a project with name and optional description. "
        "Temporary development note: Runs without authentication; owner_id is set to null."
    ),
)
def create_project_endpoint(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """
    Endpoint for creating a project.
    Delegates to project_service for database interaction.
    """
    return project_service.create_project(db=db, payload=payload)


@router.get(
    "",
    response_model=List[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="List projects",
    description="Retrieve a paginated list of projects ordered by creation date descending.",
)
def list_projects_endpoint(
    skip: int = Query(0, ge=0, description="Number of projects to skip for pagination"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of projects to return"),
    db: Session = Depends(get_db),
) -> List[ProjectResponse]:
    """
    Endpoint for querying projects.
    """
    return project_service.get_projects(db=db, skip=skip, limit=limit)
