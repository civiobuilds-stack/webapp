"""Iteration-7: commercial workspace tests — super-admin password change + logout revocation,
employees, project permissions, attendance, DPRs, push, weekly digest, residential scope."""
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import requests
from pymongo import MongoClient

def _frontend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL"):
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL missing"
    return v


BASE_URL = _frontend_url().rstrip("/") + "/api"
MONGO = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = MONGO[os.environ.get("DB_NAME", "test_database")]

SA_EMAIL = "civiobuilds@gmail.com"
SA_PASS = "CivioAdmin@2026"
NEW_SA_PASS = "CivioAdmin@2026X"
PM = ("pm@civio.build", "CivioPM@2026")
ENG = ("engineer@civio.build", "CivioEng@2026")
ENG2 = ("engineer2@civio.build", "CivioEng@2026")
CLIENT = ("client@civio.build", "CivioClient@2026")
PID = "proj-demo-1"
IST = ZoneInfo("Asia/Kolkata")


def login(email, pw):
    # Resilient: if primary pw fails, try the alt SA passwords.
    tried = [pw]
    for p in (pw, SA_PASS, NEW_SA_PASS) if email == SA_EMAIL else (pw,):
        r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": p})
        if r.status_code == 200:
            tok = r.json()["access_token"]
            # If must change, change to NEW_SA_PASS (only for super admin)
            if email == SA_EMAIL:
                me = requests.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
                if me.get("must_change_password") and p != NEW_SA_PASS:
                    cr = requests.post(f"{BASE_URL}/auth/change-password",
                                       headers={"Authorization": f"Bearer {tok}"},
                                       json={"current_password": p, "new_password": NEW_SA_PASS})
                    assert cr.status_code == 200, cr.text
            return tok
        tried.append(p)
    assert False, f"login {email}: tried {tried} last={r.status_code} {r.text}"


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------------------------------------------------------------------
# 1) Super-admin force-password-change + logout revocation
# ---------------------------------------------------------------------------
class TestSuperAdminPasswordChange:
    def test_full_flow(self):
        # Reset SA to initial state (password=SA_PASS, must_change=True)
        import subprocess
        subprocess.run(["python3", "/app/backend/scripts/reset_superadmin.py"], check=True, capture_output=True)
        tok = requests.post(f"{BASE_URL}/auth/login", json={"email": SA_EMAIL, "password": SA_PASS})
        assert tok.status_code == 200
        tok = tok.json()["access_token"]
        me = requests.get(f"{BASE_URL}/auth/me", headers=h(tok)).json()
        assert me["must_change_password"] is True

        # protected tenant API blocked
        r = requests.get(f"{BASE_URL}/projects", headers=h(tok))
        assert r.status_code == 403
        detail = r.json().get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "password_change_required"

        r = requests.get(f"{BASE_URL}/superadmin/enterprises", headers=h(tok))
        assert r.status_code == 403

        # wrong current password
        r = requests.post(f"{BASE_URL}/auth/change-password", headers=h(tok),
                          json={"current_password": "WRONG", "new_password": NEW_SA_PASS})
        assert r.status_code == 400

        # correct change
        r = requests.post(f"{BASE_URL}/auth/change-password", headers=h(tok),
                          json={"current_password": SA_PASS, "new_password": NEW_SA_PASS})
        assert r.status_code == 200

        # now works
        r = requests.get(f"{BASE_URL}/projects", headers=h(tok))
        assert r.status_code == 200

        # logout revokes jti
        r = requests.post(f"{BASE_URL}/auth/logout", headers=h(tok))
        assert r.status_code == 200
        r = requests.get(f"{BASE_URL}/auth/me", headers=h(tok))
        assert r.status_code == 401

        # re-login with new password works
        tok2 = login(SA_EMAIL, NEW_SA_PASS)
        assert tok2


