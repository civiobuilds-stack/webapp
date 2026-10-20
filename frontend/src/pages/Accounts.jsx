import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatINR } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { BillRow, BillActions, BILL_STATUS } from "@/pages/project/BillingTab";
import { toast } from "sonner";

function BillsPanel({ user }) {
  const [data, setData] = useState({ bills: [], summary: {} });
  const [status, setStatus] = useState("all");
  const [dlg, setDlg] = useState(null);
  const [projects, setProjects] = useState({});
  const load = () => api.get("/bills", { params: status === "all" ? {} : { status } }).then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [status]);
  useEffect(() => { api.get("/projects").then((r) => setProjects(Object.fromEntries(r.data.map((p) => [p.id, p])))).catch(() => {}); }, []);
  const s = data.summary;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card className="p-4"><div className="text-xs text-muted-foreground">Pending approval</div><div className="font-mono text-lg font-bold" data-testid="acc-sum-pending">{formatINR(s.pending)}</div>
          <div className="text-[11px] text-muted-foreground">{s.count_pending_pm || 0} with PM · {s.count_pending_owner || 0} with Owner</div></Card>
        <Card className="p-4"><div className="text-xs text-muted-foreground">Approved, unpaid</div><div className="font-mono text-lg font-bold" data-testid="acc-sum-approved">{formatINR(s.approved)}</div></Card>
        <Card className="p-4"><div className="text-xs text-muted-foreground">Paid</div><div className="font-mono text-lg font-bold" data-testid="acc-sum-paid">{formatINR(s.paid)}</div></Card>
        <Select value={status} onValueChange={setStatus}><SelectTrigger className="h-auto" data-testid="acc-bill-filter"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="all">All bills</SelectItem>{Object.entries(BILL_STATUS).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}</SelectContent></Select>
      </div>
      <Card className="divide-y">
        {data.bills.length === 0 && <p className="p-4 text-sm text-muted-foreground">No bills. Accounts submits bills from a project's Billing tab.</p>}
        {data.bills.map((b) => <BillRow key={b.id} b={b} user={user} project={projects[b.project_id]} onAction={setDlg} showProject />)}
      </Card>
      <BillActions dlg={dlg} setDlg={setDlg} onDone={load} />
    </div>
  );
}

export default function Accounts() {
  const { user } = useAuth();
  const [sp] = useSearchParams();
  return (
    <div className="space-y-6" data-testid="accounts-page">
      <div><p className="text-xs font-semibold uppercase tracking-widest text-accent">Accounts</p>
        <h1 className="font-heading text-3xl font-bold">Billing</h1></div>
      <Tabs defaultValue={sp.get("tab") || "bills"}>
        <TabsList><TabsTrigger value="bills" data-testid="acc-tab-bills">Bills</TabsTrigger></TabsList>
        <TabsContent value="bills" className="mt-5"><BillsPanel user={user} /></TabsContent>
      </Tabs>
    </div>
  );
}
