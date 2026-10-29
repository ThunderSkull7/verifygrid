"""Batch 13 tests: template workflow usability.

Covers explicit per-slot file binding (bindings are suggestions; the backend
re-validates them), missing/duplicate bindings, structured blocking feedback,
template rename/description edits, configuration replacement, delete, and
separation of organization templates from financial mode.

The template panel's confirm dialogs are frontend behaviour; the backend side
(update/delete/ownership/validation) is what these tests exercise.
"""

import uuid

from fastapi.testclient import TestClient

import tests.test_batch7_worksheets as b7

make_multisheet_xlsx = b7.make_multisheet_xlsx
upload_file = b7.upload_file
create_project = b7.create_project
upload_csv = b7.upload_csv

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TEMPLATES = "/api/v1/templates"


def _config(sources=None, **overrides) -> dict:
    base = {
        "version": 1,
        "sources": sources or [
            {
                "alias": "sis",
                "label": "Academic Records",
                "is_primary": True,
                "key_columns": ["student_id"],
                "field_mapping": {"student_id": "student_id", "gpa": "gpa"},
            },
            {
                "alias": "registrar",
                "is_primary": False,
                "key_columns": ["student_id"],
                "field_mapping": {"student_id": "student_id", "gpa": "gpa"},
            },
        ],
        "unified_keys": ["student_id"],
        "compare_attributes": ["gpa"],
    }
    base.update(overrides)
    return base


def _payload(name="Workflow Template", config=None, description=None, **kw) -> dict:
    payload = {
        "name": name,
        "mode": "organization",
        "configuration": config or _config(),
    }
    if description is not None:
        payload["description"] = description
    payload.update(kw)
    return payload


def _create_template(client: TestClient, name="Workflow Template", description=None) -> dict:
    res = client.post(TEMPLATES, json=_payload(name=name, description=description))
    assert res.status_code == 201, res.text
    return res.json()


def _csv(student_id: str, gpa: str) -> str:
    return f"student_id,gpa\n{student_id},{gpa}\n"


def _apply(client: TestClient, template_id: str, project_id: str, bindings: dict):
    return client.post(
        f"{TEMPLATES}/{template_id}/apply",
        json={
            "project_id": project_id,
            "sources": [{"slot": slot, "file_id": fid} for slot, fid in bindings.items()],
        },
    )


# ==============================================================================
# Explicit per-slot binding
# ==============================================================================


def test_explicit_bindings_map_each_slot_to_the_chosen_file(client: TestClient):
    """Bindings — not upload order — decide which file fills each template slot."""
    proj = create_project(client, "Bindings Project")
    f1 = upload_csv(client, proj, "first.csv", _csv("S-1", "3.5"))
    f2 = upload_csv(client, proj, "second.csv", _csv("S-2", "3.8"))
    tpl = _create_template(client, "Explicit Bindings")

    # Deliberately reversed relative to upload order: sis -> second, registrar -> first
    res = _apply(client, tpl["id"], proj, {"sis": f2["id"], "registrar": f1["id"]})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["validation_report"]["blocking"] is False
    sources = data["effective_request"]["sources"]
    by_alias = {s["alias"]: s["file_id"] for s in sources}
    assert by_alias["sis"] == f2["id"]
    assert by_alias["registrar"] == f1["id"]
    # Apply must never execute verification (no run created as a side effect).
    runs = client.get(f"/api/v1/projects/{proj}/runs")
    assert runs.status_code == 200
    assert runs.json()["total"] == 0


def test_apply_blocks_when_a_required_slot_is_unassigned(client: TestClient):
    proj = create_project(client, "Unassigned Project")
    f1 = upload_csv(client, proj, "only.csv", _csv("S-1", "3.5"))
    tpl = _create_template(client, "Missing Binding")

    res = _apply(client, tpl["id"], proj, {"sis": f1["id"]})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["validation_report"]["blocking"] is True
    messages = " ".join(i["message"] for i in detail["validation_report"]["issues"])
    assert "registrar" in messages
    assert "Unbound" in messages or "unbound" in messages


