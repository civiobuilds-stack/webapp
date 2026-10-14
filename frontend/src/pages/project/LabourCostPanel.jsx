import { useEffect, useState } from "react";
import { api, apiError, API, getToken } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileDown, IndianRupee } from "lucide-react";
import { toast } from "sonner";

const inr = (v) => `₹${Math.round(v).toLocaleString("en-IN")}`;

function RateForm({ pid, wages, onDone }) {
  const [f, setF] = useState({ mason_rate: wages.override.mason_rate ?? "", helper_rate: wages.override.helper_rate ?? "" });
  const num = (v) => (v === "" || v === null ? null : Number(v));
  const save = async () => {
    try { await api.put(`/projects/${pid}/wages`, { mason_rate: num(f.mason_rate), helper_rate: num(f.helper_rate) }); toast.success("Project wage rates saved"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <div className="flex flex-wrap items-end gap-2" data-testid="project-wage-form">
      {[["mason_rate", "Mason Rs/day"], ["helper_rate", "Helper Rs/day"]].map(([k, l]) => <div key={k} className="space-y-1"><Label className="text-xs">{l}</Label>
        <Input className="w-36" type="number" min={0} placeholder={`Default ${wages.company[k]}`} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`project-wage-${k}`} /></div>)}
      <Button variant="outline" onClick={save} data-testid="project-wage-save-btn">Save project rates</Button>
    </div>
  );
}

export function LabourCostPanel({ project, manages }) {
  const [c, setC] = useState(null);
  const [wages, setWages] = useState(null);
  const load = () => {
    api.get(`/projects/${project.id}/labour-cost`).then((r) => setC(r.data)).catch(() => {});
    api.get(`/projects/${project.id}/wages`).then((r) => setWages(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  if (!c || !wages) return null;
  return (
    <Card className="space-y-4 p-5" data-testid="labour-cost-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1 font-heading font-bold"><IndianRupee className="h-4 w-4" /> Labour cost · {c.month}</h3>
        <a href={`${API}/projects/${project.id}/labour-cost/pdf?auth=${getToken()}`} target="_blank" rel="noreferrer"><Button size="sm" variant="secondary" data-testid="project-labour-cost-pdf-btn"><FileDown className="h-4 w-4" /> PDF</Button></a>
      </div>
      <p className="text-xs text-muted-foreground">Rates in use: mason {inr(c.rates.mason_rate)}/day · helper {inr(c.rates.helper_rate)}/day{wages.override.mason_rate != null || wages.override.helper_rate != null ? " (project override)" : " (company default)"}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {[["Month-to-date", c.mtd, "mtd"], ["Last 7 days", c.week, "week"]].map(([l, a, k]) => (
          <div key={k} className="rounded-xl border p-4" data-testid={`labour-cost-${k}`}><div className="text-xs uppercase tracking-wider text-muted-foreground">{l}</div>
            <div className="font-mono text-2xl font-bold" data-testid={`labour-cost-${k}-total`}>{inr(a.total)}</div>
            <div className="text-xs">{a.mason_days} mason-days ({inr(a.mason_cost)}) · {a.helper_days} helper-days ({inr(a.helper_cost)})</div></div>))}
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[11px]">{c.days.map((d) => (
        <div key={d.date} className="rounded-md bg-muted/50 p-1.5"><div className="text-muted-foreground">{formatDate(d.date).slice(0, 6)}</div><b>{inr(d.total)}</b><div>{d.mason_days}M/{d.helper_days}H</div></div>))}</div>
      {manages && <RateForm pid={project.id} wages={wages} onDone={load} />}
    </Card>
  );
}
