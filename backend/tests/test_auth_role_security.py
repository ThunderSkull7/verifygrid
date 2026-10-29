"""Comprehensive security regression tests for VerifyGrid.

Verifies the five core security invariants:
1. Public registration cannot assign ADMIN or any other role (extra="forbid").
2. Authorization never trusts the X-User-Role header; authoritative role is resolved server-side.
3. Role elevation is strictly administrator-only via PATCH /api/v1/users/{user_id}/role.
4. Tenant isolation: project ownership checks prevent cross-project IDOR access.
5. Review, governance, and audit endpoints enforce authentication, authorization, and maker-checker separation.
"""

from __future__ import annotations

import io
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.project import Project
from app.models.user import User
from app.models.verification_run import VerificationRun, VerificationDiscrepancy


def _create_user(db: Session, email: str, role: str = "MAKER") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("Password123!"),
        full_name="Test Security User",
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_header(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# 1. Public Registration Role Escalation Resistance
# =============================================================================


def test_public_registration_rejects_admin_role_payload(client: TestClient):
    """Public registration must reject explicit role assignment with HTTP 422."""
    for forbidden_role in ["ADMIN", "CHECKER", "MAKER", "VIEWER", "SUPERUSER"]:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"hacker-{forbidden_role.lower()}@example.com",
                "password": "Password123!",
                "full_name": "Attacker",
                "role": forbidden_role,
            },
        )
        assert response.status_code == 422, response.text
        assert "extra" in response.text.lower() or "forbidden" in response.text.lower() or "value" in response.text.lower()


def test_public_registration_assigns_maker_by_default(client: TestClient, db_session: Session):
    """Public registration without role succeeds and strictly sets role='MAKER'."""
    email = f"legit-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Legitimate User",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["user"]["role"] == "MAKER"

    db_user = db_session.query(User).filter(User.email == email).first()
    assert db_user is not None
    assert db_user.role == "MAKER"


# =============================================================================
# 2. Authorization Never Trusts X-User-Role
# =============================================================================


