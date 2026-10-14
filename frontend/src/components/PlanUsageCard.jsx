import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatINR } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";

export function UsageBar({ label, used, cap, unit = "", testid }) {
  const pct = cap ? Math.min(100, (used / cap) * 100) : 0;
  return (
    <div data-testid={testid}>
      <div className="flex justify-between text-xs"><span className="text-muted-foreground">{label}</span>
        <span className={pct >= 90 ? "font-semibold text-rose-600" : "font-medium"}>{used}{unit} / {cap}{unit}</span></div>
      <Progress value={pct} className="mt-1 h-1.5" />
    </div>
  );
}

export function PlanUsageCard() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/enterprise/usage").then((r) => setD(r.data)).catch(() => {}); }, []);
  if (!d) return null;
  const { usage, limits, plan } = d;
  return (
    <Card className="border-border/60 p-5" data-testid="plan-usage-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Subscription</p>
          <h3 className="font-heading text-lg font-bold" data-testid="plan-name">{plan?.name || d.enterprise.plan_id}</h3>
        </div>
        <Badge variant="outline" className="capitalize">{d.enterprise.business_type} · {formatINR(d.price_monthly)}/mo</Badge>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <UsageBar label="Users" used={usage.users} cap={limits.max_users} testid="usage-users" />
        <UsageBar label="Active projects" used={usage.projects} cap={limits.max_projects} testid="usage-projects" />
        <UsageBar label="Storage" used={usage.storage_mb} cap={limits.max_storage_mb} unit=" MB" testid="usage-storage" />
      </div>
    </Card>
  );
}
