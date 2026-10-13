from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router

app = FastAPI(
    title="VerifyGrid API",
    description="Backend API for intelligent data verification and reconciliation.",
    version="0.1.0",
)

from app.core.config import settings

# CORS configuration supporting environment variable overrides for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Welcome to VerifyGrid API",
        "docs": "/docs",
        "version": "0.1.0",
    }
