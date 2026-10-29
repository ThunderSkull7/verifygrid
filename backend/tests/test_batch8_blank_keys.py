"""Batch 8 tests: blank/null identity-key safety.

Shared validity rule under test: an identity-key component is valid only if it
is not None and not a whitespace-only/empty string; a composite key is valid
only if EVERY component is valid. Invalid-key records are NEVER identity-matched
on the invalid key — they surface as needs_review / NULL_KEY outcomes, remain
visible, and are never counted as successful matches or confirmed duplicates.
"""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.schemas.multisource import SourceDefinition
from app.services.verification_engine import (
    key_tuple_is_valid,
    verify_datasets,
    verify_multisource_datasets,
)

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
# Validity rule unit tests
# ==============================================================================


def test_validity_rule_rejects_blank_and_whitespace_components():
    assert key_tuple_is_valid((None,)) is False
    assert key_tuple_is_valid(("",)) is False
    assert key_tuple_is_valid(("   ",)) is False
    assert key_tuple_is_valid(("S-1", None)) is False          # composite, one missing
    assert key_tuple_is_valid(("S-1", "  ")) is False
    assert key_tuple_is_valid(("S-1", "U-1")) is True
    assert key_tuple_is_valid(("0123",)) is True               # leading zeros are valid


# ==============================================================================
# Invalid primary keys (multi-source)
# ==============================================================================


def _cm():
    return {"id": "id", "val": "val"}


def _run_ms(defs, records, **kw):
    summary, results, discrepancies, _, _ = verify_multisource_datasets(
        sources=defs,
        sources_records=records,
        unified_keys=["id"],
        compare_attributes=["val"],
        numeric_tolerance=0.0,
        include_identical=True,
        **kw,
    )
    return summary, results, discrepancies


def test_both_records_null_identity_never_match():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": None, "val": "10"})],
        "b": [(1, {"id": None, "val": "10"})],
    }
    summary, results, _ = _run_ms(defs, records)
    assert summary.matched_records == 0
    assert summary.identical_matches == 0
    assert summary.invalid_key_records == 2  # one record per source
    review = [r for r in results if r.match_status.value == "needs_review"]
    # Batch 9: ONE item per record — both blank-key records remain represented.
    assert len(review) == 2
    assert all(r.reason_code.value == "NULL_KEY" for r in review)
    assert all("NOT" in r.message for r in review)  # non-misleading explanation


def test_both_records_empty_string_identity_never_match():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": "", "val": "10"})],
        "b": [(1, {"id": "", "val": "10"})],
    }
    summary, results, _ = _run_ms(defs, records)
    assert summary.matched_records == 0
    assert summary.invalid_key_records == 2
    assert any(r.match_status.value == "needs_review" for r in results)


def test_whitespace_only_identity_never_match():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": "   ", "val": "10"})],
        "b": [(1, {"id": "\t", "val": "10"})],
    }
    summary, results, _ = _run_ms(defs, records)
    assert summary.matched_records == 0
    assert summary.invalid_key_records == 2


def test_several_blank_keys_across_sources_stay_unmatched():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": None, "val": "1"}), (2, {"id": None, "val": "2"}), (3, {"id": "K-1", "val": "3"})],
        "b": [(1, {"id": None, "val": "1"}), (2, {"id": "K-1", "val": "3"})],
    }
    summary, results, _ = _run_ms(defs, records)
    # K-1 matches normally; the two blank-key records in 'a' and one in 'b'
    # must NOT merge into a (None,) tuple match.
    assert summary.matched_records == 1
    assert summary.identical_matches == 1
    assert summary.invalid_key_records == 3
    review = [r for r in results if r.match_status.value == "needs_review"]
    # Batch 9: one item per record — all 3 blank-key records stay represented.
    assert len(review) == 3
    assert sum(len(r.source_records or {}) for r in review) == 3
    assert summary.attribute_comparisons_completed == 1  # only K-1's pair


