"""Batch 3 tests: transparent, user-confirmable column mapping via SourceDefinition.field_mapping.

Proves that:
- Different source column names can map to the same canonical attribute and compare correctly.
- Unmapped attributes (excluded from compare_attributes) are never counted as verified/mismatched.
- Ambiguous duplicate mappings within one source are rejected (422).
- Financial-style payloads without field_mapping remain unchanged.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.multisource import MultiSourceVerificationRequest, SourceDefinition
from app.services.verification_engine import verify_multisource_datasets

import tests.test_multisource_wizard as wizard

create_project = wizard.create_project
upload_csv = wizard.upload_csv
upload_storage = wizard.upload_storage

MULTI_SOURCE_RUN = "/runs/multi-source"
MULTI_SOURCE_VERIFY = "/verify/multi-source"


# ==============================================================================
# Engine-level: different column names -> same canonical attribute
# ==============================================================================


def test_engine_maps_different_column_names_to_same_attribute():
    """Two files use different names for the same field; field_mapping reconciles them."""
    sources_data = {
        "academic": [
            (1, {"student_id": "S-1001", "grade": "A", "hostel": "Tagore"}),
            (2, {"student_id": "S-1002", "grade": "B", "hostel": "Tagore"}),
        ],
        "idcard": [
            (1, {"enrolment_no": "S-1001", "grade_val": "A", "hostel_block": "Tagore"}),
            (2, {"enrolment_no": "S-1002", "grade_val": "C", "hostel_block": "Tagore"}),
        ],
    }
    source_defs = [
        SourceDefinition(
            alias="academic",
            file_id="00000000-0000-0000-0000-000000000001",
            is_primary=True,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id", "grade": "grade", "hostel": "hostel"},
        ),
        SourceDefinition(
            alias="idcard",
            file_id="00000000-0000-0000-0000-000000000002",
            is_primary=False,
            key_columns=["enrolment_no"],
            field_mapping={"enrolment_no": "student_id", "grade_val": "grade", "hostel_block": "hostel"},
        ),
    ]

    summary, results, discrepancies, _, _ = verify_multisource_datasets(
        sources=source_defs,
        sources_records=sources_data,
        unified_keys=["student_id"],
        compare_attributes=["grade", "hostel"],
        numeric_tolerance=0.0,
        include_identical=True,
    )

    assert summary.total_source_records == 2
    assert summary.identical_matches == 1  # S-1001
    assert summary.field_mismatches == 1  # S-1002: grade A vs C
    s1002 = next(it for it in results if it.key_values.get("student_id") == "S-1002")
    assert s1002.match_status.value == "field_mismatch"
    grade_diff = next(d for d in s1002.field_differences if d.field_name == "grade")
    assert grade_diff.source_field == "academic.grade"
    assert grade_diff.target_field == "idcard.grade_val"


def test_engine_unmapped_attribute_not_counted_as_verified_or_mismatch():
    """An attribute present but not mapped/compared must not produce a mismatch.

    grade differs across files but 'grade' is not mapped in idcard and is excluded
    from compare_attributes -> record must come out IDENTICAL, not mismatched.
    """
    sources_data = {
        "academic": [
            (1, {"student_id": "S-1", "grade": "A", "section": "X"}),
            (2, {"student_id": "S-2", "grade": "B", "section": "Y"}),
        ],
        "idcard": [
            (1, {"enrolment_no": "S-1", "grade_val": "A"}),
            (2, {"enrolment_no": "S-2", "grade_val": "C"}),
        ],
    }
    source_defs = [
        SourceDefinition(
            alias="academic",
            file_id="00000000-0000-0000-0000-000000000001",
            is_primary=True,
            key_columns=["student_id"],
            field_mapping={"student_id": "student_id", "grade": "grade", "section": "section"},
        ),
        # grade_val and section are deliberately NOT mapped here.
        SourceDefinition(
            alias="idcard",
            file_id="00000000-0000-0000-0000-000000000002",
            is_primary=False,
            key_columns=["enrolment_no"],
            field_mapping={"enrolment_no": "student_id"},
        ),
    ]

    summary, results, _, _, _ = verify_multisource_datasets(
        sources=source_defs,
        sources_records=sources_data,
        unified_keys=["student_id"],
        # Only attributes mapped in BOTH sources are comparable: student_id is the key,
        # and nothing else is mapped in idcard, so the comparable set is empty.
        compare_attributes=[],
        numeric_tolerance=0.0,
        include_identical=True,
    )

    assert summary.field_mismatches == 0
    assert summary.identical_matches == 2
    for item in results:
        assert len(item.field_differences or []) == 0


# ==============================================================================
# Ambiguous duplicate mappings within one source
# ==============================================================================


def test_duplicate_attribute_mapping_in_one_source_rejected():
    """Two columns of the same source mapping to one attribute is a configuration error."""
    with pytest.raises(ValidationError) as exc_info:
        MultiSourceVerificationRequest(
            sources=[
                SourceDefinition(
                    alias="a",
                    file_id="00000000-0000-0000-0000-000000000001",
                    is_primary=True,
                    key_columns=["id"],
                    field_mapping={"grade": "grade", "grade_val": "grade"},
                ),
                SourceDefinition(
                    alias="b",
                    file_id="00000000-0000-0000-0000-000000000002",
                    key_columns=["id"],
                ),
            ],
            unified_keys=["id"],
        )
    assert "Ambiguous column mapping" in str(exc_info.value)


def test_duplicate_attribute_mapping_endpoint_422(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Duplicate Mapping Project")
    f1 = upload_csv(client, proj_id, "a.csv", "id,grade\n1,A\n")
    f2 = upload_csv(client, proj_id, "b.csv", "id,grade\n1,A\n")

    res = client.post(
        f"/api/v1/projects/{proj_id}{MULTI_SOURCE_VERIFY}",
        json={
            "sources": [
                {"alias": "a", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"],
                 "field_mapping": {"id": "id", "grade": "grade", "grade_copy": "grade"}},
                {"alias": "b", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"],
                 "field_mapping": {"id": "id"}},
            ],
            "unified_keys": ["id"],
            "compare_attributes": ["grade"],
        },
    )
    assert res.status_code == 422
    assert "Ambiguous column mapping" in str(res.json()["detail"])


# ==============================================================================
# Endpoint-level: mapping travels from request to engine unchanged
# ==============================================================================


def test_endpoint_different_column_names_compare_via_field_mapping(client: TestClient, upload_storage: Path):
    proj_id = create_project(client, "Mapped Columns Project")
    f1 = upload_csv(client, proj_id, "academic.csv", "student_id,grade\nS-1,A\nS-2,B\n")
    f2 = upload_csv(client, proj_id, "idcard.csv", "enrolment_no,grade_value\nS-1,A\nS-2,C\n")

    run_res = client.post(
        f"/api/v1/projects/{proj_id}{MULTI_SOURCE_RUN}",
        json={
            "sources": [
                {"alias": "academic", "file_id": f1["id"], "is_primary": True, "key_columns": ["student_id"],
                 "field_mapping": {"student_id": "student_id", "grade": "grade"}},
                {"alias": "idcard", "file_id": f2["id"], "is_primary": False, "key_columns": ["enrolment_no"],
                 "field_mapping": {"enrolment_no": "student_id", "grade_value": "grade"}},
            ],
            "unified_keys": ["student_id"],
            "compare_attributes": ["grade"],
            "include_identical": True,
        },
    )
    assert run_res.status_code == 201, run_res.text
    run_data = run_res.json()
    assert run_data["summary"]["identical_matches"] == 1
    assert run_data["summary"]["field_mismatches"] == 1
    # The mapping must round-trip through persistence.
    aliases = {s["alias"]: s.get("field_mapping") for s in run_data["sources"]}
    assert aliases["idcard"] == {"enrolment_no": "student_id", "grade_value": "grade"}


# ==============================================================================
# Financial compatibility: payloads without field_mapping unchanged
# ==============================================================================


def test_financial_style_payload_without_field_mapping_unchanged(client: TestClient, upload_storage: Path):
    """erp/bank style request with no field_mapping behaves exactly as before Batch 3."""
    proj_id = create_project(client, "Financial No Mapping Project")
    f1 = upload_csv(client, proj_id, "erp.csv", "id,amount,status\nTX-1,100.00,COMPLETED\nTX-2,200.00,COMPLETED\n")
    f2 = upload_csv(client, proj_id, "bank.csv", "id,amount,status\nTX-1,100.00,COMPLETED\nTX-2,205.00,COMPLETED\n")

    payload = {
        "sources": [
            {"alias": "erp", "file_id": f1["id"], "is_primary": True, "key_columns": ["id"]},
            {"alias": "bank", "file_id": f2["id"], "is_primary": False, "key_columns": ["id"]},
        ],
        "unified_keys": ["id"],
        "compare_attributes": ["amount", "status"],
        "numeric_tolerance": 0.0,
        "include_identical": True,
    }
    for endpoint in (MULTI_SOURCE_VERIFY, MULTI_SOURCE_RUN):
        res = client.post(f"/api/v1/projects/{proj_id}{endpoint}", json=payload)
        assert res.status_code in (200, 201), res.text
        data = res.json()
        assert data["summary"]["identical_matches"] == 1
        assert data["summary"]["field_mismatches"] == 1
