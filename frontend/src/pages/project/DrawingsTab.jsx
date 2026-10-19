import { useEffect, useState } from "react";
import { api, apiError, fileUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { FileAttach } from "@/components/FileAttach";
import { Upload, Check, X, ExternalLink } from "lucide-react";
import { toast } from "sonner";

const D_STATUS = { pending: "bg-amber-50 text-amber-800 border-amber-300", approved: "bg-emerald-50 text-emerald-800 border-emerald-300",
  rejected: "bg-rose-50 text-rose-800 border-rose-300", superseded: "bg-slate-100 text-slate-600 border-slate-300" };
const FIXED = { architect: "architectural", structural_engineer: "structural" };

function UploadDialog({ project, role, prefill, onClose, onDone }) {
  const [f, setF] = useState({ discipline: FIXED[role] || prefill?.discipline || "architectural", drawing_no: prefill?.drawing_no || "", title: prefill?.title || "", notes: "", file_ids: [] });
  const save = async () => {
    try { await api.post(`/projects/${project.id}/drawings`, { discipline: f.discipline, drawing_no: f.drawing_no, title: f.title, notes: f.notes, file_id: f.file_ids[0] });
      toast.success("Drawing uploaded — sent for approval"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>{prefill ? `New revision of ${prefill.drawing_no}` : "Upload drawing"}</DialogTitle></DialogHeader>
      <div className="space-y-3">
        <div className="space-y-1"><Label>Discipline</Label>
          <Select value={f.discipline} onValueChange={(x) => setF({ ...f, discipline: x })} disabled={!!FIXED[role]}><SelectTrigger data-testid="drawing-discipline-select"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="architectural">Architectural</SelectItem><SelectItem value="structural">Structural</SelectItem></SelectContent></Select></div>
        <div className="grid grid-cols-3 gap-2"><div className="space-y-1"><Label>Drawing no.</Label><Input value={f.drawing_no} disabled={!!prefill} onChange={(e) => setF({ ...f, drawing_no: e.target.value })} placeholder="A-101" data-testid="drawing-no-input" /></div>
          <div className="col-span-2 space-y-1"><Label>Title</Label><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Ground floor plan" data-testid="drawing-title-input" /></div></div>
        <Textarea rows={2} placeholder="Revision notes" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} data-testid="drawing-notes-input" />
        <FileAttach projectId={project.id} multiple={false} value={f.file_ids} onChange={(ids) => setF({ ...f, file_ids: ids })} testid="drawing-file" />
      </div>
      <DialogFooter><Button onClick={save} disabled={!f.drawing_no || f.title.length < 2 || !f.file_ids.length} data-testid="drawing-upload-save">Submit for approval</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function DrawingRow({ d, manages, canUpload, onDecide, onRevise }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 p-4" data-testid="drawing-row">
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-semibold">{d.drawing_no} · R{d.rev}</span><span className="font-medium">{d.title}</span>
          <Badge variant="outline" className={D_STATUS[d.status]} data-testid="drawing-status">{d.status}</Badge><Badge variant="secondary" className="capitalize">{d.discipline}</Badge></div>
        <div className="text-xs text-muted-foreground">by {d.uploaded_by_name} · {formatDateTime(d.created_at)}{d.notes ? ` · ${d.notes}` : ""}</div>
        {d.review && <div className="text-xs">{d.status === "rejected" ? "Rejected" : "Reviewed"} by {d.review.by}{d.review.remarks ? ` — ${d.review.remarks}` : ""}</div>}
      </div>
      <div className="flex flex-wrap gap-1">
        <Button size="sm" variant="outline" asChild><a href={fileUrl(d.file_id)} target="_blank" rel="noreferrer" data-testid="drawing-view-btn"><ExternalLink className="h-4 w-4" /> View</a></Button>
        {manages && d.status === "pending" && <><Button size="sm" onClick={() => onDecide(d, "approve")} data-testid="drawing-approve-btn"><Check className="h-4 w-4" /> Approve</Button>
          <Button size="sm" variant="outline" onClick={() => onDecide(d, "reject")} data-testid="drawing-reject-btn"><X className="h-4 w-4" /> Reject</Button></>}
        {canUpload && ["approved", "rejected"].includes(d.status) && <Button size="sm" variant="ghost" onClick={() => onRevise(d)} data-testid="drawing-revise-btn">Upload revision</Button>}
      </div>
    </div>
  );
}

export function DrawingsTab({ project, user, manages }) {
  const [rows, setRows] = useState([]);
  const [up, setUp] = useState(null);
  const [filter, setFilter] = useState("all");
  const load = () => api.get(`/projects/${project.id}/drawings`).then((r) => setRows(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const canUploadAny = manages || !!FIXED[user.role];
  const canUpload = (d) => manages || FIXED[user.role] === d.discipline;
  const decide = async (d, action) => {
    const remarks = action === "reject" ? window.prompt("Reason for rejecting?") : "";
    if (action === "reject" && !remarks) return;
    try { await api.post(`/drawings/${d.id}/decision`, { action, remarks }); toast.success(action === "approve" ? "Approved — visible to client" : "Rejected"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const shown = rows.filter((d) => filter === "all" || d.discipline === filter);
  return (
    <div className="space-y-4" data-testid="drawings-tab">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="font-heading text-lg font-semibold">Drawings</h2>
        <p className="text-sm text-muted-foreground">{user.role === "client" ? "Approved architectural and structural drawings." : "Architect / Structural uploads → Owner or PM approves → client can view."}</p></div>
        <div className="flex gap-2">
          <Select value={filter} onValueChange={setFilter}><SelectTrigger className="w-40" data-testid="drawing-filter"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">All disciplines</SelectItem><SelectItem value="architectural">Architectural</SelectItem><SelectItem value="structural">Structural</SelectItem></SelectContent></Select>
          {canUploadAny && <Button onClick={() => setUp({})} data-testid="upload-drawing-btn"><Upload className="h-4 w-4" /> Upload</Button>}</div></div>
      <Card className="divide-y">
        {shown.length === 0 && <p className="p-4 text-sm text-muted-foreground">No drawings yet.</p>}
        {shown.map((d) => <DrawingRow key={d.id} d={d} manages={manages} canUpload={canUpload(d)} onDecide={decide} onRevise={(x) => setUp({ prefill: x })} />)}
      </Card>
      {up && <UploadDialog project={project} role={user.role} prefill={up.prefill} onClose={() => setUp(null)} onDone={() => { setUp(null); load(); }} />}
    </div>
  );
}
