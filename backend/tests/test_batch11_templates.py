"""Batch 11 tests: reusable verification templates (personal-only launch).

Covers: persistence/CRUD with ownership scoping, strict configuration
validation and versioning, apply-time validation against new uploads
(worksheets, columns, keys, ownership), cross-user denial, and guarantees that
templates never store per-upload records or quarantine state.
"""

import io
import uuid
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings

import tests.test_batch7_worksheets as b7

make_multisheet_xlsx = b7.make_multisheet_xlsx
upload_file = b7.upload_file
create_project = b7.create_project
upload_csv = b7.upload_csv

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MULTI_SOURCE_VERIFY = "/verify/multi-source"
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


def _template_payload(name="My Template", config=None, **kw) -> dict:
    payload = {"name": name, "mode": "organization", "configuration": config or _config()}
    payload.update(kw)
    return payload


# ==============================================================================
# CRUD & ownership
# ==============================================================================


def test_create_and_get_personal_template(client: TestClient):
    res = client.post(TEMPLATES, json=_template_payload())
    assert res.status_code == 201, res.text
    t = res.json()
    assert t["name"] == "My Template"
    assert t["mode"] == "organization"
    assert t["visibility"] == "personal"
    assert t["config_version"] == 1
    assert t["source_count"] == 2

    got = client.get(f"{TEMPLATES}/{t['id']}")
    assert got.status_code == 200
    assert got.json()["configuration"]["version"] == 1


def test_list_returns_only_current_users_templates(client: TestClient, default_user, db_session):
    client.post(TEMPLATES, json=_template_payload("Owned A"))
    client.post(TEMPLATES, json=_template_payload("Owned B"))

    # Second user with their own session
    from app.models.user import User
    from app.core.security import hash_password, create_access_token

    other = User(email="other@example.com", hashed_password=hash_password("x"))
    db_session.add(other)
    db_session.flush()
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other.id), 'email': other.email})}"}

    res = client.get(TEMPLATES, headers=other_headers)
    assert res.status_code == 200
    assert res.json() == []  # cross-user rows are invisible

    own = client.get(TEMPLATES)
    assert {t["name"] for t in own.json()} == {"Owned A", "Owned B"}


def test_duplicate_name_rejected(client: TestClient):
    assert client.post(TEMPLATES, json=_template_payload("Dup")).status_code == 201
    res = client.post(TEMPLATES, json=_template_payload("Dup"))
    assert res.status_code == 409


def test_update_and_delete_owned_template(client: TestClient):
    t = client.post(TEMPLATES, json=_template_payload("V1")).json()
    upd = client.put(
        f"{TEMPLATES}/{t['id']}",
        json={"name": "V2", "description": "updated"},
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "V2"

    new_cfg = _config(compare_attributes=None, ignore_attributes=["gpa"])
    upd2 = client.put(f"{TEMPLATES}/{t['id']}", json={"configuration": new_cfg})
    assert upd2.status_code == 200
    assert upd2.json()["configuration"]["compare_attributes"] is None

    deleted = client.delete(f"{TEMPLATES}/{t['id']}")
    assert deleted.status_code == 204
    assert client.get(f"{TEMPLATES}/{t['id']}").status_code == 404


def test_cross_user_access_denied_with_404(client: TestClient, default_user, db_session):
    t = client.post(TEMPLATES, json=_template_payload("Secret")).json()

    from app.models.user import User
    from app.core.security import hash_password, create_access_token

    other = User(email="intruder@example.com", hashed_password=hash_password("x"))
    db_session.add(other)
    db_session.flush()
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other.id), 'email': other.email})}"}

    assert client.get(f"{TEMPLATES}/{t['id']}", headers=other_headers).status_code == 404
    assert (
        client.put(f"{TEMPLATES}/{t['id']}", headers=other_headers, json={"name": "Hacked"}).status_code
        == 404
    )
    assert client.delete(f"{TEMPLATES}/{t['id']}", headers=other_headers).status_code == 404
    apply = client.post(
        f"{TEMPLATES}/{t['id']}/apply",
        headers=other_headers,
        json={
            "project_id": str(uuid.uuid4()),
            "sources": [
                {"slot": "sis", "file_id": str(uuid.uuid4())},
                {"slot": "registrar", "file_id": str(uuid.uuid4())},
            ],
        },
    )
    assert apply.status_code == 404


