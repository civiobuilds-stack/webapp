from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Form, Header, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr

from auth import hash_password, verify_password, create_access_token, decode_token
import storage
import seed as seed_module

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="CIVIO BUILD API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("civio")

MANAGER_ROLES = {"admin", "project_manager"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_roles(*roles):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        return user
    return checker


async def get_project_or_403(project_id: str, user: dict, write: bool = False) -> dict:
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    role = user["role"]
    uid = user["id"]
    allowed = False
    if role == "admin":
        allowed = True
    elif role == "project_manager":
        allowed = project.get("project_manager_id") == uid or project.get("created_by") == uid
    elif role == "site_engineer":
        allowed = uid in project.get("engineer_ids", [])
    elif role == "client":
        allowed = project.get("client_id") == uid and not write
    if not allowed:
        raise HTTPException(status_code=403, detail="You cannot access this project.")
    return project


async def log_audit(project_id, actor, action, entity_type, entity_id, details=""):
    await db.audit_logs.insert_one({
        "id": new_id(),
        "project_id": project_id,
        "actor_id": actor["id"],
        "actor_name": actor["name"],
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details,
        "created_at": now_iso(),
    })


async def notify(user_id, ntype, message, project_id=None, link=None, dedupe_key=None):
    if dedupe_key:
        existing = await db.notifications.find_one({"user_id": user_id, "dedupe_key": dedupe_key, "read": False})
        if existing:
            return
    await db.notifications.insert_one({
        "id": new_id(),
        "user_id": user_id,
        "type": ntype,
        "message": message,
        "project_id": project_id,
        "link": link,
        "read": False,
        "dedupe_key": dedupe_key,
        "created_at": now_iso(),
    })


async def recompute_project_progress(project_id: str):
    activities = await db.activities.find({"project_id": project_id}, {"_id": 0}).to_list(1000)
    if not activities:
        pct = 0.0
    else:
        total_w = sum(a.get("weight", 1) or 1 for a in activities)
        pct = sum((a.get("weight", 1) or 1) * (a.get("progress_percent", 0) or 0) for a in activities) / total_w
    await db.projects.update_one({"id": project_id}, {"$set": {"progress_percent": round(pct, 1)}})
    return round(pct, 1)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    role: str = "client"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    role: str  # site_engineer | client | project_manager
    phone: Optional[str] = None


class ProjectIn(BaseModel):
    name: str
    code: str
    client_id: Optional[str] = None
    address: str = ""
    type: str = "Residential"
    description: str = ""
    start_date: Optional[str] = None
    planned_completion_date: Optional[str] = None
    status: str = "Planning"
    contract_value: Optional[float] = None
    project_manager_id: Optional[str] = None
    engineer_ids: List[str] = []
    client_budget_visible: bool = False


class AssignIn(BaseModel):
    engineer_ids: Optional[List[str]] = None
    client_id: Optional[str] = None
    project_manager_id: Optional[str] = None


class ActivityIn(BaseModel):
    name: str
    phase: str = "General"
    weight: float = 1.0
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    assigned_engineer_id: Optional[str] = None
    unit: Optional[str] = None
    quantity_total: Optional[float] = None
    requires_client_approval: bool = False


class MilestoneIn(BaseModel):
    name: str
    due_date: Optional[str] = None


class ProgressIn(BaseModel):
    activity_id: str
    percent_complete: float = 0
    quantity_completed: Optional[float] = None
    notes: str = ""
    photo_ids: List[str] = []
    submit: bool = True


class ReviewIn(BaseModel):
    action: str  # approve | return | reject
    comment: str = ""


class ClientDecisionIn(BaseModel):
    action: str  # approve | reject | clarify
    comment: str


class ReviseIn(BaseModel):
    percent_complete: float
    quantity_completed: Optional[float] = None
    notes: str = ""
    photo_ids: List[str] = []


class DefectIn(BaseModel):
    location: str
    category: str = "General"
    severity: str = "minor"  # minor | major | critical
    description: str
    responsible_party: Optional[str] = None
    corrective_action: str = ""
    assigned_to: Optional[str] = None
    target_date: Optional[str] = None
    before_photo_ids: List[str] = []


class DefectStatusIn(BaseModel):
    status: str
    note: str = ""
    closure_photo_ids: List[str] = []


def public_user(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "phone": u.get("phone")}


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
def set_auth_cookie(response: Response, token: str):
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")


@api_router.post("/auth/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    if body.role not in {"client", "site_engineer"}:
        raise HTTPException(status_code=400, detail="Self-registration is only allowed for clients and engineers.")
    uid = new_id()
    doc = {
        "id": uid, "email": email, "password_hash": hash_password(body.password),
        "name": body.name, "role": body.role, "phone": None,
        "company_id": "civio", "is_active": True, "is_demo": False, "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    token = create_access_token(uid, email, body.role)
    set_auth_cookie(response, token)
    return {"access_token": token, "user": public_user(doc)}


@api_router.post("/auth/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_access_token(user["id"], email, user["role"])
    set_auth_cookie(response, token)
    return {"access_token": token, "user": public_user(user)}


@api_router.post("/auth/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


# ---------------------------------------------------------------------------
# Users / directory
# ---------------------------------------------------------------------------
@api_router.get("/users")
async def list_users(role: Optional[str] = None, user: dict = Depends(require_roles("admin", "project_manager"))):
    q = {"company_id": "civio"}
    if role:
        q["role"] = role
    users = await db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(1000)
    return [public_user(u) for u in users]


@api_router.post("/users")
async def create_user(body: UserCreateIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    if body.role not in {"site_engineer", "client", "project_manager"}:
        raise HTTPException(status_code=400, detail="Invalid role.")
    if body.role == "project_manager" and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can add project managers.")
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    uid = new_id()
    doc = {
        "id": uid, "email": email, "password_hash": hash_password(body.password),
        "name": body.name, "role": body.role, "phone": body.phone,
        "company_id": "civio", "is_active": True, "is_demo": False, "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    return public_user(doc)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
async def enrich_project(p: dict) -> dict:
    ids = list(filter(None, [p.get("client_id"), p.get("project_manager_id")] + p.get("engineer_ids", [])))
    users = await db.users.find({"id": {"$in": ids}}, {"_id": 0, "password_hash": 0}).to_list(1000)
    umap = {u["id"]: public_user(u) for u in users}
    p["client"] = umap.get(p.get("client_id"))
    p["project_manager"] = umap.get(p.get("project_manager_id"))
    p["engineers"] = [umap[e] for e in p.get("engineer_ids", []) if e in umap]
    return p


@api_router.get("/projects")
async def list_projects(user: dict = Depends(get_current_user)):
    role, uid = user["role"], user["id"]
    q = {"company_id": "civio", "is_archived": {"$ne": True}}
    if role == "project_manager":
        q["$or"] = [{"project_manager_id": uid}, {"created_by": uid}]
    elif role == "site_engineer":
        q["engineer_ids"] = uid
    elif role == "client":
        q["client_id"] = uid
    projects = await db.projects.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for p in projects:
        await enrich_project(p)
    return projects


@api_router.post("/projects")
async def create_project(body: ProjectIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    if await db.projects.find_one({"code": body.code, "company_id": "civio"}):
        raise HTTPException(status_code=400, detail="Project code already in use.")
    pid = new_id()
    doc = body.model_dump()
    doc.update({
        "id": pid, "company_id": "civio",
        "project_manager_id": body.project_manager_id or user["id"],
        "progress_percent": 0.0, "is_archived": False, "is_demo": False,
        "created_by": user["id"], "created_at": now_iso(),
    })
    await db.projects.insert_one(doc)
    await log_audit(pid, user, "created project", "project", pid, doc["name"])
    if body.client_id:
        await notify(body.client_id, "project", f"You have been linked to project {doc['name']}.", pid)
    for e in body.engineer_ids:
        await notify(e, "assignment", f"You have been assigned to project {doc['name']}.", pid)
    doc.pop("_id", None)
    return await enrich_project(doc)


@api_router.get("/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_current_user)):
    p = await get_project_or_403(project_id, user)
    return await enrich_project(p)


@api_router.put("/projects/{project_id}")
async def update_project(project_id: str, body: ProjectIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    await get_project_or_403(project_id, user, write=True)
    data = body.model_dump()
    data.pop("code", None)  # code immutable
    await db.projects.update_one({"id": project_id}, {"$set": data})
    await log_audit(project_id, user, "updated project", "project", project_id, body.name)
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    return await enrich_project(p)


@api_router.post("/projects/{project_id}/assign")
async def assign(project_id: str, body: AssignIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    await get_project_or_403(project_id, user, write=True)
    update = {}
    if body.engineer_ids is not None:
        update["engineer_ids"] = body.engineer_ids
    if body.client_id is not None:
        update["client_id"] = body.client_id
    if body.project_manager_id is not None:
        update["project_manager_id"] = body.project_manager_id
    await db.projects.update_one({"id": project_id}, {"$set": update})
    await log_audit(project_id, user, "updated assignments", "project", project_id, str(update))
    if body.engineer_ids:
        for e in body.engineer_ids:
            await notify(e, "assignment", "You have been assigned to a project.", project_id)
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    return await enrich_project(p)


@api_router.post("/projects/{project_id}/archive")
async def archive_project(project_id: str, user: dict = Depends(require_roles("admin", "project_manager"))):
    await get_project_or_403(project_id, user, write=True)
    await db.projects.update_one({"id": project_id}, {"$set": {"is_archived": True}})
    await log_audit(project_id, user, "archived project", "project", project_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Activities & milestones
# ---------------------------------------------------------------------------
@api_router.get("/projects/{project_id}/activities")
async def list_activities(project_id: str, user: dict = Depends(get_current_user)):
    await get_project_or_403(project_id, user)
    acts = await db.activities.find({"project_id": project_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    return acts


@api_router.post("/projects/{project_id}/activities")
async def create_activity(project_id: str, body: ActivityIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    await get_project_or_403(project_id, user, write=True)
    aid = new_id()
    doc = body.model_dump()
    doc.update({
        "id": aid, "project_id": project_id, "progress_percent": 0.0,
        "quantity_completed": 0.0, "status": "not_started", "created_at": now_iso(),
    })
    await db.activities.insert_one(doc)
    await recompute_project_progress(project_id)
    await log_audit(project_id, user, "added activity", "activity", aid, body.name)
    doc.pop("_id", None)
    return doc


@api_router.get("/projects/{project_id}/milestones")
async def list_milestones(project_id: str, user: dict = Depends(get_current_user)):
    await get_project_or_403(project_id, user)
    return await db.milestones.find({"project_id": project_id}, {"_id": 0}).sort("due_date", 1).to_list(1000)


@api_router.post("/projects/{project_id}/milestones")
async def create_milestone(project_id: str, body: MilestoneIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    await get_project_or_403(project_id, user, write=True)
    doc = {"id": new_id(), "project_id": project_id, "name": body.name, "due_date": body.due_date,
           "status": "upcoming", "created_at": now_iso()}
    await db.milestones.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Progress update workflow
# ---------------------------------------------------------------------------
async def enrich_progress(pu: dict) -> dict:
    uids = list(filter(None, [pu.get("engineer_id"), pu.get("reviewed_by"), pu.get("client_decision_by")]))
    users = await db.users.find({"id": {"$in": uids}}, {"_id": 0, "password_hash": 0}).to_list(1000)
    umap = {u["id"]: public_user(u) for u in users}
    pu["engineer"] = umap.get(pu.get("engineer_id"))
    act = await db.activities.find_one({"id": pu.get("activity_id")}, {"_id": 0})
    pu["activity"] = act
    photos = await db.files.find({"id": {"$in": pu.get("photo_ids", [])}}, {"_id": 0}).to_list(100)
    pu["photos"] = photos
    return pu


@api_router.get("/projects/{project_id}/progress-updates")
async def list_progress(project_id: str, user: dict = Depends(get_current_user)):
    await get_project_or_403(project_id, user)
    q = {"project_id": project_id}
    if user["role"] == "client":
        q["status"] = {"$in": ["pending_client_decision", "approved", "rejected", "clarification_needed"]}
    updates = await db.progress_updates.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for u in updates:
        await enrich_progress(u)
    return updates


@api_router.post("/projects/{project_id}/progress-updates")
async def create_progress(project_id: str, body: ProgressIn, user: dict = Depends(require_roles("site_engineer"))):
    project = await get_project_or_403(project_id, user, write=True)
    act = await db.activities.find_one({"id": body.activity_id, "project_id": project_id}, {"_id": 0})
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not (0 <= body.percent_complete <= 100):
        raise HTTPException(status_code=400, detail="Percent complete must be between 0 and 100.")
    pid = new_id()
    status = "submitted" if body.submit else "draft"
    doc = {
        "id": pid, "project_id": project_id, "activity_id": body.activity_id,
        "engineer_id": user["id"], "percent_complete": body.percent_complete,
        "quantity_completed": body.quantity_completed, "notes": body.notes,
        "photo_ids": body.photo_ids, "status": status, "version": 1,
        "previous_version_id": None, "pm_comment": None, "client_comment": None,
        "reviewed_by": None, "reviewed_at": None, "client_decision_by": None, "client_decision_at": None,
        "requires_client_approval": act.get("requires_client_approval", False),
        "created_at": now_iso(),
        "history": [{"status": status, "by": user["name"], "at": now_iso(), "comment": body.notes}],
    }
    await db.progress_updates.insert_one(doc)
    await log_audit(project_id, user, f"progress update {status}", "progress_update", pid, act["name"])
    if status == "submitted" and project.get("project_manager_id"):
        await notify(project["project_manager_id"], "review_required",
                     f"Progress update submitted for {act['name']} — review required.", project_id)
    doc.pop("_id", None)
    return await enrich_progress(doc)


@api_router.post("/progress-updates/{pu_id}/review")
async def review_progress(pu_id: str, body: ReviewIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    pu = await db.progress_updates.find_one({"id": pu_id}, {"_id": 0})
    if not pu:
        raise HTTPException(status_code=404, detail="Update not found")
    project = await get_project_or_403(pu["project_id"], user, write=True)
    if pu["status"] not in {"submitted", "clarification_needed"}:
        raise HTTPException(status_code=400, detail="This update is not awaiting review.")
    ts = now_iso()
    if body.action == "approve":
        new_status = "pending_client_decision" if pu.get("requires_client_approval") else "approved"
    elif body.action == "return":
        new_status = "clarification_needed"
    elif body.action == "reject":
        new_status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="Invalid action.")
    update = {"status": new_status, "reviewed_by": user["id"], "reviewed_at": ts, "pm_comment": body.comment}
    await db.progress_updates.update_one({"id": pu_id}, {
        "$set": update,
        "$push": {"history": {"status": new_status, "by": user["name"], "at": ts, "comment": body.comment}},
    })
    await log_audit(pu["project_id"], user, f"progress review: {body.action}", "progress_update", pu_id, body.comment)
    if new_status == "approved":
        await apply_approved_progress(pu)
    if new_status == "pending_client_decision" and project.get("client_id"):
        await notify(project["client_id"], "client_decision",
                     "A progress update is awaiting your decision.", pu["project_id"], dedupe_key=f"pending-{pu_id}")
    if new_status in {"clarification_needed", "rejected"}:
        await notify(pu["engineer_id"], "returned",
                     f"Your progress update was {body.action}ed. Please review PM comments.", pu["project_id"])
    pu = await db.progress_updates.find_one({"id": pu_id}, {"_id": 0})
    return await enrich_progress(pu)


async def apply_approved_progress(pu: dict):
    act = await db.activities.find_one({"id": pu["activity_id"]}, {"_id": 0})
    if not act:
        return
    status = "completed" if pu["percent_complete"] >= 100 else "in_progress"
    await db.activities.update_one({"id": pu["activity_id"]}, {"$set": {
        "progress_percent": pu["percent_complete"],
        "quantity_completed": pu.get("quantity_completed") or act.get("quantity_completed", 0),
        "status": status,
    }})
    await recompute_project_progress(pu["project_id"])


@api_router.post("/progress-updates/{pu_id}/client-decision")
async def client_decision(pu_id: str, body: ClientDecisionIn, user: dict = Depends(require_roles("client"))):
    pu = await db.progress_updates.find_one({"id": pu_id}, {"_id": 0})
    if not pu:
        raise HTTPException(status_code=404, detail="Update not found")
    project = await db.projects.find_one({"id": pu["project_id"]}, {"_id": 0})
    if not project or project.get("client_id") != user["id"]:
        raise HTTPException(status_code=403, detail="You cannot decide on this update.")
    if pu["status"] != "pending_client_decision":
        raise HTTPException(status_code=400, detail="This update is not awaiting your decision.")
    if not body.comment.strip():
        raise HTTPException(status_code=400, detail="A comment is required for your decision.")
    mapping = {"approve": "approved", "reject": "rejected", "clarify": "clarification_needed"}
    if body.action not in mapping:
        raise HTTPException(status_code=400, detail="Invalid action.")
    new_status = mapping[body.action]
    ts = now_iso()
    await db.progress_updates.update_one({"id": pu_id}, {
        "$set": {"status": new_status, "client_decision_by": user["id"], "client_decision_at": ts, "client_comment": body.comment},
        "$push": {"history": {"status": new_status, "by": user["name"] + " (Client)", "at": ts, "comment": body.comment}},
    })
    await log_audit(pu["project_id"], user, f"client decision: {body.action}", "progress_update", pu_id, body.comment)
    if new_status == "approved":
        await apply_approved_progress(pu)
    if project.get("project_manager_id"):
        await notify(project["project_manager_id"], "decision",
                     f"Client {body.action}ed a progress update.", pu["project_id"])
    await notify(pu["engineer_id"], "decision", f"Client {body.action}ed your progress update.", pu["project_id"])
    pu = await db.progress_updates.find_one({"id": pu_id}, {"_id": 0})
    return await enrich_progress(pu)


@api_router.post("/progress-updates/{pu_id}/revise")
async def revise_progress(pu_id: str, body: ReviseIn, user: dict = Depends(require_roles("site_engineer"))):
    old = await db.progress_updates.find_one({"id": pu_id}, {"_id": 0})
    if not old:
        raise HTTPException(status_code=404, detail="Update not found")
    if old["engineer_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only revise your own submissions.")
    # Re-verify the engineer is still assigned to the project.
    await get_project_or_403(old["project_id"], user, write=True)
    if old["status"] not in {"clarification_needed", "rejected"}:
        raise HTTPException(status_code=400, detail="Only returned or rejected updates can be revised.")
    project = await db.projects.find_one({"id": old["project_id"]}, {"_id": 0})
    pid = new_id()
    ts = now_iso()
    doc = {
        "id": pid, "project_id": old["project_id"], "activity_id": old["activity_id"],
        "engineer_id": user["id"], "percent_complete": body.percent_complete,
        "quantity_completed": body.quantity_completed, "notes": body.notes,
        "photo_ids": body.photo_ids, "status": "submitted", "version": old["version"] + 1,
        "previous_version_id": pu_id, "pm_comment": None, "client_comment": None,
        "reviewed_by": None, "reviewed_at": None, "client_decision_by": None, "client_decision_at": None,
        "requires_client_approval": old.get("requires_client_approval", False),
        "created_at": ts,
        "history": [{"status": "submitted (revision)", "by": user["name"], "at": ts, "comment": body.notes}],
    }
    await db.progress_updates.insert_one(doc)
    await db.progress_updates.update_one({"id": pu_id}, {"$set": {"superseded_by": pid}})
    await log_audit(old["project_id"], user, "submitted revision", "progress_update", pid, f"v{doc['version']}")
    if project and project.get("project_manager_id"):
        await notify(project["project_manager_id"], "review_required", "A revised progress update was submitted.", old["project_id"])
    doc.pop("_id", None)
    return await enrich_progress(doc)


# ---------------------------------------------------------------------------
# Defects
# ---------------------------------------------------------------------------
DEFECT_FLOW = {"open", "assigned", "in_progress", "awaiting_verification", "reopened", "closed"}


async def enrich_defect(d: dict) -> dict:
    uids = list(filter(None, [d.get("reported_by"), d.get("assigned_to"), d.get("reviewed_by")]))
    users = await db.users.find({"id": {"$in": uids}}, {"_id": 0, "password_hash": 0}).to_list(100)
    umap = {u["id"]: public_user(u) for u in users}
    d["reporter"] = umap.get(d.get("reported_by"))
    d["assignee"] = umap.get(d.get("assigned_to"))
    pids = d.get("before_photo_ids", []) + d.get("closure_photo_ids", [])
    photos = await db.files.find({"id": {"$in": pids}}, {"_id": 0}).to_list(100)
    pmap = {p["id"]: p for p in photos}
    d["before_photos"] = [pmap[i] for i in d.get("before_photo_ids", []) if i in pmap]
    d["closure_photos"] = [pmap[i] for i in d.get("closure_photo_ids", []) if i in pmap]
    return d


@api_router.get("/projects/{project_id}/defects")
async def list_defects(project_id: str, user: dict = Depends(get_current_user)):
    await get_project_or_403(project_id, user)
    defects = await db.defects.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for d in defects:
        await enrich_defect(d)
    return defects


@api_router.post("/projects/{project_id}/defects")
async def create_defect(project_id: str, body: DefectIn, user: dict = Depends(require_roles("admin", "project_manager", "site_engineer"))):
    await get_project_or_403(project_id, user, write=True)
    if body.severity not in {"minor", "major", "critical"}:
        raise HTTPException(status_code=400, detail="Invalid severity.")
    count = await db.defects.count_documents({"project_id": project_id})
    did = new_id()
    escalated = body.severity == "critical"
    status = "assigned" if body.assigned_to else "open"
    ts = now_iso()
    doc = body.model_dump()
    doc.update({
        "id": did, "project_id": project_id, "defect_code": f"DEF-{count + 1:03d}",
        "reported_by": user["id"], "status": status, "escalated": escalated,
        "closure_photo_ids": [], "verification_notes": None, "reviewed_by": None, "closure_date": None,
        "created_at": ts,
        "history": [{"status": status, "by": user["name"], "at": ts, "note": "Defect raised"}],
    })
    await db.defects.insert_one(doc)
    await log_audit(project_id, user, "raised defect", "defect", did, f"{doc['defect_code']} ({body.severity})")
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if project and project.get("project_manager_id") and project["project_manager_id"] != user["id"]:
        msg = f"{'ESCALATED: ' if escalated else ''}Defect {doc['defect_code']} raised ({body.severity})."
        await notify(project["project_manager_id"], "defect", msg, project_id)
    if body.assigned_to:
        await notify(body.assigned_to, "defect", f"Defect {doc['defect_code']} assigned to you.", project_id)
    doc.pop("_id", None)
    return await enrich_defect(doc)


@api_router.post("/defects/{defect_id}/status")
async def update_defect_status(defect_id: str, body: DefectStatusIn, user: dict = Depends(get_current_user)):
    d = await db.defects.find_one({"id": defect_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Defect not found")
    await get_project_or_403(d["project_id"], user, write=True)
    if body.status not in DEFECT_FLOW:
        raise HTTPException(status_code=400, detail="Invalid status.")
    # Only authorized reviewers (admin/PM) may verify & close
    if body.status in {"closed"} and user["role"] not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Only a project manager or admin may verify and close a defect.")
    ts = now_iso()
    update = {"status": body.status}
    if body.closure_photo_ids:
        update["closure_photo_ids"] = d.get("closure_photo_ids", []) + body.closure_photo_ids
    if body.status == "closed":
        update["reviewed_by"] = user["id"]
        update["closure_date"] = ts
        update["verification_notes"] = body.note
    await db.defects.update_one({"id": defect_id}, {
        "$set": update,
        "$push": {"history": {"status": body.status, "by": user["name"], "at": ts, "note": body.note}},
    })
    await log_audit(d["project_id"], user, f"defect status -> {body.status}", "defect", defect_id, body.note)
    reporter_id = d.get("reported_by")
    if reporter_id:
        await notify(reporter_id, "defect", f"Defect {d['defect_code']} is now {body.status.replace('_', ' ')}.", d["project_id"])
    d = await db.defects.find_one({"id": defect_id}, {"_id": 0})
    return await enrich_defect(d)


# ---------------------------------------------------------------------------
# Files (private object storage)
# ---------------------------------------------------------------------------
@api_router.post("/files/upload")
async def upload_file(file: UploadFile = File(...), project_id: str = Form(None), caption: str = Form(""),
                      user: dict = Depends(get_current_user)):
    if project_id:
        # Uploading into a project is a write — clients (read-only) are rejected here.
        await get_project_or_403(project_id, user, write=True)
    elif user["role"] == "client":
        raise HTTPException(status_code=403, detail="Clients cannot upload files.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    fid = new_id()
    path = f"{storage.APP_NAME}/uploads/{user['id']}/{fid}.{ext}"
    data = await file.read()
    content_type = storage.MIME_TYPES.get(ext, file.content_type or "application/octet-stream")
    try:
        result = storage.put_object(path, data, content_type)
    except Exception as e:
        logger.error(f"upload failed: {e}")
        raise HTTPException(status_code=502, detail="File upload failed. Please try again.")
    doc = {
        "id": fid, "storage_path": result["path"], "original_filename": file.filename,
        "content_type": content_type, "size": result.get("size", len(data)),
        "project_id": project_id, "caption": caption, "uploaded_by": user["id"],
        "is_deleted": False, "created_at": now_iso(),
    }
    await db.files.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/projects/{project_id}/photos")
async def project_photos(project_id: str, user: dict = Depends(get_current_user)):
    await get_project_or_403(project_id, user)
    files = await db.files.find(
        {"project_id": project_id, "is_deleted": False, "content_type": {"$regex": "^image/"}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)
    return files


@api_router.get("/files/{file_id}/download")
async def download_file(file_id: str, request: Request, auth: str = Query(None)):
    # img tags cannot send headers: accept ?auth=<token>
    if auth and "Authorization" not in request.headers:
        token = auth
        try:
            payload = decode_token(token)
            u = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not u:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = u
    else:
        user = await get_current_user(request)
    record = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    if record.get("project_id"):
        await get_project_or_403(record["project_id"], user)
    elif record.get("uploaded_by") != user["id"] and user["role"] not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="You cannot access this file.")
    data, ctype = storage.get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type", ctype))


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@api_router.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user)):
    items = await db.notifications.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    unread = sum(1 for i in items if not i.get("read"))
    return {"items": items, "unread": unread}


@api_router.post("/notifications/{nid}/read")
async def read_notification(nid: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.post("/notifications/read-all")
async def read_all(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Audit log & dashboard
# ---------------------------------------------------------------------------
@api_router.get("/projects/{project_id}/audit-log")
async def project_audit(project_id: str, user: dict = Depends(require_roles("admin", "project_manager"))):
    await get_project_or_403(project_id, user)
    return await db.audit_logs.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api_router.get("/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    projects = await list_projects(user)
    pids = [p["id"] for p in projects]
    pending_reviews = 0
    pending_client = 0
    open_defects = 0
    if pids:
        if user["role"] in MANAGER_ROLES:
            pending_reviews = await db.progress_updates.count_documents({"project_id": {"$in": pids}, "status": {"$in": ["submitted", "clarification_needed"]}})
        if user["role"] == "client":
            pending_client = await db.progress_updates.count_documents({"project_id": {"$in": pids}, "status": "pending_client_decision"})
        open_defects = await db.defects.count_documents({"project_id": {"$in": pids}, "status": {"$nin": ["closed"]}})
    notif = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    return {
        "projects": len(projects),
        "active_projects": sum(1 for p in projects if p.get("status") not in ["Completed", "Archived"]),
        "pending_reviews": pending_reviews,
        "pending_client_decisions": pending_client,
        "open_defects": open_defects,
        "unread_notifications": notif,
        "avg_progress": round(sum(p.get("progress_percent", 0) for p in projects) / len(projects), 1) if projects else 0,
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.projects.create_index("code")
    try:
        storage.init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    await seed_module.seed_all(db, hash_password, now_iso)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