# ---------------------------------------------------------------------------
# 2) Employees + org config
# ---------------------------------------------------------------------------
class TestEmployees:
    def setup_method(self):
        self.admin = login(SA_EMAIL, NEW_SA_PASS)
        self.pm = login(*PM)

    def test_org_config_crud_and_employees(self):
        r = requests.get(f"{BASE_URL}/org/config", headers=h(self.admin))
        assert r.status_code == 200
        cfg = r.json()
        assert "Civil" in cfg["departments"] and "Site Engineer" in cfg["designations"]

        # PM cannot edit org
        r = requests.put(f"{BASE_URL}/org/config", headers=h(self.pm),
                         json={"departments": cfg["departments"], "designations": cfg["designations"]})
        assert r.status_code == 403

        # list employees — admin ok, client excluded
        r = requests.get(f"{BASE_URL}/employees", headers=h(self.admin))
        assert r.status_code == 200
        emps = r.json()
        assert all(e["role"] != "client" for e in emps)
        eng_id = next(e["id"] for e in emps if e["email"] == ENG[0])
        eng2_id = next(e["id"] for e in emps if e["email"] == ENG2[0])

        # PM cannot edit
        r = requests.put(f"{BASE_URL}/employees/{eng_id}", headers=h(self.pm),
                         json={"employee_id": "EMP-100", "designation": "Site Engineer", "department": "Civil"})
        assert r.status_code == 403

        # Admin assigns ids
        r = requests.put(f"{BASE_URL}/employees/{eng_id}", headers=h(self.admin),
                         json={"employee_id": "EMP-100", "designation": "Site Engineer", "department": "Civil"})
        assert r.status_code == 200
        assert r.json()["employee_id"] == "EMP-100"

        # Duplicate -> 409
        r = requests.put(f"{BASE_URL}/employees/{eng2_id}", headers=h(self.admin),
                         json={"employee_id": "EMP-100", "designation": "Site Engineer", "department": "Civil"})
        assert r.status_code == 409

        # Self manager -> 400
        r = requests.put(f"{BASE_URL}/employees/{eng_id}", headers=h(self.admin),
                         json={"employee_id": "EMP-100", "designation": "Site Engineer",
                               "department": "Civil", "reporting_manager_id": eng_id})
        assert r.status_code == 400

        # Unknown department -> 400
        r = requests.put(f"{BASE_URL}/employees/{eng_id}", headers=h(self.admin),
                         json={"employee_id": "EMP-100", "designation": "Site Engineer", "department": "Mars"})
        assert r.status_code == 400

    def teardown_method(self):
        # cleanup employee_id from eng + eng2
        DB.users.update_many({"email": {"$in": [ENG[0], ENG2[0]]}},
                             {"$unset": {"employee_id": "", "designation": "", "department": "",
                                         "reporting_manager_id": ""}})


