"""Tests for Authentication & Authorization."""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password, verify_password, create_access_token, decode_access_token


def test_password_hashing():
    """Verify password hashing generates unique salts and validates properly."""
    pwd = "super-secret-password-123"
    h1 = hash_password(pwd)
    h2 = hash_password(pwd)

    # Different salts produce different hashes
    assert h1 != h2
    assert h1.startswith("pbkdf2_sha256$")

    # Plain password verifies correctly
    assert verify_password(pwd, h1)
    assert verify_password(pwd, h2)

    # Invalid password fails
    assert not verify_password("wrong-password", h1)
    assert not verify_password("", h1)
    assert not verify_password(pwd, "")


def test_token_creation_and_expiration():
    """Verify JWT access token generation, decoding and expiration."""
    user_id = str(uuid.uuid4())
    token = create_access_token({"sub": user_id, "email": "jwt@example.com"}, expires_delta_seconds=60)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["email"] == "jwt@example.com"

    # Expired token returns None
    expired_token = create_access_token({"sub": user_id}, expires_delta_seconds=-10)
    assert decode_access_token(expired_token) is None

    # Tampered token returns None
    tampered = token[:-4] + "abcd"
    assert decode_access_token(tampered) is None


def test_register_and_login_success(client: TestClient):
    """Test full registration and login flow."""
    # Use unauthenticated client for register/login
    clean_client = TestClient(client.app)

    reg_payload = {
        "email": "alice@verifygrid.io",
        "password": "Password123!",
        "full_name": "Alice Auditor",
    }
    reg_res = clean_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["email"] == "alice@verifygrid.io"
    assert reg_data["user"]["full_name"] == "Alice Auditor"

    # Login with correct credentials
    login_payload = {
        "email": "alice@verifygrid.io",
        "password": "Password123!",
    }
    login_res = clean_client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data

    # Use received token to access /me
    me_res = clean_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_data['access_token']}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "alice@verifygrid.io"


def test_register_duplicate_email(client: TestClient):
    """Test registering an already existing email returns 409 Conflict."""
    clean_client = TestClient(client.app)
    payload = {
        "email": "bob@verifygrid.io",
        "password": "Password123!",
    }
    r1 = clean_client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201

    r2 = clean_client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"]


def test_login_invalid_credentials(client: TestClient):
    """Test login with wrong password or non-existent user returns 401."""
    clean_client = TestClient(client.app)
    # Non-existent email
    r1 = clean_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Password123!"},
    )
    assert r1.status_code == 401

    # Register first
    clean_client.post(
        "/api/v1/auth/register",
        json={"email": "carol@verifygrid.io", "password": "CorrectPassword123"},
    )
    # Wrong password
    r2 = clean_client.post(
        "/api/v1/auth/login",
        json={"email": "carol@verifygrid.io", "password": "WrongPassword"},
    )
    assert r2.status_code == 401


def test_unauthenticated_request_rejected(client: TestClient):
    """Ensure protected endpoints return 401 when no token is provided."""
    clean_client = TestClient(client.app)

    # Projects
    assert clean_client.get("/api/v1/projects").status_code == 401
    assert clean_client.post("/api/v1/projects", json={"name": "P"}).status_code == 401

    fake_id = str(uuid.uuid4())
    # Uploads
    assert clean_client.post(f"/api/v1/projects/{fake_id}/files").status_code == 401
    # Preprocessing
    assert clean_client.post(f"/api/v1/projects/{fake_id}/files/{fake_id}/preprocess").status_code == 401
    # Verification
    assert clean_client.post(f"/api/v1/projects/{fake_id}/verify", json={}).status_code == 401
    assert clean_client.get(f"/api/v1/projects/{fake_id}/runs").status_code == 401
    assert clean_client.get(f"/api/v1/projects/{fake_id}/runs/{fake_id}/export").status_code == 401

    # Health endpoints remain public
    assert clean_client.get("/api/v1/health").status_code == 200
    assert clean_client.get("/").status_code == 200


def test_cross_user_project_isolation(client: TestClient):
    """
    Ensure User A cannot view, access, upload to, or export from User B's projects (IDOR protection).
    """
    clean_client = TestClient(client.app)

    # Register User A
    res_a = clean_client.post("/api/v1/auth/register", json={"email": "usera@example.com", "password": "PasswordA123"})
    token_a = res_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register User B
    res_b = clean_client.post("/api/v1/auth/register", json={"email": "userb@example.com", "password": "PasswordB123"})
    token_b = res_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates a project
    proj_res = clean_client.post("/api/v1/projects", json={"name": "User A Private Project"}, headers=headers_a)
    assert proj_res.status_code == 201
    proj_a_id = proj_res.json()["id"]

    # User B lists projects -> should be empty
    list_b = clean_client.get("/api/v1/projects", headers=headers_b)
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # User A lists projects -> sees their project
    list_a = clean_client.get("/api/v1/projects", headers=headers_a)
    assert list_a.status_code == 200
    assert len(list_a.json()) == 1
    assert list_a.json()[0]["id"] == proj_a_id

    # User B attempts to upload file to User A's project -> 404
    upload_res = clean_client.post(
        f"/api/v1/projects/{proj_a_id}/files",
        files={"file": ("test.csv", b"id\n1\n", "text/csv")},
        headers=headers_b,
    )
    assert upload_res.status_code == 404
    assert upload_res.json()["detail"] == "Project not found."

    # User B attempts to access verification runs of User A's project -> 404
    runs_res = clean_client.get(f"/api/v1/projects/{proj_a_id}/runs", headers=headers_b)
    assert runs_res.status_code == 404
    assert runs_res.json()["detail"] == "Project not found."