def test_governance_ignores_x_user_role_header(client: TestClient, db_session: Session):
    """A MAKER sending X-User-Role: CHECKER or ADMIN must still be denied checker actions."""
    maker = _create_user(db_session, f"maker-{uuid.uuid4().hex[:8]}@example.com", role="MAKER")
    attacker = _create_user(db_session, f"attacker-{uuid.uuid4().hex[:8]}@example.com", role="MAKER")

    project = Project(name="SecGovProject", owner_id=maker.id)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    run = VerificationRun(
        project_id=project.id,
        status="completed",
        key_columns=["id"],
        column_mapping={},
        configuration={},
        summary={},
        sign_off_status="AWAITING_SIGN_OFF",
        sign_off_proposed_by=maker.id,
        sign_off_proposed_by_name="Maker",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # Attacker tries to approve using forged X-User-Role headers on maker's project
    for forged_header in ["CHECKER", "ADMIN", "checker", "ADMIN "]:
        resp = client.post(
            f"/api/v1/projects/{project.id}/runs/{run.id}/sign-off/approve",
            json={"note": "I forged the checker header!"},
            headers={
                **_auth_header(attacker),
                "X-User-Role": forged_header,
            },
        )
        assert resp.status_code == 404, resp.text  # Blocked by project access

    # Now attacker is owner of their project, but their authoritative role in users.role is MAKER
    proj_maker = Project(name="AttackerProj", owner_id=attacker.id)
    db_session.add(proj_maker)
    db_session.commit()
    db_session.refresh(proj_maker)

    run_maker = VerificationRun(
        project_id=proj_maker.id,
        status="completed",
        key_columns=["id"],
        column_mapping={},
        configuration={},
        summary={},
        sign_off_status="AWAITING_SIGN_OFF",
        sign_off_proposed_by=maker.id,
        sign_off_proposed_by_name="Maker",
    )
    db_session.add(run_maker)
    db_session.commit()
    db_session.refresh(run_maker)

    # Attacker attempts to approve sign-off sending X-User-Role: CHECKER
    resp = client.post(
        f"/api/v1/projects/{proj_maker.id}/runs/{run_maker.id}/sign-off/approve",
        json={"note": "I am a maker pretending to be checker!"},
        headers={
            **_auth_header(attacker),
            "X-User-Role": "CHECKER",
        },
    )
    # Must fail closed with 403 Forbidden
    assert resp.status_code == 403, resp.text
    assert "CHECKER" in resp.text or "not authorized" in resp.text.lower() or "lacks authority" in resp.text.lower()

    # Sign-off state must remain untouched
    db_session.refresh(run_maker)
    assert run_maker.sign_off_status == "AWAITING_SIGN_OFF"
    assert run_maker.sign_off_approved_by is None


# =============================================================================
# 3. Role Elevation is Administrator-Only
# =============================================================================


def test_role_elevation_requires_admin(client: TestClient, db_session: Session):
    """Non-admin roles (MAKER, CHECKER, VIEWER) cannot elevate roles."""
    target = _create_user(db_session, f"target-{uuid.uuid4().hex[:8]}@example.com", role="MAKER")

    for unprivileged_role in ["MAKER", "CHECKER", "VIEWER"]:
        actor = _create_user(db_session, f"actor-{uuid.uuid4().hex[:8]}@example.com", role=unprivileged_role)
        resp = client.patch(
            f"/api/v1/users/{target.id}/role",
            json={"role": "ADMIN"},
            headers=_auth_header(actor),
        )
        assert resp.status_code == 403, f"{unprivileged_role} should receive 403, got {resp.status_code}"
        assert "ADMIN" in resp.text

    # Unauthenticated caller returns 401
    resp = client.patch(
        f"/api/v1/users/{target.id}/role",
        json={"role": "ADMIN"},
        headers={"Authorization": ""},
    )
    assert resp.status_code == 401


def test_role_elevation_admin_success_and_validation(client: TestClient, db_session: Session):
    """ADMIN can change user roles; invalid role formats are rejected with 422."""
    admin = _create_user(db_session, f"admin-{uuid.uuid4().hex[:8]}@example.com", role="ADMIN")
    target = _create_user(db_session, f"target-{uuid.uuid4().hex[:8]}@example.com", role="MAKER")

    # Admin elevates target to CHECKER
    resp = client.patch(
        f"/api/v1/users/{target.id}/role",
        json={"role": "CHECKER"},
        headers=_auth_header(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "CHECKER"
    db_session.refresh(target)
    assert target.role == "CHECKER"

    # Reject invalid target roles with 422
    for invalid in ["SUPERUSER", "admin", "checker ", "", "ROOT"]:
        resp = client.patch(
            f"/api/v1/users/{target.id}/role",
            json={"role": invalid},
            headers=_auth_header(admin),
        )
        assert resp.status_code == 422, f"Expected 422 for {invalid!r}, got {resp.status_code}"


# =============================================================================
# 4. Tenant Isolation / IDOR Protection
# =============================================================================


def test_cross_project_idor_protection(client: TestClient, db_session: Session):
    """User B cannot access or modify User A's project resources."""
    user_a = _create_user(db_session, f"usera-{uuid.uuid4().hex[:8]}@example.com", role="MAKER")
    user_b = _create_user(db_session, f"userb-{uuid.uuid4().hex[:8]}@example.com", role="MAKER")

    project_a = Project(name="Project A", owner_id=user_a.id)
    db_session.add(project_a)
    db_session.commit()
    db_session.refresh(project_a)

    run_a = VerificationRun(
        project_id=project_a.id,
        status="completed",
        key_columns=["id"],
        column_mapping={},
        configuration={},
        summary={},
    )
    db_session.add(run_a)
    db_session.commit()
    db_session.refresh(run_a)

    headers_b = _auth_header(user_b)

    # 1. Project file upload
    resp = client.post(
        f"/api/v1/projects/{project_a.id}/files",
        files={"file": ("test.csv", io.BytesIO(b"id,name\n1,Alice\n"), "text/csv")},
        headers=headers_b,
    )
    assert resp.status_code == 404

    # 2. Audit trail access
    resp = client.get(
        f"/api/v1/projects/{project_a.id}/runs/{run_a.id}/audit-trail",
        headers=headers_b,
    )
    assert resp.status_code == 404

    # 3. Governance sign-off details
    resp = client.get(
        f"/api/v1/projects/{project_a.id}/runs/{run_a.id}/sign-off",
        headers=headers_b,
    )
    assert resp.status_code == 404

    # 4. Propose sign-off
    resp = client.post(
        f"/api/v1/projects/{project_a.id}/runs/{run_a.id}/sign-off/propose",
        json={"note": "Intrusion attempt"},
        headers=headers_b,
    )
    assert resp.status_code == 404

    # 5. Clusters endpoint
    resp = client.get(
        f"/api/v1/projects/{project_a.id}/runs/{run_a.id}/clusters",
        headers=headers_b,
    )
    assert resp.status_code == 404


# =============================================================================
# 5. Review, Governance, and Audit Endpoint Authorization
# =============================================================================


def test_maker_checker_separation_enforced(client: TestClient, db_session: Session):
    """The user who proposed a sign-off cannot countersign/approve their own sign-off."""
    admin_user = _create_user(db_session, f"adminmc-{uuid.uuid4().hex[:8]}@example.com", role="ADMIN")
    checker_user = _create_user(db_session, f"checkermc-{uuid.uuid4().hex[:8]}@example.com", role="CHECKER")

    project = Project(name="MakerCheckerProj", owner_id=admin_user.id)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    run = VerificationRun(
        project_id=project.id,
        status="completed",
        key_columns=["id"],
        column_mapping={},
        configuration={},
        summary={},
        sign_off_status="DRAFT",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # admin_user proposes sign-off (ADMIN has maker capability)
    prop_resp = client.post(
        f"/api/v1/projects/{project.id}/runs/{run.id}/sign-off/propose",
        json={"note": "Proposed by admin_user acting as maker"},
        headers=_auth_header(admin_user),
    )
    assert prop_resp.status_code == 200, prop_resp.text
    assert prop_resp.json()["sign_off_status"] == "AWAITING_SIGN_OFF"

    # Same admin_user attempts to approve -> Must be rejected with 403 Separation of Duties violation
    appr_resp = client.post(
        f"/api/v1/projects/{project.id}/runs/{run.id}/sign-off/approve",
        json={"note": "Self-approving by same admin"},
        headers=_auth_header(admin_user),
    )
    assert appr_resp.status_code == 403, appr_resp.text
    assert "separation of duties" in appr_resp.text.lower() or "maker" in appr_resp.text.lower()

    # Different checker can approve after project ownership transferred or shared
    project.owner_id = checker_user.id
    db_session.commit()

    ok_resp = client.post(
        f"/api/v1/projects/{project.id}/runs/{run.id}/sign-off/approve",
        json={"note": "Approved by independent checker"},
        headers=_auth_header(checker_user),
    )
    assert ok_resp.status_code == 200, ok_resp.text
    assert ok_resp.json()["sign_off_status"] == "APPROVED"
