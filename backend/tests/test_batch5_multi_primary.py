"""Batch 5 tests: multi-primary comparison and per-field field ownership.

Scenarios: legacy compatibility, ownership validation, owner-aware comparison,
owner-blank handling, unmapped-attribute handling, identity/fallback separation,
and preview vs persisted-run consistency.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

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


def _multi_primary_defs():
    """Three authoritative files, each owning a different attribute set.

    academic owns student_name; hostel owns hostel; fee owns fee_status.
    Identity key (student_id) is mapped in all three via differently named columns.
    """
    return [
        _src("academic", "00000000-0000-0000-0000-000000000001", True, "student_id",
             {"student_id": "student_id", "student_name": "student_name"}),
        _src("hostel", "00000000-0000-0000-0000-000000000002", True, "enrol_no",
             {"enrol_no": "student_id", "hostel": "hostel", "student_name": "student_name"}),
        _src("fee", "00000000-0000-0000-0000-000000000003", True, "reg_id",
             {"reg_id": "student_id", "fee_status": "fee_status", "hostel": "hostel"}),
    ]


# ==============================================================================
# Request validation
# ==============================================================================


def test_legacy_single_primary_request_remains_valid():
    req = MultiSourceVerificationRequest(
        sources=[
            _src("a", "00000000-0000-0000-0000-000000000001", True, "id", {}),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {}),
        ],
        unified_keys=["id"],
    )
    assert req.multi_primary is False


def test_legacy_multiple_primaries_still_invalid_without_opt_in():
    with pytest.raises(ValidationError) as exc:
        MultiSourceVerificationRequest(
            sources=[
                _src("a", "00000000-0000-0000-0000-000000000001", True, "id", {}),
                _src("b", "00000000-0000-0000-0000-000000000002", True, "id", {}),
            ],
            unified_keys=["id"],
        )
    assert "multi-primary" in str(exc.value)


def test_multi_primary_with_valid_ownership_accepted():
    req = MultiSourceVerificationRequest(
        sources=_multi_primary_defs(),
        unified_keys=["student_id"],
        multi_primary=True,
        field_ownership={"student_name": "academic", "hostel": "hostel", "fee_status": "fee"},
    )
    assert req.multi_primary is True
    assert req.field_ownership["hostel"] == "hostel"


def test_multi_primary_requires_at_least_one_primary():
    with pytest.raises(ValidationError) as exc:
        MultiSourceVerificationRequest(
            sources=[
                _src("a", "00000000-0000-0000-0000-000000000001", False, "id", {}),
                _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {}),
            ],
            unified_keys=["id"],
            multi_primary=True,
        )
    assert "primary source" in str(exc.value)


def test_unknown_owner_alias_rejected():
    with pytest.raises(ValidationError) as exc:
        MultiSourceVerificationRequest(
            sources=_multi_primary_defs(),
            unified_keys=["student_id"],
            multi_primary=True,
            field_ownership={"hostel": "nonexistent"},
        )
    assert "unknown source alias" in str(exc.value)


def test_owner_without_mapped_attribute_rejected():
    sources = _multi_primary_defs()
    # fee does not map student_name.
    with pytest.raises(ValidationError) as exc:
        MultiSourceVerificationRequest(
            sources=sources,
            unified_keys=["student_id"],
            multi_primary=True,
            field_ownership={"student_name": "fee"},
        )
    assert "does not map" in str(exc.value)


def test_ownership_on_identity_key_rejected():
    with pytest.raises(ValidationError) as exc:
        MultiSourceVerificationRequest(
            sources=_multi_primary_defs(),
            unified_keys=["student_id"],
            multi_primary=True,
            field_ownership={"student_id": "academic"},
        )
    assert "Identity key attribute" in str(exc.value)


def test_field_ownership_without_opt_in_rejected():
    with pytest.raises(ValidationError) as exc:
        MultiSourceVerificationRequest(
            sources=[
                _src("a", "00000000-0000-0000-0000-000000000001", True, "id", {"name": "name"}),
                _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {"name": "name"}),
            ],
            unified_keys=["id"],
            field_ownership={"name": "a"},
        )
    assert "multi_primary" in str(exc.value)


def test_fallback_keys_with_multi_primary_rejected():
    """Documented compatibility constraint: the fallback pre-pass is primary-anchored."""
    with pytest.raises(ValidationError) as exc:
        MultiSourceVerificationRequest(
            sources=_multi_primary_defs(),
            unified_keys=["student_id"],
            multi_primary=True,
            fallback_keys=[["phone"]],
        )
    assert "Fallback matching is not yet supported" in str(exc.value)


# ==============================================================================
# Comparison behavior
# ==============================================================================


def _ownership_records(name_owner="academic"):
    return {
        "academic": [
            (1, {"student_id": "S-1", "student_name": "Asha", "hostel": "Tagore"}),
            (2, {"student_id": "S-2", "student_name": "Ravi", "hostel": "Tagore"}),
        ],
        "hostel": [
            (1, {"enrol_no": "S-1", "hostel": "Tagore", "student_name": "Asha"}),
            (2, {"enrol_no": "S-2", "hostel": "Nehru", "student_name": "Ravi"}),
        ],
        "fee": [
            (1, {"reg_id": "S-1", "fee_status": "PAID", "hostel": "Tagore"}),
            (2, {"reg_id": "S-2", "fee_status": "PAID", "hostel": "Nehru"}),
        ],
    }


def test_field_compared_against_configured_owner():
    """Hostel owns 'hostel'; academic's conflicting hostel value is a mismatch vs owner."""
    summary, results, discrepancies, _, _ = verify_multisource_datasets(
        sources=_multi_primary_defs(),
        sources_records=_ownership_records(),
        unified_keys=["student_id"],
        compare_attributes=["student_name", "hostel"],
        multi_primary=True,
        field_ownership={"student_name": "academic", "hostel": "hostel"},
    )
    assert summary.matched_records == 2
    s2 = next(it for it in results if it.key_values.get("student_id") == "S-2")
    # academic says Tagore, owner (hostel) says Nehru -> mismatch attributed to owner.
    hostel_diff = next(d for d in s2.field_differences if d.field_name == "hostel")
    assert hostel_diff.source_field.startswith("hostel.")
    assert hostel_diff.source_value == "Nehru"
    assert hostel_diff.target_value == "Tagore"  # academic (non-owner) value
    # student_name agrees with owner -> no diff for it.
    assert not any(d.field_name == "student_name" for d in s2.field_differences)


