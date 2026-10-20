"""Iteration 13: subscription lifecycle, cron reminders, team add/remove, per-project access, fleet flow, selfie attendance."""
import io
import os
import subprocess
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
CRON_SECRET = None
for line in open("/app/backend/.env"):
    if line.startswith("WEBHOOK_CRON_SECRET"):
        CRON_SECRET = line.split("=", 1)[1].strip().strip('"')

SA = ("civiobuilds@gmail.com", "Civio@123456")
PM = ("pm@civio.build", "CivioPM@2026")
ENG = ("engineer@civio.build", "CivioEng@2026")
ENG2 = ("engineer2@civio.build", "CivioEng@2026")
ACC = ("accounts@civio.build", "CivioRole@2026")
DRV = ("driver@civio.build", "CivioRole@2026")
STORE = ("store@civio.build", "CivioRole@2026")
R_OWNER = ("owner@civiohomes.build", "CivioHome@2026")
R_PM = ("pm@civiohomes.build", "CivioHome@2026")
TODAY = date.today()
_tok = {}


def mongo(js):
    return subprocess.run(["mongosh", "test_database", "--quiet", "--eval", js], capture_output=True, text=True).stdout


def tok(cred):
    if cred[0] not in _tok:
        mongo("db.login_attempts.deleteMany({})")
        r = requests.post(f"{API}/auth/login", json={"email": cred[0], "password": cred[1]})
        assert r.status_code == 200, r.text
        _tok[cred[0]] = r.json()["access_token"]
    return _tok[cred[0]]


def H(cred):
    return {"Authorization": f"Bearer {tok(cred)}"}


def jpeg():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 100, 50)).save(b, "JPEG")
    return b.getvalue()


# ---------------- Subscription lifecycle ----------------
class TestSubscription:
    def test_expire_then_restore(self):
        past = (TODAY - timedelta(days=2)).isoformat()
        r = requests.post(f"{API}/superadmin/enterprises/civio-homes/lifecycle", headers=H(SA), json={"action": "set_trial", "trial_end": past})
        assert r.status_code == 200, r.text
        try:
            h = H(R_OWNER)
            r = requests.get(f"{API}/projects", headers=h)
            assert r.status_code == 403 and r.json()["detail"]["code"] == "subscription_expired"
            r = requests.get(f"{API}/projects/proj-res-1/activities", headers=h)
            assert r.status_code == 403
            r = requests.get(f"{API}/files/x/download", params={"auth": tok(R_OWNER)})
            assert r.status_code == 403, r.text
            me = requests.get(f"{API}/auth/me", headers=h)
            assert me.status_code == 200
            assert me.json().get("subscription", {}).get("expired") is True, me.json().get("subscription")
            info = requests.get(f"{API}/subscription/info", headers=h)
            assert info.status_code == 200 and info.json()["expired"] is True and "plans" in info.json()
            ar = requests.post(f"{API}/subscription/activation-request", headers=h, json={"message": "TEST_please"})
            assert ar.status_code == 200 and ar.json()["ok"]
            ents = requests.get(f"{API}/superadmin/enterprises", headers=H(SA)).json()
            ent = next(e for e in (ents if isinstance(ents, list) else ents.get("enterprises", [])) if e["id"] == "civio-homes")
            print("SA ent keys:", {k: ent.get(k) for k in ent if "activ" in k or "subscr" in k})
            assert any("activation" in k and ent.get(k) for k in ent), "activation requested not surfaced in SA list"
            # extend -> restore
            r = requests.post(f"{API}/superadmin/enterprises/civio-homes/lifecycle", headers=H(SA), json={"action": "extend_trial", "days": 5})
            assert r.status_code == 200
            assert r.json()["trial_end"] == (TODAY + timedelta(days=5)).isoformat()
            assert requests.get(f"{API}/projects", headers=h).status_code == 200
            # expire again then activate
            requests.post(f"{API}/superadmin/enterprises/civio-homes/lifecycle", headers=H(SA), json={"action": "set_trial", "trial_end": past})
            assert requests.get(f"{API}/projects", headers=h).status_code == 403
            r = requests.post(f"{API}/superadmin/enterprises/civio-homes/lifecycle", headers=H(SA),
                              json={"action": "activate", "renewal_date": (TODAY + timedelta(days=30)).isoformat()})
            assert r.status_code == 200
            assert requests.get(f"{API}/projects", headers=h).status_code == 200
            r = requests.post(f"{API}/superadmin/enterprises/civio-homes/lifecycle", headers=H(SA),
                              json={"action": "activate", "renewal_date": past})
            assert r.status_code == 400
        finally:
            mongo("db.enterprises.updateOne({id:'civio-homes'},{$unset:{subscription_state:'',trial_end:'',trial_start:'',subscription_expires_at:''}});"
                  "db.activation_requests.deleteMany({message:'TEST_please'})")

    def test_trial_banner_info(self):
        mongo(f"db.enterprises.updateOne({{id:'civio-homes'}},{{$set:{{subscription_state:'trial',trial_end:'{(TODAY + timedelta(days=4)).isoformat()}'}}}})")
        try:
            info = requests.get(f"{API}/subscription/info", headers=H(R_OWNER)).json()
            assert info["state"] == "trial" and info["days_left"] == 4
        finally:
            mongo("db.enterprises.updateOne({id:'civio-homes'},{$unset:{subscription_state:'',trial_end:'',trial_start:'',subscription_expires_at:''}})")

    def test_civio_exempt(self):
        info = requests.get(f"{API}/subscription/info", headers=H(PM)).json()
        assert info["expired"] is False

    def test_billing_settings_and_create_with_trial(self):
        orig = requests.get(f"{API}/superadmin/settings/billing", headers=H(SA)).json()
        r = requests.put(f"{API}/superadmin/settings/billing", headers=H(SA), json={"payment_instructions": "TEST_ pay UPI", "default_trial_days": 21})
        assert r.status_code == 200 and r.json()["default_trial_days"] == 21
        assert requests.get(f"{API}/superadmin/settings/billing", headers=H(SA)).json()["payment_instructions"] == "TEST_ pay UPI"
        email = f"test_owner_{os.urandom(3).hex()}@example.com"
        r = requests.post(f"{API}/superadmin/enterprises", headers=H(SA), json={"company_name": "TEST_ Trial Co", "business_type": "residential",
                                                                                 "owner_name": "Test Owner", "owner_email": email, "trial_days": 10})
        assert r.status_code == 200, r.text
        eid = r.json()["enterprise_id"]
        ent = mongo(f"printjson(db.enterprises.findOne({{id:'{eid}'}},{{_id:0,trial_end:1,subscription_state:1}}))")
        assert (TODAY + timedelta(days=10)).isoformat() in ent and "trial" in ent
        # restore settings
        requests.put(f"{API}/superadmin/settings/billing", headers=H(SA), json={"payment_instructions": orig.get("payment_instructions", ""),
                                                                                 "default_trial_days": orig.get("default_trial_days")})


