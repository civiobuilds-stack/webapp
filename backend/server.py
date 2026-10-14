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
import reports as reports_module
import emailer
import csv
import asyncio
import io
import secrets
import httpx

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="CIVIO BUILD API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("civio")

MANAGER_ROLES = {"admin", "project_manager"}
ROLE_NAMES = {"admin": "Owner / Admin", "project_manager": "Project Manager", "site_engineer": "Site Engineer", "client": "Client"}
DEFAULT_ENTERPRISE_ID = "civio"
ALL_MODULES = {"activities", "progress", "defects", "procurement", "reports", "photos", "team", "audit"}
MODULES = {
    "commercial": (ALL_MODULES - {"defects"}) | {"dpr", "attendance", "members", "store"},
    "residential": ALL_MODULES - {"procurement"},
}
DEFAULT_PLANS = [
    {"id": "free", "name": "Free Trial", "price_monthly": 0, "max_users": 5, "max_projects": 2, "max_storage_mb": 500,
     "description": "Try CIVIO with a small team."},
    {"id": "starter", "name": "Starter", "price_monthly": 2999, "max_users": 15, "max_projects": 10, "max_storage_mb": 5120,
     "description": "For growing builders and small PMCs."},
    {"id": "professional", "name": "Professional", "price_monthly": 7999, "max_users": 50, "max_projects": 40, "max_storage_mb": 25600,
     "description": "Multi-site firms with full workflows."},
    {"id": "enterprise", "name": "Enterprise", "price_monthly": 19999, "max_users": 500, "max_projects": 300, "max_storage_mb": 204800,
     "description": "Large enterprises with custom limits."},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
async def get_current_user(request: Request) -> dict:
    user = await get_identity(request)
    enforce_password_changed(user)
    return await enforce_active_enterprise(user)


def enforce_password_changed(user: dict):
    if user.get("must_change_password"):
        raise HTTPException(status_code=403, detail={"code": "password_change_required",
                                                     "message": "Please change your password to continue."})


async def enforce_active_enterprise(user: dict) -> dict:
    ent = await db.enterprises.find_one({"id": user.get("company_id")}, {"_id": 0})
    if not ent or ent.get("status") != "active":
        raise HTTPException(status_code=403, detail={
            "code": "enterprise_inactive", "status": (ent or {}).get("status", "missing"),
            "message": "Your company workspace is not active yet."})
    user["_enterprise"] = ent
    return user


async def user_from_query_token(request: Request, auth: Optional[str]) -> dict:
    if auth and "Authorization" not in request.headers:
        try:
            payload = decode_token(auth)
            u = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not u or not u.get("is_active", True) or await db.revoked_tokens.find_one({"jti": payload.get("jti")}):
            raise HTTPException(status_code=401, detail="Invalid token")
        enforce_password_changed(u)
        return await enforce_active_enterprise(u)
    return await get_current_user(request)


def require_super_admin():
    async def checker(request: Request) -> dict:
        user = await get_identity(request)
        if user.get("platform_role") != "super_admin":
            raise HTTPException(status_code=403, detail="Super Admin access required.")
        enforce_password_changed(user)
        return user
    return checker


def require_module(user: dict, module: str):
    ent = user.get("_enterprise") or {}
    if module not in MODULES.get(ent.get("business_type", "commercial"), set()):
        raise HTTPException(status_code=403, detail="This module is not available for your workspace type.")


async def ensure_company_users(ids, user: dict):
    ids = {i for i in ids if i}
    if not ids:
        return
    n = await db.users.count_documents({"id": {"$in": list(ids)}, "company_id": user["company_id"]})
    if n != len(ids):
        raise HTTPException(status_code=400, detail="One or more selected users do not belong to your company.")


async def enforce_limit(user: dict, kind: str):
    ent = user.get("_enterprise") or {}
    limits = ent.get("limits") or {}
    cid = user["company_id"]
    if kind == "users":
        used = await db.users.count_documents({"company_id": cid, "is_active": {"$ne": False}})
        cap = limits.get("max_users")
    elif kind == "projects":
        used = await db.projects.count_documents({"company_id": cid, "is_archived": {"$ne": True}})
        cap = limits.get("max_projects")
    else:
        used = await storage_used_mb(cid)
        cap = limits.get("max_storage_mb")
    if cap is not None and used >= cap:
        raise HTTPException(status_code=403, detail=f"Your plan limit for {kind} has been reached ({cap}). Please contact CIVIO to upgrade.")


async def storage_used_mb(company_id: str) -> float:
    agg = await db.files.aggregate([
        {"$match": {"company_id": company_id, "is_deleted": False}},
        {"$group": {"_id": None, "total": {"$sum": "$size"}}},
    ]).to_list(1)
    return round((agg[0]["total"] if agg else 0) / (1024 * 1024), 2)


async def get_identity(request: Request) -> dict:
    # 1) App JWT (access_token cookie or Bearer)
    token = request.cookies.get("access_token")
    bearer = request.headers.get("Authorization", "")
    if bearer.startswith("Bearer "):
        bearer = bearer[7:]
    else:
        bearer = ""
    jwt_token = token or bearer
    if jwt_token:
        try:
            payload = decode_token(jwt_token)
            if payload.get("type") == "access" and not await db.revoked_tokens.find_one({"jti": payload.get("jti")}):
                user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
                if user and user.get("is_active", True):
                    user["_jti"] = payload.get("jti")
                    user["_exp"] = payload.get("exp")
                    return user
        except Exception:
            pass
    # 2) Emergent Google session_token (session_token cookie or Bearer)
    session_token = request.cookies.get("session_token") or bearer
    if session_token:
        sess = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
        if sess:
            exp = sess["expires_at"]
            if isinstance(exp, str):
                exp = datetime.fromisoformat(exp)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp >= datetime.now(timezone.utc):
                user = await db.users.find_one({"id": sess["user_id"]}, {"_id": 0, "password_hash": 0})
                if user and user.get("is_active", True):
                    return user
    raise HTTPException(status_code=401, detail="Not authenticated")


def require_roles(*roles):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        return user
    return checker


async def get_project_or_403(project_id: str, user: dict, write: bool = False) -> dict:
    project = await db.projects.find_one({"id": project_id, "company_id": user.get("company_id")}, {"_id": 0})
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
    if not allowed and not write and role != "client":
        allowed = bool(await db.project_members.find_one({"project_id": project_id, "user_id": uid}))
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


async def notify(user_id, ntype, message, project_id=None, link=None, dedupe_key=None, push=False):
    if dedupe_key:
        existing = await db.notifications.find_one({"user_id": user_id, "dedupe_key": dedupe_key, "read": False})
        if existing:
            return
    if push:
        import commercial
        url = link or (f"/projects/{project_id}" if project_id else "/notifications")
        asyncio.create_task(commercial.send_push([user_id], "CIVIO", message, url, ntype))
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
    phone: str = Field(min_length=6)
    role: str = "client"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class OtpVerifyIn(BaseModel):
    email: EmailStr
    code: str


class OtpResendIn(BaseModel):
    email: EmailStr


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


class MaterialRequestIn(BaseModel):
    item: str
    quantity: float
    unit: str = "nos"
    needed_by: Optional[str] = None
    notes: str = ""


class MaterialDecisionIn(BaseModel):
    action: str  # authorize | reject
    comment: str = ""


class SupplierIn(BaseModel):
    name: str
    contact: str = ""
    categories: str = ""


class POItemIn(BaseModel):
    description: str
    quantity: float
    unit: str = "nos"
    rate: float = 0


class PurchaseOrderIn(BaseModel):
    supplier_id: str
    material_request_id: Optional[str] = None
    items: List[POItemIn]
    notes: str = ""


class POStatusIn(BaseModel):
    status: Optional[str] = None  # draft | approved | ordered | delivered | accepted
    delivered_qty: Optional[float] = None
    accepted_qty: Optional[float] = None
    invoice_status: Optional[str] = None  # pending | paid | overdue
    note: str = ""


class ReportIn(BaseModel):
    type: str  # progress | completion | cost
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    recommendations: str = ""


class EnterpriseRegisterIn(BaseModel):
    company_name: str = Field(min_length=2)
    business_type: str
    city: str = ""
    name: str
    email: EmailStr
    phone: str = Field(min_length=6)
    password: str = Field(min_length=6)


class EnterpriseStatusIn(BaseModel):
    status: str  # active | rejected | suspended
    reason: str = ""


class SubscriptionIn(BaseModel):
    plan_id: str
    price_monthly: Optional[float] = None
    max_users: Optional[int] = None
    max_projects: Optional[int] = None
    max_storage_mb: Optional[int] = None
    billing_status: str = "manual"


class InviteIn(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    role: str
    phone: Optional[str] = None


class InviteAcceptIn(BaseModel):
    password: str = Field(min_length=6)
    phone: str = Field(min_length=6)
    name: Optional[str] = None


class EnterpriseSettingsIn(BaseModel):
    display_name: str = Field(min_length=2)
    tagline: str = ""
    address: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    website: str = ""


class PlanIn(BaseModel):
    name: str
    price_monthly: float = Field(ge=0)
    max_users: int = Field(ge=1)
    max_projects: int = Field(ge=1)
    max_storage_mb: int = Field(ge=1)
    description: str = ""


def public_user(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "phone": u.get("phone"),
            "platform_role": u.get("platform_role"), "company_id": u.get("company_id"),
            "must_change_password": bool(u.get("must_change_password")),
            "employee_id": u.get("employee_id"), "designation": u.get("designation"),
            "department": u.get("department"), "reporting_manager_id": u.get("reporting_manager_id")}


def public_enterprise(e: Optional[dict]) -> Optional[dict]:
    if not e:
        return None
    bt = e.get("business_type", "commercial")
    return {"id": e["id"], "name": e["name"], "business_type": bt, "status": e.get("status"),
            "status_reason": e.get("status_reason"), "plan_id": e.get("plan_id"),
            "display_name": e.get("display_name") or e["name"], "has_logo": bool(e.get("logo_path")),
            "modules": sorted(MODULES.get(bt, ALL_MODULES))}


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
def set_auth_cookie(response: Response, token: str):
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")


OTP_TTL_MIN = 10


async def issue_otp(user_doc: dict):
    code = f"{secrets.randbelow(1000000):06d}"
    expires = (datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MIN)).isoformat()
    await db.users.update_one({"id": user_doc["id"]}, {"$set": {
        "otp_code": code, "otp_expires": expires, "otp_attempts": 0,
    }})
    await emailer.send_email(
        to=user_doc["email"],
        subject="Your CIVIO verification code",
        html=emailer.otp_email_html(user_doc["name"], code),
    )


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
        "name": body.name, "role": body.role, "phone": body.phone,
        "company_id": "civio", "is_active": True, "is_demo": False,
        "email_verified": False, "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    await issue_otp(doc)
    return {"requires_verification": True, "email": email}


@api_router.post("/auth/register-enterprise")
async def register_enterprise(body: EnterpriseRegisterIn):
    email = body.email.lower()
    if body.business_type not in MODULES:
        raise HTTPException(status_code=400, detail="Business type must be residential or commercial.")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    plan = await db.plans.find_one({"id": "free"}, {"_id": 0}) or DEFAULT_PLANS[0]
    eid, uid, ts = new_id(), new_id(), now_iso()
    ent = {
        "id": eid, "name": body.company_name.strip(), "business_type": body.business_type, "city": body.city,
        "status": "pending", "status_reason": None, "owner_id": uid, "owner_email": email,
        "owner_name": body.name, "phone": body.phone, "plan_id": plan["id"],
        "price_monthly": plan["price_monthly"], "billing_status": "manual",
        "limits": {k: plan[k] for k in ("max_users", "max_projects", "max_storage_mb")},
        "created_at": ts, "approved_at": None,
    }
    await db.enterprises.insert_one(ent)
    await db.users.insert_one({
        "id": uid, "email": email, "password_hash": hash_password(body.password), "name": body.name,
        "role": "admin", "phone": body.phone, "company_id": eid, "is_active": True, "is_demo": False,
        "email_verified": False, "created_at": ts,
    })
    await issue_otp({"id": uid, "email": email, "name": body.name})
    async for sa in db.users.find({"platform_role": "super_admin"}, {"_id": 0, "id": 1}):
        await notify(sa["id"], "enterprise", f"New enterprise registration: {ent['name']} ({body.business_type}).",
                     link="/superadmin")
    return {"requires_verification": True, "email": email, "enterprise_status": "pending"}


@api_router.post("/auth/verify-otp")
async def verify_otp(body: OtpVerifyIn, response: Response):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")
    if user.get("email_verified"):
        token = create_access_token(user["id"], email, user["role"])
        set_auth_cookie(response, token)
        return {"access_token": token, "user": public_user(user)}
    if not user.get("otp_code") or not user.get("otp_expires"):
        raise HTTPException(status_code=400, detail="No active code. Please request a new one.")
    if user.get("otp_attempts", 0) >= 6:
        raise HTTPException(status_code=429, detail="Too many attempts. Please request a new code.")
    if datetime.now(timezone.utc) > datetime.fromisoformat(user["otp_expires"]):
        raise HTTPException(status_code=400, detail="This code has expired. Please request a new one.")
    if body.code.strip() != user["otp_code"]:
        await db.users.update_one({"id": user["id"]}, {"$inc": {"otp_attempts": 1}})
        raise HTTPException(status_code=400, detail="Incorrect code. Please try again.")
    await db.users.update_one({"id": user["id"]}, {
        "$set": {"email_verified": True},
        "$unset": {"otp_code": "", "otp_expires": "", "otp_attempts": ""},
    })
    token = create_access_token(user["id"], email, user["role"])
    set_auth_cookie(response, token)
    return {"access_token": token, "user": public_user(user)}


@api_router.post("/auth/resend-otp")
async def resend_otp(body: OtpResendIn):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if user and not user.get("email_verified"):
        await issue_otp(user)
    return {"ok": True}


@api_router.post("/auth/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user.get("email_verified") is False:
        await issue_otp(user)
        raise HTTPException(status_code=403, detail={"code": "email_not_verified", "email": email,
                                                     "message": "Please verify your email. We've sent you a new code."})
    token = create_access_token(user["id"], email, user["role"])
    set_auth_cookie(response, token)
    return {"access_token": token, "user": public_user(user)}


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response, user: dict = Depends(get_identity)):
    st = request.cookies.get("session_token")
    if st:
        await db.user_sessions.delete_one({"session_token": st})
    if user.get("_jti"):
        await db.revoked_tokens.update_one({"jti": user["_jti"]}, {"$set": {
            "jti": user["_jti"], "expires_at": datetime.fromtimestamp(user["_exp"], tz=timezone.utc)}}, upsert=True)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


class GoogleSessionIn(BaseModel):
    session_id: str


@api_router.post("/auth/google/session")
async def google_session(body: GoogleSessionIn, response: Response):
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": body.session_id},
            )
        r.raise_for_status()
        data = r.json()
    except Exception:
        raise HTTPException(status_code=401, detail="Google sign-in failed. Please try again.")
    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="Google sign-in did not return an email.")
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="No CIVIO account exists for this Google email. Register your company or ask your admin to invite you.")
    session_token = data.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="Google sign-in failed. Please try again.")
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user["id"], "session_token": session_token,
        "expires_at": expires.isoformat(), "created_at": now_iso(),
    })
    response.set_cookie("session_token", session_token, httponly=True, secure=True,
                        samesite="none", max_age=7 * 24 * 3600, path="/")
    return {"user": public_user(user)}


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@api_router.post("/auth/change-password")
async def change_password(body: ChangePasswordIn, user: dict = Depends(get_identity)):
    doc = await db.users.find_one({"id": user["id"]})
    if not doc.get("password_hash") or not verify_password(body.current_password, doc["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="New password must be different from the current one.")
    if not (any(c.isdigit() for c in body.new_password) and any(c.isalpha() for c in body.new_password)):
        raise HTTPException(status_code=400, detail="Password must contain letters and numbers.")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(body.new_password),
                                                            "must_change_password": False, "password_changed_at": now_iso()}})
    return {"ok": True}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_identity)):
    out = public_user(user)
    out["enterprise"] = public_enterprise(await db.enterprises.find_one({"id": user.get("company_id")}, {"_id": 0}))
    return out