def test_identical_non_key_attributes_do_not_cause_blank_key_match():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": None, "val": "identical-value"})],
        "b": [(1, {"id": None, "val": "identical-value"})],
    }
    summary, results, _ = _run_ms(defs, records)
    assert summary.matched_records == 0
    assert summary.invalid_key_records == 2
    # No attribute comparison ran -> nothing reported as verified/checked.
    assert summary.attribute_comparisons_completed == 0


def test_different_non_key_attributes_do_not_cause_blank_key_match_or_mismatch():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": None, "val": "one"})],
        "b": [(1, {"id": None, "val": "two"})],
    }
    summary, results, _ = _run_ms(defs, records)
    assert summary.matched_records == 0
    assert summary.field_mismatches == 0  # no attribute comparison ran
    assert all(
        not r.field_differences for r in results  # invalid key is not an attribute mismatch
    )


def test_invalid_key_records_remain_visible_in_results():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": None, "val": "10"})],
        "b": [(1, {"id": None, "val": "10"})],
    }
    summary, results, discrepancies = _run_ms(defs, records)
    # Batch 9: one result item per record, each carrying its own record.
    assert len(results) == 2
    assert len(discrepancies) == 2
    per_source = {
        alias: next(r for r in results if alias in (r.source_records or {}))
        for alias in ("a", "b")
    }
    assert per_source["a"].source_records == {"a": records["a"][0][1]}
    assert per_source["b"].source_records == {"b": records["b"][0][1]}
    assert all(r.unverified_fields == ["val"] for r in results)  # explicitly NOT verified


def test_missing_identity_column_is_invalid_not_matchable():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": "K-1", "val": "10"})],
        "b": [(1, {"val": "10"})],  # 'id' column entirely absent -> invalid key
    }
    summary, results, _ = _run_ms(defs, records)
    assert summary.matched_records == 0
    assert summary.invalid_key_records == 1
    assert any(r.match_status.value == "needs_review" for r in results)


def test_composite_key_one_missing_component_never_matches():
    cm = {"id": "id", "sub": "sub", "val": "val"}
    defs = [_src("a", str(uuid.uuid4()), True, "id", cm),
            _src("b", str(uuid.uuid4()), False, "id", cm)]
    records = {
        "a": [(1, {"id": "K-1", "sub": None, "val": "10"})],
        "b": [(1, {"id": "K-1", "sub": None, "val": "10"})],
    }
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=records, unified_keys=["id", "sub"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
    )
    assert summary.matched_records == 0
    assert summary.invalid_key_records == 2


# ==============================================================================
# Valid identity keys
# ==============================================================================


def test_valid_single_and_composite_keys_still_match():
    cm = {"id": "id", "sub": "sub", "val": "val"}
    defs = [_src("a", str(uuid.uuid4()), True, "id", cm),
            _src("b", str(uuid.uuid4()), False, "id", cm)]
    records = {
        "a": [
            (1, {"id": "K-1", "sub": "S-1", "val": "10"}),
            (2, {"id": "K-2", "sub": None, "val": "20"}),
        ],
        "b": [
            (1, {"id": "K-1", "sub": "S-1", "val": "10"}),
            (2, {"id": "K-2", "sub": None, "val": "20"}),
        ],
    }
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=records, unified_keys=["id", "sub"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
    )
    # (K-1, S-1) valid composite -> matched. (K-2, None) invalid composite -> review.
    assert summary.matched_records == 1
    assert summary.identical_matches == 1
    assert summary.invalid_key_records == 2


def test_leading_zero_identifiers_remain_distinct():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": "0123", "val": "10"})],
        "b": [(1, {"id": "123", "val": "10"})],
    }
    summary, _, _ = _run_ms(defs, records)
    # "0123" and "123" are different identifiers — no match, and NOT invalid keys.
    assert summary.matched_records == 0
    assert summary.invalid_key_records == 0
    assert summary.unmatched_source_records == 1
    assert summary.unmatched_target_records == 1


def test_invalid_key_record_not_mislabeled_as_duplicate():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": None, "val": "1"}), (2, {"id": None, "val": "2"})],
        "b": [],
    }
    summary, results, _ = _run_ms(defs, records)
    assert summary.duplicate_source_keys_count == 0  # blank keys are NOT duplicates
    assert summary.invalid_key_records == 2
    assert all(
        r.match_status.value not in ("duplicate_key_source", "duplicate_key_target")
        for r in results
    )


