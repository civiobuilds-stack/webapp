"""Iteration 10 — Commercial Phase 2: roles, company store (issue/shortage/3-step tool return), overdue reminders,
weekly engineer targets, site passes, residential inspection client sign-off."""
import io
# NOTE: run serially with -n0 (classes share state)
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

ADMIN = ("civiobuilds@gmail.com", "Civio@123456")
PM = ("pm@civio.build", "CivioPM@2026")
ENG = ("engineer@civio.build", "CivioEng@2026")
STORE = ("store@civio.build", "CivioRole@2026")
STOREMGR = ("storemanager@civio.build", "CivioRole@2026")
PASS = ("pass@civio.build", "CivioRole@2026")
CLIENT = ("client@civio.build", "CivioClient@2026")
R_OWNER = ("owner@civiohomes.build", "CivioHome@2026")
R_ENG = ("engineer@civiohomes.build", "CivioHome@2026")
R_PM = ("pm@civiohomes.build", "CivioHome@2026")
R_CLIENT = ("client@civiohomes.build", "CivioHome@2026")
PID = "proj-demo-1"
RPID = "proj-res-1"
TAG = uuid.uuid4().hex[:6]
ITEM = f"TEST_Tool_{TAG}"
MAT = f"TEST_Mat_{TAG}"
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb004300") + b"\x08" * 64 + bytes.fromhex("ffd9")

_tok = {}


def tok(c):
    if c not in _tok:
        DB.login_attempts.delete_many({})
        r = requests.post(f"{API}/auth/login", json={"email": c[0], "password": c[1]})
        assert r.status_code == 200, f"login {c[0]}: {r.status_code} {r.text}"
        _tok[c] = r.json()["access_token"]
    return _tok[c]


def H(c):
    return {"Authorization": f"Bearer {tok(c)}"}


def upload(c, pid):
    r = requests.post(f"{API}/files/upload", headers=H(c), files={"file": ("cam.jpg", io.BytesIO(JPEG), "image/jpeg")}, data={"project_id": pid})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    DB.users.delete_many({"email": {"$regex": f"^test_{TAG}"}})
    DB.store_requests.delete_many({"item": {"$in": [ITEM, MAT]}})
    DB.company_stock.delete_many({"item": {"$in": [ITEM, MAT]}})
    DB.store_txns.delete_many({"item": {"$in": [ITEM, MAT]}})
    DB.site_passes.delete_many({"person_name": {"$regex": "^TEST_"}})


