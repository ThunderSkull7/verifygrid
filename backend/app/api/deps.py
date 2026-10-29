"""FastAPI dependencies for user authentication and authorization."""

from __future__ import annotations

import uuid
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User

security_bearer = HTTPBearer(auto_error=False)

VALID_ROLES = frozenset({"MAKER", "CHECKER", "ADMIN", "VIEWER"})


def get_authoritative_role(user: User) -> str:
    """Resolve the server-side role, failing closed on missing/unknown values."""
    raw = getattr(user, "role", None)
    role = str(raw).strip().upper() if raw is not None else ""
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Authenticated user has no recognized role; this action is denied."
            ),
        )
    return role


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    """Return a dependency that requires one of the authoritative server roles."""
    normalized = frozenset(role.strip().upper() for role in allowed_roles)
    if not normalized or not normalized.issubset(VALID_ROLES):
        raise ValueError("require_roles() received an invalid role set.")

    def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        role = get_authoritative_role(current_user)
        if role not in normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{role}' is not authorized for this action; "
                    f"requires one of: {', '.join(sorted(normalized))}."
                ),
            )
        return current_user

    return role_dependency


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate request via Bearer JWT token.
    Raises HTTP 401 Unauthorized if missing, invalid, or expired.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token principal identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account has been removed.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# Defined after get_current_user so the nested dependency default resolves at
# module import time.
require_admin = require_roles("ADMIN")


def verify_project_access(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    """
    Enforce tenant isolation by verifying that the project exists and belongs
    to the authenticated user. Prevents IDOR vulnerabilities.
    """
    from app.services.project_service import get_project_by_id

    project = get_project_by_id(db, project_id, current_user=current_user)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return project