def test_shared_visibility_rejected(client: TestClient):
    res = client.post(TEMPLATES, json=_template_payload("Shared", visibility="organization_shared"))
    assert res.status_code == 422
    assert "disabled" in res.text

    t = client.post(TEMPLATES, json=_template_payload("Personal")).json()
    upd = client.put(f"{TEMPLATES}/{t['id']}", json={"visibility": "organization_shared"})
    assert upd.status_code == 422
    # And the stored template remains personal.
    assert client.get(f"{TEMPLATES}/{t['id']}").json()["visibility"] == "personal"


def test_unauthenticated_access_rejected(client: TestClient):
    no_auth = TestClient(client.app)
    assert no_auth.get(TEMPLATES).status_code == 401
    assert no_auth.post(TEMPLATES, json=_template_payload()).status_code == 401


# ==============================================================================
# Configuration validation & versioning
# ==============================================================================


def test_unsupported_version_rejected(client: TestClient):
    cfg = _config()
    cfg["version"] = 99
    res = client.post(TEMPLATES, json=_template_payload("Bad Version", config=cfg))
    assert res.status_code == 422
    assert "Unsupported template configuration version" in res.text


def test_unexpected_fields_rejected_not_silently_dropped(client: TestClient):
    cfg = _config(unauthorized_field="should-fail")
    res = client.post(TEMPLATES, json=_template_payload("Sneaky", config=cfg))
    assert res.status_code == 422


def test_invalid_source_roles_rejected(client: TestClient):
    # No primary
    cfg = _config()
    for s in cfg["sources"]:
        s["is_primary"] = False
    res = client.post(TEMPLATES, json=_template_payload("NoPrimary", config=cfg))
    assert res.status_code == 422

    # Duplicate aliases
    cfg2 = _config()
    cfg2["sources"][1]["alias"] = "sis"
    res2 = client.post(TEMPLATES, json=_template_payload("DupAlias", config=cfg2))
    assert res2.status_code == 422


def test_invalid_identity_key_and_fallback_rejected(client: TestClient):
    # Unified key not mapped in a source
    cfg = _config()
    cfg["sources"][1]["field_mapping"] = {"other_col": "other"}
    res = client.post(TEMPLATES, json=_template_payload("UnmappedKey", config=cfg))
    assert res.status_code == 422

    # Fallback identical to primary key
    cfg2 = _config(fallback_keys=[["student_id"]])
    res2 = client.post(TEMPLATES, json=_template_payload("FallbackDup", config=cfg2))
    assert res2.status_code == 422


def test_invalid_multi_primary_ownership_rejected(client: TestClient):
    cfg = _config(field_ownership={"gpa": "nonexistent"}, multi_primary=True)
    res = client.post(TEMPLATES, json=_template_payload("BadOwner", config=cfg))
    assert res.status_code == 422

    cfg2 = _config(field_ownership={"gpa": "registrar"})  # ownership without multi_primary
    res2 = client.post(TEMPLATES, json=_template_payload("OwnerNoMp", config=cfg2))
    assert res2.status_code == 422

    # Multi-primary WITH fallback is rejected (Batch 5 invariant preserved).
    cfg3 = _config(fallback_keys=[["phone"]], multi_primary=True)
    res3 = client.post(TEMPLATES, json=_template_payload("MpFallback", config=cfg3))
    assert res3.status_code == 422


def test_ambiguous_mapping_and_key_overlap_rejected(client: TestClient):
    cfg = _config()
    cfg["sources"][0]["field_mapping"] = {"a": "gpa", "b": "gpa", "student_id": "student_id"}
    assert client.post(TEMPLATES, json=_template_payload("Ambig", config=cfg)).status_code == 422

    cfg2 = _config(compare_attributes=["student_id", "gpa"])
    assert (
        client.post(TEMPLATES, json=_template_payload("KeyCmp", config=cfg2)).status_code == 422
    )


