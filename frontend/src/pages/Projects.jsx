import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BrandLoader } from "@/components/BrandLoader";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatINR, formatDate, isManager } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Plus, Loader2, Search } from "lucide-react";
import { toast } from "sonner";

export default function Projects() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  const load = () => api.get("/projects").then((r) => setProjects(r.data)).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const filtered = projects.filter((p) => `${p.name} ${p.code} ${p.address}`.toLowerCase().includes(q.toLowerCase()));
  const manager = isManager(user.role);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold">Projects</h1>
          <p className="text-muted-foreground">{manager ? "Create and manage your construction projects." : "Your assigned projects."}</p>
        </div>
        {manager && <NewProjectDialog onCreated={load} />}
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search projects..." className="pl-9" data-testid="project-search-input" />
      </div>

      {loading ? (
        <BrandLoader fullScreen={false} />
      ) : filtered.length === 0 ? (
        <Card className="p-12 text-center text-muted-foreground" data-testid="no-projects">No projects found.</Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((p) => (
            <Card key={p.id} data-testid="project-card-item" onClick={() => navigate(`/projects/${p.id}`)}
              className="group cursor-pointer border-border/60 p-5 transition-all hover:-translate-y-0.5 hover:shadow-lg">
              <div className="flex items-center justify-between">
                <Badge variant="outline" className="font-mono text-[11px]">{p.code}</Badge>
                <Badge variant="secondary">{p.status}</Badge>
              </div>
              <h3 className="mt-3 font-heading text-lg font-semibold group-hover:text-primary">{p.name}</h3>
              <p className="truncate text-sm text-muted-foreground">{p.address}</p>
              <div className="mt-4">
                <div className="mb-1 flex justify-between text-sm"><span className="text-muted-foreground">Progress</span><span className="font-mono font-bold">{p.progress_percent ?? 0}%</span></div>
                <Progress value={p.progress_percent ?? 0} className="h-2" />
              </div>
              <div className="mt-4 flex items-center justify-between border-t pt-3 text-xs text-muted-foreground">
                <span>{p.engineers?.length || 0} engineer(s)</span>
                {(manager || p.client_budget_visible) && p.contract_value ? <span className="font-mono font-semibold text-foreground">{formatINR(p.contract_value)}</span> : <span>Due {formatDate(p.planned_completion_date)}</span>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function NewProjectDialog({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [clients, setClients] = useState([]);
  const [engineers, setEngineers] = useState([]);
  const [form, setForm] = useState({
    name: "", code: "", address: "", type: "Residential", description: "",
    start_date: "", planned_completion_date: "", contract_value: "", client_id: "", engineer_ids: [], client_budget_visible: false,
  });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    if (!open) return;
    api.get("/users?role=client").then((r) => setClients(r.data)).catch(() => {});
    api.get("/users?role=site_engineer").then((r) => setEngineers(r.data)).catch(() => {});
  }, [open]);

  const toggleEng = (id) => setForm((f) => ({ ...f, engineer_ids: f.engineer_ids.includes(id) ? f.engineer_ids.filter((x) => x !== id) : [...f.engineer_ids, id] }));

  const submit = async () => {
    if (!form.name || !form.code) { toast.error("Name and code are required."); return; }
    setBusy(true);
    try {
      const payload = { ...form, contract_value: form.contract_value ? Number(form.contract_value) : null, client_id: form.client_id || null };
      await api.post("/projects", payload);
      toast.success("Project created");
      setOpen(false); onCreated();
      setForm({ name: "", code: "", address: "", type: "Residential", description: "", start_date: "", planned_completion_date: "", contract_value: "", client_id: "", engineer_ids: [], client_budget_visible: false });
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button data-testid="new-project-btn"><Plus className="h-4 w-4" /> New Project</Button></DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle>Create construction project</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Project name *</Label><Input value={form.name} onChange={set("name")} data-testid="project-name-input" /></div>
            <div className="space-y-1.5"><Label>Project code *</Label><Input value={form.code} onChange={set("code")} placeholder="CIV-RES-002" data-testid="project-code-input" /></div>
          </div>
          <div className="space-y-1.5"><Label>Site address</Label><Input value={form.address} onChange={set("address")} data-testid="project-address-input" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Type</Label>
              <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                <SelectTrigger data-testid="project-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{["Residential", "Commercial", "Industrial", "Infrastructure"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Contract value (₹)</Label><Input type="number" value={form.contract_value} onChange={set("contract_value")} data-testid="project-value-input" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Start date</Label><Input type="date" value={form.start_date} onChange={set("start_date")} data-testid="project-start-input" /></div>
            <div className="space-y-1.5"><Label>Planned completion</Label><Input type="date" value={form.planned_completion_date} onChange={set("planned_completion_date")} data-testid="project-end-input" /></div>
          </div>
          <div className="space-y-1.5"><Label>Description</Label><Textarea value={form.description} onChange={set("description")} rows={2} data-testid="project-desc-input" /></div>
          <div className="space-y-1.5"><Label>Client</Label>
            <Select value={form.client_id} onValueChange={(v) => setForm({ ...form, client_id: v })}>
              <SelectTrigger data-testid="project-client-select"><SelectValue placeholder="Assign a client" /></SelectTrigger>
              <SelectContent>{clients.length === 0 ? <div className="p-2 text-sm text-muted-foreground">No clients yet</div> : clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5"><Label>Assign engineers</Label>
            <div className="flex flex-wrap gap-2">
              {engineers.length === 0 ? <span className="text-sm text-muted-foreground">No engineers yet</span> : engineers.map((e) => (
                <button key={e.id} type="button" onClick={() => toggleEng(e.id)} data-testid={`assign-eng-${e.id}`}
                  className={`rounded-full border px-3 py-1 text-sm ${form.engineer_ids.includes(e.id) ? "border-primary bg-primary text-primary-foreground" : "bg-card"}`}>{e.name}</button>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={busy} data-testid="create-project-submit">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create project"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
