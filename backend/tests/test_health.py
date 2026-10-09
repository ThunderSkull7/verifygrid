from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db


def test_root_endpoint(client: TestClient):
    """
    Ensure root endpoint returns 200 and basic API details.
    """
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Welcome to VerifyGrid API"
    assert data["docs"] == "/docs"


def test_health_check_endpoint(client: TestClient):
    """
    Ensure the standard /api/v1/health endpoint returns 200 OK.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "VerifyGrid API"


def test_health_check_db_connected(client: TestClient):
    """
    Ensure /api/v1/health/db returns 200 OK when database is reachable.
    """
    response = client.get("/api/v1/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_health_check_db_disconnected():
    """
    Ensure /api/v1/health/db returns 503 Service Unavailable when database fails,
    without leaking internal exceptions, passwords, or connection strings.
    """
    def broken_get_db():
        mock_db = MagicMock()
        mock_db.execute.side_effect = ConnectionRefusedError("Simulated database failure")
        yield mock_db

    app.dependency_overrides[get_db] = broken_get_db
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/api/v1/health/db")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["database"] == "disconnected"
            assert data["error"] == "Database is unreachable"
    finally:
        app.dependency_overrides.clear()
