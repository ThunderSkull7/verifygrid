from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


@pytest.fixture
def upload_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "storage_root", root)
    return root


def create_project(client: TestClient) -> str:
    response = client.post("/api/v1/projects", json={"name": "Scholarship verification"})
    assert response.status_code == 201
    return response.json()["id"]


def test_upload_csv_for_project(client: TestClient, upload_storage: Path):
    project_id = create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": ("applicants.csv", b"roll_no,name\n1,Ada\n", "text/csv")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["project_id"] == project_id
    assert data["original_filename"] == "applicants.csv"
    assert data["file_type"] == "csv"
    assert data["file_size"] == len(b"roll_no,name\n1,Ada\n")
    assert data["status"] == "uploaded"
    assert list((upload_storage / project_id).glob("*.csv"))


def test_upload_xlsx_for_project(client: TestClient, upload_storage: Path):
    project_id = create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": ("fees.XLSX", b"xlsx-placeholder", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 201
    assert response.json()["file_type"] == "xlsx"
    assert list((upload_storage / project_id).glob("*.xlsx"))


def test_rejects_unsupported_upload(client: TestClient, upload_storage: Path):
    project_id = create_project(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/files",
        files={"file": ("records.pdf", b"not supported", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Only CSV and XLSX files are supported."
    assert not upload_storage.exists()


def test_upload_to_unknown_project_returns_404(client: TestClient, upload_storage: Path):
    response = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/files",
        files={"file": ("records.csv", b"id\n1\n", "text/csv")},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found."
    assert not upload_storage.exists()
