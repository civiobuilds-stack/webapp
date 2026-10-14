"""Iteration 8 — Labour cost report, project wages, overdue tool reminders, cron endpoints, SA password."""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = ("civiobuilds@gmail.com", "Civio@123456")
PM = ("pm@civio.build", "CivioPM@2026")
ENG = ("engineer@civio.build", "CivioEng@2026")

PROJECT_ID = "proj-demo-1"
COMPANY_ID = "civio"

MONGO = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = MONGO[os.environ.get("DB_NAME", "test_database")]

CRON_SECRET = "auurPXrWXHcshr32vCKsWk0hZ8iu26z2rgQ-9W3aosI"


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_tok():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def pm_tok():
    return login(*PM)


@pytest.fixture(scope="module")
def eng_tok():
    return login(*ENG)


# ---------- SA password / no forced change ----------
class TestSuperAdminPassword:
    def test_login_new_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
        assert r.status_code == 200
        tok = r.json()["access_token"]
        me = requests.get(f"{API}/auth/me", headers=H(tok))
        assert me.status_code == 200
        assert me.json().get("must_change_password") is False

    def test_old_password_fails(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN[0], "password": "CivioAdmin@2026"})
        assert r.status_code in (400, 401)


# ---------- Wages ----------
class TestWages:
    def test_admin_get_put_wages(self, admin_tok):
        prev = requests.get(f"{API}/labour/wages", headers=H(admin_tok))
        assert prev.status_code == 200
        orig = {"mason_rate": prev.json().get("mason_rate", 0), "helper_rate": prev.json().get("helper_rate", 0)}
        r = requests.put(f"{API}/labour/wages", json={"mason_rate": 800, "helper_rate": 500}, headers=H(admin_tok))
        assert r.status_code == 200
        assert r.json()["mason_rate"] == 800 and r.json()["helper_rate"] == 500
        g = requests.get(f"{API}/labour/wages", headers=H(admin_tok)).json()
        assert g["mason_rate"] == 800 and g["helper_rate"] == 500
        # restore
        requests.put(f"{API}/labour/wages", json=orig, headers=H(admin_tok))

    def test_pm_forbidden_company_wages(self, pm_tok):
        assert requests.get(f"{API}/labour/wages", headers=H(pm_tok)).status_code == 403
        assert requests.put(f"{API}/labour/wages", json={"mason_rate": 1, "helper_rate": 1}, headers=H(pm_tok)).status_code == 403

    def test_project_wages_structure(self, admin_tok):
        r = requests.get(f"{API}/projects/{PROJECT_ID}/wages", headers=H(admin_tok))
        assert r.status_code == 200
        j = r.json()
        assert "company" in j and "override" in j and "effective" in j

    def test_pm_can_set_project_override(self, pm_tok, admin_tok):
        r = requests.put(f"{API}/projects/{PROJECT_ID}/wages", json={"mason_rate": 900, "helper_rate": 600}, headers=H(pm_tok))
        assert r.status_code == 200
        eff = r.json()["effective"]
        assert eff["mason_rate"] == 900 and eff["helper_rate"] == 600
        # null falls back to company
        r2 = requests.put(f"{API}/projects/{PROJECT_ID}/wages", json={"mason_rate": None, "helper_rate": None}, headers=H(pm_tok))
        assert r2.status_code == 200
        comp = r2.json()["company"]
        eff2 = r2.json()["effective"]
        assert eff2["mason_rate"] == comp["mason_rate"] and eff2["helper_rate"] == comp["helper_rate"]

    def test_engineer_cannot_set_project_wages(self, eng_tok):
        r = requests.put(f"{API}/projects/{PROJECT_ID}/wages", json={"mason_rate": 1, "helper_rate": 1}, headers=H(eng_tok))
        assert r.status_code == 403


