"""Append-only cryptographic audit trail service.

Integrates the deployed SHA-256 hash-chain implementation against the
``audit_events`` table already created by ``0004_enterprise_governance``.
Sequence allocation is serialized with a PostgreSQL transaction-scoped
advisory lock (and an in-process lock on other dialects) so concurrent
appends cannot reuse a sequence number. No schema change is made here.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from app.models.audit_log import AuditEvent
from app.schemas.audit import (
    AuditEventResponse,
    AuditTrailResponse,
    AuditVerificationBrokenLink,
    AuditVerificationResponse,
)

GENESIS_HASH = "0" * 64
_SEQUENCE_LOCK = threading.Lock()


def serialize_canonical_payload(payload: Any) -> str:
    """Produce deterministic, canonical JSON with sorted keys and no whitespace."""
    if payload is None:
        payload = {}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def compute_event_hash(
    previous_hash: str,
    timestamp_str: str,
    event_type: str,
    canonical_payload: str,
) -> str:
    """Hash the previous link, timestamp, event type, and canonical payload."""
    content = f"{previous_hash}{timestamp_str}{event_type}{canonical_payload}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _chain_lock_key(project_id: uuid.UUID, run_id: Optional[uuid.UUID]) -> int:
    raw = f"{project_id}:{run_id or 'project'}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big", signed=True)


def _acquire_chain_lock(
    db: Session,
    project_id: uuid.UUID,
    run_id: Optional[uuid.UUID],
) -> bool:
    """Serialize sequence allocation for one project/run chain.

    PostgreSQL uses a transaction-scoped advisory lock. Other dialects use the
    process lock only; they are acceptable for tests but not multi-process
    production use. Batch 26C should add a database constraint/index contract
    if stronger cross-process guarantees are required.

    Returns True when the in-process lock was acquired by this call.
    """
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _chain_lock_key(project_id, run_id)},
        )
        return False
    _SEQUENCE_LOCK.acquire()
    return True


def _release_chain_lock(acquired: bool) -> None:
    if acquired:
        _SEQUENCE_LOCK.release()


def _assert_project_access(
    db: Session,
    project_id: uuid.UUID,
    current_user: Any = None,
) -> None:
    """Defense in depth for service callers; routes also use verify_project_access."""
    if current_user is None:
        return
    from app.services.project_service import get_project_by_id

    if get_project_by_id(db, project_id, current_user=current_user) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )


def log_audit_event(
    db: Session,
    project_id: uuid.UUID,
    event_type: str,
    event_payload: Dict[str, Any],
    run_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    user_email: Optional[str] = None,
    user_role: str = "MAKER",
    timestamp_utc: Optional[datetime] = None,
) -> AuditEvent:
    """Append an immutable audit event with SHA-256 hash chaining.

    The caller owns the transaction. This function flushes so the new event is
    visible to subsequent work in the same transaction but does not commit.
    """
    if timestamp_utc is None:
        timestamp_utc = datetime.now(timezone.utc)
    elif timestamp_utc.tzinfo is None:
        timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
    else:
        timestamp_utc = timestamp_utc.astimezone(timezone.utc)

    timestamp_str = timestamp_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    lock_acquired = _acquire_chain_lock(db, project_id, run_id)
    try:
        query = select(AuditEvent)
        if run_id is not None:
            query = query.where(AuditEvent.run_id == run_id)
        else:
            query = query.where(
                and_(AuditEvent.project_id == project_id, AuditEvent.run_id.is_(None))
            )

        query = (
            query.order_by(
                AuditEvent.sequence_number.desc(),
                AuditEvent.timestamp_utc.desc(),
            )
            .limit(1)
            .with_for_update()
        )
        latest_event = db.execute(query).scalars().first()

        if latest_event is None:
            previous_hash = GENESIS_HASH
            sequence_number = 1
        else:
            previous_hash = latest_event.current_event_hash
            sequence_number = latest_event.sequence_number + 1

        canonical_payload = serialize_canonical_payload(event_payload)
        current_hash = compute_event_hash(
            previous_hash=previous_hash,
            timestamp_str=timestamp_str,
            event_type=event_type,
            canonical_payload=canonical_payload,
        )

        event = AuditEvent(
            event_id=f"evt_{uuid.uuid4().hex[:16]}",
            sequence_number=sequence_number,
            run_id=run_id,
            project_id=project_id,
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            event_type=event_type,
            timestamp_utc=timestamp_utc,
            timestamp_str=timestamp_str,
            event_payload=event_payload,
            previous_event_hash=previous_hash,
            current_event_hash=current_hash,
        )

        db.add(event)
        db.flush()
        return event
    finally:
        _release_chain_lock(lock_acquired)


def verify_audit_chain(
    db: Session,
    project_id: uuid.UUID,
    run_id: Optional[uuid.UUID] = None,
    current_user: Any = None,
) -> AuditVerificationResponse:
    """Recompute the chain from genesis and report any broken link or tampering."""
    _assert_project_access(db, project_id, current_user)

    query = select(AuditEvent)
    if run_id is not None:
        query = query.where(AuditEvent.run_id == run_id)
    else:
        query = query.where(
            and_(AuditEvent.project_id == project_id, AuditEvent.run_id.is_(None))
        )

    query = query.order_by(AuditEvent.sequence_number.asc(), AuditEvent.timestamp_utc.asc())
    events = list(db.execute(query).scalars().all())

    if not events:
        return AuditVerificationResponse(
            status="VALID",
            is_valid=True,
            total_events=0,
            head_hash=None,
            genesis_hash=GENESIS_HASH,
            broken_link=None,
            message="No audit events found; chain is trivially intact.",
        )

    expected_prev_hash = GENESIS_HASH

    for idx, event in enumerate(events):
        expected_seq = idx + 1

        if event.sequence_number != expected_seq:
            return AuditVerificationResponse(
                status="TAMPERED",
                is_valid=False,
                total_events=len(events),
                head_hash=events[-1].current_event_hash,
                genesis_hash=GENESIS_HASH,
                broken_link=AuditVerificationBrokenLink(
                    sequence_number=event.sequence_number,
                    event_id=event.event_id,
                    reason=(
                        f"Sequence out of order: expected #{expected_seq}, "
                        f"found #{event.sequence_number}"
                    ),
                    expected_hash=expected_prev_hash,
                    actual_hash=event.previous_event_hash,
                ),
                message=f"Sequence broken at event #{event.sequence_number}",
            )

        if event.previous_event_hash != expected_prev_hash:
            return AuditVerificationResponse(
                status="TAMPERED",
                is_valid=False,
                total_events=len(events),
                head_hash=events[-1].current_event_hash,
                genesis_hash=GENESIS_HASH,
                broken_link=AuditVerificationBrokenLink(
                    sequence_number=event.sequence_number,
                    event_id=event.event_id,
                    reason="Previous event hash mismatch (chain linkage broken)",
                    expected_hash=expected_prev_hash,
                    actual_hash=event.previous_event_hash,
                ),
                message=(
                    f"Broken cryptographic link at event #{event.sequence_number} "
                    f"({event.event_id})"
                ),
            )

        canonical_payload = serialize_canonical_payload(event.event_payload)
        recalculated_hash = compute_event_hash(
            previous_hash=event.previous_event_hash,
            timestamp_str=event.timestamp_str,
            event_type=event.event_type,
            canonical_payload=canonical_payload,
        )

        if event.current_event_hash != recalculated_hash:
            return AuditVerificationResponse(
                status="TAMPERED",
                is_valid=False,
                total_events=len(events),
                head_hash=events[-1].current_event_hash,
                genesis_hash=GENESIS_HASH,
                broken_link=AuditVerificationBrokenLink(
                    sequence_number=event.sequence_number,
                    event_id=event.event_id,
                    reason="Event payload or hash tampering detected",
                    expected_hash=recalculated_hash,
                    actual_hash=event.current_event_hash,
                ),
                message=(
                    f"Payload or signature tampering detected at event "
                    f"#{event.sequence_number} ({event.event_id})"
                ),
            )

        expected_prev_hash = event.current_event_hash

    return AuditVerificationResponse(
        status="VALID",
        is_valid=True,
        total_events=len(events),
        head_hash=events[-1].current_event_hash,
        genesis_hash=GENESIS_HASH,
        broken_link=None,
        message=(
            f"Cryptographic audit chain is unbroken and 100% verified across "
            f"{len(events)} events."
        ),
    )


def get_audit_trail(
    db: Session,
    project_id: uuid.UUID,
    run_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: Any = None,
) -> AuditTrailResponse:
    """Retrieve a paginated audit trail plus live chain-integrity status."""
    _assert_project_access(db, project_id, current_user)

    query = select(AuditEvent)
    if run_id is not None:
        query = query.where(AuditEvent.run_id == run_id)
    else:
        query = query.where(
            and_(AuditEvent.project_id == project_id, AuditEvent.run_id.is_(None))
        )

    all_events = list(
        db.execute(query.order_by(AuditEvent.sequence_number.asc())).scalars().all()
    )
    total = len(all_events)
    head_hash = all_events[-1].current_event_hash if all_events else None

    paged_events = all_events[skip : skip + limit]
    items = [AuditEventResponse.model_validate(e) for e in paged_events]
    verification = verify_audit_chain(
        db=db,
        project_id=project_id,
        run_id=run_id,
        current_user=None,
    )

    return AuditTrailResponse(
        total=total,
        items=items,
        is_chain_valid=verification.is_valid,
        head_hash=head_hash,
        genesis_hash=GENESIS_HASH,
    )
