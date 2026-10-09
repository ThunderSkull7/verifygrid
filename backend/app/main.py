from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router

app = FastAPI(
    title="VerifyGrid API",
    description="Backend API for intelligent data verification and reconciliation.",
    version="0.1.0",
)

# Development configuration for the React frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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
