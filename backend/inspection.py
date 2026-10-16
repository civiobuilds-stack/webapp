"""Inspection Checklist (replaces Defects in both workspaces): staged checklist, drawings/documents, PDF report."""
import asyncio
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import server as S
import reports as R

router = APIRouter()
STATUSES = {"pending", "pass", "fail", "na"}
TEMPLATE = [
    ("Setting Out", ["Site survey and benchmark established", "Grid lines and building corners marked as per drawing", "Plot boundaries and setbacks verified", "Setting-out approved by engineer"]),
    ("Excavation", ["Excavation depth and width as per drawing", "Soil strata matches design assumptions", "Shoring / side protection provided where required", "Dewatering arranged if water table encountered", "Bottom levelled, compacted and anti-termite treated"]),
    ("Foundations", ["PCC bed thickness and level checked", "Footing size and position as per drawing", "Column starter positions verified", "Plinth beam level and alignment checked"]),
    ("Reinforcement", ["Bar diameter, spacing and count as per BBS", "Lap length and staggering correct", "Cover blocks of correct size placed", "Stirrups / rings hooks and spacing correct", "Bars free of rust, oil and mud"]),
    ("Shuttering", ["Formwork line, level and plumb checked", "Joints sealed to prevent slurry leakage", "Props and bracing adequate and secured", "Release agent applied"]),
    ("Concreting", ["Concrete grade / mix design confirmed", "Slump test conducted", "Cube samples taken", "Vibration and compaction adequate", "Curing started and maintained"]),
    ("Masonry", ["Brick / block quality accepted", "Mortar ratio as specified", "Line, level and plumb of walls", "Bond pattern and joint thickness correct", "Lintels and sill bands provided"]),
    ("Waterproofing", ["Surface prepared and cleaned", "Waterproofing material as specified", "Coats and overlaps applied correctly", "Ponding / flood test passed"]),
    ("Plastering", ["Surface hacked and wetted", "Plaster thickness and mix correct", "Line, level and corners true", "Curing done for specified days"]),
    ("Plumbing", ["Pipe material and sizes as per drawing", "Slopes for drainage lines correct", "Pressure test of supply lines passed", "Sleeves provided at wall / slab crossings", "Concealed lines photographed before closing"]),
    ("Electrical", ["Conduit routing as per layout", "Wire gauge and colour coding correct", "Switch / socket box positions and heights", "Earthing provided and tested", "Insulation resistance test passed"]),
    ("Flooring", ["Base levelled and compacted", "Floor slopes towards drains", "Material and pattern as approved", "No hollow sound / cracks"]),
    ("Tiling", ["Tile quality and shade matched", "Joint width uniform and grouted", "Level and alignment checked", "Skirting and dado finished properly"]),
    ("Doors & Windows", ["Frames fixed in plumb and level", "Shutters operate smoothly", "Hardware fitted as specified", "Glazing and sealant complete"]),
    ("Painting", ["Surface putty and primer applied", "Paint shade as approved", "Number of coats as specified", "No patches, runs or brush marks"]),
    ("Fixtures", ["Sanitary fixtures installed and leak-free", "Electrical fixtures installed and working", "Kitchen / wardrobe fittings complete"]),
    ("Finishing", ["Snag list closed", "Site cleaned and debris removed", "External works and drainage complete"]),
    ("Handover", ["All services tested and commissioned", "As-built drawings and warranties handed over", "Keys handed over", "Client walkthrough completed and signed off"]),
]


class ItemUpdate(BaseModel):
    status: str
    remarks: str = Field(default="", max_length=1000)
    responsible_id: Optional[str] = None
    photo_ids: List[str] = []


class CustomItem(BaseModel):
    stage: str = Field(min_length=1, max_length=60)
    item: str = Field(min_length=1, max_length=200)


class DocIn(BaseModel):
    file_id: str
    title: str = Field(min_length=1, max_length=120)
    category: str = "drawing"


def _mod(user):
    S.require_module(user, "inspection")


async def _seed(pid, cid):
    if await S.db.inspection_items.find_one({"project_id": pid}):
        return
    docs = [{"id": S.new_id(), "project_id": pid, "company_id": cid, "stage": st, "stage_order": si, "item": it, "order": ii,
             "status": "pending", "remarks": "", "responsible_id": None, "photo_ids": [], "history": [], "created_at": S.now_iso()}
            for si, (st, items) in enumerate(TEMPLATE) for ii, it in enumerate(items)]
    await S.db.inspection_items.insert_many(docs)


