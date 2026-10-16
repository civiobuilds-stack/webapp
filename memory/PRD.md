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
- Verified by testing agent (backend 25/25; all frontend flows passed).

## Implemented (2026-06, Stage 2 — Authorization Hardening) ✅
- Backend authorization audit: single project-level gate `get_project_or_403` on every read/write.
- Hardened: file upload requires write access (blocks clients); orphan files restricted to uploader/managers; progress-revise re-checks project membership.
- Verified by testing agent: 47/47 authorization/IDOR tests pass. Regression suite `tests/test_authorization.py`.

## Implemented (2026-06, Stage 4 — Branding + Phone/OTP + Email) ✅
- **Rebrand to CIVIO**: navy/blue/green logo palette across app (theme tokens, sidebar, project header, PDF reports), CIVIO wordmark + ring app-icon, favicon, tagline "Your Build, Our Expertise".
- **People management**: Owner/PM screen to create engineers & clients (and PMs by admin) with auto temp password + copyable credentials.
- **Phone + Email OTP verification** (Emergent-managed Resend): signup requires a phone number; a 6-digit code is emailed and must be verified before first login. Applies to self-signup AND admin/PM-created accounts. Login gates unverified users (403 `email_not_verified`) and reissues a code; resend endpoint is enumeration-safe; attempts rate-limited (429 after 6). Seeded/demo accounts are pre-verified.
- **Report emailing**: generating a report emails the PDF (attached) to the project client + assigned engineers; failures are swallowed (report still saved).
- Verified by testing agent: OTP flow 18/18, authorization & prior suites green. Emailer never raises on provider errors.
- **PDF Reports** (`reports.py`, reportlab): Civio-branded Progress / Completion / Cost reports from live data — project header, activity/milestone/defect tables, dated site photos, cost summary, completion sign-off block, page footer (timestamp, revision id, page numbers). Stored in Object Storage; historical revisions preserved; list + download (`?auth=` token); client can download published reports; generation notifies client.
- **Procurement & Cost**: material requests (engineer raise → PM authorize/reject), suppliers, purchase orders with line items (amount = qty×rate, PO numbers), PO + invoice status tracking, INR cost summary (budget / committed / actual / forecast / variance). Client sees procurement only if `client_budget_visible`.
- **Shared-Photo Scoping**: clients only see photos on approved or pending-decision updates and closed-defect photos (`client_visible_file_ids`), enforced on both the gallery and file download.
- **Audit CSV Export**: admin-only timestamped CSV of the project audit log.
- Verified by testing agent: 36/36 new-feature tests pass, 100% backend + frontend. Suite `tests/test_civio_new_features.py`.

## Implemented (2026-06, Stage 5 — Multi-Tenant SaaS) ✅
- Tenant = enterprise (`enterprises` collection; `users/projects/suppliers/files.company_id`). Startup migration (non-destructive, idempotent) puts all legacy data in default enterprise `civio` (CIVIO PMC, commercial, active), seeds `plans` (Free/Starter/Professional/Enterprise, INR).
- Two role scopes: `platform_role=super_admin` (civiobuilds@gmail.com) + tenant `role`. All tenant APIs enforce active enterprise (403 `enterprise_inactive`); project gate is company-scoped (404 cross-tenant); assignment ids validated in-company; file/report/CSV downloads tenant-scoped.
- Enterprise onboarding: `/register` → company + Residential/Commercial → email OTP → pending screen until Super Admin approves. Google sign-in only for existing accounts.
- Super Admin dashboard `/superadmin`: stats (MRR), pending/all lists with usage bars, approve/reject/suspend/reactivate (reason + email/notification), plan & limit overrides (manual billing), editable plans, platform activity log.
- Plan limits enforced: users, active projects, storage MB. Tenant admin sees plan usage card on dashboard.
- Business-type workspaces: residential hides Procurement (UI + backend 403) and cost report; commercial = full module set.
- PWA: manifest + service worker (installable).
- Verified: 99/99 backend tests (incl. new `tests/test_multitenant_saas.py`), frontend flows 100%.

