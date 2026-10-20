"""Commercial billing (Accounts -> PM -> Owner approval) and company vehicles with driver assignment."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import server as S
import commercial as C

router = APIRouter()
BILL_STAGES = {"pending_pm": "Awaiting PM approval", "pending_owner": "Awaiting Owner approval", "approved": "Approved",
               "paid": "Paid", "rejected": "Rejected"}


def _need(user, module):
    S.require_module(user, module)


async def billing_user(user: dict = Depends(S.get_current_user)) -> dict:
    _need(user, "billing")
    return user


async def vehicles_user(user: dict = Depends(S.get_current_user)) -> dict:
    _need(user, "vehicles")
    return user


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
# Company fleet & project vehicle requests (PM approves, PM/Owner assigns)
# ---------------------------------------------------------------------------
class VehicleIn(BaseModel):
    reg_no: str = Field(min_length=3, max_length=20)
    model: str = Field(min_length=1, max_length=80)
    vehicle_type: str = Field(default="Car", max_length=40)
    capacity: str = Field(default="", max_length=40)
    driver_name: str = Field(default="", max_length=80)
    driver_phone: str = Field(default="", max_length=20)
    insurance_expiry: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    permit_expiry: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: str = "active"


class TripIn(BaseModel):
    purpose: str = Field(min_length=3, max_length=300)
    destination: str = Field(min_length=1, max_length=200)
    from_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    to_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    vehicle_type: str = Field(default="Any", max_length=40)
    notes: str = Field(default="", max_length=500)


class AssignIn(BaseModel):
    vehicle_id: str
    driver_id: Optional[str] = None
    remarks: str = Field(default="", max_length=500)


class TripAction(BaseModel):
    action: str
    remarks: str = Field(default="", max_length=500)


VEHICLE_STATUSES = {"active", "maintenance", "inactive"}
ACTIVE_TRIP = ["assigned", "in_progress"]


def _fleet_admin(user):
    if user["role"] not in {"admin", "project_manager"}:
        raise HTTPException(status_code=403, detail="Only the Owner or a project manager can manage vehicles.")


async def _trip_manager(user, t):
    project = await S.db.projects.find_one({"id": t["project_id"]}, {"_id": 0})
    if not project or not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Only this project's manager or the Owner can do this.")
    return project


async def _tell(t, msg, exclude=None, link=None):
    project = await S.db.projects.find_one({"id": t["project_id"]}, {"_id": 0, "project_manager_id": 1})
    ids = {t["requested_by"], (t.get("driver") or {}).get("id"), (project or {}).get("project_manager_id"), *await _admins(t["company_id"])}
    for rid in ids - {None, exclude}:
        await S.notify(rid, "vehicle", msg, t["project_id"], link=link or f"/projects/{t['project_id']}?tab=vehicles", push=True)


def _check_vehicle(body):
    if body.status not in VEHICLE_STATUSES:
        raise HTTPException(status_code=400, detail="Status must be active, maintenance or inactive.")


@router.get("/vehicles")
async def list_vehicles(user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    return await S.db.vehicles.find({"company_id": user["company_id"]}, {"_id": 0}).sort("reg_no", 1).to_list(500)


@router.post("/vehicles")
async def add_vehicle(body: VehicleIn, user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    _check_vehicle(body)
    reg = body.reg_no.strip().upper().replace(" ", "")
    if await S.db.vehicles.find_one({"company_id": user["company_id"], "reg_no": reg}):
        raise HTTPException(status_code=409, detail="A vehicle with this registration number already exists.")
    doc = {"id": S.new_id(), "company_id": user["company_id"], **body.model_dump(), "reg_no": reg, "created_by_name": user["name"], "created_at": S.now_iso()}
    await S.db.vehicles.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/vehicles/{vid}")
async def edit_vehicle(vid: str, body: VehicleIn, user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    _check_vehicle(body)
    reg = body.reg_no.strip().upper().replace(" ", "")
    if await S.db.vehicles.find_one({"company_id": user["company_id"], "reg_no": reg, "id": {"$ne": vid}}):
        raise HTTPException(status_code=409, detail="A vehicle with this registration number already exists.")
    res = await S.db.vehicles.update_one({"id": vid, "company_id": user["company_id"]}, {"$set": {**body.model_dump(), "reg_no": reg}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return await S.db.vehicles.find_one({"id": vid}, {"_id": 0})


@router.get("/drivers")
async def list_drivers(user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    rows = await S.db.users.find({"company_id": user["company_id"], "role": "driver", "is_active": {"$ne": False}}, {"_id": 0, "password_hash": 0}).to_list(500)
    return [S.public_user(u) for u in rows]


@router.get("/fleet/status")
async def fleet_status(user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    today = datetime.now(C.IST).date().isoformat()
    vehicles = await S.db.vehicles.find({"company_id": user["company_id"], "status": {"$ne": "inactive"}}, {"_id": 0}).sort("reg_no", 1).to_list(500)
    trips = await S.db.vehicle_requests.find({"company_id": user["company_id"], "status": {"$in": ACTIVE_TRIP}}, {"_id": 0}).to_list(1000)
    out = []
    for v in vehicles:
        cur = next((t for t in trips if t["vehicle"]["id"] == v["id"] and (t["status"] == "in_progress" or t["from_date"] <= today <= t["to_date"])), None)
        out.append({**v, "current": cur and {"trip_id": cur["id"], "project_id": cur["project_id"], "project_name": cur["project_name"], "status": cur["status"],
                                             "destination": cur.get("destination"), "to_date": cur["to_date"], "driver": cur.get("driver")}})
    return out


async def _trip(tid, user):
    t = await S.db.vehicle_requests.find_one({"id": tid, "company_id": user["company_id"]}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Vehicle request not found")
    return t


@router.get("/projects/{pid}/vehicle-requests")
async def project_trips(pid: str, user: dict = Depends(vehicles_user)):
    project, perms = await C.require_perm(user, pid, "vehicles", "view")
    q = {"project_id": pid}
    if not C._manages(user, project) and "approve" not in perms.get("vehicles", []):
        q["$or"] = [{"requested_by": user["id"]}, {"driver.id": user["id"]}]
    return await S.db.vehicle_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/projects/{pid}/vehicle-requests")
async def request_vehicle(pid: str, body: TripIn, user: dict = Depends(vehicles_user)):
    project, _ = await C.require_perm(user, pid, "vehicles", "create")
    if body.to_date < body.from_date:
        raise HTTPException(status_code=400, detail="End date cannot be before start date.")
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, "project_name": project["name"], **body.model_dump(),
           "status": "requested", "requested_by": user["id"], "requested_by_name": user["name"], "vehicle": None, "driver": None,
           "created_at": S.now_iso(), "history": [_hist("requested", user)]}
    await S.db.vehicle_requests.insert_one(doc)
    doc.pop("_id", None)
    await _tell(doc, f"Vehicle requested by {user['name']} ({body.from_date} → {body.to_date}, {body.destination}) — {project['name']}. Awaiting PM approval.", user["id"])
    return doc


@router.get("/vehicle-requests")
async def all_trips(status: Optional[str] = Query(None), user: dict = Depends(vehicles_user)):
    _fleet_admin(user)
    q = {"company_id": user["company_id"], **({"status": status} if status else {})}
    if user["role"] == "project_manager":
        q["project_id"] = {"$in": [p["id"] for p in await S.list_projects(user) if C._manages(user, p)]}
    rows = await S.db.vehicle_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return sorted(rows, key=lambda t: t["status"] not in {"requested", "approved"})


@router.get("/my-trips")
async def my_trips(user: dict = Depends(vehicles_user)):
    if user["role"] != "driver":
        raise HTTPException(status_code=403, detail="Only drivers have trips.")
    return await S.db.vehicle_requests.find({"company_id": user["company_id"], "driver.id": user["id"]}, {"_id": 0}).sort("from_date", -1).to_list(500)


@router.post("/vehicle-requests/{tid}/decision")
async def decide_trip(tid: str, body: TripAction, user: dict = Depends(vehicles_user)):
    t = await _trip(tid, user)
    await _trip_manager(user, t)
    if t["status"] != "requested" or body.action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="This request is not awaiting approval.")
    if body.action == "reject" and not body.remarks.strip():
        raise HTTPException(status_code=400, detail="Please give a reason.")
    st = "approved" if body.action == "approve" else "rejected"
    await S.db.vehicle_requests.update_one({"id": tid, "status": "requested"}, {"$set": {"status": st, "decided_by_name": user["name"]}, "$push": {"history": _hist(st, user, body.remarks)}})
    await _tell(t, f"Vehicle request ({t['from_date']}, {t['destination']}) was {st} by {user['name']}{': ' + body.remarks if body.remarks else ''}.", user["id"])
    return await _trip(tid, user)


@router.post("/vehicle-requests/{tid}/assign")
async def assign_trip(tid: str, body: AssignIn, user: dict = Depends(vehicles_user)):
    t = await _trip(tid, user)
    await _trip_manager(user, t)
    if t["status"] not in {"approved", "assigned"}:
        raise HTTPException(status_code=400, detail="Approve the request before assigning a vehicle.")
    v = await S.db.vehicles.find_one({"id": body.vehicle_id, "company_id": user["company_id"]}, {"_id": 0})
    if not v or v.get("status") != "active":
        raise HTTPException(status_code=400, detail="Choose an active company vehicle.")
    d = None
    if body.driver_id:
        d = await S.db.users.find_one({"id": body.driver_id, "company_id": user["company_id"], "role": "driver", "is_active": {"$ne": False}}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=400, detail="Choose an active driver.")
    overlap = {"company_id": user["company_id"], "id": {"$ne": tid}, "status": {"$in": ACTIVE_TRIP},
               "from_date": {"$lte": t["to_date"]}, "to_date": {"$gte": t["from_date"]}}
    who = [{"vehicle.id": v["id"]}] + ([{"driver.id": d["id"]}] if d else [])
    if await S.db.vehicle_requests.find_one({**overlap, "$or": who}):
        raise HTTPException(status_code=409, detail="This vehicle or driver is already booked for these dates.")
    driver = {"id": d["id"], "name": d["name"], "phone": d.get("phone")} if d else {"id": None, "name": v.get("driver_name") or "—", "phone": v.get("driver_phone")}
    upd = {"status": "assigned", "vehicle": {"id": v["id"], "reg_no": v["reg_no"], "model": v["model"]}, "driver": driver,
           "assigned_by_name": user["name"], "assigned_at": S.now_iso()}
    await S.db.vehicle_requests.update_one({"id": tid}, {"$set": upd, "$push": {"history": _hist("assigned", user, f"{v['reg_no']} · {driver['name']} {body.remarks}".strip())}})
    await S.log_audit(t["project_id"], user, "vehicle assigned", "vehicle_request", tid, f"{v['reg_no']} driver {driver['name']}")
    t2 = await _trip(tid, user)
    await _tell(t2, f"Vehicle {v['reg_no']} with driver {driver['name']} assigned ({t['from_date']} → {t['to_date']}, {t['destination']}).", user["id"],
                link="/trips" if d else None)
    return t2


@router.post("/vehicle-requests/{tid}/status")
async def trip_status(tid: str, body: TripAction, user: dict = Depends(vehicles_user)):
    t = await _trip(tid, user)
    flows = {"start": ({"assigned"}, "in_progress"), "return": ({"assigned", "in_progress"}, "returned"),
             "cancel": ({"requested", "approved"}, "cancelled")}
    if body.action not in flows or t["status"] not in flows[body.action][0]:
        raise HTTPException(status_code=400, detail="This action is not allowed for the request's current status.")
    is_driver = (t.get("driver") or {}).get("id") == user["id"]
    if body.action == "start" and not is_driver:
        await _trip_manager(user, t)
    if body.action == "return" and not is_driver:
        await _trip_manager(user, t)
    if body.action == "cancel" and t["requested_by"] != user["id"]:
        await _trip_manager(user, t)
    nxt = flows[body.action][1]
    await S.db.vehicle_requests.update_one({"id": tid}, {"$set": {"status": nxt, f"{nxt}_at": S.now_iso()}, "$push": {"history": _hist(nxt, user, body.remarks)}})
    await _tell(t, f"Trip {t['from_date']} ({t['destination']}) is now {nxt.replace('_', ' ')}"
                   f"{' — vehicle ' + t['vehicle']['reg_no'] + ' is available again' if nxt == 'returned' else ''}.", user["id"])
    return await _trip(tid, user)
