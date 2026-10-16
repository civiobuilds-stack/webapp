"""Commercial: labour wage rates, labour cost report (PDF + weekly email), overdue tool reminders."""
import asyncio
import hmac
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field

import server as S
import commercial as C
import emailer
import reports as R

router = APIRouter()
log = logging.getLogger("civio.labour_cost")
OPEN_TOOL = ["issued", "partially_issued", "partially_returned"]


class WagesIn(BaseModel):
    mason_rate: float = Field(ge=0, le=100000)
    helper_rate: float = Field(ge=0, le=100000)


class ProjectWagesIn(BaseModel):
    mason_rate: Optional[float] = Field(default=None, ge=0, le=100000)
    helper_rate: Optional[float] = Field(default=None, ge=0, le=100000)


def _admin(user):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the company admin can do this.")


def _today():
    return datetime.now(timezone.utc).astimezone(C.IST).date()


async def _company_wages(cid):
    w = await S.db.wage_settings.find_one({"company_id": cid}, {"_id": 0})
    return w or {"company_id": cid, "mason_rate": 0, "helper_rate": 0}


def _effective(company, project):
    o = project.get("wage_override") or {}
    return {k: o[k] if o.get(k) is not None else company[k] for k in ("mason_rate", "helper_rate")}


@router.get("/labour/wages")
async def get_wages(user: dict = Depends(C.commercial_user)):
    _admin(user)
    return await _company_wages(user["company_id"])


@router.put("/labour/wages")
async def put_wages(body: WagesIn, user: dict = Depends(C.commercial_user)):
    _admin(user)
    doc = {**body.model_dump(), "company_id": user["company_id"], "updated_at": S.now_iso()}
    await S.db.wage_settings.update_one({"company_id": user["company_id"]}, {"$set": doc}, upsert=True)
    return doc


@router.get("/projects/{pid}/wages")
async def get_project_wages(pid: str, user: dict = Depends(C.commercial_user)):
    project, _ = await C.require_perm(user, pid, "attendance", "view")
    company = await _company_wages(user["company_id"])
    return {"company": company, "override": project.get("wage_override") or {}, "effective": _effective(company, project)}


@router.put("/projects/{pid}/wages")
async def put_project_wages(pid: str, body: ProjectWagesIn, user: dict = Depends(C.commercial_user)):
    project = await S.get_project_or_403(pid, user)
    if not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Only the project manager or admin can set project wage rates.")
    await S.db.projects.update_one({"id": pid}, {"$set": {"wage_override": body.model_dump()}})
    await S.log_audit(pid, user, "set project wage rates", "project", pid, str(body.model_dump()))
    return await get_project_wages(pid, user)


async def project_cost(project, company_w, today):
    rates = _effective(company_w, project)
    start, week_start = today.replace(day=1).isoformat(), (today - timedelta(days=6)).isoformat()
    lo = min(start, week_start)
    rows = await S.db.labour_attendance.find({"project_id": project["id"], "date": {"$gte": lo, "$lte": today.isoformat()}}, {"_id": 0}).to_list(5000)

    def agg(rs):
        m, h = sum(r["masons"] for r in rs), sum(r["helpers"] for r in rs)
        return {"mason_days": m, "helper_days": h, "mason_cost": m * rates["mason_rate"], "helper_cost": h * rates["helper_rate"],
                "total": m * rates["mason_rate"] + h * rates["helper_rate"]}
    days = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        days.append({"date": d, **agg([r for r in rows if r["date"] == d])})
    return {"project": {"id": project["id"], "name": project["name"], "code": project.get("code", "")}, "rates": rates,
            "mtd": agg([r for r in rows if r["date"] >= start]), "week": agg([r for r in rows if r["date"] >= week_start]),
            "days": days, "month": today.strftime("%B %Y"), "as_of": today.isoformat()}


async def company_report(ent, project_ids=None):
    today = _today()
    company_w = await _company_wages(ent["id"])
    q = {"company_id": ent["id"], "is_archived": {"$ne": True}}
    if project_ids is not None:
        q["id"] = {"$in": project_ids}
    return [await project_cost(p, company_w, today) async for p in S.db.projects.find(q, {"_id": 0})]


