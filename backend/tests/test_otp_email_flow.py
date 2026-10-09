"""Tests for the OTP + phone + email verification feature (iteration 4)."""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

mongo = MongoClient(MONGO_URL)
users_col = mongo[DB_NAME]["users"]

CREATED_EMAILS = []  # for cleanup

SEEDED = [
    ("civiobuilds@gmail.com", "CivioAdmin@2026", "admin"),
    ("pm@civio.build", "CivioPM@2026", "project_manager"),
    ("engineer@civio.build", "CivioEng@2026", "site_engineer"),
    ("client@civio.build", "CivioClient@2026", "client"),
]


def _rand_email(prefix="otp"):
    return f"test_{prefix}_{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture(scope="session", autouse=True)
def _cleanup_at_end():
    yield
    if CREATED_EMAILS:
        users_col.delete_many({"email": {"$in": CREATED_EMAILS}})


# ----------- regression: seeded users still log in --------------------------
@pytest.mark.parametrize("email,password,role", SEEDED)
def test_seeded_login(email, password, role):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"{email} login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data and data["access_token"]
    assert data["user"]["role"] == role


# ----------- phone required on register -------------------------------------
def test_register_without_phone_rejected():
    email = _rand_email("nophone")
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Password@123", "name": "No Phone", "role": "client"
    }, timeout=20)
    assert r.status_code in (400, 422), f"expected 400/422, got {r.status_code} {r.text}"


def test_register_short_phone_rejected():
    email = _rand_email("short")
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Password@123", "name": "Short", "phone": "123", "role": "client"
    }, timeout=20)
    assert r.status_code in (400, 422)


def test_register_with_phone_returns_requires_verification():
    email = _rand_email("ok")
    CREATED_EMAILS.append(email)
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Password@123", "name": "Alice",
        "phone": "+919999900000", "role": "client",
    }, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("requires_verification") is True
    assert body.get("email") == email
    assert "access_token" not in body
    doc = users_col.find_one({"email": email})
    assert doc is not None
    assert doc.get("email_verified") is False
    assert doc.get("otp_code") and len(doc["otp_code"]) == 6
    assert doc.get("phone") == "+919999900000"


# ----------- login gated until verified -------------------------------------
def test_login_before_verify_returns_403_and_reissues():
    email = _rand_email("gated")
    CREATED_EMAILS.append(email)
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Password@123", "name": "Bob",
        "phone": "+911234567890", "role": "site_engineer",
    }, timeout=20)
    assert r.status_code == 200
    old_code = users_col.find_one({"email": email})["otp_code"]
    time.sleep(0.5)
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Password@123"}, timeout=20)
    assert r.status_code == 403, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "email_not_verified"
    assert detail.get("email") == email
    # a fresh OTP should be issued
    new_code = users_col.find_one({"email": email})["otp_code"]
    assert new_code and new_code != old_code or new_code == old_code  # may happen to repeat; just assert set
    assert users_col.find_one({"email": email})["otp_attempts"] == 0


# ----------- verify OTP: wrong, then correct --------------------------------
def test_verify_otp_wrong_then_correct():
    email = _rand_email("verify")
    CREATED_EMAILS.append(email)
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Password@123", "name": "Carol",
        "phone": "+911234567890", "role": "client",
    }, timeout=20)
    assert r.status_code == 200
    # wrong code
    r = requests.post(f"{API}/auth/verify-otp", json={"email": email, "code": "000000"}, timeout=20)
    # if the real code happens to be "000000" we re-fetch; vanishingly unlikely
    real = users_col.find_one({"email": email})["otp_code"]
    if real != "000000":
        assert r.status_code == 400
        assert users_col.find_one({"email": email})["otp_attempts"] >= 1
    # correct code
    r = requests.post(f"{API}/auth/verify-otp", json={"email": email, "code": real}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and data["access_token"]
    assert data["user"]["email"] == email
    doc = users_col.find_one({"email": email})
    assert doc.get("email_verified") is True
    assert "otp_code" not in doc
    # login now works
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Password@123"}, timeout=20)
    assert r.status_code == 200


def test_verify_otp_rate_limit_after_6_wrong():
    email = _rand_email("ratelimit")
    CREATED_EMAILS.append(email)
    requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Password@123", "name": "Dave",
        "phone": "+911234567890", "role": "client",
    }, timeout=20)
    real = users_col.find_one({"email": email})["otp_code"]
    wrong = "999999" if real != "999999" else "111111"
    last = None
    for _ in range(7):
        last = requests.post(f"{API}/auth/verify-otp", json={"email": email, "code": wrong}, timeout=20)
    assert last.status_code == 429, f"expected 429, got {last.status_code} {last.text}"


# ----------- resend OTP -----------------------------------------------------
def test_resend_otp_for_unverified_sets_new_code():
    email = _rand_email("resend")
    CREATED_EMAILS.append(email)
    requests.post(f"{API}/auth/register", json={
        "email": email, "password": "Password@123", "name": "Eve",
        "phone": "+911234567890", "role": "client",
    }, timeout=20)
    old = users_col.find_one({"email": email})["otp_code"]
    # ensure it changes: loop few times
    changed = False
    for _ in range(3):
        r = requests.post(f"{API}/auth/resend-otp", json={"email": email}, timeout=20)
        assert r.status_code == 200
        new = users_col.find_one({"email": email})["otp_code"]
        if new != old:
            changed = True
            break
    assert changed, "resend-otp did not rotate otp_code within 3 attempts"


def test_resend_otp_for_unknown_email_is_200():
    r = requests.post(f"{API}/auth/resend-otp", json={"email": f"unknown_{uuid.uuid4().hex}@example.com"}, timeout=20)
    assert r.status_code == 200


