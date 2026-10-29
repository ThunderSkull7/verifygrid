"""Tests for Batch 8: Multi-Sheet Audit Workbook, Golden Record & Reusable Recipes."""

from __future__ import annotations

import io
import json
import uuid
import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.project import Project
from app.models.source_file import SourceFile
from app.models.user import User
from app.models.verification_run import VerificationDiscrepancy, VerificationRun
from app.schemas.recipe import (
    RecipeApplyRequest,
    VerificationRecipe,
)
from app.services.export_service import (
    generate_audit_workbook_xlsx,
    generate_golden_record_csv,
    generate_golden_record_json,
    generate_golden_record_xlsx,
    sanitize_formula_value,
)
from app.services.recipe_service import apply_recipe_to_files, export_recipe_from_run


@pytest.fixture
def auth_client(client: TestClient, db_session: Session):
    """Sets up an authenticated client with project and a completed verification run."""
    user = User(
        email="auditor@verifygrid.com",
        hashed_password="fakehashedpassword",
        full_name="Lead Auditor",
        role="ADMIN",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    project = Project(
        name="Quarterly Financial Audit",
        description="Comprehensive audit of ledger vs bank",
        owner_id=user.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    src_file = SourceFile(
        project_id=project.id,
        original_filename="erp_ledger.csv",
        storage_path="mock/erp_ledger.csv",
        file_type="csv",
        file_size=1024,
        status="uploaded",
    )
    tgt_file = SourceFile(
        project_id=project.id,
        original_filename="bank_feed.csv",
        storage_path="mock/bank_feed.csv",
        file_type="csv",
        file_size=1024,
        status="uploaded",
    )
    db_session.add_all([src_file, tgt_file])
    db_session.commit()
    db_session.refresh(src_file)
    db_session.refresh(tgt_file)

    run = VerificationRun(
        project_id=project.id,
        source_file_id=src_file.id,
        target_file_id=tgt_file.id,
        status="completed",
        key_columns=["tx_id"],
        column_mapping={"tx_id": "tx_id", "amount": "amount", "status": "status"},
        sources=[
            {
                "alias": "erp",
                "file_id": str(src_file.id),
                "key_columns": ["tx_id"],
                "field_mapping": {"tx_id": "tx_id", "amount": "amount"},
                "is_primary": True,
            },
            {
                "alias": "bank",
                "file_id": str(tgt_file.id),
                "key_columns": ["tx_id"],
                "field_mapping": {"tx_id": "tx_id", "amount": "amount"},
                "is_primary": False,
            },
        ],
        configuration={
            "unified_keys": ["tx_id"],
            "numeric_tolerance": 0.05,
            "ignore_whitespace": True,
            "ignore_case": True,
            "rule_config": {
                "version": "1.0.0",
                "where_conditions": [],
            },
        },
        summary={
            "total_source_records": 100,
            "total_target_records": 98,
            "matched_records": 95,
            "identical_matches": 90,
            "field_mismatches": 5,
            "unmatched_source_records": 5,
            "unmatched_target_records": 3,
            "total_discrepancies": 8,
            "gross_exposure": 1250.75,
            "net_variance": -350.25,
            "claimed_amount": 50000.0,
            "verified_amount": 49649.75,
            "outstanding_variance": 350.25,
        },
        sign_off_status="APPROVED",
        sign_off_proposed_by=user.id,
        sign_off_proposed_by_name="Alice Maker",
        sign_off_proposal_note="All variances under $100 reviewed and accounted for.",
        sign_off_approved_by=uuid.uuid4(),
        sign_off_approved_by_name="Bob Checker",
        sign_off_decision_note="Countersigned. Spot-checked high-exposure items.",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # Discrepancy 1: Unresolved discrepancy with injection risk payload
    disc1 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="field_mismatch",
        discrepancy_category="field_mismatch",
        key_values={"tx_id": "=cmd|' /C calc'!A0"},
        source_row_number=10,
        target_row_number=12,
        source_amount=500.0,
        target_amount=450.0,
        variance_amount=50.0,
        exposure_amount=50.0,
        currency="USD",
        severity="medium",
        resolution_status="unresolved",
        cluster_id="cl_rounding",
        cluster_name="Rounding Discrepancies",
        assigned_to="reviewer@verifygrid.com",
        source_record={"tx_id": "=cmd|' /C calc'!A0", "amount": 500.0, "status": "COMPLETED"},
        target_record={"tx_id": "=cmd|' /C calc'!A0", "amount": 450.0, "status": "COMPLETED"},
        field_differences=[{"field_name": "amount", "source_value": "=cmd|' /C calc'!A0", "target_value": 450.0}],
        resolution_note="=cmd|' /C calc'!A0",
        message="Amount variance exceeds strict equality",
    )

    # Discrepancy 2: Approved and resolved override
    disc2 = VerificationDiscrepancy(
        run_id=run.id,
        match_status="field_mismatch",
        discrepancy_category="field_mismatch",
        key_values={"tx_id": "@malicious_formula()"},
        source_row_number=20,
        target_row_number=22,
        source_amount=1000.0,
        target_amount=950.0,
        variance_amount=50.0,
        exposure_amount=50.0,
        currency="USD",
        severity="high",
        resolution_status="resolved",
        resolution_note="Approved timing difference under SLA clause 4.2",
        resolved_by="Bob Checker",
        cluster_id="cl_timing",
        cluster_name="SLA Timing Lag",
        assigned_to="lead@verifygrid.com",
        source_record={"tx_id": "@malicious_formula()", "amount": 1000.0, "status": "SETTLED"},
        target_record={"tx_id": "@malicious_formula()", "amount": 950.0, "status": "SETTLED"},
        field_differences=[{"field_name": "amount", "source_value": 1000.0, "target_value": 950.0}],
        message="Timing lag verified",
    )

    db_session.add_all([disc1, disc2])
    db_session.commit()

    return client, user, project, run


def test_formula_injection_sanitization():
    """Verify that all spreadsheet formula injection triggers are safely escaped."""
    assert sanitize_formula_value("=1+1") == "'=1+1"
    assert sanitize_formula_value("+cmd|' /C calc'") == "'+cmd|' /C calc'"
    assert sanitize_formula_value("-10.50") == "-10.50"
    assert sanitize_formula_value("-SUM(A1:A10)") == "'-SUM(A1:A10)"
    assert sanitize_formula_value("@SUM(B1:B2)") == "'@SUM(B1:B2)"
    assert sanitize_formula_value("\t=DDE()") == "'\t=DDE()"
    assert sanitize_formula_value("\r+DDE()") == "'\r+DDE()"
    assert sanitize_formula_value(100) == 100
    assert sanitize_formula_value(99.95) == 99.95
    assert sanitize_formula_value(None) == ""
    assert sanitize_formula_value("Regular Safe String") == "Regular Safe String"


def test_multi_sheet_audit_workbook_structure_and_metadata(auth_client, db_session: Session):
    """Verify that the generated Excel audit workbook has 4 distinct styled tabs with complete metadata."""
    client, user, project, run = auth_client

    discrepancies = db_session.query(VerificationDiscrepancy).filter(VerificationDiscrepancy.run_id == run.id).all()
    xlsx_bytes = generate_audit_workbook_xlsx(db=db_session, run=run, discrepancies=discrepancies)

    assert len(xlsx_bytes) > 0

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    sheet_names = wb.sheetnames
    assert len(sheet_names) == 4
    assert sheet_names == [
        "Executive Summary",
        "Detailed Comparison",
        "Exception Log & Decisions",
        "Golden Record",
    ]

    # Tab 1: Executive Summary
    ws1 = wb["Executive Summary"]
    assert "VerifyGrid Executive Audit Certificate" in str(ws1["A1"].value)
    values_str = " ".join(str(cell.value or "") for row in ws1.iter_rows() for cell in row)
    assert str(run.id) in values_str
    assert project.name in values_str
    assert "Alice Maker" in values_str
    assert "Bob Checker" in values_str
    assert "APPROVED" in values_str
    assert "1,250.75" in values_str or "1250.75" in values_str

    # Tab 2: Detailed Comparison
    ws2 = wb["Detailed Comparison"]
    header_vals = [cell.value for cell in ws2[1]]
    assert "Match Status" in header_vals
    assert "Key Values" in header_vals
    assert "Exposure Amount" in header_vals
    rows_text = " ".join(str(c.value or "") for r in ws2.iter_rows() for c in r)
    assert "'=cmd" in rows_text or "\'=cmd" in rows_text

    # Tab 3: Exception Log & Decisions
    ws3 = wb["Exception Log & Decisions"]
    ws3_headers = [cell.value for cell in ws3[1]]
    assert "Exception Cluster Name" in ws3_headers
    assert "Resolution Status" in ws3_headers
    assert "Override / Justification Note" in ws3_headers
    ws3_text = " ".join(str(c.value or "") for r in ws3.iter_rows() for c in r)
    assert "Rounding Discrepancies" in ws3_text
    assert "SLA Timing Lag" in ws3_text
    assert "Approved timing difference" in ws3_text

    # Tab 4: Golden Record
    ws4 = wb["Golden Record"]
    ws4_headers = [cell.value for cell in ws4[1]]
    assert "Golden Record ID" in ws4_headers
    assert "Golden Status" in ws4_headers
    assert "Resolution Policy" in ws4_headers


def test_golden_record_export_filtering_policies(auth_client, db_session: Session):
    """Test golden dataset standalone exports and filtering policy enforcement."""
    client, user, project, run = auth_client
    discrepancies = db_session.query(VerificationDiscrepancy).filter(VerificationDiscrepancy.run_id == run.id).all()

    # Policy 1: ONLY_VERIFIED_AND_APPROVED
    csv_bytes_only = generate_golden_record_csv(run, discrepancies, policy="ONLY_VERIFIED_AND_APPROVED")
    csv_text_only = csv_bytes_only.decode("utf-8")
    assert "# VerifyGrid Authoritative Golden Record Export" in csv_text_only
    assert "# Export Policy,ONLY_VERIFIED_AND_APPROVED" in csv_text_only
    assert "APPROVED_WITH_OVERRIDE" in csv_text_only
    assert "UNRESOLVED_EXCEPTION" not in csv_text_only

    # JSON export with ONLY_VERIFIED_AND_APPROVED
    json_bytes_only = generate_golden_record_json(run, discrepancies, policy="ONLY_VERIFIED_AND_APPROVED")
    json_data_only = json.loads(json_bytes_only.decode("utf-8"))
    assert "manifest" in json_data_only
    assert json_data_only["manifest"]["export_policy"] == "ONLY_VERIFIED_AND_APPROVED"
    assert len(json_data_only["records"]) == 1
    assert json_data_only["records"][0]["golden_status"] == "APPROVED_WITH_OVERRIDE"

    # Policy 2: ALL_WITH_STATUS_METADATA
    csv_bytes_all = generate_golden_record_csv(run, discrepancies, policy="ALL_WITH_STATUS_METADATA")
    csv_text_all = csv_bytes_all.decode("utf-8")
    assert "APPROVED_WITH_OVERRIDE" in csv_text_all
    assert "UNRESOLVED_EXCEPTION" in csv_text_all

    json_bytes_all = generate_golden_record_json(run, discrepancies, policy="ALL_WITH_STATUS_METADATA")
    json_data_all = json.loads(json_bytes_all.decode("utf-8"))
    assert len(json_data_all["records"]) == 2

    # XLSX export
    xlsx_bytes = generate_golden_record_xlsx(run, discrepancies, policy="ALL_WITH_STATUS_METADATA")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    assert "VerifyGrid Authoritative Golden Record Dataset" in str(ws["A1"].value)


def test_recipe_export_and_apply_workflow(auth_client, db_session: Session):
    """Test generating a recipe from a run, and applying it to project files."""
    client, user, project, run = auth_client

    # 1. Export Recipe from Run
    recipe = export_recipe_from_run(db=db_session, project_id=project.id, run_id=run.id, current_user=user)
    assert isinstance(recipe, VerificationRecipe)
    assert recipe.version == "1.0.0"
    assert "Quarterly Financial Audit" in recipe.recipe_name
    assert recipe.unified_keys == ["tx_id"]
    assert recipe.numeric_tolerance == 0.05
    assert len(recipe.sources) == 2
    assert recipe.sources[0].alias == "erp"
    assert recipe.sources[1].alias == "bank"

    # 2. Apply Recipe with compatible files
    src_file = db_session.query(SourceFile).filter(SourceFile.original_filename == "erp_ledger.csv").first()
    tgt_file = db_session.query(SourceFile).filter(SourceFile.original_filename == "bank_feed.csv").first()

    apply_req = RecipeApplyRequest(
        recipe=recipe,
        file_ids=[src_file.id, tgt_file.id],
        file_mappings={"erp": src_file.id, "bank": tgt_file.id},
    )

    validation_result = apply_recipe_to_files(
        db=db_session,
        project_id=project.id,
        request=apply_req,
        current_user=user,
    )

    assert validation_result.valid is True
    assert validation_result.suggested_unified_keys == ["tx_id"]
    assert str(src_file.id) in validation_result.suggested_source_aliases
    assert validation_result.suggested_source_aliases[str(src_file.id)] == "erp"
    assert validation_result.suggested_source_aliases[str(tgt_file.id)] == "bank"
    assert validation_result.numeric_tolerance == 0.05


def test_api_export_and_recipe_endpoints(auth_client):
    """Test REST endpoints for multi-sheet workbook, golden record exports, and recipe standard."""
    client, user, project, run = auth_client
    token = create_access_token({"sub": str(user.id), "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Standard Report XLSX (Audit Workbook)
    res_xlsx = client.get(f"/api/v1/projects/{project.id}/runs/{run.id}/audit-workbook/export", headers=headers)
    assert res_xlsx.status_code == 200
    assert "application/vnd.openxmlformats" in res_xlsx.headers["content-type"]
    wb = openpyxl.load_workbook(io.BytesIO(res_xlsx.content))
    assert len(wb.sheetnames) == 4

    # 2. Golden Record CSV
    res_golden_csv = client.get(
        f"/api/v1/projects/{project.id}/runs/{run.id}/golden-record/export?format=csv&policy=ONLY_VERIFIED_AND_APPROVED",
        headers=headers,
    )
    assert res_golden_csv.status_code == 200
    assert "text/csv" in res_golden_csv.headers["content-type"]
    assert "attachment; filename=\"golden_record_" in res_golden_csv.headers["content-disposition"]
    assert "APPROVED_WITH_OVERRIDE" in res_golden_csv.text

    # 3. Golden Record JSON
    res_golden_json = client.get(
        f"/api/v1/projects/{project.id}/runs/{run.id}/golden-record/export?format=json&policy=ALL_WITH_STATUS_METADATA",
        headers=headers,
    )
    assert res_golden_json.status_code == 200
    data = res_golden_json.json()
    assert "manifest" in data
    assert "records" in data
    assert len(data["records"]) == 2

    # 4. Recipe Export GET
    res_recipe = client.get(f"/api/v1/projects/{project.id}/runs/{run.id}/recipe", headers=headers)
    assert res_recipe.status_code == 200
    recipe_json = res_recipe.json()
    assert recipe_json["version"] == "1.0.0"
    assert recipe_json["unified_keys"] == ["tx_id"]

    # 5. Recipe Apply POST
    res_apply = client.post(
        f"/api/v1/projects/{project.id}/recipes/apply",
        json={
            "recipe": recipe_json,
            "file_ids": [str(run.source_file_id), str(run.target_file_id)],
            "file_mappings": {
                "erp": str(run.source_file_id),
                "bank": str(run.target_file_id),
            },
        },
        headers=headers,
    )
    assert res_apply.status_code == 200
    apply_data = res_apply.json()
    assert apply_data["valid"] is True
    assert apply_data["suggested_unified_keys"] == ["tx_id"]
