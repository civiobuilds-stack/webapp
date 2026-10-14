"""
CIVIO BUILD — Authorization / IDOR audit tests.
Verifies role-based + project-level access control on backend for every read and write.
Creates a SECOND project with a freshly registered client/engineer to prove cross-tenant isolation.
"""
import io
import os
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin":  ("civiobuilds@gmail.com", "CivioAdmin@2026"),
    "pm":     ("pm@civio.build",        "CivioPM@2026"),
    "eng":    ("engineer@civio.build",  "CivioEng@2026"),
    "eng2":   ("engineer2@civio.build", "CivioEng@2026"),
    "client": ("client@civio.build",    "CivioClient@2026"),
}
DEMO_PROJECT = "proj-demo-1"
DEMO_PU = "pu-1"
DEMO_DEFECT = "def-1"


def _login(email, password):
    if email.startswith("test_"):
        from pymongo import MongoClient
        MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].users.update_one(
            {"email": email.lower()}, {"$set": {"email_verified": True}})
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _register(email, password, name, role):
    requests.post(f"{API}/auth/register",
                  json={"email": email, "password": password, "name": name, "role": role, "phone": "+910000000000"},
                  timeout=15)
    from pymongo import MongoClient
    MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].users.update_one(
        {"email": email.lower()}, {"$set": {"email_verified": True}})
    return _login(email, password)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def tokens():
    toks = {k: _login(*v) for k, v in CREDS.items()}
    # Create an outsider client + outsider engineer who have NO link to any seeded project
    uid = uuid.uuid4().hex[:8]
    toks["outsider_client"] = _register(f"test_outclient_{uid}@civio.build", "OutsiderPwd@1",
                                        "TEST Outside Client", "client")
    toks["outsider_eng"] = _register(f"test_outeng_{uid}@civio.build", "OutsiderPwd@1",
                                     "TEST Outside Engineer", "site_engineer")
    return toks


@pytest.fixture(scope="session")
def second_project(tokens):
    """Admin creates a SECOND project with NO engineers/client attached - truly isolated."""
    code = f"TEST-ISO-{uuid.uuid4().hex[:6].upper()}"
    r = requests.post(f"{API}/projects", headers=H(tokens["admin"]),
                      json={"name": f"TEST isolated {code}", "code": code, "type": "Residential"},
                      timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# PROJECT IDOR
# ---------------------------------------------------------------------------
class TestProjectIDOR:
    def test_client_list_only_own_projects(self, tokens):
        r = requests.get(f"{API}/projects", headers=H(tokens["client"]), timeout=10)
        assert r.status_code == 200
        for p in r.json():
            assert p.get("client_id") == "user-client", f"Client sees foreign project {p['id']}"

    def test_client_cannot_access_second_project(self, tokens, second_project):
        r = requests.get(f"{API}/projects/{second_project}", headers=H(tokens["client"]), timeout=10)
        assert r.status_code in (403, 404), f"IDOR: client sees unrelated project ({r.status_code})"

    def test_outsider_client_cannot_access_demo(self, tokens):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}", headers=H(tokens["outsider_client"]), timeout=10)
        assert r.status_code in (403, 404)

    def test_outsider_client_list_empty(self, tokens):
        r = requests.get(f"{API}/projects", headers=H(tokens["outsider_client"]), timeout=10)
        assert r.status_code == 200
        assert r.json() == [] or all(p["id"] != DEMO_PROJECT for p in r.json())


