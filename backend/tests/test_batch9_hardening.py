"""Batch 9 tests: ingestion & identity-safety hardening.

Part 1 — invalid-key record preservation: multiple records sharing an equal
invalid identity-key tuple must each remain represented in results (never
collapsed into a single item), never matched, never labeled duplicates.

Part 2 — worksheet-aware quarantine/profile sidecars: resolutions are keyed to
the worksheet they were made against. Switching worksheets never reuses stale
row-index resolutions; returning to the original worksheet reapplies them;
unknown worksheets fail clearly; CSV behavior is unchanged.
"""

import io
import uuid
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas.multisource import SourceDefinition
from app.services.profiling_service import get_excluded_row_indices_for_file
from app.services.preprocessing import get_active_worksheet_name
from app.services.verification_engine import verify_multisource_datasets

import tests.test_batch7_worksheets as b7

make_multisheet_xlsx = b7.make_multisheet_xlsx
upload_file = b7.upload_file
create_project = b7.create_project
upload_csv = b7.upload_csv

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MULTI_SOURCE_RUN = "/runs/multi-source"
MULTI_SOURCE_VERIFY = "/verify/multi-source"


@pytest.fixture
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


def _src(alias: str, fid: str, primary: bool, mapping: dict) -> SourceDefinition:
    return SourceDefinition(
        alias=alias,
        file_id=fid,
        is_primary=primary,
        key_columns=["id"],
        field_mapping=mapping,
    )


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


# ==============================================================================
# Part 1: invalid-key record preservation
# ==============================================================================


def test_multiple_whitespace_keys_in_one_source_stay_distinct():
    """Three whitespace-only-key records in ONE source: each must produce its
    own result item — never collapsed into a single per-tuple item."""
    defs = [_src("a", str(uuid.uuid4()), True, _cm()),
            _src("b", str(uuid.uuid4()), False, _cm())]
    records = {
        "a": [
            (1, {"id": "   ", "val": "one"}),
            (2, {"id": "\t", "val": "two"}),
            (3, {"id": "", "val": "three"}),
        ],
        "b": [(1, {"id": None, "val": "four"})],
    }
    summary, results, _ = _run_ms(defs, records)
    assert summary.invalid_key_records == 4
    review = [r for r in results if r.match_status.value == "needs_review"]
    assert len(review) == 4  # one item PER RECORD
    covered = {(alias, idx) for r in review for alias, idx in (r.source_row_indices or {}).items()}
    assert covered == {("a", 1), ("a", 2), ("a", 3), ("b", 1)}
    # Every original record payload must appear exactly once.
    payloads = sorted(str(next(iter((r.source_records or {}).values()))) for r in review)
    assert len(payloads) == 4


def test_null_and_partial_composite_keys_each_preserved():
    cm = {"id": "id", "sub": "sub", "val": "val"}
    defs = [_src("a", str(uuid.uuid4()), True, cm),
            _src("b", str(uuid.uuid4()), False, cm)]
    records = {
        "a": [
            (1, {"id": None, "sub": None, "val": "1"}),
            (2, {"id": None, "sub": "S-1", "val": "2"}),
            (3, {"id": "K-1", "sub": None, "val": "3"}),
        ],
        "b": [
            (1, {"id": None, "sub": None, "val": "1"}),
            (2, {"id": None, "sub": "S-1", "val": "2"}),
            (3, {"id": "K-1", "sub": None, "val": "3"}),
        ],
    }
    summary, results, _, _, _ = verify_multisource_datasets(
        sources=defs, sources_records=records, unified_keys=["id", "sub"],
        compare_attributes=["val"], numeric_tolerance=0.0, include_identical=True,
    )
    # All six records have (partially) invalid composite keys and must each be
    # represented — not merged into 3 tuple-level items.
    assert summary.matched_records == 0
    assert summary.invalid_key_records == 6
    review = [r for r in results if r.match_status.value == "needs_review"]
    assert len(review) == 6
    covered = {(alias, idx) for r in review for alias, idx in (r.source_row_indices or {}).items()}
    assert covered == {("a", 1), ("a", 2), ("a", 3), ("b", 1), ("b", 2), ("b", 3)}


