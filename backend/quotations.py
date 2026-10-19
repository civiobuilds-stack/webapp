"""Residential: branded quotations with revisions + client e-signature, and architect/structural drawings."""
import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import server as S
import commercial as C
import reports as reports_module

router = APIRouter()
DISCIPLINE_ROLE = {"architect": "architectural", "structural_engineer": "structural"}


async def quote_user(user: dict = Depends(S.get_current_user)) -> dict:
    S.require_module(user, "quotations")
    return user


async def drawing_user(user: dict = Depends(S.get_current_user)) -> dict:
    S.require_module(user, "drawings")
    return user


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------
class QItem(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    unit: str = Field(default="nos", max_length=20)
    qty: float = Field(gt=0)
    rate: float = Field(ge=0)


class QuoteIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    items: List[QItem] = Field(min_length=1)
    tax_pct: float = Field(default=18, ge=0, le=50)
    discount: float = Field(default=0, ge=0)
    valid_until: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str = Field(default="", max_length=2000)
    terms: str = Field(default="", max_length=3000)


class QuoteResponse(BaseModel):
    action: str
    comment: str = Field(default="", max_length=1000)
    signature_name: str = Field(default="", max_length=80)


def _calc(body: QuoteIn):
    items = [{**i.model_dump(), "amount": round(i.qty * i.rate, 2)} for i in body.items]
    sub = round(sum(i["amount"] for i in items), 2)
    if body.discount > sub:
        raise HTTPException(status_code=400, detail="Discount cannot exceed the subtotal.")
    taxable = sub - body.discount
    tax = round(taxable * body.tax_pct / 100, 2)
    return {"items": items, "subtotal": sub, "discount": body.discount, "tax_pct": body.tax_pct, "tax": tax, "total": round(taxable + tax, 2),
            "valid_until": body.valid_until, "notes": body.notes, "terms": body.terms}


def _mgr(user, project):
    if not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Only the Owner or this project's manager can prepare quotations.")


async def _quote(qid, user):
    q = await S.db.quotations.find_one({"id": qid, "company_id": user["company_id"]}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    project = await S.get_project_or_403(q["project_id"], user)
    if user["role"] == "client" and q["status"] == "draft" and len(q["revisions"]) == 1:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return q, project


def _client_view(q):
    """Clients only see revisions that were sent to them."""
    revs = [r for r in q["revisions"] if r.get("sent_at")]
    return {**q, "revisions": revs, "status": q["status"] if q["status"] != "draft" else "revision_in_progress"}


@router.get("/projects/{pid}/quotations")
async def list_quotes(pid: str, user: dict = Depends(quote_user)):
    project = await S.get_project_or_403(pid, user)
    if user["role"] != "client" and not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Quotations are visible to the Owner, the project manager and the client only.")
    rows = await S.db.quotations.find({"project_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    if user["role"] == "client":
        rows = [_client_view(q) for q in rows if any(r.get("sent_at") for r in q["revisions"])]
    return rows


@router.post("/projects/{pid}/quotations")
async def create_quote(pid: str, body: QuoteIn, user: dict = Depends(quote_user)):
    project = await S.get_project_or_403(pid, user, write=True)
    _mgr(user, project)
    ctr = await S.db.counters.find_one_and_update({"id": f"quote-{pid}"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    ts = S.now_iso()
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, "title": body.title,
           "number": f"QT-{project.get('code', 'P')}-{ctr['seq']:03d}", "status": "draft", "current_rev": 1,
           "revisions": [{"rev": 1, **_calc(body), "created_by_name": user["name"], "created_at": ts, "sent_at": None}],
           "client_response": None, "created_by": user["id"], "created_at": ts, "updated_at": ts}
    await S.db.quotations.insert_one(doc)
    doc.pop("_id", None)
    await S.log_audit(pid, user, "created quotation", "quotation", doc["id"], doc["number"])
    return doc


@router.put("/quotations/{qid}")
async def edit_quote(qid: str, body: QuoteIn, user: dict = Depends(quote_user)):
    q, project = await _quote(qid, user)
    _mgr(user, project)
    if q["status"] != "draft":
        raise HTTPException(status_code=400, detail="Only a draft revision can be edited. Create a new revision instead.")
    rev = {**q["revisions"][-1], **_calc(body), "created_by_name": user["name"]}
    await S.db.quotations.update_one({"id": qid}, {"$set": {"title": body.title, "revisions": q["revisions"][:-1] + [rev], "updated_at": S.now_iso()}})
    return (await _quote(qid, user))[0]


@router.post("/quotations/{qid}/revise")
async def revise_quote(qid: str, body: QuoteIn, user: dict = Depends(quote_user)):
    q, project = await _quote(qid, user)
    _mgr(user, project)
    if q["status"] not in {"sent", "changes_requested", "rejected"}:
        raise HTTPException(status_code=400, detail="Revisions can be made after the quotation is sent and before it is accepted.")
    n = q["current_rev"] + 1
    rev = {"rev": n, **_calc(body), "created_by_name": user["name"], "created_at": S.now_iso(), "sent_at": None}
    await S.db.quotations.update_one({"id": qid}, {"$set": {"title": body.title, "status": "draft", "current_rev": n, "updated_at": S.now_iso()},
                                                   "$push": {"revisions": rev}})
    await S.log_audit(q["project_id"], user, "revised quotation", "quotation", qid, f"{q['number']} R{n}")
    return (await _quote(qid, user))[0]


@router.post("/quotations/{qid}/send")
async def send_quote(qid: str, user: dict = Depends(quote_user)):
    q, project = await _quote(qid, user)
    _mgr(user, project)
    if q["status"] != "draft":
        raise HTTPException(status_code=400, detail="This revision has already been sent.")
    if not project.get("client_id"):
        raise HTTPException(status_code=400, detail="Link a client to this project before sending a quotation.")
    revs = q["revisions"]
    revs[-1]["sent_at"] = S.now_iso()
    await S.db.quotations.update_one({"id": qid, "status": "draft"}, {"$set": {"status": "sent", "revisions": revs, "client_response": None, "updated_at": S.now_iso()}})
    await S.log_audit(q["project_id"], user, "sent quotation", "quotation", qid, f"{q['number']} R{q['current_rev']}")
    await S.notify(project["client_id"], "quotation", f"New quotation {q['number']} R{q['current_rev']} (Rs {revs[-1]['total']:,.0f}) is ready for your review.",
                   q["project_id"], link=f"/projects/{q['project_id']}?tab=quotations", push=True)
    return (await _quote(qid, user))[0]


@router.post("/quotations/{qid}/respond")
async def respond_quote(qid: str, body: QuoteResponse, request: Request, user: dict = Depends(quote_user)):
    q, project = await _quote(qid, user)
    if user["role"] != "client" or project.get("client_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Only the project's client can respond to a quotation.")
    if q["status"] != "sent":
        raise HTTPException(status_code=400, detail="This quotation is not awaiting your response.")
    mapping = {"accept": "accepted", "reject": "rejected", "request_changes": "changes_requested"}
    if body.action not in mapping:
        raise HTTPException(status_code=400, detail="Invalid action.")
    if body.action == "accept" and len(body.signature_name.strip()) < 3:
        raise HTTPException(status_code=400, detail="Type your full name as your e-signature to accept.")
    if body.action != "accept" and not body.comment.strip():
        raise HTTPException(status_code=400, detail="Please add a comment for the team.")
    last = q["revisions"][-1]
    if body.action == "accept" and last.get("valid_until") and last["valid_until"] < datetime.now(timezone.utc).date().isoformat():
        raise HTTPException(status_code=400, detail="This quotation has expired. Please ask the team for a fresh revision.")
    resp = {"action": body.action, "rev": q["current_rev"], "comment": body.comment, "by": user["name"], "at": S.now_iso(),
            "signature_name": body.signature_name.strip() if body.action == "accept" else None,
            "ip": (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()}
    st = mapping[body.action]
    res = await S.db.quotations.update_one({"id": qid, "status": "sent"}, {"$set": {"status": st, "client_response": resp, "updated_at": S.now_iso()},
                                                                         "$push": {"responses": resp}})
    if not res.modified_count:
        raise HTTPException(status_code=409, detail="Already responded.")
    await S.log_audit(q["project_id"], user, f"quotation {st}", "quotation", qid, f"{q['number']} R{q['current_rev']} {resp['signature_name'] or body.comment}")
    for rid in {project.get("project_manager_id"), q["created_by"]} - {None}:
        await S.notify(rid, "quotation", f"Client {st.replace('_', ' ')} quotation {q['number']} R{q['current_rev']}.", q["project_id"],
                       link=f"/projects/{q['project_id']}?tab=quotations", push=True)
    return _client_view((await _quote(qid, user))[0])


@router.get("/quotations/{qid}/pdf")
async def quote_pdf(qid: str, request: Request, rev: Optional[int] = Query(None), auth: str = Query(None)):
    user = await S.user_from_query_token(request, auth)
    S.require_module(user, "quotations")
    q, project = await _quote(qid, user)
    if user["role"] != "client" and not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Not allowed.")
    revs = _client_view(q)["revisions"] if user["role"] == "client" else q["revisions"]
    want = rev or (revs[-1]["rev"] if revs else 0)
    r = next((x for x in revs if x["rev"] == want), None)
    if not r:
        raise HTTPException(status_code=404, detail="Revision not found")
    client = await S.db.users.find_one({"id": project.get("client_id")}, {"_id": 0, "name": 1, "email": 1, "phone": 1}) or {}
    resp = next((x for x in reversed(q.get("responses", [])) if x["rev"] == r["rev"]), None)
    ent = user["_enterprise"]
    meta = {"title": "Quotation", "code": f"{q['number']} · R{r['rev']}", "generated": datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC"),
            "revision": f"R{r['rev']}", "confidential": f"Confidential — {ent.get('display_name') or ent['name']}"}
    brand = await asyncio.to_thread(S.report_brand, ent)
    pdf = reports_module.build_quotation(project, q, r, client, resp, meta, brand)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{q["number"]}_R{r["rev"]}.pdf"'})


# ---------------------------------------------------------------------------
# Drawings (Architect / Structural Engineer -> Owner/PM approval -> client)
# ---------------------------------------------------------------------------
class DrawingIn(BaseModel):
    discipline: str
    drawing_no: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=2, max_length=150)
    file_id: str
    notes: str = Field(default="", max_length=1000)


class DrawingDecision(BaseModel):
    action: str
    remarks: str = Field(default="", max_length=1000)


def _can_upload(user, project, discipline):
    if discipline not in {"architectural", "structural"}:
        raise HTTPException(status_code=400, detail="Discipline must be architectural or structural.")
    if user["role"] in DISCIPLINE_ROLE:
        if DISCIPLINE_ROLE[user["role"]] != discipline:
            raise HTTPException(status_code=403, detail=f"As {S.ROLE_NAMES[user['role']]} you can upload {DISCIPLINE_ROLE[user['role']]} drawings only.")
    elif not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Only architects, structural engineers, the Owner or PM can upload drawings.")


@router.get("/projects/{pid}/drawings")
async def list_drawings(pid: str, user: dict = Depends(drawing_user)):
    await S.get_project_or_403(pid, user)
    q = {"project_id": pid, **({"status": "approved"} if user["role"] == "client" else {})}
    rows = await S.db.drawings.find(q, {"_id": 0}).sort([("drawing_no", 1), ("rev", -1)]).to_list(2000)
    return rows


@router.post("/projects/{pid}/drawings")
async def upload_drawing(pid: str, body: DrawingIn, user: dict = Depends(drawing_user)):
    project = await S.get_project_or_403(pid, user, write=True)
    _can_upload(user, project, body.discipline)
    if not await S.db.files.find_one({"id": body.file_id, "project_id": pid, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Upload the drawing file to this project first.")
    no = body.drawing_no.strip().upper()
    if await S.db.drawings.find_one({"project_id": pid, "drawing_no": no, "status": "pending"}):
        raise HTTPException(status_code=409, detail="A revision of this drawing is already awaiting approval.")
    prev = await S.db.drawings.count_documents({"project_id": pid, "drawing_no": no})
    doc = {"id": S.new_id(), "company_id": user["company_id"], "project_id": pid, **body.model_dump(), "drawing_no": no, "rev": prev + 1,
           "status": "pending", "uploaded_by": user["id"], "uploaded_by_name": user["name"], "uploaded_by_role": user["role"], "created_at": S.now_iso(),
           "review": None}
    await S.db.drawings.insert_one(doc)
    doc.pop("_id", None)
    await S.log_audit(pid, user, "uploaded drawing", "drawing", doc["id"], f"{no} R{doc['rev']} {body.title}")
    for rid in {project.get("project_manager_id")} - {None, user["id"]}:
        await S.notify(rid, "drawing", f"Drawing {no} R{doc['rev']} ({body.title}) awaits your approval.", pid, link=f"/projects/{pid}?tab=drawings", push=True)
    return doc


@router.post("/drawings/{did}/decision")
async def decide_drawing(did: str, body: DrawingDecision, user: dict = Depends(drawing_user)):
    d = await S.db.drawings.find_one({"id": did, "company_id": user["company_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Drawing not found")
    project = await S.get_project_or_403(d["project_id"], user)
    if not C._manages(user, project):
        raise HTTPException(status_code=403, detail="Only the Owner or this project's manager can approve drawings.")
    if d["status"] != "pending" or body.action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="This drawing is not awaiting approval.")
    if body.action == "reject" and not body.remarks.strip():
        raise HTTPException(status_code=400, detail="Please add a reason for rejecting.")
    st = "approved" if body.action == "approve" else "rejected"
    if st == "approved":
        await S.db.drawings.update_many({"project_id": d["project_id"], "drawing_no": d["drawing_no"], "status": "approved"}, {"$set": {"status": "superseded"}})
    await S.db.drawings.update_one({"id": did}, {"$set": {"status": st, "review": {"by": user["name"], "at": S.now_iso(), "remarks": body.remarks}}})
    await S.log_audit(d["project_id"], user, f"drawing {st}", "drawing", did, f"{d['drawing_no']} R{d['rev']} {body.remarks}")
    link = f"/projects/{d['project_id']}?tab=drawings"
    await S.notify(d["uploaded_by"], "drawing", f"Drawing {d['drawing_no']} R{d['rev']} was {st}{': ' + body.remarks if body.remarks else ''}.", d["project_id"], link=link, push=True)
    if st == "approved" and project.get("client_id"):
        await S.notify(project["client_id"], "drawing", f"New approved drawing: {d['title']} ({d['drawing_no']} R{d['rev']}).", d["project_id"], link=link, push=True)
    return await S.db.drawings.find_one({"id": did}, {"_id": 0})


@router.get("/dashboard/design")
async def design_dashboard(user: dict = Depends(drawing_user)):
    if user["role"] not in DISCIPLINE_ROLE:
        raise HTTPException(status_code=403, detail="Design dashboard is for architects and structural engineers.")
    projects = await S.list_projects(user)
    pids = [p["id"] for p in projects]
    mine = await S.db.drawings.find({"project_id": {"$in": pids}, "uploaded_by": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    count = lambda st: sum(1 for d in mine if d["status"] == st)  # noqa: E731
    return {"role": user["role"], "role_label": S.ROLE_NAMES[user["role"]], "discipline": DISCIPLINE_ROLE[user["role"]],
            "cards": [{"key": "projects", "label": "My projects", "count": len(projects)},
                      {"key": "pending", "label": "Awaiting approval", "count": count("pending")},
                      {"key": "approved", "label": "Approved (current)", "count": count("approved")},
                      {"key": "rejected", "label": "Rejected — revise", "count": count("rejected"), "alert": True}],
            "projects": [{"id": p["id"], "name": p["name"], "code": p.get("code"),
                          "drawings": sum(1 for d in mine if d["project_id"] == p["id"])} for p in projects],
            "recent": mine[:10]}
