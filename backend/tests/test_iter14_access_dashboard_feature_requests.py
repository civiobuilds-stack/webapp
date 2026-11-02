# Iteration 14: Access-based dashboard cards + Feature requests
import os
import pytest
import requests
import subprocess

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
OTHER_PROJ = "4491459d-14c1-4448-b50f-dc468eefddfb"

CREDS = {
    "sa": ("civiobuilds@gmail.com", "Civio@123456"),
    "pm": ("pm@civio.build", "CivioPM@2026"),
    "eng": ("engineer@civio.build", "CivioEng@2026"),
    "store": ("store@civio.build", "CivioRole@2026"),
    "accounts": ("accounts@civio.build", "CivioRole@2026"),
    "driver": ("driver@civio.build", "CivioRole@2026"),
    "client": ("client@civiohomes.build", "CivioHome@2026"),
    "respm": ("pm@civiohomes.build", "CivioHome@2026"),
}
_tok = {}


def tok(k):
    if k not in _tok:
        subprocess.run(["mongosh", "test_database", "--quiet", "--eval", "db.login_attempts.deleteMany({})"], capture_output=True)
        e, p = CREDS[k]
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, f"login {k}: {r.status_code} {r.text}"
        _tok[k] = r.json()["access_token"]
    return {"Authorization": f"Bearer {_tok[k]}"}


def cards(k):
    r = requests.get(f"{API}/dashboard/role", headers=tok(k))
    assert r.status_code == 200, r.text
    d = r.json()
    return {c["key"] for c in d["cards"]}, set(d["modules"])


# --- Dashboard role cards per role
class TestRoleCards:
    def test_admin_all(self):
        keys, mods = cards("sa")
        assert {"store_approve", "dpr_review", "bills_owner", "to_issue", "trips_open"} <= keys
        assert {"dpr", "store", "billing", "vehicles"} <= mods

    def test_modules_endpoint(self):
        r = requests.get(f"{API}/dashboard/modules", headers=tok("eng"))
        assert r.status_code == 200 and isinstance(r.json()["modules"], list)

    def test_store(self):
        keys, _ = cards("store")
        print("store", keys)
        assert keys and all(k in {"to_issue", "return_receive", "shortage", "tools_out"} for k in keys)

    def test_driver(self):
        keys, mods = cards("driver")
        assert {"trips_today", "trips_upcoming"} <= keys and "vehicles" in mods

    def test_accounts(self):
        keys, mods = cards("accounts")
        print("accounts", keys, mods)
        assert "bills_unpaid" in keys or "bills_rejected" in keys
        assert not keys & {"dpr_review", "my_dprs", "to_issue"}


# --- Access toggling for engineer
class TestEngineerAccess:
    def test_toggle(self):
        base, _ = cards("eng")
        assert {"my_requests", "my_dprs"} <= base, base
        restricted = {"progress": ["view", "create"], "attendance": ["view"]}
        try:
            r1 = requests.put(f"{API}/projects/proj-demo-1/members/user-eng", headers=tok("pm"), json={"permissions": restricted})
            assert r1.status_code == 200, r1.text
            r2 = requests.put(f"{API}/projects/{OTHER_PROJ}/members/user-eng", headers=tok("sa"), json={"permissions": restricted})
            assert r2.status_code == 200, r2.text
            keys, mods = cards("eng")
            print("restricted", keys, mods)
            assert "my_requests" not in keys and "my_dprs" not in keys
            assert "dpr" not in mods and "store" not in mods
            # restore on one project only
            full = {"dpr": ["view", "create", "edit"], "store": ["view", "create", "edit"]}
            r3 = requests.put(f"{API}/projects/proj-demo-1/members/user-eng", headers=tok("pm"), json={"permissions": full})
            assert r3.status_code == 200
            keys, _ = cards("eng")
            assert {"my_requests", "my_dprs"} <= keys
        finally:
            requests.delete(f"{API}/projects/proj-demo-1/members/user-eng", headers=tok("pm"))
            requests.delete(f"{API}/projects/{OTHER_PROJ}/members/user-eng", headers=tok("sa"))
        keys, _ = cards("eng")
        assert {"my_requests", "my_dprs"} <= keys


# --- Feature requests
class TestFeatureRequests:
    def test_create_and_mine(self):
        r = requests.post(f"{API}/feature-requests", headers=tok("eng"),
                          json={"title": "TEST_ GPS photo tags", "description": "Tag DPR photos with GPS", "priority": "high"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user_name"] and d["user_email"] == "engineer@civio.build" and d["enterprise_name"] and d["priority"] == "high"
        mine = requests.get(f"{API}/feature-requests/mine", headers=tok("eng")).json()
        assert any(m["id"] == d["id"] for m in mine)
        sa = requests.get(f"{API}/superadmin/feature-requests", headers=tok("sa"))
        assert sa.status_code == 200
        row = next(x for x in sa.json() if x["id"] == d["id"])
        assert row["user_role"] and "user_phone" in row

    def test_bad_priority(self):
        r = requests.post(f"{API}/feature-requests", headers=tok("eng"), json={"title": "Abc def", "description": "something", "priority": "urgent"})
        assert r.status_code == 400

    def test_short_title(self):
        r = requests.post(f"{API}/feature-requests", headers=tok("eng"), json={"title": "ab", "description": "something"})
        assert r.status_code == 422

    def test_sa_list_forbidden(self):
        for k in ("eng", "pm", "client"):
            assert requests.get(f"{API}/superadmin/feature-requests", headers=tok(k)).status_code == 403

    def test_client_can_post(self):
        # Spec: clients should not be able to request features; check backend enforcement
        r = requests.post(f"{API}/feature-requests", headers=tok("client"), json={"title": "TEST_ client req", "description": "client wants x", "priority": "low"})
        print("client post", r.status_code)
        assert r.status_code == 403, f"client allowed to create feature request: {r.status_code}"