def test_financial_mode_templates_rejected_separate(client: TestClient):
    res = client.post(TEMPLATES, json=_template_payload("Fin", mode="financial"))
    assert res.status_code == 422
    assert "financial" in res.text.lower()


# ==============================================================================
# Apply
# ==============================================================================


BATCH11_SHEETS = {
    "Roster": [
        ["student_id", "gpa"],
        ["S-1", 3.5],
        ["S-2", 3.0],
    ],
}


def _upload_project_with_file(client: TestClient, sheets=None, csv_data=None):
    proj_id = create_project(client, "Template Apply Project")
    if sheets:
        f = upload_file(client, proj_id, "roster.xlsx", make_multisheet_xlsx(sheets), XLSX_CONTENT_TYPE)
    else:
        f = upload_csv(client, proj_id, "roster.csv", csv_data)
    return proj_id, f


def test_apply_success_returns_effective_request_without_executing(client: TestClient):
    proj_id, f = _upload_project_with_file(client, sheets=BATCH11_SHEETS)
    t = client.post(TEMPLATES, json=_template_payload("Apply OK")).json()

    res = client.post(
        f"{TEMPLATES}/{t['id']}/apply",
        json={
            "project_id": proj_id,
            "sources": [
                {"slot": "sis", "file_id": f["id"]},
                {"slot": "registrar", "file_id": f["id"]},
            ],
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    report = data["validation_report"]
    assert report["blocking"] is False
    eff = data["effective_request"]
    assert eff["sources"][0]["file_id"] == f["id"]
    assert eff["sources"][0]["alias"] == "sis"
    assert eff["sources"][0]["is_primary"] is True
    assert eff["unified_keys"] == ["student_id"]
    assert "excluded_row_indices" not in eff["sources"][0] or eff["sources"][0]["excluded_row_indices"] in (None, [])

    # The effective request executes through the EXISTING verification endpoint.
    v = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}", json=eff)
    assert v.status_code == 200, v.text
    assert v.json()["summary"]["matched_records"] == 2


def test_apply_blocks_missing_columns(client: TestClient):
    proj_id, f = _upload_project_with_file(
        client, csv_data="student_id,honor\nS-1,yes\nS-2,no\n"
    )
    t = client.post(TEMPLATES, json=_template_payload("Gpa Col")).json()
    res = client.post(
        f"{TEMPLATES}/{t['id']}/apply",
        json={
            "project_id": proj_id,
            "sources": [
                {"slot": "sis", "file_id": f["id"]},
                {"slot": "registrar", "file_id": f["id"]},
            ],
        },
    )
    assert res.status_code == 422
    report = res.json()["detail"]["validation_report"]
    assert report["blocking"] is True
    messages = " ".join(i["message"] for i in report["issues"])
    assert "gpa" in messages  # renamed/missing column surfaced


def test_apply_blocks_missing_worksheet_and_csv_sheet_rule(client: TestClient):
    proj_id, f = _upload_project_with_file(client, sheets=BATCH11_SHEETS)
    cfg = _config()
    cfg["sources"][0]["sheet_name"] = "NoSuchSheet"
    t = client.post(TEMPLATES, json=_template_payload("Bad Sheet", config=cfg)).json()

    res = client.post(
        f"{TEMPLATES}/{t['id']}/apply",
        json={
            "project_id": proj_id,
            "sources": [
                {"slot": "sis", "file_id": f["id"]},
                {"slot": "registrar", "file_id": f["id"]},
            ],
        },
    )
    assert res.status_code == 422
    assert "NoSuchSheet" in res.text

    # sheet_name on a CSV-bound slot is rejected (Batch 7 rule).
    cfg2 = _config()
    cfg2["sources"][0]["sheet_name"] = "Roster"
    t2 = client.post(TEMPLATES, json=_template_payload("Sheet On Csv", config=cfg2)).json()
    proj2, f2 = _upload_project_with_file(client, csv_data="student_id,gpa\nS-1,3.5\nS-2,3.0\n")
    res2 = client.post(
        f"{TEMPLATES}/{t2['id']}/apply",
        json={
            "project_id": proj2,
            "sources": [
                {"slot": "sis", "file_id": f2["id"]},
                {"slot": "registrar", "file_id": f2["id"]},
            ],
        },
    )
    assert res2.status_code == 422


def test_apply_blocks_unbound_or_unknown_slots_and_foreign_files(client: TestClient, db_session, default_user):
    proj_id, f = _upload_project_with_file(client, sheets=BATCH11_SHEETS)
    t = client.post(TEMPLATES, json=_template_payload("Slots")).json()

    # Missing one binding
    res = client.post(
        f"{TEMPLATES}/{t['id']}/apply",
        json={"project_id": proj_id, "sources": [{"slot": "sis", "file_id": f["id"]}]},
    )
    assert res.status_code == 422

    # Unknown slot
    res2 = client.post(
        f"{TEMPLATES}/{t['id']}/apply",
        json={
            "project_id": proj_id,
            "sources": [
                {"slot": "sis", "file_id": f["id"]},
                {"slot": "registrar", "file_id": f["id"]},
                {"slot": "ghost", "file_id": f["id"]},
            ],
        },
    )
    assert res2.status_code == 422

    # File from a different project
    other_proj = create_project(client, "Other Project")
    res3 = client.post(
        f"{TEMPLATES}/{t['id']}/apply",
        json={
            "project_id": other_proj,
            "sources": [
                {"slot": "sis", "file_id": f["id"]},  # belongs to proj_id
                {"slot": "registrar", "file_id": f["id"]},
            ],
        },
    )
    assert res3.status_code == 422


def test_apply_foreign_project_denied(client: TestClient, db_session, default_user):
    proj_id, f = _upload_project_with_file(client, sheets=BATCH11_SHEETS)
    t = client.post(TEMPLATES, json=_template_payload("Own")).json()

    from app.models.user import User
    from app.core.security import hash_password, create_access_token

    other = User(email="otherowner@example.com", hashed_password=hash_password("x"))
    db_session.add(other)
    db_session.flush()
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(other.id), 'email': other.email})}"}
    other_proj_res = TestClient(client.app)
    other_proj_res.headers.update(other_headers)
    other_proj = create_project(other_proj_res, "Other User Project")

    res = other_proj_res.post(
        f"{TEMPLATES}/{t['id']}/apply",
        json={
            "project_id": other_proj,
            "sources": [
                {"slot": "sis", "file_id": f["id"]},
                {"slot": "registrar", "file_id": f["id"]},
            ],
        },
    )
    assert res.status_code == 404  # template belongs to someone else


