"""
CIVIO BUILD — Backend end-to-end API tests.
Covers: auth, RBAC, projects, assignments, progress workflow (submit/review/revise/client-decision),
weighted progress recompute, defects + severity, file upload/download, notifications,
dashboard summary, audit log.
"""
import io
import os
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://site-ledger-15.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "admin":   ("civiobuilds@gmail.com", "CivioAdmin@2026"),
    "pm":      ("pm@civio.build",        "CivioPM@2026"),
    "eng":     ("engineer@civio.build",  "CivioEng@2026"),
    "eng2":    ("engineer2@civio.build", "CivioEng@2026"),
    "client":  ("client@civio.build",    "CivioClient@2026"),
}
DEMO_PROJECT = "proj-demo-1"
DEMO_PU      = "pu-1"
DEMO_DEFECT  = "def-1"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def tokens():
    return {k: _login(*v) for k, v in CREDS.items()}


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- Auth ---------------------------------------------------------------
class TestAuth:
    def test_login_invalid_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": CREDS["admin"][0], "password": "wrong"}, timeout=10)
        assert r.status_code == 401

    @pytest.mark.parametrize("role,expected", [
        ("admin", "admin"), ("pm", "project_manager"),
        ("eng", "site_engineer"), ("client", "client"),
    ])
    def test_me_returns_role(self, tokens, role, expected):
        r = requests.get(f"{API}/auth/me", headers=H(tokens[role]), timeout=10)
        assert r.status_code == 200
        assert r.json()["role"] == expected


# --- RBAC ---------------------------------------------------------------
class TestRBAC:
    def test_client_cannot_list_users(self, tokens):
        r = requests.get(f"{API}/users", headers=H(tokens["client"]), timeout=10)
        assert r.status_code == 403

    def test_engineer_cannot_create_project(self, tokens):
        r = requests.post(f"{API}/projects", headers=H(tokens["eng"]),
                          json={"name": "x", "code": "ZZ-1"}, timeout=10)
        assert r.status_code == 403

    def test_unknown_project_id(self, tokens):
        r = requests.get(f"{API}/projects/nonexistent-id", headers=H(tokens["admin"]), timeout=10)
        assert r.status_code == 404

    def test_client_can_access_assigned_project(self, tokens):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}", headers=H(tokens["client"]), timeout=10)
        assert r.status_code == 200


# --- Project create + assignment ---------------------------------------
class TestProjectCreateAssign:
    def test_admin_creates_project_and_assigns(self, tokens):
        import uuid as _u
        code = f"TEST-{_u.uuid4().hex[:6].upper()}"
        r = requests.post(f"{API}/projects", headers=H(tokens["admin"]),
                          json={"name": f"TEST_proj {code}", "code": code, "type": "Residential"},
                          timeout=15)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]

        # Assign engineer + client
        r = requests.post(f"{API}/projects/{pid}/assign", headers=H(tokens["admin"]),
                          json={"engineer_ids": ["user-eng"], "client_id": "user-client"}, timeout=10)
        assert r.status_code == 200

        # Appears for engineer
        r = requests.get(f"{API}/projects", headers=H(tokens["eng"]), timeout=10)
        assert pid in [p["id"] for p in r.json()]
        # Appears for client
        r = requests.get(f"{API}/projects", headers=H(tokens["client"]), timeout=10)
        assert pid in [p["id"] for p in r.json()]
        # NOT visible to engineer2 (not assigned)
        r = requests.get(f"{API}/projects", headers=H(tokens["eng2"]), timeout=10)
        assert pid not in [p["id"] for p in r.json()]
        # engineer2 forbidden on direct GET
        r = requests.get(f"{API}/projects/{pid}", headers=H(tokens["eng2"]), timeout=10)
        assert r.status_code == 403


# --- Weighted progress --------------------------------------------------
class TestWeightedProgress:
    def test_demo_project_weighted_progress(self, tokens):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}", headers=H(tokens["pm"]), timeout=10)
        assert r.status_code == 200
        pct = r.json()["progress_percent"]
        acts = requests.get(f"{API}/projects/{DEMO_PROJECT}/activities",
                            headers=H(tokens["pm"]), timeout=10).json()
        total_w = sum(a.get("weight", 1) for a in acts)
        expected = round(sum(a.get("weight", 1) * a.get("progress_percent", 0) for a in acts) / total_w, 1)
        # NOT a plain average
        plain = round(sum(a.get("progress_percent", 0) for a in acts) / len(acts), 1)
        assert abs(pct - expected) < 0.2, f"weighted recompute mismatch: project={pct} expected={expected}"
        # And weighted should differ from plain average when weights are non-uniform
        assert expected != plain or len(set(a.get("weight", 1) for a in acts)) == 1


