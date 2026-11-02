"""People/account management, project team, safe project deletion, residential material approvals."""
import asyncio
import secrets
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import server as S
import commercial as C
import emailer

router = APIRouter()
STAGES = {"pending_pm": "Awaiting PM review", "pending_client": "Awaiting client approval", "approved": "Approved", "rejected": "Rejected"}


class JobIn(BaseModel):
    job_title: str = Field(default="", max_length=80)
    job_description: str = Field(default="", max_length=1000)


class TeamIn(JobIn):
    user_id: str


class DeleteProjectIn(BaseModel):
    confirm_code: str


class MatIn(BaseModel):
    item: str = Field(min_length=1, max_length=120)
    quantity: float = Field(gt=0)
    unit: str = Field(default="nos", max_length=20)
    required_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    remarks: str = Field(default="", max_length=1000)
    specification: str = Field(default="", max_length=200)
    brand: str = Field(default="", max_length=80)
    delivery_location: str = Field(default="", max_length=200)
    priority: str = Field(default="normal", pattern=r"^(low|normal|urgent)$")
    purpose: str = Field(default="", max_length=300)
    attachment_ids: List[str] = Field(default=[], max_length=5)


class MatDecisionIn(BaseModel):
    action: str
    remarks: str = Field(default="", max_length=1000)


managers = S.require_roles("admin", "project_manager")


async def _target(uid, actor):
    t = await S.db.users.find_one({"id": uid, "company_id": actor["company_id"]}, {"_id": 0})
    if not t or (t.get("platform_role") == "super_admin" and t["id"] != actor["id"]):
        raise HTTPException(status_code=404, detail="User not found")
    if actor["role"] == "project_manager" and t["role"] in {"admin", "project_manager"} and t["id"] != actor["id"]:
        raise HTTPException(status_code=403, detail="Only an admin can manage owners and project managers.")
    return t


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
@router.put("/users/{uid}/job")
async def set_job(uid: str, body: JobIn, user: dict = Depends(managers)):
    await _target(uid, user)
    await S.db.users.update_one({"id": uid}, {"$set": body.model_dump()})
    return S.public_user(await S.db.users.find_one({"id": uid}, {"_id": 0}))


@router.post("/users/{uid}/reset-password")
async def reset_password(uid: str, user: dict = Depends(managers)):
    t = await _target(uid, user)
    if t["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Use Change password for your own account.")
    if t.get("is_active") is False:
        raise HTTPException(status_code=400, detail="Reactivate this account before resetting its password.")
    temp = f"Civio@{secrets.randbelow(900000) + 100000}"
    await S.db.users.update_one({"id": uid}, {"$set": {"password_hash": S.hash_password(temp), "password_reset_at": S.now_iso(),
                                                       "password_reset_by": user["id"], "email_verified": True}})
    await S.db.user_sessions.delete_many({"user_id": uid})
    await S.log_audit(None, user, "reset user password", "user", uid, t["email"])
    return {"login_id": t["email"], "temporary_password": temp}


async def _detach(uid, user, t):
    async for p in S.db.projects.find({"company_id": user["company_id"], "$or": [{"engineer_ids": uid}, {"client_id": uid}, {"team": {"$elemMatch": {"user_id": uid, "removed_at": None}}}]}, {"_id": 0}):
        await _remove_from_project(p, uid, user, t["name"])
    await S.db.project_members.delete_many({"user_id": uid, "company_id": user["company_id"]})


@router.post("/users/{uid}/deactivate")
async def deactivate(uid: str, user: dict = Depends(managers)):
    t = await _target(uid, user)
    if t["id"] == user["id"] or t["role"] == "admin" and t["id"] == user["_enterprise"].get("owner_id"):
        raise HTTPException(status_code=400, detail="This account cannot be removed.")
    if await S.db.projects.find_one({"project_manager_id": uid, "is_deleted": {"$ne": True}, "is_archived": {"$ne": True}}):
        raise HTTPException(status_code=400, detail="Reassign this PM's projects to another PM first.")
    await S.db.users.update_one({"id": uid}, {"$set": {"is_active": False, "deactivated_at": S.now_iso(), "deactivated_by": user["id"]}})
    await S.db.user_sessions.delete_many({"user_id": uid})
    await _detach(uid, user, t)
    await S.log_audit(None, user, "removed user from organisation", "user", uid, t["email"])
    return {"ok": True}


