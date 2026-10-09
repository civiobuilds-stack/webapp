# CIVIO BUILD — Product Requirements Document

## Original problem statement
Full-stack construction project management platform for Civio, a Project Management Consultancy (PMC).
Three roles (Admin/Owner/PM, Site Engineer, Client), database-backed. Architected to later support
multiple PMC companies (SaaS). Modules: projects, assignments, activities/milestones, progress-update
approval workflow, defects/quality, client approvals, procurement/cost (INR), PDF reports, notifications,
audit logs. Premium forest-green "CIVIO BUILD" design, mobile-first for engineers.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`, `auth.py`, `storage.py`, `seed.py`), MongoDB (motor).
  UUID string ids on all docs; ISO datetimes. All routes `/api`-prefixed.
- Auth: JWT (bcrypt) Bearer token in localStorage + httpOnly cookie. `get_current_user` + `require_roles`.
- RBAC: `get_project_or_403` enforces role + project-level access server-side on every read/write.
- Files: Emergent Object Storage (private), served via `/api/files/{id}/download` with access checks.
- Frontend: React 19 + Vite + Tailwind v4 + shadcn/ui. Role-aware AppShell, AuthContext, TanStack Query available.

## User personas
- Admin/Owner & Project Manager — manage projects, teams, activities, review submissions, verify defects, audit.
- Site Engineer — mobile-first: assigned sites, submit progress + photos, raise defects, revise returned work.
- Client — transparent read + approve/reject/clarify decisions with mandatory comments.

## Core requirements (static)
- Normalized model: users, companies(civio), projects, activities, milestones, progress_updates (+history/versions),
  defects (+history), files, notifications, audit_logs.
- Progress workflow: Draft → Submitted → Reviewed → Pending Client Decision → Approved/Rejected/Clarification.
  Revisions preserve previous versions. Overall progress = weighted by activity weight (not simple average).
- Defect register with severity (minor/major/critical→escalated) and statuses open/assigned/in_progress/
  awaiting_verification/reopened/closed. Only PM/admin may close.
- Client approval requires mandatory comment; decisions never overwrite history.
- In-app notifications with dedupe. Audit log for sensitive actions.

## Implemented (2026-06, Stage 1 — Core Foundation) ✅
- JWT auth + 4 seeded roles; registration (client/engineer only).
- Projects CRUD, archive, assign (engineer/client/PM); searchable list; role-scoped visibility.
- Activities (weighted) + milestones; weighted overall progress recompute.
- Progress-update workflow end-to-end: submit → PM review (approve/return/reject) → client decision → apply progress; revisions with version history + timeline.
- Defect register: raise (with before photos), status transitions, verify/close (PM only), history, critical escalation.
- Private photo upload/download (Object Storage) with per-project access checks; project photo gallery.
- In-app notification centre (bell + page, mark read/all). Audit log tab (manager only). Role-aware dashboard summary.
- Seeded demo project (Kapoor Residence, CIV-RES-001) with pending client decision + escalated defect.
- Verified by testing agent (backend 24/25 → 25/25 after fix; all frontend flows passed).

## Backlog / remaining
### P0 (next stage)
- PDF reporting: Daily/Weekly progress, Project Status, Defect register, Client Approval register,
  Procurement/Cost, Completion report — Civio-branded, with photos, stored history/regeneration.
- Procurement & cost: material requests → PM authorization → suppliers/quotes → POs → qty tracking →
  invoices/payment status → budget vs committed vs actual vs forecast (INR), variations.
### P1
- Brute-force lockout on login; password reset flow; email/WhatsApp/push notification hooks (design-ready).
- Project-specific approval-requirement configuration UI; client visibility/notification settings.
- Risks, instructions, change requests; documents/drawings with revisions.
### P2
- Multi-company (SaaS) onboarding & company switching; backup/recovery docs; split server.py into routers.

## Test credentials
See `/app/memory/test_credentials.md`.
