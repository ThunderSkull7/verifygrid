"""Unit and integration tests for Multi-Source Ingestion & Reconciliation Wizard (Batch 3)."""

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas.multisource import SourceDefinition, MultiSourceVerificationRequest
from app.schemas.result import MatchStatus
from app.services.profiling_service import (
    discover_multisource_candidate_keys,
)
from app.services.verification_engine import (
    verify_multisource_datasets,
)


@pytest.fixture
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


def create_project(client: TestClient, name: str = "MultiSource Test Project") -> str:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def upload_csv(client: TestClient, project_id: str, filename: str, csv_data: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": (filename, io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 201
    return response.json()


# ==============================================================================
# Unit Tests: Candidate Key Discovery & Overlap Scoring
# ==============================================================================


def test_discover_multisource_candidate_keys_single():
    """Verify single candidate key discovery with uniqueness, low nulls, and value overlap."""
    source_records = {
        "erp": [
            {"txn_id": "TX100", "amount": "100.00", "branch": "North"},
            {"txn_id": "TX101", "amount": "250.50", "branch": "South"},
            {"txn_id": "TX102", "amount": "300.00", "branch": "North"},
        ],
        "bank": [
            {"txn_id": "TX100", "amount": "100.00", "branch": "North"},
            {"txn_id": "TX101", "amount": "250.50", "branch": "South"},
            {"txn_id": "TX102", "amount": "300.00", "branch": "North"},
        ],
        "gateway": [
            {"txn_id": "TX100", "amount": "100.00", "branch": "North"},
            {"txn_id": "TX101", "amount": "250.50", "branch": "South"},
            {"txn_id": "TX103", "amount": "999.00", "branch": "East"},
        ],
    }

    recs = discover_multisource_candidate_keys(source_records)
    assert len(recs) > 0

    top_rec = recs[0]
    assert top_rec.key_name == "txn_id"
    assert top_rec.is_composite is False
    assert top_rec.uniqueness_by_source["erp"] == 1.0
    assert top_rec.null_rate_by_source["erp"] == 0.0
    assert top_rec.overlap_score > 0.6
    assert top_rec.overall_score >= 0.8


def test_discover_multisource_composite_keys():
    """Verify composite candidate key discovery when single columns have collisions."""
    # Individually, 'branch' and 'date' have duplicate values, but ('branch', 'date') is unique
    source_records = {
        "erp": [
            {"branch": "NYC", "date": "2026-01-01", "amount": "100"},
            {"branch": "NYC", "date": "2026-01-02", "amount": "200"},
            {"branch": "LON", "date": "2026-01-01", "amount": "300"},
            {"branch": "LON", "date": "2026-01-02", "amount": "400"},
        ],
        "bank": [
            {"branch": "NYC", "date": "2026-01-01", "amount": "100"},
            {"branch": "NYC", "date": "2026-01-02", "amount": "200"},
            {"branch": "LON", "date": "2026-01-01", "amount": "300"},
            {"branch": "LON", "date": "2026-01-02", "amount": "400"},
        ],
    }

    recs = discover_multisource_candidate_keys(source_records)
    composite_recs = [r for r in recs if r.is_composite]
    assert len(composite_recs) > 0

    best_composite = composite_recs[0]
    assert "branch" in best_composite.key_name
    assert "date" in best_composite.key_name
    assert best_composite.uniqueness_by_source["erp"] == 1.0
    assert best_composite.overlap_score == 1.0


# ==============================================================================
# Unit Tests: Multi-Source Engine & Lineage Tracking
# ==============================================================================


def test_verify_multisource_datasets_3_way():
    """Verify multi-source reconciliation logic with 3 distinct sources."""
    sources_data = {
        "erp": [
            (1, {"id": "TX-1", "amount": "100.00", "status": "COMPLETED"}),
            (2, {"id": "TX-2", "amount": "200.00", "status": "COMPLETED"}),
            (3, {"id": "TX-3", "amount": "300.00", "status": "PENDING"}),
            (4, {"id": "TX-4", "amount": "400.00", "status": "COMPLETED"}),
        ],
        "bank": [
            (1, {"id": "TX-1", "amount": "100.00", "status": "COMPLETED"}),
            (2, {"id": "TX-2", "amount": "205.00", "status": "COMPLETED"}),  # Discrepancy
            (3, {"id": "TX-3", "amount": "300.00", "status": "PENDING"}),
            # TX-4 is missing in bank
        ],
        "gateway": [
            (1, {"id": "TX-1", "amount": "100.00", "status": "COMPLETED"}),
            (2, {"id": "TX-2", "amount": "200.00", "status": "COMPLETED"}),
            (3, {"id": "TX-3", "amount": "300.00", "status": "PENDING"}),
            (4, {"id": "TX-4", "amount": "400.00", "status": "COMPLETED"}),
            (5, {"id": "TX-5", "amount": "500.00", "status": "COMPLETED"}),  # Missing in primary (erp)
        ],
    }

    source_defs = [
        SourceDefinition(alias="erp", file_id="00000000-0000-0000-0000-000000000001", is_primary=True, key_columns=["id"]),
        SourceDefinition(alias="bank", file_id="00000000-0000-0000-0000-000000000002", is_primary=False, key_columns=["id"]),
        SourceDefinition(alias="gateway", file_id="00000000-0000-0000-0000-000000000003", is_primary=False, key_columns=["id"]),
    ]

    summary, results, discrepancies, records_by_src, missing_by_src = verify_multisource_datasets(
        sources=source_defs,
        sources_records=sources_data,
        unified_keys=["id"],
        compare_attributes=["amount", "status"],
        numeric_tolerance=0.0,
        include_identical=True,
    )

    assert summary.total_source_records == 4
    assert summary.identical_matches == 2  # TX-1, TX-3
    assert summary.field_mismatches == 1  # TX-2 (bank amount is 205.00)
    assert summary.unmatched_source_records == 1  # TX-4 missing in bank
    assert summary.unmatched_target_records == 1  # TX-5 present only in gateway

    # Check row lineage tracking for TX-1
    tx1_item = next(it for it in results if it.key_values.get("id") == "TX-1")
    assert tx1_item.source_row_indices == {"erp": 1, "bank": 1, "gateway": 1}
    assert tx1_item.match_status == MatchStatus.IDENTICAL
    assert len(tx1_item.field_differences or []) == 0

    # Check field difference for TX-2
    tx2_item = next(it for it in results if it.key_values.get("id") == "TX-2")
    assert tx2_item.match_status == MatchStatus.FIELD_MISMATCH
    assert tx2_item.source_row_indices == {"erp": 2, "bank": 2, "gateway": 2}
    diff_amount = next(d for d in tx2_item.field_differences if d.field_name == "amount")
    assert str(diff_amount.source_value) == "200.00"
    assert str(diff_amount.target_value) == "205.00"  # from bank

    # Check missing in bank for TX-4
    tx4_item = next(it for it in results if it.key_values.get("id") == "TX-4")
    assert tx4_item.match_status == MatchStatus.MISSING_IN_TARGET
    assert "bank" in (tx4_item.missing_in_sources or [])
    assert tx4_item.source_row_indices == {"erp": 4, "gateway": 4, "bank": None}

    # Check missing in primary for TX-5
    tx5_item = next(it for it in results if it.key_values.get("id") == "TX-5")
    assert tx5_item.match_status == MatchStatus.MISSING_IN_SOURCE
    assert tx5_item.source_row_indices == {"erp": None, "bank": None, "gateway": 5}


def test_verify_multisource_tolerance_and_status_rules():
    """Verify numeric tolerance and status equivalence across multiple sources."""
    sources_data = {
        "erp": [
            (1, {"id": "INV-1", "amount": "100.00", "state": "PAID"}),
        ],
        "bank": [
            (1, {"id": "INV-1", "amount": "100.02", "state": "SETTLED"}),
        ],
        "pos": [
            (1, {"id": "INV-1", "amount": "99.98", "state": "SUCCESS"}),
        ],
    }

    source_defs = [
        SourceDefinition(alias="erp", file_id="00000000-0000-0000-0000-000000000001", is_primary=True, key_columns=["id"]),
        SourceDefinition(alias="bank", file_id="00000000-0000-0000-0000-000000000002", is_primary=False, key_columns=["id"]),
        SourceDefinition(alias="pos", file_id="00000000-0000-0000-0000-000000000003", is_primary=False, key_columns=["id"]),
    ]

    summary, results, _, _, _ = verify_multisource_datasets(
        sources=source_defs,
        sources_records=sources_data,
        unified_keys=["id"],
        compare_attributes=["amount", "state"],
        numeric_tolerance=0.05,
        status_rules={"PAID": ["SETTLED", "SUCCESS"], "SETTLED": ["PAID", "SUCCESS"]},
        include_identical=True,
    )

    assert summary.identical_matches == 1
    assert summary.field_mismatches == 0
    assert results[0].match_status == MatchStatus.IDENTICAL


# ==============================================================================
# Integration Tests: Endpoints & Persistence
# ==============================================================================


def test_multisource_candidate_key_recommend_endpoint(
    client: TestClient, upload_storage: Path
):
    """Test candidate key recommendation API across 3 uploaded files."""
    proj_id = create_project(client, "Recommend Keys Project")

    f1 = upload_csv(
        client,
        proj_id,
        "erp.csv",
        "order_id,total,status\nORD-1,100,NEW\nORD-2,200,PAID\nORD-3,300,PAID\n",
    )
    f2 = upload_csv(
        client,
        proj_id,
        "bank.csv",
        "order_id,total,status\nORD-1,100,NEW\nORD-2,200,PAID\nORD-3,300,PAID\n",
    )
    f3 = upload_csv(
        client,
        proj_id,
        "gateway.csv",
        "order_id,total,status\nORD-1,100,NEW\nORD-2,200,PAID\nORD-4,400,PAID\n",
    )

    rec_res = client.post(
        f"/api/v1/projects/{proj_id}/keys/recommend",
        json={
            "file_ids": [f1["id"], f2["id"], f3["id"]],
            "aliases": ["erp", "bank", "gateway"],
        },
    )
    assert rec_res.status_code == 200
    data = rec_res.json()
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0

    top = data["recommendations"][0]
    assert top["key_name"] == "order_id"
    assert top["uniqueness_by_source"]["erp"] == 1.0
    assert top["overall_score"] > 0.7


def test_multisource_verify_endpoint(
    client: TestClient, upload_storage: Path
):
    """Test POST /api/v1/projects/{id}/verify/multi-source dry-run endpoint."""
    proj_id = create_project(client, "MultiSource Verify Project")

    f1 = upload_csv(
        client,
        proj_id,
        "src1.csv",
        "ref_num,amount,currency\nREF1,50.00,USD\nREF2,75.00,USD\n",
    )
    f2 = upload_csv(
        client,
        proj_id,
        "src2.csv",
        "ref_num,amount,currency\nREF1,50.00,USD\nREF2,79.00,USD\n",
    )
    f3 = upload_csv(
        client,
        proj_id,
        "src3.csv",
        "ref_num,amount,currency\nREF1,50.00,USD\nREF2,75.00,USD\n",
    )

    res = client.post(
        f"/api/v1/projects/{proj_id}/verify/multi-source",
        json={
            "sources": [
                {"alias": "src1", "file_id": f1["id"], "is_primary": True, "key_columns": ["ref_num"]},
                {"alias": "src2", "file_id": f2["id"], "is_primary": False, "key_columns": ["ref_num"]},
                {"alias": "src3", "file_id": f3["id"], "is_primary": False, "key_columns": ["ref_num"]},
            ],
            "unified_keys": ["ref_num"],
            "compare_attributes": ["amount", "currency"],
            "numeric_tolerance": 0.0,
            "include_identical": True,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "summary" in body
    assert "results" in body
    assert body["summary"]["matched_records"] == 2
    assert body["summary"]["field_mismatches"] == 1

    # Check lineage in results
    ref1 = next(it for it in body["results"] if it["key_values"].get("ref_num") == "REF1")
    assert ref1["source_row_indices"] == {"src1": 2, "src2": 2, "src3": 2}
    assert ref1["match_status"] == "identical"


def test_multisource_runs_endpoint_persistence(
    client: TestClient, upload_storage: Path
):
    """Test POST /api/v1/projects/{id}/runs/multi-source persistence with full lineage."""
    proj_id = create_project(client, "MultiSource Persistent Run Project")

    f1 = upload_csv(
        client,
        proj_id,
        "erp.csv",
        "sku,stock\nSKU-A,10\nSKU-B,20\n",
    )
    f2 = upload_csv(
        client,
        proj_id,
        "warehouse.csv",
        "sku,stock\nSKU-A,10\nSKU-B,25\n",
    )
    f3 = upload_csv(
        client,
        proj_id,
        "store.csv",
        "sku,stock\nSKU-A,10\nSKU-C,30\n",
    )

    run_res = client.post(
        f"/api/v1/projects/{proj_id}/runs/multi-source",
        json={
            "sources": [
                {"alias": "erp", "file_id": f1["id"], "is_primary": True, "key_columns": ["sku"]},
                {"alias": "warehouse", "file_id": f2["id"], "is_primary": False, "key_columns": ["sku"]},
                {"alias": "store", "file_id": f3["id"], "is_primary": False, "key_columns": ["sku"]},
            ],
            "unified_keys": ["sku"],
            "compare_attributes": ["stock"],
            "include_identical": True,
        },
    )
    assert run_res.status_code == 201
    run_data = run_res.json()
    assert run_data["status"] == "completed"
    assert "sources" in run_data
    assert len(run_data["sources"]) == 3
    assert run_data["summary"]["total_source_records"] == 2

    # Fetch discrepancies from GET /runs/{run_id}/results
    disc_res = client.get(f"/api/v1/projects/{proj_id}/runs/{run_data['id']}/results")
    assert disc_res.status_code == 200
    discrepancies_data = disc_res.json()
    items = discrepancies_data["items"]
    assert len(items) >= 2  # SKU-B (diff/missing in store) and SKU-C (unmatched)
    for disc in items:
        assert "source_row_indices" in disc
        assert disc["source_row_indices"] is not None

    # Fetch run via GET /runs/{run_id} to verify database persistence
    get_res = client.get(f"/api/v1/projects/{proj_id}/runs/{run_data['id']}")
    assert get_res.status_code == 200
    persisted = get_res.json()
    assert persisted["id"] == run_data["id"]
    assert persisted["sources"] == run_data["sources"]
    assert persisted["summary"]["total_source_records"] == 2


def test_backward_compatibility_two_file_endpoints(
    client: TestClient, upload_storage: Path
):
    """Verify that existing 2-file /verify and /runs endpoints continue to function cleanly."""
    proj_id = create_project(client, "Backward Compat Project")

    f1 = upload_csv(
        client,
        proj_id,
        "file1.csv",
        "id,val\n1,10\n2,20\n",
    )
    f2 = upload_csv(
        client,
        proj_id,
        "file2.csv",
        "id,val\n1,10\n2,25\n",
    )

    # 1. Existing 2-file dry-run /verify
    verify_res = client.post(
        f"/api/v1/projects/{proj_id}/verify",
        json={
            "source_file_id": f1["id"],
            "target_file_id": f2["id"],
            "key_columns": ["id"],
            "numeric_tolerance": 0.0,
            "include_identical": True,
        },
    )
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["summary"]["total_source_records"] == 2
    assert v_data["summary"]["field_mismatches"] == 1

    # 2. Existing 2-file persistent /runs
    run_res = client.post(
        f"/api/v1/projects/{proj_id}/runs",
        json={
            "source_file_id": f1["id"],
            "target_file_id": f2["id"],
            "key_columns": ["id"],
            "numeric_tolerance": 0.0,
        },
    )
    assert run_res.status_code == 201
    r_data = run_res.json()
    assert r_data["source_file_id"] == f1["id"]
    assert r_data["target_file_id"] == f2["id"]
    assert r_data["status"] == "completed"
