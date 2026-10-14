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
  const [f, setF] = useState({ plan_id: ent.plan_id, price_monthly: ent.price_monthly ?? 0, ...ent.limits });
  const [busy, setBusy] = useState(false);
  const pickPlan = (id) => {
    const p = plans.find((x) => x.id === id);
    setF({ plan_id: id, price_monthly: p.price_monthly, max_users: p.max_users, max_projects: p.max_projects, max_storage_mb: p.max_storage_mb });
  };
  const save = async () => {
    setBusy(true);
    try {
      const body = { plan_id: f.plan_id };
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
          <p className="text-xs text-muted-foreground">Billing is manual for now — no online payment is collected.</p>
        </div>
        <DialogFooter><Button onClick={save} disabled={busy} data-testid="sa-sub-save-btn">Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
