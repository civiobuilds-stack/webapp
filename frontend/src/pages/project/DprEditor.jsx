import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { CameraCapture } from "@/components/CameraCapture";
import { useEffect } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";

const today = () => new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);
const BLANK = { activities: { description: "", unit: "", planned_qty: 0, actual_qty: 0, planned_pct: 0, actual_pct: 0 },
  manpower: { name: "", count: 0, hours: 0 }, equipment: { name: "", count: 0, hours: 0 }, materials: { item: "", quantity: 0, unit: "", status: "received", note: "" } };
const COLS = {
  activities: [["description", "Activity", "text"], ["unit", "Unit", "text"], ["planned_qty", "Plan qty"], ["actual_qty", "Actual qty"], ["planned_pct", "Plan %"], ["actual_pct", "Actual %"]],
  manpower: [["name", "Trade", "text"], ["count", "Count"], ["hours", "Hours"]],
  equipment: [["name", "Equipment", "text"], ["count", "Count"], ["hours", "Hours"]],
  materials: [["item", "Item", "text"], ["quantity", "Qty"], ["unit", "Unit", "text"], ["status", "received/delayed", "text"], ["note", "Note", "text"]],
};

function RowEditor({ k, title, rows, set }) {
  const upd = (i, f, v) => set(rows.map((r, j) => (j === i ? { ...r, [f]: v } : r)));
  return (
    <div className="space-y-2" data-testid={`dpr-section-${k}`}>
      <div className="flex items-center justify-between"><Label>{title}</Label>
        <Button type="button" size="sm" variant="outline" onClick={() => set([...rows, { ...BLANK[k] }])} data-testid={`dpr-add-${k}`}><Plus className="h-3 w-3" /> Add</Button></div>
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2">
          {COLS[k].map(([f, ph, t]) => (
            <Input key={f} className={t ? "min-w-[120px] flex-1" : "w-24"} type={t || "number"} placeholder={ph} value={r[f]}
              onChange={(e) => upd(i, f, t ? e.target.value : Number(e.target.value))} data-testid={`dpr-${k}-${i}-${f}`} />
          ))}
          <Button type="button" size="icon" variant="ghost" onClick={() => set(rows.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>
        </div>
      ))}
    </div>
  );
}

