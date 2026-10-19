import { useCallback, useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
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

function CreateEnterprise({ plans, onDone }) {
  const blank = { company_name: "", business_type: "commercial", city: "", owner_name: "", owner_email: "", phone: "", plan_id: "free" };
  const [f, setF] = useState(blank);
  const [res, setRes] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { const { data } = await api.post("/superadmin/enterprises", f); setRes(data); setF(blank); toast.success("Enterprise created"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const sel = "h-9 rounded-md border bg-transparent px-2 text-sm";
  return (
    <Card className="space-y-3 p-5" data-testid="sa-create-enterprise">
      <h3 className="font-heading font-semibold">Create enterprise account</h3>
      <div className="grid gap-2 md:grid-cols-4">
        <Input placeholder="Company name" value={f.company_name} onChange={set("company_name")} data-testid="sa-create-company" />
        <select className={sel} value={f.business_type} onChange={set("business_type")} data-testid="sa-create-type"><option value="commercial">Commercial</option><option value="residential">Residential</option></select>
        <Input placeholder="City" value={f.city} onChange={set("city")} />
        <select className={sel} value={f.plan_id} onChange={set("plan_id")} data-testid="sa-create-plan">{plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <Input placeholder="Owner name" value={f.owner_name} onChange={set("owner_name")} data-testid="sa-create-owner" />
        <Input placeholder="Owner email (login ID)" value={f.owner_email} onChange={set("owner_email")} data-testid="sa-create-email" />
        <Input placeholder="Phone" value={f.phone} onChange={set("phone")} />
        <Button onClick={save} disabled={!f.company_name || !f.owner_name || !f.owner_email} data-testid="sa-create-submit">Create</Button>
      </div>
      {res && <div className="rounded-xl border bg-muted/40 p-3 font-mono text-sm" data-testid="sa-create-credentials">Login ID: {res.login_id} · Temporary password: {res.temporary_password}
        <span className="ml-2 font-sans text-xs text-muted-foreground">(shown once)</span></div>}
    </Card>
  );
}

function LimitsTable() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/superadmin/enterprises").then((r) => setItems(r.data)); }, []);
  const pct = (u, c) => (c ? `${u}/${c}` : `${u}/∞`);
  return (
    <Card className="overflow-x-auto" data-testid="sa-limits-table"><table className="w-full text-sm"><thead><tr className="border-b bg-muted/40 text-left text-xs uppercase text-muted-foreground">
      <th className="p-3">Enterprise</th><th className="p-3">Status</th><th className="p-3">Plan / billing</th><th className="p-3">Users</th><th className="p-3">Projects</th><th className="p-3">Storage MB</th><th className="p-3">Expiry</th></tr></thead>
      <tbody>{items.map((e) => <tr key={e.id} className="border-b last:border-0" data-testid="sa-limits-row"><td className="p-3 font-medium">{e.name}</td><td className="p-3 capitalize">{e.status}</td>
        <td className="p-3">{e.plan_id} · {(e.billing_status || "manual").replace("_", " ")} · {e.billing_period || "monthly"}</td>
        <td className="p-3">{pct(e.usage.users, e.limits?.max_users)}</td><td className="p-3">{pct(e.usage.projects, e.limits?.max_projects)}</td><td className="p-3">{pct(e.usage.storage_mb, e.limits?.max_storage_mb)}</td>
        <td className={`p-3 ${e.subscription_state === "expired" ? "font-semibold text-rose-600" : e.subscription_state === "expiring_soon" ? "text-amber-600" : ""}`}>{e.subscription_expires_at || "—"} {e.subscription_state !== "no_expiry" ? `(${e.subscription_state.replace("_", " ")})` : ""}</td></tr>)}</tbody></table></Card>
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
        <TabsList className="grid h-auto w-full grid-cols-2 gap-2 bg-transparent p-0 md:grid-cols-5">
          {[["pending", "Registration Approvals", `${ov?.by_status?.pending || 0} pending`], ["access", "Enterprise & Client Access", "Create, reset, suspend"],
            ["plans", "Monetisation & Plans", "Pricing, billing, limits"], ["limits", "Limits & Subscription Status", "Usage and expiry"], ["audit", "Activity Log", "Platform actions"]].map(([v, l, sub]) => (
            <TabsTrigger key={v} value={v} className="flex h-auto flex-col items-start rounded-xl border bg-card p-4 text-left data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground" data-testid={`sa-tab-${v}`}>
              <span className="font-semibold">{l}</span><span className="text-xs opacity-70">{sub}</span></TabsTrigger>))}
        </TabsList>
        <TabsContent value="pending" className="mt-5"><EnterpriseList status="pending" plans={plans} onChanged={loadOv} /></TabsContent>
        <TabsContent value="access" className="mt-5 space-y-4"><CreateEnterprise plans={plans} onDone={loadOv} /><EnterpriseList plans={plans} onChanged={loadOv} /></TabsContent>
        <TabsContent value="limits" className="mt-5"><LimitsTable /></TabsContent>
        <TabsContent value="plans" className="mt-5"><PlansPanel plans={plans} onSaved={loadPlans} /></TabsContent>
        <TabsContent value="audit" className="mt-5"><AuditPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
