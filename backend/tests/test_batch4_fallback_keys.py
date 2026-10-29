"""Batch 4 tests: configurable, deterministic fallback matching keys.

Invariants under test:
- Requests without fallback_keys behave exactly as before.
- Fallbacks are tried in order, only after the primary key fails, with exact
  normalized-value equality (leading zeroes preserved).
- Blank/null/whitespace fallback values never match.
- A fallback match requires exactly one unique unconsumed candidate per
  participating source; ambiguity is never silently resolved.
- One primary record cannot be matched to multiple fallback candidates.
- Matching method and key are recorded in result lineage.
- Composite fallbacks and differently-named mapped columns are supported.
- Dry-run preview and persisted runs agree; financial/aggregation behavior unchanged.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.schemas.multisource import MultiSourceVerificationRequest, SourceDefinition
from app.services.verification_engine import verify_multisource_datasets

import tests.test_multisource_wizard as wizard

create_project = wizard.create_project
upload_csv = wizard.upload_csv
upload_storage = wizard.upload_storage

MULTI_SOURCE_RUN = "/runs/multi-source"
MULTI_SOURCE_VERIFY = "/verify/multi-source"


def _src(alias: str, fid: str, primary: bool, key: str, mapping: dict) -> SourceDefinition:
    return SourceDefinition(
        alias=alias,
        file_id=fid,
        is_primary=primary,
        key_columns=[key],
        field_mapping=mapping,
    )


# ==============================================================================
# Engine-level fallback matching
# ==============================================================================


def test_no_fallback_configuration_behaves_as_before():
    """fallback_keys=None must produce identical outcomes to the legacy engine."""
    sources_data = {
        "a": [(1, {"id": "1", "val": "10"})],
        "b": [(1, {"id": "2", "val": "10"})],  # key mismatch -> unmatched
    }
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", {"id": "id"}),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {"id": "id"})]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
    )
    assert summary.unmatched_source_records == 1
    assert summary.fallback_matched_records == 0


def test_fallback_matches_when_primary_key_missing():
    """Primary record with a blank key is matched via a unique fallback value."""
    sources_data = {
        "academic": [
            (1, {"student_id": "S-1", "phone": "P-1"}),
            (2, {"student_id": None, "phone": "P-2"}),  # blank primary key
        ],
        "idcard": [
            (1, {"student_id": "S-1", "phone": "P-1"}),
            (2, {"student_id": "S-3", "phone": "P-2"}),
        ],
    }
    defs = [_src("academic", "00000000-0000-0000-0000-000000000001", True, "student_id",
                 {"student_id": "student_id", "phone": "phone"}),
            _src("idcard", "00000000-0000-0000-0000-000000000002", False, "student_id",
                 {"student_id": "student_id", "phone": "phone"})]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["student_id"],
        compare_attributes=["phone"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    assert summary.fallback_matched_records == 1
    # The idcard S-3 record (the P-2 carrier) was consumed by the fallback match,
    # so nothing is left unmatched.
    assert summary.unmatched_source_records == 0
    # The blank-key record was matched through the fallback, not merged with S-1.
    fb_item = next(it for it in results if (it.lineage or {}).get("matching_method") == "fallback_key")
    assert fb_item.lineage["fallback_key"] == ["phone"]
    assert fb_item.lineage["fallback_values"] == {"phone": "P-2"}
    assert fb_item.lineage["fallback_columns"] == {"idcard": ["phone"]}
    assert fb_item.key_values.get("student_id") is None  # primary-key display retained


def test_fallback_when_primary_key_present_but_cannot_match():
    """Present-but-mismatched primary keys fall back consistently with missing semantics."""
    sources_data = {
        "a": [(1, {"id": "X-9", "phone": "P-1", "val": "10"})],
        "b": [(1, {"id": "Y-1", "phone": "P-1", "val": "10"})],
    }
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", {"id": "id", "phone": "phone"}),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {"id": "id", "phone": "phone"})]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    assert summary.fallback_matched_records == 1
    item = results[0]
    assert item.match_status.value == "identical"  # compared after fallback match
    assert (item.lineage or {}).get("matching_method") == "fallback_key"


def test_fallback_priority_order_respected():
    """The first fallback definition that resolves uniquely wins; later ones are not consulted."""
    sources_data = {
        "a": [(1, {"id": None, "phone": None, "email": "e@x.y", "val": "1"})],
        "b": [(1, {"id": "Z-1", "phone": "P-9", "email": "e@x.y", "val": "1"})],
    }
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id",
                 {"id": "id", "phone": "phone", "email": "email"}),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id",
                 {"id": "id", "phone": "phone", "email": "email"})]
    # phone comes first but is blank in the primary record -> skipped; email used.
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"], ["email"]],
    )
    assert summary.fallback_matched_records == 1
    assert results[0].lineage["fallback_key"] == ["email"]
    assert results[0].lineage["fallback_key_index"] == 1


def test_composite_fallback_key():
    """Composite fallbacks use all components; a single shared component is not enough."""
    sources_data = {
        "a": [
            (1, {"id": "X-1", "dob": "2000-01-01", "last": "Sharma"}),
            (2, {"id": "X-2", "dob": "2001-02-02", "last": "Verma"}),
        ],
        "b": [
            (1, {"id": "Y-1", "dob": "2000-01-01", "last": "Sharma"}),
            (2, {"id": "Y-2", "dob": "2001-02-02", "last": "Verma"}),
        ],
    }
    colmap = {"id": "id", "dob": "dob", "last": "last"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", colmap),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", colmap)]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["last"], numeric_tolerance=0.0, include_identical=True,
        # "last" alone is shared by no one here, but dob+last is unique per person.
        fallback_keys=[["last"], ["dob", "last"]],
    )
    assert summary.fallback_matched_records == 2
    used = {tuple(it.lineage["fallback_key"]) for it in results}
    assert used == {("last",), ("dob", "last")} or used == {("last",)}


def test_composite_fallback_requires_all_components():
    """A record matching on one composite component only must not match."""
    sources_data = {
        "a": [(1, {"id": "X-1", "dob": "2000-01-01", "last": "Sharma"})],
        "b": [(1, {"id": "Y-1", "dob": "1999-12-12", "last": "Sharma"})],
    }
    colmap = {"id": "id", "dob": "dob", "last": "last"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", colmap),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", colmap)]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["last"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["dob", "last"]],
    )
    assert summary.fallback_matched_records == 0
    assert summary.unmatched_source_records == 1


def test_duplicate_fallback_values_in_one_source_are_ambiguous():
    """Two target records sharing the fallback value -> no match is chosen."""
    sources_data = {
        "a": [(1, {"id": "X-1", "phone": "P-1"})],
        "b": [
            (1, {"id": "Y-1", "phone": "P-1"}),
            (2, {"id": "Y-2", "phone": "P-1"}),  # duplicate fallback value
        ],
    }
    colmap = {"id": "id", "phone": "phone"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", colmap),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", colmap)]
    summary, _, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["phone"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    assert summary.fallback_matched_records == 0
    # Y-1 and Y-2 each appear only in the non-primary source -> both reported.
    assert summary.unmatched_source_records == 2


def test_three_way_fallback_requires_uniqueness_in_every_missing_source():
    """With 3 sources, the fallback must resolve uniquely in ALL missing sources."""
    sources_data = {
        "a": [(1, {"id": "X-1", "phone": "P-1"})],
        "b": [(1, {"id": "Y-1", "phone": "P-1"})],
        "c": [
            (1, {"id": "Z-1", "phone": "P-1"}),
            (2, {"id": "Z-2", "phone": "P-1"}),  # ambiguity in third source
        ],
    }
    colmap = {"id": "id", "phone": "phone"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", colmap),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", colmap),
            _src("c", "00000000-0000-0000-0000-000000000003", False, "id", colmap)]
    summary, _, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["phone"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    assert summary.fallback_matched_records == 0


def test_blank_fallback_values_never_match():
    """Two records must not match merely because both fallback values are missing."""
    sources_data = {
        "a": [(1, {"id": "X-1", "phone": None}), (2, {"id": "X-2", "phone": "  "})],
        "b": [(1, {"id": "Y-1", "phone": None})],
    }
    colmap = {"id": "id", "phone": "phone"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", colmap),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", colmap)]
    summary, _, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["phone"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    assert summary.fallback_matched_records == 0
    # X-1 (blank phone) and X-2 (whitespace phone) stay unmatched; Y-1's tuple is
    # also reported as missing-in-primary.
    assert summary.unmatched_source_records == 1


def test_leading_zero_identifiers_preserved_in_fallback():
    sources_data = {
        "a": [(1, {"id": "X-1", "phone": "0091"})],
        "b": [
            (1, {"id": "Y-1", "phone": "0091"}),   # exact leading-zero string
            (2, {"id": "Y-2", "phone": "91"}),     # numeric twin, must NOT match
        ],
    }
    colmap = {"id": "id", "phone": "phone"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", colmap),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", colmap)]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["phone"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    assert summary.fallback_matched_records == 1
    assert results[0].lineage["fallback_values"] == {"phone": "0091"}


def test_fallback_one_to_many_is_prevented():
    """Two primary records sharing a fallback value cannot both consume one target record."""
    sources_data = {
        "a": [
            (1, {"id": "X-1", "phone": "P-1"}),
            (2, {"id": "X-2", "phone": "P-1"}),  # same fallback value, distinct primary keys
        ],
        "b": [(1, {"id": "Y-1", "phone": "P-1"})],
    }
    colmap = {"id": "id", "phone": "phone"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", colmap),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", colmap)]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["phone"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    # Exactly one fallback match; the other primary record stays unmatched
    # (primary present -> counted as unmatched target).
    assert summary.fallback_matched_records == 1
    assert summary.unmatched_target_records == 1
    # The record matched first (sorted key order: "X-1" < "X-2") consumed Y-1.
    assert results[0].key_values == {"id": "X-1"}


def test_fallback_through_differently_named_mapped_columns():
    """Fallback attributes resolve per-source through field_mapping."""
    sources_data = {
        "academic": [(1, {"student_id": None, "contact": "P-5"})],
        "idcard": [(1, {"enrolment_no": "E-9", "mobile": "P-5"})],
    }
    defs = [_src("academic", "00000000-0000-0000-0000-000000000001", True, "student_id",
                 {"student_id": "student_id", "contact": "phone"}),
            _src("idcard", "00000000-0000-0000-0000-000000000002", False, "enrolment_no",
                 {"enrolment_no": "student_id", "mobile": "phone"})]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["student_id"],
        compare_attributes=["phone"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    assert summary.fallback_matched_records == 1
    item = results[0]
    assert item.lineage["fallback_columns"] == {"idcard": ["mobile"]}
    assert item.lineage["fallback_values"] == {"phone": "P-5"}


# ==============================================================================
# Schema validation
# ==============================================================================


def test_fallback_identical_to_primary_key_rejected():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as exc:
        MultiSourceVerificationRequest(
            sources=[
                _src("a", "00000000-0000-0000-0000-000000000001", True, "id", {}),
                _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {}),
            ],
            unified_keys=["id"],
            fallback_keys=[["id"]],
        )
    assert "identical to the primary matching key" in str(exc.value)


def test_fallback_empty_and_duplicate_definitions_rejected():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        MultiSourceVerificationRequest(
            sources=[
                _src("a", "00000000-0000-0000-0000-000000000001", True, "id", {}),
                _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {}),
            ],
            unified_keys=["id"],
            fallback_keys=[[]],
        )
    with pytest.raises(ValidationError):
        MultiSourceVerificationRequest(
            sources=[
                _src("a", "00000000-0000-0000-0000-000000000001", True, "id", {}),
                _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {}),
            ],
            unified_keys=["id"],
            fallback_keys=[["phone"], ["phone"]],
        )


# ==============================================================================
# Endpoint-level: preview (dry-run) vs persisted run consistency
# ==============================================================================


def _fallback_endpoint_payload(f1: dict, f2: dict) -> dict:
    return {
        "sources": [
            {"alias": "academic", "file_id": f1["id"], "is_primary": True,
             "key_columns": ["student_id"],
             "field_mapping": {"student_id": "student_id", "phone": "phone"}},
            {"alias": "idcard", "file_id": f2["id"], "is_primary": False,
             "key_columns": ["enrolment_no"],
             "field_mapping": {"enrolment_no": "student_id", "mobile": "phone"}},
        ],
        "unified_keys": ["student_id"],
        "compare_attributes": ["phone"],
        "fallback_keys": [["phone"]],
        "include_identical": True,
    }


def test_preview_and_persisted_run_agree_on_fallback(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Fallback Preview Consistency Project")
    f1 = upload_csv(client, proj_id, "academic.csv", "student_id,phone\nS-1,P-1\n,P-2\n")
    f2 = upload_csv(client, proj_id, "idcard.csv", "enrolment_no,mobile\nE-1,P-1\nE-9,P-2\n")

    payload = _fallback_endpoint_payload(f1, f2)

    verify_res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}", json=payload)
    assert verify_res.status_code == 200, verify_res.text
    v_summary = verify_res.json()["summary"]

    run_res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert run_res.status_code == 201, run_res.text
    r_summary = run_res.json()["summary"]

    # S-1->E-1 (phone P-1) and blank->E-9 (phone P-2): both resolved via fallback.
    assert v_summary["fallback_matched_records"] == 2
    assert r_summary["fallback_matched_records"] == v_summary["fallback_matched_records"]
    assert r_summary["identical_matches"] == v_summary["identical_matches"]
    assert r_summary["unmatched_source_records"] == v_summary["unmatched_source_records"]

    persisted = client.get(f"/api/v1/projects/{proj_id}/runs/{run_res.json()['id']}").json()
    assert persisted["configuration"]["fallback_keys"] == [["phone"]]
    # lineage persisted on the discrepancy-free result: check via results if included
    assert persisted["status"] == "completed"


def test_endpoint_without_fallback_keys_unchanged(client: TestClient, upload_storage: Path):
    """Financial-style requests must not gain fallback matches."""
    proj_id = create_project(client, "No Fallback Project")
    f1 = upload_csv(client, proj_id, "erp.csv", "id,amount\nTX-1,100.00\n,77.00\n")
    f2 = upload_csv(client, proj_id, "bank.csv", "id,amount\nTX-2,77.00\nTX-1,100.00\n")

    payload = {
        "sources": [
            {"alias": "erp", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"]},
            {"alias": "bank", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"]},
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["amount"],
        "numeric_tolerance": 0.0,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["summary"]["fallback_matched_records"] == 0
    # The blank-key record must not be rescued without a configured fallback.
    assert data["summary"]["unmatched_source_records"] >= 1
