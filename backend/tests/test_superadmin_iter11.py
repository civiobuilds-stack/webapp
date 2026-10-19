"""Iteration 11: Super Admin dashboard upgrade - create enterprise, reset owner, history, subscription, plans, security."""
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient


def _env(path, key):
    for line in Path(path).read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
mdb = MongoClient(_env("/app/backend/.env", "MONGO_URL"))[_env("/app/backend/.env", "DB_NAME")]

SUPER = ("civiobuilds@gmail.com", "Civio@123456")
RES_OWNER = ("owner@civiohomes.build", "CivioHome@2026")


def login(email, pw):
    mdb.login_attempts.delete_many({})
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def sa():
    r = login(*SUPER)
    assert r.status_code == 200, r.text
    return hdr(r.json()["access_token"])


@pytest.fixture(scope="module")
def ent(sa):
    email = f"test_owner_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/superadmin/enterprises", headers=sa, json={
        "company_name": f"TEST_Ent {uuid.uuid4().hex[:4]}", "business_type": "commercial", "city": "Pune",
        "owner_name": "Test Owner", "owner_email": email, "plan_id": "starter"})
    assert r.status_code == 200, r.text
    d = r.json()
    yield d
    # cleanup
    eid = d["enterprise_id"]
    mdb.users.delete_many({"company_id": eid})
    mdb.projects.delete_many({"company_id": eid})
    mdb.enterprises.delete_one({"id": eid})
    mdb.platform_audit.delete_many({"enterprise_id": eid})
    mdb.login_attempts.delete_many({})


# --- Create enterprise
class TestCreateEnterprise:
    def test_created_active_and_owner_login(self, sa, ent):
        assert ent["temporary_password"].startswith("Civio@")
        e = mdb.enterprises.find_one({"id": ent["enterprise_id"]})
        assert e["status"] == "active" and e["plan_id"] == "starter"
        assert e["limits"]["max_users"] == 15
        r = login(ent["login_id"], ent["temporary_password"])
        assert r.status_code == 200, r.text
        print("owner must_change_password after create:", r.json()["user"].get("must_change_password"))

    def test_duplicate_email_400(self, sa, ent):
        r = requests.post(f"{API}/superadmin/enterprises", headers=sa, json={
            "company_name": "TEST_Dup", "business_type": "commercial", "owner_name": "Dup", "owner_email": ent["login_id"]})
        assert r.status_code == 400

    def test_bad_type_and_plan_400(self, sa):
        base = {"company_name": "TEST_X", "owner_name": "Xx", "owner_email": f"test_{uuid.uuid4().hex[:6]}@example.com"}
        assert requests.post(f"{API}/superadmin/enterprises", headers=sa, json={**base, "business_type": "foo"}).status_code == 400
        assert requests.post(f"{API}/superadmin/enterprises", headers=sa, json={**base, "business_type": "residential", "plan_id": "nope"}).status_code == 400


# --- Reset owner
class TestResetOwner:
    def test_reset_owner(self, sa, ent):
        old = ent["temporary_password"]
        r = requests.post(f"{API}/superadmin/enterprises/{ent['enterprise_id']}/reset-owner", headers=sa)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["login_id"] == ent["login_id"] and d["temporary_password"] != old
        assert "password_hash" not in d
        assert login(ent["login_id"], old).status_code == 401
        r2 = login(ent["login_id"], d["temporary_password"])
        assert r2.status_code == 200
        assert r2.json()["user"]["must_change_password"] is True
        # blocked until change
        tok = hdr(r2.json()["access_token"])
        assert requests.get(f"{API}/projects", headers=tok).status_code == 403
        # change password then usable
        newpw = "TestOwner@2026x"
        c = requests.post(f"{API}/auth/change-password", headers=tok, json={"current_password": d["temporary_password"], "new_password": newpw})
        assert c.status_code == 200, c.text
        ent["temporary_password"] = newpw

    def test_reset_civio_blocked(self, sa):
        r = requests.post(f"{API}/superadmin/enterprises/civio/reset-owner", headers=sa)
        assert r.status_code in (400, 404)

    def test_reset_unknown_404(self, sa):
        assert requests.post(f"{API}/superadmin/enterprises/nope/reset-owner", headers=sa).status_code == 404


