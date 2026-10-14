"""Commercial: store in-charge (material/tool requests, issue/return, inventory), BOQ, labour attendance."""
import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import server as S
import commercial as C

router = APIRouter()


async def _photos_ok(pid, ids):
    if not ids:
        raise HTTPException(status_code=400, detail="A photo is required for this transaction.")
    if await S.db.files.count_documents({"id": {"$in": ids}, "project_id": pid, "is_deleted": False}) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Photos must be uploaded to this project.")


def _hist(user, status, note=""):
    return {"status": status, "by": user["name"], "at": S.now_iso(), "note": note}


# ---------------------------------------------------------------------------
# Store requests & inventory (quantities only — no pricing)
# ---------------------------------------------------------------------------
class StoreReqIn(BaseModel):
    kind: str  # material | tool
    item: str = Field(min_length=1)
    quantity: float = Field(gt=0)
    unit: str = "nos"
    required_date: Optional[str] = None
    expected_return: Optional[str] = None
    remarks: str = ""


class DecisionIn(BaseModel):
    action: str
    comment: str = ""


class IssueIn(BaseModel):
    quantity: float = Field(gt=0)
    photo_ids: List[str]
    responsible_person: str = Field(min_length=1)
    note: str = ""


class ReturnIn(BaseModel):
    good: float = Field(ge=0)
    damaged: float = Field(ge=0, default=0)
    lost: float = Field(ge=0, default=0)
    photo_ids: List[str]
    responsible_person: str = Field(min_length=1)
    note: str = ""


class ReceiveIn(BaseModel):
    kind: str
    item: str = Field(min_length=1)
    unit: str = "nos"
    quantity: float = Field(gt=0)
    photo_ids: List[str]
    responsible_person: str = Field(min_length=1)
    note: str = ""


def _key(item):
    return " ".join(item.lower().split())


async def _txn(user, pid, ttype, item, kind, qty, photo_ids, person, request_id=None, extra=None):
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, "type": ttype, "item": item, "kind": kind,
           "quantity": qty, "photo_ids": photo_ids, "responsible_person": person, "request_id": request_id,
           "by": user["id"], "by_name": user["name"], "at": S.now_iso(), **(extra or {})}
    await S.db.store_txns.insert_one(doc)
    await S.log_audit(pid, user, f"store {ttype}", "store", doc["id"], f"{qty} {item}")


@router.get("/projects/{pid}/store/requests")
async def list_store_requests(pid: str, user: dict = Depends(C.commercial_user)):
    _, perms = await C.require_perm(user, pid, "store", "view")
    q = {"project_id": pid}
    if "approve" not in perms.get("store", []):
        q["requested_by"] = user["id"]
    return await S.db.store_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/projects/{pid}/store/requests")
async def create_store_request(pid: str, body: StoreReqIn, user: dict = Depends(C.commercial_user)):
    project, _ = await C.require_perm(user, pid, "store", "create")
    if body.kind not in {"material", "tool"}:
        raise HTTPException(status_code=400, detail="Kind must be material or tool.")
    if body.kind == "tool" and not body.expected_return:
        raise HTTPException(status_code=400, detail="Tool requests need an expected return date.")
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, **body.model_dump(), "status": "requested",
           "requested_by": user["id"], "requested_by_name": user["name"], "issued_qty": 0, "returned_qty": 0, "damaged_qty": 0,
           "lost_qty": 0, "created_at": S.now_iso(), "history": [_hist(user, "requested", body.remarks)]}
    await S.db.store_requests.insert_one(doc)
    await S.log_audit(pid, user, f"{body.kind} request raised", "store_request", doc["id"], f"{body.quantity} {body.unit} {body.item}")
    for rid in await C.recipients_with(project, "store", "approve", exclude=user["id"]):
        await S.notify(rid, "store_request", f"New {body.kind} request: {body.quantity} {body.unit} {body.item} — {project['name']}.",
                       pid, link=f"/projects/{pid}?tab=store", push=True)
    doc.pop("_id", None)
    return doc