# ---------------- Cron reminders ----------------
class TestCron:
    def test_cron_auth_and_dedupe(self):
        assert requests.post(f"{API}/cron/subscription-reminders").status_code == 401
        assert requests.post(f"{API}/cron/subscription-reminders", headers={"Authorization": "Bearer wrong"}).status_code == 401
        end = (TODAY + timedelta(days=7)).isoformat()
        mongo(f"db.enterprises.updateOne({{id:'civio-homes'}},{{$set:{{subscription_state:'trial',trial_end:'{end}'}}}});"
              "db.subscription_email_log.deleteMany({enterprise_id:'civio-homes'})")
        try:
            import time
            for _ in range(2):
                r = requests.post(f"{API}/cron/subscription-reminders", headers={"Authorization": f"Bearer {CRON_SECRET}"})
                assert r.status_code == 200 and r.json()["accepted"]
                time.sleep(6)
            n = mongo("print(db.subscription_email_log.countDocuments({enterprise_id:'civio-homes'}))").strip()
            assert n == "1", n
        finally:
            mongo("db.enterprises.updateOne({id:'civio-homes'},{$unset:{subscription_state:'',trial_end:'',trial_start:'',subscription_expires_at:''}})")


# ---------------- Team add/remove ----------------
class TestTeam:
    def test_users_list_all_roles_for_pm(self):
        r = requests.get(f"{API}/users", headers=H(R_PM))
        assert r.status_code == 200
        roles = {u["role"] for u in r.json()}
        print("res PM sees roles", roles)
        r = requests.get(f"{API}/users", headers=H(PM))
        roles = {u["role"] for u in r.json()}
        print("comm PM sees roles", roles)
        assert {"accounts", "driver", "store_incharge"} <= roles

    def test_add_multiple_and_remove_history(self):
        pid = "proj-res-1"
        h = H(R_PM)
        users = requests.get(f"{API}/users", headers=h).json()
        p = requests.get(f"{API}/projects/{pid}", headers=h).json()
        on = {t["user_id"] for t in p.get("team", []) if not t.get("removed_at")} | set(p.get("engineer_ids", [])) | {p.get("project_manager_id"), p.get("client_id")}
        cands = [u for u in users if u["id"] not in on and u["role"] not in {"admin", "client", "project_manager"}][:2]
        if not cands:
            pytest.skip("no free candidates")
        for u in cands:
            r = requests.post(f"{API}/projects/{pid}/team", headers=h, json={"user_id": u["id"], "job_title": "TEST_"})
            assert r.status_code == 200, r.text
        for u in cands:
            r = requests.delete(f"{API}/projects/{pid}/team/{u['id']}", headers=h)
            assert r.status_code == 200, r.text
        hist = mongo(f"print(JSON.stringify(db.projects.findOne({{id:'{pid}'}},{{_id:0,team_history:1}}).team_history.filter(x=>x.user_id=='{cands[0]['id']}').map(x=>x.action)))")
        assert "added" in hist and "removed" in hist

    def test_pm_not_managing_gets_403(self):
        r = requests.post(f"{API}/projects/4491459d-14c1-4448-b50f-dc468eefddfb/team", headers=H(PM), json={"user_id": "user-store"})
        assert r.status_code == 403, r.text


