import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { isManager } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Loader2 } from "lucide-react";
import { toast } from "sonner";

const STATUS_CLS = { completed: "bg-emerald-100 text-emerald-700", in_progress: "bg-amber-100 text-amber-700", not_started: "bg-slate-100 text-slate-600" };

export function ActivitiesTab({ project, role, reload }) {
  const [acts, setActs] = useState([]);
  const manager = isManager(role);
  const load = () => api.get(`/projects/${project.id}/activities`).then((r) => setActs(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h3 className="font-heading text-lg font-semibold">Activities & phases</h3>
          <p className="text-sm text-muted-foreground">Overall progress is weighted by each activity's configured weight.</p></div>
        {manager && <AddActivityDialog projectId={project.id} onAdded={() => { load(); reload(); }} />}
      </div>
      {acts.length === 0 ? <Card className="p-10 text-center text-muted-foreground">No activities defined.</Card> : (
        <div className="space-y-3">
          {acts.map((a) => (
            <Card key={a.id} className="p-4" data-testid="activity-row">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[11px]">{a.phase}</Badge>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_CLS[a.status] || ""}`}>{a.status.replace("_", " ")}</span>
                    {a.requires_client_approval && <Badge variant="secondary" className="text-[11px]">Client approval</Badge>}
                  </div>
                  <div className="mt-1 font-medium">{a.name}</div>
                  <div className="text-xs text-muted-foreground">Weight: {a.weight} {a.unit && a.quantity_total ? `· ${a.quantity_completed || 0}/${a.quantity_total} ${a.unit}` : ""}</div>
                </div>
                <div className="w-40">
                  <div className="mb-1 flex justify-between text-sm"><span className="text-muted-foreground">Progress</span><span className="font-mono font-bold">{a.progress_percent}%</span></div>
                  <Progress value={a.progress_percent} className="h-2" />
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function AddActivityDialog({ projectId, onAdded }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ name: "", phase: "Foundation", weight: "10", unit: "", quantity_total: "", requires_client_approval: false });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    if (!f.name) { toast.error("Name required"); return; }
    setBusy(true);
    try {
      await api.post(`/projects/${projectId}/activities`, { ...f, weight: Number(f.weight) || 1, quantity_total: f.quantity_total ? Number(f.quantity_total) : null, unit: f.unit || null });
      toast.success("Activity added"); setOpen(false); onAdded();
      setF({ name: "", phase: "Foundation", weight: "10", unit: "", quantity_total: "", requires_client_approval: false });
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm" data-testid="add-activity-btn"><Plus className="h-4 w-4" /> Add activity</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Add activity</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Activity name</Label><Input value={f.name} onChange={set("name")} data-testid="activity-name-input" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Phase</Label>
              <Select value={f.phase} onValueChange={(v) => setF({ ...f, phase: v })}>
                <SelectTrigger data-testid="activity-phase-select"><SelectValue /></SelectTrigger>
                <SelectContent>{["Foundation", "Superstructure", "MEP", "Finishing", "External", "General"].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Weight</Label><Input type="number" value={f.weight} onChange={set("weight")} data-testid="activity-weight-input" /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Unit (optional)</Label><Input value={f.unit} onChange={set("unit")} placeholder="sq ft / cum" /></div>
            <div className="space-y-1.5"><Label>Total quantity</Label><Input type="number" value={f.quantity_total} onChange={set("quantity_total")} /></div>
          </div>
          <div className="flex items-center justify-between rounded-lg border p-3">
            <Label className="cursor-pointer">Requires client approval</Label>
            <Switch checked={f.requires_client_approval} onCheckedChange={(v) => setF({ ...f, requires_client_approval: v })} data-testid="activity-client-approval-switch" />
          </div>
        </div>
        <DialogFooter><Button onClick={submit} disabled={busy} data-testid="submit-activity-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add activity"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
