"""
CIVIO BUILD — Backend tests for iteration-3 features:
Procurement (material requests, suppliers, purchase orders), Cost Summary,
PDF Reports, Shared-Photo Scoping (client), Audit CSV Export.
"""
import io
import os
import uuid
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent.parent / "frontend" / ".env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"

CREDS = {
    "admin":  ("civiobuilds@gmail.com", "CivioAdmin@2026"),
    "pm":     ("pm@civio.build",        "CivioPM@2026"),
    "eng":    ("engineer@civio.build",  "CivioEng@2026"),
    "eng2":   ("engineer2@civio.build", "CivioEng@2026"),
    "client": ("client@civio.build",    "CivioClient@2026"),
}
PROJECT = "proj-demo-1"
TIMEOUT = 20


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=TIMEOUT)
    assert r.status_code == 200, f"login failed: {email} {r.status_code} {r.text}"
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def tokens():
    toks = {k: _login(*v) for k, v in CREDS.items()}
    # Create a fresh "outsider" PM (no project link) via admin
    email = f"test_outpm_{uuid.uuid4().hex[:6]}@civio.build"
    pwd = "OutsiderPM@2026"
    r = requests.post(f"{API}/users", headers=H(toks["admin"]), json={
        "name": "TEST Outsider PM", "email": email, "password": pwd,
        "role": "project_manager"
    }, timeout=TIMEOUT)
    assert r.status_code in (200, 201), r.text
    toks["outpm"] = _login(email, pwd)
    return toks