# ---------------------------------------------------------------------------
# ENGINEER IDOR + role restrictions
# ---------------------------------------------------------------------------
class TestEngineerIDOR:
    def test_engineer_list_only_assigned(self, tokens):
        r = requests.get(f"{API}/projects", headers=H(tokens["eng"]), timeout=10)
        assert r.status_code == 200
        for p in r.json():
            assert "user-eng" in p.get("engineer_ids", []), f"Engineer sees unassigned proj {p['id']}"

    def test_engineer_cannot_get_unassigned_project(self, tokens, second_project):
        r = requests.get(f"{API}/projects/{second_project}", headers=H(tokens["eng"]), timeout=10)
        assert r.status_code in (403, 404)

    def test_outsider_engineer_cannot_access_demo(self, tokens):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}", headers=H(tokens["outsider_eng"]), timeout=10)
        assert r.status_code in (403, 404)

    def test_engineer_cannot_create_project(self, tokens):
        r = requests.post(f"{API}/projects", headers=H(tokens["eng"]),
                          json={"name": "x", "code": f"ENG-{uuid.uuid4().hex[:6]}"}, timeout=10)
        assert r.status_code == 403

    def test_engineer_cannot_assign(self, tokens):
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/assign", headers=H(tokens["eng"]),
                          json={"engineer_ids": ["user-eng"]}, timeout=10)
        assert r.status_code == 403

    def test_engineer_cannot_archive(self, tokens):
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/archive", headers=H(tokens["eng"]), timeout=10)
        assert r.status_code == 403

    def test_engineer_cannot_list_users(self, tokens):
        r = requests.get(f"{API}/users", headers=H(tokens["eng"]), timeout=10)
        assert r.status_code == 403

    def test_engineer_cannot_view_audit(self, tokens):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}/audit-log", headers=H(tokens["eng"]), timeout=10)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# CLIENT write restrictions
# ---------------------------------------------------------------------------
class TestClientWriteRestrictions:
    def test_client_cannot_post_activity(self, tokens):
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/activities", headers=H(tokens["client"]),
                          json={"name": "x"}, timeout=10)
        assert r.status_code == 403

    def test_client_cannot_post_milestone(self, tokens):
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/milestones", headers=H(tokens["client"]),
                          json={"name": "x"}, timeout=10)
        assert r.status_code == 403

    def test_client_cannot_post_defect(self, tokens):
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/defects", headers=H(tokens["client"]),
                          json={"location": "x", "description": "x"}, timeout=10)
        assert r.status_code == 403

    def test_client_cannot_post_progress_update(self, tokens):
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/progress-updates", headers=H(tokens["client"]),
                          json={"activity_id": "act-1", "percent_complete": 10}, timeout=10)
        assert r.status_code == 403

    def test_client_cannot_upload_with_project_id(self, tokens):
        files = {"file": ("x.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")}
        r = requests.post(f"{API}/files/upload", headers=H(tokens["client"]),
                          files=files, data={"project_id": DEMO_PROJECT}, timeout=15)
        assert r.status_code == 403

    def test_client_cannot_upload_orphan(self, tokens):
        files = {"file": ("x.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")}
        r = requests.post(f"{API}/files/upload", headers=H(tokens["client"]),
                          files=files, timeout=15)
        assert r.status_code == 403

    def test_client_cannot_update_defect_status(self, tokens):
        r = requests.post(f"{API}/defects/{DEMO_DEFECT}/status", headers=H(tokens["client"]),
                          json={"status": "in_progress"}, timeout=10)
        assert r.status_code == 403

    def test_client_cannot_create_project(self, tokens):
        r = requests.post(f"{API}/projects", headers=H(tokens["client"]),
                          json={"name": "x", "code": f"CL-{uuid.uuid4().hex[:6]}"}, timeout=10)
        assert r.status_code == 403

    def test_client_cannot_assign(self, tokens):
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/assign", headers=H(tokens["client"]),
                          json={"engineer_ids": []}, timeout=10)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# PROGRESS-UPDATE object-level auth
