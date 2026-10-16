import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { TargetRow } from "@/pages/project/TargetsPanel";

export function RoleDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/dashboard/role").then((r) => setD(r.data)).catch(() => {}); }, []);
  if (!d) return null;
  const met = d.targets.filter((t) => t.met).length;
  return (
    <div className="space-y-4" data-testid="role-dashboard">
      <p className="text-xs text-muted-foreground" data-testid="role-dashboard-label">{d.role_label} dashboard{d.approver_label ? ` · approvals go to ${d.approver_label}` : ""}</p>
      {d.cards.length > 0 && <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{d.cards.map((c) => (
        <Card key={c.key} className={`p-4 ${c.alert && c.count ? "border-rose-300 bg-rose-50" : ""}`} data-testid={`role-card-${c.key}`}>
          <div className="text-xs text-muted-foreground">{c.label}</div><div className="font-mono text-2xl font-bold">{c.count}</div></Card>))}</div>}
      {d.targets.length > 0 && <Card className="p-4" data-testid="targets-dashboard">
        <div className="mb-1 flex items-center justify-between font-semibold"><span>Weekly targets · week of {d.week_start}</span>
          <span className={`rounded-full px-2 py-0.5 text-xs text-white ${met === d.targets.length ? "bg-emerald-600" : "bg-rose-600"}`} data-testid="targets-overall">{met}/{d.targets.length} achieved</span></div>
        <div className="divide-y">{d.targets.map((t) => <TargetRow key={t.id} t={t} />)}</div></Card>}
    </div>
  );
}