def _pdf(ent, data, title_code):
    meta = {"title": "Labour Cost Report", "code": title_code, "generated": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
            "revision": "AUTO", "confidential": f"Confidential — {ent.get('display_name') or ent['name']}"}
    return R.build_labour_cost(data, meta, S.report_brand(ent))


@router.get("/projects/{pid}/labour-cost")
async def get_project_cost(pid: str, user: dict = Depends(C.commercial_user)):
    project, _ = await C.require_perm(user, pid, "attendance", "view")
    return await project_cost(project, await _company_wages(user["company_id"]), _today())


@router.get("/projects/{pid}/labour-cost/pdf")
async def project_cost_pdf(pid: str, request: Request, auth: str = Query(None)):
    user = await S.user_from_query_token(request, auth)
    C._commercial(user)
    project, _ = await C.require_perm(user, pid, "attendance", "view")
    data = [await project_cost(project, await _company_wages(user["company_id"]), _today())]
    pdf = await asyncio.to_thread(_pdf, user["_enterprise"], data, f"{project.get('code', '')} · {data[0]['month']}")
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="Labour_Cost_{project.get("code")}.pdf"'})


@router.get("/labour-cost/pdf")
async def company_cost_pdf(request: Request, auth: str = Query(None)):
    user = await S.user_from_query_token(request, auth)
    C._commercial(user)
    _admin(user)
    data = await company_report(user["_enterprise"])
    pdf = await asyncio.to_thread(_pdf, user["_enterprise"], data, _today().strftime("%B %Y"))
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="Labour_Cost_Report.pdf"'})


async def send_cost_report(ent, key, trigger):
    try:
        await S.db.labour_cost_logs.insert_one({"id": S.new_id(), "company_id": ent["id"], "key": key, "trigger": trigger,
                                                "status": "running", "created_at": S.now_iso()})
    except Exception:
        return
    try:
        data = await company_report(ent)
        name = ent.get("display_name") or ent["name"]
        pdf = await asyncio.to_thread(_pdf, ent, data, _today().strftime("%B %Y"))
        owners = await S.db.users.find({"company_id": ent["id"], "role": "admin", "is_active": {"$ne": False}}, {"_id": 0, "email": 1, "name": 1}).to_list(50)
        results = []
        for u in owners:
            mid = await emailer.send_email(to=u["email"], subject=f"Weekly labour cost report — {name}",
                                           html=emailer.labour_cost_email_html(u["name"], name, data),
                                           attachments=[emailer.pdf_attachment(f"Labour_Cost_{_today().isoformat()}.pdf", pdf)])
            results.append({"email": u["email"], "ok": bool(mid)})
        status = "sent" if results and all(r["ok"] for r in results) else ("partial" if any(r["ok"] for r in results) else "failed")
        await S.db.labour_cost_logs.update_one({"company_id": ent["id"], "key": key}, {"$set": {"status": status, "recipients": results, "projects": len(data), "finished_at": S.now_iso()}})
    except Exception as e:
        log.error(f"labour cost report failed for {ent['id']}: {e}")
        await S.db.labour_cost_logs.update_one({"company_id": ent["id"], "key": key}, {"$set": {"status": "failed", "error": str(e)[:300]}})


@router.post("/labour-cost/send-now")
async def cost_send_now(user: dict = Depends(C.commercial_user)):
    _admin(user)
    key = f"manual-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    asyncio.create_task(send_cost_report(user["_enterprise"], key, "manual"))
    return {"queued": True, "key": key}


@router.get("/labour-cost/logs")
async def cost_logs(user: dict = Depends(C.commercial_user)):
    _admin(user)
    return await S.db.labour_cost_logs.find({"company_id": user["company_id"]}, {"_id": 0}).sort("created_at", -1).to_list(20)


