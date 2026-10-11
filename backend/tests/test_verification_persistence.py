"""Automated test suite for persistent verification runs and results."""

import io
import uuid
from pathlib import Path
from typing import Any, List

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


@pytest.fixture
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


def create_project(client: TestClient, name: str = "Persistent Verification Project") -> str:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def upload_file(client: TestClient, project_id: str, filename: str, content: bytes, content_type: str = "text/csv") -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201
    return response.json()


def test_create_and_get_persistent_verification_run(client: TestClient, upload_storage: Path):
    project_id = create_project(client, "Run Persistence Test")

    csv_1 = (
        "emp_id, full_name, salary\n"
        "101, Alice, 70000\n"
        "102, Bob, 60000\n"
        "103, Charlie, 50000\n"
    ).encode("utf-8")
    csv_2 = (
        "emp_id, full_name, salary\n"
        "101, Alice, 70000\n"
        "102, Bob, 65000\n"  # Field mismatch
        "104, Dave, 80000\n"   # Missing in source
    ).encode("utf-8")

    f1 = upload_file(client, project_id, "src.csv", csv_1)
    f2 = upload_file(client, project_id, "tgt.csv", csv_2)

    # 1. Create persistent run
    payload = {
        "source_file_id": f1["id"],
        "target_file_id": f2["id"],
        "key_columns": ["emp_id"],
    }
    create_res = client.post(f"/api/v1/projects/{project_id}/runs", json=payload)
    assert create_res.status_code == 201
    run_data = create_res.json()

    run_id = run_data["id"]
    assert run_data["project_id"] == project_id
    assert run_data["status"] == "completed"
    assert run_data["summary"]["matched_records"] == 2
    assert run_data["summary"]["identical_matches"] == 1
    assert run_data["summary"]["field_mismatches"] == 1
    assert run_data["summary"]["unmatched_source_records"] == 1  # 103
    assert run_data["summary"]["unmatched_target_records"] == 1  # 104
    assert run_data["started_at"] is not None
    assert run_data["completed_at"] is not None

    # 2. Retrieve run details
    get_res = client.get(f"/api/v1/projects/{project_id}/runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == run_id
    assert get_res.json()["status"] == "completed"


def test_list_project_runs_pagination_and_filtering(client: TestClient, upload_storage: Path):
    project_id = create_project(client, "List Runs Test")
    csv_bytes = "id,val\n1,A\n".encode("utf-8")
    f1 = upload_file(client, project_id, "f1.csv", csv_bytes)

    # Create 3 runs
    for _ in range(3):
        client.post(
            f"/api/v1/projects/{project_id}/runs",
            json={
                "source_file_id": f1["id"],
                "target_file_id": f1["id"],
                "key_columns": ["id"],
            },
        )

    # List all runs
    list_res = client.get(f"/api/v1/projects/{project_id}/runs?skip=0&limit=10")
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3

    # Test pagination
    page_res = client.get(f"/api/v1/projects/{project_id}/runs?skip=1&limit=1")
    assert page_res.status_code == 200
    assert len(page_res.json()["items"]) == 1

    # Test status filter
    filter_res = client.get(f"/api/v1/projects/{project_id}/runs?status=completed")
    assert filter_res.status_code == 200
    assert filter_res.json()["total"] == 3

    filter_failed = client.get(f"/api/v1/projects/{project_id}/runs?status=failed")
    assert filter_failed.status_code == 200
    assert filter_failed.json()["total"] == 0


def test_paginate_and_filter_run_discrepancies(client: TestClient, upload_storage: Path):
    project_id = create_project(client, "Discrepancy Results Test")
    csv_1 = (
        "id, score\n"
        "1, 100\n"
        "2, 200\n"
        "3, 300\n"
    ).encode("utf-8")
    csv_2 = (
        "id, score\n"
        "1, 100\n"
        "2, 250\n"  # field_mismatch
        "4, 400\n"  # missing_record
    ).encode("utf-8")

    f1 = upload_file(client, project_id, "d1.csv", csv_1)
    f2 = upload_file(client, project_id, "d2.csv", csv_2)

    run_res = client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "source_file_id": f1["id"],
            "target_file_id": f2["id"],
            "key_columns": ["id"],
        },
    )
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]

    # Retrieve all discrepancies
    results_res = client.get(f"/api/v1/projects/{project_id}/runs/{run_id}/results")
    assert results_res.status_code == 200
    results_data = results_res.json()
    assert results_data["total"] == 3  # id 2 mismatch, id 3 missing in target, id 4 missing in source
    assert len(results_data["items"]) == 3

    # Filter by discrepancy_category='field_mismatch'
    cat_res = client.get(f"/api/v1/projects/{project_id}/runs/{run_id}/results?discrepancy_category=field_mismatch")
    assert cat_res.status_code == 200
    assert cat_res.json()["total"] == 1
    assert str(cat_res.json()["items"][0]["key_values"]["id"]) == "2"


    # Filter by match_status='missing_in_target'
    status_res = client.get(f"/api/v1/projects/{project_id}/runs/{run_id}/results?match_status=missing_in_target")
    assert status_res.status_code == 200
    assert status_res.json()["total"] == 1
    assert str(status_res.json()["items"][0]["key_values"]["id"]) == "3"



def test_access_isolation_across_projects(client: TestClient, upload_storage: Path):
    proj_a = create_project(client, "Project Isolation A")
    proj_b = create_project(client, "Project Isolation B")

    csv_bytes = "id,name\n1,Alice\n".encode("utf-8")
    f_a = upload_file(client, proj_a, "fa.csv", csv_bytes)

    run_res = client.post(
        f"/api/v1/projects/{proj_a}/runs",
        json={
            "source_file_id": f_a["id"],
            "target_file_id": f_a["id"],
            "key_columns": ["id"],
        },
    )
    assert run_res.status_code == 201
    run_id = run_res.json()["id"]

    # Attempting to read run belonging to Project A under Project B -> 404
    cross_res = client.get(f"/api/v1/projects/{proj_b}/runs/{run_id}")
    assert cross_res.status_code == 404
    assert "Verification run not found" in cross_res.json()["detail"]

    # Attempting to query discrepancies of Project A under Project B -> 404
    cross_disc = client.get(f"/api/v1/projects/{proj_b}/runs/{run_id}/results")
    assert cross_disc.status_code == 404


def test_invalid_ids_and_nonexistent_project(client: TestClient, upload_storage: Path):
    fake_project = str(uuid.uuid4())
    fake_run = str(uuid.uuid4())

    # Nonexistent project
    res1 = client.get(f"/api/v1/projects/{fake_project}/runs")
    assert res1.status_code == 404

    # Nonexistent run
    res2 = client.get(f"/api/v1/projects/{fake_project}/runs/{fake_run}")
    assert res2.status_code == 404


def test_failure_handling_records_failed_status(client: TestClient, upload_storage: Path):
    project_id = create_project(client, "Failure Handling Project")
    csv_bytes = "id,name\n1,Alice\n".encode("utf-8")
    f1 = upload_file(client, project_id, "f1.csv", csv_bytes)

    # Invalid key column triggers failure
    payload = {
        "source_file_id": f1["id"],
        "target_file_id": f1["id"],
        "key_columns": ["invalid_col"],
    }
    fail_res = client.post(f"/api/v1/projects/{project_id}/runs", json=payload)
    assert fail_res.status_code == 422

    # Verify run was marked as failed
    list_res = client.get(f"/api/v1/projects/{project_id}/runs")
    assert list_res.status_code == 200
    runs = list_res.json()["items"]
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert "invalid_col" in (runs[0]["error_message"] or "")
