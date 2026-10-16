"""Commercial Phase 2: role catalogue, role dashboards, weekly engineer BOQ targets, site passes (labour/engineer)."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import server as S
import commercial as C

router = APIRouter()


def _monday(d: Optional[str] = None) -> str:
    day = datetime.fromisoformat(d).date() if d else datetime.now(C.IST).date()
    return (day - timedelta(days=day.weekday())).isoformat()


@router.get("/roles")
async def roles(user: dict = Depends(S.get_current_user)):
    bt = user["_enterprise"].get("business_type")
    keys = [k for k in S.ROLE_NAMES if k != "admin" and (bt == "commercial" or k not in S.COMMERCIAL_ONLY_ROLES)]
    return [{"key": k, "label": S.ROLE_NAMES[k], "approver": S.APPROVER.get(k), "approver_label": S.ROLE_NAMES.get(S.APPROVER.get(k), ""),
             "admin_only": S.APPROVER.get(k) == "admin"} for k in keys]


# ---------------------------------------------------------------------------
# Weekly targets
# ---------------------------------------------------------------------------
class TargetIn(BaseModel):
    engineer_id: str
    boq_id: str
    week_start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    target_qty: float = Field(gt=0)


async def _achieved(pid, eng, week):
    end = (datetime.fromisoformat(week) + timedelta(days=6)).date().isoformat()
    got = {}
    async for d in S.db.dprs.find({"project_id": pid, "created_by": eng, "status": "approved", "report_date": {"$gte": week, "$lte": end}}, {"_id": 0, "boq_entries": 1}):
        for e in d.get("boq_entries", []):
            got[e["boq_id"]] = got.get(e["boq_id"], 0) + e["qty"]
    return got


async def _targets(q):
    rows = await S.db.engineer_targets.find(q, {"_id": 0}).to_list(2000)
    cache = {}
    for t in rows:
        k = (t["project_id"], t["engineer_id"], t["week_start"])
        if k not in cache:
            cache[k] = await _achieved(*k)
        t["achieved_qty"] = round(cache[k].get(t["boq_id"], 0), 3)
        t["met"] = t["achieved_qty"] >= t["target_qty"]
    return rows


@router.get("/projects/{pid}/targets")
async def list_targets(pid: str, week: Optional[str] = Query(None), user: dict = Depends(C.commercial_user)):
    project = await S.get_project_or_403(pid, user)
    q = {"project_id": pid, "week_start": _monday(week)}
    if not C._manages(user, project):
        q["engineer_id"] = user["id"]
    return await _targets(q)


@router.put("/projects/{pid}/targets")
async def set_target(pid: str, body: TargetIn, user: dict = Depends(C.commercial_user)):
    project = await S.get_project_or_403(pid, user)
    if not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Only the project manager or admin can set targets.")
    if body.engineer_id not in project.get("engineer_ids", []):
        raise HTTPException(status_code=400, detail="Choose a site engineer assigned to this project.")
    boq = await S.db.boq_items.find_one({"id": body.boq_id, "project_id": pid}, {"_id": 0})
    if not boq:
        raise HTTPException(status_code=400, detail="Choose an approved BOQ item of this project.")
    week = _monday(body.week_start)
    doc = {"project_id": pid, "company_id": user["company_id"], "engineer_id": body.engineer_id, "boq_id": body.boq_id, "week_start": week,
           "target_qty": body.target_qty, "boq_code": boq["code"], "boq_description": boq["description"], "unit": boq["unit"],
           "set_by": user["id"], "updated_at": S.now_iso()}
    await S.db.engineer_targets.update_one({"project_id": pid, "engineer_id": body.engineer_id, "boq_id": body.boq_id, "week_start": week},
                                           {"$set": doc, "$setOnInsert": {"id": S.new_id()}}, upsert=True)
    await S.log_audit(pid, user, "set weekly target", "target", body.engineer_id, f"{boq['code']} {body.target_qty} {boq['unit']} wk {week}")
    await S.notify(body.engineer_id, "target", f"Weekly target set: {body.target_qty} {boq['unit']} {boq['code']} (week of {week}).", pid,
                   link=f"/projects/{pid}?tab=dpr", dedupe_key=f"tgt-{pid}-{body.boq_id}-{week}")
    return await list_targets(pid, week, user)


@router.delete("/projects/{pid}/targets/{tid}")
async def del_target(pid: str, tid: str, user: dict = Depends(C.commercial_user)):
    project = await S.get_project_or_403(pid, user)
    if not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Not allowed.")
    await S.db.engineer_targets.delete_one({"id": tid, "project_id": pid})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Site passes (labour / engineer) — Pass Coordinator creates, PM approves
# ---------------------------------------------------------------------------
class PassIn(BaseModel):
    pass_type: str
    person_name: str = Field(min_length=1, max_length=80)
    phone: str = Field(default="", max_length=20)
    id_proof: str = Field(default="", max_length=60)
    trade: str = Field(default="", max_length=60)
    valid_from: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    valid_to: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    photo_ids: list = []


class PassDecision(BaseModel):
    action: str
    remarks: str = ""


def _pass_staff(user):
    if user["role"] not in {"pass_coordinator", "admin", "project_manager"}:
        raise HTTPException(status_code=403, detail="Only the Pass Coordinator, PM or admin can manage passes.")


@router.get("/projects/{pid}/passes")
async def list_passes(pid: str, user: dict = Depends(C.commercial_user)):
    await S.get_project_or_403(pid, user)
    return await S.db.site_passes.find({"project_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/projects/{pid}/passes")
async def create_pass(pid: str, body: PassIn, user: dict = Depends(C.commercial_user)):
    _pass_staff(user)
    project = await S.get_project_or_403(pid, user, write=True)
    if body.pass_type not in {"labour", "engineer"} or body.valid_to < body.valid_from:
        raise HTTPException(status_code=400, detail="Pass type must be labour or engineer and validity dates must be in order.")
    if not body.photo_ids or await S.db.files.count_documents({"id": {"$in": body.photo_ids}, "project_id": pid, "is_deleted": False}) != len(set(body.photo_ids)):
        raise HTTPException(status_code=400, detail="A camera photo of the pass holder is required.")
    n = await S.db.site_passes.count_documents({"project_id": pid})
    mgr = C._manages(user, project)
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, **body.model_dump(),
           "pass_no": f"{project.get('code', 'P')}-{'L' if body.pass_type == 'labour' else 'E'}{n + 1:04d}",
           "status": "active" if mgr else "pending", "created_by": user["id"], "created_by_name": user["name"], "created_at": S.now_iso(),
           "approved_by_name": user["name"] if mgr else None}
    await S.db.site_passes.insert_one(doc)
    doc.pop("_id", None)
    await S.log_audit(pid, user, "created site pass", "pass", doc["id"], f"{doc['pass_no']} {body.person_name}")
    if not mgr and project.get("project_manager_id"):
        await S.notify(project["project_manager_id"], "pass", f"Site pass {doc['pass_no']} for {body.person_name} awaits approval.", pid,
                       link=f"/projects/{pid}?tab=passes", push=True)
    return doc


@router.post("/passes/{xid}/decision")
async def decide_pass(xid: str, body: PassDecision, user: dict = Depends(C.commercial_user)):
    p = await S.db.site_passes.find_one({"id": xid, "company_id": user["company_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Pass not found")
    project = await S.get_project_or_403(p["project_id"], user)
    flow = {"approve": ("pending", "active"), "reject": ("pending", "rejected"), "revoke": ("active", "revoked")}
    if body.action not in flow or p["status"] != flow[body.action][0]:
        raise HTTPException(status_code=400, detail="Invalid action for this pass.")
    if body.action != "revoke" and not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Only the project manager approves passes.")
    if body.action == "revoke":
        _pass_staff(user)
    st = flow[body.action][1]
    await S.db.site_passes.update_one({"id": xid}, {"$set": {"status": st, "decision_remarks": body.remarks, "approved_by_name": user["name"], "decided_at": S.now_iso()}})
    await S.log_audit(p["project_id"], user, f"site pass {st}", "pass", xid, f"{p['pass_no']} {body.remarks}")
    await S.notify(p["created_by"], "pass", f"Site pass {p['pass_no']} is now {st}.", p["project_id"], link=f"/projects/{p['project_id']}?tab=passes")
    return {"ok": True, "status": st}


# ---------------------------------------------------------------------------
# Role dashboard
# ---------------------------------------------------------------------------
@router.get("/dashboard/role")
async def role_dashboard(user: dict = Depends(C.commercial_user)):
    role, uid, cid = user["role"], user["id"], user["company_id"]
    pids = [p["id"] for p in await S.list_projects(user)]
    n = S.db.store_requests.count_documents
    cards = []
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    if role in {"admin", "project_manager"}:
        cards += [{"key": "store_approve", "label": "Store requests to approve", "count": await n({"project_id": {"$in": pids}, "status": "requested"})},
                  {"key": "return_approve", "label": "Tool returns to approve", "count": await n({"project_id": {"$in": pids}, "pending_return.stage": "awaiting_pm"})},
                  {"key": "dpr_review", "label": "DPRs to review", "count": await S.db.dprs.count_documents({"project_id": {"$in": pids}, "status": "submitted"})},
                  {"key": "passes", "label": "Site passes to approve", "count": await S.db.site_passes.count_documents({"project_id": {"$in": pids}, "status": "pending"})}]
    if role in {"admin", "store_incharge", "store_manager"}:
        cards += [{"key": "to_issue", "label": "Approved requests to issue", "count": await n({"project_id": {"$in": pids}, "status": {"$in": ["approved", "partially_issued"]}})},
                  {"key": "return_receive", "label": "Returns to verify", "count": await n({"project_id": {"$in": pids}, "pending_return.stage": "awaiting_store"})},
                  {"key": "shortage", "label": "Stock shortages", "count": await n({"company_id": cid, "status": "shortage"}), "alert": True},
                  {"key": "tools_out", "label": "Tools out > 7 days", "count": await n({"project_id": {"$in": pids}, "kind": "tool", "status": {"$in": ["issued", "partially_issued", "partially_returned"]}, "issued_at": {"$lt": week_ago}}), "alert": True}]
    if role == "site_engineer":
        cards += [{"key": "my_requests", "label": "My open store requests", "count": await n({"requested_by": uid, "status": {"$in": ["requested", "approved", "partially_issued", "shortage"]}})},
                  {"key": "my_dprs", "label": "My DPRs returned for correction", "count": await S.db.dprs.count_documents({"created_by": uid, "status": "returned"})}]
    if role == "pass_coordinator":
        cards += [{"key": "pass_active", "label": "Active passes", "count": await S.db.site_passes.count_documents({"company_id": cid, "status": "active"})},
                  {"key": "pass_pending", "label": "Passes awaiting PM", "count": await S.db.site_passes.count_documents({"company_id": cid, "status": "pending", "created_by": uid})}]
    q = {"project_id": {"$in": pids}, "week_start": _monday()}
    if role == "site_engineer":
        q["engineer_id"] = uid
    targets = await _targets(q) if role in {"admin", "project_manager", "site_engineer"} else []
    names = {u["id"]: u["name"] async for u in S.db.users.find({"id": {"$in": list({t["engineer_id"] for t in targets})}}, {"_id": 0, "id": 1, "name": 1})}
    for t in targets:
        t["engineer_name"] = names.get(t["engineer_id"])
    return {"role": role, "role_label": S.ROLE_NAMES.get(role, role), "approver_label": S.ROLE_NAMES.get(S.APPROVER.get(role), ""),
            "cards": cards, "targets": targets, "week_start": _monday()}
