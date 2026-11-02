"""Individual employee attendance with live selfie + GPS, outside any project (labour crew attendance is separate)."""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile

import server as S
import commercial as C
import storage
from store import _dist

router = APIRouter()
MAX_SELFIE = 6 * 1024 * 1024


def _today():
    return datetime.now(C.IST).date().isoformat()


def _enabled(u):
    return u.get("role") != "client" and u.get("attendance_required", True) is not False


async def _my_projects(user):
    out = {}
    for p in await S.list_projects(user):
        m = await S.db.project_members.find_one({"project_id": p["id"], "user_id": user["id"]}, {"_id": 0, "location_required": 1})
        out[p["id"]] = {"id": p["id"], "name": p["name"], "code": p.get("code"), "geofence": p.get("geofence"),
                        "location_required": bool((m or {}).get("location_required"))}
    return out


def _people_of(project):
    ids = {project.get("project_manager_id"), *project.get("engineer_ids", []), *[t["user_id"] for t in project.get("team", []) if not t.get("removed_at")]}
    return ids - {None}


async def _managed_user_ids(user):
    if user["role"] == "admin":
        return None
    projects = [p for p in await S.list_projects(user) if C._manages(user, p)]
    ids = set()
    for p in projects:
        ids |= _people_of(p)
        ids |= {m["user_id"] async for m in S.db.project_members.find({"project_id": p["id"]}, {"_id": 0, "user_id": 1})}
    return ids - {user["id"]}, [p["id"] for p in projects]


@router.get("/my-attendance/status")
async def status(user: dict = Depends(S.get_current_user)):
    enabled = _enabled(user)
    projects = [{**{k: v for k, v in p.items() if k != "geofence"}, "has_geofence": bool(p["geofence"])} for p in (await _my_projects(user)).values()] if enabled else []
    today = await S.db.staff_attendance.find_one({"user_id": user["id"], "date": _today()}, {"_id": 0})
    can_review = user["role"] in {"admin", "project_manager"}
    return {"enabled": enabled, "projects": projects, "today": today, "needs_check_in": enabled and not today, "can_review": can_review}


@router.post("/my-attendance/check-in")
async def check_in(selfie: UploadFile = File(...), lat: float = Form(...), lng: float = Form(...), accuracy: Optional[float] = Form(None),
                   project_id: str = Form(""), user: dict = Depends(S.get_current_user)):
    if not _enabled(user):
        raise HTTPException(status_code=403, detail="Attendance is switched off for you. Ask your project manager.")
    rows = await _my_projects(user)
    day = _today()
    if await S.db.staff_attendance.find_one({"user_id": user["id"], "date": day}):
        raise HTTPException(status_code=409, detail="You have already checked in today.")
    if not (selfie.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="The selfie must be an image from the camera.")
    data = await selfie.read()
    if not data or len(data) > MAX_SELFIE:
        raise HTTPException(status_code=400, detail="Selfie missing or larger than 6 MB.")
    project, distance = None, None
    if project_id:
        if project_id not in rows:
            raise HTTPException(status_code=400, detail="Choose one of your assigned projects or Office / off-site.")
        project = rows[project_id]
        g = project.get("geofence")
        if g:
            distance = round(_dist(g["lat"], g["lng"], lat, lng))
        if project.get("location_required"):
            if not g:
                raise HTTPException(status_code=400, detail="Site location is required but the PM has not set the site geofence yet.")
            slack = min(accuracy or 0, 100)
            if distance - slack > g["radius_m"]:
                raise HTTPException(status_code=403, detail=f"You are {distance} m from site (GPS accuracy ±{round(accuracy or 0)} m) — the allowed radius is {int(g['radius_m'])} m. Move closer and retry.")
    aid = S.new_id()
    path = f"civio/{user['company_id']}/selfies/{user['id']}/{day}-{aid}.jpg"
    await asyncio.to_thread(storage.put_object, path, data, selfie.content_type)
    doc = {"id": aid, "company_id": user["company_id"], "user_id": user["id"], "user_name": user["name"], "role": user["role"], "date": day,
           "project_id": project["id"] if project else None, "project_name": project["name"] if project else "Office / off-site",
           "check_in": {"at": S.now_iso(), "lat": lat, "lng": lng, "accuracy": accuracy, "distance_m": distance}, "selfie_path": path,
           "check_out": None, "created_at": S.now_iso()}
    try:
        await S.db.staff_attendance.insert_one(doc)
    except Exception:
        raise HTTPException(status_code=409, detail="You have already checked in today.")
    doc.pop("_id", None)
    doc.pop("selfie_path", None)
    return doc


