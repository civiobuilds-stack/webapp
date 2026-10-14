import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

const NUM = [["price_monthly", "Price / month (₹)"], ["max_users", "Users"], ["max_projects", "Projects"], ["max_storage_mb", "Storage (MB)"]];

function PlanCard({ plan, onSaved }) {
  const [f, setF] = useState(plan);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const body = { name: f.name, description: f.description || "" };
      NUM.forEach(([k]) => { body[k] = Number(f[k]); });
      await api.put(`/superadmin/plans/${plan.id}`, body);
      toast.success(`${f.name} saved`);
      onSaved();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <Card className="space-y-3 border-border/60 p-5" data-testid={`sa-plan-${plan.id}`}>
      <Input className="font-heading font-bold" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid={`sa-plan-name-${plan.id}`} />
      <Input value={f.description || ""} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="Description" />
      <div className="grid grid-cols-2 gap-2">
        {NUM.map(([k, l]) => (
          <div key={k} className="space-y-1"><Label className="text-xs">{l}</Label>
            <Input type="number" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`sa-plan-${plan.id}-${k}`} /></div>
        ))}
      </div>
      <Button size="sm" className="w-full" onClick={save} disabled={busy} data-testid={`sa-plan-save-${plan.id}`}>Save plan</Button>
    </Card>
  );
}

export function PlansPanel({ plans, onSaved }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {plans.map((p) => <PlanCard key={p.id + p.price_monthly + p.name} plan={p} onSaved={onSaved} />)}
    </div>
  );
}
