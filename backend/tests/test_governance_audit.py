import copy
import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditEvent
from app.models.project import Project
from app.models.user import User
from app.models.verification_run import VerificationRun
from app.schemas.audit import AuditEventType
from app.schemas.governance import (
    ApproveSignOffRequest,
    ProposeSignOffRequest,
    RejectSignOffRequest,
    SignOffStatus,
    UserRole,
)
from app.services.audit_service import (
    GENESIS_HASH,
    compute_event_hash,
    get_audit_trail,
    log_audit_event,
    serialize_canonical_payload,
    verify_audit_chain,
)
from app.services.governance_service import (
    approve_run_sign_off,
    get_sign_off_details,
    propose_run_sign_off,
    reject_run_sign_off,
)


@pytest.fixture
def maker_user(db_session: Session) -> User:
    """Create a user with role MAKER."""
    user = User(
        email="maker@example.com",
        hashed_password=hash_password("makerpass123"),
        full_name="Maker Alice",
        role="MAKER",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def checker_user(db_session: Session) -> User:
    """Create a user with role CHECKER."""
    user = User(
        email="checker@example.com",
        hashed_password=hash_password("checkerpass123"),
        full_name="Checker Bob",
        role="CHECKER",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def viewer_user(db_session: Session) -> User:
    """Create a user with role VIEWER."""
    user = User(
        email="viewer@example.com",
        hashed_password=hash_password("viewerpass123"),
        full_name="Viewer Charlie",
        role="VIEWER",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def sample_project_and_run(db_session: Session):
    """Create a project and persistent verification run for governance tests."""
    project = Project(
        name="Governance Test Project",
        description="Testing Maker-Checker and Tamper-evident Audit",
        owner_id=None,
    )
    db_session.add(project)
    db_session.flush()

    run = VerificationRun(
        project_id=project.id,
        status="completed",
        key_columns=["account_id"],
        sign_off_status=SignOffStatus.DRAFT.value,
        summary={"total_records": 100, "gross_exposure": 5400.0},
    )
    db_session.add(run)
    db_session.commit()
    return project, run


def test_maker_proposal_creation_and_status_transition(
    db_session: Session, maker_user: User, sample_project_and_run
):
    """Test that a Maker can propose a sign-off, transitioning the run to AWAITING_SIGN_OFF."""
    project, run = sample_project_and_run

    req = ProposeSignOffRequest(
        note="Reconciliation reviewed; tolerances within acceptable bounds.",
        proposed_by_name="Maker Alice",
    )
    res = propose_run_sign_off(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        user=maker_user,
        request=req,
    )

    assert res.sign_off_status == SignOffStatus.AWAITING_SIGN_OFF.value
    assert res.sign_off_proposed_by == maker_user.id
    assert res.sign_off_proposed_by_name == "Maker Alice"
    assert res.sign_off_proposal_note == req.note
    assert res.sign_off_proposed_at is not None
    assert res.is_maker is True
    assert res.can_approve is False  # Maker cannot approve own submission

    # Verify audit event was logged
    events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.run_id == run.id)
        .order_by(AuditEvent.sequence_number.asc())
        .all()
    )
    assert len(events) == 1
    assert events[0].event_type == AuditEventType.RUN_SIGN_OFF_PROPOSED.value
    assert events[0].sequence_number == 1
    assert events[0].previous_event_hash == GENESIS_HASH


def test_separation_of_duties_blocks_self_approval(
    db_session: Session, maker_user: User, sample_project_and_run
):
    """Test that Maker-Checker separation of duties strictly prevents self-approval."""
    project, run = sample_project_and_run

    # 1. Maker proposes sign-off
    propose_run_sign_off(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        user=maker_user,
        request=ProposeSignOffRequest(note="Proposing my own run."),
    )

    # 2. Maker attempts to approve/countersign their own proposal (even with admin/checker role override)
    with pytest.raises(Exception) as excinfo:
        approve_run_sign_off(
            db=db_session,
            project_id=project.id,
            run_id=run.id,
            user=maker_user,
            request=ApproveSignOffRequest(note="Self-approval attempt"),
            role_override="CHECKER",
        )
    assert "Separation of Duties violation" in str(excinfo.value)

    # Verify run remains in AWAITING_SIGN_OFF state
    db_session.refresh(run)
    assert run.sign_off_status == SignOffStatus.AWAITING_SIGN_OFF.value
    assert run.sign_off_approved_by is None


def test_distinct_checker_countersignature_and_rejection(
    db_session: Session,
    maker_user: User,
    checker_user: User,
    viewer_user: User,
    sample_project_and_run,
):
    """Test distinct Checker countersigning and approving, and rejecting with mandatory note."""
    project, run = sample_project_and_run

    # Propose sign-off as Maker
    propose_run_sign_off(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        user=maker_user,
        request=ProposeSignOffRequest(note="Ready for checker review."),
    )

    # Viewer cannot approve
    with pytest.raises(Exception) as exc_viewer:
        approve_run_sign_off(
            db=db_session,
            project_id=project.id,
            run_id=run.id,
            user=viewer_user,
            request=ApproveSignOffRequest(note="Viewer approval attempt"),
        )
    assert "lacks authority" in str(exc_viewer.value)

    # Rejection requires mandatory note
    with pytest.raises(Exception) as exc_empty_note:
        reject_run_sign_off(
            db=db_session,
            project_id=project.id,
            run_id=run.id,
            user=checker_user,
            request=RejectSignOffRequest(note="   "),
        )
    assert "Mandatory justification note is required" in str(exc_empty_note.value)

    # Checker rejects proposal with valid reason
    rej_res = reject_run_sign_off(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        user=checker_user,
        request=RejectSignOffRequest(note="Missing tax reconciliation schedule; please re-run."),
    )
    assert rej_res.sign_off_status == SignOffStatus.REJECTED.value
    assert rej_res.sign_off_decision_note == "Missing tax reconciliation schedule; please re-run."

    # Maker re-proposes after addressing feedback
    propose_run_sign_off(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        user=maker_user,
        request=ProposeSignOffRequest(note="Tax schedule attached and reconciled."),
    )

    # Distinct Checker countersigns and approves
    app_res = approve_run_sign_off(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        user=checker_user,
        request=ApproveSignOffRequest(note="Countersigned and verified."),
    )
    assert app_res.sign_off_status == SignOffStatus.APPROVED.value
    assert app_res.sign_off_approved_by == checker_user.id
    assert app_res.sign_off_approved_by_name == "Checker Bob"
    assert app_res.sign_off_decision_note == "Countersigned and verified."
    assert app_res.sign_off_decided_at is not None


def test_append_only_sha256_hash_chaining(
    db_session: Session, sample_project_and_run
):
    """Test append-only SHA-256 hash chaining calculation and deterministic sequence."""
    project, run = sample_project_and_run

    # 1. First event uses GENESIS_HASH
    e1 = log_audit_event(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        event_type=AuditEventType.FILE_UPLOADED.value,
        event_payload={"filename": "ledger.csv", "rows": 1000},
    )
    assert e1.sequence_number == 1
    assert e1.previous_event_hash == GENESIS_HASH

    expected_h1 = compute_event_hash(
        previous_hash=GENESIS_HASH,
        timestamp_str=e1.timestamp_str,
        event_type=e1.event_type,
        canonical_payload=serialize_canonical_payload(e1.event_payload),
    )
    assert e1.current_event_hash == expected_h1

    # 2. Second event chains to e1.current_event_hash
    e2 = log_audit_event(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        event_type=AuditEventType.RUN_EXECUTED.value,
        event_payload={"gross_exposure": 1250.0},
    )
    assert e2.sequence_number == 2
    assert e2.previous_event_hash == e1.current_event_hash

    expected_h2 = compute_event_hash(
        previous_hash=e1.current_event_hash,
        timestamp_str=e2.timestamp_str,
        event_type=e2.event_type,
        canonical_payload=serialize_canonical_payload(e2.event_payload),
    )
    assert e2.current_event_hash == expected_h2

    # 3. Third event chains to e2.current_event_hash
    e3 = log_audit_event(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        event_type=AuditEventType.RUN_SIGN_OFF_APPROVED.value,
        event_payload={"approved": True},
    )
    assert e3.sequence_number == 3
    assert e3.previous_event_hash == e2.current_event_hash

    # Verify intact chain
    verification = verify_audit_chain(db=db_session, project_id=project.id, run_id=run.id)
    assert verification.status == "VALID"
    assert verification.is_valid is True
    assert verification.total_events == 3
    assert verification.head_hash == e3.current_event_hash
    assert verification.broken_link is None


def test_audit_chain_validator_detects_payload_tampering_and_broken_links(
    db_session: Session, sample_project_and_run
):
    """Test audit chain validator detects modified payload or broken hash linkage."""
    project, run = sample_project_and_run

    # Create 3 valid chained events
    e1 = log_audit_event(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        event_type=AuditEventType.RUN_EXECUTED.value,
        event_payload={"amount": 100},
    )
    e2 = log_audit_event(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        event_type=AuditEventType.RUN_SIGN_OFF_PROPOSED.value,
        event_payload={"amount": 100},
    )
    e3 = log_audit_event(
        db=db_session,
        project_id=project.id,
        run_id=run.id,
        event_type=AuditEventType.RUN_SIGN_OFF_APPROVED.value,
        event_payload={"amount": 100},
    )

    # Verify valid before tampering
    res_valid = verify_audit_chain(db=db_session, project_id=project.id, run_id=run.id)
    assert res_valid.is_valid is True

    # TAMPERING 1: Modify payload of event 2 without updating hash
    e2.event_payload = {"amount": 999999}  # tampered payload
    db_session.flush()

    res_tampered_payload = verify_audit_chain(db=db_session, project_id=project.id, run_id=run.id)
    assert res_tampered_payload.status == "TAMPERED"
    assert res_tampered_payload.is_valid is False
    assert res_tampered_payload.broken_link is not None
    assert res_tampered_payload.broken_link.sequence_number == 2
    assert "tampering detected" in res_tampered_payload.broken_link.reason.lower()

    # Revert payload tampering
    e2.event_payload = {"amount": 100}
    db_session.flush()

    # TAMPERING 2: Corrupt previous_event_hash linkage
    e3.previous_event_hash = "deadbeef" * 8
    db_session.flush()

    res_tampered_link = verify_audit_chain(db=db_session, project_id=project.id, run_id=run.id)
    assert res_tampered_link.status == "TAMPERED"
    assert res_tampered_link.is_valid is False
    assert res_tampered_link.broken_link is not None
    assert res_tampered_link.broken_link.sequence_number == 3
    assert "mismatch" in res_tampered_link.broken_link.reason.lower()


def test_api_governance_and_audit_endpoints(
    client: TestClient,
    db_session: Session,
    maker_user: User,
    checker_user: User,
    sample_project_and_run,
):
    """Test full HTTP endpoints for sign-off governance, audit retrieval, and verification."""
    project, run = sample_project_and_run

    maker_token = create_access_token({"sub": str(maker_user.id), "email": maker_user.email})
    checker_token = create_access_token({"sub": str(checker_user.id), "email": checker_user.email})

    maker_headers = {"Authorization": f"Bearer {maker_token}", "X-User-Role": "MAKER"}
    checker_headers = {"Authorization": f"Bearer {checker_token}", "X-User-Role": "CHECKER"}

    # 1. Propose sign-off via API
    resp_prop = client.post(
        f"/api/v1/projects/{project.id}/runs/{run.id}/sign-off/propose",
        json={"note": "Maker proposal note", "proposed_by_name": "Maker Alice"},
        headers=maker_headers,
    )
    assert resp_prop.status_code == 200, resp_prop.text
    prop_data = resp_prop.json()
    assert prop_data["sign_off_status"] == "AWAITING_SIGN_OFF"
    assert prop_data["sign_off_proposed_by_name"] == "Maker Alice"

    # 2. Maker self-approval via API is blocked (403 Forbidden)
    resp_self = client.post(
        f"/api/v1/projects/{project.id}/runs/{run.id}/sign-off/approve",
        json={"note": "Illegal self-approval"},
        headers=maker_headers,
    )
    assert resp_self.status_code == 403
    assert "Separation of Duties" in resp_self.json()["detail"] or "lacks authority" in resp_self.json()["detail"]

    # 3. Checker approves via API
    resp_app = client.post(
        f"/api/v1/projects/{project.id}/runs/{run.id}/sign-off/approve",
        json={"note": "Countersigned by Checker", "approved_by_name": "Checker Bob"},
        headers=checker_headers,
    )
    assert resp_app.status_code == 200, resp_app.text
    app_data = resp_app.json()
    assert app_data["sign_off_status"] == "APPROVED"
    assert app_data["sign_off_approved_by_name"] == "Checker Bob"

    # 4. Retrieve paginated audit trail
    resp_audit = client.get(
        f"/api/v1/projects/{project.id}/runs/{run.id}/audit-trail",
        headers=checker_headers,
    )
    assert resp_audit.status_code == 200
    trail_data = resp_audit.json()
    assert trail_data["total"] >= 2
    assert trail_data["is_chain_valid"] is True
    assert trail_data["head_hash"] is not None

    # 5. Live cryptographic verification endpoint returns VALID
    resp_verify = client.get(
        f"/api/v1/projects/{project.id}/runs/{run.id}/audit-trail/verify",
        headers=checker_headers,
    )
    assert resp_verify.status_code == 200
    verify_data = resp_verify.json()
    assert verify_data["status"] == "VALID"
    assert verify_data["is_valid"] is True
    assert verify_data["broken_link"] is None