def test_templates_never_store_per_upload_state(client: TestClient):
    proj_id, f = _upload_project_with_file(client, sheets=BATCH11_SHEETS)
    # A tampered config trying to smuggle per-upload state is rejected.
    cfg = _config()
    cfg["sources"][0]["file_id"] = f["id"]
    cfg["sources"][0]["excluded_row_indices"] = [3]
    res = client.post(TEMPLATES, json=_template_payload("Smuggler", config=cfg))
    assert res.status_code == 422

    # A legitimately saved template contains no per-upload fields.
    t = client.post(TEMPLATES, json=_template_payload("Clean")).json()
    stored = client.get(f"{TEMPLATES}/{t['id']}").json()
    raw = str(stored["configuration"])
    for forbidden in ("excluded_row", "quarantine", "resolution", "storage_path"):
        assert forbidden not in raw
    for s in stored["configuration"]["sources"]:
        assert "file_id" not in s


def test_legacy_verification_without_templates_unchanged(client: TestClient):
    proj_id, f = _upload_project_with_file(client, sheets=BATCH11_SHEETS)
    payload = {
        "sources": [
            {"alias": "a", "file_id": f["id"], "is_primary": True, "key_columns": ["student_id"],
             "field_mapping": {"student_id": "student_id", "gpa": "gpa"}},
            {"alias": "b", "file_id": f["id"], "is_primary": False, "key_columns": ["student_id"],
             "field_mapping": {"student_id": "student_id", "gpa": "gpa"}},
        ],
        "unified_keys": ["student_id"],
        "compare_attributes": ["gpa"],
        "include_identical": True,
    }
    res = client.post(f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}", json=payload)
    assert res.status_code == 200
    assert res.json()["summary"]["matched_records"] == 2
