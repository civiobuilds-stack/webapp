# Iteration 12: Commercial billing/vehicles/permissions + Residential quotations/drawings/design dashboard
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
P_COM = "proj-demo-1"
P_RES = "proj-res-1"
CREDS = {
    "owner": ("civiobuilds@gmail.com", "Civio@123456"),
    "pm": ("pm@civio.build", "CivioPM@2026"),
    "eng": ("engineer@civio.build", "CivioEng@2026"),
    "eng2": ("engineer2@civio.build", "CivioEng@2026"),
    "client": ("client@civio.build", "CivioClient@2026"),
    "accounts": ("accounts@civio.build", "CivioRole@2026"),
    "driver": ("driver@civio.build", "CivioRole@2026"),
    "arch": ("architect@civiohomes.build", "CivioRole@2026"),
    "struct": ("structural@civiohomes.build", "CivioRole@2026"),
    "rpm": ("pm@civiohomes.build", "CivioHome@2026"),
    "rowner": ("owner@civiohomes.build", "CivioHome@2026"),
    "rclient": ("client@civiohomes.build", "CivioHome@2026"),
}
_tok = {}
UID = uuid.uuid4().hex[:6].upper()
import random
TRIP_DATE = f"2027-{random.randint(1,12):02d}-{random.randint(1,28):02d}"


def tok(k):
    if k not in _tok:
        r = requests.post(f"{API}/auth/login", json={"email": CREDS[k][0], "password": CREDS[k][1]})
        assert r.status_code == 200, f"login {k}: {r.status_code} {r.text}"
        _tok[k] = r.json()["access_token"]
    return _tok[k]


def H(k):
    return {"Authorization": f"Bearer {tok(k)}"}


def bill_body(**kw):
    b = {"vendor_name": f"TEST_Vendor_{UID}", "bill_no": f"INV-{uuid.uuid4().hex[:6]}", "bill_date": "2026-01-10",
         "category": "Material", "description": "cement", "amount": 1000, "gst_amount": 180}
    b.update(kw)
    return b


# ---------------- Billing ----------------
class TestBilling:
    def test_full_flow(self):
        r = requests.post(f"{API}/projects/{P_COM}/bills", json=bill_body(), headers=H("accounts"))
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["status"] == "pending_pm" and b["total"] == 1180 and b["ref_no"].startswith("BILL-")
        bid = b["id"]
        # owner cannot approve while pending_pm
        r = requests.post(f"{API}/bills/{bid}/decision", json={"action": "approve"}, headers=H("owner"))
        assert r.status_code == 403
        # mark paid before approved -> 400
        r = requests.post(f"{API}/bills/{bid}/paid", json={"paid_on": "2026-01-11"}, headers=H("accounts"))
        assert r.status_code == 400
        r = requests.post(f"{API}/bills/{bid}/decision", json={"action": "approve"}, headers=H("pm"))
        assert r.status_code == 200 and r.json()["status"] == "pending_owner", r.text
        r = requests.post(f"{API}/bills/{bid}/decision", json={"action": "approve"}, headers=H("pm"))
        assert r.status_code == 403
        r = requests.post(f"{API}/bills/{bid}/decision", json={"action": "approve"}, headers=H("owner"))
        assert r.status_code == 200 and r.json()["status"] == "approved"
        r = requests.post(f"{API}/bills/{bid}/decision", json={"action": "approve"}, headers=H("owner"))
        assert r.status_code == 400
        r = requests.post(f"{API}/bills/{bid}/paid", json={"paid_on": "2026-01-12", "payment_ref": "UTR1"}, headers=H("accounts"))
        assert r.status_code == 200 and r.json()["status"] == "paid"
        lst = requests.get(f"{API}/projects/{P_COM}/bills", headers=H("accounts")).json()
        assert any(x["id"] == bid and x["status"] == "paid" for x in lst)

    def test_reject_and_resubmit(self):
        b = requests.post(f"{API}/projects/{P_COM}/bills", json=bill_body(), headers=H("accounts")).json()
        r = requests.post(f"{API}/bills/{b['id']}/decision", json={"action": "reject"}, headers=H("pm"))
        assert r.status_code == 400
        r = requests.post(f"{API}/bills/{b['id']}/decision", json={"action": "reject", "remarks": "wrong qty"}, headers=H("pm"))
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        r = requests.put(f"{API}/bills/{b['id']}", json=bill_body(bill_no=b["bill_no"], amount=900), headers=H("accounts"))
        assert r.status_code == 200 and r.json()["status"] == "pending_pm" and r.json()["total"] == 1080
        # resubmit non-rejected -> 400
        r = requests.put(f"{API}/bills/{b['id']}", json=bill_body(bill_no=b["bill_no"]), headers=H("accounts"))
        assert r.status_code == 400

    def test_duplicate_409(self):
        body = bill_body()
        assert requests.post(f"{API}/projects/{P_COM}/bills", json=body, headers=H("accounts")).status_code == 200
        r = requests.post(f"{API}/projects/{P_COM}/bills", json=body, headers=H("accounts"))
        assert r.status_code == 409

    def test_client_no_access(self):
        r = requests.get(f"{API}/projects/{P_COM}/bills", headers=H("client"))
        assert r.status_code == 403
        r = requests.post(f"{API}/projects/{P_COM}/bills", json=bill_body(), headers=H("client"))
        assert r.status_code == 403

    def test_bills_summary(self):
        for k in ("accounts", "owner"):
            r = requests.get(f"{API}/bills", headers=H(k))
            assert r.status_code == 200
            d = r.json()
            assert "bills" in d and {"pending", "approved", "paid", "count_pending_pm"} <= set(d["summary"])
        assert requests.get(f"{API}/bills", headers=H("eng")).status_code == 403

    def test_validation(self):
        r = requests.post(f"{API}/projects/{P_COM}/bills", json=bill_body(amount=0), headers=H("accounts"))
        assert r.status_code == 422