@api_router.get("/enterprise/usage")
async def enterprise_usage(user: dict = Depends(require_roles("admin", "project_manager"))):
    ent = user["_enterprise"]
    cid = user["company_id"]
    plan = await db.plans.find_one({"id": ent.get("plan_id")}, {"_id": 0})
    return {
        "enterprise": public_enterprise(ent), "plan": plan, "limits": ent.get("limits") or {},
        "price_monthly": ent.get("price_monthly"),
        "usage": {
            "users": await db.users.count_documents({"company_id": cid, "is_active": {"$ne": False}}),
            "projects": await db.projects.count_documents({"company_id": cid, "is_archived": {"$ne": True}}),
            "storage_mb": await storage_used_mb(cid),
        },
    }


# ---------------------------------------------------------------------------
# Users / directory
# ---------------------------------------------------------------------------
@api_router.get("/users")
async def list_users(role: Optional[str] = None, user: dict = Depends(require_roles("admin", "project_manager"))):
    q = {"company_id": user["company_id"]}
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
    if body.role in {"site_engineer", "client"} and not (body.phone and len(body.phone) >= 6):
        raise HTTPException(status_code=400, detail="A phone number is required for engineers and clients.")
    await enforce_limit(user, "users")
    uid = new_id()
    doc = {
        "id": uid, "email": email, "password_hash": hash_password(body.password),
        "name": body.name, "role": body.role, "phone": body.phone,
        "company_id": user["company_id"], "is_active": True, "is_demo": False,
        "email_verified": False, "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    await issue_otp(doc)
    out = public_user(doc)
    out["requires_verification"] = True
    return out


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
    q = {"company_id": user["company_id"], "is_archived": {"$ne": True}}
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
    if await db.projects.find_one({"code": body.code, "company_id": user["company_id"]}):
        raise HTTPException(status_code=400, detail="Project code already in use.")
    await ensure_company_users([body.client_id, body.project_manager_id, *body.engineer_ids], user)
    await enforce_limit(user, "projects")
    pid = new_id()
    doc = body.model_dump()
    doc.update({
        "id": pid, "company_id": user["company_id"],
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
    await ensure_company_users([body.client_id, body.project_manager_id, *body.engineer_ids], user)
    data = body.model_dump()
    data.pop("code", None)  # code immutable
    await db.projects.update_one({"id": project_id}, {"$set": data})
    await log_audit(project_id, user, "updated project", "project", project_id, body.name)
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    return await enrich_project(p)


@api_router.post("/projects/{project_id}/assign")
async def assign(project_id: str, body: AssignIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    await get_project_or_403(project_id, user, write=True)
    await ensure_company_users([body.client_id, body.project_manager_id, *(body.engineer_ids or [])], user)
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
    await ensure_company_users([body.assigned_engineer_id], user)
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
                     f"Progress update submitted for {act['name']} — review required.", project_id, push=True)
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
                     "A progress update is awaiting your decision.", pu["project_id"], dedupe_key=f"pending-{pu_id}", push=True)
    if new_status in {"clarification_needed", "rejected"}:
        await notify(pu["engineer_id"], "returned",
                     f"Your progress update was {body.action}ed. Please review PM comments.", pu["project_id"], push=True)
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
    project = await db.projects.find_one({"id": pu["project_id"], "company_id": user["company_id"]}, {"_id": 0})
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
                     f"Client {body.action}ed a progress update.", pu["project_id"], push=True)
    await notify(pu["engineer_id"], "decision", f"Client {body.action}ed your progress update.", pu["project_id"], push=True)
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
        await notify(project["project_manager_id"], "review_required", "A revised progress update was submitted.", old["project_id"], push=True)
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
    require_module(user, "defects")
    defects = await db.defects.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for d in defects:
        await enrich_defect(d)
    return defects


@api_router.post("/projects/{project_id}/defects")
async def create_defect(project_id: str, body: DefectIn, user: dict = Depends(require_roles("admin", "project_manager", "site_engineer"))):
    await get_project_or_403(project_id, user, write=True)
    require_module(user, "defects")
    await ensure_company_users([body.assigned_to], user)
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
    require_module(user, "defects")
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
    await enforce_limit(user, "storage")
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
        "company_id": user["company_id"], "is_deleted": False, "created_at": now_iso(),
    }
    await db.files.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def client_visible_file_ids(project_id: str) -> set:
    """Photos a client may see: those attached to updates pending their decision or approved,
    plus closure/before photos on closed defects. Draft/internal media stays hidden."""
    ids = set()
    pus = await db.progress_updates.find(
        {"project_id": project_id, "status": {"$in": ["pending_client_decision", "approved"]}},
        {"_id": 0, "photo_ids": 1},
    ).to_list(1000)
    for pu in pus:
        ids.update(pu.get("photo_ids", []))
    defs = await db.defects.find(
        {"project_id": project_id, "status": "closed"}, {"_id": 0, "before_photo_ids": 1, "closure_photo_ids": 1},
    ).to_list(1000)
    for d in defs:
        ids.update(d.get("before_photo_ids", []))
        ids.update(d.get("closure_photo_ids", []))
    return ids