# ---------------------------------------------------------------------------
# Overdue tool reminders
# ---------------------------------------------------------------------------
async def remind_overdue(company_id=None):
    today = _today().isoformat()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    q = {"kind": "tool", "status": {"$in": OPEN_TOOL}, "$or": [{"expected_return": {"$nin": [None, ""], "$lt": today}}, {"issued_at": {"$lt": week_ago}}]}
    if company_id:
        q["company_id"] = company_id
    sent = 0
    async for r in S.db.store_requests.find(q, {"_id": 0}):
        try:
            await S.db.tool_reminders.insert_one({"id": S.new_id(), "request_id": r["id"], "date": today, "company_id": r["company_id"], "created_at": S.now_iso()})
        except Exception:
            continue
        project = await S.db.projects.find_one({"id": r["project_id"]}, {"_id": 0})
        if not project:
            continue
        out = r["issued_qty"] - r["returned_qty"] - r["damaged_qty"] - r["lost_qty"]
        if out <= 0:
            continue
        due = (r.get("expected_return") or "")[:10] or (datetime.fromisoformat(r["issued_at"]) + timedelta(days=7)).date().isoformat()
        r["expected_return"] = due
        days = max((_today() - datetime.fromisoformat(due).date()).days, 0)
        holder = await S.db.users.find_one({"id": r["requested_by"]}, {"_id": 0, "id": 1, "email": 1, "name": 1})
        store_ids = [u["id"] async for u in S.db.users.find({"company_id": r["company_id"], "role": {"$in": ["store_incharge", "store_manager"]}, "is_active": {"$ne": False}}, {"_id": 0, "id": 1})]
        cc_ids = list({i for i in await C.recipients_with(project, "store", "approve") + store_ids if i != r["requested_by"]})
        cc = await S.db.users.find({"id": {"$in": cc_ids}, "is_active": {"$ne": False}}, {"_id": 0, "id": 1, "email": 1, "name": 1}).to_list(50)
        link = f"/projects/{r['project_id']}?tab=store"
        msg = f"OVERDUE: {out} {r['unit']} {r['item']} was due back on {r['expected_return'][:10]} ({days} day(s) late) — {project['name']}."
        info = {"item": r["item"], "qty": out, "unit": r["unit"], "due": r["expected_return"][:10], "days": days, "project": project["name"],
                "holder": holder["name"] if holder else r.get("requested_by_name", "")}
        for u in ([holder] if holder else []) + cc:
            await S.notify(u["id"], "tool_overdue", msg, r["project_id"], link=link, dedupe_key=f"tool-overdue-{r['id']}-{today}-{u['id']}", push=True)
        if holder:
            await emailer.send_email(to=holder["email"], subject=f"Tool return overdue — {r['item']}", html=emailer.tool_overdue_email_html(holder["name"], info, False))
        if cc:
            await emailer.send_email(to=[u["email"] for u in cc], subject=f"[CC] Tool return overdue — {r['item']} ({info['holder']})",
                                     html=emailer.tool_overdue_email_html("Store team", info, True))
        sent += 1
    return sent


@router.get("/projects/{pid}/store/overdue")
async def list_overdue(pid: str, user: dict = Depends(C.commercial_user)):
    await C.require_perm(user, pid, "store", "view")
    q = {"project_id": pid, "kind": "tool", "status": {"$in": OPEN_TOOL}, "expected_return": {"$nin": [None, ""], "$lt": _today().isoformat()}}
    return await S.db.store_requests.find(q, {"_id": 0, "history": 0}).to_list(500)


@router.post("/store/overdue/remind-now")
async def remind_now(user: dict = Depends(C.commercial_user)):
    if user["role"] not in S.MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Only admins or project managers can send reminders.")
    return {"reminded": await remind_overdue(user["company_id"])}


# ---------------------------------------------------------------------------
# Crons
# ---------------------------------------------------------------------------
async def _cron_ok(request: Request):
    auth = request.headers.get("authorization", "")
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    if not secret or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid body")


async def _weekly_cost_all():
    iso = _today().isocalendar()
    async for ent in S.db.enterprises.find({"status": "active", "business_type": "commercial"}, {"_id": 0}):
        await send_cost_report(ent, f"week-{iso[0]}-{iso[1]:02d}", "scheduled")


async def _safe(coro):
    try:
        await coro
    except Exception as e:
        log.error(f"cron task failed: {e}")


@router.post("/cron/labour-cost")
async def cron_labour_cost(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    await _cron_ok(request)
    asyncio.create_task(_safe(_weekly_cost_all()))
    return {"accepted": True}


@router.post("/cron/tool-overdue")
async def cron_tool_overdue(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    await _cron_ok(request)
    asyncio.create_task(_safe(remind_overdue()))
    return {"accepted": True}