# ---------------- Vehicles ----------------
@pytest.mark.skip(reason='Obsolete after iter13 fleet redesign (accounts no longer manages vehicles; from/to_date schema). See test_iter13_subscription_fleet_access.py')
class TestVehicles:
    state = {}

    def test_add_vehicles_and_drivers(self):
        r = requests.post(f"{API}/vehicles", json={"reg_no": f"MH01{UID}", "model": "TEST Innova", "vehicle_type": "Car"}, headers=H("accounts"))
        assert r.status_code == 200, r.text
        self.state["v1"] = r.json()["id"]
        assert r.json()["reg_no"] == f"MH01{UID}"
        r = requests.post(f"{API}/vehicles", json={"reg_no": f"MH01{UID}", "model": "dup"}, headers=H("accounts"))
        assert r.status_code == 409
        r = requests.post(f"{API}/vehicles", json={"reg_no": f"MH02{UID}", "model": "TEST Bolero", "status": "maintenance"}, headers=H("accounts"))
        assert r.status_code == 200
        self.state["vm"] = r.json()["id"]
        r = requests.post(f"{API}/vehicles", json={"reg_no": f"MH03{UID}", "model": "x"}, headers=H("eng"))
        assert r.status_code == 403
        d = requests.get(f"{API}/drivers", headers=H("accounts"))
        assert d.status_code == 200 and any(x["email"] == "driver@civio.build" for x in d.json())
        self.state["driver"] = next(x["id"] for x in d.json() if x["email"] == "driver@civio.build")

    def _req(self, time="10:00"):
        r = requests.post(f"{API}/projects/{P_COM}/vehicle-requests", json={"purpose": "TEST site visit", "pickup": "Office", "drop": "Site",
                                                                           "trip_date": TRIP_DATE, "trip_time": time}, headers=H("eng"))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "requested"
        return r.json()["id"]

    def test_assign_clash_trip(self):
        t1 = self._req("10:30")
        t2 = self._req("10:30")
        # maintenance vehicle cannot be assigned
        r = requests.post(f"{API}/vehicle-requests/{t1}/assign", json={"vehicle_id": self.state["vm"], "driver_id": self.state["driver"]}, headers=H("accounts"))
        assert r.status_code == 400
        r = requests.post(f"{API}/vehicle-requests/{t1}/assign", json={"vehicle_id": self.state["v1"], "driver_id": self.state["driver"]}, headers=H("accounts"))
        assert r.status_code == 200 and r.json()["status"] == "assigned" and r.json()["driver"]["id"] == self.state["driver"]
        r = requests.post(f"{API}/vehicle-requests/{t2}/assign", json={"vehicle_id": self.state["v1"], "driver_id": self.state["driver"]}, headers=H("accounts"))
        assert r.status_code == 409
        # reject needs reason
        r = requests.post(f"{API}/vehicle-requests/{t2}/status", json={"action": "reject"}, headers=H("accounts"))
        assert r.status_code == 400
        r = requests.post(f"{API}/vehicle-requests/{t2}/status", json={"action": "reject", "remarks": "no vehicle"}, headers=H("accounts"))
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        # driver trips
        mt = requests.get(f"{API}/my-trips", headers=H("driver"))
        assert mt.status_code == 200 and any(x["id"] == t1 for x in mt.json())
        assert requests.get(f"{API}/my-trips", headers=H("eng")).status_code == 403
        # non-driver cannot start
        r = requests.post(f"{API}/vehicle-requests/{t1}/status", json={"action": "start"}, headers=H("accounts"))
        assert r.status_code == 403
        r = requests.post(f"{API}/vehicle-requests/{t1}/status", json={"action": "complete"}, headers=H("driver"))
        assert r.status_code == 400
        r = requests.post(f"{API}/vehicle-requests/{t1}/status", json={"action": "start"}, headers=H("driver"))
        assert r.status_code == 200 and r.json()["status"] == "in_progress"
        r = requests.post(f"{API}/vehicle-requests/{t1}/status", json={"action": "complete"}, headers=H("driver"))
        assert r.status_code == 200 and r.json()["status"] == "completed"

    def test_engineer_sees_own_requests(self):
        r = requests.get(f"{API}/projects/{P_COM}/vehicle-requests", headers=H("eng"))
        assert r.status_code == 200 and all(x["requested_by"] == "user-eng" for x in r.json())


