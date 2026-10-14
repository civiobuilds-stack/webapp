import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatINR, formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { UsageBar } from "@/components/PlanUsageCard";
import { SubscriptionDialog } from "@/pages/superadmin/SubscriptionDialog";
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
            {ent.status_reason && <p className="mt-1 text-xs text-rose-700">Reason: {ent.status_reason}</p>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {ent.status !== "active" && <Button size="sm" onClick={activate} data-testid="sa-approve-btn">{ent.status === "pending" ? "Approve" : "Reactivate"}</Button>}
          {ent.status === "pending" && <Button size="sm" variant="outline" onClick={() => setDlg("rejected")} data-testid="sa-reject-btn">Reject</Button>}
          {ent.status === "active" && ent.id !== "civio" && <Button size="sm" variant="outline" onClick={() => setDlg("suspended")} data-testid="sa-suspend-btn">Suspend</Button>}
          <Button size="sm" variant="secondary" onClick={() => setDlg("sub")} data-testid="sa-subscription-btn">Plan & limits</Button>
        </div>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <UsageBar label="Users" used={ent.usage.users} cap={l.max_users} testid="sa-usage-users" />
        <UsageBar label="Projects" used={ent.usage.projects} cap={l.max_projects} testid="sa-usage-projects" />
        <UsageBar label="Storage" used={ent.usage.storage_mb} cap={l.max_storage_mb} unit=" MB" testid="sa-usage-storage" />
      </div>
      {(dlg === "rejected" || dlg === "suspended") && <ReasonDialog action={dlg} ent={ent} onClose={() => setDlg(null)} onDone={done} />}
      {dlg === "sub" && <SubscriptionDialog ent={ent} plans={plans} onClose={() => setDlg(null)} onDone={done} />}
    </Card>
  );
}