def test_apply_rejects_unknown_slots(client: TestClient):
    proj = create_project(client, "Unknown Slot Project")
    f1 = upload_csv(client, proj, "one.csv", _csv("S-1", "3.5"))
    f2 = upload_csv(client, proj, "two.csv", _csv("S-2", "3.8"))
    tpl = _create_template(client, "Unknown Slot")

    res = _apply(
        client,
        tpl["id"],
        proj,
        {"sis": f1["id"], "registrar": f2["id"], "ghost": f1["id"]},
    )
    assert res.status_code == 422
    issues = res.json()["detail"]["validation_report"]["issues"]
    assert any("ghost" in i["message"] for i in issues)


def test_apply_blocks_files_from_another_project(client: TestClient):
    proj = create_project(client, "Owning Project")
    other = create_project(client, "Other Project")
    f_own = upload_csv(client, proj, "own.csv", _csv("S-1", "3.5"))
    f_foreign = upload_csv(client, other, "foreign.csv", _csv("S-2", "3.8"))
    tpl = _create_template(client, "Foreign File")

    res = _apply(client, tpl["id"], proj, {"sis": f_own["id"], "registrar": f_foreign["id"]})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["validation_report"]["blocking"] is True
    assert any(i.get("field") == "file_id" for i in detail["validation_report"]["issues"])


def test_duplicate_file_assignment_is_allowed_by_backend(client: TestClient):
    """Documents the backend contract: one file may fill several slots.

    The frontend surfaces a warning for this; it must not be silently blocked.
    """
    proj = create_project(client, "Duplicate Binding Project")
    f1 = upload_csv(client, proj, "same.csv", _csv("S-1", "3.5"))
    tpl = _create_template(client, "Duplicate Binding")

    res = _apply(client, tpl["id"], proj, {"sis": f1["id"], "registrar": f1["id"]})
    assert res.status_code == 200, res.text
    by_alias = {s["alias"]: s["file_id"] for s in res.json()["effective_request"]["sources"]}
    assert by_alias["sis"] == f1["id"]
    assert by_alias["registrar"] == f1["id"]


# ==============================================================================
# Structured blocking feedback (slot / worksheet / column + reason + action)
# ==============================================================================


def test_blocking_issues_identify_slot_worksheet_and_columns(client: TestClient):
    proj = create_project(client, "Feedback Project")
    # CSV without a gpa column: mapped columns are missing.
    f = upload_csv(client, proj, "roster.csv", "student_id,honor\nS-1,yes\nS-2,no\n")
    tpl = _create_template(client, "Feedback")

    res = _apply(client, tpl["id"], proj, {"sis": f["id"], "registrar": f["id"]})
    assert res.status_code == 422
    detail = res.json()["detail"]
    report = detail["validation_report"]
    assert report["blocking"] is True
    assert report["warnings"] == []  # no warnings -> distinct from errors
    slots = {i.get("slot") for i in report["issues"]}
    assert {"sis", "registrar"} <= slots
    fields = {i.get("field") for i in report["issues"]}
    assert "field_mapping" in fields
    messages = " ".join(i["message"] for i in report["issues"])
    assert "gpa" in messages
    assert "Available columns" in messages  # actionable guidance


def test_blocking_issue_identifies_missing_worksheet(client: TestClient):
    proj = create_project(client, "Worksheet Project")
    sheets = {"Roster": [["student_id", "gpa"], ["S-1", 3.5]]}
    f = upload_file(client, proj, "book.xlsx", make_multisheet_xlsx(sheets), XLSX_CONTENT_TYPE)
    cfg = _config()
    cfg["sources"][0]["sheet_name"] = "NoSuchSheet"
    tpl = client.post(TEMPLATES, json=_payload(name="Bad Worksheet", config=cfg)).json()

    res = _apply(client, tpl["id"], proj, {"sis": f["id"], "registrar": f["id"]})
    assert res.status_code == 422
    issues = res.json()["detail"]["validation_report"]["issues"]
    sheet_issues = [i for i in issues if i.get("field") == "sheet_name"]
    assert sheet_issues
    assert sheet_issues[0]["slot"] == "sis"
    assert "NoSuchSheet" in sheet_issues[0]["message"]
    assert "Available worksheets" in sheet_issues[0]["message"]


# ==============================================================================
# Rename / description / configuration update
# ==============================================================================


def test_rename_and_description_update_preserves_configuration(client: TestClient):
    tpl = _create_template(client, "Original Name", description="Original description")
    original_config = tpl["configuration"]

    res = client.put(
        f"{TEMPLATES}/{tpl['id']}",
        json={"name": "Renamed Template", "description": "Updated description"},
    )
    assert res.status_code == 200, res.text
    updated = res.json()
    assert updated["name"] == "Renamed Template"
    assert updated["description"] == "Updated description"
    assert updated["configuration"] == original_config  # details edit never touches config