# ---------------- Permissions ----------------
class TestPermissions:
    def test_member_billing_modules(self):
        perms = {"dpr": ["view", "create", "edit", "submit"], "attendance": ["view", "create"], "billing": [], "vehicles": ["view", "create"]}
        r = requests.put(f"{API}/projects/{P_COM}/members/user-eng2", json={"responsibility": "TEST", "permissions": perms}, headers=H("pm"))
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/projects/{P_COM}/bills", headers=H("eng2")).status_code == 403
        perms["billing"] = ["view"]
        r = requests.put(f"{API}/projects/{P_COM}/members/user-eng2", json={"permissions": perms}, headers=H("pm"))
        assert r.status_code == 200
        assert requests.get(f"{API}/projects/{P_COM}/bills", headers=H("eng2")).status_code == 200
        assert requests.post(f"{API}/projects/{P_COM}/bills", json=bill_body(), headers=H("eng2")).status_code == 403
        r = requests.put(f"{API}/projects/{P_COM}/members/user-eng2", json={"permissions": {"billing": ["fly"]}}, headers=H("pm"))
        assert r.status_code == 400
        # cleanup
        requests.delete(f"{API}/projects/{P_COM}/members/user-eng2", headers=H("pm"))


# ---------------- Role creation ----------------
class TestRoleCreation:
    def test_architect_in_commercial_400(self):
        r = requests.post(f"{API}/users", json={"name": "TEST Arch", "email": f"test_arch_{UID.lower()}@x.com", "password": "Passw0rd!23",
                                                "role": "architect"}, headers=H("owner"))
        assert r.status_code == 400, r.text

    def test_accounts_in_residential_400(self):
        r = requests.post(f"{API}/users", json={"name": "TEST Acc", "email": f"test_acc_{UID.lower()}@x.com", "password": "Passw0rd!23",
                                                "role": "accounts"}, headers=H("rowner"))
        assert r.status_code == 400, r.text


# ---------------- Quotations ----------------
def qbody(title="TEST Kitchen", rate=5000):
    return {"title": title, "items": [{"description": "Modular kitchen", "unit": "set", "qty": 2, "rate": rate}], "tax_pct": 18, "discount": 1000,
            "valid_until": "2026-12-31", "notes": "n", "terms": "t"}


