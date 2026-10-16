# Iteration 9: Residential Phase 1 — accounts (no OTP), team, project delete, inspection, material approvals, residential DPR/BOQ
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PWD = "CivioHome@2026"
PID = "proj-res-1"
STAMP = uuid.uuid4().hex[:6]
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")


def login(email, pw=PWD):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    return r


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tok():
    out = {}
    for k in ["owner", "pm", "engineer", "client"]:
        r = login(f"{k}@civiohomes.build")
        assert r.status_code == 200, f"{k} login failed {r.text}"
        out[k] = r.json()["access_token"]
    out["_ids"] = {k: requests.get(f"{API}/auth/me", headers=H(out[k])).json().get("id") for k in ["owner", "pm", "engineer", "client"]}
    return out


def upload(token, pid=PID):
    r = requests.post(f"{API}/files/upload", headers=H(token), files={"file": ("t.png", io.BytesIO(PNG), "image/png")},
                      data={"project_id": pid, "caption": "TEST_"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# --- Accounts: login without OTP, reset password, deactivate / reactivate
class TestAccounts:
    created = []

    def test_create_and_login_no_otp(self, tok):
        for role in ["site_engineer", "client"]:
            email = f"test_{role}_{STAMP}@example.com"
            r = requests.post(f"{API}/users", headers=H(tok["owner"]), json={"email": email, "password": "Temp@12345", "name": f"TEST {role}",
                                                                              "role": role, "phone": "9999999999", "job_title": "TEST JT"})
            assert r.status_code == 200, r.text
            assert r.json()["job_title"] == "TEST JT"
            TestAccounts.created.append(r.json()["id"])
            lr = login(email, "Temp@12345")
            assert lr.status_code == 200, lr.text
            assert "access_token" in lr.json()

    def test_users_list_has_status(self, tok):
        r = requests.get(f"{API}/users", headers=H(tok["owner"]))
        assert r.status_code == 200
        u = next(x for x in r.json() if x["id"] == TestAccounts.created[0])
        assert u["is_active"] is True and "password_hash" not in u

    def test_set_job(self, tok):
        uid = TestAccounts.created[0]
        r = requests.put(f"{API}/users/{uid}/job", headers=H(tok["pm"]), json={"job_title": "Senior SE", "job_description": "Slabs"})
        assert r.status_code == 200 and r.json()["job_title"] == "Senior SE"

    def test_reset_password(self, tok):
        uid = TestAccounts.created[0]
        r = requests.post(f"{API}/users/{uid}/reset-password", headers=H(tok["pm"]))
        assert r.status_code == 200, r.text
        temp = r.json()["temporary_password"]
        assert login(r.json()["login_id"], temp).status_code == 200
        assert login(r.json()["login_id"], "Temp@12345").status_code == 401

    def test_pm_cannot_manage_owner_or_self_reset(self, tok):
        ids = tok["_ids"]
        assert requests.post(f"{API}/users/{ids['owner']}/reset-password", headers=H(tok["pm"])).status_code == 403
        assert requests.post(f"{API}/users/{ids['owner']}/deactivate", headers=H(tok["pm"])).status_code == 403
        assert requests.post(f"{API}/users/{ids['pm']}/reset-password", headers=H(tok["pm"])).status_code == 400

    def test_engineer_cannot_reset(self, tok):
        uid = TestAccounts.created[0]
        assert requests.post(f"{API}/users/{uid}/reset-password", headers=H(tok["engineer"])).status_code == 403

    def test_deactivate_then_login_403_then_reactivate(self, tok):
        uid = TestAccounts.created[1]
        email = f"test_client_{STAMP}@example.com"
        r = requests.post(f"{API}/users/{uid}/deactivate", headers=H(tok["pm"]))
        assert r.status_code == 200, r.text
        assert login(email, "Temp@12345").status_code == 403
        r = requests.post(f"{API}/users/{uid}/reactivate", headers=H(tok["pm"]))
        assert r.status_code == 200
        assert login(email, "Temp@12345").status_code == 200


# --- Team management & project delete (throwaway project)
class TestTeam:
    def test_team_add_remove_and_delete_project(self, tok):
        ids = tok["_ids"]
        code = f"TEST-{STAMP}"
        r = requests.post(f"{API}/projects", headers=H(tok["owner"]), json={"name": f"TEST proj {STAMP}", "code": code, "project_manager_id": ids["pm"]})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        # add engineer with job
        r = requests.post(f"{API}/projects/{pid}/team", headers=H(tok["pm"]), json={"user_id": ids["engineer"], "job_title": "TEST Site lead", "job_description": "x"})
        assert r.status_code == 200, r.text
        assert any(t["user_id"] == ids["engineer"] and t["job_title"] == "TEST Site lead" for t in r.json()["team"])
        assert requests.get(f"{API}/projects/{pid}", headers=H(tok["engineer"])).status_code == 200
        # PM cannot be removed
        assert requests.delete(f"{API}/projects/{pid}/team/{ids['pm']}", headers=H(tok["owner"])).status_code == 400
        # remove engineer
        r = requests.delete(f"{API}/projects/{pid}/team/{ids['engineer']}", headers=H(tok["pm"]))
        assert r.status_code == 200
        assert requests.get(f"{API}/projects/{pid}", headers=H(tok["engineer"])).status_code in (403, 404)
        # delete wrong code
        assert requests.post(f"{API}/projects/{pid}/delete", headers=H(tok["pm"]), json={"confirm_code": "WRONG"}).status_code == 400
        assert requests.post(f"{API}/projects/{pid}/delete", headers=H(tok["engineer"]), json={"confirm_code": code}).status_code == 403
        r = requests.post(f"{API}/projects/{pid}/delete", headers=H(tok["pm"]), json={"confirm_code": code})
        assert r.status_code == 200
        projs = requests.get(f"{API}/projects", headers=H(tok["owner"])).json()
        assert all(p["id"] != pid for p in projs)
        assert requests.get(f"{API}/projects/{pid}", headers=H(tok["owner"])).status_code in (403, 404)


# --- Inspection checklist
class TestInspection:
    def test_seed(self, tok):
        r = requests.get(f"{API}/projects/{PID}/inspection", headers=H(tok["pm"]))
        assert r.status_code == 200
        d = r.json()
        assert len(d["stages"]) >= 18 and d["summary"]["total"] >= 76
        assert d["stages"][0]["stage"] == "Setting Out" and d["stages"][17]["stage"] == "Handover"
        TestInspection.item = d["stages"][0]["items"][0]["id"]
        TestInspection.item2 = d["stages"][0]["items"][1]["id"]

    def test_client_can_view(self, tok):
        assert requests.get(f"{API}/projects/{PID}/inspection", headers=H(tok["client"])).status_code == 200

    def test_pass_without_photo_400(self, tok):
        r = requests.put(f"{API}/inspection-items/{TestInspection.item}", headers=H(tok["engineer"]), json={"status": "pass"})
        assert r.status_code == 400

    def test_pass_with_photo_ok(self, tok):
        fid = upload(tok["engineer"])
        r = requests.put(f"{API}/inspection-items/{TestInspection.item}", headers=H(tok["engineer"]),
                         json={"status": "pass", "photo_ids": [fid], "responsible_id": tok["_ids"]["engineer"], "remarks": "TEST ok"})
        assert r.status_code == 200, r.text
        d = requests.get(f"{API}/projects/{PID}/inspection", headers=H(tok["pm"])).json()
        it = next(i for s in d["stages"] for i in s["items"] if i["id"] == TestInspection.item)
        assert it["status"] == "pass" and fid in it["photo_ids"] and it["responsible_name"]
        TestInspection.fid = fid

    def test_fail_requires_remarks(self, tok):
        r = requests.put(f"{API}/inspection-items/{TestInspection.item2}", headers=H(tok["engineer"]), json={"status": "fail", "photo_ids": [TestInspection.fid]})
        assert r.status_code == 400
        r = requests.put(f"{API}/inspection-items/{TestInspection.item2}", headers=H(tok["engineer"]), json={"status": "na"})
        assert r.status_code == 200

    def test_client_put_403(self, tok):
        r = requests.put(f"{API}/inspection-items/{TestInspection.item}", headers=H(tok["client"]), json={"status": "na"})
        assert r.status_code == 403

    def test_documents(self, tok):
        fid = upload(tok["pm"])
        r = requests.post(f"{API}/projects/{PID}/documents", headers=H(tok["pm"]), json={"file_id": fid, "title": "TEST drawing", "category": "drawing"})
        assert r.status_code == 200, r.text
        did = r.json()["id"]
        docs = requests.get(f"{API}/projects/{PID}/documents", headers=H(tok["client"])).json()
        assert any(d["id"] == did for d in docs)
        assert requests.delete(f"{API}/documents/{did}", headers=H(tok["pm"])).status_code == 200

    def test_report_roles(self, tok):
        assert requests.post(f"{API}/projects/{PID}/inspection/report", headers=H(tok["engineer"])).status_code == 403
        for k in ["pm", "owner", "client"]:
            r = requests.post(f"{API}/projects/{PID}/inspection/report", headers=H(tok[k]))
            assert r.status_code == 200, f"{k}: {r.text}"
            rid = r.json()["id"]
        reps = requests.get(f"{API}/projects/{PID}/reports", headers=H(tok["pm"])).json()
        assert any(x["id"] == rid for x in reps)
        dl = requests.get(f"{API}/reports/{rid}/download", headers=H(tok["client"]))
        assert dl.status_code == 200 and dl.content[:4] == b"%PDF"

    def test_commercial_inspection(self):
        t = login("civiobuilds@gmail.com", "Civio@123456").json()["access_token"]
        r = requests.get(f"{API}/projects/proj-demo-1/inspection", headers=H(t))
        assert r.status_code == 200 and r.json()["summary"]["total"] >= 76
        assert requests.get(f"{API}/projects/proj-demo-1/defects", headers=H(t)).status_code == 403


# --- Material approvals
class TestMaterials:
    def test_flow_approve(self, tok):
        r = requests.post(f"{API}/projects/{PID}/material-approvals", headers=H(tok["engineer"]),
                          json={"item": "TEST Cement", "quantity": 50, "unit": "bags", "required_date": "2026-02-10"})
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["status"] == "pending_pm"
        mid = m["id"]
        cl = requests.get(f"{API}/projects/{PID}/material-approvals", headers=H(tok["client"])).json()
        assert all(x["id"] != mid for x in cl)
        pm_pending = requests.get(f"{API}/material-approvals/pending", headers=H(tok["pm"])).json()
        assert any(x["id"] == mid for x in pm_pending)
        assert requests.post(f"{API}/material-approvals/{mid}/pm", headers=H(tok["engineer"]), json={"action": "submit"}).status_code == 403
        r = requests.post(f"{API}/material-approvals/{mid}/pm", headers=H(tok["pm"]), json={"action": "submit", "remarks": "ok"})
        assert r.status_code == 200 and r.json()["status"] == "pending_client"
        cp = requests.get(f"{API}/material-approvals/pending", headers=H(tok["client"])).json()
        assert any(x["id"] == mid for x in cp)
        assert requests.post(f"{API}/material-approvals/{mid}/client", headers=H(tok["engineer"]), json={"action": "approve"}).status_code == 403
        assert requests.post(f"{API}/material-approvals/{mid}/client", headers=H(tok["client"]), json={"action": "reject"}).status_code == 400
        r = requests.post(f"{API}/material-approvals/{mid}/client", headers=H(tok["client"]), json={"action": "approve", "remarks": "fine"})
        assert r.status_code == 200 and r.json()["status"] == "approved"
        assert len(r.json()["history"]) == 3
        notes = requests.get(f"{API}/notifications", headers=H(tok["engineer"])).json()
        notes = notes if isinstance(notes, list) else notes.get("items", notes.get("notifications", []))
        assert any("TEST Cement" in n.get("message", "") for n in notes)

    def test_pm_direct_and_client_reject(self, tok):
        r = requests.post(f"{API}/projects/{PID}/material-approvals", headers=H(tok["pm"]), json={"item": "TEST Steel", "quantity": 2, "unit": "t"})
        assert r.status_code == 200 and r.json()["status"] == "pending_client"
        mid = r.json()["id"]
        r = requests.post(f"{API}/material-approvals/{mid}/client", headers=H(tok["client"]), json={"action": "reject", "remarks": "too costly"})
        assert r.status_code == 200 and r.json()["status"] == "rejected"

    def test_pm_reject_needs_remarks(self, tok):
        mid = requests.post(f"{API}/projects/{PID}/material-approvals", headers=H(tok["engineer"]), json={"item": "TEST Sand", "quantity": 1}).json()["id"]
        assert requests.post(f"{API}/material-approvals/{mid}/pm", headers=H(tok["pm"]), json={"action": "reject"}).status_code == 400
        r = requests.post(f"{API}/material-approvals/{mid}/pm", headers=H(tok["pm"]), json={"action": "reject", "remarks": "no"})
        assert r.json()["status"] == "rejected"

    def test_client_cannot_create(self, tok):
        assert requests.post(f"{API}/projects/{PID}/material-approvals", headers=H(tok["client"]), json={"item": "x", "quantity": 1}).status_code == 403


# --- Residential DPR + BOQ
class TestResDpr:
    def test_boq(self, tok):
        r = requests.post(f"{API}/projects/{PID}/boq", headers=H(tok["pm"]), json={"code": f"TEST-{STAMP}", "description": "TEST slab", "unit": "m3", "approved_qty": 10})
        assert r.status_code == 200, r.text
        TestResDpr.boq = r.json()["id"]
        assert any(b["id"] == TestResDpr.boq for b in requests.get(f"{API}/projects/{PID}/boq", headers=H(tok["pm"])).json())

    def test_dpr_flow(self, tok):
        # pick an unused date
        existing = {d["report_date"] for d in requests.get(f"{API}/projects/{PID}/dprs", headers=H(tok["pm"])).json()}
        day = next(f"2025-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 28) if f"2025-{m:02d}-{d:02d}" not in existing)
        r = requests.post(f"{API}/projects/{PID}/dprs", headers=H(tok["engineer"]), json={"report_date": day, "weather": "Sunny",
                          "boq_entries": [{"boq_id": TestResDpr.boq, "qty": 2}]})
        if r.status_code == 422:
            r = requests.post(f"{API}/projects/{PID}/dprs", headers=H(tok["engineer"]), json={"report_date": day, "weather": "Sunny"})
        assert r.status_code == 200, r.text
        did = r.json()["id"]
        cl = requests.get(f"{API}/projects/{PID}/dprs", headers=H(tok["client"]))
        assert cl.status_code == 200 and all(d["id"] != did for d in cl.json())
        assert requests.post(f"{API}/dprs/{did}/submit", headers=H(tok["engineer"])).status_code == 200
        r = requests.post(f"{API}/dprs/{did}/review", headers=H(tok["pm"]), json={"action": "approve", "comment": "ok"})
        assert r.status_code == 200, r.text
        cl = requests.get(f"{API}/projects/{PID}/dprs", headers=H(tok["client"])).json()
        assert any(d["id"] == did for d in cl)
        pdf = requests.get(f"{API}/dprs/{did}/pdf", headers=H(tok["client"]))
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
        TestResDpr.did = did


# --- Commercial regression
class TestCommercialRegression:
    def test_commercial(self):
        t = login("civiobuilds@gmail.com", "Civio@123456").json()["access_token"]
        for path in ["dprs", "attendance", "store/stock", "members", "boq"]:
            r = requests.get(f"{API}/projects/proj-demo-1/{path}", headers=H(t))
            assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        assert requests.get(f"{API}/projects/proj-demo-1/material-approvals", headers=H(t)).status_code == 403