def test_valid_duplicate_key_groups_keep_duplicate_outcome():
    defs = [_src("a", str(uuid.uuid4()), True, "id", _cm()),
            _src("b", str(uuid.uuid4()), False, "id", _cm())]
    records = {
        "a": [(1, {"id": "K-1", "val": "1"}), (2, {"id": "K-1", "val": "2"})],
        "b": [],
    }
    summary, _, _ = _run_ms(defs, records)
    assert summary.duplicate_source_keys_count == 1
    assert summary.invalid_key_records == 0


# ==============================================================================
# Fallback compatibility
# ==============================================================================


def test_blank_fallback_components_never_match():
    cm = {"id": "id", "phone": "phone", "val": "val"}
    defs = [_src("a", str(uuid.uuid4()), True, "id", cm),
            _src("b", str(uuid.uuid4()), False, "id", cm)]
    records = {
        "a": [
            (1, {"id": "X-1", "phone": None, "val": "10"}),
            (2, {"id": "X-2", "phone": None, "val": "20"}),
        ],
        "b": [
            (1, {"id": "Y-1", "phone": None, "val": "10"}),
            (2, {"id": "Y-2", "phone": None, "val": "20"}),
        ],
    }
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=records, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    # Shared blank phone values must never establish identity: no fallback match,
    # no invalid keys (ids are valid), and each record stays unmatched on its own
    # primary key rather than merging on the missing phone value.
    assert summary.matched_records == 0
    assert summary.fallback_matched_records == 0
    assert summary.invalid_key_records == 0
    assert summary.unmatched_source_records == 2
    assert summary.unmatched_target_records == 2


def test_invalid_primary_key_can_match_via_valid_fallback_component():
    """Legacy mode only: a blank primary key resolved by an unambiguous valid
    fallback key is preserved (never on missing identity components)."""
    cm = {"id": "id", "phone": "phone", "val": "val"}
    defs = [_src("a", str(uuid.uuid4()), True, "id", cm),
            _src("b", str(uuid.uuid4()), False, "id", cm)]
    records = {
        "a": [
            (1, {"id": None, "phone": "P-1", "val": "10"}),
            (2, {"id": "K-1", "phone": "P-2", "val": "20"}),
        ],
        "b": [
            (1, {"id": "Y-1", "phone": "P-1", "val": "10"}),
            (2, {"id": "K-1", "phone": "P-2", "val": "20"}),
        ],
    }
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=records, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    # Row 1: invalid primary key, unique valid fallback (P-1) -> resolved.
    # Row 2: valid primary key K-1 -> matched normally (fallback not needed).
    assert summary.matched_records == 2
    assert summary.fallback_matched_records == 1
    assert summary.invalid_key_records == 0
    resolved = next(r for r in results if r.key_values.get("id") is None)
    assert (resolved.lineage or {}).get("matching_method") == "fallback_key"


def test_fallback_match_never_reuses_a_row_and_stays_ordered():
    cm = {"id": "id", "phone": "phone", "val": "val"}
    defs = [_src("a", str(uuid.uuid4()), True, "id", cm),
            _src("b", str(uuid.uuid4()), False, "id", cm)]
    records = {
        "a": [
            (1, {"id": None, "phone": "P-1", "val": "10"}),
            (2, {"id": "K-1", "phone": "P-2", "val": "20"}),
        ],
        "b": [
            (1, {"id": "Y-1", "phone": "P-1", "val": "10"}),
            (2, {"id": "K-1", "phone": "P-1", "val": "20"}),
        ],
    }
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=records, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    # b has TWO rows with phone P-1 -> the fallback candidate group is ambiguous and
    # must remain unresolved (never resolved by row reuse or arbitrary choice).
    # The valid K-1 tuple still matches normally, exactly once.
    assert summary.fallback_matched_records == 0
    assert summary.matched_records == 1
    assert summary.identical_matches == 1
    assert summary.invalid_key_records == 1  # the blank-id record stays needs_review