async def _req(rid, user):
    r = await S.db.store_requests.find_one({"id": rid, "company_id": user["company_id"]}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    return r


@router.post("/store/requests/{rid}/decision")
async def decide_store_request(rid: str, body: DecisionIn, user: dict = Depends(C.commercial_user)):
    r = await _req(rid, user)
    await C.require_perm(user, r["project_id"], "store", "approve")
    if body.action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Invalid action.")
    st = "approved" if body.action == "approve" else "rejected"
    res = await S.db.store_requests.update_one({"id": rid, "status": "requested"}, {"$set": {"status": st, "decided_by": user["id"], "decision_comment": body.comment},
                                                                                  "$push": {"history": _hist(user, st, body.comment)}})
    if not res.modified_count:
        raise HTTPException(status_code=400, detail="This request has already been decided.")
    await S.log_audit(r["project_id"], user, f"store request {st}", "store_request", rid, body.comment)
    await S.notify(r["requested_by"], "store_decision", f"Your {r['kind']} request for {r['item']} was {st}.", r["project_id"],
                   link=f"/projects/{r['project_id']}?tab=store", push=True)
    return await _req(rid, user)


@router.post("/store/requests/{rid}/issue")
async def issue_store_request(rid: str, body: IssueIn, user: dict = Depends(C.commercial_user)):
    r = await _req(rid, user)
    await C.require_perm(user, r["project_id"], "store", "approve")
    if r["status"] not in {"approved", "partially_issued"}:
        raise HTTPException(status_code=400, detail="Only approved requests can be issued.")
    if r["issued_qty"] + body.quantity > r["quantity"]:
        raise HTTPException(status_code=400, detail="Issue quantity exceeds the approved request.")
    await _photos_ok(r["project_id"], body.photo_ids)
    stock = await S.db.store_stock.find_one_and_update(
        {"project_id": r["project_id"], "item_key": _key(r["item"]), "available": {"$gte": body.quantity}},
        {"$inc": {"available": -body.quantity, "issued_out": body.quantity if r["kind"] == "tool" else 0,
                  "consumed": body.quantity if r["kind"] == "material" else 0}})
    if not stock:
        raise HTTPException(status_code=400, detail="Insufficient stock available for this item.")
    issued = r["issued_qty"] + body.quantity
    st = "issued" if issued >= r["quantity"] else "partially_issued"
    await S.db.store_requests.update_one({"id": rid}, {"$set": {"issued_qty": issued, "status": st},
                                                       "$push": {"history": _hist(user, st, f"{body.quantity} issued to {body.responsible_person}")}})
    await _txn(user, r["project_id"], "issue", r["item"], r["kind"], body.quantity, body.photo_ids, body.responsible_person, rid, {"note": body.note})
    await S.notify(r["requested_by"], "store_issue", f"{body.quantity} {r['unit']} {r['item']} issued to {body.responsible_person}.",
                   r["project_id"], link=f"/projects/{r['project_id']}?tab=store", push=True)
    return await _req(rid, user)


@router.post("/store/requests/{rid}/return")
async def return_tool(rid: str, body: ReturnIn, user: dict = Depends(C.commercial_user)):
    r = await _req(rid, user)
    await C.require_perm(user, r["project_id"], "store", "approve")
    total = body.good + body.damaged + body.lost
    if r["kind"] != "tool" or r["status"] not in {"issued", "partially_issued", "partially_returned"}:
        raise HTTPException(status_code=400, detail="Only issued tools can be returned.")
    if total <= 0 or r["returned_qty"] + r["damaged_qty"] + r["lost_qty"] + total > r["issued_qty"]:
        raise HTTPException(status_code=400, detail="Return quantity exceeds what was issued.")
    await _photos_ok(r["project_id"], body.photo_ids)
    await S.db.store_stock.update_one({"project_id": r["project_id"], "item_key": _key(r["item"])},
                                      {"$inc": {"available": body.good, "issued_out": -total, "damaged": body.damaged, "lost": body.lost}})
    done = r["returned_qty"] + r["damaged_qty"] + r["lost_qty"] + total >= r["issued_qty"] and r["issued_qty"] >= r["quantity"]
    st = "returned" if done else "partially_returned"
    await S.db.store_requests.update_one({"id": rid}, {"$inc": {"returned_qty": body.good, "damaged_qty": body.damaged, "lost_qty": body.lost},
                                                       "$set": {"status": st}, "$push": {"history": _hist(user, st, f"good {body.good}, damaged {body.damaged}, lost {body.lost}")}})
    await _txn(user, r["project_id"], "return", r["item"], "tool", total, body.photo_ids, body.responsible_person, rid,
               {"good": body.good, "damaged": body.damaged, "lost": body.lost, "note": body.note})
    await S.notify(r["requested_by"], "store_issue", f"Return recorded for {r['item']}: {body.good} good, {body.damaged} damaged, {body.lost} lost.",
                   r["project_id"], link=f"/projects/{r['project_id']}?tab=store", push=True)
    return await _req(rid, user)


@router.post("/projects/{pid}/store/receive")
async def receive_stock(pid: str, body: ReceiveIn, user: dict = Depends(C.commercial_user)):
    await C.require_perm(user, pid, "store", "approve")
    if body.kind not in {"material", "tool"}:
        raise HTTPException(status_code=400, detail="Kind must be material or tool.")
    await _photos_ok(pid, body.photo_ids)
    await S.db.store_stock.update_one({"project_id": pid, "item_key": _key(body.item)},
                                      {"$inc": {"available": body.quantity, "received": body.quantity},
                                       "$setOnInsert": {"item": body.item.strip(), "unit": body.unit, "kind": body.kind, "company_id": user["company_id"],
                                                        "issued_out": 0, "consumed": 0, "damaged": 0, "lost": 0}}, upsert=True)
    await _txn(user, pid, "receive", body.item.strip(), body.kind, body.quantity, body.photo_ids, body.responsible_person, None, {"note": body.note})
    return {"ok": True}


@router.get("/projects/{pid}/store/stock")
async def list_stock(pid: str, user: dict = Depends(C.commercial_user)):
    await C.require_perm(user, pid, "store", "view")
    return await S.db.store_stock.find({"project_id": pid}, {"_id": 0}).sort("item", 1).to_list(1000)


@router.get("/projects/{pid}/store/transactions")
async def list_txns(pid: str, user: dict = Depends(C.commercial_user)):
    await C.require_perm(user, pid, "store", "view")
    return await S.db.store_txns.find({"project_id": pid}, {"_id": 0}).sort("at", -1).to_list(500)


# ---------------------------------------------------------------------------
# BOQ (approved quantities)
# ---------------------------------------------------------------------------
class BoqIn(BaseModel):
    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    unit: str
    approved_qty: float = Field(gt=0)


@router.get("/projects/{pid}/boq")
async def list_boq(pid: str, user: dict = Depends(C.commercial_user)):
    await C.require_perm(user, pid, "dpr", "view")
    items = await S.db.boq_items.find({"project_id": pid}, {"_id": 0}).sort("code", 1).to_list(2000)
    for b in items:
        b["remaining_qty"] = round(max(b["approved_qty"] - b["accepted_qty"], 0), 3)
        b["progress_pct"] = round(min(b["accepted_qty"] / b["approved_qty"], 1) * 100, 1)
    return items


@router.post("/projects/{pid}/boq")
async def create_boq(pid: str, body: BoqIn, user: dict = Depends(C.commercial_user)):
    project = await S.get_project_or_403(pid, user)
    if not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Only the project manager or admin can approve BOQ items.")
    if await S.db.boq_items.find_one({"project_id": pid, "code": body.code.strip()}):
        raise HTTPException(status_code=409, detail="BOQ code already exists on this project.")
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, **body.model_dump(), "code": body.code.strip(),
           "status": "approved", "accepted_qty": 0.0, "approved_by": user["id"], "created_at": S.now_iso()}
    await S.db.boq_items.insert_one(doc)
    await S.log_audit(pid, user, "approved BOQ item", "boq", doc["id"], f"{body.code} {body.approved_qty} {body.unit}")
    doc.pop("_id", None)
    return doc