# ---------------------------------------------------------------------------
# PROCUREMENT: material requests
# ---------------------------------------------------------------------------
class TestMaterialRequests:
    def test_engineer_creates_mr_pm_authorizes(self, tokens):
        payload = {"item": "TEST_sand", "quantity": 2.5, "unit": "truckloads",
                   "needed_by": "2026-02-01", "notes": "TEST mr auth"}
        r = requests.post(f"{API}/projects/{PROJECT}/material-requests",
                          headers=H(tokens["eng"]), json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        mr = r.json()
        assert mr["status"] == "requested"
        assert mr["item"] == "TEST_sand"
        mid = mr["id"]

        r = requests.post(f"{API}/material-requests/{mid}/decision",
                          headers=H(tokens["pm"]),
                          json={"action": "authorize", "comment": "ok"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "authorized"

    def test_engineer_creates_mr_pm_rejects(self, tokens):
        payload = {"item": "TEST_reject_item", "quantity": 1, "unit": "nos", "notes": ""}
        r = requests.post(f"{API}/projects/{PROJECT}/material-requests",
                          headers=H(tokens["eng"]), json=payload, timeout=TIMEOUT)
        assert r.status_code == 200
        mid = r.json()["id"]
        r = requests.post(f"{API}/material-requests/{mid}/decision",
                          headers=H(tokens["pm"]),
                          json={"action": "reject", "comment": "nope"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_client_cannot_create_mr(self, tokens):
        r = requests.post(f"{API}/projects/{PROJECT}/material-requests",
                          headers=H(tokens["client"]),
                          json={"item": "x", "quantity": 1, "unit": "nos"}, timeout=TIMEOUT)
        assert r.status_code == 403

    def test_outsider_pm_cannot_decide(self, tokens):
        # create one as engineer
        r = requests.post(f"{API}/projects/{PROJECT}/material-requests",
                          headers=H(tokens["eng"]),
                          json={"item": "TEST_outpm_mr", "quantity": 1, "unit": "nos"}, timeout=TIMEOUT)
        assert r.status_code == 200
        mid = r.json()["id"]
        r = requests.post(f"{API}/material-requests/{mid}/decision",
                          headers=H(tokens["outpm"]),
                          json={"action": "authorize", "comment": "steal"}, timeout=TIMEOUT)
        assert r.status_code == 403

    def test_list_requires_project_access(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/material-requests",
                         headers=H(tokens["outpm"]), timeout=TIMEOUT)
        assert r.status_code == 403
        # assigned engineer can list
        r = requests.get(f"{API}/projects/{PROJECT}/material-requests",
                         headers=H(tokens["eng"]), timeout=TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# SUPPLIERS
# ---------------------------------------------------------------------------
class TestSuppliers:
    def test_pm_creates_supplier(self, tokens):
        payload = {"name": f"TEST_Supplier_{uuid.uuid4().hex[:5]}", "contact": "99", "categories": "cement"}
        r = requests.post(f"{API}/suppliers", headers=H(tokens["pm"]), json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == payload["name"]

    def test_list_suppliers_pm(self, tokens):
        r = requests.get(f"{API}/suppliers", headers=H(tokens["pm"]), timeout=TIMEOUT)
        assert r.status_code == 200
        names = [s["name"] for s in r.json()]
        assert any("UltraTech" in n or "Tata" in n for n in names)

    def test_engineer_forbidden_suppliers(self, tokens):
        r = requests.get(f"{API}/suppliers", headers=H(tokens["eng"]), timeout=TIMEOUT)
        assert r.status_code == 403
        r = requests.post(f"{API}/suppliers", headers=H(tokens["eng"]),
                          json={"name": "x"}, timeout=TIMEOUT)
        assert r.status_code == 403

    def test_client_forbidden_suppliers(self, tokens):
        r = requests.get(f"{API}/suppliers", headers=H(tokens["client"]), timeout=TIMEOUT)
        assert r.status_code == 403
        r = requests.post(f"{API}/suppliers", headers=H(tokens["client"]),
                          json={"name": "x"}, timeout=TIMEOUT)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# PURCHASE ORDERS
# ---------------------------------------------------------------------------
class TestPurchaseOrders:
    def test_pm_creates_po_math(self, tokens):
        payload = {
            "supplier_id": "sup-1",
            "items": [
                {"description": "TEST cement", "quantity": 10, "unit": "bags", "rate": 350},
                {"description": "TEST sand",   "quantity": 2,  "unit": "trk",  "rate": 1500},
            ],
            "notes": "TEST PO"
        }
        r = requests.post(f"{API}/projects/{PROJECT}/purchase-orders",
                          headers=H(tokens["pm"]), json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        po = r.json()
        assert po["items"][0]["amount"] == 10 * 350
        assert po["items"][1]["amount"] == 2 * 1500
        assert po["total_amount"] == 10 * 350 + 2 * 1500
        assert po["po_number"].startswith("PO-")
        assert po["status"] == "draft"
        assert po["invoice_status"] == "pending"
        # status update
        r = requests.post(f"{API}/purchase-orders/{po['id']}/status",
                          headers=H(tokens["pm"]),
                          json={"status": "approved", "invoice_status": "pending",
                                "note": "approved"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_engineer_cannot_create_po(self, tokens):
        r = requests.post(f"{API}/projects/{PROJECT}/purchase-orders",
                          headers=H(tokens["eng"]),
                          json={"supplier_id": "sup-1", "items": []}, timeout=TIMEOUT)
        assert r.status_code == 403

    def test_client_cannot_create_po(self, tokens):
        r = requests.post(f"{API}/projects/{PROJECT}/purchase-orders",
                          headers=H(tokens["client"]),
                          json={"supplier_id": "sup-1", "items": []}, timeout=TIMEOUT)
        assert r.status_code == 403

    def test_engineer_cannot_update_po(self, tokens):
        # list to find a seeded one
        r = requests.get(f"{API}/projects/{PROJECT}/purchase-orders",
                         headers=H(tokens["pm"]), timeout=TIMEOUT)
        pos = r.json()
        assert len(pos) >= 2
        po_id = pos[0]["id"]
        r = requests.post(f"{API}/purchase-orders/{po_id}/status",
                          headers=H(tokens["eng"]),
                          json={"status": "cancelled"}, timeout=TIMEOUT)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# COST SUMMARY
# ---------------------------------------------------------------------------
class TestCostSummary:
    def test_pm_cost_summary_math(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/cost-summary",
                         headers=H(tokens["pm"]), timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        # Seeded expected minimum from po-1 (accepted,paid,492000) + po-2 (ordered,pending,544000)
        assert d["budget"] == 42500000
        # Other TEST POs added above will also be in committed if status != draft; po-1 and po-2 give 1036000 minimum from accepted/ordered
        # Our TEST PO above is in 'approved' status => also counted in committed.
        # So committed >= 1036000, actual >= 492000. Verify math holds among seeded ones at least.
        assert d["committed"] >= 1036000
        assert d["actual"] >= 492000
        assert d["forecast"] == max(d["committed"], d["actual"])
        assert d["variance"] == round(d["budget"] - d["forecast"], 2)

    def test_client_with_budget_visible_can_access(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/cost-summary",
                         headers=H(tokens["client"]), timeout=TIMEOUT)
        assert r.status_code == 200
        assert "budget" in r.json()


# ---------------------------------------------------------------------------
# PDF REPORTS
# ---------------------------------------------------------------------------
REPORT_IDS = {}


class TestReports:
    @pytest.mark.parametrize("rtype,extra", [
        ("progress", {}),
        ("completion", {"recommendations": "TEST handover notes"}),
        ("cost", {}),
    ])
    def test_pm_generates_report(self, tokens, rtype, extra):
        body = {"type": rtype, **extra}
        r = requests.post(f"{API}/projects/{PROJECT}/reports",
                          headers=H(tokens["pm"]), json=body, timeout=60)
        assert r.status_code == 200, r.text
        rec = r.json()
        assert rec["type"] == rtype
        assert rec["revision"].startswith(rtype[:3].upper() + "-")
        assert rec["size"] > 0
        REPORT_IDS[rtype] = rec["id"]

    def test_list_reports_newest_first(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/reports",
                         headers=H(tokens["pm"]), timeout=TIMEOUT)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 3
        for i in range(len(rows) - 1):
            assert rows[i]["generated_at"] >= rows[i + 1]["generated_at"]

    def test_download_returns_pdf(self, tokens):
        rid = REPORT_IDS.get("progress")
        assert rid, "progress report missing"
        # Header auth
        r = requests.get(f"{API}/reports/{rid}/download",
                         headers=H(tokens["pm"]), timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content.startswith(b"%PDF")
        # ?auth= query param
        r = requests.get(f"{API}/reports/{rid}/download?auth={tokens['pm']}", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")

    def test_engineer_cannot_generate_report(self, tokens):
        r = requests.post(f"{API}/projects/{PROJECT}/reports",
                          headers=H(tokens["eng"]), json={"type": "progress"}, timeout=TIMEOUT)
        assert r.status_code == 403

    def test_client_cannot_generate_report(self, tokens):
        r = requests.post(f"{API}/projects/{PROJECT}/reports",
                          headers=H(tokens["client"]), json={"type": "progress"}, timeout=TIMEOUT)
        assert r.status_code == 403

    def test_client_can_list_and_download(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/reports",
                         headers=H(tokens["client"]), timeout=TIMEOUT)
        assert r.status_code == 200
        rid = REPORT_IDS.get("progress")
        r = requests.get(f"{API}/reports/{rid}/download?auth={tokens['client']}", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")

    def test_outsider_cannot_download(self, tokens):
        rid = REPORT_IDS.get("progress")
        r = requests.get(f"{API}/reports/{rid}/download",
                         headers=H(tokens["outpm"]), timeout=TIMEOUT)
        assert r.status_code == 403

    def test_invalid_report_type(self, tokens):
        r = requests.post(f"{API}/projects/{PROJECT}/reports",
                          headers=H(tokens["pm"]), json={"type": "bogus"}, timeout=TIMEOUT)
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# SHARED-PHOTO SCOPING
# ---------------------------------------------------------------------------
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0"
       b"\x00\x00\x00\x03\x00\x01\x5b\x8f\xa7\xa0\x00\x00\x00\x00IEND\xaeB`\x82")


class TestClientPhotoScoping:
    def test_submitted_update_photo_hidden_from_client(self, tokens):
        # engineer uploads a photo
        files = {"file": ("hidden.png", io.BytesIO(PNG), "image/png")}
        r = requests.post(f"{API}/files/upload",
                          headers=H(tokens["eng"]), files=files,
                          data={"project_id": PROJECT, "caption": "TEST hidden"}, timeout=TIMEOUT)
        assert r.status_code == 200
        fid = r.json()["id"]

        # attach to a NEW submitted progress update on act-3
        r = requests.post(f"{API}/projects/{PROJECT}/progress-updates",
                          headers=H(tokens["eng"]),
                          json={"activity_id": "act-3", "percent_complete": 60,
                                "notes": "TEST submitted update", "photo_ids": [fid]},
                          timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "submitted"

        # client photo list must NOT contain fid
        r = requests.get(f"{API}/projects/{PROJECT}/photos",
                         headers=H(tokens["client"]), timeout=TIMEOUT)
        assert r.status_code == 200
        assert fid not in [f["id"] for f in r.json()]

        # client cannot download
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['client']}", timeout=TIMEOUT)
        assert r.status_code == 403

        # engineer still can download
        r = requests.get(f"{API}/files/{fid}/download?auth={tokens['eng']}", timeout=TIMEOUT)
        assert r.status_code == 200

        # PM (manager) sees it in gallery
        r = requests.get(f"{API}/projects/{PROJECT}/photos",
                         headers=H(tokens["pm"]), timeout=TIMEOUT)
        assert fid in [f["id"] for f in r.json()]

    def test_pending_client_decision_photos_visible_to_client(self, tokens):
        # pu-1 is seeded pending_client_decision. Fetch and verify any photos it has are
        # exposed to client. Even if no photos, this at least confirms endpoint works.
        r = requests.get(f"{API}/projects/{PROJECT}/progress-updates",
                         headers=H(tokens["client"]), timeout=TIMEOUT)
        assert r.status_code == 200
        pu1 = next((p for p in r.json() if p["id"] == "pu-1"), None)
        if pu1 and pu1.get("photo_ids"):
            r = requests.get(f"{API}/projects/{PROJECT}/photos",
                             headers=H(tokens["client"]), timeout=TIMEOUT)
            visible_ids = [f["id"] for f in r.json()]
            for pid in pu1["photo_ids"]:
                assert pid in visible_ids, f"client should see pending-decision photo {pid}"


# ---------------------------------------------------------------------------
# AUDIT CSV EXPORT
# ---------------------------------------------------------------------------
class TestAuditCSVExport:
    def test_admin_exports_csv_header_auth(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/audit-log/export",
                         headers=H(tokens["admin"]), timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/csv")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and ".csv" in cd
        # timestamp in filename pattern _YYYYMMDD_HHMMSS
        import re
        assert re.search(r"\d{8}_\d{6}", cd), f"no timestamp in {cd}"
        text = r.content.decode()
        header_line = text.splitlines()[0]
        assert header_line == "Timestamp (UTC),Actor,Action,Entity Type,Entity ID,Details"

    def test_admin_exports_csv_query_auth(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/audit-log/export?auth={tokens['admin']}", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/csv")

    def test_pm_forbidden(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/audit-log/export",
                         headers=H(tokens["pm"]), timeout=TIMEOUT)
        assert r.status_code == 403

    def test_engineer_forbidden(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/audit-log/export",
                         headers=H(tokens["eng"]), timeout=TIMEOUT)
        assert r.status_code == 403

    def test_client_forbidden(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/audit-log/export",
                         headers=H(tokens["client"]), timeout=TIMEOUT)
        assert r.status_code == 403

    def test_invalid_token_query(self, tokens):
        r = requests.get(f"{API}/projects/{PROJECT}/audit-log/export?auth=garbage", timeout=TIMEOUT)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# QUICK REGRESSION
# ---------------------------------------------------------------------------
class TestRegression:
    def test_login_all_roles(self, tokens):
        for role in ["admin", "pm", "eng", "client"]:
            r = requests.get(f"{API}/auth/me", headers=H(tokens[role]), timeout=TIMEOUT)
            assert r.status_code == 200

    def test_dashboard_summary(self, tokens):
        r = requests.get(f"{API}/dashboard/summary", headers=H(tokens["pm"]), timeout=TIMEOUT)
        assert r.status_code == 200

    def test_project_list(self, tokens):
        r = requests.get(f"{API}/projects", headers=H(tokens["pm"]), timeout=TIMEOUT)
        assert r.status_code == 200
        assert any(p["id"] == PROJECT for p in r.json())