def test_non_owner_agreement_does_not_override_owner():
    """A non-owner source agreeing with another non-owner does not validate a conflict."""
    records = _ownership_records()
    # Owner academic says "Asha"; the only participating non-owner (hostel) says "Wrong".
    records["hostel"][0][1]["student_name"] = "Wrong"
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=_multi_primary_defs(),
        sources_records=records,
        unified_keys=["student_id"],
        compare_attributes=["student_name", "hostel"],
        multi_primary=True,
        field_ownership={"student_name": "academic", "hostel": "hostel"},
    )
    s1 = next(it for it in results if it.key_values.get("student_id") == "S-1")
    name_diff = next(d for d in s1.field_differences if d.field_name == "student_name")
    assert name_diff.source_value == "Asha"      # owner value is authoritative
    assert name_diff.target_value == "Wrong"
    assert s1.match_status.value == "field_mismatch"

    # When the non-owner agrees with the owner, the record is identical.
    records2 = _ownership_records()
    summary2, results2, _, _, _ = verify_multisource_datasets(
        sources=_multi_primary_defs(),
        sources_records=records2,
        unified_keys=["student_id"],
        compare_attributes=["student_name", "hostel"],
        multi_primary=True,
        field_ownership={"student_name": "academic", "hostel": "hostel"},
    )
    s1b = next(it for it in results2 if it.key_values.get("student_id") == "S-1")
    assert s1b.match_status.value == "identical"


def test_owner_blank_value_not_promoted_and_not_verified():
    """Owner's blank value -> attribute unverified, no mismatch fabricated."""
    records = _ownership_records()
    records["hostel"][0][1]["hostel"] = None  # owner (hostel) blank for S-1
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=_multi_primary_defs(),
        sources_records=records,
        unified_keys=["student_id"],
        compare_attributes=["student_name", "hostel"],
        multi_primary=True,
        field_ownership={"student_name": "academic", "hostel": "hostel"},
    )
    s1 = next(it for it in results if it.key_values.get("student_id") == "S-1")
    assert s1.match_status.value == "identical"  # compared fields agree
    assert "hostel" in (s1.unverified_fields or [])
    assert s1.field_differences == []