# ---------------------------------------------------------------------------
class TestProgressObjectAuth:
    def test_other_pm_cannot_review(self, tokens, second_project):
        """PM (seeded pm) does NOT manage second_project (admin created it, pm is not manager).
        Submit a progress update via admin-flow... but second_project has no engineer.
        Instead: create an update on demo via engineer, then try outsider PM — we only have one PM.
        Workaround: create a second PM via admin."""
        # Create a second PM
        uid = uuid.uuid4().hex[:6]
        r = requests.post(f"{API}/users", headers=H(tokens["admin"]),
                          json={"email": f"test_pm2_{uid}@civio.build", "password": "Pm2Pwd@1",
                                "name": "TEST PM2", "role": "project_manager"}, timeout=10)
        assert r.status_code == 200, r.text
        pm2_token = _login(f"test_pm2_{uid}@civio.build", "Pm2Pwd@1")

        # Engineer submits a progress update on the demo project
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/progress-updates",
                          headers=H(tokens["eng"]),
                          json={"activity_id": "act-3", "percent_complete": 60, "notes": "TEST pm-isolation"},
                          timeout=15)
        assert r.status_code == 200, r.text
        pu_id = r.json()["id"]

        # pm2 does NOT manage demo project → review must be 403
        r = requests.post(f"{API}/progress-updates/{pu_id}/review",
                          headers=H(pm2_token),
                          json={"action": "approve", "comment": "sneaky"}, timeout=10)
        assert r.status_code == 403, f"IDOR: foreign PM reviewed update ({r.status_code})"

    def test_other_client_cannot_decide(self, tokens):
        # outsider_client is not linked to proj-demo-1
        r = requests.post(f"{API}/progress-updates/{DEMO_PU}/client-decision",
                          headers=H(tokens["outsider_client"]),
                          json={"action": "approve", "comment": "foreign"}, timeout=10)
        assert r.status_code == 403

    def test_engineer_cannot_revise_other_engineers_update(self, tokens):
        # pu-1 is seeded engineer=user-eng (Anita). eng2 should not revise it.
        r = requests.post(f"{API}/progress-updates/{DEMO_PU}/revise",
                          headers=H(tokens["eng2"]),
                          json={"percent_complete": 70}, timeout=10)
        assert r.status_code == 403

    def test_outsider_engineer_cannot_revise(self, tokens):
        r = requests.post(f"{API}/progress-updates/{DEMO_PU}/revise",
                          headers=H(tokens["outsider_eng"]),
                          json={"percent_complete": 70}, timeout=10)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# DEFECT object-level auth
# ---------------------------------------------------------------------------
class TestDefectObjectAuth:
    def test_outsider_cannot_change_defect_status(self, tokens):
        r = requests.post(f"{API}/defects/{DEMO_DEFECT}/status",
                          headers=H(tokens["outsider_eng"]),
                          json={"status": "in_progress"}, timeout=10)
        assert r.status_code == 403

    def test_engineer_cannot_close_defect(self, tokens):
        # engineer has write access to project but cannot CLOSE
        r = requests.post(f"{API}/defects/{DEMO_DEFECT}/status",
                          headers=H(tokens["eng"]),
                          json={"status": "closed"}, timeout=10)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# FILE access control
# ---------------------------------------------------------------------------
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0"
       b"\x00\x00\x00\x03\x00\x01\x5b\x8f\xa7\xa0\x00\x00\x00\x00IEND\xaeB`\x82")