@api_router.get("/projects/{project_id}/photos")
async def project_photos(project_id: str, user: dict = Depends(get_current_user)):
    await get_project_or_403(project_id, user)
    files = await db.files.find(
        {"project_id": project_id, "is_deleted": False, "content_type": {"$regex": "^image/"}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)
    if user["role"] == "client":
        visible = await client_visible_file_ids(project_id)
        files = [f for f in files if f["id"] in visible]
    return files


@api_router.get("/files/{file_id}/download")
async def download_file(file_id: str, request: Request, auth: str = Query(None)):
    # img tags cannot send headers: accept ?auth=<token>
    user = await user_from_query_token(request, auth)
    record = await db.files.find_one({"id": file_id, "is_deleted": False, "company_id": user["company_id"]}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    if record.get("project_id"):
        await get_project_or_403(record["project_id"], user)
        if user["role"] == "client":
            visible = await client_visible_file_ids(record["project_id"])
            if file_id not in visible:
                raise HTTPException(status_code=403, detail="This photo has not been shared with you.")
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


# ---------------------------------------------------------------------------
# Procurement & cost
# ---------------------------------------------------------------------------
async def enrich_mr(m: dict) -> dict:
    uids = list(filter(None, [m.get("requested_by"), m.get("decided_by")]))
    users = await db.users.find({"id": {"$in": uids}}, {"_id": 0, "password_hash": 0}).to_list(50)
    umap = {u["id"]: public_user(u) for u in users}
    m["requester"] = umap.get(m.get("requested_by"))
    return m


@api_router.get("/projects/{project_id}/material-requests")
async def list_material_requests(project_id: str, user: dict = Depends(get_current_user)):
    project = await get_project_or_403(project_id, user)
    if user["role"] == "client" and not project.get("client_budget_visible"):
        raise HTTPException(status_code=403, detail="Procurement is not shared for this project.")
    items = await db.material_requests.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for m in items:
        await enrich_mr(m)
    return items


@api_router.post("/projects/{project_id}/material-requests")
async def create_material_request(project_id: str, body: MaterialRequestIn, user: dict = Depends(require_roles("admin", "project_manager", "site_engineer"))):
    await get_project_or_403(project_id, user, write=True)
    require_module(user, "procurement")
    mid = new_id()
    ts = now_iso()
    doc = body.model_dump()
    doc.update({
        "id": mid, "project_id": project_id, "requested_by": user["id"], "status": "requested",
        "decided_by": None, "decision_comment": None, "created_at": ts,
        "history": [{"status": "requested", "by": user["name"], "at": ts, "note": body.notes}],
    })
    await db.material_requests.insert_one(doc)
    await log_audit(project_id, user, "raised material request", "material_request", mid, f"{body.quantity} {body.unit} {body.item}")
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if project and project.get("project_manager_id") and project["project_manager_id"] != user["id"]:
        await notify(project["project_manager_id"], "material", f"Material request raised: {body.item}.", project_id, push=True)
    doc.pop("_id", None)
    return await enrich_mr(doc)


@api_router.post("/material-requests/{mr_id}/decision")
async def decide_material_request(mr_id: str, body: MaterialDecisionIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    mr = await db.material_requests.find_one({"id": mr_id}, {"_id": 0})
    if not mr:
        raise HTTPException(status_code=404, detail="Request not found")
    await get_project_or_403(mr["project_id"], user, write=True)
    if mr["status"] != "requested":
        raise HTTPException(status_code=400, detail="This request has already been decided.")
    if body.action not in {"authorize", "reject"}:
        raise HTTPException(status_code=400, detail="Invalid action.")
    new_status = "authorized" if body.action == "authorize" else "rejected"
    ts = now_iso()
    await db.material_requests.update_one({"id": mr_id}, {
        "$set": {"status": new_status, "decided_by": user["id"], "decision_comment": body.comment},
        "$push": {"history": {"status": new_status, "by": user["name"], "at": ts, "note": body.comment}},
    })
    await log_audit(mr["project_id"], user, f"material request {new_status}", "material_request", mr_id, body.comment)
    await notify(mr["requested_by"], "material", f"Your material request for {mr['item']} was {new_status}.", mr["project_id"], push=True)
    mr = await db.material_requests.find_one({"id": mr_id}, {"_id": 0})
    return await enrich_mr(mr)


@api_router.get("/suppliers")
async def list_suppliers(user: dict = Depends(require_roles("admin", "project_manager"))):
    return await db.suppliers.find({"company_id": user["company_id"]}, {"_id": 0}).sort("name", 1).to_list(1000)


@api_router.post("/suppliers")
async def create_supplier(body: SupplierIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    require_module(user, "procurement")
    doc = body.model_dump()
    doc.update({"id": new_id(), "company_id": user["company_id"], "created_at": now_iso()})
    await db.suppliers.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def enrich_po(po: dict) -> dict:
    supplier = await db.suppliers.find_one({"id": po.get("supplier_id")}, {"_id": 0})
    po["supplier"] = supplier
    return po


@api_router.get("/projects/{project_id}/purchase-orders")
async def list_purchase_orders(project_id: str, user: dict = Depends(get_current_user)):
    project = await get_project_or_403(project_id, user)
    if user["role"] == "client" and not project.get("client_budget_visible"):
        raise HTTPException(status_code=403, detail="Procurement is not shared for this project.")
    pos = await db.purchase_orders.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for po in pos:
        await enrich_po(po)
    return pos


@api_router.post("/projects/{project_id}/purchase-orders")
async def create_purchase_order(project_id: str, body: PurchaseOrderIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    await get_project_or_403(project_id, user, write=True)
    require_module(user, "procurement")
    supplier = await db.suppliers.find_one({"id": body.supplier_id, "company_id": user["company_id"]}, {"_id": 0})
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    items = [i.model_dump() for i in body.items]
    for i in items:
        i["amount"] = round((i.get("quantity", 0) or 0) * (i.get("rate", 0) or 0), 2)
    total = round(sum(i["amount"] for i in items), 2)
    count = await db.purchase_orders.count_documents({"project_id": project_id})
    pid = new_id()
    ts = now_iso()
    doc = {
        "id": pid, "project_id": project_id, "po_number": f"PO-{count + 1:03d}",
        "supplier_id": body.supplier_id, "material_request_id": body.material_request_id,
        "items": items, "total_amount": total, "notes": body.notes,
        "status": "draft", "delivered_qty": 0, "accepted_qty": 0, "invoice_status": "pending",
        "created_by": user["id"], "created_at": ts,
        "history": [{"status": "draft", "by": user["name"], "at": ts, "note": "PO created"}],
    }
    await db.purchase_orders.insert_one(doc)
    await log_audit(project_id, user, "created purchase order", "purchase_order", pid, f"{doc['po_number']} {_inr_plain(total)}")
    if body.material_request_id:
        await db.material_requests.update_one({"id": body.material_request_id, "project_id": project_id}, {"$set": {"status": "ordered"}})
    doc.pop("_id", None)
    return await enrich_po(doc)


@api_router.post("/purchase-orders/{po_id}/status")
async def update_po_status(po_id: str, body: POStatusIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    await get_project_or_403(po["project_id"], user, write=True)
    update = {}
    PO_FLOW = {"draft", "approved", "ordered", "delivered", "accepted", "cancelled"}
    if body.status is not None:
        if body.status not in PO_FLOW:
            raise HTTPException(status_code=400, detail="Invalid PO status.")
        update["status"] = body.status
    if body.delivered_qty is not None:
        update["delivered_qty"] = body.delivered_qty
    if body.accepted_qty is not None:
        update["accepted_qty"] = body.accepted_qty
    if body.invoice_status is not None:
        if body.invoice_status not in {"pending", "paid", "overdue"}:
            raise HTTPException(status_code=400, detail="Invalid invoice status.")
        update["invoice_status"] = body.invoice_status
    ts = now_iso()
    await db.purchase_orders.update_one({"id": po_id}, {
        "$set": update,
        "$push": {"history": {"status": body.status or po["status"], "by": user["name"], "at": ts, "note": body.note}},
    })
    await log_audit(po["project_id"], user, "updated purchase order", "purchase_order", po_id, str(update))
    po = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    return await enrich_po(po)


def _inr_plain(v):
    try:
        return f"Rs {float(v):,.0f}"
    except Exception:
        return "Rs 0"


@api_router.get("/projects/{project_id}/cost-summary")
async def cost_summary(project_id: str, user: dict = Depends(get_current_user)):
    project = await get_project_or_403(project_id, user)
    if user["role"] == "client" and not project.get("client_budget_visible"):
        raise HTTPException(status_code=403, detail="Budget is not shared for this project.")
    pos = await db.purchase_orders.find({"project_id": project_id, "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(1000)
    committed = round(sum(po.get("total_amount", 0) for po in pos if po.get("status") in {"approved", "ordered", "delivered", "accepted"}), 2)
    actual = round(sum(po.get("total_amount", 0) for po in pos if po.get("invoice_status") == "paid"), 2)
    budget = project.get("contract_value") or 0
    forecast = max(committed, actual)
    return {
        "budget": budget, "committed": committed, "actual": actual, "forecast": forecast,
        "variance": round(budget - forecast, 2), "po_count": len(pos),
        "outstanding_invoices": round(sum(po.get("total_amount", 0) for po in pos if po.get("invoice_status") in {"pending", "overdue"}), 2),
    }


# ---------------------------------------------------------------------------
# PDF reports
# ---------------------------------------------------------------------------
async def _build_report_ctx(project, rtype, body, user):
    acts = await db.activities.find({"project_id": project["id"]}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    mstones = await db.milestones.find({"project_id": project["id"]}, {"_id": 0}).sort("due_date", 1).to_list(1000)
    defects = await db.defects.find({"project_id": project["id"], "status": {"$ne": "closed"}}, {"_id": 0}).sort("severity", 1).to_list(1000)

    pu_query = {"project_id": project["id"], "status": {"$in": ["submitted", "reviewed", "pending_client_decision", "approved"]}}
    if body.period_start:
        pu_query["created_at"] = {"$gte": body.period_start}
    if body.period_end:
        pu_query.setdefault("created_at", {})["$lte"] = body.period_end + "T23:59:59"
    pus = await db.progress_updates.find(pu_query, {"_id": 0}).sort("created_at", -1).to_list(200)
    act_map = {a["id"]: a for a in acts}
    eng_ids = list({u["engineer_id"] for u in pus})
    engs = await db.users.find({"id": {"$in": eng_ids}}, {"_id": 0, "name": 1, "id": 1}).to_list(100)
    eng_map = {e["id"]: e["name"] for e in engs}
    progress = [{"activity_name": act_map.get(u["activity_id"], {}).get("name", "—"),
                 "percent_complete": u.get("percent_complete", 0), "status": u.get("status", ""),
                 "engineer_name": eng_map.get(u.get("engineer_id"), "—"), "created_at": u.get("created_at")} for u in pus]

    # Photos within period from the progress updates
    photo_ids = []
    for u in pus:
        photo_ids.extend(u.get("photo_ids", []))
    photo_ids = photo_ids[:9]
    photo_docs = await db.files.find({"id": {"$in": photo_ids}, "is_deleted": False}, {"_id": 0}).to_list(50)
    photos = []
    fetched = await asyncio.gather(*[asyncio.to_thread(storage.get_object, pd["storage_path"]) for pd in photo_docs],
                                   return_exceptions=True)
    for pd, res in zip(photo_docs, fetched):
        if isinstance(res, Exception):
            logger.error(f"report photo fetch failed: {res}")
            continue
        photos.append((res[0], pd.get("caption") or pd.get("original_filename"), pd.get("created_at")))

    cost = None
    if rtype in ("cost", "completion"):
        pos = await db.purchase_orders.find({"project_id": project["id"], "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(1000)
        committed = sum(po.get("total_amount", 0) for po in pos if po.get("status") in {"approved", "ordered", "delivered", "accepted"})
        actual = sum(po.get("total_amount", 0) for po in pos if po.get("invoice_status") == "paid")
        budget = project.get("contract_value") or 0
        forecast = max(committed, actual)
        cost = {"budget": budget, "committed": committed, "actual": actual, "forecast": forecast, "variance": budget - forecast}

    return {"project": project, "activities": acts, "milestones": mstones, "defects": defects,
            "progress": progress, "photos": photos, "cost": cost}


@api_router.get("/projects/{project_id}/reports")
async def list_reports(project_id: str, user: dict = Depends(get_current_user)):
    await get_project_or_403(project_id, user)
    return await db.reports.find({"project_id": project_id}, {"_id": 0}).sort("generated_at", -1).to_list(500)


@api_router.post("/projects/{project_id}/reports")
async def generate_report(project_id: str, body: ReportIn, user: dict = Depends(require_roles("admin", "project_manager"))):
    project = await get_project_or_403(project_id, user, write=True)
    if body.type not in {"progress", "completion", "cost"}:
        raise HTTPException(status_code=400, detail="Unknown report type.")
    titles = {"progress": "Construction Progress Report", "completion": "Project Completion Report", "cost": "Project Cost Summary"}
    rev_count = await db.reports.count_documents({"project_id": project_id, "type": body.type})
    revision = f"{body.type[:3].upper()}-{rev_count + 1:02d}"
    meta = {
        "title": titles[body.type], "code": project.get("code", ""),
        "period_start": body.period_start, "period_end": body.period_end,
        "generated": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
        "revision": revision, "recommendations": body.recommendations,
        "confidential": f"Confidential — {user['_enterprise'].get('display_name') or user['_enterprise']['name']}",
    }
    ctx = await _build_report_ctx(project, body.type, body, user)
    ctx["meta"] = meta
    ctx["brand"] = report_brand(user["_enterprise"])
    pdf_bytes = reports_module.build_report(body.type, ctx)
    rid = new_id()
    path = f"{storage.APP_NAME}/reports/{project_id}/{rid}.pdf"
    try:
        result = storage.put_object(path, pdf_bytes, "application/pdf")
    except Exception as e:
        logger.error(f"report upload failed: {e}")
        raise HTTPException(status_code=502, detail="Could not store the generated report.")
    doc = {
        "id": rid, "project_id": project_id, "type": body.type, "title": titles[body.type],
        "revision": revision, "period_start": body.period_start, "period_end": body.period_end,
        "storage_path": result["path"], "size": result.get("size", len(pdf_bytes)),
        "generated_by": user["id"], "generated_by_name": user["name"], "generated_at": now_iso(),
    }
    await db.reports.insert_one(doc)
    await log_audit(project_id, user, "generated report", "report", rid, f"{titles[body.type]} ({revision})")
    # Notify + email client and assigned engineers with the PDF attached.
    recipient_ids = list(filter(None, [project.get("client_id")] + project.get("engineer_ids", [])))
    recipients = await db.users.find({"id": {"$in": recipient_ids}}, {"_id": 0}).to_list(100)
    attachment = emailer.pdf_attachment(f"{titles[body.type].replace(' ', '_')}_{revision}.pdf", pdf_bytes)
    for r in recipients:
        await notify(r["id"], "report", f"A new report was published: {titles[body.type]}.", project_id, push=True)
    mailable = [r for r in recipients if r.get("email")]

    async def _send_all():
        for r in mailable:
            await emailer.send_email(
                to=r["email"],
                subject=f"{titles[body.type]} — {project.get('name', 'CIVIO project')}",
                html=emailer.report_email_html(r["name"], project.get("name", ""), titles[body.type], revision),
                attachments=[attachment],
            )
    asyncio.create_task(_send_all())
    doc.pop("_id", None)
    doc["emailed_to"] = [r["email"] for r in mailable]
    return doc


@api_router.get("/reports/{report_id}/download")
async def download_report(report_id: str, request: Request, auth: str = Query(None)):
    user = await user_from_query_token(request, auth)
    rec = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")
    await get_project_or_403(rec["project_id"], user)
    data, _ = storage.get_object(rec["storage_path"])
    fname = f"{rec['title'].replace(' ', '_')}_{rec['revision']}.pdf"
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


# ---------------------------------------------------------------------------
# Audit export (CSV)
# ---------------------------------------------------------------------------
@api_router.get("/projects/{project_id}/audit-log/export")
async def export_audit_csv(project_id: str, request: Request, auth: str = Query(None)):
    user = await user_from_query_token(request, auth)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can export the audit log.")
    project = await get_project_or_403(project_id, user)
    logs = await db.audit_logs.find({"project_id": project_id}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Timestamp (UTC)", "Actor", "Action", "Entity Type", "Entity ID", "Details"])
    for l in logs:
        writer.writerow([l.get("created_at", ""), l.get("actor_name", ""), l.get("action", ""),
                         l.get("entity_type", ""), l.get("entity_id", ""), l.get("details", "")])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"civio_audit_{project.get('code', 'project')}_{stamp}.csv"
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ---------------------------------------------------------------------------
# Team invites
# ---------------------------------------------------------------------------
INVITE_TTL_DAYS = 7


def _hash_token(t: str) -> str:
    import hashlib
    return hashlib.sha256(t.encode()).hexdigest()


def public_invite(i: dict) -> dict:
    return {k: i.get(k) for k in ("id", "name", "email", "role", "phone", "status", "invited_by_name", "created_at", "expires_at", "accepted_at")}


@api_router.get("/invites")
async def list_invites(user: dict = Depends(require_roles("admin", "project_manager"))):
    items = await db.invites.find({"company_id": user["company_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    now = now_iso()
    for i in items:
        if i["status"] == "pending" and i["expires_at"] < now:
            i["status"] = "expired"
    return [public_invite(i) for i in items]


@api_router.post("/invites")
async def create_invite(body: InviteIn, request: Request, user: dict = Depends(require_roles("admin", "project_manager"))):
    if body.role not in {"site_engineer", "client", "project_manager"}:
        raise HTTPException(status_code=400, detail="Invalid role.")
    if body.role == "project_manager" and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can invite project managers.")
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    origin = (request.headers.get("origin") or "").rstrip("/")
    if not origin.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invites must be sent from the secure CIVIO web app.")
    await enforce_limit(user, "users")
    await db.invites.update_many({"company_id": user["company_id"], "email": email, "status": "pending"},
                                 {"$set": {"status": "revoked"}})
    token = secrets.token_urlsafe(32)
    ts = datetime.now(timezone.utc)
    doc = {
        "id": new_id(), "token_hash": _hash_token(token), "company_id": user["company_id"],
        "name": body.name, "email": email, "role": body.role, "phone": body.phone, "status": "pending",
        "invited_by": user["id"], "invited_by_name": user["name"], "created_at": ts.isoformat(),
        "expires_at": (ts + timedelta(days=INVITE_TTL_DAYS)).isoformat(), "accepted_at": None,
    }
    await db.invites.insert_one(doc)
    link = f"{origin}/invite/{token}"
    ent = user["_enterprise"]
    mid = await emailer.send_email(
        to=email, subject=f"You're invited to join {ent.get('display_name') or ent['name']} on CIVIO",
        html=emailer.invite_email_html(body.name, ent.get("display_name") or ent["name"], user["name"],
                                       ROLE_NAMES.get(body.role, body.role), link),
    )
    out = public_invite(doc)
    out["invite_link"] = link
    out["emailed"] = bool(mid)
    return out


@api_router.delete("/invites/{invite_id}")
async def revoke_invite(invite_id: str, user: dict = Depends(require_roles("admin", "project_manager"))):
    res = await db.invites.update_one({"id": invite_id, "company_id": user["company_id"], "status": "pending"},
                                      {"$set": {"status": "revoked"}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"ok": True}


async def _load_invite(token: str) -> tuple:
    inv = await db.invites.find_one({"token_hash": _hash_token(token)}, {"_id": 0})
    if not inv or inv["status"] != "pending" or inv["expires_at"] < now_iso():
        raise HTTPException(status_code=404, detail="This invite link is invalid or has expired.")
    ent = await db.enterprises.find_one({"id": inv["company_id"]}, {"_id": 0})
    if not ent or ent.get("status") != "active":
        raise HTTPException(status_code=404, detail="This invite link is invalid or has expired.")
    return inv, ent


@api_router.get("/invites/token/{token}")
async def invite_info(token: str):
    inv, ent = await _load_invite(token)
    return {"name": inv["name"], "email": inv["email"], "role": inv["role"], "phone": inv.get("phone"),
            "company": ent.get("display_name") or ent["name"], "business_type": ent.get("business_type")}


@api_router.post("/invites/token/{token}/accept")
async def accept_invite(token: str, body: InviteAcceptIn, response: Response):
    inv, ent = await _load_invite(token)
    if await db.users.find_one({"email": inv["email"]}):
        raise HTTPException(status_code=400, detail="An account with this email already exists. Please sign in.")
    await enforce_limit({"company_id": ent["id"], "_enterprise": ent}, "users")
    uid = new_id()
    doc = {
        "id": uid, "email": inv["email"], "password_hash": hash_password(body.password),
        "name": (body.name or inv["name"]).strip(), "role": inv["role"], "phone": body.phone,
        "company_id": ent["id"], "is_active": True, "is_demo": False, "email_verified": True,
        "invited_by": inv["invited_by"], "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    await db.invites.update_one({"id": inv["id"]}, {"$set": {"status": "accepted", "accepted_at": now_iso(), "user_id": uid}})
    await notify(inv["invited_by"], "invite", f"{doc['name']} accepted your invite and joined as {ROLE_NAMES.get(inv['role'])}.", link="/people")
    token_out = create_access_token(uid, inv["email"], inv["role"])
    set_auth_cookie(response, token_out)
    return {"access_token": token_out, "user": public_user(doc)}


# ---------------------------------------------------------------------------
# Company settings & branding
# ---------------------------------------------------------------------------
BRAND_FIELDS = ("display_name", "tagline", "address", "contact_email", "contact_phone", "website")


@api_router.get("/enterprise/settings")
async def get_enterprise_settings(user: dict = Depends(get_current_user)):
    ent = user["_enterprise"]
    out = {k: ent.get(k) or "" for k in BRAND_FIELDS}
    out["display_name"] = ent.get("display_name") or ent["name"]
    out.update({"name": ent["name"], "business_type": ent.get("business_type"), "has_logo": bool(ent.get("logo_path"))})
    return out


@api_router.put("/enterprise/settings")
async def update_enterprise_settings(body: EnterpriseSettingsIn, user: dict = Depends(require_roles("admin"))):
    data = {k: v.strip() for k, v in body.model_dump().items()}
    await db.enterprises.update_one({"id": user["company_id"]}, {"$set": data})
    return {"ok": True, **data}


@api_router.post("/enterprise/logo")
async def upload_logo(file: UploadFile = File(...), user: dict = Depends(require_roles("admin"))):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in {"png", "jpg", "jpeg"}:
        raise HTTPException(status_code=400, detail="Logo must be a PNG or JPG image.")
    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo must be under 2 MB.")
    path = f"{storage.APP_NAME}/branding/{user['company_id']}/{new_id()}.{ext}"
    try:
        result = storage.put_object(path, data, storage.MIME_TYPES[ext])
    except Exception as e:
        logger.error(f"logo upload failed: {e}")
        raise HTTPException(status_code=502, detail="Logo upload failed. Please try again.")
    await db.enterprises.update_one({"id": user["company_id"]}, {"$set": {"logo_path": result["path"], "logo_type": storage.MIME_TYPES[ext]}})
    return {"ok": True, "has_logo": True}


@api_router.delete("/enterprise/logo")
async def delete_logo(user: dict = Depends(require_roles("admin"))):
    await db.enterprises.update_one({"id": user["company_id"]}, {"$unset": {"logo_path": "", "logo_type": ""}})
    return {"ok": True, "has_logo": False}


@api_router.get("/enterprise/logo")
async def get_logo(request: Request, auth: str = Query(None)):
    user = await user_from_query_token(request, auth)
    ent = user["_enterprise"]
    if not ent.get("logo_path"):
        raise HTTPException(status_code=404, detail="No logo")
    data, ctype = storage.get_object(ent["logo_path"])
    return Response(content=data, media_type=ent.get("logo_type") or ctype, headers={"Cache-Control": "private, max-age=300"})


def report_brand(ent: dict) -> dict:
    logo = None
    if ent.get("logo_path"):
        try:
            logo, _ = storage.get_object(ent["logo_path"])
        except Exception as e:
            logger.error(f"report logo fetch failed: {e}")
    name = ent.get("display_name") or ent["name"]
    contact = " · ".join(filter(None, [ent.get("contact_email"), ent.get("contact_phone"), ent.get("website")]))
    return {"name": name, "tagline": ent.get("tagline") or "Construction Project Management",
            "logo": logo, "contact": contact, "address": ent.get("address") or ""}


# ---------------------------------------------------------------------------
# Super Admin (platform scope)
# ---------------------------------------------------------------------------
async def platform_audit(actor, action, enterprise_id, details=""):
    await db.platform_audit.insert_one({
        "id": new_id(), "actor_id": actor["id"], "actor_name": actor["name"], "action": action,
        "enterprise_id": enterprise_id, "details": details, "created_at": now_iso(),
    })


async def enterprise_with_usage(e: dict) -> dict:
    cid = e["id"]
    e["usage"] = {
        "users": await db.users.count_documents({"company_id": cid, "is_active": {"$ne": False}}),
        "projects": await db.projects.count_documents({"company_id": cid, "is_archived": {"$ne": True}}),
        "storage_mb": await storage_used_mb(cid),
    }
    return e


@api_router.get("/superadmin/overview")
async def sa_overview(sa: dict = Depends(require_super_admin())):
    ents = await db.enterprises.find({}, {"_id": 0}).to_list(10000)
    by_status = {s: sum(1 for e in ents if e.get("status") == s) for s in ("pending", "active", "suspended", "rejected")}
    by_type = {t: sum(1 for e in ents if e.get("business_type") == t) for t in MODULES}
    mrr = sum(e.get("price_monthly") or 0 for e in ents if e.get("status") == "active")
    return {"enterprises": len(ents), "by_status": by_status, "by_type": by_type, "mrr": mrr,
            "users": await db.users.count_documents({}), "projects": await db.projects.count_documents({"is_archived": {"$ne": True}})}


@api_router.get("/superadmin/enterprises")
async def sa_list_enterprises(status: Optional[str] = None, q: Optional[str] = None, sa: dict = Depends(require_super_admin())):
    query = {}
    if status:
        query["status"] = status
    if q:
        import re
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"name": rx}, {"owner_email": rx}, {"city": rx}]
    ents = await db.enterprises.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [await enterprise_with_usage(e) for e in ents]


@api_router.post("/superadmin/enterprises/{eid}/status")
async def sa_set_status(eid: str, body: EnterpriseStatusIn, sa: dict = Depends(require_super_admin())):
    if body.status not in {"active", "rejected", "suspended"}:
        raise HTTPException(status_code=400, detail="Invalid status.")
    if eid == DEFAULT_ENTERPRISE_ID and body.status != "active":
        raise HTTPException(status_code=400, detail="The platform's own workspace cannot be deactivated.")
    ent = await db.enterprises.find_one({"id": eid}, {"_id": 0})
    if not ent:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    if body.status in {"rejected", "suspended"} and not body.reason.strip():
        raise HTTPException(status_code=400, detail="Please give a reason.")
    update = {"status": body.status, "status_reason": body.reason or None, "status_updated_at": now_iso()}
    if body.status == "active" and not ent.get("approved_at"):
        update["approved_at"] = now_iso()
    await db.enterprises.update_one({"id": eid}, {"$set": update})
    await platform_audit(sa, f"enterprise -> {body.status}", eid, body.reason)
    if ent.get("owner_id"):
        msg = {"active": f"Your workspace {ent['name']} is approved and active.",
               "rejected": f"Your workspace registration was rejected: {body.reason}",
               "suspended": f"Your workspace has been suspended: {body.reason}"}[body.status]
        await notify(ent["owner_id"], "enterprise", msg)
        if ent.get("owner_email"):
            await emailer.send_email(to=ent["owner_email"], subject=f"CIVIO workspace update — {ent['name']}",
                                     html=f"<p>Hello {ent.get('owner_name', '')},</p><p>{msg}</p><p>— Team CIVIO</p>")
    return await enterprise_with_usage(await db.enterprises.find_one({"id": eid}, {"_id": 0}))


@api_router.put("/superadmin/enterprises/{eid}/subscription")
async def sa_set_subscription(eid: str, body: SubscriptionIn, sa: dict = Depends(require_super_admin())):
    ent = await db.enterprises.find_one({"id": eid}, {"_id": 0})
    if not ent:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    plan = await db.plans.find_one({"id": body.plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=400, detail="Unknown plan.")
    limits = {k: getattr(body, k) if getattr(body, k) is not None else plan[k]
              for k in ("max_users", "max_projects", "max_storage_mb")}
    if any(v < 1 for v in limits.values()):
        raise HTTPException(status_code=400, detail="Limits must be at least 1.")
    price = body.price_monthly if body.price_monthly is not None else plan["price_monthly"]
    await db.enterprises.update_one({"id": eid}, {"$set": {
        "plan_id": plan["id"], "limits": limits, "price_monthly": max(price, 0), "billing_status": body.billing_status,
    }})
    await platform_audit(sa, "subscription updated", eid, f"{plan['name']} ₹{price} {limits}")
    return await enterprise_with_usage(await db.enterprises.find_one({"id": eid}, {"_id": 0}))


@api_router.get("/superadmin/plans")
async def sa_list_plans(sa: dict = Depends(require_super_admin())):
    return await db.plans.find({}, {"_id": 0}).sort("price_monthly", 1).to_list(100)


@api_router.put("/superadmin/plans/{plan_id}")
async def sa_update_plan(plan_id: str, body: PlanIn, sa: dict = Depends(require_super_admin())):
    res = await db.plans.update_one({"id": plan_id}, {"$set": body.model_dump()})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Plan not found")
    await platform_audit(sa, "plan updated", None, f"{plan_id}: {body.model_dump()}")
    return await db.plans.find_one({"id": plan_id}, {"_id": 0})


@api_router.get("/superadmin/audit")
async def sa_audit(sa: dict = Depends(require_super_admin())):
    return await db.platform_audit.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


import commercial  # noqa: E402
api_router.include_router(commercial.router)
import store as store_module  # noqa: E402
api_router.include_router(store_module.router)


async def migrate_multitenant():
    for p in DEFAULT_PLANS:
        await db.plans.update_one({"id": p["id"]}, {"$setOnInsert": p}, upsert=True)
    ent_plan = DEFAULT_PLANS[-1]
    await db.enterprises.update_one({"id": DEFAULT_ENTERPRISE_ID}, {"$setOnInsert": {
        "id": DEFAULT_ENTERPRISE_ID, "name": "CIVIO PMC", "business_type": "commercial", "city": "Mumbai",
        "status": "active", "status_reason": None, "owner_id": "user-admin",
        "owner_email": os.environ["ADMIN_EMAIL"].lower(), "owner_name": "Civio Owner", "phone": None,
        "plan_id": ent_plan["id"], "price_monthly": 0, "billing_status": "internal",
        "limits": {k: ent_plan[k] for k in ("max_users", "max_projects", "max_storage_mb")},
        "created_at": now_iso(), "approved_at": now_iso(),
    }}, upsert=True)
    missing = {"$or": [{"company_id": {"$exists": False}}, {"company_id": None}]}
    for coll in ("users", "projects", "suppliers"):
        await db[coll].update_many(missing, {"$set": {"company_id": DEFAULT_ENTERPRISE_ID}})
    async for f in db.files.find(missing, {"_id": 0, "id": 1, "project_id": 1, "uploaded_by": 1}):
        src = None
        if f.get("project_id"):
            src = await db.projects.find_one({"id": f["project_id"]}, {"_id": 0, "company_id": 1})
        if not src and f.get("uploaded_by"):
            src = await db.users.find_one({"id": f["uploaded_by"]}, {"_id": 0, "company_id": 1})
        await db.files.update_one({"id": f["id"]}, {"$set": {"company_id": (src or {}).get("company_id", DEFAULT_ENTERPRISE_ID)}})
    await db.users.update_one({"email": os.environ["ADMIN_EMAIL"].lower()}, {"$set": {"platform_role": "super_admin"}})
    await db.enterprises.create_index("id", unique=True)
    await db.projects.create_index([("company_id", 1), ("code", 1)])
    await db.files.create_index([("company_id", 1), ("is_deleted", 1)])
    await db.dprs.create_index([("project_id", 1), ("report_date", 1)], unique=True)
    await db.boq_items.create_index([("project_id", 1), ("code", 1)], unique=True)
    await db.store_stock.create_index([("project_id", 1), ("item_key", 1)], unique=True)
    await db.project_members.create_index([("project_id", 1), ("user_id", 1)], unique=True)
    await db.attendance.create_index([("project_id", 1), ("user_id", 1), ("date", 1)], unique=True)
    await db.digest_logs.create_index([("company_id", 1), ("key", 1)], unique=True)
    await db.push_subscriptions.create_index("endpoint", unique=True)
    await db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.users.create_index([("company_id", 1), ("employee_id", 1)], unique=True,
                                partialFilterExpression={"employee_id": {"$type": "string"}})


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
    # Legacy/demo accounts predate OTP — mark them verified so they remain usable.
    await db.users.update_many({"email_verified": {"$exists": False}}, {"$set": {"email_verified": True}})
    await migrate_multitenant()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
