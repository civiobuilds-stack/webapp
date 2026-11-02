"""Commercial workspace: employees, project permissions, attendance, DPRs, weekly digest, web push."""
import asyncio
import csv
import hmac
import io
import json
import os
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field

import server as S
import emailer
import reports as reports_module

router = APIRouter()
log = logging.getLogger("civio.commercial")
IST = ZoneInfo("Asia/Kolkata")

MODULE_LABELS = {"overview": "Overview", "activities": "Activities", "progress": "Progress", "dpr": "DPR", "inspection": "Inspection",
                 "procurement": "Materials & Procurement", "store": "Store & Inventory", "tools": "Tools", "attendance": "Attendance",
                 "passes": "Site Passes", "documents": "Documents", "billing": "Billing & Cost", "vehicles": "Vehicles", "reports": "Reports",
                 "photos": "Photos", "team": "Team"}
PERM_MODULES = list(MODULE_LABELS)
_V, _C, _E, _A = ["view"], ["view", "create", "submit"], ["view", "create", "submit", "edit"], ["view", "create", "submit", "edit", "approve", "export"]
_BASE = {"overview": _V, "team": _V, "photos": _V, "attendance": ["create"]}
ROLE_PRESETS = {
    "site_engineer": {**_BASE, "activities": _E, "progress": _E, "dpr": _E, "inspection": _E, "store": _C, "procurement": _C, "photos": _C,
                      "tools": _C, "documents": _V, "reports": ["view", "create"], "vehicles": _C, "passes": _C},
    "project_manager": {**_BASE, "activities": _E, "progress": _E, "dpr": _E, "inspection": _E, "store": _C, "procurement": _C, "photos": _C,
                        "tools": _C, "documents": _C, "reports": ["view", "create"], "vehicles": _C, "passes": _C},
    "store_incharge": {**_BASE, "store": _A, "procurement": _V, "vehicles": _V, "tools": _A},
    "store_manager": {**_BASE, "store": _A, "procurement": _V, "vehicles": _V, "tools": _A, "reports": _V},
    "accounts": {**_BASE, "billing": ["view", "create", "submit", "edit", "export"], "procurement": _V, "reports": _V, "vehicles": _V},
    "safety_engineer": {**_BASE, "inspection": _E, "activities": _V, "progress": _V, "dpr": _V, "photos": _C, "passes": _V, "reports": _V},
    "safety_manager": {**_BASE, "inspection": _A, "activities": _V, "progress": _V, "dpr": _V, "photos": _C, "passes": _A, "reports": _V},
    "quality_engineer": {**_BASE, "inspection": _E, "activities": _V, "progress": _V, "dpr": _V, "photos": _C, "reports": _V},
    "quality_manager": {**_BASE, "inspection": _A, "activities": _V, "progress": _V, "dpr": _V, "photos": _C, "reports": _V},
    "pass_coordinator": {**_BASE, "passes": _A},
    "driver": {**_BASE, "vehicles": _V},
    "architect": {**_BASE, "documents": _C, "progress": _V, "activities": _V, "reports": _V},
    "structural_engineer": {**_BASE, "documents": _C, "progress": _V, "activities": _V, "reports": _V, "inspection": _V},
}
DEFAULT_PRESET = {**_BASE, "dpr": _V, "activities": _V, "progress": _V}
ROUTE_MODULES = [("my-permissions", None), ("files/upload", None), ("geofence", None), ("quotation", None), ("audit-log", None), ("/delete", None),
                 ("/archive", None), ("bills", "billing"), ("cost-summary", "billing"), ("labour-cost", "billing"), ("wages", "billing"),
                 ("vehicle", "vehicles"), ("inspection", "inspection"), ("defect", "inspection"), ("dpr", "dpr"), ("labour", "attendance"),
                 ("attendance", "attendance"), ("material", "procurement"), ("purchase-order", "procurement"), ("supplier", "procurement"),
                 ("store", "store"), ("tool", "tools"), ("passes", "passes"), ("drawing", "documents"), ("document", "documents"),
                 ("report", "reports"), ("activities", "activities"), ("milestone", "progress"), ("progress", "progress"), ("target", "progress"),
                 ("boq", "progress"), ("photos", "photos"), ("members", "team"), ("/team", "team"), ("/assign", "team")]
_APPROVE_WORDS = ("approve", "decision", "signoff", "review", "/pm", "verify", "/correct")


def route_module(method, path):
    p = path.lower()
    mod = next((m for k, m in ROUTE_MODULES if k in p), "missing")
    if mod == "missing":
        parts = p.strip("/").split("/")
        mod = "overview" if len(parts) == 3 and parts[1] == "projects" else None
    if not mod:
        return None, None
    if method == "GET":
        return mod, "view"
    if any(w in p for w in _APPROVE_WORDS):
        return mod, "approve"
    return mod, "edit" if method in {"PUT", "PATCH", "DELETE"} else "create"
ACTIONS = ["view", "create", "edit", "submit", "approve", "export", "delete"]
ENGINEER_DEFAULT = {"dpr": ["view", "create", "edit", "submit"], "attendance": ["view", "create"], "store": ["view", "create"], "vehicles": ["view", "create"]}
MEMBER_DEFAULT = {"dpr": ["view"], "attendance": ["create"]}
DEFAULT_DEPARTMENTS = ["Civil", "MEP", "QA/QC", "Safety", "Planning", "Procurement"]
DEFAULT_DESIGNATIONS = ["Project Manager", "Site Engineer", "Supervisor", "Foreman", "QA/QC Engineer", "Safety Officer", "Storekeeper"]


def _commercial(user):
    S.require_module(user, "dpr")


async def commercial_user(user: dict = Depends(S.get_current_user)) -> dict:
    _commercial(user)
    return user


