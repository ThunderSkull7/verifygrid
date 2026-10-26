import os

# Permanently enforce isolated in-memory SQLite database before any app or settings imports
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models.user import User
from app.core.security import hash_password, create_access_token

# Isolated in-memory SQLite database for fast, self-contained unit tests
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Create all tables in the SQLite test database once for the test session.
    """
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """
    Provide an isolated database session per test with automatic rollback/cleanup.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def default_user(db_session: Session) -> User:
    """Create a default authenticated test user."""
    user = User(
        email="testuser@example.com",
        hashed_password=hash_password("password123"),
        full_name="Test User",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def auth_headers(default_user: User) -> dict:
    """Generate bearer token auth headers for the default test user."""
    token = create_access_token({"sub": str(default_user.id), "email": default_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db_session: Session, auth_headers: dict) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient with overridden get_db and default auth headers for convenience.
    """
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.headers.update(auth_headers)
        yield test_client
    app.dependency_overrides.clear()

