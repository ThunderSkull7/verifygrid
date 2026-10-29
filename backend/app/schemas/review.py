"""Pydantic schemas for exception clustering, bulk review, and assignment."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.result import DiscrepancyItemResponse


class ExceptionCluster(BaseModel):
    """Grouped exception cluster sharing a deterministic root-cause signature."""

    cluster_id: str = Field(..., description="Deterministic cluster hash / identifier")
    cluster_name: str = Field(..., max_length=255, description="Human-readable cluster description")
    reason_code: str = Field(..., description="Primary reason code")
    rule_id: Optional[str] = Field(default=None, description="Failed rule identifier if applicable")
    failed_field_names: List[str] = Field(default_factory=list, description="Fields with mismatches")
    source_alias: Optional[str] = Field(default=None, description="Source dataset alias")
    discrepancy_category: str = Field(..., description="Classification category")
    severity: str = Field(default="medium", description="Cluster severity (high, medium, low, BLOCKING)")
    total_records: int = Field(..., description="Total count of discrepancies in cluster")
    total_exposure: float = Field(..., description="Sum of financial exposure in cluster")
    currency: str = Field(default="USD", description="Currency symbol/code")
    root_cause_explanation: str = Field(..., description="Summary explanation of common failure")
    status_counts: Dict[str, int] = Field(default_factory=dict, description="Counts by resolution status")
    sample_record: Optional[Dict[str, Any]] = Field(default=None, description="Representative record")
    discrepancy_ids: Optional[List[str]] = Field(default=None, description="Discrepancy IDs in this cluster")
    assigned_to: Optional[str] = Field(default=None, description="Current assignee if uniform")


class ClusterListResponse(BaseModel):
    """Response containing all exception clusters for a verification run."""

    total_clusters: int = Field(..., description="Count of distinct clusters")
    total_exceptions: int = Field(..., description="Total discrepancies grouped into clusters")
    total_cluster_exposure: float = Field(..., description="Aggregated exposure across clusters")
    clusters: List[ExceptionCluster] = Field(..., description="List of exception clusters")


class ClusterRecordsResponse(BaseModel):
    """Paginated records belonging to a specific cluster."""

    cluster_id: str
    cluster_name: str
    total: int
    items: List[DiscrepancyItemResponse]
    skip: int
    limit: int


class ReviewDecisionRequest(BaseModel):
    """Manual review decision on a single discrepancy."""

    decision: str = Field(
        ...,
        max_length=50,
        description="Review decision: APPROVE, REJECT, FORCE_MATCH, ESCALATE, or REOPEN",
        examples=["APPROVE"],
    )
    justification: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Mandatory auditor or reviewer justification note",
        examples=["Approved difference: within business grace period."],
    )
    # Retained for wire compatibility only. Reviewer identity is derived from
    # the authenticated principal and these values are ignored.
    reviewer_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Deprecated: ignored; authenticated reviewer identity is used.",
    )
    reviewer_email: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Deprecated: ignored; authenticated reviewer identity is used.",
    )


class ReviewDecisionItem(BaseModel):
    """Persisted audit decision entry for a discrepancy."""

    id: str
    discrepancy_id: str
    run_id: str
    decision: str
    justification: str
    reviewer_id: Optional[str] = None
    reviewer_email: Optional[str] = None
    previous_status: Optional[str] = None
    new_status: str
    is_bulk_action: bool = False
    cluster_id: Optional[str] = None
    created_at: datetime


class BulkReviewRequest(BaseModel):
    """Request to apply a review decision in bulk across a cluster or selected IDs."""

    decision: str = Field(
        ...,
        max_length=50,
        description="Bulk decision: APPROVE, REJECT, FORCE_MATCH, ESCALATE, or REOPEN",
    )
    justification: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Mandatory justification note explaining the bulk action",
    )
    cluster_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Target cluster ID to resolve all constituent records",
    )
    discrepancy_ids: Optional[List[str]] = Field(
        default=None,
        max_length=1000,
        description="Explicit list of discrepancy IDs to resolve",
    )
    max_exposure_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Maximum allowed exposure per record for bulk approval safeguard",
    )
    allow_blocking_override: bool = Field(
        default=False,
        description="Whether to permit override on hard BLOCKING rule failures",
    )


class BulkReviewResponse(BaseModel):
    """Report detailing partial or full success of bulk review action."""

    total_requested: int
    succeeded_count: int
    failed_count: int
    ineligible_count: int
    succeeded_ids: List[str]
    failed_records: List[Dict[str, Any]]
    message: str


class AssignmentRequest(BaseModel):
    """Assign records or a whole cluster to a reviewer.

    ``assigned_to`` is ``varchar(100)`` in the canonical schema, so both
    identifier fields are bounded to reject overlong values with 422 instead
    of surfacing a database ``DataError``.
    """

    reviewer_id: str = Field(..., min_length=1, max_length=100, description="Target reviewer user ID or email")
    reviewer_email: Optional[str] = Field(default=None, max_length=100, description="Reviewer email")
    cluster_id: Optional[str] = Field(default=None, max_length=64, description="Assign all records in cluster")
    discrepancy_ids: Optional[List[str]] = Field(
        default=None,
        max_length=1000,
        description="Assign specific discrepancy IDs",
    )


class AssignmentResponse(BaseModel):
    """Result of assignment operation."""

    assigned_count: int
    reviewer_id: str
    discrepancy_ids: List[str]
    message: str
