import json
import urllib.request
import urllib.parse
import mimetypes
import uuid

BASE_URL = "http://127.0.0.1:8000/api/v1"

def test_full_pipeline():
    print("[1] Testing Health Endpoint...")
    req = urllib.request.Request(f"{BASE_URL}/health")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        print("  -> Health:", resp.read().decode())

    test_email = f"alex_{uuid.uuid4().hex[:6]}@example.com"
    print(f"\n[2] Testing Registration for {test_email}...")
    reg_payload = json.dumps({
        "email": test_email,
        "password": "Password123!",
        "full_name": "Alex Mercer"
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/register",
        data=reg_payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 201
        reg_data = json.loads(resp.read().decode())
        token = reg_data["access_token"]
        print("  -> Registered. Token acquired:", token[:15], "...")

    print("\n[3] Testing /auth/me...")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        me_data = json.loads(resp.read().decode())
        assert me_data["email"] == test_email
        assert me_data["full_name"] == "Alex Mercer"
        print("  -> /auth/me Verified:", me_data["full_name"], f"({me_data['id']})")

    print("\n[4] Testing Login...")
    login_payload = json.dumps({
        "email": test_email,
        "password": "Password123!"
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/login",
        data=login_payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        login_data = json.loads(resp.read().decode())
        assert "access_token" in login_data
        print("  -> Login verified successfully.")

    print("\n[5] Testing Project Creation...")
    proj_payload = json.dumps({
        "name": "Q4 Finance Audit",
        "description": "Audit of accounts receivable vs bank records"
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/projects",
        data=proj_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 201
        proj_data = json.loads(resp.read().decode())
        project_id = proj_data["id"]
        print("  -> Project Created:", proj_data["name"], f"({project_id})")

    print("\n[6] Testing File Upload (Source File)...")
    def upload_file(filename, filepath):
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        with open(filepath, "rb") as f:
            file_bytes = f.read()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: text/csv\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            f"{BASE_URL}/projects/{project_id}/files",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {token}"
            }
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 201
            return json.loads(resp.read().decode())

    source_file = upload_file("test_source.csv", "c:/Users/shaha/verifygrid/frontend/test_source.csv")
    print("  -> Source file uploaded:", source_file["original_filename"], f"({source_file['id']})")

    target_file = upload_file("test_target.csv", "c:/Users/shaha/verifygrid/frontend/test_target.csv")
    print("  -> Target file uploaded:", target_file["original_filename"], f"({target_file['id']})")

    print("\n[7] Testing Preprocessing Endpoint...")
    req = urllib.request.Request(
        f"{BASE_URL}/projects/{project_id}/files/{source_file['id']}/preprocess",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        prep_data = json.loads(resp.read().decode())
        print(f"  -> Preprocessing successful: {prep_data['data_rows_count']} rows, {len(prep_data['columns'])} columns detected.")

    print("\n[8] Testing Verification Reconciliation...")
    verify_payload = json.dumps({
        "source_file_id": source_file["id"],
        "target_file_id": target_file["id"],
        "key_columns": ["id"],
        "numeric_tolerance": 0.0,
        "include_identical": True
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{BASE_URL}/projects/{project_id}/verify",
        data=verify_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        verify_data = json.loads(resp.read().decode())
        summary = verify_data["summary"]
        print("  -> Verification Summary:")
        print(f"     * Matched Records: {summary['matched_records']}")
        print(f"     * Identical Matches: {summary['identical_matches']}")
        print(f"     * Field Mismatches: {summary['field_mismatches']}")
        print(f"     * Unmatched Source Records: {summary['unmatched_source_records']}")
        print(f"     * Unmatched Target Records: {summary['unmatched_target_records']}")
        print(f"     * Total Discrepancies: {summary['total_discrepancies']}")

    print("\n[9] Testing Persistent Run Creation...")
    req = urllib.request.Request(
        f"{BASE_URL}/projects/{project_id}/runs",
        data=verify_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 201
        run_data = json.loads(resp.read().decode())
        run_id = run_data["id"]
        print("  -> Persistent Run Created:", run_id, f"Status: {run_data['status']}")

    print("\n[10] Testing Discrepancy Pagination...")
    req = urllib.request.Request(
        f"{BASE_URL}/projects/{project_id}/runs/{run_id}/results",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        discrepancies_data = json.loads(resp.read().decode())
        print(f"  -> Discrepancies paginated: {discrepancies_data['total']} discrepancy items.")

    print("\n[11] Testing Reports Exports (CSV, JSON, XLSX)...")
    for fmt in ["csv", "json", "xlsx"]:
        req = urllib.request.Request(
            f"{BASE_URL}/projects/{project_id}/runs/{run_id}/export?format={fmt}",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content = resp.read()
            assert len(content) > 0
            print(f"  -> Export format '{fmt}' OK ({len(content)} bytes received).")

    print("\n[SUCCESS] ALL PIPELINE WORKFLOWS PASSED VERIFICATION!")

if __name__ == "__main__":
    test_full_pipeline()