class TestFileAccessControl:
    def test_engineer_upload_project_file(self, tokens):
        files = {"file": ("x.png", io.BytesIO(PNG), "image/png")}
        r = requests.post(f"{API}/files/upload", headers=H(tokens["eng"]),
                          files=files, data={"project_id": DEMO_PROJECT}, timeout=20)
        assert r.status_code == 200
        pytest.fid_project = r.json()["id"]

    def test_outsider_cannot_download_project_file(self, tokens):
        fid = pytest.fid_project
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['outsider_eng']}", timeout=15)
        assert r.status_code in (403, 404)

    def test_outsider_client_cannot_download(self, tokens):
        fid = pytest.fid_project
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['outsider_client']}", timeout=15)
        assert r.status_code in (403, 404)

    def test_pm_can_download_project_file(self, tokens):
        fid = pytest.fid_project
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['pm']}", timeout=15)
        assert r.status_code == 200

    def test_orphan_file_only_uploader_or_manager(self, tokens):
        # PM uploads an orphan file (no project_id)
        files = {"file": ("orph.png", io.BytesIO(PNG), "image/png")}
        r = requests.post(f"{API}/files/upload", headers=H(tokens["pm"]),
                          files=files, timeout=15)
        assert r.status_code == 200
        fid = r.json()["id"]

        # Uploader (pm) can download
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['pm']}", timeout=15)
        assert r.status_code == 200

        # Admin (manager role) can download
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['admin']}", timeout=15)
        assert r.status_code == 200

        # Engineer (not uploader, not manager) cannot
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['eng']}", timeout=15)
        assert r.status_code == 403

        # Outsider client cannot
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['outsider_client']}", timeout=15)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Project sub-resource reads (photos/activities/milestones/defects/pu/audit)
# ---------------------------------------------------------------------------
class TestSubresourceReads:
    @pytest.mark.parametrize("path", [
        "photos", "activities", "milestones", "defects", "progress-updates",
    ])
    def test_outsider_client_blocked(self, tokens, path):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}/{path}",
                         headers=H(tokens["outsider_client"]), timeout=10)
        assert r.status_code in (403, 404), f"{path} leaked to outsider client"

    @pytest.mark.parametrize("path", [
        "photos", "activities", "milestones", "defects", "progress-updates", "audit-log",
    ])
    def test_outsider_engineer_blocked(self, tokens, path):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}/{path}",
                         headers=H(tokens["outsider_eng"]), timeout=10)
        assert r.status_code in (403, 404), f"{path} leaked to outsider engineer"


# ---------------------------------------------------------------------------
# Dashboard summary scope
# ---------------------------------------------------------------------------
class TestDashboardScope:
    def test_outsider_client_dashboard_empty(self, tokens):
        r = requests.get(f"{API}/dashboard/summary", headers=H(tokens["outsider_client"]), timeout=10)
        assert r.status_code == 200
        s = r.json()
        assert s["projects"] == 0
        assert s["open_defects"] == 0

    def test_outsider_engineer_dashboard_empty(self, tokens):
        r = requests.get(f"{API}/dashboard/summary", headers=H(tokens["outsider_eng"]), timeout=10)
        assert r.status_code == 200
        assert r.json()["projects"] == 0


# ---------------------------------------------------------------------------
# Positive paths still work
# ---------------------------------------------------------------------------
class TestPositivePaths:
    def test_admin_end_to_end(self, tokens):
        """Admin creates a project, assigns an engineer+client, both can see it."""
        code = f"TEST-POS-{uuid.uuid4().hex[:6].upper()}"
        r = requests.post(f"{API}/projects", headers=H(tokens["admin"]),
                          json={"name": f"TEST pos {code}", "code": code}, timeout=15)
        assert r.status_code == 200
        pid = r.json()["id"]

        # assign existing demo engineer + client
        r = requests.post(f"{API}/projects/{pid}/assign", headers=H(tokens["admin"]),
                          json={"engineer_ids": ["user-eng"], "client_id": "user-client"}, timeout=10)
        assert r.status_code == 200

        # Engineer sees it
        r = requests.get(f"{API}/projects/{pid}", headers=H(tokens["eng"]), timeout=10)
        assert r.status_code == 200
        # Client sees it
        r = requests.get(f"{API}/projects/{pid}", headers=H(tokens["client"]), timeout=10)
        assert r.status_code == 200

    def test_pm_can_still_review_own_project(self, tokens):
        """Legitimate PM review on demo project should still work."""
        # Submit new update
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/progress-updates",
                          headers=H(tokens["eng"]),
                          json={"activity_id": "act-3", "percent_complete": 65, "notes": "TEST pos pm"},
                          timeout=15)
        assert r.status_code == 200
        pu_id = r.json()["id"]
        # PM returns it (safe no-op for weighted progress)
        r = requests.post(f"{API}/progress-updates/{pu_id}/review", headers=H(tokens["pm"]),
                          json={"action": "return", "comment": "ok test"}, timeout=10)
        assert r.status_code == 200
