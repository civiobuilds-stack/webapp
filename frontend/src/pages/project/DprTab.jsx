import { useEffect, useState } from "react";
import { api, apiError, API, getToken } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { PhotoGrid } from "@/components/PhotoUpload";
import { DprEditor } from "@/pages/project/DprEditor";
import { Plus, FileDown, Send, Check, RotateCcw, X, Pencil } from "lucide-react";
import { toast } from "sonner";

export const DPR_STATUS = {
  draft: "bg-slate-100 text-slate-700 border-slate-300", submitted: "bg-sky-50 text-sky-800 border-sky-300",
  returned: "bg-orange-50 text-orange-800 border-orange-300", approved: "bg-emerald-50 text-emerald-800 border-emerald-300",
  rejected: "bg-rose-50 text-rose-800 border-rose-300",
};
const can = (p, a) => (p?.dpr || []).includes(a);

function Rows({ title, rows }) {
  if (!rows.length) return null;
  return <div><div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</div><ul className="mt-1 space-y-0.5 text-sm">{rows.map((r, i) => <li key={i}>{r}</li>)}</ul></div>;
}

function DprView({ dpr, perms, userId, onEdit, onChanged }) {
  const [review, setReview] = useState(null);
  const [comment, setComment] = useState("");
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); onChanged(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  const submitReview = () => act(() => api.post(`/dprs/${dpr.id}/review`, { action: review, comment }), "Decision recorded").then(() => { setReview(null); setComment(""); });
  const editable = ["draft", "returned"].includes(dpr.status);
  return (
    <Card className="space-y-4 p-5" data-testid="dpr-detail">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h3 className="font-heading text-lg font-bold">DPR · {formatDate(dpr.report_date)}</h3>
          <p className="text-xs text-muted-foreground">By {dpr.created_by_name}{dpr.weather ? ` · ${dpr.weather}` : ""}</p></div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className={DPR_STATUS[dpr.status]} data-testid="dpr-status">{dpr.status}</Badge>
          {editable && can(perms, "edit") && <Button size="sm" variant="outline" onClick={onEdit} data-testid="dpr-edit-btn"><Pencil className="h-4 w-4" /> Edit</Button>}
          {editable && can(perms, "submit") && <Button size="sm" onClick={() => act(() => api.post(`/dprs/${dpr.id}/submit`), "DPR submitted for review")} data-testid="dpr-submit-btn"><Send className="h-4 w-4" /> Submit</Button>}
          {dpr.status === "submitted" && can(perms, "approve") && dpr.created_by !== userId && <>
            <Button size="sm" onClick={() => setReview("approve")} data-testid="dpr-approve-btn"><Check className="h-4 w-4" /> Approve</Button>
            <Button size="sm" variant="outline" onClick={() => setReview("return")} data-testid="dpr-return-btn"><RotateCcw className="h-4 w-4" /> Return</Button>
            <Button size="sm" variant="outline" onClick={() => setReview("reject")} data-testid="dpr-reject-btn"><X className="h-4 w-4" /> Reject</Button></>}
          <a href={`${API}/dprs/${dpr.id}/pdf?auth=${getToken()}`} target="_blank" rel="noreferrer"><Button size="sm" variant="secondary" data-testid="dpr-pdf-btn"><FileDown className="h-4 w-4" /> Generate DPR Report</Button></a>
        </div>
      </div>
      {dpr.review_comment && <p className="rounded-lg bg-muted p-3 text-sm" data-testid="dpr-review-comment"><b>Reviewer:</b> {dpr.review_comment}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <Rows title="BOQ quantities (today)" rows={(dpr.boq_entries || []).map((e) => `${e.code} ${e.description}: ${e.qty} ${e.unit} @ ${e.location || "—"} · cumulative before ${e.cumulative_before}/${e.approved_qty}${e.excess ? " · ⚠ EXCESS — review" : ""}`)} />
        <Rows title="Activities (planned vs actual)" rows={dpr.activities.map((a) => `${a.description}: ${a.actual_qty}/${a.planned_qty} ${a.unit} · ${a.actual_pct}% vs ${a.planned_pct}%`)} />
        <Rows title="Manpower" rows={dpr.manpower.map((m) => `${m.name}: ${m.count}${m.hours ? ` · ${m.hours}h` : ""}`)} />
        <Rows title="Equipment" rows={dpr.equipment.map((m) => `${m.name}: ${m.count}${m.hours ? ` · ${m.hours}h` : ""}`)} />
        <Rows title="Materials" rows={dpr.materials.map((m) => `${m.item} ${m.quantity} ${m.unit} — ${m.status}${m.note ? ` (${m.note})` : ""}`)} />
        {[["Quality", dpr.quality_notes], ["Safety", dpr.safety_notes], ["Delays & hindrances", dpr.delays], ["Next-day plan", dpr.next_day_plan]].filter(([, v]) => v).map(([k, v]) => <Rows key={k} title={k} rows={[v]} />)}
      </div>
      {dpr.photo_files?.length > 0 && <PhotoGrid photos={dpr.photo_files} />}
      {review && (
        <Dialog open onOpenChange={() => setReview(null)}>
          <DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle className="capitalize">{review} DPR</DialogTitle></DialogHeader>
            <Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder={review === "approve" ? "Comment (optional)" : "What needs correcting? (required)"} data-testid="dpr-review-comment-input" />
            <DialogFooter><Button onClick={submitReview} disabled={review !== "approve" && !comment.trim()} data-testid="dpr-review-confirm-btn">Confirm</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </Card>
  );
}

function BoqPanel({ project }) {
  const [items, setItems] = useState([]);
  const [f, setF] = useState({ code: "", description: "", unit: "", approved_qty: 0 });
  const load = () => api.get(`/projects/${project.id}/boq`).then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const add = async () => { try { await api.post(`/projects/${project.id}/boq`, f); toast.success("BOQ item approved"); setF({ code: "", description: "", unit: "", approved_qty: 0 }); load(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  return (
    <Card className="space-y-2 p-4" data-testid="boq-panel">
      <div className="font-semibold">Approved BOQ</div>
      {items.map((b) => <div key={b.id} className="flex flex-wrap justify-between gap-2 text-sm" data-testid="boq-row"><span><b>{b.code}</b> {b.description}</span>
        <span>{b.accepted_qty}/{b.approved_qty} {b.unit} · remaining {b.remaining_qty} · <b>{b.progress_pct}%</b></span></div>)}
      <div className="flex flex-wrap gap-2 pt-2">
        {[["code", "Code"], ["description", "Description"], ["unit", "Unit"], ["approved_qty", "Approved qty"]].map(([k, l]) => (
          <input key={k} className="h-9 min-w-[100px] flex-1 rounded-md border bg-background px-2 text-sm" placeholder={l} type={k === "approved_qty" ? "number" : "text"} value={f[k]}
            onChange={(e) => setF({ ...f, [k]: k === "approved_qty" ? Number(e.target.value) : e.target.value })} data-testid={`boq-${k}-input`} />))}
        <Button size="sm" onClick={add} data-testid="boq-add-btn">Add (PM)</Button>
      </div>
    </Card>
  );
}

export function DprTab({ project, userId, perms, initialDpr }) {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState(null);
  const [editing, setEditing] = useState(null);
  const load = () => api.get(`/projects/${project.id}/dprs`).then((r) => setList(r.data)).catch(() => {});
  const open = (id) => api.get(`/dprs/${id}`).then((r) => setSel(r.data)).catch((e) => toast.error(apiError(e.response?.data?.detail)));
  useEffect(() => { load(); if (initialDpr) open(initialDpr); /* eslint-disable-next-line */ }, [project.id]);
  const changed = () => { load(); if (sel) open(sel.id); };
  if (!can(perms, "view")) return <Card className="p-8 text-center text-sm text-muted-foreground" data-testid="dpr-no-access">You don't have permission to view DPRs on this project.</Card>;
  return (
    <div className="space-y-4" data-testid="dpr-tab">
      <div className="flex items-center justify-between"><h2 className="font-heading text-lg font-semibold">Daily Progress Reports</h2>
        {can(perms, "create") && <Button onClick={() => setEditing({})} data-testid="new-dpr-btn"><Plus className="h-4 w-4" /> New DPR</Button>}</div>
      <BoqPanel project={project} />
      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <Card className="divide-y">
          {list.length === 0 && <p className="p-4 text-sm text-muted-foreground">No DPRs yet.</p>}
          {list.map((d) => (
            <button key={d.id} onClick={() => open(d.id)} className={`flex w-full items-center justify-between p-3 text-left text-sm hover:bg-muted/50 ${sel?.id === d.id ? "bg-muted" : ""}`} data-testid="dpr-row">
              <span><span className="font-medium">{formatDate(d.report_date)}</span><span className="block text-xs text-muted-foreground">{d.created_by_name}</span></span>
              <Badge variant="outline" className={DPR_STATUS[d.status]}>{d.status}</Badge>
            </button>
          ))}
        </Card>
        {sel ? <DprView dpr={sel} perms={perms} userId={userId} onEdit={() => setEditing(sel)} onChanged={changed} /> : <Card className="p-8 text-center text-sm text-muted-foreground">Select a DPR to view.</Card>}
      </div>
      {editing && <DprEditor project={project} dpr={editing} onClose={() => setEditing(null)} onSaved={(d) => { setEditing(null); load(); open(d.id); }} />}
    </div>
  );
}
