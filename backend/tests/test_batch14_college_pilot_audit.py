"""Batch 14: college-data end-to-end pilot audit.

Synthetic three-source scenario (academic + hostel + library) exercising identity
matching, field comparison, missing records, duplicates, blank/composite keys,
leading-zero identifiers, fallback matching, worksheets, templates, and both
execution paths (preview and persistent runs).

Expected outcomes are documented in each test before assertions. The backend
test harness uses isolated in-memory SQLite (see conftest.py) — nothing here
touches PostgreSQL, Neon, or the local development database.
"""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

import tests.test_batch7_worksheets as b7

make_multisheet_xlsx = b7.make_multisheet_xlsx
upload_file = b7.upload_file
create_project = b7.create_project
upload_csv = b7.upload_csv

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TEMPLATES = "/api/v1/templates"
MULTI_VERIFY = "/verify/multi-source"
MULTI_RUN = "/runs/multi-source"


@pytest.fixture
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


# =============================================================================
# Synthetic college datasets
# =============================================================================

ACADEMIC_CSV = """student_id,enrollment_no,name,course,batch,department
S001,E001,Asha Rao,BSc Physics,2024-2027,Physics
S002,E002,Ben Kumar,BCom,2023-2026,Commerce
S003,E003,Chitra Menon,BSc Chemistry,2024-2027,Chemistry
S004,E004,Dev Patel,BA Economics,2022-2025,Economics
,E005,Esha Nair,BSc Mathematics,2024-2027,Mathematics
S006,E006,Farhan Ali,BCom,2023-2026,Commerce
S007,,Gita Roy,BSc Physics,2024-2027,Physics
S008,E008,Ishan Das,BSc Statistics,2024-2027,Statistics
00123,E123,Jaya Iyer,BA History,2022-2025,History
S010,E010,Kabir Shah,BSc Physics,2024-2027,Physics
S011,E011,Leena Joseph,BSc Physics,2023-2026,Physics
S011,E011,Leena Joseph,BSc Physics,2023-2026,Chemistry
"""

# Library deliberately omits S004 (missing secondary record) and holds the
# duplicate S006 row plus the leading-zero-collapsed key "123".
LIBRARY_CSV = """student_id,enrollment_no,name,membership_status
S001,E001,Asha Rao,Active
S002,E002,Ben Kumar,Active
S003,E003,Chitra Menon,Active
,E005,Esha Nair,Active
S006,E006,Farhan Ali,Active
S006,E006,Farhan Ali,Inactive
S007,,Gita Roy,Active
LIB-008,E008,Ishan Das,Active
123,E123,Jaya Iyer,Active
S010,E010,Kabir Shah,Active
S011,E011,Leena Joseph,Active
"""

# "Archive" is intentionally the first worksheet, with a different column set.
# Selecting "Roster" (second) must parse only Roster; changing the template to
# "Archive" invalidates the room_number/enrollment_no mappings.
HOSTEL_SHEETS = {
    "Archive": [
        ["student_id", "name", "hostel_name", "batch"],
        ["S001", "Asha Rao", "Old Hostel", "2020-2021"],
        ["X999", "Ghost Student", "Old Hostel", "2019-2020"],
    ],
    "Roster": [
        ["student_id", "enrollment_no", "name", "hostel_name", "room_number", "batch"],
        ["S001", "E001", "Asha Rao", "Hostel A", 101, "2024-2027"],
        ["S002", "E002", "Ben Kumar", "Hostel A", 102, "2023-2026"],
        ["S002", "E002", "Ben Kumar", "Hostel B", 205, "2023-2026"],
        ["S003", "E003", "Chitra Menon", "Hostel C", 303, "2023-2026"],
        ["S004", "E004", "Dev Patel", "Hostel D", 404, "2022-2025"],
        ["", "E005", "Esha Nair", "Hostel E", 505, "2024-2027"],
        ["S006", "E006", "Farhan Ali", "Hostel F", 606, "2023-2026"],
        ["S007", "", "Gita Roy", "Hostel G", 707, "2024-2027"],
        ["S008", "E008", "Ishan Das", "Hostel H", 808, "2024-2027"],
        ["00123", "E123", "Jaya Iyer", "Hostel I", 909, "2022-2025"],
        ["S011", "E011", "Leena Joseph", "Hostel J", 1010, "2023-2026"],
    ],
    "Notes": [["note"], ["not student data"]],
}

MAPPINGS = {
    "academic": {
        "student_id": "student_id",
        "enrollment_no": "enrollment_no",
        "name": "name",
        "course": "course",
        "batch": "batch",
        "department": "department",
    },
    "hostel": {
        "student_id": "student_id",
        "enrollment_no": "enrollment_no",
        "name": "name",
        "hostel_name": "hostel_name",
        "room_number": "room_number",
        "batch": "batch",
    },
    "library": {
        "student_id": "student_id",
        "enrollment_no": "enrollment_no",
        "name": "name",
        "membership_status": "membership_status",
    },
}


