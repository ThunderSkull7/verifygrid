from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.models.audit_log import AuditEvent
from app.schemas.audit import (
    AuditEventResponse,
    AuditTrailResponse,
    AuditVerificationBrokenLink,
    AuditVerificationResponse,
)

GENESIS_HASH = "0" * 64


def serialize_canonical_payload(payload: Any) -> str:
    """
    Produce a deterministic, canonical JSON string representation
    with sorted keys and compact separators without whitespace.
    """
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
    """
    Compute current SHA-256 hash chaining previous hash, timestamp, event type, and payload.
    """
    content = f"{previous_hash}{timestamp_str}{event_type}{canonical_payload}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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
    """
    Append an immutable cryptographic audit event with SHA-256 hash chaining.
    """
    if timestamp_utc is None:
        timestamp_utc = datetime.now(timezone.utc)
    elif timestamp_utc.tzinfo is None:
        timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
    else:
        timestamp_utc = timestamp_utc.astimezone(timezone.utc)

    timestamp_str = timestamp_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # Find the most recent event in this chain
    query = select(AuditEvent)
    if run_id is not None:
        query = query.where(AuditEvent.run_id == run_id)
    else:
        query = query.where(and_(AuditEvent.project_id == project_id, AuditEvent.run_id.is_(None)))

    query = query.order_by(AuditEvent.sequence_number.desc(), AuditEvent.timestamp_utc.desc())
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

    event_id = f"evt_{uuid.uuid4().hex[:16]}"

    event = AuditEvent(
        event_id=event_id,
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


def verify_audit_chain(
    db: Session,
    project_id: uuid.UUID,
    run_id: Optional[uuid.UUID] = None,
) -> AuditVerificationResponse:
    """
    Traverse the audit sequence from genesis to head, re-compute SHA-256 hashes,
    and detect any broken links, payload tampering, or out-of-order mutations.
    """
    query = select(AuditEvent)
    if run_id is not None:
        query = query.where(AuditEvent.run_id == run_id)
    else:
        query = query.where(and_(AuditEvent.project_id == project_id, AuditEvent.run_id.is_(None)))

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

        # 1. Sequence number validation
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
                    reason=f"Sequence out of order: expected #{expected_seq}, found #{event.sequence_number}",
                    expected_hash=expected_prev_hash,
                    actual_hash=event.previous_event_hash,
                ),
                message=f"Sequence broken at event #{event.sequence_number}",
            )

        # 2. Previous hash linkage validation
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
                message=f"Broken cryptographic link at event #{event.sequence_number} ({event.event_id})",
            )

        # 3. Payload integrity and current hash verification
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
                message=f"Payload or signature tampering detected at event #{event.sequence_number} ({event.event_id})",
            )

        expected_prev_hash = event.current_event_hash

    return AuditVerificationResponse(
        status="VALID",
        is_valid=True,
        total_events=len(events),
        head_hash=events[-1].current_event_hash,
        genesis_hash=GENESIS_HASH,
        broken_link=None,
        message=f"Cryptographic audit chain is unbroken and 100% verified across {len(events)} events.",
    )


def get_audit_trail(
    db: Session,
    project_id: uuid.UUID,
    run_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 100,
) -> AuditTrailResponse:
    """
    Retrieve paginated audit events for a verification run or project.
    """
    query = select(AuditEvent)
    if run_id is not None:
        query = query.where(AuditEvent.run_id == run_id)
    else:
        query = query.where(and_(AuditEvent.project_id == project_id, AuditEvent.run_id.is_(None)))

    # Fetch total count
    all_events = list(db.execute(query.order_by(AuditEvent.sequence_number.asc())).scalars().all())
    total = len(all_events)

    head_hash = all_events[-1].current_event_hash if all_events else None

    # Apply pagination for items
    paged_events = all_events[skip : skip + limit]

    items = [AuditEventResponse.model_validate(e) for e in paged_events]

    # Check chain integrity
    verification = verify_audit_chain(db=db, project_id=project_id, run_id=run_id)

    return AuditTrailResponse(
        total=total,
        items=items,
        is_chain_valid=verification.is_valid,
        head_hash=head_hash,
        genesis_hash=GENESIS_HASH,
    )