# ---------------------------------------------------------------------------
# 3) Project permissions
# ---------------------------------------------------------------------------
class TestProjectPermissions:
    def setup_method(self):
        self.admin = login(SA_EMAIL, NEW_SA_PASS)
        self.pm = login(*PM)
        self.eng = login(*ENG)
        self.client = login(*CLIENT)

    def test_my_permissions_defaults(self):
        r = requests.get(f"{BASE_URL}/projects/{PID}/my-permissions", headers=h(self.eng))
        assert r.status_code == 200
        perms = r.json()["permissions"]
        assert set(perms.get("dpr", [])) >= {"view", "create", "edit", "submit"}
        assert set(perms.get("attendance", [])) >= {"view", "create"}

        # Admin manages (gets all actions)
        r = requests.get(f"{BASE_URL}/projects/{PID}/my-permissions", headers=h(self.admin))
        assert r.json()["manages"] is True

    def test_upsert_member_errors_and_override(self):
        # Unknown module
        r = requests.put(f"{BASE_URL}/projects/{PID}/members/user-eng", headers=h(self.admin),
                         json={"responsibility": "lead", "permissions": {"mars": ["view"]}})
        assert r.status_code == 400

        # Unknown action
        r = requests.put(f"{BASE_URL}/projects/{PID}/members/user-eng", headers=h(self.admin),
                         json={"responsibility": "lead", "permissions": {"dpr": ["bogus"]}})
        assert r.status_code == 400

        # Client cannot be member
        r = requests.put(f"{BASE_URL}/projects/{PID}/members/user-client", headers=h(self.admin),
                         json={"responsibility": "x", "permissions": {"dpr": ["view"]}})
        assert r.status_code == 400

        # Random outsider id -> 400
        r = requests.put(f"{BASE_URL}/projects/{PID}/members/does-not-exist", headers=h(self.admin),
                         json={"responsibility": "x", "permissions": {"dpr": ["view"]}})
        assert r.status_code == 400

        # Override: eng gets only dpr:[view]
        r = requests.put(f"{BASE_URL}/projects/{PID}/members/user-eng", headers=h(self.admin),
                         json={"responsibility": "lead", "permissions": {"dpr": ["view"]}})
        assert r.status_code == 200

        # Now eng cannot create a DPR
        today = datetime.now(IST).date().isoformat()
        r = requests.post(f"{BASE_URL}/projects/{PID}/dprs", headers=h(self.eng),
                         json={"report_date": today, "activities": []})
        assert r.status_code == 403

        # Non-manager/admin cannot upsert
        r = requests.put(f"{BASE_URL}/projects/{PID}/members/user-eng2", headers=h(self.eng),
                         json={"responsibility": "x", "permissions": {"dpr": ["view"]}})
        assert r.status_code == 403

        # Cleanup — remove override
        r = requests.delete(f"{BASE_URL}/projects/{PID}/members/user-eng", headers=h(self.admin))
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 4) Attendance
# ---------------------------------------------------------------------------
class TestAttendance:
    def setup_method(self):
        self.admin = login(SA_EMAIL, NEW_SA_PASS)
        self.pm = login(*PM)
        self.eng = login(*ENG)
        self.client = login(*CLIENT)
        # Wipe today's attendance for engineer so check-in is possible
        today = datetime.now(IST).date().isoformat()
        DB.attendance.delete_many({"project_id": PID, "user_id": "user-eng", "date": today})
        self.today = today

    def test_full_flow(self):
        # Client cannot check-in (dpr module not available)
        r = requests.post(f"{BASE_URL}/projects/{PID}/attendance/check-in", headers=h(self.client), json={})
        assert r.status_code == 403

        # Engineer check-in
        r = requests.post(f"{BASE_URL}/projects/{PID}/attendance/check-in", headers=h(self.eng), json={"note": "test"})
        assert r.status_code == 200, r.text
        aid = r.json()["id"]

        # Second check-in same day -> 400
        r = requests.post(f"{BASE_URL}/projects/{PID}/attendance/check-in", headers=h(self.eng), json={})
        assert r.status_code == 400

        # Check-out
        r = requests.post(f"{BASE_URL}/projects/{PID}/attendance/check-out", headers=h(self.eng))
        assert r.status_code == 200

        # List as eng (has view default) ok; summary ok
        r = requests.get(f"{BASE_URL}/projects/{PID}/attendance?month={self.today[:7]}", headers=h(self.eng))
        assert r.status_code == 200
        assert any(x["id"] == aid for x in r.json())

        r = requests.get(f"{BASE_URL}/projects/{PID}/attendance/summary?month={self.today[:7]}", headers=h(self.eng))
        assert r.status_code == 200
        assert r.json()["month"] == self.today[:7]

        # Engineer cannot approve correction
        r = requests.post(f"{BASE_URL}/attendance/{aid}/correct", headers=h(self.eng),
                         json={"check_in": "2026-01-01T09:00:00+00:00", "check_out": "2026-01-01T17:00:00+00:00",
                               "reason": "typo"})
        assert r.status_code == 403

        # PM can
        r = requests.post(f"{BASE_URL}/attendance/{aid}/correct", headers=h(self.pm),
                         json={"check_in": "2026-01-01T09:00:00+00:00", "check_out": "2026-01-01T17:00:00+00:00",
                               "reason": "clock sync"})
        assert r.status_code == 200
        assert r.json()["corrected"] is True
        assert any(ev["action"] == "correction" for ev in r.json()["history"])

        # CSV export needs export perm — PM manages so ok
        r = requests.get(f"{BASE_URL}/projects/{PID}/attendance/export?month={self.today[:7]}&auth={self.pm}")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

        # Engineer without export -> 403
        r = requests.get(f"{BASE_URL}/projects/{PID}/attendance/export?month={self.today[:7]}&auth={self.eng}")
        assert r.status_code == 403

    def teardown_method(self):
        DB.attendance.delete_many({"project_id": PID, "user_id": "user-eng", "date": self.today})


