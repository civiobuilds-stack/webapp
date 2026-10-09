"""Seeds admin + clearly-marked demo data for CIVIO BUILD."""
import os
from datetime import datetime, timezone, timedelta


async def seed_all(db, hash_password, now_iso):
    admin_email = os.environ.get("ADMIN_EMAIL", "civiobuilds@gmail.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "CivioAdmin@2026")

    # --- Admin (idempotent) ---
    admin = await db.users.find_one({"email": admin_email})
    if not admin:
        admin = {
            "id": "user-admin", "email": admin_email, "password_hash": hash_password(admin_password),
            "name": "Civio Owner", "role": "admin", "phone": None, "company_id": "civio",
            "is_active": True, "is_demo": False, "created_at": now_iso(),
        }
        await db.users.insert_one(admin)
    elif not _ok(admin_password, admin["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    # Only seed demo content once.
    if await db.projects.find_one({"is_demo": True}):
        return

    def u(uid, email, name, role, pwd, phone=None):
        return {"id": uid, "email": email, "password_hash": hash_password(pwd), "name": name,
                "role": role, "phone": phone, "company_id": "civio", "is_active": True,
                "is_demo": True, "created_at": now_iso()}

    demo_users = [
        u("user-pm", "pm@civio.build", "Rajesh Nair (PM)", "project_manager", "CivioPM@2026", "+91 98200 11111"),
        u("user-eng", "engineer@civio.build", "Anita Deshmukh (Engineer)", "site_engineer", "CivioEng@2026", "+91 98200 22222"),
        u("user-eng2", "engineer2@civio.build", "Vikram Singh (Engineer)", "site_engineer", "CivioEng@2026", "+91 98200 33333"),
        u("user-client", "client@civio.build", "Meera Kapoor (Client)", "client", "CivioClient@2026", "+91 98200 44444"),
    ]
    for existing in demo_users:
        if not await db.users.find_one({"email": existing["email"]}):
            await db.users.insert_one(existing)

    today = datetime.now(timezone.utc)

    def iso(days):
        return (today + timedelta(days=days)).isoformat()

    project = {
        "id": "proj-demo-1", "company_id": "civio", "code": "CIV-RES-001",
        "name": "Kapoor Residence — Bandra West", "client_id": "user-client",
        "address": "Plot 42, Hill Road, Bandra West, Mumbai 400050",
        "type": "Residential", "description": "Demo project — G+3 luxury residential villa with basement parking.",
        "start_date": iso(-60), "planned_completion_date": iso(120), "status": "In Progress",
        "contract_value": 42500000, "project_manager_id": "user-pm",
        "engineer_ids": ["user-eng", "user-eng2"], "client_budget_visible": True,
        "progress_percent": 43.5, "is_archived": False, "is_demo": True,
        "created_by": "user-admin", "created_at": now_iso(),
    }
    await db.projects.insert_one(project)

    activities = [
        ("act-1", "Excavation & Foundation", "Foundation", 15, 100, "completed", "user-eng", False),
        ("act-2", "RCC Framework — Basement to G+3", "Superstructure", 30, 70, "in_progress", "user-eng", True),
        ("act-3", "Brickwork & Blockwork", "Superstructure", 15, 40, "in_progress", "user-eng2", False),
        ("act-4", "MEP Rough-in", "MEP", 15, 10, "in_progress", "user-eng2", True),
        ("act-5", "Plastering & Waterproofing", "Finishing", 15, 0, "not_started", "user-eng", False),
        ("act-6", "Flooring & Finishing", "Finishing", 10, 0, "not_started", "user-eng2", True),
    ]
    for aid, name, phase, weight, pct, status, eng, needs_client in activities:
        await db.activities.insert_one({
            "id": aid, "project_id": project["id"], "name": name, "phase": phase,
            "weight": weight, "planned_start": iso(-50), "planned_end": iso(30),
            "assigned_engineer_id": eng, "unit": "%", "quantity_total": 100,
            "quantity_completed": pct, "requires_client_approval": needs_client,
            "progress_percent": pct, "status": status, "created_at": now_iso(),
        })

    milestones = [
        ("ms-1", "Foundation Complete", iso(-40), "completed"),
        ("ms-2", "Structure Topping-out", iso(20), "upcoming"),
        ("ms-3", "MEP Complete", iso(70), "upcoming"),
        ("ms-4", "Handover", iso(120), "upcoming"),
    ]
    for mid, name, due, status in milestones:
        await db.milestones.insert_one({"id": mid, "project_id": project["id"], "name": name,
                                        "due_date": due, "status": status, "created_at": now_iso()})

    # A pending-client-decision progress update
    await db.progress_updates.insert_one({
        "id": "pu-1", "project_id": project["id"], "activity_id": "act-2",
        "engineer_id": "user-eng", "percent_complete": 70, "quantity_completed": 70,
        "notes": "3rd floor slab cast and cured. Ready for client review of structural milestone.",
        "photo_ids": [], "status": "pending_client_decision", "version": 1, "previous_version_id": None,
        "pm_comment": "Reviewed on site, structural quality verified. Forwarding for client sign-off.",
        "client_comment": None, "reviewed_by": "user-pm", "reviewed_at": now_iso(),
        "client_decision_by": None, "client_decision_at": None, "requires_client_approval": True,
        "created_at": now_iso(),
        "history": [
            {"status": "submitted", "by": "Anita Deshmukh (Engineer)", "at": iso(-2), "comment": "Slab cast complete."},
            {"status": "pending_client_decision", "by": "Rajesh Nair (PM)", "at": now_iso(), "comment": "Structural quality verified."},
        ],
    })

    # Defects
    await db.defects.insert_one({
        "id": "def-1", "project_id": project["id"], "defect_code": "DEF-001",
        "location": "Basement — North retaining wall", "category": "Waterproofing", "severity": "critical",
        "description": "Water seepage observed along construction joint during monsoon test.",
        "responsible_party": "Waterproofing subcontractor", "corrective_action": "Inject PU grout and apply crystalline coating.",
        "reported_by": "user-pm", "assigned_to": "user-eng", "target_date": iso(7), "status": "in_progress", "escalated": True,
        "before_photo_ids": [], "closure_photo_ids": [], "verification_notes": None,
        "reviewed_by": None, "closure_date": None, "created_at": now_iso(),
        "history": [
            {"status": "open", "by": "Rajesh Nair (PM)", "at": iso(-5), "note": "Defect raised"},
            {"status": "assigned", "by": "Rajesh Nair (PM)", "at": iso(-4), "note": "Assigned to Anita"},
            {"status": "in_progress", "by": "Anita Deshmukh (Engineer)", "at": iso(-2), "note": "Grouting started"},
        ],
    })
    await db.defects.insert_one({
        "id": "def-2", "project_id": project["id"], "defect_code": "DEF-002",
        "location": "2nd Floor — Master bedroom", "category": "Finishing", "severity": "minor",
        "description": "Plaster surface uneven near window reveal.", "responsible_party": "Mason team",
        "corrective_action": "Re-plaster and sand to level.", "reported_by": "user-eng2", "assigned_to": "user-eng2",
        "target_date": iso(3), "status": "awaiting_verification", "escalated": False,
        "before_photo_ids": [], "closure_photo_ids": [], "verification_notes": None,
        "reviewed_by": None, "closure_date": None, "created_at": now_iso(),
        "history": [{"status": "open", "by": "Vikram Singh (Engineer)", "at": iso(-3), "note": "Defect raised"},
                    {"status": "awaiting_verification", "by": "Vikram Singh (Engineer)", "at": iso(-1), "note": "Rework done"}],
    })

    # Notifications
    await db.notifications.insert_one({
        "id": "notif-1", "user_id": "user-client", "type": "client_decision",
        "message": "A progress update for RCC Framework is awaiting your decision.",
        "project_id": project["id"], "link": None, "read": False, "dedupe_key": "pending-pu-1", "created_at": now_iso(),
    })
    await db.notifications.insert_one({
        "id": "notif-2", "user_id": "user-pm", "type": "defect",
        "message": "ESCALATED: Defect DEF-001 raised (critical).", "project_id": project["id"],
        "link": None, "read": False, "dedupe_key": None, "created_at": now_iso(),
    })

    await db.audit_logs.insert_one({
        "id": "audit-1", "project_id": project["id"], "actor_id": "user-admin", "actor_name": "Civio Owner",
        "action": "created project", "entity_type": "project", "entity_id": project["id"],
        "details": project["name"], "created_at": now_iso(),
    })


def _ok(pwd, hashed):
    import bcrypt
    try:
        return bcrypt.checkpw(pwd.encode(), hashed.encode())
    except Exception:
        return False