class TestQuotations:
    def test_full_flow(self):
        r = requests.post(f"{API}/projects/{P_RES}/quotations", json=qbody(), headers=H("rpm"))
        assert r.status_code == 200, r.text
        q = r.json()
        assert q["status"] == "draft" and q["revisions"][0]["total"] == round(9000 * 1.18, 2)
        qid = q["id"]
        # client cannot see draft
        lst = requests.get(f"{API}/projects/{P_RES}/quotations", headers=H("rclient")).json()
        assert not any(x["id"] == qid for x in lst)
        assert requests.get(f"{API}/quotations/{qid}/pdf", params={"auth": tok("rclient")}).status_code == 404
        r = requests.put(f"{API}/quotations/{qid}", json=qbody(rate=6000), headers=H("rpm"))
        assert r.status_code == 200 and r.json()["revisions"][-1]["subtotal"] == 12000
        r = requests.post(f"{API}/quotations/{qid}/send", headers=H("rpm"))
        assert r.status_code == 200 and r.json()["status"] == "sent"
        assert requests.put(f"{API}/quotations/{qid}", json=qbody(), headers=H("rpm")).status_code == 400
        lst = requests.get(f"{API}/projects/{P_RES}/quotations", headers=H("rclient")).json()
        assert any(x["id"] == qid for x in lst)
        # request changes needs comment
        r = requests.post(f"{API}/quotations/{qid}/respond", json={"action": "request_changes"}, headers=H("rclient"))
        assert r.status_code == 400
        r = requests.post(f"{API}/quotations/{qid}/respond", json={"action": "request_changes", "comment": "cheaper pls"}, headers=H("rclient"))
        assert r.status_code == 200 and r.json()["status"] == "changes_requested"
        # PM cannot respond
        assert requests.post(f"{API}/quotations/{qid}/respond", json={"action": "accept", "signature_name": "PM"}, headers=H("rpm")).status_code == 403
        r = requests.post(f"{API}/quotations/{qid}/revise", json=qbody(rate=5500), headers=H("rpm"))
        assert r.status_code == 200 and r.json()["current_rev"] == 2 and r.json()["status"] == "draft"
        cl = next(x for x in requests.get(f"{API}/projects/{P_RES}/quotations", headers=H("rclient")).json() if x["id"] == qid)
        assert [rv["rev"] for rv in cl["revisions"]] == [1] and cl["status"] == "revision_in_progress"
        assert requests.get(f"{API}/quotations/{qid}/pdf", params={"auth": tok("rclient"), "rev": 2}).status_code == 404
        assert requests.post(f"{API}/quotations/{qid}/send", headers=H("rpm")).status_code == 200
        cl = next(x for x in requests.get(f"{API}/projects/{P_RES}/quotations", headers=H("rclient")).json() if x["id"] == qid)
        assert [rv["rev"] for rv in cl["revisions"]] == [1, 2]
        # signature min 3 chars
        r = requests.post(f"{API}/quotations/{qid}/respond", json={"action": "accept", "signature_name": "ab"}, headers=H("rclient"))
        assert r.status_code == 400
        r = requests.post(f"{API}/quotations/{qid}/respond", json={"action": "accept", "signature_name": "Client Name"}, headers=H("rclient"))
        assert r.status_code == 200 and r.json()["status"] == "accepted" and r.json()["client_response"]["signature_name"] == "Client Name"
        assert requests.post(f"{API}/quotations/{qid}/revise", json=qbody(), headers=H("rpm")).status_code == 400
        for k, rev in (("rclient", 1), ("rclient", 2), ("rpm", 2)):
            p = requests.get(f"{API}/quotations/{qid}/pdf", params={"auth": tok(k), "rev": rev})
            assert p.status_code == 200 and p.headers["content-type"].startswith("application/pdf") and p.content[:4] == b"%PDF"

    def test_reject_needs_comment_and_engineer_cannot_create(self):
        assert requests.post(f"{API}/projects/{P_RES}/quotations", json=qbody(), headers=H("arch")).status_code == 403
        q = requests.post(f"{API}/projects/{P_RES}/quotations", json=qbody("TEST Reject"), headers=H("rpm")).json()
        requests.post(f"{API}/quotations/{q['id']}/send", headers=H("rpm"))
        assert requests.post(f"{API}/quotations/{q['id']}/respond", json={"action": "reject"}, headers=H("rclient")).status_code == 400
        r = requests.post(f"{API}/quotations/{q['id']}/respond", json={"action": "reject", "comment": "too costly"}, headers=H("rclient"))
        assert r.status_code == 200 and r.json()["status"] == "rejected"

    def test_commercial_no_quotations(self):
        assert requests.get(f"{API}/projects/{P_COM}/quotations", headers=H("owner")).status_code == 403