# ---------------- Access control ----------------
class TestAccess:
    def test_activities_none_blocks_engineer(self):
        pid = "proj-demo-1"
        orig = mongo(f"printjson(db.project_members.findOne({{project_id:'{pid}',user_id:'user-eng2'}},{{_id:0}}))")
        print("orig member", orig[:300])
        mp = requests.get(f"{API}/projects/{pid}/my-permissions", headers=H(ENG2)).json()["permissions"]
        mp = {k: v for k, v in mp.items() if v}
        mp.pop("activities", None)
        mp.pop("billing", None)
        r = requests.put(f"{API}/projects/{pid}/members/user-eng2", headers=H(PM), json={"responsibility": "TEST_", "permissions": mp})
        assert r.status_code == 200, r.text
        try:
            assert requests.get(f"{API}/projects/{pid}/activities", headers=H(ENG2)).status_code == 403
            assert requests.get(f"{API}/projects/{pid}/dpr", headers=H(ENG2)).status_code in (200, 404)
            proj = requests.get(f"{API}/projects/{pid}", headers=H(ENG2)).json()
            assert "contract_value" not in proj
            assert requests.get(f"{API}/projects/{pid}/cost-summary", headers=H(ENG2)).status_code == 403
            lst = requests.get(f"{API}/projects", headers=H(ENG2)).json()
            assert all("contract_value" not in p for p in lst)
        finally:
            mongo(f"db.project_members.deleteOne({{project_id:'{pid}',user_id:'user-eng2'}})")

    def test_accounts_sees_bills_and_cost(self):
        assert requests.get(f"{API}/projects/proj-demo-1/bills", headers=H(ACC)).status_code == 200
        assert "contract_value" in requests.get(f"{API}/projects/proj-demo-1", headers=H(PM)).json()


# ---------------- Fleet ----------------
class TestFleet:
    def test_fleet_flow(self):
        pid = "proj-demo-1"
        assert requests.get(f"{API}/vehicles", headers=H(ACC)).status_code == 403
        assert requests.get(f"{API}/vehicles", headers=H(ENG)).status_code == 403
        f, t = (TODAY + timedelta(days=200)).isoformat(), (TODAY + timedelta(days=202)).isoformat()
        r = requests.post(f"{API}/projects/{pid}/vehicle-requests", headers=H(ENG), json={"purpose": "TEST_ material", "destination": "TEST_ site", "from_date": f, "to_date": t})
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        reg = f"TEST{os.urandom(2).hex().upper()}"
        v = requests.post(f"{API}/vehicles", headers=H(PM), json={"reg_no": reg, "model": "Tata Ace", "vehicle_type": "Truck"})
        assert v.status_code == 200, v.text
        vid = v.json()["id"]
        assert requests.post(f"{API}/vehicles", headers=H(PM), json={"reg_no": reg.lower(), "model": "dup"}).status_code == 409
        r = requests.post(f"{API}/vehicle-requests/{tid}/assign", headers=H(PM), json={"vehicle_id": vid, "driver_id": "user-driver"})
        assert r.status_code == 400
        assert requests.post(f"{API}/vehicle-requests/{tid}/decision", headers=H(ENG), json={"action": "approve"}).status_code == 403
        r = requests.post(f"{API}/vehicle-requests/{tid}/decision", headers=H(PM), json={"action": "approve"})
        assert r.status_code == 200 and r.json()["status"] == "approved"
        r = requests.post(f"{API}/vehicle-requests/{tid}/assign", headers=H(PM), json={"vehicle_id": vid, "driver_id": "user-driver"})
        assert r.status_code == 200 and r.json()["status"] == "assigned", r.text
        # overlapping
        r2 = requests.post(f"{API}/projects/{pid}/vehicle-requests", headers=H(ENG), json={"purpose": "TEST_ overlap", "destination": "x", "from_date": t, "to_date": t})
        tid2 = r2.json()["id"]
        requests.post(f"{API}/vehicle-requests/{tid2}/decision", headers=H(PM), json={"action": "approve"})
        r = requests.post(f"{API}/vehicle-requests/{tid2}/assign", headers=H(PM), json={"vehicle_id": vid})
        assert r.status_code == 409, r.text
        trips = requests.get(f"{API}/my-trips", headers=H(DRV)).json()
        assert any(x["id"] == tid for x in trips)
        assert requests.post(f"{API}/vehicle-requests/{tid}/status", headers=H(DRV), json={"action": "start"}).json()["status"] == "in_progress"
        assert requests.post(f"{API}/vehicle-requests/{tid}/status", headers=H(DRV), json={"action": "return"}).json()["status"] == "returned"
        r = requests.post(f"{API}/vehicle-requests/{tid2}/assign", headers=H(PM), json={"vehicle_id": vid})
        assert r.status_code == 200, r.text
        assert requests.post(f"{API}/vehicle-requests/{tid2}/status", headers=H(PM), json={"action": "return"}).json()["status"] == "returned"
        st = requests.get(f"{API}/fleet/status", headers=H(SA))
        assert st.status_code == 200 and any(x["id"] == vid for x in st.json())
        assert requests.get(f"{API}/vehicle-requests", headers=H(PM)).status_code == 200
        r = requests.put(f"{API}/vehicles/{vid}", headers=H(PM), json={"reg_no": reg, "model": "Tata Ace", "status": "inactive"})
        assert r.status_code == 200 and r.json()["status"] == "inactive"
        mongo(f"db.vehicles.deleteOne({{id:'{vid}'}});db.vehicle_requests.deleteMany({{purpose:/^TEST_/}})")