# ---------- Labour cost report ----------
class TestLabourCost:
    @pytest.fixture(autouse=True)
    def _seed(self, admin_tok):
        # Set known rates
        requests.put(f"{API}/labour/wages", json={"mason_rate": 1000, "helper_rate": 500}, headers=H(admin_tok))
        # Insert labour_attendance rows for today & yesterday
        today = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30))).date()
        self._rows = []
        for i, (d_off, m, h) in enumerate([(0, 3, 5), (1, 2, 4)]):
            d = (today - timedelta(days=d_off)).isoformat()
            doc = {"id": f"TEST-la-{uuid.uuid4().hex[:8]}", "project_id": PROJECT_ID, "company_id": COMPANY_ID,
                   "date": d, "masons": m, "helpers": h, "created_at": datetime.now(timezone.utc).isoformat()}
            DB.labour_attendance.insert_one(doc)
            self._rows.append(doc["id"])
        yield
        DB.labour_attendance.delete_many({"id": {"$in": self._rows}})

    def test_project_labour_cost_report(self, admin_tok):
        r = requests.get(f"{API}/projects/{PROJECT_ID}/labour-cost", headers=H(admin_tok))
        assert r.status_code == 200
        j = r.json()
        assert "mtd" in j and "week" in j and "days" in j and "rates" in j
        assert len(j["days"]) == 7
        # totals should be positive (we inserted 3m+5h today, 2m+4h yesterday) at 1000/500
        assert j["week"]["mason_days"] >= 5
        assert j["week"]["helper_days"] >= 9
        assert j["week"]["total"] >= 5 * 1000 + 9 * 500

    def test_project_pdf(self, admin_tok):
        r = requests.get(f"{API}/projects/{PROJECT_ID}/labour-cost/pdf", params={"auth": admin_tok})
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_company_pdf_admin_only(self, admin_tok, pm_tok):
        r = requests.get(f"{API}/labour-cost/pdf", params={"auth": admin_tok})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        r2 = requests.get(f"{API}/labour-cost/pdf", params={"auth": pm_tok})
        assert r2.status_code == 403

    def test_send_now_and_logs(self, admin_tok):
        r = requests.post(f"{API}/labour-cost/send-now", headers=H(admin_tok))
        assert r.status_code == 200
        assert r.json().get("queued") is True
        key = r.json()["key"]
        # wait for background job
        status = None
        for _ in range(20):
            time.sleep(1.5)
            logs = requests.get(f"{API}/labour-cost/logs", headers=H(admin_tok)).json()
            match = [l for l in logs if l.get("key") == key]
            if match and match[0].get("status") in ("sent", "partial", "failed"):
                status = match[0]["status"]
                break
        assert status is not None, "send-now did not finish within timeout"
        # Accept sent or partial (email service might flake); failed should fail test
        assert status in ("sent", "partial"), f"status={status}"


# ---------- Cron auth ----------
class TestCron:
    def test_cron_requires_bearer(self):
        for path in ("/cron/labour-cost", "/cron/tool-overdue"):
            r = requests.post(f"{API}{path}", json={})
            assert r.status_code == 401, path
            r2 = requests.post(f"{API}{path}", json={}, headers={"Authorization": "Bearer wrong"})
            assert r2.status_code == 401, path

    def test_cron_ok_with_secret(self):
        for path in ("/cron/labour-cost", "/cron/tool-overdue"):
            r = requests.post(f"{API}{path}", json={}, headers={"Authorization": f"Bearer {CRON_SECRET}"})
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text}"
            assert r.json().get("accepted") is True


# ---------- Overdue tools ----------
class TestOverdueTools:
    _request_id = None
    _item = None

    def test_create_overdue_issued_tool(self, admin_tok, pm_tok):
        # Insert a store_request directly in 'issued' state with expected_return in the past,
        # to exercise overdue listing + reminder logic without full issue flow (needs photos/stock).
        past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        name = f"TEST-tool-{uuid.uuid4().hex[:6]}"
        TestOverdueTools._item = name
        pm_user = DB.users.find_one({"email": PM[0]})
        rid = f"TEST-sr-{uuid.uuid4().hex[:8]}"
        TestOverdueTools._request_id = rid
        DB.store_requests.insert_one({
            "id": rid, "company_id": COMPANY_ID, "project_id": PROJECT_ID,
            "kind": "tool", "item": name, "quantity": 1, "unit": "pcs",
            "expected_return": past, "status": "issued",
            "requested_by": pm_user["id"], "requested_by_name": pm_user["name"],
            "issued_qty": 1, "returned_qty": 0, "damaged_qty": 0, "lost_qty": 0,
            "created_at": datetime.now(timezone.utc).isoformat(), "history": [],
        })

    def test_overdue_list(self, admin_tok):
        r = requests.get(f"{API}/projects/{PROJECT_ID}/store/overdue", headers=H(admin_tok))
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert TestOverdueTools._request_id in ids

    def test_remind_now_and_dedupe(self, admin_tok):
        # Clean dedup for current date for our request
        today = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
        DB.tool_reminders.delete_many({"request_id": TestOverdueTools._request_id, "date": today})
        r1 = requests.post(f"{API}/store/overdue/remind-now", headers=H(admin_tok))
        assert r1.status_code == 200
        n1 = r1.json()["reminded"]
        assert n1 >= 1
        r2 = requests.post(f"{API}/store/overdue/remind-now", headers=H(admin_tok))
        assert r2.status_code == 200
        assert r2.json()["reminded"] == 0, "dedupe failed"

    def test_notifications_created(self, pm_tok):
        r = requests.get(f"{API}/notifications", headers=H(pm_tok))
        assert r.status_code == 200
        items = r.json().get("items", []) if isinstance(r.json(), dict) else r.json()
        kinds = [n.get("type") for n in items]
        assert "tool_overdue" in kinds

    def test_cleanup(self, admin_tok):
        rid = TestOverdueTools._request_id
        if rid:
            # try cancel; fallback hard-delete
            try:
                requests.post(f"{API}/store/requests/{rid}/cancel", headers=H(admin_tok))
            except Exception:
                pass
            DB.store_requests.delete_one({"id": rid})
            DB.tool_reminders.delete_many({"request_id": rid})
