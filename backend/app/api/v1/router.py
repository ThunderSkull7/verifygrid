from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "service": "VerifyGrid API",
    }
