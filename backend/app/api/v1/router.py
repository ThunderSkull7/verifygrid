import logging
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.v1.endpoints.projects import router as projects_router
from app.api.v1.endpoints.uploads import router as uploads_router
from app.api.v1.endpoints.preprocessing import router as preprocessing_router

logger = logging.getLogger(__name__)

api_router = APIRouter()


@api_router.get("/health", tags=["System"])
def health_check():
    """
    Standard application liveness check.
    Does not depend on external services like the database.
    """
    return {
        "status": "healthy",
        "service": "VerifyGrid API",
    }


@api_router.get("/health/db", tags=["System"])
def health_check_db(db: Session = Depends(get_db)):
    """
    Database connectivity check.
    Executes a lightweight ping (SELECT 1). Returns 200 if reachable,
    or 503 Service Unavailable without exposing internal connection details or credentials.
    """
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception as exc:
        logger.warning("Database connectivity check failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": "Database is unreachable",
            },
        )


# Include resource routers
api_router.include_router(projects_router, prefix="/projects", tags=["Projects"])
api_router.include_router(uploads_router, tags=["Uploads"])
api_router.include_router(preprocessing_router, tags=["Preprocessing"])
