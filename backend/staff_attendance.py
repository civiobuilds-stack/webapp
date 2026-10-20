"""Individual employee attendance with live selfie + GPS, outside any project (labour crew attendance is separate)."""
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile

import server as S
import commercial as C
import storage
from store import _dist

router = APIRouter()
MAX_SELFIE = 6 * 1024 * 1024


def _today():
    return datetime.now(C.IST).date().isoformat()


async def _assignments(uid):
    return await S.db.project_members.find({"user_id": uid, "attendance_required": True}, {"_id": 0}).to_list(200)


async def _managed_user_ids(user):
    if user["role"] == "admin":
        return None
    pids = [p["id"] for p in await S.list_projects(user) if C._manages(user, p)]
    ids = {m["user_id"] async for m in S.db.project_members.find({"project_id": {"$in": pids}, "attendance_required": True}, {"_id": 0, "user_id": 1})}
    return ids, pids


@router.get("/my-attendance/status")
async def status(user: dict = Depends(S.get_current_user)):
    rows = await _assignments(user["id"])
    projects = []
    for m in rows:
        p = await S.db.projects.find_one({"id": m["project_id"], "is_deleted": {"$ne": True}}, {"_id": 0, "id": 1, "name": 1, "code": 1, "geofence": 1})
        if p:
            projects.append({"id": p["id"], "name": p["name"], "code": p.get("code"), "location_required": bool(m.get("location_required")),
                             "has_geofence": bool(p.get("geofence"))})
    today = await S.db.staff_attendance.find_one({"user_id": user["id"], "date": _today()}, {"_id": 0})
    can_review = user["role"] in {"admin", "project_manager"}
    return {"enabled": bool(projects), "projects": projects, "today": today, "needs_check_in": bool(projects) and not today, "can_review": can_review}


@router.post("/my-attendance/check-in")
async def check_in(selfie: UploadFile = File(...), lat: float = Form(...), lng: float = Form(...), accuracy: Optional[float] = Form(None),
                   project_id: str = Form(""), user: dict = Depends(S.get_current_user)):
    rows = {m["project_id"]: m for m in await _assignments(user["id"])}
    if not rows:
        raise HTTPException(status_code=403, detail="Attendance is not enabled for you. Ask your project manager.")
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
        project = await S.db.projects.find_one({"id": project_id}, {"_id": 0, "id": 1, "name": 1, "geofence": 1})
        g = (project or {}).get("geofence")
        if g:
            distance = round(_dist(g["lat"], g["lng"], lat, lng))
        if rows[project_id].get("location_required"):
            if not g:
                raise HTTPException(status_code=400, detail="Site location is required but the PM has not set the site geofence yet.")
            if distance > g["radius_m"]:
                raise HTTPException(status_code=403, detail=f"You are {distance} m from site — outside the {int(g['radius_m'])} m geofence.")
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
    if scope is not None:
        q["user_id"] = {"$in": list(scope[0])}
        expected = scope[0]
    else:
        expected = {m["user_id"] async for m in S.db.project_members.find({"company_id": user["company_id"], "attendance_required": True}, {"_id": 0, "user_id": 1})}
    rows = await S.db.staff_attendance.find(q, {"_id": 0, "selfie_path": 0}).sort("check_in.at", 1).to_list(2000)
    present = {r["user_id"] for r in rows}
    absent = await S.db.users.find({"id": {"$in": list(expected - present)}, "is_active": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1, "role": 1}).to_list(1000)
    return {"date": q["date"], "records": rows, "not_checked_in": absent}


@router.get("/my-attendance/{aid}/selfie")
async def selfie(aid: str, request: Request, auth: str = Query(None)):
    user = await S.user_from_query_token(request, auth)
    a = await S.db.staff_attendance.find_one({"id": aid, "company_id": user["company_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    ok = a["user_id"] == user["id"] or user["role"] == "admin"
    if not ok and user["role"] == "project_manager":
        ok = a["user_id"] in (await _managed_user_ids(user))[0]
    if not ok:
        raise HTTPException(status_code=403, detail="Not allowed.")
    data, ctype = await asyncio.to_thread(storage.get_object, a["selfie_path"])
    return Response(content=data, media_type=ctype or "image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
