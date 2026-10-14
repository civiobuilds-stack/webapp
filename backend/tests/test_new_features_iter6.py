"""Iteration-6 end-to-end tests for CIVIO new features:
- Team invites (links, roles, revoke, accept, limits)
- Company-branded reports (enterprise settings + logo + PDF branding)
- Homeowner (residential-client) dashboard data flow
- Public landing page is served implicitly via frontend (not tested here)
"""
import os
import io
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE_URL + "/api"
ORIGIN_HDR = {"Origin": BASE_URL}  # must be https:// — invites require it

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]

ADMIN = ("civiobuilds@gmail.com", "CivioAdmin@2026")
PM = ("pm@civio.build", "CivioPM@2026")
CLIENT = ("client@civio.build", "CivioClient@2026")

# ---- helpers ------------------------------------------------------------

def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, (email, r.status_code, r.text)
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _tag():
    return uuid.uuid4().hex[:8]


# Track created artifacts for teardown
_CREATED_ENTERPRISES = set()
_CREATED_INVITES = set()
_CREATED_USERS = set()
_CREATED_PROJECTS = set()


@pytest.fixture(scope="module")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def pm_token():
    return _login(*PM)


# =========================================================================
# INVITES API
# =========================================================================
class TestInvites:
    def test_pm_cannot_invite_project_manager(self, pm_token):
        email = f"TEST_pm_{_tag()}@example.com"
        r = requests.post(f"{API}/invites",
                          headers={**_auth(pm_token), **ORIGIN_HDR},
                          json={"name": "X", "email": email, "role": "project_manager"})
        assert r.status_code == 403, r.text

    def test_create_invite_as_admin(self, admin_token):
        email = f"TEST_inv_{_tag()}@example.com"
        r = requests.post(f"{API}/invites",
                          headers={**_auth(admin_token), **ORIGIN_HDR},
                          json={"name": "Invitee One", "email": email, "role": "site_engineer"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == email.lower()
        assert d["role"] == "site_engineer"
        assert d["status"] == "pending"
        assert d["invite_link"].startswith("https://") and "/invite/" in d["invite_link"]
        assert "emailed" in d
        _CREATED_INVITES.add(d["id"])
        return d

    def test_duplicate_email_returns_400(self, admin_token):
        r = requests.post(f"{API}/invites",
                          headers={**_auth(admin_token), **ORIGIN_HDR},
                          json={"name": "Dup", "email": ADMIN[0], "role": "site_engineer"})
        assert r.status_code == 400

    def test_list_invites_tenant_scoped(self, admin_token):
        r = requests.get(f"{API}/invites", headers=_auth(admin_token))
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # all items are for civio (we can't check company_id from pub_invite, but presence of recent one)
        if items:
            assert "status" in items[0] and "email" in items[0]

    def test_revoke_invite(self, admin_token):
        email = f"TEST_rev_{_tag()}@example.com"
        r = requests.post(f"{API}/invites", headers={**_auth(admin_token), **ORIGIN_HDR},
                          json={"name": "ToRevoke", "email": email, "role": "client"})
        iid = r.json()["id"]
        _CREATED_INVITES.add(iid)
        token = r.json()["invite_link"].rsplit("/", 1)[-1]
        # Public info works pre-revoke
        assert requests.get(f"{API}/invites/token/{token}").status_code == 200
        # Revoke
        r = requests.delete(f"{API}/invites/{iid}", headers=_auth(admin_token))
        assert r.status_code == 200
        # Public lookup now 404
        assert requests.get(f"{API}/invites/token/{token}").status_code == 404

    def test_accept_invite_creates_user_and_token_not_reusable(self, admin_token):
        email = f"TEST_acc_{_tag()}@example.com"
        r = requests.post(f"{API}/invites", headers={**_auth(admin_token), **ORIGIN_HDR},
                          json={"name": "Alice Accept", "email": email, "role": "site_engineer"})
        assert r.status_code == 200, r.text
        inv = r.json()
        _CREATED_INVITES.add(inv["id"])
        link = inv["invite_link"]
        token = link.rsplit("/", 1)[-1]
        # GET public
        info = requests.get(f"{API}/invites/token/{token}").json()
        assert info["email"] == email.lower() and info["role"] == "site_engineer"
        assert info["company"]  # display_name set
        # ACCEPT
        r = requests.post(f"{API}/invites/token/{token}/accept",
                          json={"password": "Str0ngPass!", "phone": "+911234567890", "name": "Alice A."})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["access_token"] and d["user"]["email"] == email.lower() and d["user"]["role"] == "site_engineer"
        assert d["user"]["company_id"] == "civio"
        _CREATED_USERS.add(d["user"]["id"])
        # Cannot reuse token
        r2 = requests.post(f"{API}/invites/token/{token}/accept",
                           json={"password": "x" * 8, "phone": "+911234567890"})
        assert r2.status_code == 404
        # Login with new credentials works
        r3 = requests.post(f"{API}/auth/login", json={"email": email, "password": "Str0ngPass!"})
        assert r3.status_code == 200


# =========================================================================
# ENTERPRISE SETTINGS + LOGO + BRANDED REPORTS
# =========================================================================
class TestBrandingAndReports:
    def test_get_settings_pm_can_read(self, pm_token):
        r = requests.get(f"{API}/enterprise/settings", headers=_auth(pm_token))
        assert r.status_code == 200
        d = r.json()
        assert d["display_name"]
        assert "has_logo" in d

    def test_pm_cannot_update_settings(self, pm_token):
        r = requests.put(f"{API}/enterprise/settings", headers=_auth(pm_token),
                         json={"display_name": "Hack Co"})
        assert r.status_code == 403

    def test_admin_update_persists(self, admin_token):
        # Save current then restore
        cur = requests.get(f"{API}/enterprise/settings", headers=_auth(admin_token)).json()
        payload = {
            "display_name": cur.get("display_name") or "CIVIO PMC",
            "tagline": "Test tagline " + _tag(),
            "address": "Test addr",
            "contact_email": "civiobuilds@gmail.com",
            "contact_phone": "+919108098446",
            "website": "https://civio.build",
        }
        r = requests.put(f"{API}/enterprise/settings", headers=_auth(admin_token), json=payload)
        assert r.status_code == 200
        got = requests.get(f"{API}/enterprise/settings", headers=_auth(admin_token)).json()
        assert got["tagline"] == payload["tagline"]
        assert got["contact_phone"] == payload["contact_phone"]

    def test_logo_rejects_non_image(self, admin_token):
        files = {"file": ("x.txt", b"hello", "text/plain")}
        r = requests.post(f"{API}/enterprise/logo", headers=_auth(admin_token), files=files)
        assert r.status_code == 400

    def test_logo_rejects_oversize(self, admin_token):
        files = {"file": ("big.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024 + 10), "image/png")}
        r = requests.post(f"{API}/enterprise/logo", headers=_auth(admin_token), files=files)
        assert r.status_code == 400

    def test_generate_report_contains_branding(self, admin_token):
        # Set a recognizable display_name for the pdf header
        requests.put(f"{API}/enterprise/settings", headers=_auth(admin_token),
                     json={"display_name": "CIVIO PMC", "tagline": "Build Smart.",
                           "contact_email": "civiobuilds@gmail.com", "contact_phone": "+919108098446",
                           "address": "Mumbai", "website": "https://civio.build"})
        t0 = time.time()
        r = requests.post(f"{API}/projects/proj-demo-1/reports",
                          headers=_auth(admin_token), json={"type": "progress"})
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        assert elapsed < 15, f"report generation too slow: {elapsed:.1f}s"
        rec = r.json()
        rid = rec["id"]
        # Download PDF bytes
        token = admin_token
        dl = requests.get(f"{API}/reports/{rid}/download", params={"auth": token})
        assert dl.status_code == 200
        pdf = dl.content
        assert pdf[:4] == b"%PDF"
        # Extract text via pypdf since ReportLab streams are compressed.
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        assert "CIVIO PMC" in text, f"display_name not in PDF text; got: {text[:400]}"
        assert "Powered by CIVIO" in text, f"footer attribution missing: {text[:400]}"
        assert "Confidential" in text


# =========================================================================
# HOMEOWNER DASHBOARD FLOW
# =========================================================================
class TestHomeownerFlow:
    """Create a residential enterprise -> approve -> seed client + engineer +
    project with activity requiring client approval -> engineer submits
    progress -> admin approves -> dashboard surfaces pending_client_decision."""

    @classmethod
    def _mk_ent(cls, admin_token):
        tag = _tag()
        payload = {
            "company_name": f"TEST Res {tag}",
            "business_type": "residential",
            "city": "Mumbai",
            "name": "TestOwner",
            "email": f"TEST_resowner_{tag}@example.com",
            "phone": "+911234567890",
            "password": "Owner@123",
        }
        r = requests.post(f"{API}/auth/register-enterprise", json=payload)
        assert r.status_code == 200, r.text
        # Verify email in DB
        db.users.update_one({"email": payload["email"].lower()}, {"$set": {"email_verified": True}})
        # Find enterprise id
        u = db.users.find_one({"email": payload["email"].lower()})
        eid = u["company_id"]
        _CREATED_ENTERPRISES.add(eid)
        _CREATED_USERS.add(u["id"])
        # Super admin approves
        sa_token = _login(*ADMIN)
        r = requests.post(f"{API}/superadmin/enterprises/{eid}/status",
                          headers=_auth(sa_token), json={"status": "active", "reason": ""})
        assert r.status_code == 200, r.text
        return payload, eid

    def test_homeowner_flow(self, admin_token):
        owner, eid = self._mk_ent(admin_token)
        owner_token = _login(owner["email"], owner["password"])
        # Create engineer
        eng_email = f"TEST_eng_{_tag()}@example.com"
        r = requests.post(f"{API}/users", headers={**_auth(owner_token), **ORIGIN_HDR},
                          json={"name": "Eng R", "email": eng_email, "role": "site_engineer",
                                "password": "Eng@12345", "phone": "+911234567890"})
        assert r.status_code == 200, r.text
        eng_id = r.json()["id"]
        _CREATED_USERS.add(eng_id)
        db.users.update_one({"id": eng_id}, {"$set": {"email_verified": True}})
        # Create client (via invite accept — cleanest; but owner can POST /users)
        cli_email = f"TEST_cli_{_tag()}@example.com"
        r = requests.post(f"{API}/users", headers={**_auth(owner_token), **ORIGIN_HDR},
                          json={"name": "Home Owner", "email": cli_email, "role": "client",
                                "password": "Cli@12345", "phone": "+911234567890"})
        assert r.status_code == 200, r.text
        cli_id = r.json()["id"]
        _CREATED_USERS.add(cli_id)
        db.users.update_one({"id": cli_id}, {"$set": {"email_verified": True}})
        # Create project
        r = requests.post(f"{API}/projects", headers=_auth(owner_token),
                          json={"name": "TEST Res Villa", "code": f"TRV-{_tag()}",
                                "client_id": cli_id, "engineer_ids": [eng_id],
                                "start_date": "2026-01-01", "target_date": "2026-12-31",
                                "budget": 1000000})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        _CREATED_PROJECTS.add(pid)
        # Create milestone
        r = requests.post(f"{API}/projects/{pid}/milestones", headers=_auth(owner_token),
                         json={"name": "Foundation", "target_date": "2026-03-01", "order": 1})
        assert r.status_code == 200, r.text
        mid = r.json()["id"]
        # Create activity requiring client approval
        r = requests.post(f"{API}/projects/{pid}/activities", headers=_auth(owner_token),
                          json={"name": "Pour footings", "milestone_id": mid,
                                "requires_client_approval": True})
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        # Engineer logs in and submits progress update
        eng_token = _login(eng_email, "Eng@12345")
        r = requests.post(f"{API}/projects/{pid}/progress-updates", headers=_auth(eng_token),
                          json={"activity_id": aid,
                                "percent_complete": 50, "notes": "Half done",
                                "requires_client_approval": True})
        assert r.status_code == 200, r.text
        pu_id = r.json()["id"]
        # Admin reviews -> approved -> pending_client_decision
        r = requests.post(f"{API}/progress-updates/{pu_id}/review", headers=_auth(owner_token),
                          json={"action": "approve", "comment": "LGTM"})
        assert r.status_code == 200, r.text
        pu_after = r.json()
        assert pu_after["status"] == "pending_client_decision", pu_after
        # Client logs in — the homeowner dashboard reads project list, pending reviews etc.
        cli_token = _login(cli_email, "Cli@12345")
        r = requests.get(f"{API}/auth/me", headers=_auth(cli_token))
        me = r.json()
        assert me["role"] == "client"
        assert me["enterprise"]["business_type"] == "residential"
        # Project visible
        r = requests.get(f"{API}/projects", headers=_auth(cli_token))
        assert r.status_code == 200
        assert any(p["id"] == pid for p in r.json()), r.json()
        # Progress updates with pending status
        r = requests.get(f"{API}/projects/{pid}/progress-updates", headers=_auth(cli_token))
        assert r.status_code == 200
        pending = [u for u in r.json() if u["status"] == "pending_client_decision"]
        assert pending, "homeowner needs at least one pending decision"
        # Client decision — approve
        r = requests.post(f"{API}/progress-updates/{pu_id}/client-decision",
                          headers=_auth(cli_token),
                          json={"action": "approve", "comment": "Looks great"})
        assert r.status_code == 200, r.text
        # Now pending list drained
        r = requests.get(f"{API}/projects/{pid}/progress-updates", headers=_auth(cli_token))
        assert not any(u["status"] == "pending_client_decision" for u in r.json())


# =========================================================================
# TEARDOWN
# =========================================================================
def teardown_module(module):
    # Delete our created artifacts
    for pid in list(_CREATED_PROJECTS):
        db.projects.delete_one({"id": pid})
        db.milestones.delete_many({"project_id": pid})
        db.activities.delete_many({"project_id": pid})
        db.progress_updates.delete_many({"project_id": pid})
        db.audit_logs.delete_many({"project_id": pid})
        db.reports.delete_many({"project_id": pid})
    for uid in list(_CREATED_USERS):
        db.users.delete_one({"id": uid})
    db.users.delete_many({"email": {"$regex": "^TEST_"}})
    db.invites.delete_many({"email": {"$regex": "^TEST_"}})
    for eid in list(_CREATED_ENTERPRISES):
        db.enterprises.delete_one({"id": eid})
        db.users.delete_many({"company_id": eid})
        db.projects.delete_many({"company_id": eid})
    # Restore civio display_name/tagline to canonical values
    db.enterprises.update_one({"id": "civio"}, {"$set": {
        "display_name": "CIVIO PMC",
        "tagline": "",
        "address": "",
        "contact_email": "",
        "contact_phone": "",
        "website": "",
    }})