def _upload_college_project(
    client: TestClient,
    name: str,
    *,
    reverse_order: bool = False,
    academic_csv: str = ACADEMIC_CSV,
) -> tuple[str, dict[str, dict]]:
    project_id = create_project(client, name)
    if reverse_order:
        files = {
            "library": upload_csv(client, project_id, "library.csv", LIBRARY_CSV),
            "hostel": upload_file(
                client,
                project_id,
                "hostel.xlsx",
                make_multisheet_xlsx(HOSTEL_SHEETS),
                XLSX_CONTENT_TYPE,
            ),
            "academic": upload_csv(client, project_id, "academic.csv", academic_csv),
        }
    else:
        files = {
            "academic": upload_csv(client, project_id, "academic.csv", academic_csv),
            "hostel": upload_file(
                client,
                project_id,
                "hostel.xlsx",
                make_multisheet_xlsx(HOSTEL_SHEETS),
                XLSX_CONTENT_TYPE,
            ),
            "library": upload_csv(client, project_id, "library.csv", LIBRARY_CSV),
        }
    return project_id, files


def _sources(files: dict[str, dict], *, composite: bool = False) -> list[dict]:
    keys = ["student_id", "enrollment_no"] if composite else ["student_id"]
    return [
        {
            "alias": "academic",
            "file_id": files["academic"]["id"],
            "is_primary": True,
            "label": "Academic Records",
            "key_columns": keys,
            "field_mapping": MAPPINGS["academic"],
        },
        {
            "alias": "hostel",
            "file_id": files["hostel"]["id"],
            "is_primary": False,
            "label": "Hostel Roster",
            "key_columns": keys,
            "field_mapping": MAPPINGS["hostel"],
            "sheet_name": "Roster",
        },
        {
            "alias": "library",
            "file_id": files["library"]["id"],
            "is_primary": False,
            "label": "Library Membership",
            "key_columns": keys,
            "field_mapping": MAPPINGS["library"],
        },
    ]


def _legacy_payload(files: dict[str, dict], *, composite: bool = False) -> dict:
    return {
        "sources": _sources(files, composite=composite),
        "unified_keys": ["student_id", "enrollment_no"] if composite else ["student_id"],
        "compare_attributes": ["name"],
        "fallback_keys": None if composite else [["enrollment_no"]],
        "include_identical": True,
    }


def _item(results: list[dict], student_id) -> dict:
    return next(r for r in results if r["key_values"].get("student_id") == student_id)


def _items_for_source_record(results: list[dict], alias: str, student_id) -> list[dict]:
    found = []
    for item in results:
        rec = (item.get("source_records") or {}).get(alias)
        if rec is not None and rec.get("student_id") == student_id:
            found.append(item)
    return found


# =============================================================================
# Main scenario: identity, comparison, coverage
# =============================================================================


def test_college_main_scenario_identity_and_result_outcomes(
    client: TestClient, upload_storage: Path
):
    """Expected:
    - S001/S003/S007 match on the primary key.
    - S008 resolves via enrollment_no fallback (library key is LIB-008).
    - The leading-zero pair ('00123' vs 123) is NOT matched on student_id but
      resolves through the distinct, valid enrollment_no fallback E123 — proving
      leading zeros stay distinct and are never rewritten.
    - S002 (two hostel rows) and S006 (two library rows) are duplicate keys.
    - S011 duplicated in the primary is a duplicate-source key.
    - S004 is missing in library; S010 is missing in hostel.
    - S005's blank student_id is invalid in all three sources (3 review items).
    """
    project_id, files = _upload_college_project(client, "College Main Scenario")
    res = client.post(f"/api/v1/projects/{project_id}{MULTI_VERIFY}", json=_legacy_payload(files))
    assert res.status_code == 200, res.text
    data = res.json()
    summary = data["summary"]

    assert data["records_by_source"] == {"academic": 12, "hostel": 11, "library": 11}
    assert summary["total_source_records"] == 12
    assert summary["total_target_records"] == 22
    assert summary["matched_records"] == 5
    assert summary["identical_matches"] == 5
    assert summary["field_mismatches"] == 0
    assert summary["fallback_matched_records"] == 2
    assert summary["invalid_key_records"] == 3
    # No secondary-only record remains: library "123" is consumed by the
    # enrollment_no fallback that resolves the leading-zero pair.
    assert summary["unmatched_source_records"] == 0
    # S004 (no library row) and S010 (no hostel row) are primary records whose
    # key is absent from one target source.
    assert summary["unmatched_target_records"] == 2
    assert summary["duplicate_source_keys_count"] == 1
    assert summary["duplicate_source_records"] == 2
    assert summary["duplicate_target_keys_count"] == 2
    assert summary["duplicate_target_records"] == 4
    assert summary["total_discrepancies"] == 8
    assert summary["attribute_comparisons_completed"] == 5
    assert summary["attributes_not_checked"] == 3
    # Invalid-key rows surface as needs_review results but are counted through
    # invalid_key_records — needs_review_records is reserved for fuzzy candidates.
    assert summary["needs_review_records"] == 0
    assert len(data["results"]) == 13

    s001 = _item(data["results"], "S001")
    assert s001["match_status"] == "identical"
    assert s001["source_row_indices"] == {"academic": 2, "hostel": 2, "library": 2}
    assert s001["source_presence"] == {"academic": True, "hostel": True, "library": True}

    s004 = _item(data["results"], "S004")
    assert s004["match_status"] == "missing_in_target"
    assert s004["missing_in_sources"] == ["library"]

    s010 = _item(data["results"], "S010")
    assert s010["match_status"] == "missing_in_target"
    assert s010["missing_in_sources"] == ["hostel"]

    s002 = _item(data["results"], "S002")
    assert s002["match_status"] == "duplicate_key_source"
    assert s002["discrepancy_category"] == "duplicate_key"
    assert s002["source_row_indices"]["hostel"] == 3  # first of the two hostel rows

    s006 = _item(data["results"], "S006")
    assert s006["match_status"] == "duplicate_key_source"
    assert s006["source_row_indices"]["library"] == 6

    s011 = _item(data["results"], "S011")
    assert s011["match_status"] == "duplicate_key_source"
    assert s011["discrepancy_category"] == "duplicate_key"

    invalid = [r for r in data["results"] if r["match_status"] == "needs_review"]
    assert len(invalid) == 3
    assert all(r["reason_code"] == "NULL_KEY" for r in invalid)
    assert all(r["key_values"]["student_id"] is None for r in invalid)
    assert {next(iter(r["source_records"])) for r in invalid} == {
        "academic", "hostel", "library"
    }
    assert all("NOT" in r["message"] for r in invalid)
    assert all(r["unverified_fields"] == ["name"] for r in invalid)

    fallback = _item(data["results"], "S008")
    assert fallback["match_status"] == "identical"
    assert fallback["lineage"]["matching_method"] == "fallback_key"
    assert fallback["lineage"]["fallback_key"] == ["enrollment_no"]
    assert fallback["lineage"]["fallback_values"] == {"enrollment_no": "E008"}
    assert fallback["source_records"]["library"]["student_id"] == "LIB-008"

    zero_item = next(
        r for r in data["results"]
        if (r.get("source_records") or {}).get("academic", {}).get("student_id") == "00123"
    )
    assert zero_item["match_status"] == "identical"
    assert zero_item["lineage"]["matching_method"] == "fallback_key"
    assert zero_item["lineage"]["fallback_values"] == {"enrollment_no": "E123"}
    library_id = zero_item["source_records"]["library"]["student_id"]
    assert library_id != "00123"  # never rewritten to the primary form
    assert str(library_id) == "123"
    assert summary["invalid_key_records"] == 3  # distinct values, NOT invalid keys


