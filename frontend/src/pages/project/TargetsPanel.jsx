import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Target, Trash2 } from "lucide-react";
import { toast } from "sonner";

const monday = () => { const d = new Date(Date.now() + 5.5 * 3600e3); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); return d.toISOString().slice(0, 10); };

export function TargetRow({ t }) {
  const pct = Math.min(100, (t.achieved_qty / t.target_qty) * 100);
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm" data-testid="target-row">
      <span>{t.engineer_name ? <b>{t.engineer_name} · </b> : null}{t.boq_code} {t.boq_description}</span>
      <span className="flex items-center gap-2"><span className="font-mono">{t.achieved_qty}/{t.target_qty} {t.unit}</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold text-white ${t.met ? "bg-emerald-600" : "bg-rose-600"}`} data-testid="target-status">{t.met ? "Achieved" : `${Math.round(pct)}%`}</span></span>
    </div>
  );
}

export function TargetsPanel({ project, manages }) {
  const [week, setWeek] = useState(monday());
  const [rows, setRows] = useState([]);
  const [boq, setBoq] = useState([]);
  const [f, setF] = useState({ engineer_id: "", boq_id: "", target_qty: "" });
  const load = () => api.get(`/projects/${project.id}/targets?week=${week}`).then((r) => setRows(r.data)).catch(() => {});
  useEffect(() => { load(); if (manages) api.get(`/projects/${project.id}/boq`).then((r) => setBoq(r.data)).catch(() => {}); /* eslint-disable-next-line */ }, [project.id, week]);
  const names = Object.fromEntries((project.engineers || []).map((e) => [e.id, e.name]));
  const save = async () => {
    try { const { data } = await api.put(`/projects/${project.id}/targets`, { ...f, week_start: week, target_qty: Number(f.target_qty) }); setRows(data); toast.success("Target saved"); setF({ ...f, target_qty: "" }); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const del = async (id) => { await api.delete(`/projects/${project.id}/targets/${id}`); load(); };
  const sel = "h-9 rounded-md border bg-transparent px-2 text-sm";
  return (
    <Card className="space-y-2 p-4" data-testid="targets-panel">
      <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2 font-semibold"><Target className="h-4 w-4" /> Weekly targets (approved DPR quantities)</div>
        <Input type="date" className="w-40" value={week} onChange={(e) => setWeek(e.target.value)} data-testid="target-week-input" /></div>
      {rows.length === 0 ? <p className="text-sm text-muted-foreground">No targets for this week.</p> : <div className="divide-y">{rows.map((t) => (
        <div key={t.id} className="flex items-center gap-2"><div className="flex-1"><TargetRow t={{ ...t, engineer_name: names[t.engineer_id] }} /></div>
          {manages && <Button size="sm" variant="ghost" onClick={() => del(t.id)}><Trash2 className="h-3.5 w-3.5" /></Button>}</div>))}</div>}
      {manages && <div className="flex flex-wrap gap-2 pt-2">
        <select className={sel} value={f.engineer_id} onChange={(e) => setF({ ...f, engineer_id: e.target.value })} data-testid="target-engineer-select"><option value="">Engineer</option>{(project.engineers || []).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select>
        <select className={sel} value={f.boq_id} onChange={(e) => setF({ ...f, boq_id: e.target.value })} data-testid="target-boq-select"><option value="">BOQ item</option>{boq.map((b) => <option key={b.id} value={b.id}>{b.code} {b.description} ({b.unit})</option>)}</select>
        <Input className="w-28" type="number" placeholder="Target qty" value={f.target_qty} onChange={(e) => setF({ ...f, target_qty: e.target.value })} data-testid="target-qty-input" />
        <Button size="sm" onClick={save} disabled={!f.engineer_id || !f.boq_id || !(Number(f.target_qty) > 0)} data-testid="target-save-btn">Set target</Button></div>}
    </Card>
  );
}
