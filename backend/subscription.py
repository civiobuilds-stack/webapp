"""Subscription lifecycle: trial / active / expired, super-admin controls, reminder emails, activation requests."""
import asyncio
import hmac
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import server as S
import emailer

router = APIRouter()
sa_dep = S.require_super_admin()


async def _settings():
    return await S.db.platform_settings.find_one({"id": "billing"}, {"_id": 0}) or {"id": "billing", "payment_instructions": "", "default_trial_days": None}


async def _plans():
    return await S.db.plans.find({}, {"_id": 0}).sort("price_monthly", 1).to_list(100)


@router.get("/subscription/info")
async def info(user: dict = Depends(S.get_identity)):
    ent = await S.db.enterprises.find_one({"id": user.get("company_id")}, {"_id": 0})
    if not ent:
        raise HTTPException(status_code=404, detail="No workspace")
    req = await S.db.activation_requests.find_one({"enterprise_id": ent["id"], "status": "open"}, {"_id": 0})
    return {**S.subscription_info(ent), "trial_end": ent.get("trial_end"), "renewal_date": ent.get("subscription_expires_at"),
            "plans": await _plans(), "payment_instructions": (await _settings()).get("payment_instructions", ""),
            "activation_requested_at": (req or {}).get("created_at"), "enterprise_name": ent.get("name")}


class ActivationIn(BaseModel):
    plan_id: Optional[str] = None
    message: str = Field(default="", max_length=1000)


@router.post("/subscription/activation-request")
async def request_activation(body: ActivationIn, user: dict = Depends(S.get_identity)):
    ent = await S.db.enterprises.find_one({"id": user.get("company_id")}, {"_id": 0})
    if not ent:
        raise HTTPException(status_code=404, detail="No workspace")
    if await S.db.activation_requests.find_one({"enterprise_id": ent["id"], "status": "open"}):
        return {"ok": True, "already_requested": True}
    doc = {"id": S.new_id(), "enterprise_id": ent["id"], "enterprise_name": ent["name"], "plan_id": body.plan_id, "message": body.message,
           "requested_by": user["id"], "requested_by_name": user["name"], "requested_by_email": user.get("email"), "status": "open", "created_at": S.now_iso()}
    await S.db.activation_requests.insert_one(doc)
    async for sa in S.db.users.find({"platform_role": "super_admin"}, {"_id": 0, "id": 1, "email": 1}):
        await S.notify(sa["id"], "enterprise", f"Activation requested by {user['name']} for {ent['name']}.", link="/superadmin")
        await emailer.send_email(to=sa["email"], subject=f"CIVIO activation request — {ent['name']}",
                                 html=f"<p>{user['name']} ({user.get('email')}) requested activation for <b>{ent['name']}</b>"
                                      f"{' on plan ' + body.plan_id if body.plan_id else ''}.</p><p>{body.message}</p>")
    return {"ok": True}


class BillingSettingsIn(BaseModel):
    payment_instructions: str = Field(default="", max_length=4000)
    default_trial_days: Optional[int] = Field(default=None, ge=1, le=365)


@router.get("/superadmin/settings/billing")
async def get_billing_settings(sa: dict = Depends(sa_dep)):
    return await _settings()


@router.put("/superadmin/settings/billing")
async def put_billing_settings(body: BillingSettingsIn, sa: dict = Depends(sa_dep)):
    await S.db.platform_settings.update_one({"id": "billing"}, {"$set": {"id": "billing", **body.model_dump()}}, upsert=True)
    await S.platform_audit(sa, "billing settings updated", None, f"trial days {body.default_trial_days}")
    return await _settings()


class LifecycleIn(BaseModel):
    action: str
    trial_end: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    days: Optional[int] = Field(default=None, ge=1, le=365)
    renewal_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


def _valid(d):
    try:
        date.fromisoformat(d)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Enter a valid date.")


@router.post("/superadmin/enterprises/{eid}/lifecycle")
async def lifecycle(eid: str, body: LifecycleIn, sa: dict = Depends(sa_dep)):
    ent = await S.db.enterprises.find_one({"id": eid}, {"_id": 0})
    if not ent:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    today = datetime.now(timezone.utc).date()
    if body.action == "set_trial":
        _valid(body.trial_end)
        upd = {"subscription_state": "trial", "trial_end": body.trial_end, "trial_start": ent.get("trial_start") or today.isoformat(), "billing_status": "trial"}
    elif body.action == "extend_trial":
        if not body.days:
            raise HTTPException(status_code=400, detail="Enter the number of days to extend.")
        base = max(date.fromisoformat(ent["trial_end"]) if ent.get("trial_end") else today, today)
        upd = {"subscription_state": "trial", "trial_end": (base + timedelta(days=body.days)).isoformat(),
               "trial_start": ent.get("trial_start") or today.isoformat(), "billing_status": "trial"}
    elif body.action == "activate":
        _valid(body.renewal_date)
        if body.renewal_date < today.isoformat():
            raise HTTPException(status_code=400, detail="Renewal date must be today or later.")
        upd = {"subscription_state": "active", "subscription_expires_at": body.renewal_date, "billing_status": "manual"}
    else:
        raise HTTPException(status_code=400, detail="Action must be set_trial, extend_trial or activate.")
    await S.db.enterprises.update_one({"id": eid}, {"$set": upd})
    await S.db.activation_requests.update_many({"enterprise_id": eid, "status": "open"}, {"$set": {"status": "resolved", "resolved_at": S.now_iso()}})
    await S.platform_audit(sa, f"subscription {body.action}", eid, str(upd))
    if ent.get("owner_id") and body.action != "set_trial":
        await S.notify(ent["owner_id"], "enterprise", "Your CIVIO subscription has been updated — full access is available.")
    return await S.enterprise_with_usage(await S.db.enterprises.find_one({"id": eid}, {"_id": 0}))