def _dpr_ok(user):
    mods = S.MODULES.get((user.get("_enterprise") or {}).get("business_type", "commercial"), set())
    if not ({"dpr", "res_dpr"} & mods):
        raise HTTPException(status_code=403, detail="This module is not available for your workspace type.")


async def dpr_user(user: dict = Depends(S.get_current_user)) -> dict:
    _dpr_ok(user)
    return user


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
def _manages(user, project):
    return user["role"] == "admin" or (user["role"] == "project_manager" and (
        project.get("project_manager_id") == user["id"] or project.get("created_by") == user["id"]))


async def perms_for(user, project) -> Dict[str, List[str]]:
    if _manages(user, project):
        return {m: list(ACTIONS) for m in PERM_MODULES}
    if user["role"] == "client":
        return {"dpr": ["view"]} if project.get("client_id") == user["id"] else {}
    preset = ROLE_PRESETS.get(user["role"], DEFAULT_PRESET)
    m = await S.db.project_members.find_one({"project_id": project["id"], "user_id": user["id"]}, {"_id": 0})
    explicit = (m or {}).get("permissions") or {}
    if m and m.get("access_v2"):
        return {k: list(explicit.get(k, [])) for k in PERM_MODULES}
    return {k: sorted(set(explicit.get(k, [])) | set(preset.get(k, [])), key=ACTIONS.index) for k in PERM_MODULES}


async def visible_modules(user, projects):
    if user["role"] == "admin":
        return set(PERM_MODULES)
    mods = set()
    for p in projects:
        perms = await perms_for(user, p)
        mods |= {m for m, acts in perms.items() if acts and ("view" in acts or m == "attendance")}
    if user["role"] == "driver":
        mods.add("vehicles")
    return mods


async def require_perm(user, project_id, module, action):
    project = await S.get_project_or_403(project_id, user)
    perms = await perms_for(user, project)
    if action not in perms.get(module, []):
        raise HTTPException(status_code=403, detail=f"You do not have '{action}' permission for {module} on this project.")
    return project, perms


async def recipients_with(project, module, action, exclude=None):
    ids = set(filter(None, [project.get("project_manager_id")]))
    async for m in S.db.project_members.find({"project_id": project["id"], f"permissions.{module}": action}, {"_id": 0, "user_id": 1}):
        ids.add(m["user_id"])
    ids.discard(exclude)
    return list(ids)


def _clean_perms(perms: Dict[str, List[str]]):
    out = {}
    for mod, acts in (perms or {}).items():
        if mod not in PERM_MODULES:
            raise HTTPException(status_code=400, detail=f"Unknown module {mod}.")
        bad = [a for a in acts if a not in ACTIONS]
        if bad:
            raise HTTPException(status_code=400, detail=f"Unknown action(s) {bad}.")
        if acts:
            out[mod] = sorted(set(acts), key=ACTIONS.index)
    return out


# ---------------------------------------------------------------------------
# Organisation & employees
# ---------------------------------------------------------------------------
class OrgConfigIn(BaseModel):
    departments: List[str]
    designations: List[str]


class EmployeeIn(BaseModel):
    employee_id: str = Field(min_length=1, max_length=40)
    designation: str
    department: str
    reporting_manager_id: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None


async def _org(cid):
    c = await S.db.org_config.find_one({"company_id": cid}, {"_id": 0})
    return c or {"company_id": cid, "departments": DEFAULT_DEPARTMENTS, "designations": DEFAULT_DESIGNATIONS}


@router.get("/org/config")
async def get_org(user: dict = Depends(commercial_user)):
    return await _org(user["company_id"])