@router.post("/users/{uid}/reactivate")
async def reactivate(uid: str, user: dict = Depends(managers)):
    t = await _target(uid, user)
    await S.enforce_limit(user, "users")
    await S.db.users.update_one({"id": uid}, {"$set": {"is_active": True}, "$unset": {"deactivated_at": ""}})
    await S.log_audit(None, user, "reactivated user", "user", uid, t["email"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Project team & deletion
# ---------------------------------------------------------------------------
async def _remove_from_project(p, uid, user, name):
    upd = {"$pull": {"engineer_ids": uid}}
    if p.get("client_id") == uid:
        upd["$set"] = {"client_id": None}
    await S.db.projects.update_one({"id": p["id"]}, upd)
    if any(t["user_id"] == uid and not t.get("removed_at") for t in p.get("team", [])):
        await S.db.projects.update_one({"id": p["id"]}, {"$set": {"team.$[t].removed_at": S.now_iso(), "team.$[t].removed_by": user["id"]}},
                                       array_filters=[{"t.user_id": uid, "t.removed_at": None}])
    await S.log_audit(p["id"], user, "removed person from project", "user", uid, name)


@router.post("/projects/{pid}/team")
async def add_team(pid: str, body: TeamIn, user: dict = Depends(managers)):
    p = await S.get_project_or_403(pid, user, write=True)
    if not C._manages(user, p):
        raise HTTPException(status_code=403, detail="Only the admin or this project's manager can add people.")
    t = await S.db.users.find_one({"id": body.user_id, "company_id": user["company_id"], "is_active": {"$ne": False}}, {"_id": 0})
    if not t or t.get("platform_role") == "super_admin" and t["role"] == "admin":
        raise HTTPException(status_code=400, detail="Choose an active person from your company.")
    upd = {}
    if t["role"] == "site_engineer":
        upd["$addToSet"] = {"engineer_ids": t["id"]}
    elif t["role"] == "client":
        if p.get("client_id") and p["client_id"] != t["id"]:
            raise HTTPException(status_code=400, detail="This project already has a client. Remove them first.")
        upd["$set"] = {"client_id": t["id"]}
    elif t["role"] == "project_manager":
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Only an admin can change the project manager.")
        upd["$set"] = {"project_manager_id": t["id"]}
    if upd:
        await S.db.projects.update_one({"id": pid}, upd)
    await S.db.projects.update_one({"id": pid}, {"$pull": {"team": {"user_id": t["id"], "removed_at": None}}})
    entry = {"user_id": t["id"], **body.model_dump(exclude={"user_id"}), "added_by": user["id"], "added_at": S.now_iso(), "removed_at": None}
    await S.db.projects.update_one({"id": pid}, {"$push": {"team": entry, "team_history": {**entry, "action": "added"}}})
    if t["role"] != "client" and not await S.db.project_members.find_one({"project_id": pid, "user_id": t["id"]}):
        await S.db.project_members.insert_one({"project_id": pid, "user_id": t["id"], "company_id": user["company_id"], "responsibility": body.job_title or "",
                                               "permissions": dict(C.ROLE_PRESETS.get(t["role"], C.DEFAULT_PRESET)), "access_v2": True,
                                               "attendance_required": False, "location_required": False, "updated_by": user["id"],
                                               "updated_at": S.now_iso(), "created_at": S.now_iso()})
    await S.log_audit(pid, user, "assigned person to project", "user", t["id"], f"{t['name']} as {body.job_title or S.ROLE_NAMES.get(t['role'])}")
    await S.notify(t["id"], "assignment", f"You were added to project {p['name']}" + (f" as {body.job_title}." if body.job_title else "."), pid)
    return await S.enrich_project(await S.db.projects.find_one({"id": pid}, {"_id": 0}))


@router.delete("/projects/{pid}/team/{uid}")
async def remove_team(pid: str, uid: str, user: dict = Depends(managers)):
    p = await S.get_project_or_403(pid, user, write=True)
    if not C._manages(user, p):
        raise HTTPException(status_code=403, detail="Only the admin or this project's manager can remove people.")
    if p.get("project_manager_id") == uid:
        raise HTTPException(status_code=400, detail="Assign a different project manager before removing this one.")
    t = await S.db.users.find_one({"id": uid, "company_id": user["company_id"]}, {"_id": 0, "name": 1})
    if not t:
        raise HTTPException(status_code=404, detail="User not found")
    await _remove_from_project(p, uid, user, t["name"])
    await S.db.projects.update_one({"id": pid}, {"$push": {"team_history": {"user_id": uid, "action": "removed", "by": user["id"], "at": S.now_iso()}}})
    await S.db.project_members.delete_one({"project_id": pid, "user_id": uid})
    return await S.enrich_project(await S.db.projects.find_one({"id": pid}, {"_id": 0}))


@router.post("/projects/{pid}/delete")
async def delete_project(pid: str, body: DeleteProjectIn, user: dict = Depends(managers)):
    p = await S.get_project_or_403(pid, user, write=True)
    if body.confirm_code.strip() != p.get("code"):
        raise HTTPException(status_code=400, detail="Type the project code exactly to confirm deletion.")
    await S.db.projects.update_one({"id": pid}, {"$set": {"is_deleted": True, "is_archived": True, "deleted_at": S.now_iso(), "deleted_by": user["id"]}})
    await S.log_audit(pid, user, "deleted project (records retained)", "project", pid, p["name"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Residential material approvals (no costing)
# ---------------------------------------------------------------------------
async def _mat(mid, user):
    m = await S.db.material_approvals.find_one({"id": mid, "company_id": user["company_id"]}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Request not found")
    return m, await S.get_project_or_403(m["project_id"], user)


CLIENT_MAT_FIELDS = ("id", "item", "specification", "status", "project_id", "project_name", "created_at", "updated_at")


def _out(m, user=None):
    st = "pending_pm" if m["status"] == "pending_client" else m["status"]
    if user and user["role"] == "client":
        return {**{k: m.get(k) for k in CLIENT_MAT_FIELDS}, "status": st, "stage_label": STAGES[st]}
    return {**m, "status": st, "stage_label": STAGES[st]}


async def _check_attachments(pid, ids):
    if ids and await S.db.files.count_documents({"id": {"$in": ids}, "project_id": pid, "is_deleted": False}) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Attachments must be uploaded to this project.")


async def _email_client(p, m):
    if not p.get("client_id"):
        return
    c = await S.db.users.find_one({"id": p["client_id"]}, {"_id": 0})
    if not c:
        return
    await S.notify(c["id"], "material_approval", f"Material approval needed: {m['quantity']} {m['unit']} {m['item']} — {p['name']}.", p["id"],
                   link=f"/projects/{p['id']}?tab=materials", dedupe_key=f"mat-{m['id']}", push=True)
    asyncio.create_task(emailer.send_email(to=c["email"], subject=f"Material approval required — {p['name']}",
                                           html=emailer.material_approval_email_html(c["name"], p["name"], m)))


async def _log(mid, status, user, remarks, extra=None):
    ts = S.now_iso()
    await S.db.material_approvals.update_one({"id": mid}, {"$set": {"status": status, "updated_at": ts, **(extra or {})},
                                                           "$push": {"history": {"status": status, "by": user["name"], "role": user["role"], "at": ts, "remarks": remarks}}})


@router.get("/projects/{pid}/material-approvals")
async def list_mats(pid: str, user: dict = Depends(S.get_current_user)):
    S.require_module(user, "material_approval")
    await S.get_project_or_403(pid, user)
    return [_out(m, user) for m in await S.db.material_approvals.find({"project_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(1000)]


@router.post("/projects/{pid}/material-approvals")
async def create_mat(pid: str, body: MatIn, user: dict = Depends(S.require_roles("admin", "project_manager", "site_engineer"))):
    S.require_module(user, "material_approval")
    p = await S.get_project_or_403(pid, user, write=True)
    mgr = C._manages(user, p)
    await _check_attachments(pid, body.attachment_ids)
    ts, status = S.now_iso(), "approved" if mgr else "pending_pm"
    m = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, "project_name": p["name"], **body.model_dump(),
         "status": status, "requested_by": user["id"], "requested_by_name": user["name"], "requested_by_role": user["role"],
         "created_at": ts, "updated_at": ts, "history": [{"status": status, "by": user["name"], "role": user["role"], "at": ts, "remarks": body.remarks}]}
    await S.db.material_approvals.insert_one(m)
    m.pop("_id", None)
    await S.log_audit(pid, user, "raised material request", "material_approval", m["id"], f"{body.quantity} {body.unit} {body.item}")
    if not mgr and p.get("project_manager_id"):
        await S.notify(p["project_manager_id"], "material_approval", f"{user['name']} requested {body.quantity} {body.unit} {body.item} — review needed.",
                       pid, link=f"/projects/{pid}?tab=materials", push=True)
    return _out(m)


@router.post("/material-approvals/{mid}/pm")
async def pm_decide(mid: str, body: MatDecisionIn, user: dict = Depends(managers)):
    m, p = await _mat(mid, user)
    await S.get_project_or_403(p["id"], user, write=True)
    if not C._manages(user, p):
        raise HTTPException(status_code=403, detail="Only the owner or this project's manager can decide.")
    if m["status"] not in {"pending_pm", "pending_client"} or body.action not in {"approve", "submit", "reject"}:
        raise HTTPException(status_code=400, detail="This request is not awaiting PM review.")
    if body.action == "reject" and not body.remarks.strip():
        raise HTTPException(status_code=400, detail="Add remarks when rejecting.")
    status = "rejected" if body.action == "reject" else "approved"
    await _log(mid, status, user, body.remarks, {"pm_by": user["id"], "pm_remarks": body.remarks})
    await S.log_audit(p["id"], user, f"material request {status}", "material_approval", mid, body.remarks)
    m = (await _mat(mid, user))[0]
    await S.notify(m["requested_by"], "material_approval", f"Your material request for {m['item']}: {STAGES[status]}.", p["id"],
                   link=f"/projects/{p['id']}?tab=materials", push=True)
    return _out(m)


@router.post("/material-approvals/{mid}/client")
async def client_decide(mid: str, body: MatDecisionIn, user: dict = Depends(S.require_roles("admin", "client"))):
    raise HTTPException(status_code=410, detail="Client approval of material requests has been removed. The PM or owner decides.")
    m, p = await _mat(mid, user)
    if user["role"] == "client" and p.get("client_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Only this project's client can decide.")
    if m["status"] != "pending_client" or body.action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="This request is not awaiting client approval.")
    if body.action == "reject" and not body.remarks.strip():
        raise HTTPException(status_code=400, detail="Add remarks when rejecting.")
    status = "approved" if body.action == "approve" else "rejected"
    await _log(mid, status, user, body.remarks, {"client_by": user["id"], "client_remarks": body.remarks, "decided_at": S.now_iso()})
    await S.log_audit(p["id"], user, f"client {status} material request", "material_approval", mid, body.remarks)
    for uid in {m["requested_by"], p.get("project_manager_id")} - {None, user["id"]}:
        await S.notify(uid, "material_approval", f"Material request {m['item']} was {status} by {user['name']}.", p["id"],
                       link=f"/projects/{p['id']}?tab=materials", push=True)
    return _out((await _mat(mid, user))[0])


@router.get("/material-approvals/pending")
async def pending_mats(user: dict = Depends(S.get_current_user)):
    if "material_approval" not in S.MODULES.get(user["_enterprise"].get("business_type"), set()):
        return []
    pids = [p["id"] for p in await S.list_projects(user)]
    if user["role"] == "client":
        return []
    items = await S.db.material_approvals.find({"project_id": {"$in": pids}, "status": {"$in": ["pending_pm", "pending_client"]}}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [_out(m, user) for m in items]


@router.put("/material-approvals/{mid}")
async def edit_mat(mid: str, body: MatIn, user: dict = Depends(S.get_current_user)):
    m, p = await _mat(mid, user)
    if m["requested_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the requester can edit this request.")
    if m["status"] not in {"pending_pm", "pending_client"}:
        raise HTTPException(status_code=400, detail="The PM has already decided — this request can no longer be edited.")
    await _check_attachments(p["id"], body.attachment_ids)
    await S.db.material_approvals.update_one({"id": mid}, {"$set": {**body.model_dump(), "updated_at": S.now_iso()},
                                                          "$push": {"history": {"status": m["status"], "by": user["name"], "role": user["role"], "at": S.now_iso(), "remarks": "Edited by requester"}}})
    await S.log_audit(p["id"], user, "edited material request", "material_approval", mid, body.item)
    return _out((await _mat(mid, user))[0], user)