@router.post("/my-attendance/check-out")
async def check_out(lat: float = Form(...), lng: float = Form(...), user: dict = Depends(S.get_current_user)):
    a = await S.db.staff_attendance.find_one({"user_id": user["id"], "date": _today()}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=400, detail="Check in first.")
    if a.get("check_out"):
        raise HTTPException(status_code=409, detail="You have already checked out today.")
    await S.db.staff_attendance.update_one({"id": a["id"]}, {"$set": {"check_out": {"at": S.now_iso(), "lat": lat, "lng": lng}}})
    return await S.db.staff_attendance.find_one({"id": a["id"]}, {"_id": 0, "selfie_path": 0})


@router.get("/my-attendance/mine")
async def mine(user: dict = Depends(S.get_current_user)):
    return await S.db.staff_attendance.find({"user_id": user["id"]}, {"_id": 0, "selfie_path": 0}).sort("date", -1).to_list(120)


@router.get("/my-attendance/team")
async def team(day: Optional[str] = Query(None, alias="date"), user: dict = Depends(S.get_current_user)):
    if user["role"] not in {"admin", "project_manager"}:
        raise HTTPException(status_code=403, detail="Only the admin and project managers can view team attendance.")
    q = {"company_id": user["company_id"], "date": day or _today()}
    scope = await _managed_user_ids(user)
    uq = {"company_id": user["company_id"], "role": {"$ne": "client"}, "is_active": {"$ne": False}, "attendance_required": {"$ne": False}}
    if scope is not None:
        q["user_id"] = {"$in": list(scope[0])}
        uq["id"] = {"$in": list(scope[0])}
    expected = {u["id"] async for u in S.db.users.find(uq, {"_id": 0, "id": 1})}
    rows = await S.db.staff_attendance.find(q, {"_id": 0, "selfie_path": 0}).sort("check_in.at", 1).to_list(2000)
    present = {r["user_id"] for r in rows}
    absent = await S.db.users.find({"id": {"$in": list(expected - present)}, "is_active": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(1000)
    return {"date": q["date"], "records": rows, "not_checked_in": absent}


@router.get("/my-attendance/{aid}/selfie")
async def selfie(aid: str, request: Request, auth: str = Query(None)):
    user = await S.user_from_query_token(request, auth)
    a = await S.db.staff_attendance.find_one({"id": aid, "company_id": user["company_id"]}, {"_id": 0})
    if not a or not a.get("selfie_path"):
        raise HTTPException(status_code=404, detail="Not found")
    ok = a["user_id"] == user["id"] or user["role"] == "admin"
    if not ok and user["role"] == "project_manager":
        ok = a["user_id"] in (await _managed_user_ids(user))[0]
    if not ok:
        raise HTTPException(status_code=403, detail="Not allowed.")
    data, ctype = await asyncio.to_thread(storage.get_object, a["selfie_path"])
    return Response(content=data, media_type=ctype or "image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


async def _can_manage(user, uid):
    if user["role"] == "admin":
        return True
    if user["role"] != "project_manager":
        return False
    return uid in (await _managed_user_ids(user))[0]


@router.get("/my-attendance/people")
async def people(user: dict = Depends(S.get_current_user)):
    if user["role"] not in {"admin", "project_manager"}:
        raise HTTPException(status_code=403, detail="Not allowed.")
    q = {"company_id": user["company_id"], "role": {"$ne": "client"}, "is_active": {"$ne": False}}
    scope = await _managed_user_ids(user)
    if scope is not None:
        q["id"] = {"$in": list(scope[0])}
    rows = await S.db.users.find(q, {"_id": 0, "id": 1, "name": 1, "role": 1, "attendance_required": 1}).sort("name", 1).to_list(2000)
    return [{**r, "attendance_required": r.get("attendance_required", True) is not False} for r in rows]


class ToggleIn(BaseModel):
    attendance_required: bool


@router.put("/my-attendance/people/{uid}")
async def toggle(uid: str, body: ToggleIn, user: dict = Depends(S.get_current_user)):
    if not await _can_manage(user, uid):
        raise HTTPException(status_code=403, detail="You can only change attendance for people on projects you manage.")
    t = await S.db.users.find_one({"id": uid, "company_id": user["company_id"]}, {"_id": 0, "name": 1})
    if not t:
        raise HTTPException(status_code=404, detail="Person not found")
    await S.db.users.update_one({"id": uid}, {"$set": {"attendance_required": body.attendance_required}})
    await S.db.attendance_audit.insert_one({"id": S.new_id(), "company_id": user["company_id"], "user_id": uid, "action": "toggle",
                                            "value": body.attendance_required, "by": user["id"], "by_name": user["name"], "at": S.now_iso()})
    return {"ok": True}


class CorrectionIn(BaseModel):
    user_id: str
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    check_in: str = Field(pattern=r"^\d{2}:\d{2}$")
    check_out: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    project_id: str = ""
    reason: str = Field(min_length=5, max_length=500)


def _iso(day, hm):
    return datetime.fromisoformat(f"{day}T{hm}:00").replace(tzinfo=C.IST).astimezone(timezone.utc).isoformat()


@router.post("/my-attendance/correct")
async def correct(body: CorrectionIn, user: dict = Depends(S.get_current_user)):
    if not await _can_manage(user, body.user_id):
        raise HTTPException(status_code=403, detail="Only the admin or the person's PM can correct attendance.")
    if body.date > _today():
        raise HTTPException(status_code=400, detail="You cannot correct a future date.")
    if body.check_out and body.check_out <= body.check_in:
        raise HTTPException(status_code=400, detail="Check-out must be after check-in.")
    t = await S.db.users.find_one({"id": body.user_id, "company_id": user["company_id"]}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Person not found")
    project = await S.db.projects.find_one({"id": body.project_id, "company_id": user["company_id"]}, {"_id": 0, "id": 1, "name": 1}) if body.project_id else None
    existing = await S.db.staff_attendance.find_one({"user_id": body.user_id, "date": body.date}, {"_id": 0})
    entry = {"by": user["id"], "by_name": user["name"], "at": S.now_iso(), "reason": body.reason,
             "before": {"check_in": (existing or {}).get("check_in", {}).get("at") if existing else None,
                        "check_out": ((existing or {}).get("check_out") or {}).get("at") if existing else None}}
    cin = {**((existing or {}).get("check_in") or {}), "at": _iso(body.date, body.check_in), "manual": True}
    cout = {**((existing or {}).get("check_out") or {}), "at": _iso(body.date, body.check_out), "manual": True} if body.check_out else (existing or {}).get("check_out")
    upd = {"check_in": cin, "check_out": cout, "manual": True, "project_id": project["id"] if project else (existing or {}).get("project_id"),
           "project_name": project["name"] if project else (existing or {}).get("project_name", "Office / off-site")}
    if existing:
        await S.db.staff_attendance.update_one({"id": existing["id"]}, {"$set": upd, "$push": {"corrections": entry}})
        aid = existing["id"]
    else:
        aid = S.new_id()
        await S.db.staff_attendance.insert_one({"id": aid, "company_id": user["company_id"], "user_id": t["id"], "user_name": t["name"], "role": t["role"],
                                                "date": body.date, "selfie_path": None, "created_at": S.now_iso(), **upd, "corrections": [entry]})
    await S.db.attendance_audit.insert_one({"id": S.new_id(), "company_id": user["company_id"], "user_id": t["id"], "attendance_id": aid, "action": "correction",
                                            **entry, "after": {"check_in": cin["at"], "check_out": (cout or {}).get("at")}})
    if upd["project_id"]:
        await S.log_audit(upd["project_id"], user, "corrected attendance", "staff_attendance", aid, f"{t['name']} {body.date} {body.check_in}-{body.check_out or ''}: {body.reason}")
    await S.notify(t["id"], "attendance", f"{user['name']} corrected your attendance for {body.date}: {body.reason}")
    return await S.db.staff_attendance.find_one({"id": aid}, {"_id": 0, "selfie_path": 0})