# --- Status + history
class TestStatusHistory:
    def test_suspend_needs_reason(self, sa, ent):
        r = requests.post(f"{API}/superadmin/enterprises/{ent['enterprise_id']}/status", headers=sa, json={"status": "suspended", "reason": " "})
        assert r.status_code == 400

    def test_suspend_reactivate_history(self, sa, ent):
        eid = ent["enterprise_id"]
        r = requests.post(f"{API}/superadmin/enterprises/{eid}/status", headers=sa, json={"status": "suspended", "reason": "TEST_nonpayment"})
        assert r.status_code == 200 and r.json()["status"] == "suspended"
        # owner blocked
        t = login(ent["login_id"], ent["temporary_password"])
        if t.status_code == 200:
            assert requests.get(f"{API}/projects", headers=hdr(t.json()["access_token"])).status_code == 403
        r = requests.post(f"{API}/superadmin/enterprises/{eid}/status", headers=sa, json={"status": "active", "reason": "TEST_paid offline"})
        assert r.status_code == 200 and r.json()["status"] == "active"
        h = requests.get(f"{API}/superadmin/enterprises/{eid}/history", headers=sa).json()
        tos = [(s["from"], s["to"], s["reason"]) for s in h["status_history"]]
        assert tos[0][1] == "active"
        assert (None if False else "active", "suspended", "TEST_nonpayment") in tos
        assert ("suspended", "active", "TEST_paid offline") in tos
        assert any(a["action"] == "owner access reset" for a in h["audit"])

    def test_cannot_suspend_civio(self, sa):
        r = requests.post(f"{API}/superadmin/enterprises/civio/status", headers=sa, json={"status": "suspended", "reason": "x"})
        assert r.status_code == 400


# --- Subscription
class TestSubscription:
    def test_paid_rejected(self, sa, ent):
        r = requests.put(f"{API}/superadmin/enterprises/{ent['enterprise_id']}/subscription", headers=sa,
                         json={"plan_id": "starter", "billing_status": "paid"})
        assert r.status_code == 400

    def test_bad_period_and_date(self, sa, ent):
        u = f"{API}/superadmin/enterprises/{ent['enterprise_id']}/subscription"
        assert requests.put(u, headers=sa, json={"plan_id": "starter", "billing_status": "manual", "billing_period": "weekly"}).status_code == 400
        assert requests.put(u, headers=sa, json={"plan_id": "starter", "billing_status": "manual", "subscription_expires_at": "31-12-2026"}).status_code == 422

    def test_states_and_persist(self, sa, ent):
        u = f"{API}/superadmin/enterprises/{ent['enterprise_id']}/subscription"
        soon = (date.today() + timedelta(days=5)).isoformat()
        r = requests.put(u, headers=sa, json={"plan_id": "starter", "billing_status": "pending_payment", "billing_period": "quarterly", "subscription_expires_at": soon})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["subscription_state"] == "expiring_soon" and d["billing_period"] == "quarterly" and d["billing_status"] == "pending_payment"
        far = (date.today() + timedelta(days=90)).isoformat()
        assert requests.put(u, headers=sa, json={"plan_id": "starter", "billing_status": "manual", "subscription_expires_at": far}).json()["subscription_state"] == "active"

    def test_expired_blocks_users_projects(self, sa, ent):
        u = f"{API}/superadmin/enterprises/{ent['enterprise_id']}/subscription"
        past = (date.today() - timedelta(days=2)).isoformat()
        r = requests.put(u, headers=sa, json={"plan_id": "starter", "billing_status": "overdue", "subscription_expires_at": past})
        assert r.status_code == 200 and r.json()["subscription_state"] == "expired"
        lst = requests.get(f"{API}/superadmin/enterprises", headers=sa, params={"q": ent["login_id"]}).json()
        assert lst and lst[0]["subscription_state"] == "expired"
        t = login(ent["login_id"], ent["temporary_password"])
        assert t.status_code == 200, t.text
        oh = hdr(t.json()["access_token"])
        ru = requests.post(f"{API}/users", headers=oh, json={"email": f"test_u_{uuid.uuid4().hex[:6]}@example.com", "password": "Passw0rd!",
                                                              "name": "TEST U", "role": "project_manager", "phone": "9999999999"})
        assert ru.status_code == 403, ru.text
        assert ru.json()["detail"]["code"] == "subscription_expired"
        rp = requests.post(f"{API}/projects", headers=oh, json={"name": "TEST_P", "code": f"T-{uuid.uuid4().hex[:4]}"})
        print("project create on expired:", rp.status_code, rp.text[:200])
        assert rp.status_code == 403
        assert rp.json()["detail"]["code"] == "subscription_expired"
        # renewing unblocks
        requests.put(u, headers=sa, json={"plan_id": "starter", "billing_status": "manual", "subscription_expires_at": None})
        ru2 = requests.post(f"{API}/users", headers=oh, json={"email": f"test_u_{uuid.uuid4().hex[:6]}@example.com", "password": "Passw0rd!",
                                                               "name": "TEST U", "role": "project_manager", "phone": "9999999999"})
        assert ru2.status_code == 200, ru2.text