def test_description_can_be_cleared(client: TestClient):
    tpl = _create_template(client, "Has Description", description="To be cleared")
    res = client.put(f"{TEMPLATES}/{tpl['id']}", json={"description": ""})
    assert res.status_code == 200, res.text
    assert res.json()["description"] is None


def test_rename_conflict_returns_409(client: TestClient):
    first = _create_template(client, "Taken Name")
    second = _create_template(client, "Other Name")
    res = client.put(f"{TEMPLATES}/{second['id']}", json={"name": first["name"]})
    assert res.status_code == 409
    assert "already exists" in res.text


def test_update_existing_configuration_replaces_snapshot_only(client: TestClient):
    tpl = _create_template(client, "Config Target", description="Keep me")
    new_cfg = _config(compare_attributes=["gpa"], ignore_case=True)
    new_cfg["sources"][0]["label"] = "Updated label"

    res = client.put(f"{TEMPLATES}/{tpl['id']}", json={"configuration": new_cfg})
    assert res.status_code == 200, res.text
    updated = res.json()
    assert updated["configuration"] == new_cfg
    assert updated["name"] == "Config Target"  # name untouched
    assert updated["description"] == "Keep me"  # description untouched


def test_update_rejects_invalid_configuration_and_shared_visibility(client: TestClient):
    tpl = _create_template(client, "Validation Target")

    bad_cfg = _config()
    bad_cfg["version"] = 99
    res = client.put(f"{TEMPLATES}/{tpl['id']}", json={"configuration": bad_cfg})
    assert res.status_code == 422
    assert "Unsupported template configuration version" in res.text

    res2 = client.put(
        f"{TEMPLATES}/{tpl['id']}", json={"visibility": "organization_shared"}
    )
    assert res2.status_code == 422
    assert "disabled" in res2.text
    assert client.get(f"{TEMPLATES}/{tpl['id']}").json()["visibility"] == "personal"


def test_update_rejects_client_supplied_owner_id(client: TestClient):
    tpl = _create_template(client, "Owner Injection")
    res = client.put(
        f"{TEMPLATES}/{tpl['id']}",
        json={"name": "Injected", "owner_id": str(uuid.uuid4())},
    )
    assert res.status_code == 422  # strict schema: extra fields are rejected


def test_delete_template_then_get_returns_404(client: TestClient):
    tpl = _create_template(client, "Delete Me")
    assert client.delete(f"{TEMPLATES}/{tpl['id']}").status_code == 204
    assert client.get(f"{TEMPLATES}/{tpl['id']}").status_code == 404
    # Deleting again is a 404, not a silent success.
    assert client.delete(f"{TEMPLATES}/{tpl['id']}").status_code == 404


def test_cross_user_update_and_delete_are_404(client: TestClient, db_session):
    tpl = _create_template(client, "Private Template")

    from app.core.security import create_access_token, hash_password
    from app.models.user import User

    intruder = User(email="batch13-intruder@example.com", hashed_password=hash_password("x"))
    db_session.add(intruder)
    db_session.flush()
    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(intruder.id), 'email': intruder.email})}"
    }

    assert (
        client.put(f"{TEMPLATES}/{tpl['id']}", headers=headers, json={"name": "Hijack"}).status_code
        == 404
    )
    assert client.delete(f"{TEMPLATES}/{tpl['id']}", headers=headers).status_code == 404
    # Owner's copy is intact.
    assert client.get(f"{TEMPLATES}/{tpl['id']}").json()["name"] == "Private Template"


# ==============================================================================
# Mode separation
# ==============================================================================


def test_financial_mode_templates_stay_rejected(client: TestClient):
    res = client.post(TEMPLATES, json=_payload(name="Financial", mode="financial"))
    assert res.status_code == 422
    assert "financial" in res.text.lower()


def test_list_can_filter_organization_templates(client: TestClient):
    _create_template(client, "Org Template A")
    _create_template(client, "Org Template B")
    res = client.get(f"{TEMPLATES}?mode=organization")
    assert res.status_code == 200
    assert {t["name"] for t in res.json()} == {"Org Template A", "Org Template B"}
    other = client.get(f"{TEMPLATES}?mode=financial")
    assert other.status_code == 200
    assert other.json() == []
