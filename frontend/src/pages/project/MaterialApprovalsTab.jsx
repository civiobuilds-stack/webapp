import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Check, X, Send, Package } from "lucide-react";
import { toast } from "sonner";

const STEPS = [["pending_pm", "Engineer request"], ["pending_client", "PM review"], ["approved", "Client approval"]];
const COLOR = { pending_pm: "bg-amber-500", pending_client: "bg-blue-600", approved: "bg-emerald-600", rejected: "bg-rose-600" };

export function MatStepper({ m }) {
  const idx = { pending_pm: 1, pending_client: 2, approved: 3, rejected: -1 }[m.status];
  return (
    <div className="flex items-center gap-1 text-[11px]" data-testid="mat-stepper">
      {STEPS.map(([k, l], i) => <div key={k} className="flex items-center gap-1">
        <span className={`rounded-full px-2 py-0.5 ${idx > i ? "bg-emerald-100 text-emerald-800" : idx === i ? "bg-blue-100 font-semibold text-blue-800" : "bg-muted text-muted-foreground"}`}>{l}</span>
        {i < STEPS.length - 1 && <span className="text-muted-foreground">›</span>}</div>)}
    </div>
  );
}

export function DecideDialog({ m, kind, onClose, onDone }) {
  const [remarks, setRemarks] = useState("");
  const act = async (action) => {
    try { await api.post(`/material-approvals/${m.id}/${kind}`, { action, remarks }); toast.success("Decision saved"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md" data-testid="mat-decide-dialog"><DialogHeader><DialogTitle>{m.quantity} {m.unit} · {m.item}</DialogTitle></DialogHeader>
      <p className="text-sm text-muted-foreground">Required by {formatDate(m.required_date)} · requested by {m.requested_by_name}{m.remarks ? ` — ${m.remarks}` : ""}</p>
      <div className="space-y-1.5"><Label>Remarks {kind === "client" ? "(required to reject)" : ""}</Label><Textarea rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} data-testid="mat-remarks-input" /></div>
      <DialogFooter className="gap-2">
        <Button variant="outline" className="text-rose-600" onClick={() => act("reject")} data-testid="mat-reject-btn"><X className="h-4 w-4" /> Reject</Button>
        {kind === "pm" ? <Button onClick={() => act("submit")} data-testid="mat-submit-client-btn"><Send className="h-4 w-4" /> Send to client</Button>
          : <Button className="bg-emerald-600 text-white hover:bg-emerald-700" onClick={() => act("approve")} data-testid="mat-approve-btn"><Check className="h-4 w-4" /> Approve</Button>}
      </DialogFooter></DialogContent></Dialog>
  );
}

function NewDialog({ pid, onClose, onDone }) {
  const [f, setF] = useState({ item: "", quantity: "", unit: "nos", required_date: "", remarks: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { await api.post(`/projects/${pid}/material-approvals`, { ...f, quantity: Number(f.quantity), required_date: f.required_date || null }); toast.success("Material request raised"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>New material request</DialogTitle></DialogHeader>
      <div className="space-y-3"><div className="space-y-1.5"><Label>Item</Label><Input value={f.item} onChange={set("item")} data-testid="mat-item-input" /></div>
        <div className="grid grid-cols-3 gap-2"><div className="space-y-1.5"><Label>Quantity</Label><Input type="number" value={f.quantity} onChange={set("quantity")} data-testid="mat-qty-input" /></div>
          <div className="space-y-1.5"><Label>Unit</Label><Input value={f.unit} onChange={set("unit")} data-testid="mat-unit-input" /></div>
          <div className="space-y-1.5"><Label>Required date</Label><Input type="date" value={f.required_date} onChange={set("required_date")} data-testid="mat-date-input" /></div></div>
        <div className="space-y-1.5"><Label>Remarks</Label><Textarea rows={2} value={f.remarks} onChange={set("remarks")} data-testid="mat-remarks-new" /></div></div>
      <DialogFooter><Button onClick={save} disabled={!f.item || !(Number(f.quantity) > 0)} data-testid="mat-save-btn">Raise request</Button></DialogFooter></DialogContent></Dialog>
  );
}

export function MaterialApprovalsTab({ project, role, userId }) {
  const [items, setItems] = useState([]);
  const [dlg, setDlg] = useState(null);
  const load = () => api.get(`/projects/${project.id}/material-approvals`).then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const mgr = role === "admin" || role === "project_manager";
  const isClient = role === "client" ? project.client_id === userId : role === "admin";
  const done = () => { setDlg(null); load(); };
  return (
    <div className="space-y-4" data-testid="materials-tab">
      <div className="flex items-center justify-between"><div><h3 className="font-heading text-lg font-semibold">Material requests</h3>
        <p className="text-sm text-muted-foreground">Engineer requests → PM reviews → Client approves. No costing or purchasing.</p></div>
        {role !== "client" && <Button onClick={() => setDlg({ type: "new" })} data-testid="new-mat-btn"><Plus className="h-4 w-4" /> New request</Button>}</div>
      {items.length === 0 ? <Card className="p-10 text-center text-muted-foreground"><Package className="mx-auto mb-2 h-8 w-8" />No material requests yet.</Card> : items.map((m) => (
        <Card key={m.id} className="space-y-2 p-4" data-testid="mat-row">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div><div className="font-medium">{m.quantity} {m.unit} · {m.item}</div>
              <div className="text-xs text-muted-foreground">Required {formatDate(m.required_date)} · by {m.requested_by_name}{m.remarks ? ` · ${m.remarks}` : ""}</div></div>
            <Badge className={`${COLOR[m.status]} text-white`} data-testid="mat-status">{m.stage_label}</Badge></div>
          <MatStepper m={m} />
          <div className="space-y-0.5 text-xs text-muted-foreground" data-testid="mat-history">{(m.history || []).map((h, i) => <div key={i}>{formatDateTime(h.at)} · {h.by} — {h.status.replace("_", " ")}{h.remarks ? `: ${h.remarks}` : ""}</div>)}</div>
          <div className="flex gap-2">
            {mgr && m.status === "pending_pm" && <Button size="sm" onClick={() => setDlg({ type: "pm", m })} data-testid="mat-pm-review-btn">Review</Button>}
            {isClient && m.status === "pending_client" && <Button size="sm" onClick={() => setDlg({ type: "client", m })} data-testid="mat-client-review-btn">Approve / Reject</Button>}
          </div>
        </Card>))}
      {dlg?.type === "new" && <NewDialog pid={project.id} onClose={() => setDlg(null)} onDone={done} />}
      {dlg?.m && <DecideDialog m={dlg.m} kind={dlg.type} onClose={() => setDlg(null)} onDone={done} />}
    </div>
  );
}

export function PendingMaterials({ role }) {
  const [items, setItems] = useState([]);
  const [dlg, setDlg] = useState(null);
  const load = () => api.get("/material-approvals/pending").then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  if (!items.length) return null;
  const kindFor = (m) => (m.status === "pending_pm" ? (role === "client" ? null : "pm") : (role === "client" || role === "admin" ? "client" : null));
  return (
    <Card className="space-y-3 p-5" data-testid="pending-materials">
      <h3 className="font-heading font-semibold">Material requests awaiting decision <Badge variant="secondary">{items.length}</Badge></h3>
      {items.map((m) => (
        <div key={m.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3" data-testid="pending-mat-row">
          <div><div className="text-sm font-medium">{m.quantity} {m.unit} · {m.item} <span className="text-xs text-muted-foreground">— {m.project_name}</span></div>
            <div className="mt-1"><MatStepper m={m} /></div></div>
          {kindFor(m) ? <Button size="sm" onClick={() => setDlg({ m, kind: kindFor(m) })} data-testid="pending-mat-act-btn">{kindFor(m) === "pm" ? "Review" : "Approve / Reject"}</Button>
            : <Badge variant="outline">{m.stage_label}</Badge>}
        </div>))}
      {dlg && <DecideDialog m={dlg.m} kind={dlg.kind} onClose={() => setDlg(null)} onDone={() => { setDlg(null); load(); }} />}
    </Card>
  );
}
