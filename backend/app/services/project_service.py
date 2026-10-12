from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate


def create_project(db: Session, payload: ProjectCreate, current_user: Optional[User] = None) -> Project:
    """
    Create a new project record scoped to the authenticated user.
    """
    project = Project(
        name=payload.name,
        description=payload.description,
        owner_id=current_user.id if current_user else None,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_projects(db: Session, current_user: Optional[User] = None, skip: int = 0, limit: int = 100) -> List[Project]:
    """
    Retrieve a list of projects for the authenticated user, ordered by creation time descending.
    """
    stmt = select(Project)
    if current_user:
        stmt = stmt.where(Project.owner_id == current_user.id)
    stmt = (
        stmt.order_by(Project.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_project_by_id(db: Session, project_id, current_user: Optional[User] = None) -> Optional[Project]:
    """
    Retrieve a single project by primary key ID and verify user ownership.
    """
    stmt = select(Project).where(Project.id == project_id)
    if current_user:
        stmt = stmt.where(Project.owner_id == current_user.id)
    return db.scalars(stmt).first()