## Implemented (2026-06, Stage 6 — Invites, Branding, Homeowner, Landing) ✅
- Public landing page at "/" for visitors (what CIVIO is, features, Residential/Commercial workspaces, contact civiobuilds@gmail.com / +91 91080 98446, Sign in / Register). Logged-in users still land on their dashboard.
- Team invites: admins and PMs invite by name/email/role → an email link to /invite/{token} (7 days, single use, hashed token) → the invitee sets a password and phone and joins the inviting company already verified (no OTP). The People page lists invites and lets you revoke them.
- Company Settings (/settings, admin only): display name, tagline, contact email/phone, website, address, and a logo upload (PNG/JPG under 2 MB, object storage). The sidebar shows the logo and name. PDF reports use the company's name, logo and contact in the header, with "Confidential — {company}" and "Powered by CIVIO" in the footer.
- Residential homeowner dashboard for clients: progress ring hero, big Approve / Request changes cards, a build timeline (milestones and phase progress), a site-team contact card (call/email), and latest photos.
- Report emails now go out in the background, and photos are fetched in parallel (report generation went from about 60s to under 1s). Corrupt photos are skipped in PDFs.
- Verified in iteration_6 (all backend and frontend checks passed).

## Backlog / remaining
### Next (SaaS)
- Residential-specific modules/dashboard copy (homeowner timeline, simplified client view); per-enterprise branding on PDFs.
- Online subscription payments (Stripe/Razorpay); invite-by-link for tenant users; Super Admin enterprise detail/user list; push notifications; native Expo app (separate job); Twilio SMS OTP (needs keys); split server.py into routers.
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

## Verified (2026-06, Stage 7 — Store / Labour / BOQ-DPR E2E) ✅
- iteration_7: Store (requests, approve/reject, partial/full issue, tool return good/damaged/lost, receive, stock, txns), BOQ + BOQ-linked DPR (excess flag), Labour geofence check-in/out, cross-tenant denial — all pass. Tests: backend/tests/test_store_boq_labour_iter7.py (run with -n 0).
- Camera permission denied -> gallery file picker fallback verified.
- UX: Receive-stock Kind is now a select; Return dialog shows outstanding qty + over-return warning.

## Implemented (2026-06, Stage 8 — Branding, Labour Cost, Overdue Tools) ✅
- Real CIVIO wordmark logo (white bg) in sidebar, mobile header, login, landing, PWA icons (icon-192/512), PDF header fallback (backend/assets/civio-icon.png); BrandLoader (logo on white) for all page loads + index.html splash. CIVIO PMC enterprise logo re-uploaded.
- Labour wages: company default (Settings) + per-project override (Attendance tab). Labour cost JSON/PDF per project & company (MTD + last 7 days). Weekly email with PDF to company admins — cron Sat 18:00 IST (/api/cron/labour-cost).
- Overdue tool reminders: daily 09:00 IST cron (/api/cron/tool-overdue) push + email to requester, CC PM/store approvers; dedupe per request/day; manual "remind now"; Overdue badge in Store.
- Super Admin password = Civio@123456, no forced change.
- Tests: iteration_8 (18/18 backend pass, frontend pass). backend/labour_cost.py.

## Backlog
- P1 Low stock alerts; P1 native mobile app; P2 payment gateway for subscriptions; P2 split server.py

## Implemented (2026-06, Stage 9 — Residential Phase 1) ✅  (iteration_9: backend 24/24, frontend flows pass; follow-up fixes applied)
- No OTP for employees/clients created by PM/Admin (owner self-registration still OTP). Login lockout: 5 fails / 15 min (login_attempts).
- People page: Login accounts table (login ID, role/job, status, last login), edit job role/description, reset password (temp shown once, hash only), remove/reactivate (soft, history kept).
- Team tab: Add People dropdown with project job role/description, remove with confirm; Delete project (type code; soft delete is_deleted).
- Inspection Checklist replaces Defects in BOTH workspaces (inspection.py): 18 stages/76 items, pass/fail/NA, remarks, responsible, photos required for pass/fail, drawings/documents, Generate Inspection Report (PM/owner/client) -> reports collection.
- Residential material approvals (residential.py): engineer -> PM -> client approve/reject with remarks, email+push, stage stepper, dashboard pending cards.
- Residential DPR tab (module res_dpr) reusing commercial DPR; client sees approved only; Generate DPR Report auto-includes that day's site photos.
- Residential demo tenant civio-homes (seed.py seed_residential).

## Next: Phase 2 (Commercial hierarchy/roles incl. ASCO Manager & Pass Coordinator, company store workflow, DPR weekly targets) → Phase 3 (vehicles/drivers, safety, billing/QS docs, approval dashboard). User choices: camera-only for commercial required photos; push only for drivers (no SMS); passwords hash-only.