def test_ambiguous_fallback_candidates_remain_unresolved():
    cm = {"id": "id", "phone": "phone", "val": "val"}
    defs = [_src("a", str(uuid.uuid4()), True, "id", cm),
            _src("b", str(uuid.uuid4()), False, "id", cm)]
    records = {
        "a": [(1, {"id": None, "phone": "P-1", "val": "10"})],
        "b": [
            (1, {"id": "Y-1", "phone": "P-1", "val": "10"}),
            (2, {"id": "Y-2", "phone": "P-1", "val": "20"}),
        ],
    }
    summary, _, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=records, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    # Two candidates -> ambiguity is never resolved, and 'b' rows also form a
    # duplicate key group on their own primary keys.
    assert summary.fallback_matched_records == 0


def test_multi_primary_still_rejects_fallback_keys():
    """Batch 5 constraint remains: fallback + multi-primary is a 422 (never enabled)."""
    from pydantic import ValidationError

    import tests.test_batch5_multi_primary as b5

    with pytest.raises(ValidationError) as exc:
        b5.MultiSourceVerificationRequest(
            sources=b5._multi_primary_defs(),
            unified_keys=["student_id"],
            multi_primary=True,
            fallback_keys=[["phone"]],
        )
    assert "Fallback matching is not yet supported" in str(exc.value)


# ==============================================================================
# Two-source / financial path
# ==============================================================================


def test_two_source_blank_keys_never_match_financial_path():
    source = [(1, {"txn_id": None, "amount": 100.0})]
    target = [(1, {"txn_id": None, "amount": 100.0})]
    summary, results, discrepancies, warnings, _ = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["txn_id"],
    )
    assert summary.matched_records == 0
    assert summary.identical_matches == 0
    assert summary.invalid_key_records == 2
    assert all(r.match_status.value == "needs_review" for r in results)
    assert len(discrepancies) == 2


def test_two_source_valid_keys_unchanged():
    source = [(1, {"txn_id": "T-1", "amount": 100.0})]
    target = [(1, {"txn_id": "T-1", "amount": 100.0})]
    summary, results, _, _, _ = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["txn_id"],
    )
    assert summary.matched_records == 1
    assert summary.identical_matches == 1
    assert summary.invalid_key_records == 0


def test_two_source_composite_partial_null_explicit():
    source = [(1, {"tenant": "T1", "user_id": None, "role": "admin"})]
    target = [(1, {"tenant": "T1", "user_id": None, "role": "admin"})]
    summary, _, _, _, _ = verify_datasets(
        source_records=source,
        target_records=target,
        key_columns=["tenant", "user_id"],
    )
    # Previously this blank-composite pair "matched identically"; now it cannot.
    assert summary.matched_records == 0
    assert summary.invalid_key_records == 2


# ==============================================================================
# Execution consistency
# ==============================================================================


def test_endpoint_preview_and_persisted_agree_on_blank_keys(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Blank Key Consistency Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,val\n,10\nK-1,20\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,val\n,10\nK-1,20\n")

    payload = {
        "sources": [
            {"alias": "a", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"],
             "field_mapping": {"id": "id", "val": "val"}},
            {"alias": "b", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"],
             "field_mapping": {"id": "id", "val": "val"}},
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["val"],
        "include_identical": True,
    }
    v_res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}", json=payload)
    assert v_res.status_code == 200, v_res.text
    v_summary = v_res.json()["summary"]

    r_res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert r_res.status_code == 201, r_res.text
    r_summary = r_res.json()["summary"]

    assert v_summary["invalid_key_records"] == 2
    assert v_summary["matched_records"] == 1  # only K-1
    assert r_summary["invalid_key_records"] == v_summary["invalid_key_records"]
    assert r_summary["matched_records"] == v_summary["matched_records"]
    # Coverage: blank-key pairs are not checked, valid-key pairs are completed.
    assert v_summary["attribute_comparisons_completed"] == 1
    assert v_summary["attributes_not_checked"] == 2

    persisted = client.get(f"/api/v1/projects/{proj_id}/runs/{r_res.json()['id']}").json()
    assert persisted["summary"]["invalid_key_records"] == 2
    assert persisted["status"] == "completed"
