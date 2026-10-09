import uuid
from fastapi.testclient import TestClient


def test_create_project_success(client: TestClient):
    """
    Test creating a project with valid name and description.
    """
    payload = {
        "name": "Audit Run 2026",
        "description": "Financial reconciliation dataset",
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    # Validate UUID format
    project_id = uuid.UUID(data["id"])
    assert project_id is not None
    assert data["name"] == "Audit Run 2026"
    assert data["description"] == "Financial reconciliation dataset"
    assert data["owner_id"] is None
    assert "created_at" in data
    assert "updated_at" in data


def test_create_project_without_description(client: TestClient):
    """
    Test creating a project with only the required name field.
    """
    payload = {"name": "Minimal Project"}
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Minimal Project"
    assert data["description"] is None
    assert data["owner_id"] is None


def test_create_project_validation_missing_name(client: TestClient):
    """
    Ensure 422 Unprocessable Entity when name is omitted.
    """
    payload = {"description": "Missing name field"}
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 422


def test_create_project_validation_empty_name(client: TestClient):
    """
    Ensure 422 Unprocessable Entity when name is an empty string.
    """
    payload = {"name": "", "description": "Empty name"}
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 422


def test_create_project_ignores_injected_owner_id(client: TestClient):
    """
    Security check: verify that client-injected owner_id values are not used.
    In this development stage prior to authentication, owner_id must remain None.
    """
    fake_user_id = str(uuid.uuid4())
    payload = {
        "name": "Injection Test Project",
        "owner_id": fake_user_id,
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["owner_id"] is None


def test_list_projects(client: TestClient):
    """
    Test listing projects and verifying ordering and pagination.
    """
    # Create two projects
    p1 = client.post("/api/v1/projects", json={"name": "Project Alpha"}).json()
    p2 = client.post("/api/v1/projects", json={"name": "Project Beta"}).json()

    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 2

    # Verify project IDs are present
    ids = [item["id"] for item in items]
    assert p1["id"] in ids
    assert p2["id"] in ids


def test_list_projects_pagination(client: TestClient):
    """
    Test pagination using skip and limit query parameters.
    """
    # Create projects
    for i in range(5):
        client.post("/api/v1/projects", json={"name": f"Paging Test {i}"})

    response = client.get("/api/v1/projects?skip=0&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Verify invalid pagination params return 422
    invalid_resp = client.get("/api/v1/projects?limit=-1")
    assert invalid_resp.status_code == 422