async def apply_default_trial(eid: str, days: Optional[int] = None):
    days = days or (await _settings()).get("default_trial_days")
    if not days:
        return
    today = datetime.now(timezone.utc).date()
    await S.db.enterprises.update_one({"id": eid, "trial_end": {"$exists": False}}, {"$set": {
        "subscription_state": "trial", "trial_start": today.isoformat(), "trial_end": (today + timedelta(days=days)).isoformat(), "billing_status": "trial"}})


# ---------------------------------------------------------------------------
# Daily reminder emails
# ---------------------------------------------------------------------------
def _email_html(ent, sub, plans, instructions, name):
    d = sub["days_left"]
    what = "trial" if sub["base_state"] == "trial" else "subscription"
    head = (f"Your CIVIO {what} for <b>{ent['name']}</b> ends in <b>{d} day{'s' if d != 1 else ''}</b> ({sub['end_date']})." if d >= 0
            else f"Your CIVIO {what} for <b>{ent['name']}</b> ended on {sub['end_date']}. Your data is safe, but access is paused until renewal.")
    rows = "".join(f"<tr><td style='padding:6px;border:1px solid #ddd'><b>{p['name']}</b><br><small>{p.get('description', '')}</small></td>"
                   f"<td style='padding:6px;border:1px solid #ddd'>₹{p['price_monthly']:,}/{p.get('billing_period', 'monthly')}</td>"
                   f"<td style='padding:6px;border:1px solid #ddd'>{p['max_users']} users · {p['max_projects']} projects · {p['max_storage_mb']} MB</td></tr>" for p in plans)
    pay = (instructions or "Reply to this email and our team will help you renew.").replace("\n", "<br>")
    return (f"<p>Hello {name},</p><p>{head}</p><h3>Plans</h3><table style='border-collapse:collapse'>"
            f"<tr><th style='padding:6px;border:1px solid #ddd'>Plan</th><th style='padding:6px;border:1px solid #ddd'>Price</th>"
            f"<th style='padding:6px;border:1px solid #ddd'>Limits</th></tr>{rows}</table><h3>How to pay</h3><p>{pay}</p><p>— Team CIVIO</p>")


def _due(days_left):
    return days_left in (7, 3, 1) or (days_left < 0 and (-days_left - 1) % 3 == 0)


async def run_reminders():
    today = datetime.now(timezone.utc).date().isoformat()
    plans, instructions = await _plans(), (await _settings()).get("payment_instructions", "")
    async for ent in S.db.enterprises.find({"status": "active"}, {"_id": 0}):
        sub = S.subscription_info(ent)
        if sub["days_left"] is None or not _due(sub["days_left"]):
            continue
        key = f"{ent['id']}:{today}"
        try:
            await S.db.subscription_email_log.insert_one({"key": key, "enterprise_id": ent["id"], "date": today, "days_left": sub["days_left"],
                                                          "state": sub["state"], "created_at": S.now_iso(), "recipients": []})
        except Exception:
            continue
        sent = []
        async for u in S.db.users.find({"company_id": ent["id"], "role": "admin", "is_active": {"$ne": False}}, {"_id": 0, "email": 1, "name": 1}):
            subj = f"CIVIO — {'trial ends in ' + str(sub['days_left']) + ' days' if sub['days_left'] >= 0 else 'subscription expired, renew to continue'}"
            await emailer.send_email(to=u["email"], subject=subj, html=_email_html(ent, sub, plans, instructions, u["name"]))
            sent.append(u["email"])
        await S.db.subscription_email_log.update_one({"key": key}, {"$set": {"recipients": sent}})


@router.post("/cron/subscription-reminders")
async def cron_reminders(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    auth = request.headers.get("authorization", "")
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    if not secret or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    asyncio.create_task(run_reminders())
    return {"accepted": True}


@router.get("/superadmin/subscription-emails")
async def email_log(sa: dict = Depends(sa_dep)):
    return await S.db.subscription_email_log.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


# ---------------------------------------------------------------------------
# Feature requests (any enterprise employee -> Super Admin list)
# ---------------------------------------------------------------------------
class FeatureIn(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=5, max_length=3000)
    priority: str = "medium"


@router.post("/feature-requests")
async def create_feature(body: FeatureIn, user: dict = Depends(S.get_identity)):
    if user["role"] == "client" or user.get("platform_role") == "super_admin":
        raise HTTPException(status_code=403, detail="Feature requests are for company employees.")
    if body.priority not in {"low", "medium", "high"}:
        raise HTTPException(status_code=400, detail="Priority must be low, medium or high.")
    ent = await S.db.enterprises.find_one({"id": user.get("company_id")}, {"_id": 0, "id": 1, "name": 1, "business_type": 1})
    if not ent:
        raise HTTPException(status_code=400, detail="No workspace")
    doc = {"id": S.new_id(), **body.model_dump(), "title": body.title.strip(), "user_id": user["id"], "user_name": user["name"],
           "user_email": user.get("email"), "user_phone": user.get("phone"), "user_role": S.ROLE_NAMES.get(user["role"], user["role"]),
           "enterprise_id": ent["id"], "enterprise_name": ent["name"], "business_type": ent.get("business_type"), "created_at": S.now_iso()}
    await S.db.feature_requests.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/feature-requests/mine")
async def my_features(user: dict = Depends(S.get_identity)):
    return await S.db.feature_requests.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/superadmin/feature-requests")
async def all_features(sa: dict = Depends(sa_dep)):
    return await S.db.feature_requests.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