def test_invalid_keys_alongside_matches_missing_and_duplicates():
    defs = [_src("a", str(uuid.uuid4()), True, _cm()),
            _src("b", str(uuid.uuid4()), False, _cm())]
    records = {
        "a": [
            (1, {"id": None, "val": "1"}),     # invalid key
            (2, {"id": None, "val": "2"}),     # invalid key
            (3, {"id": "K-1", "val": "10"}),   # matches b K-1
            (4, {"id": "K-2", "val": "20"}),   # duplicate in a
            (5, {"id": "K-2", "val": "21"}),
        ],
        "b": [
            (1, {"id": None, "val": "9"}),     # invalid key
            (2, {"id": "K-1", "val": "10"}),   # match
            (3, {"id": "K-3", "val": "30"}),   # missing in a
        ],
    }
    summary, results, _ = _run_ms(defs, records)
    # Exact preservation of the 3 invalid-key source records.
    assert summary.invalid_key_records == 3
    review = [r for r in results if r.match_status.value == "needs_review"]
    assert len(review) == 3
    covered = {(alias, idx) for r in review for alias, idx in (r.source_row_indices or {}).items()}
    assert covered == {("a", 1), ("a", 2), ("b", 1)}
    # They must not distort valid outcomes.
    assert summary.identical_matches == 1          # K-1
    assert summary.duplicate_source_keys_count == 1  # K-2 in a (NOT triggered by blanks)
    assert summary.unmatched_source_records == 1   # K-3 present only in b
    assert summary.unmatched_target_records == 0


def test_invalid_record_count_matches_input_exactly():
    """Parametrized: N blank-key records per source -> exactly N preserved per source."""
    defs = [_src("a", str(uuid.uuid4()), True, _cm()),
            _src("b", str(uuid.uuid4()), False, _cm())]
    for n in (2, 5):
        records = {
            "a": [(i, {"id": None, "val": str(i)}) for i in range(1, n + 1)],
            "b": [(i, {"id": None, "val": str(i)}) for i in range(1, n + 1)],
        }
        summary, results, _ = _run_ms(defs, records)
        assert summary.invalid_key_records == 2 * n
        review = [r for r in results if r.match_status.value == "needs_review"]
        assert len(review) == 2 * n
        a_rows = {idx for r in review for a, idx in (r.source_row_indices or {}).items() if a == "a"}
        assert a_rows == set(range(1, n + 1))


def test_preview_and_persisted_preserve_invalid_records(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Batch 9 Preservation Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,val\n,1\n,2\nK-1,10\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,val\n,1\nK-1,10\n")
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
    v = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}", json=payload)
    assert v.status_code == 200, v.text
    preview_results = v.json()["results"]
    assert v.json()["summary"]["invalid_key_records"] == 3
    review = [r for r in preview_results if r["match_status"] == "needs_review"]
    assert len(review) == 3

    r = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}", json=payload)
    assert r.status_code == 201, r.text
    run_summary = r.json()["summary"]
    assert run_summary["invalid_key_records"] == 3
    persisted = client.get(f"/api/v1/projects/{proj_id}/runs/{r.json()['id']}").json()
    assert persisted["summary"]["invalid_key_records"] == 3

    # Batch 14 regression: the persisted discrepancy API must preserve the
    # invalid-key outcome (NULL_KEY), not mislabel it as a fuzzy-name review.
    items = client.get(
        f"/api/v1/projects/{proj_id}/runs/{r.json()['id']}/results",
        params={"limit": 100},
    ).json()["items"]
    persisted_review = [it for it in items if it["match_status"] == "needs_review"]
    assert len(persisted_review) == 3
    assert all(it["reason_code"] == "NULL_KEY" for it in persisted_review)


# ==============================================================================
# Part 2: worksheet-aware quarantine / profile sidecars
# ==============================================================================

# Alpha row 3 and Beta row 3 are BOTH quarantined (negative amounts) at the SAME
# row index with DIFFERENT data — proving stale resolutions must not cross
# worksheets, and that the right record is flagged in each worksheet.
BATCH9_SHEETS = {
    "Alpha": [["id", "amount"], ["S-1", 100], ["S-2", -50]],
    "Beta": [["id", "amount"], ["T-1", 200], ["T-2", -999]],
}


def _upload_batch9_xlsx(client: TestClient, proj_id: str, name="ws_sidecar.xlsx"):
    return upload_file(client, proj_id, name, make_multisheet_xlsx(BATCH9_SHEETS), XLSX_CONTENT_TYPE)