# ---------------- Selfie attendance ----------------
class TestSelfieAttendance:
    def test_selfie_flow(self):
        pid = "proj-demo-1"
        mongo("db.staff_attendance.deleteMany({user_id:'user-eng2'})")
        h = H(ENG2)
        r = requests.put(f"{API}/projects/{pid}/members/user-eng2", headers=H(PM), json={"responsibility": "", "attendance_required": True, "location_required": False})
        assert r.status_code == 200
        try:
            st = requests.get(f"{API}/my-attendance/status", headers=h).json()
            assert st["enabled"] and st["needs_check_in"]
            assert requests.post(f"{API}/my-attendance/check-out", headers=h, data={"lat": 19.0, "lng": 72.8}).status_code == 400
            # location required + far geofence
            requests.put(f"{API}/projects/{pid}/members/user-eng2", headers=H(PM), json={"responsibility": "", "location_required": True})
            g = requests.put(f"{API}/projects/{pid}/geofence", headers=H(PM), json={"lat": 28.6, "lng": 77.2, "radius_m": 200})
            print("geofence", g.status_code, g.text[:200])
            r = requests.post(f"{API}/my-attendance/check-in", headers=h, files={"selfie": ("s.jpg", jpeg(), "image/jpeg")},
                              data={"lat": "19.06", "lng": "72.83", "project_id": pid})
            assert r.status_code == 403, r.text
            requests.put(f"{API}/projects/{pid}/members/user-eng2", headers=H(PM), json={"responsibility": "", "location_required": False})
            r = requests.post(f"{API}/my-attendance/check-in", headers=h, files={"selfie": ("s.jpg", jpeg(), "image/jpeg")},
                              data={"lat": "19.06", "lng": "72.83", "project_id": pid})
            assert r.status_code == 200, r.text
            aid = r.json()["id"]
            r = requests.post(f"{API}/my-attendance/check-in", headers=h, files={"selfie": ("s.jpg", jpeg(), "image/jpeg")}, data={"lat": "19", "lng": "72"})
            assert r.status_code == 409
            team = requests.get(f"{API}/my-attendance/team", headers=H(PM)).json()
            assert any(x["id"] == aid for x in team["records"])
            assert requests.get(f"{API}/my-attendance/team", headers=H(ENG)).status_code == 403
            assert requests.get(f"{API}/my-attendance/{aid}/selfie", params={"auth": tok(ENG)}).status_code == 403
            assert requests.get(f"{API}/my-attendance/{aid}/selfie", params={"auth": tok(PM)}).status_code == 200
            assert requests.get(f"{API}/my-attendance/{aid}/selfie", params={"auth": tok(ENG2)}).status_code == 200
            assert requests.post(f"{API}/my-attendance/check-out", headers=h, data={"lat": 19.0, "lng": 72.8}).status_code == 200
            assert requests.post(f"{API}/my-attendance/check-out", headers=h, data={"lat": 19.0, "lng": 72.8}).status_code == 409
        finally:
            mongo("db.projects.updateOne({id:'proj-demo-1'},{$unset:{geofence:''}});db.staff_attendance.deleteMany({user_id:'user-eng2'})")
            mongo(f"db.project_members.deleteOne({{project_id:'{pid}',user_id:'user-eng2'}})")