def test_college_composite_key_with_one_blank_component(
    client: TestClient, upload_storage: Path
):
    """Expected: composite (student_id, enrollment_no).
    S005 has a blank student_id and S007 a blank enrollment_no in all three
    sources -> 6 per-record needs_review items, never a composite match.
    """
    project_id, files = _upload_college_project(client, "College Composite Keys")
    res = client.post(
        f"/api/v1/projects/{project_id}{MULTI_VERIFY}",
        json=_legacy_payload(files, composite=True),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["summary"]["invalid_key_records"] == 6
    review = [r for r in data["results"] if r["match_status"] == "needs_review"]
    assert len(review) == 6
    assert all(r["reason_code"] == "NULL_KEY" for r in review)

    s007 = _items_for_source_record(data["results"], "academic", "S007")
    assert len(s007) == 1
    assert s007[0]["key_values"] == {"student_id": "S007", "enrollment_no": None}

    s005 = _items_for_source_record(data["results"], "hostel", None)
    assert len(s005) == 1
    assert s005[0]["key_values"] == {"student_id": None, "enrollment_no": "E005"}
    assert data["summary"]["matched_records"] == 2  # only S001 and S003 remain


def test_college_multi_primary_batch_conflict_and_coverage(
    client: TestClient, upload_storage: Path
):
    """Expected: multi-primary with academic owning name/batch.
    S003's academic batch (2024-2027) conflicts with hostel (2023-2026) ->
    FIELD_MISMATCH on batch only. Library does not carry batch and must be
    skipped (no fabricated null mismatch). 3 matched records x 2 attributes =
    6 completed comparisons; 3 invalid-key records x 2 = 6 not checked.
    """
    project_id, files = _upload_college_project(client, "College Multi Primary")
    sources = _sources(files)
    sources[1]["is_primary"] = True  # hostel is a second primary
    payload = {
        "sources": sources,
        "unified_keys": ["student_id"],
        "compare_attributes": ["name", "batch"],
        "multi_primary": True,
        "field_ownership": {"name": "academic", "batch": "academic"},
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{project_id}{MULTI_VERIFY}", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    summary = data["summary"]

    assert summary["matched_records"] == 3
    assert summary["identical_matches"] == 2
    assert summary["field_mismatches"] == 1
    assert summary["invalid_key_records"] == 3
    assert summary["attribute_comparisons_completed"] == 6
    assert summary["attributes_not_checked"] == 6
    assert summary["unmatched_source_records"] == 2   # library LIB-008 and "123"
    assert summary["unmatched_target_records"] == 4   # S004, S008, S010, "00123"

    s001 = _item(data["results"], "S001")
    assert s001["match_status"] == "identical"
    assert s001["lineage"] == {"matching_method": "primary_key", "ownership_mode": "multi_primary"}
    assert s001["unverified_fields"] == ["batch"]  # library does not carry batch

    s003 = _item(data["results"], "S003")
    assert s003["match_status"] == "field_mismatch"
    batch_diffs = [d for d in s003["field_differences"] if d["field_name"] == "batch"]
    assert len(batch_diffs) == 1
    assert batch_diffs[0]["source_field"] == "academic.batch"
    assert batch_diffs[0]["target_field"] == "hostel.batch"
    assert not any("library" in d["target_field"] for d in s003["field_differences"])


def test_college_persistent_run_matches_preview_and_persists_review_reason(
    client: TestClient, upload_storage: Path
):
    """Expected: persistent run summary == preview summary; discrepancy rows keep
    source row lineage, and invalid-key discrepancies retain NULL_KEY (not the
    generic fuzzy-review code).
    """
    project_id, files = _upload_college_project(client, "College Persistent Run")
    payload = _legacy_payload(files)

    preview = client.post(f"/api/v1/projects/{project_id}{MULTI_VERIFY}", json=payload)
    assert preview.status_code == 200, preview.text
    preview_summary = preview.json()["summary"]

    run_res = client.post(f"/api/v1/projects/{project_id}{MULTI_RUN}", json=payload)
    assert run_res.status_code == 201, run_res.text
    run = run_res.json()
    assert run["status"] == "completed"
    for field in (
        "total_source_records",
        "total_target_records",
        "matched_records",
        "identical_matches",
        "field_mismatches",
        "invalid_key_records",
        "fallback_matched_records",
        "unmatched_source_records",
        "unmatched_target_records",
        "duplicate_source_records",
        "duplicate_target_records",
        "duplicate_source_keys_count",
        "duplicate_target_keys_count",
        "total_discrepancies",
        "attribute_comparisons_completed",
        "attributes_not_checked",
    ):
        assert run["summary"][field] == preview_summary[field], field

    disc = client.get(
        f"/api/v1/projects/{project_id}/runs/{run['id']}/results",
        params={"limit": 200},
    )
    assert disc.status_code == 200, disc.text
    items = disc.json()["items"]
    assert len(items) == preview_summary["total_discrepancies"] == 8

    invalid = [r for r in items if r["match_status"] == "needs_review"]
    assert len(invalid) == 3
    assert all(r["reason_code"] == "NULL_KEY" for r in invalid)
    assert all(r["source_row_indices"] for r in invalid)

    s002 = next(r for r in items if r["key_values"].get("student_id") == "S002")
    assert s002["match_status"] == "duplicate_key_source"
    assert s002["source_row_indices"]["hostel"] == 3

    runs = client.get(f"/api/v1/projects/{project_id}/runs")
    assert runs.status_code == 200
    assert runs.json()["total"] == 1


# =============================================================================
# Template workflow: save, reversed upload order, explicit bindings, apply
# =============================================================================


def _template_config() -> dict:
    return {
        "version": 1,
        "sources": [
            {
                "alias": "academic",
                "label": "Academic Records",
                "is_primary": True,
                "key_columns": ["student_id"],
                "field_mapping": MAPPINGS["academic"],
            },
            {
                "alias": "hostel",
                "label": "Hostel Roster",
                "is_primary": False,
                "key_columns": ["student_id"],
                "field_mapping": MAPPINGS["hostel"],
                "sheet_name": "Roster",
            },
            {
                "alias": "library",
                "label": "Library Membership",
                "is_primary": False,
                "key_columns": ["student_id"],
                "field_mapping": MAPPINGS["library"],
            },
        ],
        "unified_keys": ["student_id"],
        "compare_attributes": ["name"],
        "ignore_attributes": [],
        "numeric_tolerance": 0.0,
        "ignore_whitespace": True,
        "ignore_case": False,
        "include_identical": True,
        "fallback_keys": [["enrollment_no"]],
        "multi_primary": False,
    }


def _create_template(client: TestClient, name: str, config: dict | None = None) -> dict:
    res = client.post(
        TEMPLATES,
        json={
            "name": name,
            "description": "College pilot template",
            "mode": "organization",
            "configuration": config or _template_config(),
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _assert_no_per_upload_state(value, path="root") -> None:
    forbidden = {
        "file_id",
        "source_file_id",
        "target_file_id",
        "excluded_row_indices",
        "excluded_source_rows",
        "excluded_target_rows",
        "source_row_indices",
        "source_records",
        "resolutions",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            assert key not in forbidden, f"{path}.{key} leaked per-upload state"
            _assert_no_per_upload_state(child, f"{path}.{key}")
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            _assert_no_per_upload_state(child, f"{path}[{idx}]")


def test_college_template_roundtrip_reversed_uploads_and_separate_execution(
    client: TestClient, upload_storage: Path
):
    """Expected: template stores configuration only; files uploaded as
    library -> hostel -> academic still bind explicitly by slot. Apply restores
    the saved roles, mappings, fallback and Roster worksheet, creates no run,
    and the separately submitted effective request reproduces the main summary.
    """
    project1, _ = _upload_college_project(client, "College Template Source")
    template = _create_template(client, "College Three-Source Template")
    assert template["source_count"] == 3
    _assert_no_per_upload_state(template["configuration"])

    project2, files2 = _upload_college_project(
        client, "College Template Target", reverse_order=True
    )
    # Deliberately bind in a different order than the saved slot order.
    bindings = [
        {"slot": "library", "file_id": files2["library"]["id"]},
        {"slot": "academic", "file_id": files2["academic"]["id"]},
        {"slot": "hostel", "file_id": files2["hostel"]["id"]},
    ]
    apply_res = client.post(
        f"{TEMPLATES}/{template['id']}/apply",
        json={"project_id": project2, "sources": bindings},
    )
    assert apply_res.status_code == 200, apply_res.text
    applied = apply_res.json()
    assert applied["validation_report"] == {"blocking": False, "issues": [], "warnings": []}

    effective = applied["effective_request"]
    assert [s["alias"] for s in effective["sources"]] == ["academic", "hostel", "library"]
    by_alias = {s["alias"]: s for s in effective["sources"]}
    assert by_alias["academic"]["file_id"] == files2["academic"]["id"]
    assert by_alias["hostel"]["file_id"] == files2["hostel"]["id"]
    assert by_alias["library"]["file_id"] == files2["library"]["id"]
    assert by_alias["academic"]["is_primary"] is True
    assert by_alias["hostel"]["is_primary"] is False
    assert by_alias["hostel"]["sheet_name"] == "Roster"
    assert by_alias["hostel"]["label"] == "Hostel Roster"
    assert by_alias["academic"]["field_mapping"] == MAPPINGS["academic"]
    assert effective["fallback_keys"] == [["enrollment_no"]]
    assert effective["unified_keys"] == ["student_id"]

    # Applying must not execute verification.
    runs_before = client.get(f"/api/v1/projects/{project2}/runs")
    assert runs_before.status_code == 200
    assert runs_before.json()["total"] == 0

    run_res = client.post(f"/api/v1/projects/{project2}{MULTI_RUN}", json=effective)
    assert run_res.status_code == 201, run_res.text
    run = run_res.json()
    assert run["summary"]["total_source_records"] == 12
    assert run["summary"]["matched_records"] == 5
    assert run["summary"]["fallback_matched_records"] == 2
    assert run["summary"]["invalid_key_records"] == 3
    assert run["summary"]["total_discrepancies"] == 8
    assert run["summary"]["attribute_comparisons_completed"] == 5
    assert [s["alias"] for s in run["sources"]] == ["academic", "hostel", "library"]
    assert next(s for s in run["sources"] if s["alias"] == "hostel")["sheet_name"] == "Roster"

    runs_after = client.get(f"/api/v1/projects/{project2}/runs")
    assert runs_after.json()["total"] == 1


def test_college_template_apply_blocks_missing_slots_bad_worksheets_and_columns(
    client: TestClient, upload_storage: Path
):
    """Expected blocking (422, structured issues, no run):
    - unbound/unknown slots;
    - unknown worksheet;
    - worksheet switched to Archive -> saved room_number/enrollment_no mappings gone;
    - new academic upload missing a mapped column (course);
    - a file bound from another project.
    """
    project1, files = _upload_college_project(client, "College Template Guards")
    template = _create_template(client, "College Guard Template")

    # 1) Missing slot.
    res = client.post(
        f"{TEMPLATES}/{template['id']}/apply",
        json={"project_id": project1, "sources": [{"slot": "academic", "file_id": files["academic"]["id"]}]},
    )
    assert res.status_code == 422
    report = res.json()["detail"]["validation_report"]
    assert report["blocking"] is True
    assert any("Unbound" in i["message"] for i in report["issues"])

    # 2) Unknown slot.
    res = client.post(
        f"{TEMPLATES}/{template['id']}/apply",
        json={
            "project_id": project1,
            "sources": [
                {"slot": "academic", "file_id": files["academic"]["id"]},
                {"slot": "hostel", "file_id": files["hostel"]["id"]},
                {"slot": "library", "file_id": files["library"]["id"]},
                {"slot": "ghost", "file_id": files["library"]["id"]},
            ],
        },
    )
    assert res.status_code == 422
    assert any("Unknown" in i["message"] for i in res.json()["detail"]["validation_report"]["issues"])

    # 3) Unknown worksheet on a second template.
    bad_sheet_cfg = _template_config()
    bad_sheet_cfg["sources"][1]["sheet_name"] = "NoSuchSheet"
    bad_sheet_tpl = _create_template(client, "College Unknown Sheet", bad_sheet_cfg)
    res = client.post(
        f"{TEMPLATES}/{bad_sheet_tpl['id']}/apply",
        json={
            "project_id": project1,
            "sources": [
                {"slot": "academic", "file_id": files["academic"]["id"]},
                {"slot": "hostel", "file_id": files["hostel"]["id"]},
                {"slot": "library", "file_id": files["library"]["id"]},
            ],
        },
    )
    assert res.status_code == 422
    sheet_issue = next(
        i for i in res.json()["detail"]["validation_report"]["issues"]
        if i.get("field") == "sheet_name"
    )
    assert "NoSuchSheet" in sheet_issue["message"]
    assert "Roster" in sheet_issue["message"]

    # 4) Worksheet changed to Archive -> stale mapping is rejected.
    archive_cfg = _template_config()
    archive_cfg["sources"][1]["sheet_name"] = "Archive"
    archive_tpl = _create_template(client, "College Archive Sheet", archive_cfg)
    res = client.post(
        f"{TEMPLATES}/{archive_tpl['id']}/apply",
        json={
            "project_id": project1,
            "sources": [
                {"slot": "academic", "file_id": files["academic"]["id"]},
                {"slot": "hostel", "file_id": files["hostel"]["id"]},
                {"slot": "library", "file_id": files["library"]["id"]},
            ],
        },
    )
    assert res.status_code == 422
    mapped_issue = next(
        i for i in res.json()["detail"]["validation_report"]["issues"]
        if i.get("field") == "field_mapping" and i.get("slot") == "hostel"
    )
    assert "room_number" in mapped_issue["message"]
    assert "enrollment_no" in mapped_issue["message"]

    # 5) New academic file missing a mapped column.
    project2, files2 = _upload_college_project(
        client,
        "College Template Missing Column",
        academic_csv=ACADEMIC_CSV.replace(",course,", ",program_title,"),
    )
    res = client.post(
        f"{TEMPLATES}/{template['id']}/apply",
        json={
            "project_id": project2,
            "sources": [
                {"slot": "academic", "file_id": files2["academic"]["id"]},
                {"slot": "hostel", "file_id": files2["hostel"]["id"]},
                {"slot": "library", "file_id": files2["library"]["id"]},
            ],
        },
    )
    assert res.status_code == 422
    col_issue = next(
        i for i in res.json()["detail"]["validation_report"]["issues"]
        if i.get("slot") == "academic" and i.get("field") == "field_mapping"
    )
    assert "course" in col_issue["message"]
    assert "Available columns" in col_issue["message"]

    # 6) Foreign-project file.
    res = client.post(
        f"{TEMPLATES}/{template['id']}/apply",
        json={
            "project_id": project2,
            "sources": [
                {"slot": "academic", "file_id": files["academic"]["id"]},
                {"slot": "hostel", "file_id": files2["hostel"]["id"]},
                {"slot": "library", "file_id": files2["library"]["id"]},
            ],
        },
    )
    assert res.status_code == 422
    file_issue = next(
        i for i in res.json()["detail"]["validation_report"]["issues"]
        if i.get("field") == "file_id"
    )
    assert "not found in this project" in file_issue["message"]

    for project in (project1, project2):
        assert client.get(f"/api/v1/projects/{project}/runs").json()["total"] == 0


def test_college_template_lifecycle_rename_description_replace_delete(
    client: TestClient, upload_storage: Path
):
    """Expected: details-only edits never touch configuration; configuration
    replacement never touches name/description; delete is 204 then 404; no runs.
    """
    project_id, _ = _upload_college_project(client, "College Template Lifecycle")
    template = _create_template(client, "Lifecycle Template")
    original_config = template["configuration"]

    res = client.put(
        f"{TEMPLATES}/{template['id']}",
        json={"name": "Lifecycle Renamed", "description": "Updated description"},
    )
    assert res.status_code == 200
    renamed = res.json()
    assert renamed["name"] == "Lifecycle Renamed"
    assert renamed["description"] == "Updated description"
    assert renamed["configuration"] == original_config

    new_cfg = _template_config()
    new_cfg["compare_attributes"] = ["name", "batch"]
    new_cfg["ignore_case"] = True
    res = client.put(f"{TEMPLATES}/{template['id']}", json={"configuration": new_cfg})
    assert res.status_code == 200
    replaced = res.json()
    assert replaced["configuration"] == new_cfg
    assert replaced["name"] == "Lifecycle Renamed"
    assert replaced["description"] == "Updated description"

    assert client.delete(f"{TEMPLATES}/{template['id']}").status_code == 204
    assert client.get(f"{TEMPLATES}/{template['id']}").status_code == 404
    assert client.delete(f"{TEMPLATES}/{template['id']}").status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}/runs").json()["total"] == 0


# =============================================================================
# Legacy two-source path consistency
# =============================================================================


def test_college_legacy_two_source_identity_rules(client: TestClient, upload_storage: Path):
    """Expected: the two-source path applies the same blank-key and leading-zero
    rules as multi-source. S001 matches; both blank-key rows are needs_review;
    '00123' vs '123' stays unmatched in both directions.
    """
    project_id = create_project(client, "College Legacy Two Source")
    source = upload_csv(
        client,
        project_id,
        "legacy_source.csv",
        "student_id,name\nS001,Asha Rao\n,Esha Nair\n00123,Jaya Iyer\n",
    )
    target = upload_csv(
        client,
        project_id,
        "legacy_target.csv",
        "student_id,name\nS001,Asha Rao\n,Esha Nair\n123,Jaya Iyer\n",
    )
    payload = {
        "source_file_id": source["id"],
        "target_file_id": target["id"],
        "key_columns": ["student_id"],
        "compare_columns": ["name"],
        "include_identical": True,
    }
    preview = client.post(f"/api/v1/projects/{project_id}/verify", json=payload)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    summary = data["summary"]
    assert summary["matched_records"] == 1
    assert summary["identical_matches"] == 1
    assert summary["invalid_key_records"] == 2
    assert summary["unmatched_source_records"] == 1
    assert summary["unmatched_target_records"] == 1
    assert summary["total_discrepancies"] == 4

    review = [r for r in data["results"] if r["match_status"] == "needs_review"]
    assert len(review) == 2
    assert all(r["reason_code"] == "NULL_KEY" for r in review)
    zero = next(
        r for r in data["results"]
        if (r.get("source_record") or {}).get("student_id") == "00123"
    )
    collapsed = next(
        r for r in data["results"]
        if (r.get("target_record") or {}).get("student_id") == 123
    )
    assert zero["match_status"] == "missing_in_target"
    assert collapsed["match_status"] == "missing_in_source"

    run_res = client.post(f"/api/v1/projects/{project_id}/runs", json=payload)
    assert run_res.status_code == 201, run_res.text
    run = run_res.json()
    assert run["summary"]["matched_records"] == summary["matched_records"]
    assert run["summary"]["invalid_key_records"] == 2
    assert run["summary"]["unmatched_target_records"] == 1


# =============================================================================
# Fallback ambiguity / consumed rows (direct engine, college-shaped records)
# =============================================================================


def test_college_fallback_ambiguity_and_row_consumption():
    """Expected: two library candidates sharing enrollment_no make the fallback
    ambiguous -> no fallback match and no arbitrary row reuse; a unique candidate
    is consumed once and cannot satisfy a second primary record.
    """
    from app.schemas.multisource import SourceDefinition
    from app.services.verification_engine import verify_multisource_datasets

    def _src(alias, primary, mapping):
        return SourceDefinition(
            alias=alias,
            file_id=str(uuid.uuid4()),
            is_primary=primary,
            key_columns=["student_id"],
            field_mapping=mapping,
        )

    defs = [
        _src("academic", True, {"student_id": "student_id", "enrollment_no": "enrollment_no", "name": "name"}),
        _src("library", False, {"student_id": "student_id", "enrollment_no": "enrollment_no", "name": "name"}),
    ]
    ambiguous_records = {
        "academic": [(1, {"student_id": "S-1", "enrollment_no": "E-1", "name": "Asha"})],
        "library": [
            (1, {"student_id": "L-1", "enrollment_no": "E-1", "name": "Asha"}),
            (2, {"student_id": "L-2", "enrollment_no": "E-1", "name": "Asha B"}),
        ],
    }
    summary, _, _, _, _ = verify_multisource_datasets(
        sources=defs,
        sources_records=ambiguous_records,
        unified_keys=["student_id"],
        compare_attributes=["name"],
        fallback_keys=[["enrollment_no"]],
        include_identical=True,
    )
    assert summary.fallback_matched_records == 0
    assert summary.matched_records == 0

    consumed_records = {
        "academic": [
            (1, {"student_id": "S-1", "enrollment_no": "E-9", "name": "Asha"}),
            (2, {"student_id": "S-2", "enrollment_no": "E-9", "name": "Asha"}),
        ],
        "library": [(1, {"student_id": "L-1", "enrollment_no": "E-9", "name": "Asha"})],
    }
    summary2, results2, _, _, _ = verify_multisource_datasets(
        sources=defs,
        sources_records=consumed_records,
        unified_keys=["student_id"],
        compare_attributes=["name"],
        fallback_keys=[["enrollment_no"]],
        include_identical=True,
    )
    assert summary2.fallback_matched_records == 1  # only the first primary row
    assert summary2.matched_records == 1
    matched = [r for r in results2 if r.match_status.value == "identical"]
    assert len(matched) == 1
    assert matched[0].lineage["matching_method"] == "fallback_key"


# =============================================================================
# Worksheet + sidecar isolation
# =============================================================================

SIDECAR_SHEETS = {
    "Roster": [["student_id", "amount"], ["S-1", 100], ["S-2", -50]],
    "Archive": [["student_id", "amount"], ["A-1", 200], ["A-2", -999]],
}


def _sidecar_workbook(client: TestClient, project_id: str, name: str = "sidecar.xlsx") -> dict:
    return upload_file(
        client,
        project_id,
        name,
        make_multisheet_xlsx(SIDECAR_SHEETS),
        XLSX_CONTENT_TYPE,
    )


def _quarantine(client: TestClient, project_id: str, file_id: str, worksheet: str | None):
    suffix = f"?worksheet={worksheet}" if worksheet else ""
    res = client.get(f"/api/v1/projects/{project_id}/files/{file_id}/quarantine{suffix}")
    assert res.status_code == 200, res.text
    return res.json()


def _resolve(client: TestClient, project_id: str, file_id: str, worksheet: str, row: int) -> dict:
    res = client.post(
        f"/api/v1/projects/{project_id}/files/{file_id}/quarantine/resolve?worksheet={worksheet}",
        json={"resolutions": [{"source_row_index": row, "action": "EXCLUDE"}]},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _row3(resp: dict) -> dict:
    return next(r for r in resp["records"] if r["source_row_index"] == 3)


def test_college_worksheet_selection_parses_exact_sheet_and_rejects_unknown(
    client: TestClient, upload_storage: Path
):
    """Expected: the selected Roster sheet (not the first Archive sheet) drives
    row counts; unknown names fail with the available worksheet list.
    """
    project_id = create_project(client, "College Worksheet Selection")
    hostel = upload_file(
        client, project_id, "hostel.xlsx", make_multisheet_xlsx(HOSTEL_SHEETS), XLSX_CONTENT_TYPE
    )
    copy = upload_csv(client, project_id, "roster_copy.csv", "student_id,name\nS001,Asha Rao\n")

    base_sources = [
        {
            "alias": "hostel",
            "file_id": hostel["id"],
            "is_primary": True,
            "key_columns": ["student_id"],
            "field_mapping": {"student_id": "student_id", "name": "name"},
            "sheet_name": "Roster",
        },
        {
            "alias": "copy",
            "file_id": copy["id"],
            "is_primary": False,
            "key_columns": ["student_id"],
            "field_mapping": {"student_id": "student_id", "name": "name"},
        },
    ]
    payload = {
        "sources": base_sources,
        "unified_keys": ["student_id"],
        "compare_attributes": ["name"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{project_id}{MULTI_VERIFY}", json=payload)
    assert res.status_code == 200, res.text
    assert res.json()["summary"]["total_source_records"] == 11

    archive_payload = json.loads(json.dumps(payload))
    archive_payload["sources"][0]["sheet_name"] = "Archive"
    res = client.post(f"/api/v1/projects/{project_id}{MULTI_VERIFY}", json=archive_payload)
    assert res.status_code == 200
    assert res.json()["summary"]["total_source_records"] == 2

    unknown_payload = json.loads(json.dumps(payload))
    unknown_payload["sources"][0]["sheet_name"] = "NoSuchSheet"
    res = client.post(f"/api/v1/projects/{project_id}{MULTI_VERIFY}", json=unknown_payload)
    assert res.status_code == 422
    assert "NoSuchSheet" in res.text and "Roster" in res.text


def test_college_sidecar_resolutions_are_worksheet_scoped_and_survive_switching(
    client: TestClient, upload_storage: Path
):
    """Expected: resolving Roster row 3 never excludes Archive row 3; resolving
    Archive afterwards must not destroy the Roster resolution; reprofiling either
    sheet keeps its own state. CSV files keep worksheet-less behavior.
    """
    project_id = create_project(client, "College Sidecar Isolation")
    workbook = _sidecar_workbook(client, project_id)
    file_id = workbook["id"]

    roster = _resolve(client, project_id, file_id, "Roster", 3)
    assert roster["excluded_row_indices"] == [3]

    archive = _quarantine(client, project_id, file_id, "Archive")
    assert _row3(archive)["resolution_action"] != "EXCLUDE"
    assert archive["impact_preview"]["excluded_rows_count"] == 0

    archive_resolution = _resolve(client, project_id, file_id, "Archive", 3)
    assert archive_resolution["excluded_row_indices"] == [3]

    # Returning to Roster must still apply its own resolution.
    roster_again = _quarantine(client, project_id, file_id, "Roster")
    assert _row3(roster_again)["resolution_action"] == "EXCLUDE"
    assert roster_again["impact_preview"]["excluded_rows_count"] == 1

    archive_again = _quarantine(client, project_id, file_id, "Archive")
    assert _row3(archive_again)["resolution_action"] == "EXCLUDE"
    assert archive_again["impact_preview"]["excluded_rows_count"] == 1

    # Reprofiling the same worksheet keeps its state.
    roster_reprofiled = _quarantine(client, project_id, file_id, "Roster")
    assert _row3(roster_reprofiled)["resolution_action"] == "EXCLUDE"

    # CSV behavior remains worksheet-less.
    csv_file = upload_csv(client, project_id, "amounts.csv", "student_id,amount\nC-1,100\nC-2,-50\n")
    assert any(r["source_row_index"] == 3 for r in _quarantine(client, project_id, csv_file["id"], None)["records"])
    resolved = _resolve(client, project_id, csv_file["id"], "Roster", 3)
    assert resolved["excluded_row_indices"] == [3]
    csv_again = _quarantine(client, project_id, csv_file["id"], None)
    assert _row3(csv_again)["resolution_action"] == "EXCLUDE"


def test_college_verification_uses_worksheet_specific_exclusions(
    client: TestClient, upload_storage: Path
):
    """Expected: Roster row 3 exclusion removes S-2 only from Roster. Archive
    verification still includes A-2 (no cross-worksheet leakage).
    """
    project_id = create_project(client, "College Sidecar Verification")
    workbook = _sidecar_workbook(client, project_id)
    file_id = workbook["id"]
    _resolve(client, project_id, file_id, "Roster", 3)

    def _verify(sheet: str) -> dict:
        payload = {
            "sources": [
                {
                    "alias": "x",
                    "file_id": file_id,
                    "is_primary": True,
                    "key_columns": ["student_id"],
                    "field_mapping": {"student_id": "student_id", "amount": "amount"},
                    "sheet_name": sheet,
                },
                {
                    "alias": "y",
                    "file_id": file_id,
                    "is_primary": False,
                    "key_columns": ["student_id"],
                    "field_mapping": {"student_id": "student_id", "amount": "amount"},
                    "sheet_name": sheet,
                },
            ],
            "unified_keys": ["student_id"],
            "compare_attributes": ["amount"],
            "include_identical": True,
        }
        res = client.post(f"/api/v1/projects/{project_id}{MULTI_VERIFY}", json=payload)
        assert res.status_code == 200, res.text
        return res.json()

    roster = _verify("Roster")
    assert roster["summary"]["total_source_records"] == 1
    roster_ids = {
        rec.get("student_id")
        for r in roster["results"]
        for rec in (r.get("source_records") or {}).values()
    }
    assert "S-2" not in roster_ids

    archive = _verify("Archive")
    assert archive["summary"]["total_source_records"] == 2
    archive_ids = {
        rec.get("student_id")
        for r in archive["results"]
        for rec in (r.get("source_records") or {}).values()
    }
    assert "A-2" in archive_ids


def test_college_legacy_sidecar_without_worksheet_applies_only_to_active_sheet(
    client: TestClient, upload_storage: Path
):
    """Expected compatibility rule: a pre-Batch-9 sidecar (no worksheet key)
    applies to the active sheet / no selection, never to a different sheet.
    """
    from app.services.profiling_service import get_excluded_row_indices_for_file
    from app.services.preprocessing import get_active_worksheet_name

    project_id = create_project(client, "College Legacy Sidecar")
    workbook = _sidecar_workbook(client, project_id)
    file_id = workbook["id"]
    candidates = list((settings.storage_root / project_id).glob(f"{file_id}.*"))
    assert len(candidates) == 1
    path = candidates[0].resolve()
    active = get_active_worksheet_name(path)
    assert active is not None

    sidecar = path.with_name(path.name + ".quarantine.json")
    sidecar.write_text(
        json.dumps({"file_id": file_id, "resolutions": {"3": "EXCLUDE"}, "notes": {}}),
        encoding="utf-8",
    )
    assert get_excluded_row_indices_for_file(path, active) == [3]
    assert get_excluded_row_indices_for_file(path) == [3]
    other = next(s for s in SIDECAR_SHEETS if s != active)
    assert get_excluded_row_indices_for_file(path, other) == []
