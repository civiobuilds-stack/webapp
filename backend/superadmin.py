"""Super Admin platform administration: create enterprises, owner access reset, approval history."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

import server as S

router = APIRouter()
sa_dep = S.require_super_admin()


class EnterpriseCreateIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    business_type: str
    city: str = ""
    owner_name: str = Field(min_length=2, max_length=80)
    owner_email: EmailStr
    phone: str = ""
    plan_id: str = "free"


def _temp():
    return f"Civio@{secrets.randbelow(900000) + 100000}"


@router.post("/superadmin/enterprises")
async def create_enterprise(body: EnterpriseCreateIn, sa: dict = Depends(sa_dep)):
    if body.business_type not in S.MODULES:
        raise HTTPException(status_code=400, detail="Business type must be residential or commercial.")
    email = body.owner_email.lower()
    if await S.db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    plan = await S.db.plans.find_one({"id": body.plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=400, detail="Unknown plan.")
    eid, uid, ts, pw = S.new_id(), S.new_id(), S.now_iso(), _temp()
    await S.db.enterprises.insert_one({
        "id": eid, "name": body.company_name.strip(), "business_type": body.business_type, "city": body.city, "status": "active",
        "status_reason": None, "owner_id": uid, "owner_email": email, "owner_name": body.owner_name, "phone": body.phone,
        "plan_id": plan["id"], "price_monthly": plan["price_monthly"], "billing_status": "trial", "billing_period": plan.get("billing_period", "monthly"),
        "limits": {k: plan[k] for k in ("max_users", "max_projects", "max_storage_mb")}, "created_at": ts, "approved_at": ts,
        "created_by_platform": sa["id"], "status_history": [{"from": None, "to": "active", "reason": "Created by Super Admin", "by": sa["name"], "at": ts}]})
    await S.db.users.insert_one({"id": uid, "email": email, "password_hash": S.hash_password(pw), "name": body.owner_name, "role": "admin",
                                 "phone": body.phone, "company_id": eid, "is_active": True, "is_demo": False, "email_verified": True, "created_at": ts})
    await S.platform_audit(sa, "enterprise created", eid, f"{body.company_name} owner {email}")
    return {"enterprise_id": eid, "login_id": email, "temporary_password": pw}


@router.post("/superadmin/enterprises/{eid}/reset-owner")
async def reset_owner(eid: str, sa: dict = Depends(sa_dep)):
    ent = await S.db.enterprises.find_one({"id": eid}, {"_id": 0})
    if not ent or not ent.get("owner_id"):
        raise HTTPException(status_code=404, detail="Enterprise owner not found")
    owner = await S.db.users.find_one({"id": ent["owner_id"]}, {"_id": 0})
    if not owner or owner.get("platform_role") == "super_admin":
        raise HTTPException(status_code=400, detail="This owner's access cannot be reset here.")
    pw = _temp()
    await S.db.users.update_one({"id": owner["id"]}, {"$set": {"password_hash": S.hash_password(pw), "must_change_password": True, "email_verified": True}})
    await S.db.user_sessions.delete_many({"user_id": owner["id"]})
    await S.platform_audit(sa, "owner access reset", eid, owner["email"])
    return {"login_id": owner["email"], "temporary_password": pw}


@router.get("/superadmin/enterprises/{eid}/history")
async def history(eid: str, sa: dict = Depends(sa_dep)):
    ent = await S.db.enterprises.find_one({"id": eid}, {"_id": 0, "status_history": 1, "created_at": 1, "approved_at": 1})
    if not ent:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    audit = await S.db.platform_audit.find({"enterprise_id": eid}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"status_history": ent.get("status_history", []), "audit": audit, "created_at": ent.get("created_at"), "approved_at": ent.get("approved_at")}
