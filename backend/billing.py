"""Commercial billing (Accounts -> PM -> Owner approval) and company vehicles with driver assignment."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import server as S
import commercial as C

router = APIRouter()
BILL_STAGES = {"pending_pm": "Awaiting PM approval", "pending_owner": "Awaiting Owner approval", "approved": "Approved",
               "paid": "Paid", "rejected": "Rejected"}
TRIP_STATUSES = {"requested", "assigned", "in_progress", "completed", "rejected", "cancelled"}


def _need(user, module):
    S.require_module(user, module)


async def billing_user(user: dict = Depends(S.get_current_user)) -> dict:
    _need(user, "billing")
    return user


async def vehicles_user(user: dict = Depends(S.get_current_user)) -> dict:
    _need(user, "vehicles")
    return user


def _fleet_admin(user):
    if user["role"] not in {"accounts", "admin"}:
        raise HTTPException(status_code=403, detail="Only Accounts or the Owner can manage vehicles and drivers.")


async def _admins(cid):
    return [u["id"] async for u in S.db.users.find({"company_id": cid, "role": "admin", "is_active": {"$ne": False}}, {"_id": 0, "id": 1})]


# ---------------------------------------------------------------------------
# Bills / invoices
# ---------------------------------------------------------------------------
class BillIn(BaseModel):
    vendor_name: str = Field(min_length=1, max_length=120)
    bill_no: str = Field(min_length=1, max_length=60)
    bill_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    due_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    category: str = Field(default="Material", max_length=60)
    description: str = Field(default="", max_length=1000)
    amount: float = Field(gt=0)
    gst_amount: float = Field(default=0, ge=0)
    file_ids: List[str] = []


class BillDecision(BaseModel):
    action: str
    remarks: str = Field(default="", max_length=1000)


class BillPaid(BaseModel):
    paid_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    payment_ref: str = Field(default="", max_length=120)


async def _bill(bid, user):
    b = await S.db.bills.find_one({"id": bid, "company_id": user["company_id"]}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Bill not found")
    return b


async def _check_files(pid, ids):
    if ids and await S.db.files.count_documents({"id": {"$in": ids}, "project_id": pid, "is_deleted": False}) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Attachments must be uploaded to this project.")


def _pm_step_ok(user, project):
    if project.get("project_manager_id"):
        return user["role"] == "project_manager" and user["id"] == project["project_manager_id"]
    return user["role"] == "admin"


def _hist(status, user, remarks=""):
    return {"status": status, "by": user["name"], "role": S.ROLE_NAMES.get(user["role"], user["role"]), "at": S.now_iso(), "remarks": remarks}


@router.get("/projects/{pid}/bills")
async def list_bills(pid: str, user: dict = Depends(billing_user)):
    await C.require_perm(user, pid, "billing", "view")
    return await S.db.bills.find({"project_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.get("/bills")
async def all_bills(status: Optional[str] = Query(None), user: dict = Depends(billing_user)):
    if user["role"] not in {"accounts", "admin", "project_manager"}:
        raise HTTPException(status_code=403, detail="Not allowed.")
    q = {"company_id": user["company_id"]}
    if user["role"] == "project_manager":
        q["project_id"] = {"$in": [p["id"] for p in await S.list_projects(user)]}
    if status:
        q["status"] = status
    rows = await S.db.bills.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    total = lambda st: round(sum(r["total"] for r in rows if r["status"] in st), 2)  # noqa: E731
    return {"bills": rows, "summary": {"pending": total({"pending_pm", "pending_owner"}), "approved": total({"approved"}), "paid": total({"paid"}),
                                       "count_pending_pm": sum(r["status"] == "pending_pm" for r in rows),
                                       "count_pending_owner": sum(r["status"] == "pending_owner" for r in rows)}}


@router.post("/projects/{pid}/bills")
async def create_bill(pid: str, body: BillIn, user: dict = Depends(billing_user)):
    project, _ = await C.require_perm(user, pid, "billing", "create")
    await _check_files(pid, body.file_ids)
    if await S.db.bills.find_one({"company_id": user["company_id"], "vendor_name": body.vendor_name.strip(), "bill_no": body.bill_no.strip()}):
        raise HTTPException(status_code=409, detail="This vendor bill number is already recorded.")
    ctr = await S.db.counters.find_one_and_update({"id": f"bill-{user['company_id']}"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, "project_name": project["name"], "project_code": project.get("code"),
           **body.model_dump(), "vendor_name": body.vendor_name.strip(), "bill_no": body.bill_no.strip(),
           "ref_no": f"BILL-{ctr['seq']:05d}", "total": round(body.amount + body.gst_amount, 2), "status": "pending_pm",
           "created_by": user["id"], "created_by_name": user["name"], "created_at": S.now_iso(), "history": [_hist("pending_pm", user, "Submitted")]}
    await S.db.bills.insert_one(doc)
    doc.pop("_id", None)
    await S.log_audit(pid, user, "submitted bill", "bill", doc["id"], f"{doc['ref_no']} {body.vendor_name} Rs {doc['total']}")
    approver = project.get("project_manager_id") or None
    for rid in ([approver] if approver else await _admins(user["company_id"])):
        if rid != user["id"]:
            await S.notify(rid, "bill", f"Bill {doc['ref_no']} ({body.vendor_name}, Rs {doc['total']:,.0f}) awaits your approval — {project['name']}.",
                           pid, link=f"/projects/{pid}?tab=billing", push=True)
    return doc


@router.put("/bills/{bid}")
async def resubmit_bill(bid: str, body: BillIn, user: dict = Depends(billing_user)):
    b = await _bill(bid, user)
    await C.require_perm(user, b["project_id"], "billing", "edit")
    if b["status"] != "rejected":
        raise HTTPException(status_code=400, detail="Only rejected bills can be corrected and resubmitted.")
    await _check_files(b["project_id"], body.file_ids)
    if await S.db.bills.find_one({"company_id": user["company_id"], "vendor_name": body.vendor_name.strip(), "bill_no": body.bill_no.strip(), "id": {"$ne": bid}}):
        raise HTTPException(status_code=409, detail="This vendor bill number is already recorded.")
    upd = {**body.model_dump(), "total": round(body.amount + body.gst_amount, 2), "status": "pending_pm", "updated_at": S.now_iso()}
    await S.db.bills.update_one({"id": bid}, {"$set": upd, "$push": {"history": _hist("pending_pm", user, "Corrected and resubmitted")}})
    return await _bill(bid, user)


@router.post("/bills/{bid}/decision")
async def decide_bill(bid: str, body: BillDecision, user: dict = Depends(billing_user)):
    b = await _bill(bid, user)
    project = await S.get_project_or_403(b["project_id"], user)
    if body.action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Invalid action.")
    if b["status"] == "pending_pm":
        if not _pm_step_ok(user, project):
            raise HTTPException(status_code=403, detail="This bill is waiting for the project manager's approval.")
        nxt = "pending_owner" if body.action == "approve" else "rejected"
    elif b["status"] == "pending_owner":
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="This bill is waiting for the Owner's approval.")
        nxt = "approved" if body.action == "approve" else "rejected"
    else:
        raise HTTPException(status_code=400, detail="This bill is not awaiting approval.")
    if body.action == "reject" and not body.remarks.strip():
        raise HTTPException(status_code=400, detail="Please give a reason for rejecting.")
    res = await S.db.bills.update_one({"id": bid, "status": b["status"]}, {"$set": {"status": nxt, f"{b['status']}_by": user["name"], "updated_at": S.now_iso()},
                                                                          "$push": {"history": _hist(nxt, user, body.remarks)}})
    if not res.modified_count:
        raise HTTPException(status_code=409, detail="This bill was already decided.")
    await S.log_audit(b["project_id"], user, f"bill -> {nxt}", "bill", bid, f"{b['ref_no']} {body.remarks}")
    link = f"/projects/{b['project_id']}?tab=billing"
    if nxt == "pending_owner":
        for rid in await _admins(user["company_id"]):
            await S.notify(rid, "bill", f"Bill {b['ref_no']} approved by PM — awaits your final approval.", b["project_id"], link=link, push=True)
    else:
        await S.notify(b["created_by"], "bill", f"Bill {b['ref_no']} was {BILL_STAGES[nxt].lower()}{': ' + body.remarks if body.remarks else ''}.",
                       b["project_id"], link=link, push=True)
    return await _bill(bid, user)


@router.post("/bills/{bid}/paid")
async def mark_paid(bid: str, body: BillPaid, user: dict = Depends(billing_user)):
    b = await _bill(bid, user)
    if user["role"] not in {"accounts", "admin"}:
        raise HTTPException(status_code=403, detail="Only Accounts or the Owner can record payments.")
    await S.get_project_or_403(b["project_id"], user)
    if b["status"] != "approved":
        raise HTTPException(status_code=400, detail="Only fully approved bills (PM + Owner) can be marked paid.")
    res = await S.db.bills.update_one({"id": bid, "status": "approved"}, {"$set": {"status": "paid", **body.model_dump()}, "$push": {"history": _hist("paid", user, body.payment_ref)}})
    if not res.modified_count:
        raise HTTPException(status_code=409, detail="This bill was already marked paid.")
    await S.log_audit(b["project_id"], user, "bill paid", "bill", bid, f"{b['ref_no']} {body.payment_ref}")
    return await _bill(bid, user)


# ---------------------------------------------------------------------------
# Vehicles & drivers
# ---------------------------------------------------------------------------
class VehicleIn(BaseModel):
    reg_no: str = Field(min_length=3, max_length=20)
    model: str = Field(min_length=1, max_length=80)
    vehicle_type: str = Field(default="Car", max_length=40)
    capacity: str = Field(default="", max_length=40)
    status: str = "active"


class TripIn(BaseModel):
    purpose: str = Field(min_length=3, max_length=300)
    pickup: str = Field(min_length=1, max_length=200)
    drop: str = Field(min_length=1, max_length=200)
    trip_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    trip_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    vehicle_type: str = Field(default="Any", max_length=40)
    notes: str = Field(default="", max_length=500)


class AssignIn(BaseModel):
    vehicle_id: str
    driver_id: str
    remarks: str = Field(default="", max_length=500)


class TripAction(BaseModel):
    action: str
    remarks: str = Field(default="", max_length=500)


@router.get("/vehicles")
async def list_vehicles(user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    return await S.db.vehicles.find({"company_id": user["company_id"]}, {"_id": 0}).sort("reg_no", 1).to_list(500)


@router.post("/vehicles")
async def add_vehicle(body: VehicleIn, user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    if body.status not in {"active", "maintenance"}:
        raise HTTPException(status_code=400, detail="Status must be active or maintenance.")
    reg = body.reg_no.strip().upper()
    if await S.db.vehicles.find_one({"company_id": user["company_id"], "reg_no": reg}):
        raise HTTPException(status_code=409, detail="A vehicle with this registration already exists.")
    doc = {"id": S.new_id(), "company_id": user["company_id"], **body.model_dump(), "reg_no": reg, "created_at": S.now_iso()}
    await S.db.vehicles.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/vehicles/{vid}")
async def edit_vehicle(vid: str, body: VehicleIn, user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    if body.status not in {"active", "maintenance"}:
        raise HTTPException(status_code=400, detail="Status must be active or maintenance.")
    res = await S.db.vehicles.update_one({"id": vid, "company_id": user["company_id"]}, {"$set": {**body.model_dump(), "reg_no": body.reg_no.strip().upper()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return await S.db.vehicles.find_one({"id": vid}, {"_id": 0})


@router.get("/drivers")
async def list_drivers(user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    rows = await S.db.users.find({"company_id": user["company_id"], "role": "driver", "is_active": {"$ne": False}}, {"_id": 0, "password_hash": 0}).to_list(500)
    return [S.public_user(u) for u in rows]


async def _trip(tid, user):
    t = await S.db.vehicle_requests.find_one({"id": tid, "company_id": user["company_id"]}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Vehicle request not found")
    return t


@router.get("/projects/{pid}/vehicle-requests")
async def project_trips(pid: str, user: dict = Depends(vehicles_user)):
    _, perms = await C.require_perm(user, pid, "vehicles", "view")
    q = {"project_id": pid}
    if "approve" not in perms.get("vehicles", []) and user["role"] not in {"accounts", "admin"}:
        q["requested_by"] = user["id"]
    return await S.db.vehicle_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/projects/{pid}/vehicle-requests")
async def request_vehicle(pid: str, body: TripIn, user: dict = Depends(vehicles_user)):
    project, _ = await C.require_perm(user, pid, "vehicles", "create")
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, "project_name": project["name"], **body.model_dump(),
           "status": "requested", "requested_by": user["id"], "requested_by_name": user["name"], "vehicle": None, "driver": None,
           "created_at": S.now_iso(), "history": [_hist("requested", user)]}
    await S.db.vehicle_requests.insert_one(doc)
    doc.pop("_id", None)
    async for u in S.db.users.find({"company_id": user["company_id"], "role": {"$in": ["accounts", "admin"]}, "is_active": {"$ne": False}}, {"_id": 0, "id": 1}):
        if u["id"] != user["id"]:
            await S.notify(u["id"], "vehicle", f"Vehicle requested by {user['name']} for {body.trip_date} {body.trip_time} — {project['name']}.",
                           pid, link="/accounts?tab=fleet", push=True)
    return doc


@router.get("/vehicle-requests")
async def all_trips(status: Optional[str] = Query(None), user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    q = {"company_id": user["company_id"], **({"status": status} if status else {})}
    rows = await S.db.vehicle_requests.find(q, {"_id": 0}).sort([("trip_date", -1), ("trip_time", -1)]).to_list(2000)
    return sorted(rows, key=lambda t: t["status"] != "requested")


@router.get("/my-trips")
async def my_trips(user: dict = Depends(vehicles_user)):
    if user["role"] != "driver":
        raise HTTPException(status_code=403, detail="Only drivers have trips.")
    return await S.db.vehicle_requests.find({"company_id": user["company_id"], "driver.id": user["id"]}, {"_id": 0}).sort([("trip_date", -1), ("trip_time", -1)]).to_list(500)


@router.post("/vehicle-requests/{tid}/assign")
async def assign_trip(tid: str, body: AssignIn, user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    t = await _trip(tid, user)
    if t["status"] not in {"requested", "assigned"}:
        raise HTTPException(status_code=400, detail="Only open requests can be assigned.")
    v = await S.db.vehicles.find_one({"id": body.vehicle_id, "company_id": user["company_id"]}, {"_id": 0})
    if not v or v.get("status") != "active":
        raise HTTPException(status_code=400, detail="Choose an active company vehicle.")
    d = await S.db.users.find_one({"id": body.driver_id, "company_id": user["company_id"], "role": "driver", "is_active": {"$ne": False}}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=400, detail="Choose an active driver.")
    clash = {"company_id": user["company_id"], "id": {"$ne": tid}, "trip_date": t["trip_date"], "trip_time": t["trip_time"], "status": {"$in": ["assigned", "in_progress"]}}
    if await S.db.vehicle_requests.find_one({**clash, "$or": [{"vehicle.id": v["id"]}, {"driver.id": d["id"]}]}):
        raise HTTPException(status_code=409, detail="This vehicle or driver is already booked for the same date and time.")
    upd = {"status": "assigned", "vehicle": {"id": v["id"], "reg_no": v["reg_no"], "model": v["model"]},
           "driver": {"id": d["id"], "name": d["name"], "phone": d.get("phone")}, "assigned_by_name": user["name"], "assigned_at": S.now_iso()}
    await S.db.vehicle_requests.update_one({"id": tid}, {"$set": upd, "$push": {"history": _hist("assigned", user, f"{v['reg_no']} · {d['name']} {body.remarks}".strip())}})
    await S.log_audit(t["project_id"], user, "vehicle assigned", "vehicle_request", tid, f"{v['reg_no']} driver {d['name']}")
    await S.notify(d["id"], "trip", f"New trip {t['trip_date']} {t['trip_time']}: {t['pickup']} → {t['drop']} ({v['reg_no']}).", t["project_id"], link="/trips", push=True)
    await S.notify(t["requested_by"], "vehicle", f"Vehicle {v['reg_no']} with driver {d['name']} assigned for {t['trip_date']} {t['trip_time']}.",
                   t["project_id"], link=f"/projects/{t['project_id']}?tab=vehicles", push=True)
    return await _trip(tid, user)


@router.post("/vehicle-requests/{tid}/status")
async def trip_status(tid: str, body: TripAction, user: dict = Depends(vehicles_user)):
    t = await _trip(tid, user)
    flows = {"start": ({"assigned"}, "in_progress", "driver"), "complete": ({"in_progress"}, "completed", "driver"),
             "reject": ({"requested", "assigned"}, "rejected", "fleet"), "cancel": ({"requested", "assigned"}, "cancelled", "requester")}
    if body.action not in flows or t["status"] not in flows[body.action][0]:
        raise HTTPException(status_code=400, detail="This action is not allowed for the request's current status.")
    _, nxt, who = flows[body.action]
    if who == "driver" and (t.get("driver") or {}).get("id") != user["id"]:
        raise HTTPException(status_code=403, detail="Only the assigned driver can update this trip.")
    if who == "fleet":
        _fleet_admin(user)
        if not body.remarks.strip():
            raise HTTPException(status_code=400, detail="Please give a reason.")
    if who == "requester" and t["requested_by"] != user["id"] and user["role"] not in {"accounts", "admin"}:
        raise HTTPException(status_code=403, detail="Only the requester can cancel.")
    await S.db.vehicle_requests.update_one({"id": tid}, {"$set": {"status": nxt, f"{nxt}_at": S.now_iso()}, "$push": {"history": _hist(nxt, user, body.remarks)}})
    msg = f"Trip {t['trip_date']} {t['trip_time']} ({t['pickup']} → {t['drop']}) is now {nxt.replace('_', ' ')}."
    for rid in {t["requested_by"], (t.get("driver") or {}).get("id")} - {None, user["id"]}:
        await S.notify(rid, "trip", msg, t["project_id"], push=True)
    return await _trip(tid, user)