# ---- Roles & user creation ----
class TestRoles:
    def test_roles_list(self):
        r = requests.get(f"{API}/roles", headers=H(PM))
        assert r.status_code == 200
        m = {x["key"]: x for x in r.json()}
        for k in ["store_incharge", "store_manager", "pass_coordinator", "safety_engineer", "driver", "billing_qs"]:
            assert k in m
        assert m["store_incharge"]["approver"] == "store_manager"
        assert m["pass_coordinator"]["approver_label"] == "Project Manager"
        assert m["store_manager"]["admin_only"] is True
        assert "asco_manager" not in m and "admin" not in m

    def test_residential_roles_hide_commercial(self):
        keys = {x["key"] for x in requests.get(f"{API}/roles", headers=H(R_OWNER)).json()}
        assert "store_incharge" not in keys and "site_engineer" in keys

    @pytest.mark.parametrize("role", ["store_incharge", "pass_coordinator", "safety_engineer"])
    def test_pm_can_create(self, role):
        r = requests.post(f"{API}/users", headers=H(PM), json={"email": f"test_{TAG}_{role}@x.com", "password": "Passw0rd!x", "name": f"T {role}", "role": role, "phone": "9999999999"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == role

    @pytest.mark.parametrize("role", ["store_manager", "safety_manager", "quality_manager", "billing_manager"])
    def test_pm_cannot_create_manager(self, role):
        r = requests.post(f"{API}/users", headers=H(PM), json={"email": f"test_{TAG}_{role}@x.com", "password": "Passw0rd!x", "name": "T", "role": role, "phone": "9999999999"})
        assert r.status_code == 403

    def test_admin_can_create_manager(self):
        r = requests.post(f"{API}/users", headers=H(ADMIN), json={"email": f"test_{TAG}_sm@x.com", "password": "Passw0rd!x", "name": "T SM", "role": "safety_manager", "phone": "9999999999"})
        assert r.status_code == 200, r.text

    def test_residential_cannot_create_commercial_role(self):
        r = requests.post(f"{API}/users", headers=H(R_OWNER), json={"email": f"test_{TAG}_res@x.com", "password": "Passw0rd!x", "name": "T", "role": "store_incharge", "phone": "9999999999"})
        assert r.status_code == 400


# ---- Company store ----
class TestCompanyStore:
    state = {}

    def test_receive_stock(self):
        r = requests.post(f"{API}/store/company/receive", headers=H(STORE), json={"kind": "tool", "item": ITEM, "unit": "nos", "quantity": 3, "photo_ids": [], "responsible_person": "Gate"})
        assert r.status_code == 200, r.text
        s = requests.get(f"{API}/store/company", headers=H(STORE)).json()
        row = next(x for x in s["stock"] if x["item"] == ITEM)
        assert row["available"] == 3

    def test_engineer_cannot_receive(self):
        r = requests.post(f"{API}/store/company/receive", headers=H(ENG), json={"kind": "tool", "item": ITEM, "quantity": 1, "photo_ids": [], "responsible_person": "x"})
        assert r.status_code == 403

    def test_request_approve(self):
        r = requests.post(f"{API}/projects/{PID}/store/requests", headers=H(ENG), json={"kind": "tool", "item": ITEM, "quantity": 5, "unit": "nos", "expected_return": "2030-01-01"})
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        self.state["rid"] = rid
        d = requests.post(f"{API}/store/requests/{rid}/decision", headers=H(PM), json={"action": "approve"})
        assert d.status_code == 200 and d.json()["status"] == "approved"

    def test_engineer_cannot_issue(self):
        ph = upload(ENG, PID)
        r = requests.post(f"{API}/store/requests/{self.state['rid']}/issue", headers=H(ENG), json={"quantity": 1, "photo_ids": [ph], "responsible_person": "x"})
        assert r.status_code == 403

    def test_issue_requires_photo(self):
        r = requests.post(f"{API}/store/requests/{self.state['rid']}/issue", headers=H(STORE), json={"quantity": 1, "photo_ids": [], "responsible_person": "x"})
        assert r.status_code == 400

    def test_issue_shortage(self):
        ph = upload(STORE, PID)
        self.state["ph"] = ph
        r = requests.post(f"{API}/store/requests/{self.state['rid']}/issue", headers=H(STORE), json={"quantity": 5, "photo_ids": [ph], "responsible_person": "Ravi"})
        assert r.status_code == 409, r.text
        req = DB.store_requests.find_one({"id": self.state["rid"]})
        assert req["status"] == "shortage" and req["shortage_qty"] == 2
        admin = DB.users.find_one({"email": ADMIN[0]})
        mgr = DB.users.find_one({"email": STOREMGR[0]})
        for u in (admin, mgr):
            assert DB.notifications.find_one({"user_id": u["id"], "type": "store_shortage", "message": {"$regex": ITEM}}), u["email"]
        s = requests.get(f"{API}/store/company", headers=H(ADMIN)).json()
        assert any(x["id"] == self.state["rid"] for x in s["shortages"])

    def test_partial_issue(self):
        r = requests.post(f"{API}/store/requests/{self.state['rid']}/issue", headers=H(STORE), json={"quantity": 3, "photo_ids": [self.state["ph"]], "responsible_person": "Ravi"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "partially_issued" and r.json()["issued_qty"] == 3
        row = DB.company_stock.find_one({"item": ITEM})
        assert row["available"] == 0 and row["issued_out"] == 3

    def test_project_stock(self):
        rows = requests.get(f"{API}/projects/{PID}/store/stock", headers=H(PM)).json()
        row = next(x for x in rows if x["request_id"] == self.state["rid"])
        assert row["issued"] == 3 and row["on_site"] == 3

    def test_return_three_step(self):
        rid = self.state["rid"]
        ph = upload(ENG, PID)
        r = requests.post(f"{API}/store/requests/{rid}/return", headers=H(ENG), json={"good": 2, "damaged": 0, "lost": 0, "photo_ids": [ph], "responsible_person": "Ravi"})
        assert r.status_code == 200, r.text
        assert r.json()["pending_return"]["stage"] == "awaiting_store"
        # PM cannot jump
        assert requests.post(f"{API}/store/requests/{rid}/return/approve", headers=H(PM), json={"action": "approve"}).status_code == 400
        # engineer cannot receive
        assert requests.post(f"{API}/store/requests/{rid}/return/receive", headers=H(ENG), json={"photo_ids": [ph]}).status_code == 403
        # store receive without photo -> 400
        assert requests.post(f"{API}/store/requests/{rid}/return/receive", headers=H(STORE), json={"photo_ids": []}).status_code == 400
        sph = upload(STORE, PID)
        r = requests.post(f"{API}/store/requests/{rid}/return/receive", headers=H(STORE), json={"photo_ids": [sph]})
        assert r.status_code == 200 and r.json()["pending_return"]["stage"] == "awaiting_pm"
        # store / engineer cannot final approve
        assert requests.post(f"{API}/store/requests/{rid}/return/approve", headers=H(STORE), json={"action": "approve"}).status_code == 403
        assert requests.post(f"{API}/store/requests/{rid}/return/approve", headers=H(ENG), json={"action": "approve"}).status_code == 403
        r = requests.post(f"{API}/store/requests/{rid}/return/approve", headers=H(PM), json={"action": "approve"})
        assert r.status_code == 200, r.text
        assert r.json()["returned_qty"] == 2 and "pending_return" not in r.json()
        row = DB.company_stock.find_one({"item": ITEM})
        assert row["available"] == 2 and row["issued_out"] == 1

    def test_company_store_visibility(self):
        assert requests.get(f"{API}/store/company", headers=H(ENG)).status_code == 200
        e = requests.get(f"{API}/store/company", headers=H(ENG)).json()
        assert e["can_edit"] is False and e["store_staff"] is False
        assert requests.get(f"{API}/store/company", headers=H(CLIENT)).status_code == 403
        s = requests.get(f"{API}/store/company", headers=H(STORE)).json()
        assert s["store_staff"] is True
        assert any(t["item"] == ITEM for t in s["transactions"])

    def test_overdue_reminder(self):
        rid = self.state["rid"]
        old = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
        DB.store_requests.update_one({"id": rid}, {"$set": {"issued_at": old}})
        DB.tool_reminders.delete_many({"request_id": rid})
        r = requests.post(f"{API}/store/overdue/remind-now", headers=H(PM))
        assert r.status_code == 200 and r.json()["reminded"] >= 1, r.text
        for e in (ENG[0], PM[0], STORE[0]):
            u = DB.users.find_one({"email": e})
            assert DB.notifications.find_one({"user_id": u["id"], "type": "tool_overdue", "message": {"$regex": ITEM}}), e
        assert requests.post(f"{API}/store/overdue/remind-now", headers=H(ENG)).status_code == 403


# ---- Weekly targets ----
class TestTargets:
    state = {}

    def test_set_and_achieve(self):
        boq = requests.post(f"{API}/projects/{PID}/boq", headers=H(PM), json={"code": f"TEST_{TAG}", "description": "TEST brickwork", "unit": "m3", "approved_qty": 1000})
        assert boq.status_code == 200, boq.text
        bid = boq.json()["id"]
        self.state["bid"] = bid
        eng = DB.users.find_one({"email": ENG[0]})["id"]
        today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
        monday = today - timedelta(days=today.weekday())
        assert requests.put(f"{API}/projects/{PID}/targets", headers=H(ENG), json={"engineer_id": eng, "boq_id": bid, "week_start": monday.isoformat(), "target_qty": 10}).status_code == 403
        r = requests.put(f"{API}/projects/{PID}/targets", headers=H(PM), json={"engineer_id": eng, "boq_id": bid, "week_start": monday.isoformat(), "target_qty": 10})
        assert r.status_code == 200, r.text
        t = next(x for x in r.json() if x["boq_id"] == bid)
        assert t["achieved_qty"] == 0 and t["met"] is False
        # free date in this week
        used = {d["report_date"] for d in DB.dprs.find({"project_id": PID}, {"report_date": 1})}
        day = next((monday + timedelta(days=i)).isoformat() for i in range(7) if (monday + timedelta(days=i)).isoformat() not in used)
        d = requests.post(f"{API}/projects/{PID}/dprs", headers=H(ENG), json={"report_date": day, "boq_entries": [{"boq_id": bid, "qty": 12}]})
        assert d.status_code == 200, d.text
        did = d.json()["id"]
        self.state["did"] = did
        assert requests.post(f"{API}/dprs/{did}/submit", headers=H(ENG)).status_code == 200
        # not approved yet -> not counted
        t = next(x for x in requests.get(f"{API}/projects/{PID}/targets", headers=H(PM)).json() if x["boq_id"] == bid)
        assert t["achieved_qty"] == 0
        assert requests.post(f"{API}/dprs/{did}/review", headers=H(PM), json={"action": "approve"}).status_code == 200
        t = next(x for x in requests.get(f"{API}/projects/{PID}/targets", headers=H(ENG)).json() if x["boq_id"] == bid)
        assert t["achieved_qty"] == 12 and t["met"] is True
        dash = requests.get(f"{API}/dashboard/role", headers=H(ENG)).json()
        assert any(x["boq_id"] == bid and x["met"] for x in dash["targets"])

    def test_dashboard_cards(self):
        for c, key in [(PM, "store_approve"), (STORE, "to_issue"), (PASS, "pass_active"), (ENG, "my_requests")]:
            r = requests.get(f"{API}/dashboard/role", headers=H(c))
            assert r.status_code == 200, r.text
            assert any(x["key"] == key for x in r.json()["cards"]), c

    @classmethod
    def teardown_class(cls):
        if cls.state.get("did"):
            DB.dprs.delete_one({"id": cls.state["did"]})
        if cls.state.get("bid"):
            DB.boq_items.delete_one({"id": cls.state["bid"]})
            DB.engineer_targets.delete_many({"boq_id": cls.state["bid"]})
            # recompute progress so seeded project unaffected
            items = list(DB.boq_items.find({"project_id": PID}))
            if not items:
                DB.projects.update_one({"id": PID}, {"$unset": {"boq_progress_percent": ""}})


# ---- Site passes ----
class TestPasses:
    def test_pass_flow(self):
        body = {"pass_type": "labour", "person_name": "TEST_Ramesh", "valid_from": "2026-01-01", "valid_to": "2026-02-01", "photo_ids": []}
        assert requests.post(f"{API}/projects/{PID}/passes", headers=H(PASS), json=body).status_code == 400
        assert requests.post(f"{API}/projects/{PID}/passes", headers=H(ENG), json=body).status_code == 403
        body["photo_ids"] = [upload(PASS, PID)]
        r = requests.post(f"{API}/projects/{PID}/passes", headers=H(PASS), json=body)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["status"] == "pending" and "-L" in p["pass_no"]
        assert requests.post(f"{API}/passes/{p['id']}/decision", headers=H(PASS), json={"action": "approve"}).status_code == 403
        r = requests.post(f"{API}/passes/{p['id']}/decision", headers=H(PM), json={"action": "approve"})
        assert r.status_code == 200 and r.json()["status"] == "active"
        r = requests.post(f"{API}/passes/{p['id']}/decision", headers=H(PASS), json={"action": "revoke", "remarks": "left"})
        assert r.status_code == 200 and r.json()["status"] == "revoked"
        lst = requests.get(f"{API}/projects/{PID}/passes", headers=H(PM)).json()
        assert next(x for x in lst if x["id"] == p["id"])["status"] == "revoked"


# ---- Residential inspection sign-off ----
class TestSignoff:
    def test_signoff_flow(self):
        insp = requests.get(f"{API}/projects/{RPID}/inspection", headers=H(R_CLIENT))
        assert insp.status_code == 200, insp.text
        stages = insp.json()["stages"]
        stage = min((s for s in stages if not s.get("signoff")), key=lambda s: len(s["items"]))
        name = stage["stage"]
        orig = {i["id"]: {k: i.get(k) for k in ("status", "remarks", "photo_ids", "history", "inspected_by", "inspected_at")} for i in stage["items"]}
        try:
            if any(i["status"] not in {"pass", "na"} for i in stage["items"]):
                r = requests.post(f"{API}/projects/{RPID}/inspection/signoff", headers=H(R_CLIENT), json={"stage": name, "remarks": "ok"})
                assert r.status_code == 400
            assert requests.post(f"{API}/projects/{RPID}/inspection/signoff", headers=H(R_PM), json={"stage": name}).status_code == 403
            ph = upload(R_ENG, RPID)
            for i in stage["items"]:
                r = requests.put(f"{API}/inspection-items/{i['id']}", headers=H(R_ENG), json={"status": "pass", "photo_ids": [ph]})
                assert r.status_code == 200, r.text
            r = requests.post(f"{API}/projects/{RPID}/inspection/signoff", headers=H(R_CLIENT), json={"stage": name, "remarks": "TEST I approve"})
            assert r.status_code == 200, r.text
            assert r.json()["signed_by_name"]
            assert requests.post(f"{API}/projects/{RPID}/inspection/signoff", headers=H(R_CLIENT), json={"stage": name}).status_code == 409
            g = next(s for s in requests.get(f"{API}/projects/{RPID}/inspection", headers=H(R_PM)).json()["stages"] if s["stage"] == name)
            assert g["signoff"]["remarks"] == "TEST I approve"
            pdf = requests.post(f"{API}/projects/{RPID}/inspection/report", headers=H(R_PM), json={})
            assert pdf.status_code == 200, pdf.text[:300]
        finally:
            DB.inspection_signoffs.delete_many({"project_id": RPID, "stage": name})
            for iid, o in orig.items():
                DB.inspection_items.update_one({"id": iid}, {"$set": o})