def test_attribute_not_carried_by_a_source_is_not_compared_there():
    """Fee file does not map student_name; it must not be compared against None."""
    records = _ownership_records()
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=_multi_primary_defs(),
        sources_records=records,
        unified_keys=["student_id"],
        compare_attributes=["student_name", "hostel"],
        multi_primary=True,
        field_ownership={"student_name": "academic", "hostel": "hostel"},
    )
    s1 = next(it for it in results if it.key_values.get("student_id") == "S-1")
    # fee is not a participant for student_name; no null_mismatch fabricated.
    assert not any(
        d.field_name == "student_name" and d.difference_type == "null_mismatch"
        for d in (s1.field_differences or [])
    )


def test_missing_attribute_not_silently_treated_as_equal():
    """Owner blank vs non-owner value: field must be listed unverified, not equal."""
    records = _ownership_records()
    records["academic"][1][1]["student_name"] = None  # owner blank for S-2
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=_multi_primary_defs(),
        sources_records=records,
        unified_keys=["student_id"],
        compare_attributes=["student_name", "hostel"],
        multi_primary=True,
        field_ownership={"student_name": "academic", "hostel": "hostel"},
    )
    s2 = next(it for it in results if it.key_values.get("student_id") == "S-2")
    assert "student_name" in (s2.unverified_fields or [])
    assert not any(d.field_name == "student_name" for d in (s2.field_differences or []))


def test_multi_primary_lineage_records_ownership_mode():
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=_multi_primary_defs(),
        sources_records=_ownership_records(),
        unified_keys=["student_id"],
        compare_attributes=["student_name", "hostel"],
        multi_primary=True,
        field_ownership={"student_name": "academic", "hostel": "hostel"},
    )
    for it in results:
        assert (it.lineage or {}).get("ownership_mode") == "multi_primary"
        assert (it.lineage or {}).get("matching_method") == "primary_key"


def test_identity_matching_separate_from_ownership():
    """Identity uses the configured key (differently named columns via mapping);
    ownership only governs value comparison. Owner of hostel is the fee file here."""
    records = _ownership_records()
    # Align academic's S-2 hostel with the fee owner so only ownership, not data,
    # differs from the academic-owner scenario.
    records["academic"][1][1]["hostel"] = "Nehru"
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=_multi_primary_defs(),
        sources_records=records,
        unified_keys=["student_id"],
        compare_attributes=["hostel"],
        multi_primary=True,
        field_ownership={"hostel": "fee"},
    )
    assert summary.matched_records == 2
    assert summary.identical_matches == 2
    diff_fields = [d.field_name for it in results for d in (it.field_differences or [])]
    assert "hostel" not in diff_fields


def test_legacy_single_primary_engine_behavior_unchanged():
    """Without multi_primary, all secondaries are compared against the primary."""
    sources_data = {
        "a": [(1, {"id": "1", "val": "10"})],
        "b": [(1, {"id": "1", "val": "99"})],
        "c": [(1, {"id": "1", "val": "99"})],
    }
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", {"id": "id", "val": "val"}),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {"id": "id", "val": "val"}),
            _src("c", "00000000-0000-0000-0000-000000000003", False, "id", {"id": "id", "val": "val"})]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
    )
    # Legacy: b AND c each mismatch vs primary (even though b and c agree).
    assert summary.field_mismatches == 1
    diffs = results[0].field_differences
    assert len(diffs) == 2
    assert all(d.source_field.startswith("a.") for d in diffs)


def test_multi_primary_default_owner_is_first_primary():
    """Attributes without an explicit owner default to the first primary source."""
    records = _ownership_records()
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=_multi_primary_defs(),
        sources_records=records,
        unified_keys=["student_id"],
        compare_attributes=["student_name"],
        multi_primary=True,
        field_ownership={"hostel": "hostel"},  # student_name unowned -> academic
    )
    assert summary.identical_matches == 2


# ==============================================================================
# Execution and compatibility
# ==============================================================================