# --- Plans
class TestPlans:
    def test_plan_period_update(self, sa):
        plans = requests.get(f"{API}/superadmin/plans", headers=sa).json()
        p = next(x for x in plans if x["id"] == "starter")
        orig = p.get("billing_period", "monthly")
        body = {k: p[k] for k in ("name", "price_monthly", "max_users", "max_projects", "max_storage_mb")}
        body["description"] = p.get("description", "")
        try:
            r = requests.put(f"{API}/superadmin/plans/starter", headers=sa, json={**body, "billing_period": "yearly"})
            assert r.status_code == 200 and r.json()["billing_period"] == "yearly"
            again = next(x for x in requests.get(f"{API}/superadmin/plans", headers=sa).json() if x["id"] == "starter")
            assert again["billing_period"] == "yearly"
            assert requests.put(f"{API}/superadmin/plans/starter", headers=sa, json={**body, "billing_period": "weekly"}).status_code == 400
            assert requests.put(f"{API}/superadmin/plans/nope", headers=sa, json={**body, "billing_period": "monthly"}).status_code == 404
        finally:
            requests.put(f"{API}/superadmin/plans/starter", headers=sa, json={**body, "billing_period": orig})


# --- Security
class TestSecurity:
    @pytest.mark.parametrize("method,path", [
        ("get", "/superadmin/overview"), ("get", "/superadmin/enterprises"), ("get", "/superadmin/plans"), ("get", "/superadmin/audit"),
        ("post", "/superadmin/enterprises"), ("post", "/superadmin/enterprises/civio-homes/reset-owner"),
        ("get", "/superadmin/enterprises/civio-homes/history"), ("post", "/superadmin/enterprises/civio-homes/status"),
        ("put", "/superadmin/enterprises/civio-homes/subscription"), ("put", "/superadmin/plans/free")])
    def test_non_superadmin_403(self, method, path):
        r = login(*RES_OWNER)
        assert r.status_code == 200
        res = getattr(requests, method)(f"{API}{path}", headers=hdr(r.json()["access_token"]), json={})
        assert res.status_code == 403, f"{path} -> {res.status_code}"

    def test_unauth_401(self):
        assert requests.get(f"{API}/superadmin/enterprises").status_code == 401
