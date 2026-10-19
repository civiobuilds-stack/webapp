import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

const FIELDS = [
  ["price_monthly", "Price / month (₹)"],
  ["max_users", "Max users"],
  ["max_projects", "Max active projects"],
  ["max_storage_mb", "Max storage (MB)"],
];

export function SubscriptionDialog({ ent, plans, onClose, onDone }) {
  const [f, setF] = useState({ plan_id: ent.plan_id, price_monthly: ent.price_monthly ?? 0, ...ent.limits,
    billing_status: ent.billing_status || "manual", billing_period: ent.billing_period || "monthly", subscription_expires_at: ent.subscription_expires_at || "" });
  const [busy, setBusy] = useState(false);
  const pickPlan = (id) => {
    const p = plans.find((x) => x.id === id);
    setF({ ...f, plan_id: id, price_monthly: p.price_monthly, max_users: p.max_users, max_projects: p.max_projects, max_storage_mb: p.max_storage_mb, billing_period: p.billing_period || "monthly" });
  };
  const save = async () => {
    setBusy(true);
    try {
      const body = { plan_id: f.plan_id, billing_status: f.billing_status, billing_period: f.billing_period, subscription_expires_at: f.subscription_expires_at || null };
      FIELDS.forEach(([k]) => { body[k] = Number(f[k]); });
      await api.put(`/superadmin/enterprises/${ent.id}/subscription`, body);
      toast.success("Subscription updated");
      onDone();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Plan & limits — {ent.name}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Plan</Label>
            <Select value={f.plan_id} onValueChange={pickPlan}>
              <SelectTrigger data-testid="sa-plan-select"><SelectValue /></SelectTrigger>
              <SelectContent>{plans.map((p) => <SelectItem key={p.id} value={p.id} data-testid={`sa-plan-option-${p.id}`}>{p.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {FIELDS.map(([k, label]) => (
              <div key={k} className="space-y-1.5"><Label>{label}</Label>
                <Input type="number" min={k === "price_monthly" ? 0 : 1} value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`sa-sub-${k}`} /></div>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5"><Label>Billing status</Label><select className="h-9 w-full rounded-md border bg-transparent px-2 text-sm" value={f.billing_status} onChange={(e) => setF({ ...f, billing_status: e.target.value })} data-testid="sa-sub-billing-status">
              {["trial", "manual", "pending_payment", "overdue", "cancelled"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</select></div>
            <div className="space-y-1.5"><Label>Billing period</Label><select className="h-9 w-full rounded-md border bg-transparent px-2 text-sm" value={f.billing_period} onChange={(e) => setF({ ...f, billing_period: e.target.value })} data-testid="sa-sub-billing-period">
              {["monthly", "quarterly", "yearly"].map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
            <div className="space-y-1.5"><Label>Expires on</Label><Input type="date" value={f.subscription_expires_at} onChange={(e) => setF({ ...f, subscription_expires_at: e.target.value })} data-testid="sa-sub-expiry" /></div>
          </div>
          <p className="text-xs text-muted-foreground">No online payments are collected yet, so "Paid" cannot be set without a verified payment record. After expiry, the enterprise cannot add users, projects or storage.</p>
        </div>
        <DialogFooter><Button onClick={save} disabled={busy} data-testid="sa-sub-save-btn">Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