# ---------------- Drawings ----------------
def upload(k, name="d.pdf"):
    r = requests.post(f"{API}/files/upload", files={"file": (name, b"%PDF-1.4 test drawing", "application/pdf")},
                      data={"project_id": P_RES}, headers=H(k))
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestDrawings:
    def test_flow(self):
        no = f"A-{UID}"
        f1 = upload("arch")
        r = requests.post(f"{API}/projects/{P_RES}/drawings", json={"discipline": "structural", "drawing_no": "S-X", "title": "Beam", "file_id": f1}, headers=H("arch"))
        assert r.status_code == 403
        r = requests.post(f"{API}/projects/{P_RES}/drawings", json={"discipline": "architectural", "drawing_no": no, "title": "Ground floor plan", "file_id": f1}, headers=H("arch"))
        assert r.status_code == 200, r.text
        d1 = r.json()
        assert d1["status"] == "pending" and d1["rev"] == 1
        r = requests.post(f"{API}/projects/{P_RES}/drawings", json={"discipline": "architectural", "drawing_no": no, "title": "dup", "file_id": f1}, headers=H("arch"))
        assert r.status_code == 409
        # structural engineer
        fs = upload("struct")
        assert requests.post(f"{API}/projects/{P_RES}/drawings", json={"discipline": "architectural", "drawing_no": "A-Y", "title": "Plan X", "file_id": fs},
                             headers=H("struct")).status_code == 403
        r = requests.post(f"{API}/projects/{P_RES}/drawings", json={"discipline": "structural", "drawing_no": f"S-{UID}", "title": "Footing", "file_id": fs}, headers=H("struct"))
        assert r.status_code == 200
        ds = r.json()
        # client hidden
        cl = requests.get(f"{API}/projects/{P_RES}/drawings", headers=H("rclient")).json()
        assert not any(x["id"] == d1["id"] for x in cl)
        assert requests.get(f"{API}/files/{f1}/download", params={"auth": tok("rclient")}).status_code == 403
        # architect cannot approve
        assert requests.post(f"{API}/drawings/{d1['id']}/decision", json={"action": "approve"}, headers=H("arch")).status_code == 403
        assert requests.post(f"{API}/drawings/{ds['id']}/decision", json={"action": "reject"}, headers=H("rpm")).status_code == 400
        r = requests.post(f"{API}/drawings/{ds['id']}/decision", json={"action": "reject", "remarks": "fix rebar"}, headers=H("rpm"))
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        r = requests.post(f"{API}/drawings/{d1['id']}/decision", json={"action": "approve"}, headers=H("rpm"))
        assert r.status_code == 200 and r.json()["status"] == "approved"
        cl = requests.get(f"{API}/projects/{P_RES}/drawings", headers=H("rclient")).json()
        assert any(x["id"] == d1["id"] for x in cl) and not any(x["id"] == ds["id"] for x in cl)
        assert requests.get(f"{API}/files/{f1}/download", params={"auth": tok("rclient")}).status_code == 200
        # new revision supersedes
        f2 = upload("arch", "d2.pdf")
        r = requests.post(f"{API}/projects/{P_RES}/drawings", json={"discipline": "architectural", "drawing_no": no, "title": "Ground floor plan v2", "file_id": f2}, headers=H("arch"))
        assert r.status_code == 200 and r.json()["rev"] == 2
        d2 = r.json()
        assert requests.post(f"{API}/drawings/{d2['id']}/decision", json={"action": "approve"}, headers=H("rowner")).status_code == 200
        allr = {x["id"]: x["status"] for x in requests.get(f"{API}/projects/{P_RES}/drawings", headers=H("rpm")).json()}
        assert allr[d1["id"]] == "superseded" and allr[d2["id"]] == "approved"
        cl = requests.get(f"{API}/projects/{P_RES}/drawings", headers=H("rclient")).json()
        assert any(x["id"] == d2["id"] for x in cl) and not any(x["id"] == d1["id"] for x in cl)

    def test_design_dashboard(self):
        for k in ("arch", "struct"):
            r = requests.get(f"{API}/dashboard/design", headers=H(k))
            assert r.status_code == 200 and len(r.json()["cards"]) == 4
        for k in ("rpm", "rclient"):
            assert requests.get(f"{API}/dashboard/design", headers=H(k)).status_code == 403
