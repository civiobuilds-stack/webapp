"""Iteration-7b: Store (material/tool requests, issue/return, receive, stock, transactions),
BOQ CRUD and DPR BOQ linkage, Labour attendance with geofence (inside/outside).
Scope: commercial workspace, project proj-demo-1, enterprise civio.
"""
import io
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests
from pymongo import MongoClient


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
    assert v
    return v.rstrip("/") + "/api"


BASE = _base()
MONGO = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = MONGO[os.environ.get("DB_NAME", "test_database")]
IST = ZoneInfo("Asia/Kolkata")
PID = "proj-demo-1"

SA_EMAIL = "civiobuilds@gmail.com"
SA_PASS = "CivioAdmin@2026"
NEW_SA_PASS = "CivioAdmin@2026X"
PM = ("pm@civio.build", "CivioPM@2026")
ENG = ("engineer@civio.build", "CivioEng@2026")


def login(email, pw):
    for p in (pw, SA_PASS, NEW_SA_PASS) if email == SA_EMAIL else (pw,):
        r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": p})
        if r.status_code == 200:
            tok = r.json()["access_token"]
            if email == SA_EMAIL:
                me = requests.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
                if me.get("must_change_password") and p != NEW_SA_PASS:
                    cr = requests.post(f"{BASE}/auth/change-password",
                                       headers={"Authorization": f"Bearer {tok}"},
                                       json={"current_password": p, "new_password": NEW_SA_PASS})
                    assert cr.status_code == 200, cr.text
            return tok
    raise AssertionError(f"login {email} failed")


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def _upload_photo(tok, pid):
    """Upload a 1x1 PNG attached to the project; return file_id."""
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
           b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x5c\xcd\xff\x69\x00\x00\x00\x00IEND\xaeB`\x82")
    r = requests.post(f"{BASE}/files/upload", headers=H(tok),
                      files={"file": ("x.png", io.BytesIO(png), "image/png")},
                      data={"project_id": pid})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def admin():
    import subprocess
    subprocess.run(["python3", "/app/backend/scripts/reset_superadmin.py"],
                   check=True, capture_output=True)
    return login(SA_EMAIL, SA_PASS)


@pytest.fixture(scope="module")
def pm():
    return login(*PM)


@pytest.fixture(scope="module")
def eng():
    return login(*ENG)


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    DB.store_requests.delete_many({"project_id": PID})
    DB.store_stock.delete_many({"project_id": PID})
    DB.store_txns.delete_many({"project_id": PID})
    DB.boq_items.delete_many({"project_id": PID})
    DB.labour_attendance.delete_many({"project_id": PID})
    DB.projects.update_one({"id": PID}, {"$unset": {"geofence": ""}})
    yield
    DB.store_requests.delete_many({"project_id": PID})
    DB.store_stock.delete_many({"project_id": PID})
    DB.store_txns.delete_many({"project_id": PID})
    DB.boq_items.delete_many({"project_id": PID})
    DB.labour_attendance.delete_many({"project_id": PID})
    DB.projects.update_one({"id": PID}, {"$unset": {"geofence": ""}})


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------
class TestStore:
    def test_full_store_flow(self, admin, pm, eng):
        # Engineer creates material request
        r = requests.post(f"{BASE}/projects/{PID}/store/requests", headers=H(eng),
                          json={"kind": "material", "item": "Cement", "quantity": 10, "unit": "bag",
                                "remarks": "Column casting"})
        assert r.status_code == 200, r.text
        mat_id = r.json()["id"]
        assert r.json()["status"] == "requested"

        # tool without expected_return -> 400
        r = requests.post(f"{BASE}/projects/{PID}/store/requests", headers=H(eng),
                          json={"kind": "tool", "item": "Drill", "quantity": 2, "unit": "nos", "remarks": ""})
        assert r.status_code == 400

        # tool with expected_return ok
        r = requests.post(f"{BASE}/projects/{PID}/store/requests", headers=H(eng),
                          json={"kind": "tool", "item": "Drill", "quantity": 2, "unit": "nos",
                                "expected_return": "2026-12-31", "remarks": ""})
        assert r.status_code == 200
        tool_id = r.json()["id"]

        # Engineer (no approve perm) cannot approve
        r = requests.post(f"{BASE}/store/requests/{mat_id}/decision", headers=H(eng),
                          json={"action": "approve"})
        assert r.status_code == 403

        # PM approves material and tool
        r = requests.post(f"{BASE}/store/requests/{mat_id}/decision", headers=H(pm),
                          json={"action": "approve"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # second decision on same -> 400
        r = requests.post(f"{BASE}/store/requests/{mat_id}/decision", headers=H(pm),
                          json={"action": "approve"})
        assert r.status_code == 400

        r = requests.post(f"{BASE}/store/requests/{tool_id}/decision", headers=H(pm),
                          json={"action": "approve"})
        assert r.status_code == 200

        # Receive stock for cement and drill (admin)
        ph = _upload_photo(admin, PID)
        r = requests.post(f"{BASE}/projects/{PID}/store/receive", headers=H(admin),
                          json={"kind": "material", "item": "Cement", "quantity": 20, "unit": "bag",
                                "photo_ids": [ph], "responsible_person": "Storekeeper", "note": "GRN-1"})
        assert r.status_code == 200
        ph2 = _upload_photo(admin, PID)
        r = requests.post(f"{BASE}/projects/{PID}/store/receive", headers=H(admin),
                          json={"kind": "tool", "item": "Drill", "quantity": 5, "unit": "nos",
                                "photo_ids": [ph2], "responsible_person": "Storekeeper"})
        assert r.status_code == 200

        # Issue partial (4 bags) then rest (6 bags) -> status partially_issued then issued
        ph3 = _upload_photo(admin, PID)
        r = requests.post(f"{BASE}/store/requests/{mat_id}/issue", headers=H(pm),
                          json={"quantity": 4, "photo_ids": [ph3], "responsible_person": "Foreman"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "partially_issued"

        # Issue more than remaining -> 400
        ph4 = _upload_photo(admin, PID)
        r = requests.post(f"{BASE}/store/requests/{mat_id}/issue", headers=H(pm),
                          json={"quantity": 100, "photo_ids": [ph4], "responsible_person": "Foreman"})
        assert r.status_code == 400

        # Issue remaining
        r = requests.post(f"{BASE}/store/requests/{mat_id}/issue", headers=H(pm),
                          json={"quantity": 6, "photo_ids": [ph4], "responsible_person": "Foreman"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "issued"

        # Stock check: cement available 20-10=10, consumed 10
        r = requests.get(f"{BASE}/projects/{PID}/store/stock", headers=H(eng))
        assert r.status_code == 200
        cement = next(s for s in r.json() if s["item"] == "Cement")
        assert cement["available"] == 10
        assert cement["consumed"] == 10

        # Issue tool
        ph5 = _upload_photo(admin, PID)
        r = requests.post(f"{BASE}/store/requests/{tool_id}/issue", headers=H(pm),
                          json={"quantity": 2, "photo_ids": [ph5], "responsible_person": "Mason"})
        assert r.status_code == 200
        assert r.json()["status"] == "issued"

        # Return tool: 1 good + 1 damaged
        ph6 = _upload_photo(admin, PID)
        r = requests.post(f"{BASE}/store/requests/{tool_id}/return", headers=H(pm),
                          json={"good": 1, "damaged": 1, "lost": 0, "photo_ids": [ph6],
                                "responsible_person": "Mason"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "returned"

        # Stock: drill available = 5-2+1 = 4, issued_out = 0, damaged=1
        r = requests.get(f"{BASE}/projects/{PID}/store/stock", headers=H(eng))
        drill = next(s for s in r.json() if s["item"] == "Drill")
        assert drill["available"] == 4
        assert drill["issued_out"] == 0
        assert drill["damaged"] == 1

        # Transactions list
        r = requests.get(f"{BASE}/projects/{PID}/store/transactions", headers=H(eng))
        assert r.status_code == 200
        types = {t["type"] for t in r.json()}
        assert {"receive", "issue", "return"} <= types

        # Reject flow — create and reject
        r = requests.post(f"{BASE}/projects/{PID}/store/requests", headers=H(eng),
                          json={"kind": "material", "item": "Sand", "quantity": 5, "unit": "cft", "remarks": ""})
        rid = r.json()["id"]
        r = requests.post(f"{BASE}/store/requests/{rid}/decision", headers=H(pm),
                          json={"action": "reject", "comment": "Not needed"})
        assert r.status_code == 200 and r.json()["status"] == "rejected"

        # Cross-tenant isolation: random fake user with different company cannot see
        # (approximated — list returns empty for a different pid)
        r = requests.get(f"{BASE}/projects/{PID}/store/requests", headers=H(eng))
        assert r.status_code == 200

    def test_cross_tenant_denied(self, admin, pm):
        """A different-enterprise user cannot access this project's store."""
        suffix = str(int(time.time()))
        email = f"test_xt_{suffix}@example.com"
        r = requests.post(f"{BASE}/auth/register-enterprise", json={
            "company_name": f"TEST_XT_{suffix}", "business_type": "commercial",
            "name": "Owner", "email": email, "phone": "+919000000001", "password": "Pass@2026X"})
        assert r.status_code == 200
        DB.users.update_one({"email": email}, {"$set": {"email_verified": True}})
        u = DB.users.find_one({"email": email})
        eid = u["company_id"]
        sa = admin
        r = requests.post(f"{BASE}/superadmin/enterprises/{eid}/status",
                          headers=H(sa), json={"status": "active", "reason": ""})
        assert r.status_code == 200
        r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": "Pass@2026X"})
        tok = r.json()["access_token"]
        # Access to other-tenant proj should 403/404
        r = requests.get(f"{BASE}/projects/{PID}/store/requests", headers=H(tok))
        assert r.status_code in (403, 404)
        r = requests.get(f"{BASE}/projects/{PID}/store/stock", headers=H(tok))
        assert r.status_code in (403, 404)
        # cleanup
        DB.users.delete_many({"email": email})
        DB.enterprises.delete_many({"id": eid})


# ---------------------------------------------------------------------------
# BOQ + DPR linkage
# ---------------------------------------------------------------------------
class TestBoqDpr:
    def test_boq_crud_and_dpr_link(self, admin, pm, eng):
        # Engineer cannot create BOQ (only pm/admin manages)
        r = requests.post(f"{BASE}/projects/{PID}/boq", headers=H(eng),
                          json={"code": "A1", "description": "RCC M25", "unit": "cum", "approved_qty": 100})
        assert r.status_code == 403

        # PM creates BOQ
        r = requests.post(f"{BASE}/projects/{PID}/boq", headers=H(pm),
                          json={"code": "A1", "description": "RCC M25", "unit": "cum", "approved_qty": 100})
        assert r.status_code == 200, r.text
        boq_id = r.json()["id"]

        # Duplicate code -> 409
        r = requests.post(f"{BASE}/projects/{PID}/boq", headers=H(pm),
                          json={"code": "A1", "description": "Dup", "unit": "cum", "approved_qty": 1})
        assert r.status_code == 409

        # GET boq
        r = requests.get(f"{BASE}/projects/{PID}/boq", headers=H(eng))
        assert r.status_code == 200
        rows = r.json()
        assert any(b["code"] == "A1" and b["remaining_qty"] == 100 for b in rows)

        # Clean any DPRs
        DB.dprs.delete_many({"project_id": PID})

        # Create DPR with BOQ entry
        today = datetime.now(IST).date().isoformat()
        r = requests.post(f"{BASE}/projects/{PID}/dprs", headers=H(eng),
                          json={"report_date": today,
                                "activities": [{"description": "Pour col", "planned_pct": 100, "actual_pct": 100}],
                                "boq_entries": [{"boq_id": boq_id, "qty": 30}]})
        assert r.status_code == 200, r.text
        did = r.json()["id"]
        entries = r.json().get("boq_entries", [])
        assert entries and entries[0]["code"] == "A1"
        assert entries[0]["excess"] is False

        # DPR entry exceeding approved -> excess flag true
        DB.dprs.delete_many({"id": did})
        r = requests.post(f"{BASE}/projects/{PID}/dprs", headers=H(eng),
                          json={"report_date": today, "activities": [],
                                "boq_entries": [{"boq_id": boq_id, "qty": 500}]})
        assert r.status_code == 200
        assert r.json()["boq_entries"][0]["excess"] is True

        # Unknown BOQ id -> 400
        DB.dprs.delete_many({"project_id": PID})
        r = requests.post(f"{BASE}/projects/{PID}/dprs", headers=H(eng),
                          json={"report_date": today, "activities": [],
                                "boq_entries": [{"boq_id": "nope", "qty": 1}]})
        assert r.status_code == 400

        # Submit & approve a legit DPR -> boq accepted_qty should bump
        DB.dprs.delete_many({"project_id": PID})
        r = requests.post(f"{BASE}/projects/{PID}/dprs", headers=H(eng),
                          json={"report_date": today, "activities": [],
                                "boq_entries": [{"boq_id": boq_id, "qty": 25}]})
        did = r.json()["id"]
        r = requests.post(f"{BASE}/dprs/{did}/submit", headers=H(eng))
        assert r.status_code == 200
        r = requests.post(f"{BASE}/dprs/{did}/review", headers=H(pm),
                          json={"action": "approve"})
        assert r.status_code == 200
        # BOQ should reflect accepted_qty 25
        r = requests.get(f"{BASE}/projects/{PID}/boq", headers=H(eng))
        a1 = next(b for b in r.json() if b["code"] == "A1")
        assert a1["remaining_qty"] == 75
        assert a1["progress_pct"] == 25.0

        # DPR PDF generates
        r = requests.get(f"{BASE}/dprs/{did}/pdf?auth={eng}")
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")

        DB.dprs.delete_many({"project_id": PID})


# ---------------------------------------------------------------------------
# Labour attendance / geofence
# ---------------------------------------------------------------------------
class TestLabour:
    def test_geofence_and_checkin_out(self, admin, pm, eng):
        # Engineer cannot set geofence (not manager)
        r = requests.put(f"{BASE}/projects/{PID}/geofence", headers=H(eng),
                         json={"lat": 19.055, "lng": 72.830, "radius_m": 200})
        assert r.status_code == 403

        # PM sets geofence
        r = requests.put(f"{BASE}/projects/{PID}/geofence", headers=H(pm),
                         json={"lat": 19.055, "lng": 72.830, "radius_m": 200})
        assert r.status_code == 200

        # Upload photo
        ph = _upload_photo(eng, PID)

        # Check-in inside geofence (center) -> OK
        r = requests.post(f"{BASE}/projects/{PID}/labour/check-in", headers=H(eng),
                          json={"labour_incharge": "Ravi Gang", "masons": 5, "helpers": 3,
                                "lat": 19.055, "lng": 72.830, "photo_id": ph})
        assert r.status_code == 200, r.text
        lid = r.json()["id"]

        # Duplicate gang today -> 400
        ph2 = _upload_photo(eng, PID)
        r = requests.post(f"{BASE}/projects/{PID}/labour/check-in", headers=H(eng),
                          json={"labour_incharge": "Ravi Gang", "masons": 5, "helpers": 3,
                                "lat": 19.055, "lng": 72.830, "photo_id": ph2})
        assert r.status_code == 400

        # Check-in outside geofence (~1km away) -> 403
        r = requests.post(f"{BASE}/projects/{PID}/labour/check-in", headers=H(eng),
                          json={"labour_incharge": "Shyam Gang", "masons": 4, "helpers": 2,
                                "lat": 19.070, "lng": 72.830, "photo_id": ph2})
        assert r.status_code == 403
        assert "geofence" in r.json()["detail"].lower()

        # Blank labour_incharge -> 400
        r = requests.post(f"{BASE}/projects/{PID}/labour/check-in", headers=H(eng),
                          json={"labour_incharge": "   ", "masons": 1, "helpers": 1,
                                "lat": 19.055, "lng": 72.830, "photo_id": ph2})
        assert r.status_code == 400

        # Check-out inside -> OK
        ph3 = _upload_photo(eng, PID)
        r = requests.post(f"{BASE}/labour/{lid}/check-out", headers=H(eng),
                          json={"labour_incharge": "Ravi Gang", "masons": 5, "helpers": 3,
                                "lat": 19.055, "lng": 72.830, "photo_id": ph3})
        assert r.status_code == 200, r.text
        assert r.json()["check_out"] is not None

        # Double check-out -> 400
        r = requests.post(f"{BASE}/labour/{lid}/check-out", headers=H(eng),
                          json={"labour_incharge": "Ravi Gang", "masons": 5, "helpers": 3,
                                "lat": 19.055, "lng": 72.830, "photo_id": ph3})
        assert r.status_code == 400

        # List attendance
        r = requests.get(f"{BASE}/projects/{PID}/labour", headers=H(eng))
        assert r.status_code == 200
        data = r.json()
        assert data["geofence"]["radius_m"] == 200
        assert data["totals"]["masons"] >= 5
        assert any(row["id"] == lid for row in data["rows"])

    def test_checkin_without_geofence(self, pm, eng):
        """If PM has not set geofence, check-in fails cleanly."""
        DB.projects.update_one({"id": PID}, {"$unset": {"geofence": ""}})
        DB.labour_attendance.delete_many({"project_id": PID})
        ph = _upload_photo(eng, PID)
        r = requests.post(f"{BASE}/projects/{PID}/labour/check-in", headers=H(eng),
                          json={"labour_incharge": "X", "masons": 1, "helpers": 1,
                                "lat": 19.055, "lng": 72.830, "photo_id": ph})
        assert r.status_code == 400
        assert "geofence" in r.json()["detail"].lower()
