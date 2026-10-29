"""Batch 6 tests: attribute-level coverage counters and result status semantics.

Coverage definitions under test (per run):
- Denominator: (all-present, non-duplicate result records) x (configured compare attributes).
- attribute_comparisons_completed: pairs where at least one actual comparison executed.
- attributes_not_checked: pairs where no comparison could execute
  (owner value blank, or attribute unavailable in every applicable source).
- completed + not_checked == denominator; fallback-matched records are counted once.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.schemas.multisource import SourceDefinition
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


def test_two_source_legacy_coverage_all_compared():
    """Legacy two-source run: every record-attribute pair is compared exactly once."""
    sources_data = {
        "a": [(1, {"id": "1", "val": "10"}), (2, {"id": "2", "val": "20"})],
        "b": [(1, {"id": "1", "val": "10"}), (2, {"id": "2", "val": "25"})],
    }
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", {"id": "id", "val": "val"}),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {"id": "id", "val": "val"})]
    summary, _, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
    )
    assert summary.matched_records == 2
    assert summary.attribute_comparisons_completed == 2  # 2 records x 1 attribute
    assert summary.attributes_not_checked == 0


def test_multi_source_legacy_coverage_denominator():
    """Three-source legacy run: pairs counted per attribute, not per source comparison."""
    sources_data = {
        "a": [(1, {"id": "1", "val": "10"})],
        "b": [(1, {"id": "1", "val": "10"})],
        "c": [(1, {"id": "1", "val": "12"})],
    }
    cm = {"id": "id", "val": "val"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", cm),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", cm),
            _src("c", "00000000-0000-0000-0000-000000000003", False, "id", cm)]
    summary, _, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
    )
    # One record x one attribute = 1 completed pair (two actual source comparisons
    # happen, but the metric measures record-attribute pairs, not source pairs).
    assert summary.attribute_comparisons_completed == 1
    assert summary.attributes_not_checked == 0


def test_owner_blank_attribute_counted_as_not_checked():
    """Multi-primary: owner-blank pair is not checked and excluded from completed."""
    cm_a = {"student_id": "student_id", "student_name": "student_name"}
    cm_h = {"enrol_no": "student_id", "hostel": "hostel", "student_name": "student_name"}
    defs = [_src("academic", "00000000-0000-0000-0000-000000000001", True, "student_id", cm_a),
            _src("hostel", "00000000-0000-0000-0000-000000000002", True, "enrol_no", cm_h)]
    sources_data = {
        "academic": [(1, {"student_id": "S-1", "student_name": "Asha"})],
        "hostel": [(1, {"enrol_no": "S-1", "hostel": None, "student_name": "Asha"})],  # owner of hostel is blank
    }
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["student_id"],
        compare_attributes=["student_name", "hostel"],
        multi_primary=True,
        field_ownership={"student_name": "academic", "hostel": "hostel"},
    )
    assert summary.attribute_comparisons_completed == 1  # student_name compared vs hostel
    assert summary.attributes_not_checked == 1          # hostel (owner blank)
    assert summary.attribute_comparisons_completed + summary.attributes_not_checked == 2
    item = results[0]
    assert "hostel" in (item.unverified_fields or [])


def test_attribute_unavailable_in_every_applicable_source_not_checked():
    """Owner blank case and non-carried attribute produce not-checked, never verified."""
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id",
                 {"id": "id", "phone": "phone"}),
            _src("b", "00000000-0000-0000-0000-000000000002", True, "id",
                 {"id": "id"})]  # b does not carry phone; a (sole primary) owns it by default
    sources_data = {
        "a": [(1, {"id": "1", "phone": "P-1"})],
        "b": [(1, {"id": "1"})],
    }
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["phone"],
        multi_primary=True,
    )
    assert summary.attributes_not_checked == 1
    assert summary.attribute_comparisons_completed == 0
    assert "phone" in (results[0].unverified_fields or [])


def test_fallback_matched_record_counted_once():
    """Fallback-matched records flow through the compare loop exactly once."""
    cm = {"id": "id", "phone": "phone", "val": "val"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", cm),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", cm)]
    sources_data = {
        "a": [
            (1, {"id": "X-1", "phone": "P-1", "val": "10"}),
            (2, {"id": "X-2", "phone": "P-2", "val": "20"}),
        ],
        "b": [
            (1, {"id": "Y-1", "phone": "P-1", "val": "10"}),
            (2, {"id": "Y-2", "phone": "P-2", "val": "25"}),
        ],
    }
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
        fallback_keys=[["phone"]],
    )
    # Both records matched via fallback (primary key mismatched on both) and compared.
    assert summary.fallback_matched_records == 2
    assert summary.matched_records == 2
    assert summary.attribute_comparisons_completed == 2  # no double counting
    assert summary.attributes_not_checked == 0


def test_missing_and_duplicate_records_excluded_from_attribute_denominator():
    """Missing-source and duplicate-key records never contribute attribute pairs."""
    cm = {"id": "id", "val": "val"}
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", cm),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", cm)]
    sources_data = {
        "a": [(1, {"id": "1", "val": "10"}), (2, {"id": "2", "val": "20"}), (3, {"id": "3", "val": "30"})],
        "b": [(1, {"id": "1", "val": "10"}), (2, {"id": "2", "val": "20"}), (3, {"id": "2", "val": "99"})],
        # record 3: missing in b; duplicate key "2" in b -> duplicate outcome
    }
    summary, _, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
    )
    # Only record "1" is all-present and non-duplicate -> one attribute pair.
    assert summary.attribute_comparisons_completed == 1
    assert summary.attributes_not_checked == 0
    assert summary.unmatched_target_records == 1  # record 3 present only in primary
    assert summary.duplicate_target_keys_count == 1  # duplicate key "2" in b


def test_preview_and_persisted_coverage_agree(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Coverage Consistency Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,val\n1,10\n2,20\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,val\n1,10\n2,25\n")

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
    assert v_res.status_code == 200
    v_summary = v_res.json()["summary"]

    r_res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert r_res.status_code == 201
    r_summary = r_res.json()["summary"]

    assert v_summary["attribute_comparisons_completed"] == 2
    assert v_summary["attributes_not_checked"] == 0
    assert r_summary["attribute_comparisons_completed"] == v_summary["attribute_comparisons_completed"]
    assert r_summary["attributes_not_checked"] == v_summary["attributes_not_checked"]

    persisted = client.get(f"/api/v1/projects/{proj_id}/runs/{r_res.json()['id']}").json()
    assert persisted["summary"]["attribute_comparisons_completed"] == 2


def test_legacy_result_items_without_metadata_render_safe():
    """Legacy-shaped results (no unverified_fields/lineage) are accepted unchanged."""
    sources_data = {
        "a": [(1, {"id": "1", "val": "10"})],
        "b": [(1, {"id": "1", "val": "10"})],
    }
    defs = [_src("a", "00000000-0000-0000-0000-000000000001", True, "id", {"id": "id"}),
            _src("b", "00000000-0000-0000-0000-000000000002", False, "id", {"id": "id"})]
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=sources_data, unified_keys=["id"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
    )
    item = results[0]
    assert item.unverified_fields is None
    assert item.lineage is None  # legacy single-primary, non-fallback
    assert summary.attribute_comparisons_completed == 1
