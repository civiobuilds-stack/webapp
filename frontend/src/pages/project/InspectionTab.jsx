import { useEffect, useState } from "react";
import { api, apiError, API, getToken } from "@/lib/api";
import { isManager, formatDateTime } from "@/lib/format";
import { CameraCapture } from "@/components/CameraCapture";
import { PhotoGrid } from "@/components/PhotoUpload";
import { DocumentsPanel } from "@/pages/project/DocumentsPanel";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { FileDown, Loader2, ClipboardCheck } from "lucide-react";
import { toast } from "sonner";

const ST = { pass: ["Pass", "bg-emerald-600"], fail: ["Fail", "bg-rose-600"], na: ["N/A", "bg-slate-500"], pending: ["Pending", "bg-amber-500"] };

function ItemDialog({ item, project, onClose, onDone }) {
  const [f, setF] = useState({ status: item.status === "pending" ? "pass" : item.status, remarks: item.remarks || "", responsible_id: item.responsible_id || "", photo_ids: item.photo_ids || [] });
  const team = [project.project_manager, ...(project.engineers || [])].filter(Boolean);
  const save = async () => {
    try { await api.put(`/inspection-items/${item.id}`, { ...f, responsible_id: f.responsible_id || null }); toast.success("Inspection saved"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg" data-testid="inspection-item-dialog">
      <DialogHeader><DialogTitle>{item.stage} · {item.item}</DialogTitle></DialogHeader>
      <div className="space-y-4">
        <div className="flex gap-2">{["pass", "fail", "na"].map((s) => <Button key={s} type="button" variant={f.status === s ? "default" : "outline"} onClick={() => setF({ ...f, status: s })} data-testid={`inspect-status-${s}`}>{ST[s][0]}</Button>)}</div>
        <div className="space-y-1.5"><Label>Responsible person</Label>
          <Select value={f.responsible_id} onValueChange={(v) => setF({ ...f, responsible_id: v })}><SelectTrigger data-testid="inspect-responsible-select"><SelectValue placeholder="Choose" /></SelectTrigger>
            <SelectContent>{team.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent></Select></div>
        <div className="space-y-1.5"><Label>Remarks {f.status === "fail" ? "*" : ""}</Label><Textarea rows={2} value={f.remarks} onChange={(e) => setF({ ...f, remarks: e.target.value })} data-testid="inspect-remarks-input" /></div>
        <CameraCapture projectId={project.id} value={f.photo_ids} onChange={(ids) => setF({ ...f, photo_ids: ids })} label={`Inspection photos ${f.status === "na" ? "(optional)" : "*"}`} />
      </div>
      <DialogFooter><Button onClick={save} data-testid="inspect-save-btn">Save inspection</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function Signoff({ g, project, onDone }) {
  const [remarks, setRemarks] = useState("");
  const [open, setOpen] = useState(false);
  const ready = g.items.every((i) => i.status === "pass" || i.status === "na");
  const save = async () => {
    try { await api.post(`/projects/${project.id}/inspection/signoff`, { stage: g.stage, remarks }); toast.success("Stage signed off"); setOpen(false); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (<>
    <Button size="sm" disabled={!ready} onClick={() => setOpen(true)} data-testid="stage-signoff-btn">{ready ? "I approve this stage" : "Sign-off available when all items pass / N/A"}</Button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>Approve {g.stage}</DialogTitle></DialogHeader>
      <Textarea rows={3} placeholder="Remarks (optional)" value={remarks} onChange={(e) => setRemarks(e.target.value)} data-testid="signoff-remarks-input" />
      <DialogFooter><Button onClick={save} data-testid="signoff-confirm-btn">I approve</Button></DialogFooter></DialogContent></Dialog>
  </>);
}

export function InspectionTab({ project, role }) {
  const [d, setD] = useState(null);
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);
  const canInspect = isManager(role) || role === "site_engineer";
  const canReport = isManager(role) || role === "client";
  const load = () => api.get(`/projects/${project.id}/inspection`).then((r) => setD(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const report = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/projects/${project.id}/inspection/report`); toast.success("Inspection report generated"); window.open(`${API}/reports/${data.id}/download?auth=${getToken()}`, "_blank"); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  if (!d) return null;
  const s = d.summary, done = s.total - s.pending;
  return (
    <div className="space-y-4" data-testid="inspection-tab">
      <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="min-w-[240px] flex-1"><h3 className="flex items-center gap-2 font-heading text-lg font-semibold"><ClipboardCheck className="h-5 w-5" /> Inspection checklist</h3>
          <p className="text-sm text-muted-foreground" data-testid="inspection-summary">{done}/{s.total} inspected · {s.pass} pass · {s.fail} fail · {s.na} N/A</p>
          <Progress value={s.total ? (done / s.total) * 100 : 0} className="mt-2 h-2" /></div>
        {canReport && <Button onClick={report} disabled={busy} data-testid="generate-inspection-report-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Generate Inspection Report</Button>}
      </Card>
      <Accordion type="multiple" className="space-y-2">
        {d.stages.map((g) => {
          const fails = g.items.filter((i) => i.status === "fail").length, ok = g.items.filter((i) => i.status !== "pending").length;
          return (
            <AccordionItem key={g.stage} value={g.stage} className="rounded-xl border bg-card px-4" data-testid="inspection-stage">
              <AccordionTrigger className="hover:no-underline"><div className="flex flex-1 items-center justify-between pr-3"><span className="font-medium">{g.stage}</span>
                <span className="flex gap-2 text-xs">{g.signoff && <Badge className="bg-emerald-600 text-white">Signed off</Badge>}{fails > 0 && <Badge className="bg-rose-600 text-white">{fails} fail</Badge>}<Badge variant="secondary">{ok}/{g.items.length}</Badge></span></div></AccordionTrigger>
              <AccordionContent>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/40 p-2 text-xs" data-testid="stage-signoff">
                  {g.signoff ? <span className="font-medium text-emerald-700" data-testid="stage-signed">Client approved by {g.signoff.signed_by_name} on {formatDateTime(g.signoff.signed_at)}{g.signoff.remarks ? ` — ${g.signoff.remarks}` : ""}</span>
                    : g.items.every((i) => i.status === "pass" || i.status === "na") ? <span className="text-muted-foreground">Ready — awaiting client sign-off</span> : <span className="text-muted-foreground">Client sign-off once all items pass / N/A</span>}
                  {!g.signoff && role === "client" && <Signoff g={g} project={project} onDone={load} />}</div>
                <div className="divide-y">{g.items.map((i) => (
                <div key={i.id} className="flex flex-wrap items-start justify-between gap-2 py-3" data-testid="inspection-item">
                  <div className="min-w-0 flex-1"><div className="text-sm">{i.item}</div>
                    {(i.remarks || i.responsible_name) && <div className="text-xs text-muted-foreground">{i.remarks}{i.responsible_name ? ` · Responsible: ${i.responsible_name}` : ""}</div>}
                    {i.photo_ids?.length > 0 && <div className="mt-2 max-w-sm"><PhotoGrid photoIds={i.photo_ids} /></div>}</div>
                  <div className="flex items-center gap-2"><Badge className={`${ST[i.status][1]} text-white`} data-testid="inspection-item-status">{ST[i.status][0]}</Badge>
                    {canInspect && <Button size="sm" variant="outline" onClick={() => setSel(i)} data-testid="inspect-item-btn">Inspect</Button>}</div>
                </div>))}</div></AccordionContent>
            </AccordionItem>);
        })}
      </Accordion>
      <DocumentsPanel project={project} canAdd={canInspect} canDelete={isManager(role)} />
      {sel && <ItemDialog item={sel} project={project} onClose={() => setSel(null)} onDone={() => { setSel(null); load(); }} />}
    </div>
  );
}
