"""Exception Clustering, Deterministic Signatures, and Root-Cause Grouping Engine.

Computes deterministic exception signatures grouping repetitive root causes,
calculating aggregate cluster exposure, and providing human-readable explanations.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.verification_run import VerificationDiscrepancy, VerificationRun
from app.schemas.result import DiscrepancyItemResponse
from app.schemas.review import (
    ClusterListResponse,
    ClusterRecordsResponse,
    ExceptionCluster,
)
from app.services.project_service import get_project_by_id


def _authorize_project(db: Session, project_id: uuid.UUID, current_user: Optional[User]) -> None:
    """Fail closed when a caller supplies a principal without project ownership."""
    if current_user is not None and get_project_by_id(db, project_id, current_user=current_user) is None:
        raise ValueError(f"Project {project_id} not found")


def _normalize_token(val: Any) -> str:
    """Normalize a string token or Enum for signature hashing."""
    if not val:
        return ""
    if hasattr(val, "value"):
        val = val.value
    return str(val).strip().upper()


def compute_exception_signature(
    record: Any,
) -> Tuple[str, Optional[str], Tuple[str, ...], str, str]:
    """
    Computes a normalized 5-tuple signature for an exception:
    (reason_code, rule_id, failed_field_names, source_alias, discrepancy_category).
    Works on VerificationDiscrepancy, VerificationResultItem, or dict.
    """
    if isinstance(record, dict):
        ms_val = record.get("match_status") or "unmatched"
        match_status = str(ms_val.value if hasattr(ms_val, "value") else ms_val)
        cat_val = record.get("discrepancy_category") or "field_mismatch"
        discrepancy_category = str(cat_val.value if hasattr(cat_val, "value") else cat_val).lower()
        reason_code = record.get("reason_code") or record.get("_reason_code")
        side_by_side = record.get("side_by_side") or {}
        field_differences = record.get("field_differences") or []
        source_records = record.get("source_records") or {}
        missing_in_sources = record.get("missing_in_sources") or []
    else:
        ms_val = getattr(record, "match_status", "unmatched") or "unmatched"
        match_status = str(ms_val.value if hasattr(ms_val, "value") else ms_val)
        cat_val = getattr(record, "discrepancy_category", "field_mismatch") or "field_mismatch"
        discrepancy_category = str(cat_val.value if hasattr(cat_val, "value") else cat_val).lower()
        reason_code = getattr(record, "reason_code", None) or getattr(record, "_reason_code", None)
        side_by_side = getattr(record, "side_by_side", None) or {}
        field_differences = getattr(record, "field_differences", None) or []
        source_records = getattr(record, "source_records", None) or {}
        missing_in_sources = getattr(record, "missing_in_sources", None) or []

    # 1. Resolve Reason Code
    if not reason_code and side_by_side.get("failed_rules"):
        fr = side_by_side["failed_rules"][0]
        reason_code = fr.get("reason_code")
    if not reason_code and field_differences:
        for fd in field_differences:
            rc = fd.get("reason_code") if isinstance(fd, dict) else getattr(fd, "reason_code", None)
            if rc:
                reason_code = rc
                break
    if not reason_code:
        status_to_reason = {
            "identical": "EXACT_MATCH",
            "field_mismatch": "FIELD_MISMATCH",
            "missing_in_target": "MISSING_IN_TARGET",
            "missing_in_source": "MISSING_IN_SOURCE",
            "duplicate_key_source": "DUPLICATE_KEY_SOURCE",
            "duplicate_key_target": "DUPLICATE_KEY_TARGET",
            "duplicate_key_both": "DUPLICATE_KEY_BOTH",
            "ambiguous_duplicate": "AMBIGUOUS_DUPLICATE",
            "needs_review": "FUZZY_NAME_REVIEW",
            "partial_payment": "PARTIAL_PAYMENT",
            "overpayment": "OVERPAYMENT",
            "unmatched_split_record": "UNMATCHED_SPLIT_RECORD",
            "duplicate_receipt": "DUPLICATE_RECEIPT",
        }
        reason_code = status_to_reason.get(match_status, "FIELD_MISMATCH")

    norm_reason_code = _normalize_token(reason_code) or "FIELD_MISMATCH"

    # 2. Resolve Rule ID
    rule_id: Optional[str] = None
    if side_by_side.get("failed_rules"):
        rule_id = side_by_side["failed_rules"][0].get("rule_id")
    if not rule_id and field_differences:
        for fd in field_differences:
            rid = fd.get("rule_id") if isinstance(fd, dict) else getattr(fd, "rule_id", None)
            if rid:
                rule_id = str(rid)
                break

    # 3. Resolve Failed Field Names
    failed_fields: Set[str] = set()
    if side_by_side.get("field_comparisons"):
        for fc in side_by_side["field_comparisons"]:
            if isinstance(fc, dict) and not fc.get("is_match", True):
                fn = fc.get("field_name")
                if fn:
                    failed_fields.add(str(fn).strip().lower())
    if not failed_fields and field_differences:
        for fd in field_differences:
            fn = fd.get("field_name") if isinstance(fd, dict) else getattr(fd, "field_name", None)
            if fn:
                failed_fields.add(str(fn).strip().lower())
                if fn:
                    failed_fields.add(str(fn).strip().lower())

    if not failed_fields:
        if "missing" in match_status or "missing" in discrepancy_category:
            failed_fields.add("record_presence")
        elif "duplicate" in match_status or "duplicate" in discrepancy_category:
            failed_fields.add("primary_key")
        elif "split" in match_status or "payment" in match_status:
            failed_fields.add("installment_amount")
        else:
            failed_fields.add("general_record")

    sorted_fields = tuple(sorted(failed_fields))

    # 4. Resolve Source Alias
    source_alias = "primary"
    if side_by_side.get("failed_rules"):
        fr = side_by_side["failed_rules"][0]
        sa = fr.get("source_alias") or fr.get("target_alias")
        if sa:
            source_alias = str(sa).strip().lower()
    elif missing_in_sources:
        source_alias = str(missing_in_sources[0]).strip().lower()
    elif source_records:
        first_alias = next(iter(source_records.keys()), "source")
        source_alias = str(first_alias).strip().lower()

    return (
        norm_reason_code,
        rule_id,
        sorted_fields,
        source_alias,
        discrepancy_category,
    )


def generate_cluster_id(
    signature: Tuple[str, Optional[str], Tuple[str, ...], str, str],
) -> str:
    """Generate a stable 16-hex deterministic cluster hash."""
    reason_code, rule_id, failed_fields, source_alias, category = signature
    sig_raw = (
        f"{reason_code}::"
        f"{rule_id or ''}::"
        f"{','.join(failed_fields)}::"
        f"{source_alias}::"
        f"{category}"
    )
    h = hashlib.sha256(sig_raw.encode("utf-8")).hexdigest()[:16]
    return f"c_{h}"


def generate_cluster_name(
    signature: Tuple[str, Optional[str], Tuple[str, ...], str, str],
    sample_record: Any = None,
) -> str:
    """Produces human-readable cluster name based on root cause semantics."""
    reason_code, rule_id, failed_fields, source_alias, category = signature
    fields_label = ", ".join(f.replace("_", " ").title() for f in failed_fields)
    alias_label = source_alias.upper() if source_alias not in ("primary", "source") else ""

    # Check if sample record has a specific rule description or message
    rule_desc = None
    if sample_record:
        sbs = getattr(sample_record, "side_by_side", None) or (
            sample_record.get("side_by_side") if isinstance(sample_record, dict) else None
        )
        if sbs and sbs.get("failed_rules"):
            rule_desc = sbs["failed_rules"][0].get("description")

    if rule_desc and len(rule_desc) < 60:
        return rule_desc

    rc_upper = reason_code.upper()

    if "WHITESPACE" in rc_upper:
        return f"Trailing Whitespace Mismatch in {fields_label}"
    if "DATE" in rc_upper or "LAG" in rc_upper:
        if alias_label:
            return f"Date Lag Exceeded (>3 Days) on {alias_label} Settlement"
        return f"Date Lag / Settlement Window Exceeded in {fields_label}"
    if "TOLERANCE" in rc_upper or "NUMERIC" in rc_upper:
        return f"Numeric Tolerance Exceeded in {fields_label}"
    if "STATUS" in rc_upper or "TRANSITION" in rc_upper:
        return f"Disallowed Status Transition in {fields_label}"
    if "MISSING_IN_TARGET" in rc_upper:
        if alias_label:
            return f"Missing Records in Target Source ({alias_label})"
        return "Unmatched Records Missing in Target Source"
    if "MISSING_IN_SOURCE" in rc_upper:
        if alias_label:
            return f"Unmatched Records in Source ({alias_label})"
        return "Records Missing in Primary Dataset"
    if "PARTIAL_PAYMENT" in rc_upper or "UNMATCHED_SPLIT" in rc_upper:
        return f"Split Payment Variance / Installment Mismatch ({fields_label})"
    if "OVERPAYMENT" in rc_upper:
        return f"Overpayment Variance on Split Installment"
    if "DUPLICATE" in rc_upper:
        return f"Duplicate Key Collision on {fields_label}"
    if "TAX" in fields_label.upper():
        if alias_label:
            return f"Missing Tax Code in {alias_label} Source"
        return f"Tax Code Discrepancy in {fields_label}"

    if alias_label:
        return f"Field Discrepancy in {fields_label} ({alias_label})"
    return f"{fields_label} Mismatch ({category.replace('_', ' ').title()})"


def generate_root_cause_explanation(
    signature: Tuple[str, Optional[str], Tuple[str, ...], str, str],
    total_records: int,
    total_exposure: float,
    currency: str = "USD",
    sample_record: Any = None,
) -> str:
    """Generates an intuitive root cause diagnosis for the cluster."""
    reason_code, rule_id, failed_fields, source_alias, category = signature
    fields_str = ", ".join(failed_fields)

    rec_label = "record" if total_records == 1 else "records"
    curr_sym = "€" if currency == "EUR" else "$"

    if "WHITESPACE" in reason_code:
        return (
            f"{total_records} {rec_label} failed verification due to leading or trailing whitespace differences "
            f"in field(s): {fields_str}. Total cluster financial exposure: {curr_sym}{total_exposure:,.2f}."
        )
    if "DATE" in reason_code:
        return (
            f"{total_records} {rec_label} exceeded configured settlement date lag thresholds "
            f"across {source_alias}. Total cluster financial exposure: {curr_sym}{total_exposure:,.2f}."
        )
    if "MISSING" in reason_code:
        return (
            f"{total_records} {rec_label} present in source but missing in {source_alias}. "
            f"Total unverified exposure: {curr_sym}{total_exposure:,.2f}."
        )
    if "PARTIAL_PAYMENT" in reason_code or "OVERPAYMENT" in reason_code:
        return (
            f"{total_records} parent records have installment sums that do not equal the expected total. "
            f"Total cluster variance: {curr_sym}{total_exposure:,.2f}."
        )

    return (
        f"{total_records} {rec_label} flagged with {reason_code} ({category}) across field(s) '{fields_str}'. "
        f"Cumulative exposure is {curr_sym}{total_exposure:,.2f}."
    )


def cluster_discrepancies_in_memory(
    records: List[Any],
    run_id: Optional[uuid.UUID] = None,
) -> List[ExceptionCluster]:
    """
    Groups a list of VerificationDiscrepancy or VerificationResultItem instances
    into deterministic ExceptionCluster objects with aggregated exposure.
    """
    clusters_map: Dict[str, Dict[str, Any]] = {}

    for rec in records:
        sig = compute_exception_signature(rec)
        cid = generate_cluster_id(sig)

        # Get monetary amount
        if isinstance(rec, dict):
            exposure = float(rec.get("exposure_amount") or 0.0)
            res_status = rec.get("resolution_status") or "unresolved"
            rec_id = str(rec.get("id") or "")
            currency = rec.get("currency") or "USD"
            assigned = rec.get("assigned_to")
            severity = rec.get("severity") or "medium"
        else:
            exposure = float(getattr(rec, "exposure_amount", 0.0) or 0.0)
            res_status = getattr(rec, "resolution_status", "unresolved") or "unresolved"
            rec_id = str(getattr(rec, "id", ""))
            currency = getattr(rec, "currency", "USD") or "USD"
            assigned = getattr(rec, "assigned_to", None)
            severity = getattr(rec, "severity", "medium") or "medium"

        if cid not in clusters_map:
            # cluster_name is varchar(255) in the canonical schema.
            cname = generate_cluster_name(sig, rec)[:255]
            clusters_map[cid] = {
                "signature": sig,
                "cluster_id": cid,
                "cluster_name": cname,
                "reason_code": sig[0],
                "rule_id": sig[1],
                "failed_field_names": list(sig[2]),
                "source_alias": sig[3],
                "discrepancy_category": sig[4],
                "severity": severity,
                "total_records": 0,
                "total_exposure": 0.0,
                "currency": currency,
                "status_counts": {},
                "sample_record": rec if isinstance(rec, dict) else None,
                "discrepancy_ids": [],
                "assignees": set(),
            }

        cdata = clusters_map[cid]
        cdata["total_records"] += 1
        cdata["total_exposure"] += exposure
        cdata["discrepancy_ids"].append(rec_id)
        cdata["status_counts"][res_status] = cdata["status_counts"].get(res_status, 0) + 1
        if assigned:
            cdata["assignees"].add(assigned)

        # Elevate severity if any record has higher severity
        if severity.lower() in ("high", "blocking"):
            cdata["severity"] = severity

    # Finalize cluster objects
    clusters: List[ExceptionCluster] = []
    for cid, cdata in clusters_map.items():
        sig = cdata["signature"]
        tot_exp = round(cdata["total_exposure"], 2)
        explanation = generate_root_cause_explanation(
            sig,
            cdata["total_records"],
            tot_exp,
            cdata["currency"],
            cdata["sample_record"],
        )
        assigned_to = None
        if len(cdata["assignees"]) == 1:
            assigned_to = next(iter(cdata["assignees"]))

        clusters.append(
            ExceptionCluster(
                cluster_id=cid,
                cluster_name=cdata["cluster_name"],
                reason_code=cdata["reason_code"],
                rule_id=cdata["rule_id"],
                failed_field_names=cdata["failed_field_names"],
                source_alias=cdata["source_alias"],
                discrepancy_category=cdata["discrepancy_category"],
                severity=cdata["severity"],
                total_records=cdata["total_records"],
                total_exposure=tot_exp,
                currency=cdata["currency"],
                root_cause_explanation=explanation,
                status_counts=cdata["status_counts"],
                sample_record=cdata["sample_record"],
                discrepancy_ids=cdata["discrepancy_ids"],
                assigned_to=assigned_to,
            )
        )

    # Sort clusters by exposure descending
    clusters.sort(key=lambda c: c.total_exposure, reverse=True)
    return clusters


def get_run_clusters(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    current_user: Optional[User] = None,
) -> ClusterListResponse:
    """
    Fetches and returns all exception clusters for a persistent verification run.
    Also syncs cluster_id and cluster_name back to VerificationDiscrepancy rows
    for optimized index lookups.
    """
    _authorize_project(db, project_id, current_user)

    # Verify run exists and belongs to project
    run = (
        db.query(VerificationRun)
        .filter(
            VerificationRun.id == run_id,
            VerificationRun.project_id == project_id,
        )
        .first()
    )
    if not run:
        raise ValueError(f"Verification run {run_id} not found in project {project_id}")

    discrepancies: List[VerificationDiscrepancy] = (
        db.query(VerificationDiscrepancy)
        .filter(VerificationDiscrepancy.run_id == run_id)
        .all()
    )

    if not discrepancies:
        return ClusterListResponse(
            total_clusters=0,
            total_exceptions=0,
            total_cluster_exposure=0.0,
            clusters=[],
        )

    # Compute clusters
    clusters = cluster_discrepancies_in_memory(discrepancies, run_id=run_id)

    # Populate cluster_id and cluster_name on discrepancy entities if missing
    dirty = False
    disc_by_id = {str(d.id): d for d in discrepancies}
    for cluster in clusters:
        if cluster.discrepancy_ids:
            for d_id in cluster.discrepancy_ids:
                disc = disc_by_id.get(d_id)
                if disc:
                    if disc.cluster_id != cluster.cluster_id or disc.cluster_name != cluster.cluster_name:
                        disc.cluster_id = cluster.cluster_id
                        disc.cluster_name = cluster.cluster_name
                        dirty = True

    if dirty:
        db.commit()

    total_exposure = round(sum(c.total_exposure for c in clusters), 2)
    return ClusterListResponse(
        total_clusters=len(clusters),
        total_exceptions=len(discrepancies),
        total_cluster_exposure=total_exposure,
        clusters=clusters,
    )


def get_cluster_records(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    cluster_id: str,
    skip: int = 0,
    limit: int = 50,
    resolution_status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    current_user: Optional[User] = None,
) -> ClusterRecordsResponse:
    """
    Returns paginated discrepancy items belonging to a specific cluster.
    """
    _authorize_project(db, project_id, current_user)

    # Ensure run belongs to project
    run = (
        db.query(VerificationRun)
        .filter(
            VerificationRun.id == run_id,
            VerificationRun.project_id == project_id,
        )
        .first()
    )
    if not run:
        raise ValueError(f"Verification run {run_id} not found in project {project_id}")

    query = db.query(VerificationDiscrepancy).filter(
        VerificationDiscrepancy.run_id == run_id,
    )

    # Check if cluster_id is populated on rows or need fallback match
    query_with_cid = query.filter(VerificationDiscrepancy.cluster_id == cluster_id)
    total = query_with_cid.count()

    if total == 0:
        # Run cluster sync first
        get_run_clusters(db, project_id, run_id)
        query_with_cid = query.filter(VerificationDiscrepancy.cluster_id == cluster_id)
        total = query_with_cid.count()

    filtered_query = query_with_cid
    if resolution_status:
        filtered_query = filtered_query.filter(
            VerificationDiscrepancy.resolution_status == resolution_status
        )
    if assigned_to:
        if assigned_to.upper() == "UNASSIGNED":
            filtered_query = filtered_query.filter(
                VerificationDiscrepancy.assigned_to.is_(None)
            )
        else:
            filtered_query = filtered_query.filter(
                VerificationDiscrepancy.assigned_to == assigned_to
            )

    cluster_name = f"Cluster {cluster_id}"
    first_record = filtered_query.first()
    if first_record and first_record.cluster_name:
        cluster_name = first_record.cluster_name

    total_filtered = filtered_query.count()
    items = (
        filtered_query.order_by(VerificationDiscrepancy.exposure_amount.desc().nullslast())
        .offset(skip)
        .limit(limit)
        .all()
    )

    response_items = [
        DiscrepancyItemResponse.model_validate(disc) for disc in items
    ]

    return ClusterRecordsResponse(
        cluster_id=cluster_id,
        cluster_name=cluster_name,
        total=total_filtered,
        items=response_items,
        skip=skip,
        limit=limit,
    )
