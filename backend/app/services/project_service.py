from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.project import Project
from app.schemas.project import ProjectCreate


def create_project(db: Session, payload: ProjectCreate) -> Project:
    """
    Create a new project record.

    NOTE (Temporary Development Approach):
    Authentication and user management are planned for a subsequent milestone.
    To ensure security and prevent arbitrary owner injection from client payloads,
    `owner_id` is intentionally set to None rather than accepting an unverified
    ID from the request. When authentication is introduced, `owner_id` will be
    derived directly from the authenticated user's session context.
    """
    project = Project(
        name=payload.name,
        description=payload.description,
        owner_id=None,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_projects(db: Session, skip: int = 0, limit: int = 100) -> List[Project]:
    """
    Retrieve a list of projects ordered by creation time descending.
    """
    stmt = (
        select(Project)
        .order_by(Project.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_project_by_id(db: Session, project_id) -> Optional[Project]:
    """
    Retrieve a single project by primary key ID.
    """
    stmt = select(Project).where(Project.id == project_id)
    return db.scalars(stmt).first()