function BoqEntries({ boq, entries, setEntries }) {
  const upd = (i, k, v) => setEntries(entries.map((e, j) => (j === i ? { ...e, [k]: v } : e)));
  return (
    <div className="space-y-2" data-testid="dpr-boq-section">
      <div className="flex items-center justify-between"><Label>Approved BOQ items — today's executed quantity</Label>
        <Button type="button" size="sm" variant="outline" disabled={!boq.length} onClick={() => setEntries([...entries, { boq_id: "", qty: 0, location: "", remarks: "" }])} data-testid="dpr-add-boq"><Plus className="h-3 w-3" /> Add</Button></div>
      {!boq.length && <p className="text-xs text-muted-foreground">No approved BOQ items yet — the project manager adds them on the DPR tab.</p>}
      {entries.map((e, i) => {
        const b = boq.find((x) => x.id === e.boq_id);
        const over = b && b.accepted_qty + e.qty > b.approved_qty;
        return (
          <div key={i} className="space-y-1 rounded-lg border p-2">
            <div className="flex flex-wrap gap-2">
              <Select value={e.boq_id} onValueChange={(v) => upd(i, "boq_id", v)}><SelectTrigger className="min-w-[200px] flex-1" data-testid={`dpr-boq-${i}-item`}><SelectValue placeholder="BOQ item" /></SelectTrigger>
                <SelectContent>{boq.map((x) => <SelectItem key={x.id} value={x.id}>{x.code} · {x.description}</SelectItem>)}</SelectContent></Select>
              <Input className="w-24" type="number" placeholder="Qty" value={e.qty} onChange={(ev) => upd(i, "qty", Number(ev.target.value))} data-testid={`dpr-boq-${i}-qty`} />
              <Input className="w-36" placeholder="Location" value={e.location} onChange={(ev) => upd(i, "location", ev.target.value)} data-testid={`dpr-boq-${i}-location`} />
              <Input className="min-w-[120px] flex-1" placeholder="Remarks" value={e.remarks} onChange={(ev) => upd(i, "remarks", ev.target.value)} />
              <Button type="button" size="icon" variant="ghost" onClick={() => setEntries(entries.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>
            </div>
            {b && <p className={`text-xs ${over ? "font-semibold text-rose-600" : "text-muted-foreground"}`} data-testid={`dpr-boq-${i}-calc`}>
              Approved {b.approved_qty} {b.unit} · accepted so far {b.accepted_qty} · remaining {b.remaining_qty} · {b.progress_pct}%{over ? " · EXCESS — will be flagged for review" : ""}</p>}
          </div>
        );
      })}
    </div>
  );
}

export function DprEditor({ project, dpr, onClose, onSaved }) {
  const [f, setF] = useState({
    report_date: dpr.report_date || today(), weather: dpr.weather || "", activities: dpr.activities || [], manpower: dpr.manpower || [],
    equipment: dpr.equipment || [], materials: dpr.materials || [], quality_notes: dpr.quality_notes || "", safety_notes: dpr.safety_notes || "",
    delays: dpr.delays || "", next_day_plan: dpr.next_day_plan || "",
  });
  const [photos, setPhotos] = useState(dpr.photos || []);
  const [boq, setBoq] = useState([]);
  const [entries, setEntries] = useState((dpr.boq_entries || []).map(({ boq_id, qty, location, remarks }) => ({ boq_id, qty, location, remarks })));
  useEffect(() => { api.get(`/projects/${project.id}/boq`).then((r) => setBoq(r.data)).catch(() => {}); }, [project.id]);
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => setF({ ...f, [k]: v });
  const save = async () => {
    setBusy(true);
    try {
      const body = { ...f, photos, boq_entries: entries.filter((e) => e.boq_id && e.qty > 0) };
      const r = dpr.id ? await api.put(`/dprs/${dpr.id}`, body) : await api.post(`/projects/${project.id}/dprs`, body);
      toast.success("DPR saved as draft"); onSaved(r.data);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl" data-testid="dpr-editor">
        <DialogHeader><DialogTitle>{dpr.id ? "Edit DPR" : "New Daily Progress Report"}</DialogTitle></DialogHeader>
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Reporting date</Label><Input type="date" value={f.report_date} onChange={(e) => set("report_date")(e.target.value)} data-testid="dpr-date-input" /></div>
            <div className="space-y-1.5"><Label>Weather</Label><Input value={f.weather} onChange={(e) => set("weather")(e.target.value)} data-testid="dpr-weather-input" /></div>
          </div>
          <BoqEntries boq={boq} entries={entries} setEntries={setEntries} />
          <RowEditor k="activities" title="Work activities & quantities" rows={f.activities} set={set("activities")} />
          <RowEditor k="manpower" title="Manpower" rows={f.manpower} set={set("manpower")} />
          <RowEditor k="equipment" title="Equipment" rows={f.equipment} set={set("equipment")} />
          <RowEditor k="materials" title="Materials received / delayed" rows={f.materials} set={set("materials")} />
          <div className="space-y-2">
            <CameraCapture projectId={project.id} label="Site photos" value={photos.map((p) => p.file_id)}
              onChange={(ids) => setPhotos(ids.map((id) => photos.find((p) => p.file_id === id) || { file_id: id, caption: "" }))} />
            {photos.map((p, i) => <Input key={p.file_id} placeholder={`Caption for photo ${i + 1}`} value={p.caption}
              onChange={(e) => setPhotos(photos.map((x) => (x.file_id === p.file_id ? { ...x, caption: e.target.value } : x)))} data-testid={`dpr-photo-caption-${i}`} />)}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {[["quality_notes", "Quality observations"], ["safety_notes", "Safety observations"], ["delays", "Delays & hindrances"], ["next_day_plan", "Next-day activities"]].map(([k, l]) => (
              <div key={k} className="space-y-1.5"><Label>{l}</Label><Textarea rows={3} value={f[k]} onChange={(e) => set(k)(e.target.value)} data-testid={`dpr-${k}-input`} /></div>
            ))}
          </div>
        </div>
        <DialogFooter><Button onClick={save} disabled={busy} data-testid="dpr-save-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save draft"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