@router.put("/org/config")
async def put_org(body: OrgConfigIn, user: dict = Depends(commercial_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can configure the organisation.")
    clean = lambda xs: sorted({x.strip() for x in xs if x.strip()})  # noqa: E731
    doc = {"company_id": user["company_id"], "departments": clean(body.departments), "designations": clean(body.designations)}
    await S.db.org_config.update_one({"company_id": user["company_id"]}, {"$set": doc}, upsert=True)
    return doc


@router.get("/employees")
async def list_employees(user: dict = Depends(commercial_user)):
    if user["role"] not in S.MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed.")
    users = await S.db.users.find({"company_id": user["company_id"], "role": {"$ne": "client"}, "is_active": {"$ne": False}},
                                  {"_id": 0, "password_hash": 0}).to_list(2000)
    counts = {}
    pids = {}
    async for m in S.db.project_members.find({"company_id": user["company_id"]}, {"_id": 0, "user_id": 1, "project_id": 1}):
        pids.setdefault(m["user_id"], set()).add(m["project_id"])
    async for p in S.db.projects.find({"company_id": user["company_id"], "is_deleted": {"$ne": True}, "is_archived": {"$ne": True}}, {"_id": 0, "id": 1, "project_manager_id": 1, "engineer_ids": 1}):
        for uid in [p.get("project_manager_id"), *p.get("engineer_ids", [])]:
            if uid:
                pids.setdefault(uid, set()).add(p["id"])
    counts.update({k: len(v) for k, v in pids.items()})
    return [{**S.public_user(u), "project_count": counts.get(u["id"], 0)} for u in users]


@router.put("/employees/{uid}")
async def update_employee(uid: str, body: EmployeeIn, user: dict = Depends(commercial_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can edit employee records.")
    target = await S.db.users.find_one({"id": uid, "company_id": user["company_id"]}, {"_id": 0})
    if not target or target["role"] == "client":
        raise HTTPException(status_code=404, detail="Employee not found")
    org = await _org(user["company_id"])
    if body.designation not in org["designations"] or body.department not in org["departments"]:
        raise HTTPException(status_code=400, detail="Choose a configured designation and department.")
    emp_id = body.employee_id.strip().upper()
    if await S.db.users.find_one({"company_id": user["company_id"], "employee_id": emp_id, "id": {"$ne": uid}}):
        raise HTTPException(status_code=409, detail=f"Employee ID {emp_id} is already in use.")
    if body.reporting_manager_id:
        if body.reporting_manager_id == uid:
            raise HTTPException(status_code=400, detail="An employee cannot report to themselves.")
        await S.ensure_company_users([body.reporting_manager_id], user)
    upd = {"employee_id": emp_id, "designation": body.designation, "department": body.department,
           "reporting_manager_id": body.reporting_manager_id}
    if body.name and body.name.strip():
        upd["name"] = body.name.strip()
    if body.phone:
        upd["phone"] = body.phone
    await S.db.users.update_one({"id": uid}, {"$set": upd})
    return S.public_user(await S.db.users.find_one({"id": uid}, {"_id": 0}))


# ---------------------------------------------------------------------------
# Project members & permissions
# ---------------------------------------------------------------------------
class MemberIn(BaseModel):
    responsibility: str = ""
    permissions: Optional[Dict[str, List[str]]] = None
    attendance_required: Optional[bool] = None
    location_required: Optional[bool] = None


@router.get("/projects/{pid}/members")
async def list_members(pid: str, user: dict = Depends(dpr_user)):
    await S.get_project_or_403(pid, user)
    ms = await S.db.project_members.find({"project_id": pid}, {"_id": 0}).to_list(500)
    umap = {u["id"]: S.public_user(u) for u in await S.db.users.find({"id": {"$in": [m["user_id"] for m in ms]}}, {"_id": 0}).to_list(500)}
    return [{**m, "user": umap.get(m["user_id"])} for m in ms]


@router.get("/projects/{pid}/my-permissions")
async def my_permissions(pid: str, user: dict = Depends(dpr_user)):
    project = await S.get_project_or_403(pid, user)
    return {"permissions": await perms_for(user, project), "manages": _manages(user, project),
            "modules": PERM_MODULES, "module_labels": MODULE_LABELS, "actions": ACTIONS, "presets": ROLE_PRESETS, "default_preset": DEFAULT_PRESET,
            "store_staff": user["role"] in {"store_incharge", "store_manager", "admin"}}


@router.put("/projects/{pid}/members/{uid}")
async def upsert_member(pid: str, uid: str, body: MemberIn, user: dict = Depends(dpr_user)):
    project = await S.get_project_or_403(pid, user)
    if not _manages(user, project):
        raise HTTPException(status_code=403, detail="Only the company admin or this project's manager can manage members.")
    target = await S.db.users.find_one({"id": uid, "company_id": user["company_id"]}, {"_id": 0})
    if not target or target["role"] == "client":
        raise HTTPException(status_code=400, detail="Only company employees can be project members.")
    existing = await S.db.project_members.find_one({"project_id": pid, "user_id": uid})
    if body.permissions is not None:
        perms, v2 = _clean_perms(body.permissions), True
    else:
        perms, v2 = (existing or {}).get("permissions") or dict(ROLE_PRESETS.get(target["role"], DEFAULT_PRESET)), (existing or {}).get("access_v2", True)
    doc = {"project_id": pid, "user_id": uid, "company_id": user["company_id"], "responsibility": body.responsibility,
           "permissions": perms, "access_v2": v2, "updated_by": user["id"], "updated_at": S.now_iso(),
           "attendance_required": body.attendance_required if body.attendance_required is not None else (existing or {}).get("attendance_required", False),
           "location_required": body.location_required if body.location_required is not None else (existing or {}).get("location_required", False)}
    await S.db.project_members.update_one({"project_id": pid, "user_id": uid}, {"$set": doc, "$setOnInsert": {"created_at": S.now_iso()}}, upsert=True)
    await S.log_audit(pid, user, "updated member permissions" if existing else "added project member", "member", uid,
                      f"{target['name']}: {json.dumps(perms)}")
    if not existing:
        await S.notify(uid, "assignment", f"You were added to project {project['name']}.", pid)
    return doc


@router.delete("/projects/{pid}/members/{uid}")
async def remove_member(pid: str, uid: str, user: dict = Depends(dpr_user)):
    project = await S.get_project_or_403(pid, user)
    if not _manages(user, project):
        raise HTTPException(status_code=403, detail="Not allowed.")
    res = await S.db.project_members.delete_one({"project_id": pid, "user_id": uid})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Member not found")
    await S.log_audit(pid, user, "removed project member", "member", uid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
class CheckIn(BaseModel):
    note: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None


class Correction(BaseModel):
    check_in: str
    check_out: Optional[str] = None
    reason: str = Field(min_length=3)


def _hours(a):
    if not a.get("check_in") or not a.get("check_out"):
        return 0.0
    d = datetime.fromisoformat(a["check_out"]) - datetime.fromisoformat(a["check_in"])
    return round(max(d.total_seconds(), 0) / 3600, 2)


@router.post("/projects/{pid}/attendance/check-in")
async def check_in(pid: str, body: CheckIn, user: dict = Depends(commercial_user)):
    await require_perm(user, pid, "attendance", "create")
    now = datetime.now(timezone.utc)
    day = now.astimezone(IST).date().isoformat()
    if await S.db.attendance.find_one({"project_id": pid, "user_id": user["id"], "date": day}):
        raise HTTPException(status_code=400, detail="You have already checked in today for this project.")
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, "user_id": user["id"],
           "user_name": user["name"], "date": day, "check_in": now.isoformat(), "check_out": None,
           "note": body.note, "lat": body.lat, "lng": body.lng, "source": "web", "corrected": False,
           "history": [{"action": "check_in", "by": user["name"], "at": now.isoformat()}], "created_at": now.isoformat()}
    await S.db.attendance.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/projects/{pid}/attendance/check-out")
async def check_out(pid: str, user: dict = Depends(commercial_user)):
    await require_perm(user, pid, "attendance", "create")
    now = datetime.now(timezone.utc)
    day = now.astimezone(IST).date().isoformat()
    a = await S.db.attendance.find_one({"project_id": pid, "user_id": user["id"], "date": day}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=400, detail="Please check in first.")
    if a.get("check_out"):
        raise HTTPException(status_code=400, detail="You have already checked out today.")
    await S.db.attendance.update_one({"id": a["id"]}, {"$set": {"check_out": now.isoformat()},
                                                       "$push": {"history": {"action": "check_out", "by": user["name"], "at": now.isoformat()}}})
    return await S.db.attendance.find_one({"id": a["id"]}, {"_id": 0})


async def _attendance_rows(pid, user, perms, month, user_id):
    q = {"project_id": pid, "company_id": user["company_id"]}
    if month:
        q["date"] = {"$regex": f"^{month}"}
    if "view" not in perms.get("attendance", []):
        q["user_id"] = user["id"]
    elif user_id:
        q["user_id"] = user_id
    rows = await S.db.attendance.find(q, {"_id": 0}).sort([("date", -1), ("user_name", 1)]).to_list(5000)
    for r in rows:
        r["hours"] = _hours(r)
    return rows


@router.get("/projects/{pid}/attendance")
async def list_attendance(pid: str, month: Optional[str] = None, user_id: Optional[str] = None, user: dict = Depends(commercial_user)):
    project = await S.get_project_or_403(pid, user)
    perms = await perms_for(user, project)
    return await _attendance_rows(pid, user, perms, month, user_id)


@router.get("/projects/{pid}/attendance/summary")
async def attendance_summary(pid: str, month: str = Query(..., pattern=r"^\d{4}-\d{2}$"), user: dict = Depends(commercial_user)):
    _, perms = await require_perm(user, pid, "attendance", "view")
    rows = await _attendance_rows(pid, user, perms, month, None)
    per = {}
    for r in rows:
        p = per.setdefault(r["user_id"], {"user_id": r["user_id"], "name": r["user_name"], "days": 0, "hours": 0.0, "corrections": 0})
        p["days"] += 1
        p["hours"] = round(p["hours"] + r["hours"], 2)
        p["corrections"] += 1 if r.get("corrected") else 0
    today = datetime.now(IST).date().isoformat()
    return {"month": month, "people": sorted(per.values(), key=lambda x: x["name"]),
            "person_days": len(rows), "total_hours": round(sum(r["hours"] for r in rows), 2),
            "today_present": await S.db.attendance.count_documents({"project_id": pid, "date": today})}


@router.post("/attendance/{aid}/correct")
async def correct_attendance(aid: str, body: Correction, user: dict = Depends(commercial_user)):
    a = await S.db.attendance.find_one({"id": aid, "company_id": user["company_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    await require_perm(user, a["project_id"], "attendance", "approve")
    try:
        ci = datetime.fromisoformat(body.check_in)
        co = datetime.fromisoformat(body.check_out) if body.check_out else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format.")
    if co and co < ci:
        raise HTTPException(status_code=400, detail="Check-out must be after check-in.")
    ts = S.now_iso()
    await S.db.attendance.update_one({"id": aid}, {"$set": {"check_in": ci.isoformat(), "check_out": co.isoformat() if co else None, "corrected": True},
                                                   "$push": {"history": {"action": "correction", "by": user["name"], "at": ts, "reason": body.reason,
                                                                         "before": {"check_in": a["check_in"], "check_out": a.get("check_out")}}}})
    await S.log_audit(a["project_id"], user, "corrected attendance", "attendance", aid, f"{a['user_name']} {a['date']}: {body.reason}")
    return await S.db.attendance.find_one({"id": aid}, {"_id": 0})


@router.get("/projects/{pid}/attendance/export")
async def export_attendance(pid: str, request: Request, month: str = Query(..., pattern=r"^\d{4}-\d{2}$"), auth: str = Query(None)):
    user = await S.user_from_query_token(request, auth)
    _commercial(user)
    project, perms = await require_perm(user, pid, "attendance", "export")
    rows = await _attendance_rows(pid, user, perms, month, None)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Employee", "Check-in (IST)", "Check-out (IST)", "Hours", "Corrected", "Note"])
    fmt = lambda v: datetime.fromisoformat(v).astimezone(IST).strftime("%H:%M") if v else ""  # noqa: E731
    for r in rows:
        w.writerow([r["date"], r["user_name"], fmt(r["check_in"]), fmt(r.get("check_out")), r["hours"], "yes" if r.get("corrected") else "", r.get("note", "")])
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="attendance_{project.get("code")}_{month}.csv"'})


# ---------------------------------------------------------------------------
# Daily Progress Reports
# ---------------------------------------------------------------------------
class DprActivity(BaseModel):
    activity_id: Optional[str] = None
    description: str
    unit: str = ""
    planned_qty: float = 0
    actual_qty: float = 0
    planned_pct: float = 0
    actual_pct: float = 0


class DprCount(BaseModel):
    name: str
    count: float = 0
    hours: float = 0


class DprMaterial(BaseModel):
    item: str
    quantity: float = 0
    unit: str = ""
    status: str = "received"  # received | delayed
    note: str = ""


class DprPhoto(BaseModel):
    file_id: str
    caption: str = ""


class DprBoqEntry(BaseModel):
    boq_id: str
    qty: float = Field(gt=0)
    location: str = ""
    remarks: str = ""


class DprIn(BaseModel):
    boq_entries: List[DprBoqEntry] = []
    report_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    weather: str = ""
    activities: List[DprActivity] = []
    manpower: List[DprCount] = []
    equipment: List[DprCount] = []
    materials: List[DprMaterial] = []
    photos: List[DprPhoto] = []
    quality_notes: str = ""
    safety_notes: str = ""
    delays: str = ""
    next_day_plan: str = ""


class DprReview(BaseModel):
    action: str  # approve | return | reject
    comment: str = ""


async def _validate_dpr(pid, body: DprIn):
    if any(m.status not in {"received", "delayed"} for m in body.materials):
        raise HTTPException(status_code=400, detail="Material status must be received or delayed.")
    fids = [p.file_id for p in body.photos]
    if fids and await S.db.files.count_documents({"id": {"$in": fids}, "project_id": pid, "is_deleted": False}) != len(set(fids)):
        raise HTTPException(status_code=400, detail="Photos must be uploaded to this project.")
    data = body.model_dump()
    data.pop("report_date")
    import store
    data["boq_entries"] = await store.annotate_boq_entries(pid, data["boq_entries"])
    return data


async def _get_dpr(did, user):
    d = await S.db.dprs.find_one({"id": did, "company_id": user["company_id"]}, {"_id": 0})
    if not d or (user["role"] == "client" and d["status"] != "approved"):
        raise HTTPException(status_code=404, detail="DPR not found")
    return d


@router.get("/projects/{pid}/dprs")
async def list_dprs(pid: str, user: dict = Depends(dpr_user)):
    await require_perm(user, pid, "dpr", "view")
    q = {"project_id": pid, **({"status": "approved"} if user["role"] == "client" else {})}
    return await S.db.dprs.find(q, {"_id": 0, "history": 0}).sort("report_date", -1).to_list(1000)


@router.post("/projects/{pid}/dprs")
async def create_dpr(pid: str, body: DprIn, user: dict = Depends(dpr_user)):
    await require_perm(user, pid, "dpr", "create")
    if await S.db.dprs.find_one({"project_id": pid, "report_date": body.report_date}):
        raise HTTPException(status_code=409, detail="A DPR already exists for this project and date.")
    data = await _validate_dpr(pid, body)
    ts = S.now_iso()
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, "report_date": body.report_date, **data,
           "status": "draft", "created_by": user["id"], "created_by_name": user["name"], "review_comment": None,
           "reviewed_by": None, "created_at": ts, "updated_at": ts,
           "history": [{"status": "draft", "by": user["name"], "at": ts, "comment": ""}]}
    await S.db.dprs.insert_one(doc)
    await S.log_audit(pid, user, "created DPR", "dpr", doc["id"], body.report_date)
    doc.pop("_id", None)
    return doc


@router.get("/dprs/{did}")
async def get_dpr(did: str, user: dict = Depends(dpr_user)):
    d = await _get_dpr(did, user)
    await require_perm(user, d["project_id"], "dpr", "view")
    files = await S.db.files.find({"id": {"$in": [p["file_id"] for p in d.get("photos", [])]}}, {"_id": 0}).to_list(100)
    d["photo_files"] = files
    return d


@router.put("/dprs/{did}")
async def update_dpr(did: str, body: DprIn, user: dict = Depends(dpr_user)):
    d = await _get_dpr(did, user)
    await require_perm(user, d["project_id"], "dpr", "edit")
    if d["status"] not in {"draft", "returned"}:
        raise HTTPException(status_code=400, detail="Only draft or returned DPRs can be edited.")
    if body.report_date != d["report_date"] and await S.db.dprs.find_one({"project_id": d["project_id"], "report_date": body.report_date}):
        raise HTTPException(status_code=409, detail="A DPR already exists for this project and date.")
    data = await _validate_dpr(d["project_id"], body)
    await S.db.dprs.update_one({"id": did}, {"$set": {**data, "report_date": body.report_date, "updated_at": S.now_iso()}})
    return await get_dpr(did, user)


@router.delete("/dprs/{did}")
async def delete_dpr(did: str, user: dict = Depends(dpr_user)):
    d = await _get_dpr(did, user)
    await require_perm(user, d["project_id"], "dpr", "delete")
    if d["status"] != "draft":
        raise HTTPException(status_code=400, detail="Only drafts can be deleted.")
    await S.db.dprs.delete_one({"id": did})
    await S.log_audit(d["project_id"], user, "deleted DPR draft", "dpr", did, d["report_date"])
    return {"ok": True}


@router.post("/dprs/{did}/submit")
async def submit_dpr(did: str, user: dict = Depends(dpr_user)):
    d = await _get_dpr(did, user)
    project, _ = await require_perm(user, d["project_id"], "dpr", "submit")
    if d["status"] not in {"draft", "returned"}:
        raise HTTPException(status_code=400, detail="This DPR has already been submitted.")
    ts = S.now_iso()
    await S.db.dprs.update_one({"id": did}, {"$set": {"status": "submitted", "submitted_at": ts},
                                             "$push": {"history": {"status": "submitted", "by": user["name"], "at": ts, "comment": ""}}})
    await S.log_audit(d["project_id"], user, "submitted DPR", "dpr", did, d["report_date"])
    for rid in await recipients_with(project, "dpr", "approve", exclude=user["id"]):
        await S.notify(rid, "dpr_review", f"DPR for {d['report_date']} submitted for approval — {project['name']}.",
                       d["project_id"], link=f"/projects/{d['project_id']}?tab=dpr&dpr={did}", dedupe_key=f"dpr-sub-{did}-{ts}", push=True)
    return await get_dpr(did, user)


@router.post("/dprs/{did}/review")
async def review_dpr(did: str, body: DprReview, user: dict = Depends(dpr_user)):
    d = await _get_dpr(did, user)
    project, _ = await require_perm(user, d["project_id"], "dpr", "approve")
    if d["status"] != "submitted":
        raise HTTPException(status_code=400, detail="This DPR is not awaiting review.")
    if d["created_by"] == user["id"]:
        raise HTTPException(status_code=403, detail="You cannot review your own DPR.")
    mapping = {"approve": "approved", "return": "returned", "reject": "rejected"}
    if body.action not in mapping:
        raise HTTPException(status_code=400, detail="Invalid action.")
    if body.action == "approve" and any(e.get("excess") for e in d.get("boq_entries", [])) and not body.comment.strip():
        raise HTTPException(status_code=400, detail="This DPR has quantities exceeding the approved BOQ. Add a review comment to approve the excess.")
    if body.action != "approve" and not body.comment.strip():
        raise HTTPException(status_code=400, detail="Please add a comment for the engineer.")
    st, ts = mapping[body.action], S.now_iso()
    res = await S.db.dprs.update_one({"id": did, "status": "submitted"}, {"$set": {"status": st, "review_comment": body.comment, "reviewed_by": user["id"],
                                                      "reviewed_by_name": user["name"], "reviewed_at": ts},
                                             "$push": {"history": {"status": st, "by": user["name"], "at": ts, "comment": body.comment}}})
    if not res.modified_count:
        raise HTTPException(status_code=409, detail="This DPR was already reviewed.")
    if st == "approved" and d.get("boq_entries"):
        import store
        await store.apply_boq(d["project_id"], d["boq_entries"])
    await S.log_audit(d["project_id"], user, f"DPR {st}", "dpr", did, f"{d['report_date']}: {body.comment}")
    msg = {"approved": "approved", "returned": "returned for correction", "rejected": "rejected"}[st]
    await S.notify(d["created_by"], "dpr_decision", f"Your DPR for {d['report_date']} was {msg}.", d["project_id"],
                   link=f"/projects/{d['project_id']}?tab=dpr&dpr={did}", push=True)
    if st == "approved":
        ids = set(project.get("engineer_ids", [])) | {m["user_id"] async for m in S.db.project_members.find({"project_id": d["project_id"]}, {"user_id": 1})}
        ids -= {user["id"], d["created_by"]}
        for uid in ids:
            await S.notify(uid, "site_update", f"New site report published: DPR {d['report_date']} — {project['name']}.",
                           d["project_id"], link=f"/projects/{d['project_id']}?tab=dpr&dpr={did}", dedupe_key=f"dpr-pub-{did}", push=True)
    return await get_dpr(did, user)


async def _day_photos(d, exclude, limit):
    """Project images uploaded on the DPR date (IST) by the site team, not already attached."""
    if limit <= 0:
        return []
    day = datetime.fromisoformat(d["report_date"]).replace(tzinfo=IST)
    lo, hi = day.astimezone(timezone.utc).isoformat(), (day + timedelta(days=1)).astimezone(timezone.utc).isoformat()
    team = await S.db.users.find({"company_id": d["company_id"], "role": {"$ne": "client"}}, {"_id": 0, "id": 1}).to_list(2000)
    q = {"project_id": d["project_id"], "is_deleted": False, "content_type": {"$regex": "^image/"}, "created_at": {"$gte": lo, "$lt": hi},
         "id": {"$nin": list(exclude)}, "uploaded_by": {"$in": [u["id"] for u in team]}}
    out = await S.db.files.find(q, {"_id": 0}).sort("created_at", 1).to_list(limit)
    if out and d["status"] == "approved" and not d.get("auto_photo_ids"):
        await S.db.dprs.update_one({"id": d["id"]}, {"$set": {"auto_photo_ids": [f["id"] for f in out]}})
    return out


@router.get("/dprs/{did}/pdf")
async def dpr_pdf(did: str, request: Request, auth: str = Query(None)):
    user = await S.user_from_query_token(request, auth)
    _dpr_ok(user)
    d = await _get_dpr(did, user)
    project, _ = await require_perm(user, d["project_id"], "dpr", "view")
    files = await S.db.files.find({"id": {"$in": [p["file_id"] for p in d.get("photos", [])]}, "is_deleted": False}, {"_id": 0}).to_list(20)
    files += await _day_photos(d, {f["id"] for f in files}, 12 - len(files))
    cap = {p["file_id"]: p.get("caption") for p in d.get("photos", [])}
    got = await asyncio.gather(*[asyncio.to_thread(S.storage.get_object, f["storage_path"]) for f in files[:9]], return_exceptions=True)
    photos = [(g[0], cap.get(f["id"]) or f.get("original_filename"), f.get("created_at")) for f, g in zip(files, got) if not isinstance(g, Exception)]
    meta = {"title": "Daily Progress Report", "code": f"{project.get('code', '')} · {d['report_date']}",
            "generated": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"), "revision": d["status"].upper(),
            "confidential": f"Confidential — {user['_enterprise'].get('display_name') or user['_enterprise']['name']}"}
    d["labour"] = await S.db.labour_attendance.find({"project_id": d["project_id"], "date": d["report_date"]}, {"_id": 0}).to_list(50)
    boq = {b["id"]: b for b in await S.db.boq_items.find({"project_id": d["project_id"]}, {"_id": 0}).to_list(2000)}
    for e in d.get("boq_entries", []):
        e["cumulative_now"] = boq.get(e["boq_id"], {}).get("accepted_qty", 0)
    pdf = reports_module.build_dpr(project, d, photos, meta, S.report_brand(user["_enterprise"]))
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="DPR_{project.get("code")}_{d["report_date"]}.pdf"'})


# ---------------------------------------------------------------------------
# Web push
# ---------------------------------------------------------------------------
class PushSub(BaseModel):
    endpoint: str
    keys: Dict[str, str]


def _webpush(sub, payload):
    from pywebpush import webpush
    webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]}, data=json.dumps(payload),
            vapid_private_key=os.environ["VAPID_PRIVATE_KEY"], vapid_claims={"sub": os.environ["VAPID_SUBJECT"]}, ttl=86400)


async def send_push(user_ids, title, body, url, category):
    subs = await S.db.push_subscriptions.find({"user_id": {"$in": list(user_ids)}}, {"_id": 0}).to_list(200)
    for sub in subs:
        status, err = "sent", None
        try:
            await asyncio.to_thread(_webpush, sub, {"title": title, "body": body, "url": url, "tag": category})
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            status, err = "failed", f"{code or ''} {str(e)[:200]}"
            if code in (404, 410):
                await S.db.push_subscriptions.delete_one({"endpoint": sub["endpoint"]})
                status = "expired_removed"
            log.warning(f"push failed for user {sub['user_id']}: {status}")
        await S.db.push_logs.insert_one({"id": S.new_id(), "user_id": sub["user_id"], "category": category, "status": status,
                                         "error": err, "url": url, "created_at": S.now_iso()})


@router.get("/push/public-key")
async def push_key():
    return {"public_key": os.environ["VAPID_PUBLIC_KEY"]}


@router.post("/push/subscribe")
async def push_subscribe(body: PushSub, request: Request, user: dict = Depends(S.get_current_user)):
    if not body.endpoint.startswith("https://") or not {"p256dh", "auth"} <= set(body.keys):
        raise HTTPException(status_code=400, detail="Invalid push subscription.")
    await S.db.push_subscriptions.update_one({"endpoint": body.endpoint}, {"$set": {
        "endpoint": body.endpoint, "keys": body.keys, "user_id": user["id"], "company_id": user["company_id"],
        "user_agent": request.headers.get("user-agent", "")[:200], "updated_at": S.now_iso()}}, upsert=True)
    return {"ok": True, "devices": await S.db.push_subscriptions.count_documents({"user_id": user["id"]})}


@router.post("/push/unsubscribe")
async def push_unsubscribe(body: PushSub, user: dict = Depends(S.get_current_user)):
    await S.db.push_subscriptions.delete_one({"endpoint": body.endpoint, "user_id": user["id"]})
    return {"ok": True}


@router.get("/push/status")
async def push_status(user: dict = Depends(S.get_current_user)):
    logs = await S.db.push_logs.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(10)
    return {"devices": await S.db.push_subscriptions.count_documents({"user_id": user["id"]}), "recent": logs}


@router.post("/push/test")
async def push_test(user: dict = Depends(S.get_current_user)):
    await send_push([user["id"]], "CIVIO", "Push notifications are working on this device.", "/notifications", "test")
    return await push_status(user)


# ---------------------------------------------------------------------------
# Weekly digest
# ---------------------------------------------------------------------------
class DigestSettingsIn(BaseModel):
    enabled: bool = True
    day_of_week: int = Field(ge=0, le=6)  # 0 = Monday
    hour: int = Field(ge=0, le=23)
    timezone: str = "Asia/Kolkata"
    recipient_ids: List[str] = []
    extra_emails: List[str] = []


async def _digest_settings(cid):
    s = await S.db.digest_settings.find_one({"company_id": cid}, {"_id": 0})
    return s or {"company_id": cid, "enabled": True, "day_of_week": 0, "hour": 9, "timezone": "Asia/Kolkata", "recipient_ids": []}


@router.get("/digest/settings")
async def get_digest_settings(user: dict = Depends(commercial_user)):
    if user["role"] not in {"admin", "project_manager"}:
        raise HTTPException(status_code=403, detail="Only an admin can configure the weekly digest.")
    return await _digest_settings(user["company_id"])


@router.put("/digest/settings")
async def put_digest_settings(body: DigestSettingsIn, user: dict = Depends(commercial_user)):
    if user["role"] not in {"admin", "project_manager"}:
        raise HTTPException(status_code=403, detail="Only an admin can configure the weekly digest.")
    try:
        ZoneInfo(body.timezone)
    except Exception:
        raise HTTPException(status_code=400, detail="Unknown timezone.")
    if body.recipient_ids:
        n = await S.db.users.count_documents({"id": {"$in": body.recipient_ids}, "company_id": user["company_id"], "role": {"$in": list(S.MANAGER_ROLES)}})
        if n != len(set(body.recipient_ids)):
            raise HTTPException(status_code=400, detail="Recipients must be admins or project managers of your company.")
    emails = sorted({e.strip().lower() for e in body.extra_emails if e.strip()})
    if any(not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) for e in emails):
        raise HTTPException(status_code=400, detail="One of the email addresses is not valid.")
    doc = {**body.model_dump(), "extra_emails": emails[:30], "company_id": user["company_id"], "updated_by": user["name"]}
    await S.db.digest_settings.update_one({"company_id": user["company_id"]}, {"$set": doc}, upsert=True)
    return doc


@router.get("/digest/logs")
async def digest_logs(user: dict = Depends(commercial_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed.")
    return await S.db.digest_logs.find({"company_id": user["company_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)


@router.post("/digest/send-now")
async def digest_send_now(user: dict = Depends(commercial_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed.")
    key = f"manual-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
    asyncio.create_task(run_digest(user["_enterprise"], key, "manual"))
    return {"queued": True, "key": key}


def _planned_pct(a, today):
    try:
        s, e = datetime.fromisoformat(a["planned_start"]), datetime.fromisoformat(a["planned_end"])
        tot = (e - s).total_seconds()
        return round(min(max((today - s).total_seconds() / tot, 0), 1) * 100, 1) if tot > 0 else None
    except Exception:
        return None


async def build_digest(ent):
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=7)).isoformat()
    since_day = (now - timedelta(days=7)).astimezone(IST).date().isoformat()
    out = []
    async for p in S.db.projects.find({"company_id": ent["id"], "is_archived": {"$ne": True}}, {"_id": 0}):
        pid = p["id"]
        acts = await S.db.activities.find({"project_id": pid}, {"_id": 0}).to_list(500)
        for a in acts:
            a["_planned"] = _planned_pct(a, now)
        pus = await S.db.progress_updates.find({"project_id": pid, "created_at": {"$gte": since}}, {"_id": 0}).to_list(500)
        dprs = await S.db.dprs.find({"project_id": pid, "report_date": {"$gte": since_day}}, {"_id": 0}).to_list(50)
        out.append({
            "project": p,
            "completed": [a["name"] for a in acts if a.get("status") == "completed"],
            "behind": [(a["name"], a["_planned"], a.get("progress_percent", 0)) for a in acts if a["_planned"] is not None and a.get("progress_percent", 0) + 5 < a["_planned"]],
            "person_days": await S.db.attendance.count_documents({"project_id": pid, "date": {"$gte": since_day}}),
            "approved_updates": sum(1 for u in pus if u["status"] == "approved"),
            "photos": await S.db.files.count_documents({"project_id": pid, "created_at": {"$gte": since}, "is_deleted": False}),
            "dprs": len(dprs),
            "open_defects": await S.db.defects.count_documents({"project_id": pid, "status": {"$ne": "closed"}}),
            "critical_defects": await S.db.defects.count_documents({"project_id": pid, "status": {"$ne": "closed"}, "severity": "critical"}),
            "safety": [d["safety_notes"] for d in dprs if d.get("safety_notes")][:3],
            "quality": [d["quality_notes"] for d in dprs if d.get("quality_notes")][:3],
            "material_delays": [m["item"] for d in dprs for m in d.get("materials", []) if m.get("status") == "delayed"],
            "pending": {
                "progress_reviews": await S.db.progress_updates.count_documents({"project_id": pid, "status": "submitted"}),
                "client_decisions": await S.db.progress_updates.count_documents({"project_id": pid, "status": "pending_client_decision"}),
                "material_requests": await S.db.material_requests.count_documents({"project_id": pid, "status": "requested"}),
                "dprs": await S.db.dprs.count_documents({"project_id": pid, "status": "submitted"}),
            },
            "upcoming": [m["name"] + " (" + (m.get("due_date") or "")[:10] + ")" for m in await S.db.milestones.find(
                {"project_id": pid, "status": {"$ne": "completed"}, "due_date": {"$lte": (now + timedelta(days=14)).isoformat()}}, {"_id": 0}).to_list(20)],
            "next_plan": next((d["next_day_plan"] for d in sorted(dprs, key=lambda x: x["report_date"], reverse=True) if d.get("next_day_plan")), ""),
        })
    return out


async def run_digest(ent, key, trigger):
    if await S.db.digest_logs.find_one({"company_id": ent["id"], "key": key}):
        return
    log_doc = {"id": S.new_id(), "company_id": ent["id"], "key": key, "trigger": trigger, "status": "running",
               "recipients": [], "created_at": S.now_iso()}
    try:
        await S.db.digest_logs.insert_one(dict(log_doc))
    except Exception:
        return  # duplicate (unique index)
    try:
        settings = await _digest_settings(ent["id"])
        q = {"company_id": ent["id"], "is_active": {"$ne": False}, "role": {"$in": list(S.MANAGER_ROLES)}}
        if settings.get("recipient_ids"):
            q["id"] = {"$in": settings["recipient_ids"]}
        users = await S.db.users.find(q, {"_id": 0, "email": 1, "name": 1}).to_list(200)
        known = {u["email"].lower() for u in users}
        users += [{"email": e, "name": e.split("@")[0]} for e in settings.get("extra_emails", []) if e not in known]
        data = await build_digest(ent)
        name = ent.get("display_name") or ent["name"]
        results = []
        for u in users:
            mid = await emailer.send_email(to=u["email"], subject=f"Weekly project digest — {name}",
                                           html=emailer.digest_email_html(u["name"], name, data))
            results.append({"email": u["email"], "ok": bool(mid)})
        status = "sent" if results and all(r["ok"] for r in results) else ("partial" if any(r["ok"] for r in results) else "failed")
        await S.db.digest_logs.update_one({"id": log_doc["id"]}, {"$set": {"status": status, "recipients": results,
                                                                         "projects": len(data), "finished_at": S.now_iso()}})
    except Exception as e:
        log.error(f"digest failed for {ent['id']}: {e}")
        await S.db.digest_logs.update_one({"id": log_doc["id"]}, {"$set": {"status": "failed", "error": str(e)[:300]}})


async def _scheduled_digests():
    now = datetime.now(timezone.utc)
    async for ent in S.db.enterprises.find({"status": "active", "business_type": "commercial"}, {"_id": 0}):
        s = await _digest_settings(ent["id"])
        local = now.astimezone(ZoneInfo(s.get("timezone") or "Asia/Kolkata"))
        if s.get("enabled") and local.weekday() == s["day_of_week"] and local.hour == s["hour"]:
            iso = local.isocalendar()
            await run_digest(ent, f"week-{iso[0]}-{iso[1]:02d}", "scheduled")


@router.post("/cron/weekly-digest")
async def cron_weekly_digest(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    auth = request.headers.get("authorization", "")
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    if not secret or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid body")
    asyncio.create_task(_scheduled_digests())
    return {"accepted": True}