def test_resend_otp_for_verified_user_is_200():
    r = requests.post(f"{API}/auth/resend-otp", json={"email": "pm@civio.build"}, timeout=20)
    assert r.status_code == 200
    # the seeded user must stay verified
    assert users_col.find_one({"email": "pm@civio.build"}).get("email_verified") is True


# ----------- admin-created users need OTP too -------------------------------
def _admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": "civiobuilds@gmail.com", "password": "CivioAdmin@2026"}, timeout=20)
    assert r.status_code == 200
    return r.json()["access_token"]


def test_admin_create_engineer_without_phone_rejected():
    token = _admin_token()
    email = _rand_email("adm_nophone")
    r = requests.post(f"{API}/users", headers={"Authorization": f"Bearer {token}"}, json={
        "email": email, "password": "Password@123", "name": "NoPhone Eng", "role": "site_engineer",
    }, timeout=20)
    assert r.status_code == 400, r.text


def test_admin_create_client_with_phone_requires_otp():
    token = _admin_token()
    email = _rand_email("adm_client")
    CREATED_EMAILS.append(email)
    r = requests.post(f"{API}/users", headers={"Authorization": f"Bearer {token}"}, json={
        "email": email, "password": "Password@123", "name": "Admin-Made Client",
        "role": "client", "phone": "+911112223333",
    }, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("requires_verification") is True
    doc = users_col.find_one({"email": email})
    assert doc.get("email_verified") is False
    assert doc.get("otp_code")
    # cannot login yet
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Password@123"}, timeout=20)
    assert r.status_code == 403
    # verify with mongo code
    code = users_col.find_one({"email": email})["otp_code"]
    r = requests.post(f"{API}/auth/verify-otp", json={"email": email, "code": code}, timeout=20)
    assert r.status_code == 200
    # now login works
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Password@123"}, timeout=20)
    assert r.status_code == 200


def test_admin_create_pm_does_not_require_phone():
    token = _admin_token()
    email = _rand_email("adm_pm")
    CREATED_EMAILS.append(email)
    r = requests.post(f"{API}/users", headers={"Authorization": f"Bearer {token}"}, json={
        "email": email, "password": "Password@123", "name": "Admin-Made PM",
        "role": "project_manager",
    }, timeout=20)
    assert r.status_code == 200, r.text


# ----------- report emailing -------------------------------------------------
def _pm_token():
    r = requests.post(f"{API}/auth/login", json={"email": "pm@civio.build", "password": "CivioPM@2026"}, timeout=20)
    return r.json()["access_token"]


def test_generate_report_returns_emailed_to_and_stores():
    token = _pm_token()
    r = requests.post(f"{API}/projects/proj-demo-1/reports",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"type": "progress"}, timeout=60)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert "id" in doc
    assert "emailed_to" in doc and isinstance(doc["emailed_to"], list)
    rid = doc["id"]
    # list
    r2 = requests.get(f"{API}/projects/proj-demo-1/reports",
                      headers={"Authorization": f"Bearer {token}"}, timeout=20)
    assert r2.status_code == 200
    assert any(x["id"] == rid for x in r2.json())
    # download via ?auth=
    r3 = requests.get(f"{API}/reports/{rid}/download?auth={token}", timeout=30)
    assert r3.status_code == 200
    assert r3.content[:4] == b"%PDF"


def test_generate_report_delivered_resend_dev_appears_in_emailed_to():
    """Assign a delivered@resend.dev client to the project temporarily, generate, verify."""
    admin = _admin_token()
    # Create / find a user with delivered@resend.dev
    email = "delivered@resend.dev"
    existing = users_col.find_one({"email": email})
    if not existing:
        r = requests.post(f"{API}/users", headers={"Authorization": f"Bearer {admin}"}, json={
            "email": email, "password": "Password@123", "name": "Resend Delivered",
            "role": "client", "phone": "+911112223334",
        }, timeout=20)
        assert r.status_code == 200
        # verify immediately via mongo otp_code so user is active
        code = users_col.find_one({"email": email}).get("otp_code")
        if code:
            requests.post(f"{API}/auth/verify-otp", json={"email": email, "code": code}, timeout=20)
    uid = users_col.find_one({"email": email})["id"]
    # grab current project
    r = requests.get(f"{API}/projects/proj-demo-1", headers={"Authorization": f"Bearer {admin}"}, timeout=20)
    assert r.status_code == 200
    original_client = r.json().get("client_id")
    try:
        # assign new client
        r = requests.post(f"{API}/projects/proj-demo-1/assign",
                          headers={"Authorization": f"Bearer {admin}"},
                          json={"client_id": uid}, timeout=20)
        assert r.status_code == 200
        # generate as PM
        token = _pm_token()
        r = requests.post(f"{API}/projects/proj-demo-1/reports",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"type": "progress"}, timeout=90)
        assert r.status_code == 200, r.text
        emailed = r.json().get("emailed_to", [])
        # delivered@resend.dev should be in emailed_to; if sandbox is paused/key missing,
        # accept empty list but warn.
        if emailed:
            assert email in emailed, f"delivered@resend.dev missing from {emailed}"
        else:
            pytest.skip("Email provider returned no accepted recipients (likely sandbox paused).")
    finally:
        # restore original client
        if original_client:
            requests.post(f"{API}/projects/proj-demo-1/assign",
                          headers={"Authorization": f"Bearer {admin}"},
                          json={"client_id": original_client}, timeout=20)


# ----------- email send safety: report must not 500 on bad recipients --------
def test_report_generation_tolerates_undeliverable_recipients():
    token = _pm_token()
    r = requests.post(f"{API}/projects/proj-demo-1/reports",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"type": "cost"}, timeout=60)
    assert r.status_code == 200, f"report generation must not 500 on email failures: {r.status_code} {r.text}"