# ---------------------------------------------------------------------------
# 5) DPRs
# ---------------------------------------------------------------------------
class TestDPR:
    _dpr_id = None

    def setup_method(self):
        self.admin = login(SA_EMAIL, NEW_SA_PASS)
        self.pm = login(*PM)
        self.eng = login(*ENG)
        DB.dprs.delete_many({"project_id": PID})

    def test_full_dpr_flow(self):
        today = datetime.now(IST).date().isoformat()

        # Engineer creates DPR
        r = requests.post(f"{BASE_URL}/projects/{PID}/dprs", headers=h(self.eng),
                         json={"report_date": today, "weather": "Sunny",
                               "activities": [{"description": "Column casting", "planned_pct": 100, "actual_pct": 80}],
                               "manpower": [{"name": "Mason", "count": 5, "hours": 8}],
                               "next_day_plan": "Cure columns"})
        assert r.status_code == 200, r.text
        did = r.json()["id"]
        TestDPR._dpr_id = did

        # Duplicate date -> 409
        r = requests.post(f"{BASE_URL}/projects/{PID}/dprs", headers=h(self.eng),
                         json={"report_date": today, "activities": []})
        assert r.status_code == 409

        # Invalid photo file_id -> 400
        r = requests.put(f"{BASE_URL}/dprs/{did}", headers=h(self.eng),
                        json={"report_date": today, "activities": [], "photos": [{"file_id": "not-here", "caption": "x"}]})
        assert r.status_code == 400

        # Review before submit -> 400
        r = requests.post(f"{BASE_URL}/dprs/{did}/review", headers=h(self.pm),
                         json={"action": "approve", "comment": ""})
        assert r.status_code == 400

        # Submit
        r = requests.post(f"{BASE_URL}/dprs/{did}/submit", headers=h(self.eng))
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"

        # Edit after submit -> 400 (only draft/returned)
        r = requests.put(f"{BASE_URL}/dprs/{did}", headers=h(self.eng),
                        json={"report_date": today, "activities": []})
        assert r.status_code == 400

        # Creator can't review own
        r = requests.post(f"{BASE_URL}/dprs/{did}/review", headers=h(self.eng),
                         json={"action": "approve", "comment": ""})
        assert r.status_code == 403

        # Return requires comment
        r = requests.post(f"{BASE_URL}/dprs/{did}/review", headers=h(self.pm),
                         json={"action": "return", "comment": ""})
        assert r.status_code == 400

        # Return ok
        r = requests.post(f"{BASE_URL}/dprs/{did}/review", headers=h(self.pm),
                         json={"action": "return", "comment": "Please fix activities"})
        assert r.status_code == 200
        assert r.json()["status"] == "returned"

        # Edit allowed in returned, resubmit
        r = requests.put(f"{BASE_URL}/dprs/{did}", headers=h(self.eng),
                        json={"report_date": today, "activities": [{"description": "Column casting", "actual_pct": 100}]})
        assert r.status_code == 200
        r = requests.post(f"{BASE_URL}/dprs/{did}/submit", headers=h(self.eng))
        assert r.status_code == 200

        # Approve
        r = requests.post(f"{BASE_URL}/dprs/{did}/review", headers=h(self.pm),
                         json={"action": "approve"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # Engineer gets dpr_decision notification
        n = requests.get(f"{BASE_URL}/notifications", headers=h(self.eng)).json()
        items = n["items"] if isinstance(n, dict) else n
        assert any(x["type"] == "dpr_decision" for x in items), f"no notification: {items[:3]}"

        # PDF
        r = requests.get(f"{BASE_URL}/dprs/{did}/pdf?auth={self.eng}")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content.startswith(b"%PDF")

    def teardown_method(self):
        DB.dprs.delete_many({"project_id": PID})


# ---------------------------------------------------------------------------
# 6) Push notifications
# ---------------------------------------------------------------------------
class TestPush:
    def setup_method(self):
        self.eng = login(*ENG)

    def test_public_key_and_subscription(self):
        r = requests.get(f"{BASE_URL}/push/public-key")
        assert r.status_code == 200 and r.json()["public_key"]

        # Bad endpoint
        r = requests.post(f"{BASE_URL}/push/subscribe", headers=h(self.eng),
                         json={"endpoint": "http://not-https", "keys": {"p256dh": "a", "auth": "b"}})
        assert r.status_code == 400

        # Missing keys
        r = requests.post(f"{BASE_URL}/push/subscribe", headers=h(self.eng),
                         json={"endpoint": "https://example.com/fake", "keys": {"p256dh": "a"}})
        assert r.status_code == 400

        # Valid subscribe (fake endpoint)
        fake_ep = "https://fcm.googleapis.com/fcm/send/TEST-FAKE-ENDPOINT"
        r = requests.post(f"{BASE_URL}/push/subscribe", headers=h(self.eng),
                         json={"endpoint": fake_ep,
                               "keys": {"p256dh": "BOGUS_P256DH_KEY", "auth": "BOGUS_AUTH"}})
        assert r.status_code == 200
        assert r.json()["devices"] >= 1

        # Status returns something
        r = requests.get(f"{BASE_URL}/push/status", headers=h(self.eng))
        assert r.status_code == 200

        # Test endpoint — should NOT crash even though push will fail
        r = requests.post(f"{BASE_URL}/push/test", headers=h(self.eng))
        assert r.status_code == 200
        time.sleep(1)
        # A log should have been created (failed/expired_removed)
        r = requests.get(f"{BASE_URL}/push/status", headers=h(self.eng))
        assert r.status_code == 200
        logs = r.json().get("recent", [])
        # Expect at least one entry if a sub existed
        assert isinstance(logs, list)

        # Unsubscribe
        r = requests.post(f"{BASE_URL}/push/unsubscribe", headers=h(self.eng),
                         json={"endpoint": fake_ep, "keys": {"p256dh": "a", "auth": "b"}})
        assert r.status_code == 200

    def teardown_method(self):
        DB.push_subscriptions.delete_many({"user_id": "user-eng"})
        DB.push_logs.delete_many({"user_id": "user-eng"})


# ---------------------------------------------------------------------------
# 7) Weekly digest
# ---------------------------------------------------------------------------
class TestDigest:
    def setup_method(self):
        self.admin = login(SA_EMAIL, NEW_SA_PASS)
        self.pm = login(*PM)
        DB.digest_logs.delete_many({"company_id": "civio"})

    def test_settings_and_cron(self):
        # PM blocked
        r = requests.get(f"{BASE_URL}/digest/settings", headers=h(self.pm))
        assert r.status_code == 403

        # Admin ok
        r = requests.get(f"{BASE_URL}/digest/settings", headers=h(self.admin))
        assert r.status_code == 200

        # Bad timezone
        r = requests.put(f"{BASE_URL}/digest/settings", headers=h(self.admin),
                         json={"enabled": True, "day_of_week": 0, "hour": 9, "timezone": "Mars/Olympus", "recipient_ids": []})
        assert r.status_code == 400

        # Client as recipient — client is NOT admin/PM -> 400
        r = requests.put(f"{BASE_URL}/digest/settings", headers=h(self.admin),
                         json={"enabled": True, "day_of_week": 0, "hour": 9, "timezone": "Asia/Kolkata",
                               "recipient_ids": ["user-client"]})
        assert r.status_code == 400

        # Set to current IST weekday/hour
        now_ist = datetime.now(IST)
        r = requests.put(f"{BASE_URL}/digest/settings", headers=h(self.admin),
                         json={"enabled": True, "day_of_week": now_ist.weekday(), "hour": now_ist.hour,
                               "timezone": "Asia/Kolkata", "recipient_ids": []})
        assert r.status_code == 200

        # Cron without secret
        r = requests.post(f"{BASE_URL}/cron/weekly-digest", json={})
        assert r.status_code == 401

        secret = os.environ.get("WEBHOOK_CRON_SECRET")
        if not secret:
            # read from backend .env
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("WEBHOOK_CRON_SECRET"):
                        secret = line.split("=", 1)[1].strip().strip('"')
                        break
        assert secret

        # Cron with secret twice -> exactly 1 scheduled log for this ISO week
        for _ in range(2):
            r = requests.post(f"{BASE_URL}/cron/weekly-digest",
                              headers={"Authorization": f"Bearer {secret}"}, json={})
            assert r.status_code == 200 and r.json().get("accepted") is True
            time.sleep(2)

        # Fetch logs
        time.sleep(2)
        r = requests.get(f"{BASE_URL}/digest/logs", headers=h(self.admin))
        assert r.status_code == 200
        logs = r.json()
        iso = datetime.now(IST).isocalendar()
        key = f"week-{iso[0]}-{iso[1]:02d}"
        scheduled = [l for l in logs if l.get("key") == key and l.get("trigger") == "scheduled"]
        assert len(scheduled) == 1, f"Expected 1 scheduled log for {key}, got {len(scheduled)}: {logs}"

        # send-now also creates a log
        r = requests.post(f"{BASE_URL}/digest/send-now", headers=h(self.admin))
        assert r.status_code == 200
        time.sleep(3)
        r = requests.get(f"{BASE_URL}/digest/logs", headers=h(self.admin))
        assert any(l.get("trigger") == "manual" for l in r.json())

    def teardown_method(self):
        DB.digest_logs.delete_many({"company_id": "civio"})
        DB.digest_settings.delete_many({"company_id": "civio"})


# ---------------------------------------------------------------------------
# 8) Residential workspace scope regression
# ---------------------------------------------------------------------------
class TestResidentialScope:
    """Register a residential enterprise and ensure commercial APIs return 403."""
    _ent_id = None
    _tok = None

    def setup_method(self):
        self.sa = login(SA_EMAIL, NEW_SA_PASS)
        suffix = str(int(time.time()))
        email = f"test_res_{suffix}@example.com"
        self.email = email
        self.ent_id = None

        # Register
        r = requests.post(f"{BASE_URL}/auth/register-enterprise", json={
            "company_name": f"TEST_RES_{suffix}", "business_type": "residential",
            "name": "Test Owner", "email": email, "phone": "+919000000000", "password": "ResOwner@2026"})
        assert r.status_code == 200, r.text

        # Bypass OTP
        DB.users.update_one({"email": email}, {"$set": {"email_verified": True}})
        u = DB.users.find_one({"email": email})
        assert u, "user not created"
        self.ent_id = u["company_id"]

        # Super-admin approves
        r = requests.post(f"{BASE_URL}/superadmin/enterprises/{self.ent_id}/status",
                          headers=h(self.sa), json={"status": "active", "reason": ""})
        assert r.status_code == 200, r.text

        # Login as new residential admin
        r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": "ResOwner@2026"})
        assert r.status_code == 200, r.text
        self.tok = r.json()["access_token"]

    def test_commercial_apis_blocked(self):
        for path in ["/employees", "/org/config"]:
            r = requests.get(f"{BASE_URL}{path}", headers=h(self.tok))
            assert r.status_code == 403, f"{path} should be 403 for residential, got {r.status_code}"

        # digest settings — residential admin should be 403 (require_module dpr)
        r = requests.get(f"{BASE_URL}/digest/settings", headers=h(self.tok))
        assert r.status_code == 403

        # create a project to try DPR endpoint
        r = requests.post(f"{BASE_URL}/projects", headers=h(self.tok), json={
            "name": "Residential test", "code": f"RES-{int(time.time())}",
            "location": "x", "start_date": "2026-01-01", "target_date": "2026-12-31"})
        if r.status_code == 200:
            rpid = r.json()["id"]
            r = requests.get(f"{BASE_URL}/projects/{rpid}/dprs", headers=h(self.tok))
            assert r.status_code == 403

    def teardown_method(self):
        # Clean up entirely
        DB.users.delete_many({"email": self.email})
        if self.ent_id:
            DB.enterprises.delete_many({"id": self.ent_id})
            DB.projects.delete_many({"company_id": self.ent_id})