# --- Progress workflow --------------------------------------------------
class TestProgressFlow:
    def test_full_progress_workflow(self, tokens):
        # Engineer submits an update on act-3 (does NOT require client approval)
        payload = {"activity_id": "act-3", "percent_complete": 50, "notes": "TEST progress", "photo_ids": []}
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/progress-updates",
                          headers=H(tokens["eng"]), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        pu_id = r.json()["id"]
        assert r.json()["status"] == "submitted"

        # Engineer cannot review their own
        r = requests.post(f"{API}/progress-updates/{pu_id}/review",
                          headers=H(tokens["eng"]), json={"action": "approve", "comment": ""}, timeout=10)
        assert r.status_code == 403

        # PM returns for clarification
        r = requests.post(f"{API}/progress-updates/{pu_id}/review",
                          headers=H(tokens["pm"]), json={"action": "return", "comment": "add photos"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "clarification_needed"

        # Engineer submits revision
        r = requests.post(f"{API}/progress-updates/{pu_id}/revise",
                          headers=H(tokens["eng"]),
                          json={"percent_complete": 55, "notes": "revised"}, timeout=10)
        assert r.status_code == 200
        new_id = r.json()["id"]
        assert r.json()["version"] == 2
        assert r.json()["previous_version_id"] == pu_id

        # Old is superseded
        all_pus = requests.get(f"{API}/projects/{DEMO_PROJECT}/progress-updates",
                               headers=H(tokens["pm"]), timeout=10).json()
        old = next(u for u in all_pus if u["id"] == pu_id)
        assert old.get("superseded_by") == new_id

        # PM approves (no client approval needed on act-3)
        r = requests.post(f"{API}/progress-updates/{new_id}/review",
                          headers=H(tokens["pm"]), json={"action": "approve", "comment": "ok"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # Activity progress updated
        acts = requests.get(f"{API}/projects/{DEMO_PROJECT}/activities",
                            headers=H(tokens["pm"]), timeout=10).json()
        act3 = next(a for a in acts if a["id"] == "act-3")
        assert act3["progress_percent"] == 55

    def test_client_decision_requires_comment(self, tokens):
        # pu-1 is seeded pending_client_decision
        r = requests.post(f"{API}/progress-updates/{DEMO_PU}/client-decision",
                          headers=H(tokens["client"]),
                          json={"action": "approve", "comment": "   "}, timeout=10)
        assert r.status_code == 400

    def test_client_cannot_review(self, tokens):
        r = requests.post(f"{API}/progress-updates/{DEMO_PU}/review",
                          headers=H(tokens["client"]), json={"action": "approve", "comment": ""}, timeout=10)
        assert r.status_code == 403


# --- Defects ------------------------------------------------------------
class TestDefects:
    def test_engineer_raises_critical_defect(self, tokens):
        r = requests.post(f"{API}/projects/{DEMO_PROJECT}/defects",
                          headers=H(tokens["eng"]),
                          json={"location": "TEST-loc", "severity": "critical",
                                "description": "TEST critical"}, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["escalated"] is True
        assert d["severity"] == "critical"

    def test_engineer_cannot_close_defect(self, tokens):
        # try close def-1 as engineer
        r = requests.post(f"{API}/defects/{DEMO_DEFECT}/status",
                          headers=H(tokens["eng"]),
                          json={"status": "closed", "note": "x"}, timeout=10)
        assert r.status_code == 403

    def test_pm_can_transition_defect(self, tokens):
        r = requests.post(f"{API}/defects/{DEMO_DEFECT}/status",
                          headers=H(tokens["pm"]),
                          json={"status": "awaiting_verification", "note": "ready"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "awaiting_verification"


# --- Files --------------------------------------------------------------
class TestFiles:
    def test_upload_and_download(self, tokens):
        # minimal PNG
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
               b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0"
               b"\x00\x00\x00\x03\x00\x01\x5b\x8f\xa7\xa0\x00\x00\x00\x00IEND\xaeB`\x82")
        files = {"file": ("test.png", io.BytesIO(png), "image/png")}
        r = requests.post(f"{API}/files/upload",
                          headers=H(tokens["eng"]),
                          files=files,
                          data={"project_id": DEMO_PROJECT, "caption": "TEST"},
                          timeout=20)
        assert r.status_code == 200, r.text
        fid = r.json()["id"]

        # Download with ?auth=
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['eng']}", timeout=15)
        assert r.status_code == 200
        assert len(r.content) > 0

        # engineer2 is on the project (assigned to demo) so has access too; test with Authorization header
        r = requests.get(f"{API}/files/{fid}/download",
                         headers=H(tokens["pm"]), timeout=15)
        assert r.status_code == 200


# --- Notifications ------------------------------------------------------
class TestNotifications:
    def test_list_and_read(self, tokens):
        r = requests.get(f"{API}/notifications", headers=H(tokens["client"]), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "unread" in data

    def test_read_all(self, tokens):
        r = requests.post(f"{API}/notifications/read-all",
                          headers=H(tokens["client"]), timeout=10)
        assert r.status_code == 200


# --- Dashboard summary --------------------------------------------------
class TestDashboard:
    def test_pm_summary(self, tokens):
        r = requests.get(f"{API}/dashboard/summary", headers=H(tokens["pm"]), timeout=10)
        assert r.status_code == 200
        s = r.json()
        for k in ["projects", "pending_reviews", "open_defects"]:
            assert k in s

    def test_client_summary(self, tokens):
        r = requests.get(f"{API}/dashboard/summary", headers=H(tokens["client"]), timeout=10)
        assert r.status_code == 200
        assert "pending_client_decisions" in r.json()


# --- Audit log ---------------------------------------------------------
class TestAudit:
    def test_pm_audit(self, tokens):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}/audit-log",
                         headers=H(tokens["pm"]), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) > 0

    def test_client_cannot_view_audit(self, tokens):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}/audit-log",
                         headers=H(tokens["client"]), timeout=10)
        assert r.status_code == 403

    def test_engineer_cannot_view_audit(self, tokens):
        r = requests.get(f"{API}/projects/{DEMO_PROJECT}/audit-log",
                         headers=H(tokens["eng"]), timeout=10)
        assert r.status_code == 403