async def _items(pid):
    items = await S.db.inspection_items.find({"project_id": pid}, {"_id": 0}).sort([("stage_order", 1), ("order", 1)]).to_list(2000)
    uids = {i["responsible_id"] for i in items if i.get("responsible_id")} | {i.get("inspected_by") for i in items if i.get("inspected_by")}
    umap = {u["id"]: u["name"] for u in await S.db.users.find({"id": {"$in": list(uids)}}, {"_id": 0, "id": 1, "name": 1}).to_list(500)}
    for i in items:
        i["responsible_name"] = umap.get(i.get("responsible_id"))
        i["inspected_by_name"] = umap.get(i.get("inspected_by"))
    return items


def _group(items):
    stages = []
    for i in items:
        if not stages or stages[-1]["stage"] != i["stage"]:
            stages.append({"stage": i["stage"], "items": []})
        stages[-1]["items"].append(i)
    summary = {k: sum(1 for i in items if i["status"] == k) for k in STATUSES}
    summary["total"] = len(items)
    return stages, summary


@router.get("/projects/{pid}/inspection")
async def get_inspection(pid: str, user: dict = Depends(S.get_current_user)):
    _mod(user)
    p = await S.get_project_or_403(pid, user)
    await _seed(pid, p["company_id"])
    stages, summary = _group(await _items(pid))
    return {"stages": stages, "summary": summary}


@router.put("/inspection-items/{iid}")
async def update_item(iid: str, body: ItemUpdate, user: dict = Depends(S.require_roles("admin", "project_manager", "site_engineer"))):
    _mod(user)
    it = await S.db.inspection_items.find_one({"id": iid, "company_id": user["company_id"]}, {"_id": 0})
    if not it:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    await S.get_project_or_403(it["project_id"], user, write=True)
    if body.status not in STATUSES:
        raise HTTPException(status_code=400, detail="Status must be pending, pass, fail or na.")
    ids = list(dict.fromkeys(body.photo_ids))
    if ids and await S.db.files.count_documents({"id": {"$in": ids}, "project_id": it["project_id"], "is_deleted": False}) != len(ids):
        raise HTTPException(status_code=400, detail="Photos must be uploaded to this project.")
    if body.status in {"pass", "fail"} and not ids:
        raise HTTPException(status_code=400, detail="Upload at least one inspection photo before marking Pass or Fail.")
    if body.status == "fail" and not body.remarks.strip():
        raise HTTPException(status_code=400, detail="Add remarks describing the failure.")
    await S.ensure_company_users([body.responsible_id], user)
    ts = S.now_iso()
    await S.db.inspection_items.update_one({"id": iid}, {
        "$set": {"status": body.status, "remarks": body.remarks, "responsible_id": body.responsible_id, "photo_ids": ids,
                 "inspected_by": user["id"], "inspected_at": ts},
        "$push": {"history": {"status": body.status, "by": user["name"], "at": ts, "remarks": body.remarks, "photos": len(ids)}}})
    await S.log_audit(it["project_id"], user, f"inspection {body.status}", "inspection", iid, f"{it['stage']}: {it['item']}")
    return {"ok": True}


@router.post("/projects/{pid}/inspection/items")
async def add_item(pid: str, body: CustomItem, user: dict = Depends(S.require_roles("admin", "project_manager"))):
    _mod(user)
    p = await S.get_project_or_403(pid, user, write=True)
    await _seed(pid, p["company_id"])
    same = await S.db.inspection_items.find_one({"project_id": pid, "stage": body.stage}, {"_id": 0}, sort=[("order", -1)])
    so = same["stage_order"] if same else 100 + await S.db.inspection_items.count_documents({"project_id": pid, "stage_order": {"$gte": 100}})
    doc = {"id": S.new_id(), "project_id": pid, "company_id": p["company_id"], "stage": body.stage.strip(), "stage_order": so,
           "item": body.item.strip(), "order": (same["order"] + 1) if same else 0, "status": "pending", "remarks": "",
           "responsible_id": None, "photo_ids": [], "history": [], "custom": True, "created_at": S.now_iso()}
    await S.db.inspection_items.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Drawings & documents