async def annotate_boq_entries(pid, entries):
    """Validate DPR BOQ entries and flag quantities that would exceed the approved BOQ."""
    out = []
    for e in entries:
        b = await S.db.boq_items.find_one({"id": e["boq_id"], "project_id": pid, "status": "approved"}, {"_id": 0})
        if not b:
            raise HTTPException(status_code=400, detail="Select approved BOQ items from this project.")
        excess = b["accepted_qty"] + e["qty"] > b["approved_qty"] + 1e-9
        out.append({**e, "code": b["code"], "description": b["description"], "unit": b["unit"], "approved_qty": b["approved_qty"],
                    "cumulative_before": b["accepted_qty"], "excess": excess})
    return out


async def apply_boq(pid, entries):
    for e in entries:
        await S.db.boq_items.update_one({"id": e["boq_id"], "project_id": pid}, {"$inc": {"accepted_qty": e["qty"]}})
    items = await S.db.boq_items.find({"project_id": pid}, {"_id": 0}).to_list(2000)
    total = sum(b["approved_qty"] for b in items)
    if total:
        pct = round(sum(min(b["accepted_qty"], b["approved_qty"]) for b in items) / total * 100, 1)
        await S.db.projects.update_one({"id": pid}, {"$set": {"progress_percent": pct, "boq_progress_percent": pct}})