def _mp_endpoint_payload(f_academic: dict, f_hostel: dict, f_fee: dict) -> dict:
    return {
        "sources": [
            {"alias": "academic", "label": "Academic Records", "file_id": f_academic["id"],
             "is_primary": True, "key_columns": ["student_id"],
             "field_mapping": {"student_id": "student_id", "student_name": "student_name", "hostel": "hostel"}},
            {"alias": "hostel", "label": "Hostel Records", "file_id": f_hostel["id"],
             "is_primary": True, "key_columns": ["enrol_no"],
             "field_mapping": {"enrol_no": "student_id", "hostel": "hostel", "student_name": "student_name"}},
            {"alias": "fee", "label": "Fee Records", "file_id": f_fee["id"],
             "is_primary": True, "key_columns": ["reg_id"],
             "field_mapping": {"reg_id": "student_id", "fee_status": "fee_status", "hostel": "hostel"}},
        ],
        "unified_keys": ["student_id"],
        "compare_attributes": ["student_name", "hostel"],
        "multi_primary": True,
        "field_ownership": {"student_name": "academic", "hostel": "hostel"},
        "include_identical": True,
    }


def test_endpoint_multi_primary_preview_and_persisted_agree(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Multi-Primary Consistency Project")
    f1 = upload_csv(client, proj_id, "academic.csv", "student_id,student_name,hostel\nS-1,Asha,Tagore\nS-2,Ravi,Tagore\n")
    f2 = upload_csv(client, proj_id, "hostel.csv", "enrol_no,hostel,student_name\nS-1,Tagore,Asha\nS-2,Nehru,Ravi\n")
    f3 = upload_csv(client, proj_id, "fee.csv", "reg_id,fee_status,hostel\nS-1,PAID,Tagore\nS-2,PAID,Nehru\n")

    payload = _mp_endpoint_payload(f1, f2, f3)

    verify_res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}", json=payload)
    assert verify_res.status_code == 200, verify_res.text
    v_data = verify_res.json()

    run_res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert run_res.status_code == 201, run_res.text
    r_data = run_res.json()

    assert v_data["summary"]["matched_records"] == 2
    assert r_data["summary"]["matched_records"] == v_data["summary"]["matched_records"]
    assert r_data["summary"]["field_mismatches"] == v_data["summary"]["field_mismatches"]

    persisted = client.get(f"/api/v1/projects/{proj_id}/runs/{run_res.json()['id']}").json()
    assert persisted["configuration"]["multi_primary"] is True
    assert persisted["configuration"]["field_ownership"] == {"student_name": "academic", "hostel": "hostel"}
    assert persisted["status"] == "completed"


def test_endpoint_invalid_ownership_422(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Invalid Ownership Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,name\n1,A\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,name\n1,A\n")

    res = client.post(
        f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}",
        json={
            "sources": [
                {"alias": "a", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"],
                 "field_mapping": {"id": "id"}},
                {"alias": "b", "file_id": f2["id"], "is_primary": True, "key_columns": ["id"],
                 "field_mapping": {"id": "id", "name": "name"}},
            ],
            "unified_keys": ["id"],
            "multi_primary": True,
            "field_ownership": {"name": "a"},  # a does not map name
        },
    )
    assert res.status_code == 422
    assert "does not map" in str(res.json()["detail"])


def test_financial_request_without_multi_primary_unchanged(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Financial Multi-Primary Regression Project")
    f1 = upload_csv(client, proj_id, "erp.csv", "id,amount,status\nTX-1,100.00,COMPLETED\nTX-2,200.00,COMPLETED\n")
    f2 = upload_csv(client, proj_id, "bank.csv", "id,amount,status\nTX-1,100.00,COMPLETED\nTX-2,205.00,COMPLETED\n")

    payload = {
        "sources": [
            {"alias": "erp", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"]},
            {"alias": "bank", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"]},
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["amount", "status"],
        "numeric_tolerance": 0.0,
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["summary"]["identical_matches"] == 1
    assert data["summary"]["field_mismatches"] == 1
    assert data["configuration"].get("multi_primary", False) is False


def test_batch4_fallback_still_works_in_legacy_mode(client: TestClient, upload_storage: Path):
    """Fallback matching remains fully functional when multi-primary is not enabled."""
    proj_id = create_project(client, "Fallback Legacy Mode Project")
    f1 = upload_csv(client, proj_id, "academic.csv", "student_id,phone\nS-1,P-1\n,P-2\n")
    f2 = upload_csv(client, proj_id, "idcard.csv", "enrolment_no,mobile\nE-1,P-1\nE-9,P-2\n")

    payload = {
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
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert res.status_code == 201, res.text
    assert res.json()["summary"]["fallback_matched_records"] == 2