# ---------------------------------------------------------------------------
@router.get("/projects/{pid}/documents")
async def list_docs(pid: str, user: dict = Depends(S.get_current_user)):
    await S.get_project_or_403(pid, user)
    docs = await S.db.project_documents.find({"project_id": pid, "is_deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


@router.post("/projects/{pid}/documents")
async def add_doc(pid: str, body: DocIn, user: dict = Depends(S.require_roles("admin", "project_manager", "site_engineer"))):
    await S.get_project_or_403(pid, user, write=True)
    if body.category not in {"drawing", "document"}:
        raise HTTPException(status_code=400, detail="Category must be drawing or document.")
    f = await S.db.files.find_one({"id": body.file_id, "project_id": pid, "is_deleted": False}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=400, detail="Upload the file to this project first.")
    doc = {"id": S.new_id(), "project_id": pid, "company_id": user["company_id"], "file_id": body.file_id, "title": body.title.strip(),
           "category": body.category, "filename": f["original_filename"], "content_type": f["content_type"],
           "uploaded_by": user["id"], "uploaded_by_name": user["name"], "created_at": S.now_iso()}
    await S.db.project_documents.insert_one(doc)
    doc.pop("_id", None)
    await S.log_audit(pid, user, f"added {body.category}", "document", doc["id"], body.title)
    return doc


@router.delete("/documents/{did}")
async def remove_doc(did: str, user: dict = Depends(S.require_roles("admin", "project_manager"))):
    d = await S.db.project_documents.find_one({"id": did, "company_id": user["company_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Document not found")
    await S.get_project_or_403(d["project_id"], user, write=True)
    await S.db.project_documents.update_one({"id": did}, {"$set": {"is_deleted": True, "deleted_by": user["id"], "deleted_at": S.now_iso()}})
    await S.log_audit(d["project_id"], user, "removed document", "document", did, d["title"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@router.post("/projects/{pid}/inspection/report")
async def inspection_report(pid: str, user: dict = Depends(S.require_roles("admin", "project_manager", "client"))):
    _mod(user)
    p = await S.get_project_or_403(pid, user)
    await _seed(pid, p["company_id"])
    items = await _items(pid)
    docs = await list_docs(pid, user)
    shot = [i for i in items if i["status"] in {"pass", "fail", "na"} and i.get("photo_ids")]
    fids = [f for i in shot for f in i["photo_ids"]][:30]
    files = {f["id"]: f for f in await S.db.files.find({"id": {"$in": fids}, "is_deleted": False}, {"_id": 0}).to_list(30)}
    order = [f for f in fids if f in files]
    got = await asyncio.gather(*[asyncio.to_thread(S.storage.get_object, files[f]["storage_path"]) for f in order], return_exceptions=True)
    data = {f: g[0] for f, g in zip(order, got) if not isinstance(g, Exception)}
    photos = [(data[f], f"{i['item'][:40]} — {i['status'].upper()}", files[f]["created_at"]) for i in shot for f in i["photo_ids"] if f in data]
    stages, summary = _group(items)
    rev = await S.db.reports.count_documents({"project_id": pid, "type": "inspection"})
    revision = f"INS-{rev + 1:02d}"
    ent = user["_enterprise"]
    meta = {"title": "Inspection Report", "code": p.get("code", ""), "generated": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
            "revision": revision, "confidential": f"Confidential — {ent.get('display_name') or ent['name']}",
            "prepared_by": f"{user['name']} ({S.ROLE_NAMES.get(user['role'], user['role'])})"}
    pdf = await asyncio.to_thread(R.build_inspection, p, stages, summary, docs, photos, meta, S.report_brand(ent))
    rid = S.new_id()
    try:
        res = await asyncio.to_thread(S.storage.put_object, f"{S.storage.APP_NAME}/reports/{pid}/{rid}.pdf", pdf, "application/pdf")
    except Exception:
        raise HTTPException(status_code=502, detail="Could not store the generated report.")
    doc = {"id": rid, "project_id": pid, "type": "inspection", "title": "Inspection Report", "revision": revision, "period_start": None,
           "period_end": None, "storage_path": res["path"], "size": res.get("size", len(pdf)), "generated_by": user["id"],
           "generated_by_name": user["name"], "generated_at": S.now_iso()}
    await S.db.reports.insert_one(doc)
    doc.pop("_id", None)
    await S.log_audit(pid, user, "generated inspection report", "report", rid, revision)
    return doc