# ---------------------------------------------------------------------------
# Labour attendance (counts, labour in-charge, photo + GPS geofence)
# ---------------------------------------------------------------------------
class GeofenceIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_m: float = Field(ge=20, le=5000)


class LabourIn(BaseModel):
    labour_incharge: str = ""
    masons: int = Field(ge=0)
    helpers: int = Field(ge=0)
    lat: float
    lng: float
    photo_id: str


def _dist(a1, o1, a2, o2):
    p = math.pi / 180
    h = math.sin((a2 - a1) * p / 2) ** 2 + math.cos(a1 * p) * math.cos(a2 * p) * math.sin((o2 - o1) * p / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


async def _fence(pid, user, body: LabourIn):
    project, _ = await C.require_perm(user, pid, "attendance", "create")
    g = project.get("geofence")
    if not g:
        raise HTTPException(status_code=400, detail="The project manager must set the site geofence first.")
    d = _dist(g["lat"], g["lng"], body.lat, body.lng)
    if d > g["radius_m"]:
        raise HTTPException(status_code=403, detail=f"You are {int(d)} m from site — outside the {int(g['radius_m'])} m geofence.")
    await _photos_ok(pid, [body.photo_id])
    return {"at": S.now_iso(), "lat": body.lat, "lng": body.lng, "distance_m": round(d), "photo_id": body.photo_id,
            "masons": body.masons, "helpers": body.helpers, "by": user["name"]}


@router.put("/projects/{pid}/geofence")
async def set_geofence(pid: str, body: GeofenceIn, user: dict = Depends(C.commercial_user)):
    project = await S.get_project_or_403(pid, user)
    if not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Only the project manager or admin can set the geofence.")
    await S.db.projects.update_one({"id": pid}, {"$set": {"geofence": body.model_dump()}})
    await S.log_audit(pid, user, "set site geofence", "project", pid, str(body.model_dump()))
    return body.model_dump()


@router.post("/projects/{pid}/labour/check-in")
async def labour_check_in(pid: str, body: LabourIn, user: dict = Depends(C.commercial_user)):
    if not body.labour_incharge.strip():
        raise HTTPException(status_code=400, detail="Enter the labour in-charge name.")
    rec = await _fence(pid, user, body)
    day = datetime.now(timezone.utc).astimezone(C.IST).date().isoformat()
    if await S.db.labour_attendance.find_one({"project_id": pid, "date": day, "labour_incharge": body.labour_incharge.strip()}):
        raise HTTPException(status_code=400, detail="This labour gang is already checked in today.")
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, "date": day, "labour_incharge": body.labour_incharge.strip(),
           "masons": body.masons, "helpers": body.helpers, "check_in": rec, "check_out": None, "recorded_by": user["id"], "created_at": S.now_iso()}
    await S.db.labour_attendance.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/labour/{lid}/check-out")
async def labour_check_out(lid: str, body: LabourIn, user: dict = Depends(C.commercial_user)):
    a = await S.db.labour_attendance.find_one({"id": lid, "company_id": user["company_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Record not found")
    if a.get("check_out"):
        raise HTTPException(status_code=400, detail="Already checked out.")
    rec = await _fence(a["project_id"], user, body)
    await S.db.labour_attendance.update_one({"id": lid}, {"$set": {"check_out": rec}})
    return await S.db.labour_attendance.find_one({"id": lid}, {"_id": 0})


@router.get("/projects/{pid}/labour")
async def list_labour(pid: str, month: Optional[str] = None, user: dict = Depends(C.commercial_user)):
    project, _ = await C.require_perm(user, pid, "attendance", "view")
    q = {"project_id": pid}
    if month:
        q["date"] = {"$regex": f"^{month}"}
    rows = await S.db.labour_attendance.find(q, {"_id": 0}).sort("date", -1).to_list(2000)
    return {"geofence": project.get("geofence"), "rows": rows,
            "totals": {"masons": sum(r["masons"] for r in rows), "helpers": sum(r["helpers"] for r in rows)}}
