export function formatINR(amount) {
  if (amount == null || isNaN(amount)) return "—";
  const n = Number(amount);
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(2)} Cr`;
  if (n >= 100000) return `₹${(n / 100000).toFixed(2)} L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

export function formatDate(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return "—"; }
}

export function formatDateTime(d) {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { return "—"; }
}

export const PROGRESS_STATUS = {
  draft: { label: "Draft", cls: "bg-slate-100 text-slate-700 border-slate-300" },
  submitted: { label: "Submitted", cls: "bg-sky-50 text-sky-800 border-sky-300" },
  reviewed: { label: "Reviewed", cls: "bg-amber-50 text-amber-800 border-amber-300" },
  pending_client_decision: { label: "Pending Client", cls: "bg-purple-50 text-purple-800 border-purple-300" },
  approved: { label: "Approved", cls: "bg-emerald-50 text-emerald-800 border-emerald-300" },
  rejected: { label: "Rejected", cls: "bg-rose-50 text-rose-800 border-rose-300" },
  clarification_needed: { label: "Clarification", cls: "bg-orange-50 text-orange-800 border-orange-300" },
};

export const SEVERITY = {
  critical: { label: "Critical", cls: "bg-rose-600 text-white" },
  major: { label: "Major", cls: "bg-amber-500 text-slate-950" },
  minor: { label: "Minor", cls: "bg-slate-200 text-slate-800" },
};

export const DEFECT_STATUS = {
  open: { label: "Open", cls: "bg-rose-50 text-rose-700 border-rose-300" },
  assigned: { label: "Assigned", cls: "bg-sky-50 text-sky-700 border-sky-300" },
  in_progress: { label: "In Progress", cls: "bg-amber-50 text-amber-700 border-amber-300" },
  awaiting_verification: { label: "Awaiting Verification", cls: "bg-purple-50 text-purple-700 border-purple-300" },
  reopened: { label: "Reopened", cls: "bg-orange-50 text-orange-700 border-orange-300" },
  closed: { label: "Closed", cls: "bg-emerald-50 text-emerald-700 border-emerald-300" },
};

export const ROLE_LABEL = {
  admin: "Owner / Admin",
  project_manager: "Project Manager",
  site_engineer: "Site Engineer",
  client: "Client",
  safety_engineer: "Safety Engineer",
  safety_manager: "Safety Manager",
  quality_engineer: "Quality Engineer",
  quality_manager: "Quality Manager",
  store_incharge: "Store In-charge",
  store_manager: "Store Manager",
  billing_qs: "Billing / QS / Documents",
  billing_manager: "Billing Manager",
  pass_coordinator: "Pass Coordinator",
  driver: "Driver",
};

export const isManager = (role) => role === "admin" || role === "project_manager";
