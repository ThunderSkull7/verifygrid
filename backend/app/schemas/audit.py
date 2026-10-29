"""Pydantic schemas for the append-only audit trail."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuditEventType(str, Enum):
    FILE_UPLOADED = "FILE_UPLOADED"
    PREFLIGHT_QUARANTINE_ACTION = "PREFLIGHT_QUARANTINE_ACTION"
    RUN_EXECUTED = "RUN_EXECUTED"
    RULE_MODIFIED = "RULE_MODIFIED"
    EXCEPTION_REVIEW_PROPOSED = "EXCEPTION_REVIEW_PROPOSED"
    CHECKER_COUNTERSIGNED = "CHECKER_COUNTERSIGNED"
    RUN_SIGN_OFF_PROPOSED = "RUN_SIGN_OFF_PROPOSED"
    RUN_SIGN_OFF_APPROVED = "RUN_SIGN_OFF_APPROVED"
    RUN_SIGN_OFF_REJECTED = "RUN_SIGN_OFF_REJECTED"
    EXPORT_GENERATED = "EXPORT_GENERATED"


class AuditEventResponse(BaseModel):
    """Single immutable audit event with hash-chain linkage."""

    id: uuid.UUID
    event_id: str
    sequence_number: int
    run_id: Optional[uuid.UUID] = None
    project_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    user_email: Optional[str] = None
    user_role: str
    event_type: str
    timestamp_utc: datetime
    timestamp_str: str
    event_payload: Dict[str, Any]
    previous_event_hash: str
    current_event_hash: str

    model_config = ConfigDict(from_attributes=True)


class AuditTrailResponse(BaseModel):
    """Paginated list of cryptographic audit events for a verification run."""

    total: int
    items: List[AuditEventResponse]
    is_chain_valid: bool = True
    head_hash: Optional[str] = None
    genesis_hash: str = "0" * 64


class AuditVerificationBrokenLink(BaseModel):
    """Diagnostic details for a broken or tampered audit event link."""

    sequence_number: int
    event_id: str
    reason: str
    expected_hash: str
    actual_hash: str


class AuditVerificationResponse(BaseModel):
    """Cryptographic chain verification outcome."""

    status: str = Field(description="VALID or TAMPERED")
    is_valid: bool
    total_events: int
    head_hash: Optional[str] = None
    genesis_hash: str = "0" * 64
    broken_link: Optional[AuditVerificationBrokenLink] = None
    message: str
