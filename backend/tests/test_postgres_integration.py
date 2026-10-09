import pytest
from sqlalchemy import create_engine, text
from app.core.config import settings


def is_postgres_accessible() -> bool:
    """
    Attempt a non-blocking short timeout probe to verify if PostgreSQL is reachable.
    """
    if not settings.database_url.startswith("postgresql"):
        return False
    try:
        # Probe with a short 2-second connect timeout
        probe_engine = create_engine(
            settings.database_url,
            connect_args={"connect_timeout": 2},
        )
        with probe_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        probe_engine.dispose()
        return True
    except Exception:
        return False


POSTGRES_AVAILABLE = is_postgres_accessible()


@pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason=(
        "Live PostgreSQL instance is not reachable at DATABASE_URL. "
        "Run PostgreSQL locally or set DATABASE_URL to enable live integration tests."
    ),
)
class TestPostgresIntegration:
    """
    Dedicated integration test suite that executes strictly against a real PostgreSQL instance.
    This is kept isolated from SQLite unit tests.
    """

    def test_live_postgres_connectivity(self):
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            assert result == 1
            assert engine.dialect.name == "postgresql"
        engine.dispose()
