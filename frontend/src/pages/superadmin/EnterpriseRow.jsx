import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatINR, formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { UsageBar } from "@/components/PlanUsageCard";
import { SubscriptionDialog } from "@/pages/superadmin/SubscriptionDialog";
import { LifecycleDialog } from "@/pages/superadmin/LifecycleDialog";
import { Home, Building2 } from "lucide-react";
import { toast } from "sonner";

export const STATUS_CLS = {
  pending: "bg-amber-50 text-amber-800 border-amber-300",
  active: "bg-emerald-50 text-emerald-800 border-emerald-300",
  suspended: "bg-slate-100 text-slate-700 border-slate-300",
  rejected: "bg-rose-50 text-rose-700 border-rose-300",
};

function ReasonDialog({ action, ent, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/superadmin/enterprises/${ent.id}/status`, { status: action, reason });
      toast.success(`${ent.name} ${action === "rejected" ? "rejected" : "suspended"}`);
      onDone();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>{action === "rejected" ? "Reject" : "Suspend"} {ent.name}</DialogTitle></DialogHeader>
        <Textarea placeholder="Reason (shared with the company owner)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="sa-reason-input" />
        <DialogFooter><Button variant="destructive" disabled={busy || !reason.trim()} onClick={submit} data-testid="sa-reason-confirm-btn">Confirm</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResetOwner({ ent, onClose }) {
  const [r, setR] = useState(null);
  const go = async () => { try { const { data } = await api.post(`/superadmin/enterprises/${ent.id}/reset-owner`); setR(data); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>Reset owner access — {ent.name}</DialogTitle></DialogHeader>
      {!r ? <><p className="text-sm text-muted-foreground">Issues a new temporary password for {ent.owner_email}. The current password is never shown; the owner must change it on next sign-in.</p>
        <DialogFooter><Button onClick={go} data-testid="sa-reset-confirm-btn">Reset access</Button></DialogFooter></>
        : <div className="rounded-xl border bg-muted/40 p-4 font-mono text-sm" data-testid="sa-reset-credentials"><div>Login ID: {r.login_id}</div><div>Temporary password: {r.temporary_password}</div>
          <p className="mt-2 font-sans text-xs text-muted-foreground">Shown once — share securely.</p></div>}
    </DialogContent></Dialog>
  );
}

function HistoryDialog({ ent, onClose }) {
  const [h, setH] = useState(null);
  useEffect(() => { api.get(`/superadmin/enterprises/${ent.id}/history`).then((r) => setH(r.data)).catch(() => setH({ status_history: [], audit: [] })); }, [ent.id]);
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-testid="sa-history-dialog"><DialogHeader><DialogTitle>History — {ent.name}</DialogTitle></DialogHeader>
      {!h ? null : <div className="space-y-3 text-sm">
        <div className="text-xs text-muted-foreground">Registered {formatDate(h.created_at)} · Approved {h.approved_at ? formatDate(h.approved_at) : "—"}</div>
        <div><div className="mb-1 font-semibold">Status changes</div>{h.status_history.length === 0 ? <p className="text-xs text-muted-foreground">None recorded.</p> :
          h.status_history.map((s, i) => <div key={i} className="text-xs" data-testid="sa-history-row">{formatDate(s.at)} · {s.from || "—"} → <b>{s.to}</b> by {s.by}{s.reason ? ` — ${s.reason}` : ""}</div>)}</div>
        <div><div className="mb-1 font-semibold">Platform actions</div>{h.audit.map((a) => <div key={a.id} className="text-xs">{formatDate(a.created_at)} · {a.action} · {a.actor_name}{a.details ? ` — ${a.details}` : ""}</div>)}</div>
      </div>}
    </DialogContent></Dialog>
  );
}

export function EnterpriseRow({ ent, plans, onChanged }) {
  const [dlg, setDlg] = useState(null);
  const Icon = ent.business_type === "residential" ? Home : Building2;
  const plan = plans.find((p) => p.id === ent.plan_id);
  const activate = async () => {
    try { await api.post(`/superadmin/enterprises/${ent.id}/status`, { status: "active" }); toast.success(`${ent.name} is active`); onChanged(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const done = () => { setDlg(null); onChanged(); };
  const l = ent.limits || {};
  return (
    <Card className="border-border/60 p-5" data-testid={`sa-ent-${ent.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary"><Icon className="h-5 w-5" /></div>
          <div>
            <div className="flex flex-wrap items-center gap-2"><h3 className="font-heading font-bold" data-testid="sa-ent-name">{ent.name}</h3>
              <Badge variant="outline" className={STATUS_CLS[ent.status]} data-testid="sa-ent-status">{ent.status}</Badge>
              <Badge variant="outline" className="capitalize">{ent.business_type}</Badge></div>
            <p className="text-sm text-muted-foreground">{ent.owner_name} · {ent.owner_email} · {ent.phone || "—"}{ent.city ? ` · ${ent.city}` : ""}</p>
            <p className="text-xs text-muted-foreground">Registered {formatDate(ent.created_at)} · {plan?.name || ent.plan_id} · {formatINR(ent.price_monthly)}/mo</p>
            <p className="text-xs" data-testid="sa-ent-subscription">Billing: <b>{(ent.billing_status || "manual").replace("_", " ")}</b> · {ent.billing_period || "monthly"} · {ent.subscription_expires_at ? `expires ${formatDate(ent.subscription_expires_at)}` : "no expiry set"}
              {ent.subscription_state && ent.subscription_state !== "no_expiry" && ent.subscription_state !== "active" && <Badge className={`ml-2 text-white ${ent.subscription_state === "expired" ? "bg-rose-600" : "bg-amber-500"}`} data-testid="sa-sub-state">{ent.subscription_state.replace("_", " ")}</Badge>}</p>
            <p className="text-xs" data-testid="sa-ent-lifecycle">State: <b className="capitalize">{ent.subscription?.state || "active"}</b>
              {ent.trial_end ? ` · trial ends ${formatDate(ent.trial_end)}` : ""}{ent.subscription?.base_state === "active" && ent.subscription_expires_at ? ` · renews ${formatDate(ent.subscription_expires_at)}` : ""}
              {ent.activation_requested_at && <Badge className="ml-2 bg-sky-600 text-white" data-testid="sa-activation-requested">Activation requested {formatDate(ent.activation_requested_at)}</Badge>}</p>
            {ent.status_reason && <p className="mt-1 text-xs text-rose-700">Reason: {ent.status_reason}</p>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {ent.status !== "active" && <Button size="sm" onClick={activate} data-testid="sa-approve-btn">{ent.status === "pending" ? "Approve" : "Reactivate"}</Button>}
          {ent.status === "pending" && <Button size="sm" variant="outline" onClick={() => setDlg("rejected")} data-testid="sa-reject-btn">Reject</Button>}
          {ent.status === "active" && ent.id !== "civio" && <Button size="sm" variant="outline" onClick={() => setDlg("suspended")} data-testid="sa-suspend-btn">Suspend</Button>}
          <Button size="sm" variant="secondary" onClick={() => setDlg("sub")} data-testid="sa-subscription-btn">Plan & limits</Button>
          {ent.id !== "civio" && <Button size="sm" onClick={() => setDlg("life")} data-testid="sa-lifecycle-btn">Trial & renewal</Button>}
          {ent.id !== "civio" && <Button size="sm" variant="outline" onClick={() => setDlg("reset")} data-testid="sa-reset-owner-btn">Reset owner access</Button>}
          <Button size="sm" variant="ghost" onClick={() => setDlg("history")} data-testid="sa-history-btn">History</Button>
        </div>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <UsageBar label="Users" used={ent.usage.users} cap={l.max_users} testid="sa-usage-users" />
        <UsageBar label="Projects" used={ent.usage.projects} cap={l.max_projects} testid="sa-usage-projects" />
        <UsageBar label="Storage" used={ent.usage.storage_mb} cap={l.max_storage_mb} unit=" MB" testid="sa-usage-storage" />
      </div>
      {(dlg === "rejected" || dlg === "suspended") && <ReasonDialog action={dlg} ent={ent} onClose={() => setDlg(null)} onDone={done} />}
      {dlg === "reset" && <ResetOwner ent={ent} onClose={() => setDlg(null)} />}
      {dlg === "history" && <HistoryDialog ent={ent} onClose={() => setDlg(null)} />}
      {dlg === "life" && <LifecycleDialog ent={ent} onClose={() => setDlg(null)} onDone={done} />}
      {dlg === "sub" && <SubscriptionDialog ent={ent} plans={plans} onClose={() => setDlg(null)} onDone={done} />}
    </Card>
  );
}