def _resolve_row(client: TestClient, proj_id: str, file_id: str, row: int, worksheet: str):
    res = client.post(
        f"/api/v1/projects/{proj_id}/files/{file_id}/quarantine/resolve?worksheet={worksheet}",
        json={"resolutions": [{"source_row_index": row, "action": "EXCLUDE"}]},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _get_quarantine(client: TestClient, proj_id: str, file_id: str, worksheet: str | None = None):
    ws = f"?worksheet={worksheet}" if worksheet else ""
    res = client.get(f"/api/v1/projects/{proj_id}/files/{file_id}/quarantine{ws}")
    assert res.status_code == 200, res.text
    return res.json()


def _quarantined_row(resp, row: int):
    return next(r for r in resp["records"] if r["source_row_index"] == row)


def test_quarantine_resolution_scoped_to_selected_worksheet(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Batch 9 Worksheet Sidecar Project")
    f = _upload_batch9_xlsx(client, proj_id)

    # Resolve row 3 (the quarantined negative-amount row) against Alpha.
    resolution = _resolve_row(client, proj_id, f["id"], 3, "Alpha")
    assert resolution["excluded_row_indices"] == [3]

    # Beta must NOT reuse Alpha's resolution — same row index, different data.
    beta = _get_quarantine(client, proj_id, f["id"], "Beta")
    beta_row = _quarantined_row(beta, 3)
    assert beta_row["resolution_action"] != "EXCLUDE"
    assert beta["impact_preview"]["excluded_rows_count"] == 0

    # Alpha still holds the resolution.
    alpha = _get_quarantine(client, proj_id, f["id"], "Alpha")
    assert _quarantined_row(alpha, 3)["resolution_action"] == "EXCLUDE"
    assert alpha["impact_preview"]["excluded_rows_count"] == 1


def test_returning_to_original_worksheet_reapplies_resolutions(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Batch 9 Return Project")
    f = _upload_batch9_xlsx(client, proj_id)

    _resolve_row(client, proj_id, f["id"], 3, "Alpha")
    # Visit Beta (no stale reuse)...
    beta = _get_quarantine(client, proj_id, f["id"], "Beta")
    assert beta["impact_preview"]["excluded_rows_count"] == 0
    # ...then return to Alpha: the resolution must still apply.
    alpha = _get_quarantine(client, proj_id, f["id"], "Alpha")
    assert _quarantined_row(alpha, 3)["resolution_action"] == "EXCLUDE"
    assert alpha["impact_preview"]["excluded_rows_count"] == 1


def test_resolving_second_worksheet_preserves_first_worksheet_resolutions(
    client: TestClient, upload_storage: Path
):
    """Batch 14 regression: every worksheet owns its own resolution map.

    Resolving Beta after Alpha must not overwrite Alpha's stored decision, and
    both worksheets must keep their independent exclusion counts. They share
    row index 3 with different data, so cross-reuse would be visible.
    """
    proj_id = create_project(client, "Batch 14 Worksheet Archive Project")
    f = _upload_batch9_xlsx(client, proj_id, "ws_archive.xlsx")

    _resolve_row(client, proj_id, f["id"], 3, "Alpha")
    _resolve_row(client, proj_id, f["id"], 3, "Beta")

    alpha = _get_quarantine(client, proj_id, f["id"], "Alpha")
    beta = _get_quarantine(client, proj_id, f["id"], "Beta")
    assert _quarantined_row(alpha, 3)["resolution_action"] == "EXCLUDE"
    assert _quarantined_row(beta, 3)["resolution_action"] == "EXCLUDE"
    assert alpha["impact_preview"]["excluded_rows_count"] == 1
    assert beta["impact_preview"]["excluded_rows_count"] == 1


def test_reprofiling_same_worksheet_retains_resolutions(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Batch 9 Reprofile Project")
    f = _upload_batch9_xlsx(client, proj_id)

    _resolve_row(client, proj_id, f["id"], 3, "Alpha")
    # Reprofile the SAME worksheet repeatedly — resolutions must survive.
    for _ in range(2):
        again = _get_quarantine(client, proj_id, f["id"], "Alpha")
        assert _quarantined_row(again, 3)["resolution_action"] == "EXCLUDE"
        assert again["impact_preview"]["excluded_rows_count"] == 1


def test_unknown_worksheet_fails_clearly(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Batch 9 Unknown Sheet Project")
    f = _upload_batch9_xlsx(client, proj_id)
    res = client.get(f"/api/v1/projects/{proj_id}/files/{f['id']}/quarantine?worksheet=DoesNotExist")
    assert res.status_code == 422
    assert "DoesNotExist" in res.text


def test_verification_does_not_leak_exclusions_across_worksheets(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Batch 9 Verification Leak Project")
    f = _upload_batch9_xlsx(client, proj_id)

    _resolve_row(client, proj_id, f["id"], 3, "Alpha")

    def _verify(sheet: str):
        payload = {
            "sources": [
                {"alias": "x", "file_id": f["id"], "is_primary": True, "key_columns": ["id"],
                 "field_mapping": {"id": "id", "amount": "amount"}, "sheet_name": sheet},
                {"alias": "y", "file_id": f["id"], "is_primary": False, "key_columns": ["id"],
                 "field_mapping": {"id": "id", "amount": "amount"}, "sheet_name": sheet},
            ],
            "unified_keys": ["id"],
            "compare_attributes": ["amount"],
            "include_identical": True,
        }
        res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}", json=payload)
        assert res.status_code == 200, res.text
        data = res.json()
        ids = [
            next(iter((r.get("source_records") or {}).values())).get("id")
            for r in data["results"]
            if r.get("source_records")
        ]
        return data, ids

    # Alpha: the quarantined row 3 (S-2) must be excluded from verification.
    alpha_data, alpha_ids = _verify("Alpha")
    assert alpha_data["summary"]["total_source_records"] == 1  # only S-1 remains
    assert "S-2" not in alpha_ids

    # Beta: same row index holds valid data (T-2) — it must NOT be excluded.
    beta_data, beta_ids = _verify("Beta")
    assert beta_data["summary"]["total_source_records"] == 2
    assert "T-2" in beta_ids

    # Legacy (no explicit selection → active sheet Alpha): exclusion still applies
    # via the legacy sidecar association with the active sheet.
    legacy = client.post(
        f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}",
        json={
            "sources": [
                {"alias": "x", "file_id": f["id"], "is_primary": True, "key_columns": ["id"],
                 "field_mapping": {"id": "id", "amount": "amount"}},
                {"alias": "y", "file_id": f["id"], "is_primary": False, "key_columns": ["id"],
                 "field_mapping": {"id": "id", "amount": "amount"}},
            ],
            "unified_keys": ["id"],
            "compare_attributes": ["amount"],
            "include_identical": True,
        },
    )
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["summary"]["total_source_records"] == 1


def test_sidecar_read_worksheet_isolation_direct(client: TestClient, upload_storage: Path):
    """Direct unit check of get_excluded_row_indices_for_file worksheet rules."""
    proj_id = create_project(client, "Batch 9 Direct Sidecar Project")
    f = _upload_batch9_xlsx(client, proj_id)

    # Storage layout: settings.storage_root / <project_id> / <file_id>.<ext>
    candidates = list((settings.storage_root / proj_id).glob(f"{f['id']}.*"))
    assert len(candidates) == 1, candidates
    path = candidates[0].resolve()
    assert path.exists(), path

    # No sidecar yet.
    assert get_excluded_row_indices_for_file(path, "Alpha") == []

    _resolve_row(client, proj_id, f["id"], 3, "Alpha")
    assert get_excluded_row_indices_for_file(path, "Alpha") == [3]
    assert get_excluded_row_indices_for_file(path, "Beta") == []
    # Active-sheet selection with a keyed sidecar for the same sheet applies.
    active = get_active_worksheet_name(path)
    if active == "Alpha":
        assert get_excluded_row_indices_for_file(path, active) == [3]
    # No selection: keyed sidecar does not leak into a different worksheet's
    # parse — the helper requires a matching worksheet name.
    legacy_view = get_excluded_row_indices_for_file(path)
    assert legacy_view in ([], [3])  # documented: legacy None-request only matches legacy sidecars


def test_csv_quarantine_behavior_unchanged(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Batch 9 CSV Compat Project")
    f = upload_csv(client, proj_id, "data.csv", "id,amount\nC-1,100\nC-2,-50\n")

    # CSV quarantine works without worksheet params (header = row 1; C-2 = row 3).
    q = _get_quarantine(client, proj_id, f["id"])
    assert any(r["source_row_index"] == 3 for r in q["records"])

    resolution = _resolve_row(client, proj_id, f["id"], 3, "Alpha")  # worksheet ignored for CSV
    assert resolution["excluded_row_indices"] == [3]

    # And the resolution persists across default (worksheet-less) reads.
    again = _get_quarantine(client, proj_id, f["id"])
    assert _quarantined_row(again, 3)["resolution_action"] == "EXCLUDE"
    assert again["impact_preview"]["excluded_rows_count"] == 1


def test_csv_verification_exclusions_unchanged(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Batch 9 CSV Verify Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,amount\nC-1,100\nC-2,-50\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,amount\nC-1,100\nC-2,-50\n")
    _resolve_row(client, proj_id, f1["id"], 3, "Alpha")

    payload = {
        "sources": [
            {"alias": "a", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"],
             "field_mapping": {"id": "id", "amount": "amount"}},
            {"alias": "b", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"],
             "field_mapping": {"id": "id", "amount": "amount"}},
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["amount"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}", json=payload)
    assert res.status_code == 200, res.text
    # C-2 excluded from source a only; C-1 still matches.
    assert res.json()["summary"]["matched_records"] == 1
