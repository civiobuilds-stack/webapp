"""Multi-tenant SaaS tests: enterprise registration, super admin, tenant isolation, plan limits, business-type modules."""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

if not BASE:
    # fallback for pytest running outside the backend env
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip().rstrip("/")
            API = f"{BASE}/api"
    for line in Path("/app/backend/.env").read_text().splitlines():
        if line.startswith("MONGO_URL="):
            MONGO_URL = line.split("=", 1)[1].strip().strip('"')
        if line.startswith("DB_NAME="):
            DB_NAME = line.split("=", 1)[1].strip().strip('"')

mongo = MongoClient(MONGO_URL)
mdb = mongo[DB_NAME]

SUPER = ("civiobuilds@gmail.com", "CivioAdmin@2026")
PM = ("pm@civio.build", "CivioPM@2026")
ENG = ("engineer@civio.build", "CivioEng@2026")
CLIENT = ("client@civio.build", "CivioClient@2026")


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return r.json()["access_token"]


def hdr(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- cleanup ----------
TEST_ENT_IDS = []
TEST_EMAILS = []


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    # delete created test enterprises + their users
    for eid in TEST_ENT_IDS:
        mdb.users.delete_many({"company_id": eid})
        mdb.enterprises.delete_one({"id": eid})
        mdb.projects.delete_many({"company_id": eid})
        mdb.suppliers.delete_many({"company_id": eid})
    for em in TEST_EMAILS:
        mdb.users.delete_one({"email": em})


# ================================================================
# 1. Migration + regression
# ================================================================
def test_super_admin_login_and_me():
    t = login(*SUPER)
    me = requests.get(f"{API}/auth/me", headers=hdr(t)).json()
    assert me["platform_role"] == "super_admin"
    assert me["company_id"] == "civio"
    ent = me["enterprise"]
    assert ent["status"] == "active"
    assert ent["business_type"] == "commercial"
    assert "procurement" in ent["modules"]


def test_demo_users_login_and_see_demo_project():
    for em, pw in (PM, ENG, CLIENT):
        t = login(em, pw)
        projs = requests.get(f"{API}/projects", headers=hdr(t))
        assert projs.status_code == 200
        ids = [p["id"] for p in projs.json()]
        assert "proj-demo-1" in ids, f"{em} missing proj-demo-1"


# ================================================================
# 2. Enterprise registration
# ================================================================
def _reg_payload(bt="commercial"):
    uniq = uuid.uuid4().hex[:8]
    email = f"test_ent_{uniq}@example.com"
    TEST_EMAILS.append(email)
    return {
        "company_name": f"TEST Co {uniq}", "business_type": bt, "city": "Pune",
        "name": f"Test Owner {uniq}", "email": email, "phone": "+919000000000",
        "password": "TestPass@123",
    }


def test_register_enterprise_invalid_business_type_400():
    p = _reg_payload()
    p["business_type"] = "industrial"
    r = requests.post(f"{API}/auth/register-enterprise", json=p)
    assert r.status_code == 400


def test_register_enterprise_duplicate_email_400():
    p = _reg_payload()
    r1 = requests.post(f"{API}/auth/register-enterprise", json=p)
    assert r1.status_code == 200
    ent = mdb.enterprises.find_one({"owner_email": p["email"]})
    assert ent is not None
    TEST_ENT_IDS.append(ent["id"])
    # duplicate
    r2 = requests.post(f"{API}/auth/register-enterprise", json=p)
    assert r2.status_code == 400


def _create_enterprise(bt="commercial"):
    p = _reg_payload(bt)
    r = requests.post(f"{API}/auth/register-enterprise", json=p)
    assert r.status_code == 200
    # bypass OTP
    mdb.users.update_one({"email": p["email"]}, {"$set": {"email_verified": True}})
    ent = mdb.enterprises.find_one({"owner_email": p["email"]})
    TEST_ENT_IDS.append(ent["id"])
    return p, ent


# ================================================================
# 3. Pending tenant blocked
# ================================================================
def test_pending_tenant_blocked_from_tenant_apis():
    p, ent = _create_enterprise()
    t = login(p["email"], p["password"])
    # /auth/me works
    me = requests.get(f"{API}/auth/me", headers=hdr(t))
    assert me.status_code == 200
    # tenant APIs 403
    for path in ("/projects", "/users", "/dashboard/summary", "/enterprise/usage"):
        r = requests.get(f"{API}{path}", headers=hdr(t))
        assert r.status_code == 403, f"{path} expected 403 got {r.status_code}"
        detail = r.json().get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "enterprise_inactive"


# ================================================================
# 4. Super admin APIs
# ================================================================
def test_superadmin_non_super_forbidden():
    t = login(*PM)
    for path in ("/superadmin/overview", "/superadmin/enterprises", "/superadmin/plans", "/superadmin/audit"):
        r = requests.get(f"{API}{path}", headers=hdr(t))
        assert r.status_code == 403, f"PM should not access {path}: {r.status_code}"


def test_superadmin_overview_and_plans():
    t = login(*SUPER)
    ov = requests.get(f"{API}/superadmin/overview", headers=hdr(t))
    assert ov.status_code == 200
    j = ov.json()
    assert "enterprises" in j and "by_status" in j and "mrr" in j
    plans = requests.get(f"{API}/superadmin/plans", headers=hdr(t))
    assert plans.status_code == 200
    assert any(p["id"] == "free" for p in plans.json())


def test_superadmin_cannot_deactivate_civio():
    t = login(*SUPER)
    r = requests.post(f"{API}/superadmin/enterprises/civio/status",
                      json={"status": "suspended", "reason": "x"}, headers=hdr(t))
    assert r.status_code == 400


def test_superadmin_reject_requires_reason():
    p, ent = _create_enterprise()
    t = login(*SUPER)
    r = requests.post(f"{API}/superadmin/enterprises/{ent['id']}/status",
                      json={"status": "rejected", "reason": ""}, headers=hdr(t))
    assert r.status_code == 400


def test_full_approve_suspend_reactivate_cycle():
    p, ent = _create_enterprise()
    sa = login(*SUPER)
    # pending -> active
    r = requests.post(f"{API}/superadmin/enterprises/{ent['id']}/status",
                      json={"status": "active"}, headers=hdr(sa))
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    # owner can now access
    t = login(p["email"], p["password"])
    projs = requests.get(f"{API}/projects", headers=hdr(t))
    assert projs.status_code == 200
    # suspend
    r = requests.post(f"{API}/superadmin/enterprises/{ent['id']}/status",
                      json={"status": "suspended", "reason": "testing"}, headers=hdr(sa))
    assert r.status_code == 200
    # owner blocked
    me = requests.get(f"{API}/auth/me", headers=hdr(t)).json()
    assert me["enterprise"]["status"] == "suspended"
    assert me["enterprise"]["status_reason"] == "testing"
    r2 = requests.get(f"{API}/projects", headers=hdr(t))
    assert r2.status_code == 403
    # reactivate
    r = requests.post(f"{API}/superadmin/enterprises/{ent['id']}/status",
                      json={"status": "active"}, headers=hdr(sa))
    assert r.status_code == 200
    r3 = requests.get(f"{API}/projects", headers=hdr(t))
    assert r3.status_code == 200


def test_superadmin_update_plan_and_audit():
    sa = login(*SUPER)
    plans = requests.get(f"{API}/superadmin/plans", headers=hdr(sa)).json()
    starter = next(p for p in plans if p["id"] == "starter")
    body = {"name": starter["name"], "description": starter.get("description", ""),
            "price_monthly": starter["price_monthly"], "max_users": starter["max_users"],
            "max_projects": starter["max_projects"], "max_storage_mb": starter["max_storage_mb"]}
    r = requests.put(f"{API}/superadmin/plans/starter", json=body, headers=hdr(sa))
    assert r.status_code == 200
    audit = requests.get(f"{API}/superadmin/audit", headers=hdr(sa))
    assert audit.status_code == 200
    assert isinstance(audit.json(), list)


# ================================================================
# 5. Tenant isolation
# ================================================================
def test_tenant_isolation_between_enterprises():
    p, ent = _create_enterprise()
    sa = login(*SUPER)
    requests.post(f"{API}/superadmin/enterprises/{ent['id']}/status",
                  json={"status": "active"}, headers=hdr(sa))
    t = login(p["email"], p["password"])
    # B sees no civio projects/users
    projs = requests.get(f"{API}/projects", headers=hdr(t)).json()
    assert projs == []
    users = requests.get(f"{API}/users", headers=hdr(t)).json()
    for u in users:
        assert u["company_id"] == ent["id"]
    # 404 on civio project
    r = requests.get(f"{API}/projects/proj-demo-1", headers=hdr(t))
    assert r.status_code == 404
    # creating project with civio client_id -> 400
    civio_client = mdb.users.find_one({"email": CLIENT[0]})
    r = requests.post(f"{API}/projects", json={
        "name": "TEST X", "code": f"TST-{uuid.uuid4().hex[:6]}", "client_id": civio_client["id"],
    }, headers=hdr(t))
    assert r.status_code == 400


# ================================================================
# 6. Plan limits
# ================================================================
def test_plan_limits_projects_and_users():
    p, ent = _create_enterprise()
    sa = login(*SUPER)
    requests.post(f"{API}/superadmin/enterprises/{ent['id']}/status",
                  json={"status": "active"}, headers=hdr(sa))
    # cap projects=1, users=2 (owner already counts)
    r = requests.put(f"{API}/superadmin/enterprises/{ent['id']}/subscription",
                     json={"plan_id": "free", "max_users": 2, "max_projects": 1,
                           "max_storage_mb": 500}, headers=hdr(sa))
    assert r.status_code == 200
    t = login(p["email"], p["password"])
    # 1st project ok
    r1 = requests.post(f"{API}/projects", json={
        "name": "TEST P1", "code": f"TP1-{uuid.uuid4().hex[:6]}"}, headers=hdr(t))
    assert r1.status_code == 200
    # 2nd blocked
    r2 = requests.post(f"{API}/projects", json={
        "name": "TEST P2", "code": f"TP2-{uuid.uuid4().hex[:6]}"}, headers=hdr(t))
    assert r2.status_code == 403
    assert "limit" in r2.json()["detail"].lower()
    # add 1 user ok
    uniq = uuid.uuid4().hex[:6]
    email1 = f"test_u1_{uniq}@example.com"
    TEST_EMAILS.append(email1)
    r3 = requests.post(f"{API}/users", json={
        "email": email1, "password": "Pass@1234", "name": "T U1",
        "role": "site_engineer", "phone": "+919000000001"}, headers=hdr(t))
    assert r3.status_code == 200
    # 3rd blocked (owner + 1 = 2)
    email2 = f"test_u2_{uniq}@example.com"
    TEST_EMAILS.append(email2)
    r4 = requests.post(f"{API}/users", json={
        "email": email2, "password": "Pass@1234", "name": "T U2",
        "role": "site_engineer", "phone": "+919000000002"}, headers=hdr(t))
    assert r4.status_code == 403


# ================================================================
# 7. Business-type modules
# ================================================================
def test_residential_blocks_procurement():
    p, ent = _create_enterprise(bt="residential")
    sa = login(*SUPER)
    requests.post(f"{API}/superadmin/enterprises/{ent['id']}/status",
                  json={"status": "active"}, headers=hdr(sa))
    t = login(p["email"], p["password"])
    me = requests.get(f"{API}/auth/me", headers=hdr(t)).json()
    assert "procurement" not in me["enterprise"]["modules"]
    # Create project
    r = requests.post(f"{API}/projects", json={
        "name": "TEST RES", "code": f"TR-{uuid.uuid4().hex[:6]}"}, headers=hdr(t))
    assert r.status_code == 200
    pid = r.json()["id"]
    # supplier blocked
    r = requests.post(f"{API}/suppliers", json={"name": "X"}, headers=hdr(t))
    assert r.status_code == 403
    # material-request blocked
    r = requests.post(f"{API}/projects/{pid}/material-requests",
                      json={"item": "cement", "quantity": 10}, headers=hdr(t))
    assert r.status_code == 403


def test_commercial_civio_still_has_procurement():
    t = login(*SUPER)
    r = requests.get(f"{API}/suppliers", headers=hdr(t))
    assert r.status_code == 200


# ================================================================
# 8. Google sign-in with invalid session_id
# ================================================================
def test_google_session_invalid():
    r = requests.post(f"{API}/auth/google/session", json={"session_id": "invalid-nonsense-123"})
    assert r.status_code == 401
