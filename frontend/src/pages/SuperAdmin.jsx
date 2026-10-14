import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatINR, formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Building2, Clock, CheckCircle2, IndianRupee, Search } from "lucide-react";
import { EnterpriseRow } from "@/pages/superadmin/EnterpriseRow";
import { PlansPanel } from "@/pages/superadmin/PlansPanel";

function Stat({ icon: Icon, label, value, testid, accent }) {
  return (
    <Card className="border-border/60 p-5" data-testid={testid}>
      <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${accent ? "bg-amber-100 text-amber-700" : "bg-primary/10 text-primary"}`}><Icon className="h-5 w-5" /></div>
      <div className="mt-4 font-mono text-3xl font-bold tracking-tight">{value}</div>
      <div className="text-sm text-muted-foreground">{label}</div>
    </Card>
  );
}

function EnterpriseList({ status, plans, onChanged }) {
  const [items, setItems] = useState(null);
  const [q, setQ] = useState("");
  const load = useCallback(() => {
    api.get("/superadmin/enterprises", { params: { status: status || undefined, q: q || undefined } }).then((r) => setItems(r.data));
  }, [status, q]);
  useEffect(() => { load(); }, [load]);
  const changed = () => { load(); onChanged(); };
  return (
    <div className="space-y-3">
      <div className="relative max-w-sm"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input className="pl-9" placeholder="Search company, email, city" value={q} onChange={(e) => setQ(e.target.value)} data-testid={`sa-search-${status || "all"}`} /></div>
      {!items ? <Skeleton className="h-32 rounded-2xl" /> : items.length === 0
        ? <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="sa-empty">No enterprises here.</Card>
        : items.map((e) => <EnterpriseRow key={e.id} ent={e} plans={plans} onChanged={changed} />)}
    </div>
  );
}

function AuditPanel() {
  const [logs, setLogs] = useState([]);
  useEffect(() => { api.get("/superadmin/audit").then((r) => setLogs(r.data)); }, []);
  return (
    <Card className="divide-y border-border/60" data-testid="sa-audit-list">
      {logs.length === 0 && <p className="p-6 text-sm text-muted-foreground">No platform activity yet.</p>}
      {logs.map((l) => (
        <div key={l.id} className="flex flex-wrap justify-between gap-2 p-4 text-sm">
          <div><span className="font-semibold">{l.actor_name}</span> · {l.action}<div className="text-xs text-muted-foreground">{l.details}</div></div>
          <span className="text-xs text-muted-foreground">{formatDateTime(l.created_at)}</span>
        </div>
      ))}
    </Card>
  );
}

export default function SuperAdmin() {
  const [ov, setOv] = useState(null);
  const [plans, setPlans] = useState([]);
  const loadOv = () => api.get("/superadmin/overview").then((r) => setOv(r.data));
  const loadPlans = () => api.get("/superadmin/plans").then((r) => setPlans(r.data));
  useEffect(() => { loadOv(); loadPlans(); }, []);
  return (
    <div className="space-y-8" data-testid="superadmin-page">
      <div className="animate-fade-up">
        <p className="text-xs font-semibold uppercase tracking-widest text-accent">Platform control</p>
        <h1 className="mt-1 font-heading text-3xl font-bold md:text-4xl">Super Admin</h1>
        <p className="mt-1 text-muted-foreground">Approve workspaces, manage subscriptions and usage limits across CIVIO.</p>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat icon={Building2} label="Enterprises" value={ov?.enterprises ?? "–"} testid="sa-stat-enterprises" />
        <Stat icon={Clock} label="Pending approval" value={ov?.by_status?.pending ?? "–"} testid="sa-stat-pending" accent={ov?.by_status?.pending > 0} />
        <Stat icon={CheckCircle2} label="Active" value={ov?.by_status?.active ?? "–"} testid="sa-stat-active" />
        <Stat icon={IndianRupee} label="Monthly recurring" value={ov ? formatINR(ov.mrr) : "–"} testid="sa-stat-mrr" />
      </div>
      <Tabs defaultValue="pending">
        <TabsList className="flex w-full flex-wrap justify-start gap-1">
          <TabsTrigger value="pending" data-testid="sa-tab-pending">Pending {ov?.by_status?.pending ? `(${ov.by_status.pending})` : ""}</TabsTrigger>
          <TabsTrigger value="all" data-testid="sa-tab-all">All enterprises</TabsTrigger>
          <TabsTrigger value="plans" data-testid="sa-tab-plans">Plans & pricing</TabsTrigger>
          <TabsTrigger value="audit" data-testid="sa-tab-audit">Activity</TabsTrigger>
        </TabsList>
        <TabsContent value="pending" className="mt-5"><EnterpriseList status="pending" plans={plans} onChanged={loadOv} /></TabsContent>
        <TabsContent value="all" className="mt-5"><EnterpriseList plans={plans} onChanged={loadOv} /></TabsContent>
        <TabsContent value="plans" className="mt-5"><PlansPanel plans={plans} onSaved={loadPlans} /></TabsContent>
        <TabsContent value="audit" className="mt-5"><AuditPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
