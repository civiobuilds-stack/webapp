import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { isManager, formatDate, formatDateTime } from "@/lib/format";
import { SeverityBadge, DefectStatusBadge } from "@/components/StatusBadges";
import { PhotoUpload, PhotoGrid } from "@/components/PhotoUpload";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Loader2, AlertTriangle, MapPin } from "lucide-react";
import { toast } from "sonner";

const NEXT_STATUSES = ["open", "assigned", "in_progress", "awaiting_verification", "reopened", "closed"];

export function DefectsTab({ project, role }) {
  const [defects, setDefects] = useState([]);
  const [selected, setSelected] = useState(null);
  const manager = isManager(role);
  const canRaise = manager || role === "site_engineer";

  const load = () => api.get(`/projects/${project.id}/defects`).then((r) => setDefects(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h3 className="font-heading text-lg font-semibold">Defect register</h3>
          <p className="text-sm text-muted-foreground">Critical issues are flagged and escalated automatically.</p></div>
        {canRaise && <RaiseDefectDialog project={project} onDone={load} />}
      </div>

      {defects.length === 0 ? <Card className="p-10 text-center text-muted-foreground">No defects logged.</Card> : (
        <div className="space-y-3">
          {defects.map((d) => (
            <Card key={d.id} className="cursor-pointer p-4 transition-colors hover:bg-muted/40" onClick={() => setSelected(d)} data-testid="defect-row">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="font-mono text-[11px]">{d.defect_code}</Badge>
                    <SeverityBadge severity={d.severity} />
                    <DefectStatusBadge status={d.status} />
                    {d.escalated && <Badge className="bg-rose-600 text-white"><AlertTriangle className="mr-1 h-3 w-3" /> Escalated</Badge>}
                  </div>
                  <div className="mt-1.5 font-medium">{d.description}</div>
                  <div className="flex items-center gap-1 text-sm text-muted-foreground"><MapPin className="h-3.5 w-3.5" /> {d.location}</div>
                </div>
                <div className="text-right text-xs text-muted-foreground"><div>Target</div><div className="font-medium text-foreground">{formatDate(d.target_date)}</div></div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {selected && <DefectDetailDialog defect={selected} role={role} onClose={() => setSelected(null)} onDone={() => { load(); setSelected(null); }} />}
    </div>
  );
}

function RaiseDefectDialog({ project, onDone }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ location: "", category: "Structural", severity: "minor", description: "", corrective_action: "", responsible_party: "", target_date: "", assigned_to: "" });
  const [photos, setPhotos] = useState([]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    if (!f.location || !f.description) { toast.error("Location and description are required."); return; }
    setBusy(true);
    try {
      await api.post(`/projects/${project.id}/defects`, { ...f, assigned_to: f.assigned_to || null, target_date: f.target_date || null, before_photo_ids: photos });
      toast.success("Defect raised"); setOpen(false); onDone();
      setF({ location: "", category: "Structural", severity: "minor", description: "", corrective_action: "", responsible_party: "", target_date: "", assigned_to: "" }); setPhotos([]);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button data-testid="raise-defect-btn"><Plus className="h-4 w-4" /> Raise defect</Button></DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle>Raise a defect</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Location *</Label><Input value={f.location} onChange={set("location")} placeholder="Floor / room / element" data-testid="defect-location-input" /></div>
            <div className="space-y-1.5"><Label>Severity</Label>
              <Select value={f.severity} onValueChange={(v) => setF({ ...f, severity: v })}>
                <SelectTrigger data-testid="defect-severity-select"><SelectValue /></SelectTrigger>
                <SelectContent>{["minor", "major", "critical"].map((s) => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Category</Label><Input value={f.category} onChange={set("category")} /></div>
            <div className="space-y-1.5"><Label>Target date</Label><Input type="date" value={f.target_date} onChange={set("target_date")} data-testid="defect-target-input" /></div>
          </div>
          <div className="space-y-1.5"><Label>Description *</Label><Textarea value={f.description} onChange={set("description")} rows={2} data-testid="defect-description-input" /></div>
          <div className="space-y-1.5"><Label>Proposed corrective action</Label><Textarea value={f.corrective_action} onChange={set("corrective_action")} rows={2} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Responsible party</Label><Input value={f.responsible_party} onChange={set("responsible_party")} /></div>
            <div className="space-y-1.5"><Label>Assign to</Label>
              <Select value={f.assigned_to} onValueChange={(v) => setF({ ...f, assigned_to: v })}>
                <SelectTrigger data-testid="defect-assign-select"><SelectValue placeholder="Engineer" /></SelectTrigger>
                <SelectContent>{(project.engineers || []).map((e) => <SelectItem key={e.id} value={e.id}>{e.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <PhotoUpload projectId={project.id} value={photos} onChange={setPhotos} label="Before photos" />
        </div>
        <DialogFooter><Button onClick={submit} disabled={busy} data-testid="submit-defect-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Raise defect"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DefectDetailDialog({ defect, role, onClose, onDone }) {
  const manager = isManager(role);
  const [status, setStatus] = useState(defect.status);
  const [note, setNote] = useState("");
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const closing = status === "closed";

  const update = async () => {
    if (closing && !manager) { toast.error("Only a PM or admin can verify and close."); return; }
    setBusy(true);
    try { await api.post(`/defects/${defect.id}/status`, { status, note, closure_photo_ids: closing ? photos : [] }); toast.success("Defect updated"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle className="flex items-center gap-2">{defect.defect_code} <SeverityBadge severity={defect.severity} /></DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Location" value={defect.location} /><Field label="Category" value={defect.category} />
            <Field label="Reported by" value={defect.reporter?.name} /><Field label="Assigned to" value={defect.assignee?.name} />
            <Field label="Responsible" value={defect.responsible_party} /><Field label="Target date" value={formatDate(defect.target_date)} />
          </div>
          <Field label="Description" value={defect.description} />
          {defect.corrective_action && <Field label="Corrective action" value={defect.corrective_action} />}
          {defect.before_photos?.length > 0 && <div><Label className="mb-2 block">Before photos</Label><PhotoGrid photos={defect.before_photos} /></div>}
          {defect.closure_photos?.length > 0 && <div><Label className="mb-2 block">Closure photos</Label><PhotoGrid photos={defect.closure_photos} /></div>}

          <div className="rounded-lg border p-3">
            <Label className="mb-2 block text-xs uppercase tracking-wider text-muted-foreground">Status history</Label>
            <div className="space-y-2">{(defect.history || []).map((h, i) => (
              <div key={i} className="text-sm"><span className="font-semibold capitalize">{h.status.replace(/_/g, " ")}</span> — {h.note}
                <div className="text-xs text-muted-foreground">{h.by} · {formatDateTime(h.at)}</div></div>
            ))}</div>
          </div>

          <div className="space-y-3 rounded-lg bg-muted/40 p-3">
            <div className="space-y-1.5"><Label>Update status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger data-testid="defect-status-select"><SelectValue /></SelectTrigger>
                <SelectContent>{NEXT_STATUSES.map((s) => <SelectItem key={s} value={s} className="capitalize" disabled={s === "closed" && !manager}>{s.replace(/_/g, " ")}{s === "closed" && !manager ? " (PM only)" : ""}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label>Note</Label><Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} data-testid="defect-status-note" /></div>
            {closing && <PhotoUpload projectId={defect.project_id} value={photos} onChange={setPhotos} label="Closure evidence" />}
          </div>
        </div>
        <DialogFooter><Button onClick={update} disabled={busy} data-testid="update-defect-status-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save update"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, value }) {
  return <div><div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</div><div className="mt-0.5">{value || "—"}</div></div>;
}
