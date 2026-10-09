from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

def get_engine_args(database_url: str) -> dict:
    """
    Return appropriate engine arguments depending on the database dialect.
    Ensures PostgreSQL gets connection pooling and health checking,
    while SQLite (used for tests) avoids unsupported pool parameters.
    """
    if database_url.startswith("sqlite"):
        return {
            "connect_args": {"check_same_thread": False},
        }
    return {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_recycle": settings.db_pool_recycle,
        "pool_timeout": settings.db_pool_timeout,
        "connect_args": {"connect_timeout": settings.db_connect_timeout},
    }


# Engine creation in SQLAlchemy does not establish immediate database connections.
# Connections are acquired lazily on first query/checkout, allowing FastAPI to start
# cleanly even if the PostgreSQL instance is temporarily unavailable.
engine = create_engine(
    settings.database_url,
    **get_engine_args(settings.database_url),
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a SQLAlchemy session per request.
    Guarantees the session is closed when the request lifecycle finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
