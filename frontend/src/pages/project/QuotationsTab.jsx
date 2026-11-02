import { useEffect, useState } from "react";
import { api, apiError, API, getToken } from "@/lib/api";
import { formatINR, formatDate, formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Trash2, Send, FileText, PenLine, Check, MessageSquare, X } from "lucide-react";
import { toast } from "sonner";
import { openPath } from "@/components/AuthImage";

const Q_STATUS = {
  draft: ["Draft", "bg-slate-100 text-slate-700"], sent: ["Awaiting client", "bg-amber-50 text-amber-800"],
  accepted: ["Accepted & signed", "bg-emerald-600 text-white"], rejected: ["Rejected", "bg-rose-50 text-rose-800"],
  changes_requested: ["Changes requested", "bg-orange-50 text-orange-800"], revision_in_progress: ["Revision in progress", "bg-sky-50 text-sky-800"],
};
const blankItem = { description: "", unit: "nos", qty: 1, rate: 0 };

function QuoteEditor({ project, quote, mode, onClose, onDone }) {
  const last = quote?.revisions?.[quote.revisions.length - 1];
  const [f, setF] = useState({ title: quote?.title || "", items: last?.items?.map(({ amount, ...i }) => i) || [{ ...blankItem }],
    tax_pct: last?.tax_pct ?? 18, discount: last?.discount ?? 0, valid_until: last?.valid_until || "", notes: last?.notes || "", terms: last?.terms || "" });
  const setItem = (i, k, v) => setF({ ...f, items: f.items.map((it, j) => (j === i ? { ...it, [k]: v } : it)) });
  const sub = f.items.reduce((a, i) => a + Number(i.qty || 0) * Number(i.rate || 0), 0);
  const total = (sub - Number(f.discount || 0)) * (1 + Number(f.tax_pct || 0) / 100);
  const save = async () => {
    const body = { ...f, valid_until: f.valid_until || null, tax_pct: Number(f.tax_pct), discount: Number(f.discount || 0),
      items: f.items.map((i) => ({ ...i, qty: Number(i.qty), rate: Number(i.rate) })) };
    try {
      if (mode === "new") await api.post(`/projects/${project.id}/quotations`, body);
      else if (mode === "edit") await api.put(`/quotations/${quote.id}`, body);
      else await api.post(`/quotations/${quote.id}/revise`, body);
      toast.success(mode === "revise" ? "New revision created (draft)" : "Quotation saved"); onDone();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-3xl">
      <DialogHeader><DialogTitle>{mode === "new" ? "New quotation" : mode === "edit" ? `Edit ${quote.number} R${quote.current_rev}` : `New revision R${quote.current_rev + 1} — ${quote.number}`}</DialogTitle></DialogHeader>
      <div className="space-y-3">
        <div className="space-y-1"><Label>Title</Label><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="e.g. Interiors — Phase 1" data-testid="quote-title-input" /></div>
        <div className="hidden grid-cols-12 gap-2 text-xs font-semibold text-muted-foreground sm:grid"><span className="col-span-5">Description</span><span className="col-span-2">Unit</span><span className="col-span-2">Qty</span><span className="col-span-2">Rate (₹)</span></div>
        <div className="space-y-2">{f.items.map((it, i) => (
          <div key={i} className="grid grid-cols-12 gap-2" data-testid="quote-item-row">
            <Input className="col-span-12 sm:col-span-5" placeholder="Description" value={it.description} onChange={(e) => setItem(i, "description", e.target.value)} data-testid={`quote-item-desc-${i}`} />
            <Input className="col-span-3 sm:col-span-2" placeholder="Unit" value={it.unit} onChange={(e) => setItem(i, "unit", e.target.value)} />
            <Input className="col-span-3 sm:col-span-2" type="number" placeholder="Qty" value={it.qty} onChange={(e) => setItem(i, "qty", e.target.value)} data-testid={`quote-item-qty-${i}`} />
            <Input className="col-span-4 sm:col-span-2" type="number" placeholder="Rate" value={it.rate} onChange={(e) => setItem(i, "rate", e.target.value)} data-testid={`quote-item-rate-${i}`} />
            <Button className="col-span-2 sm:col-span-1" size="icon" variant="ghost" disabled={f.items.length === 1} onClick={() => setF({ ...f, items: f.items.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></Button>
          </div>))}
          <Button variant="outline" size="sm" onClick={() => setF({ ...f, items: [...f.items, { ...blankItem }] })} data-testid="quote-add-item"><Plus className="h-4 w-4" /> Line item</Button></div>
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1"><Label>GST %</Label><Input type="number" value={f.tax_pct} onChange={(e) => setF({ ...f, tax_pct: e.target.value })} data-testid="quote-tax-input" /></div>
          <div className="space-y-1"><Label>Discount (₹)</Label><Input type="number" value={f.discount} onChange={(e) => setF({ ...f, discount: e.target.value })} data-testid="quote-discount-input" /></div>
          <div className="space-y-1"><Label>Valid until</Label><Input type="date" value={f.valid_until} onChange={(e) => setF({ ...f, valid_until: e.target.value })} data-testid="quote-valid-input" /></div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1"><Label>Notes</Label><Textarea rows={3} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} data-testid="quote-notes-input" /></div>
          <div className="space-y-1"><Label>Terms & conditions</Label><Textarea rows={3} value={f.terms} onChange={(e) => setF({ ...f, terms: e.target.value })} data-testid="quote-terms-input" /></div>
        </div>
        <div className="text-right font-mono text-lg font-bold" data-testid="quote-editor-total">Total {formatINR(Math.round(total))}</div>
      </div>
      <DialogFooter><Button onClick={save} disabled={f.title.length < 2 || f.items.some((i) => !i.description || Number(i.qty) <= 0)} data-testid="quote-save-btn">Save draft</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function RespondDialog({ quote, action, onClose, onDone }) {
  const [comment, setComment] = useState("");
  const [sig, setSig] = useState("");
  const [agree, setAgree] = useState(false);
  const accept = action === "accept";
  const go = async () => {
    try { await api.post(`/quotations/${quote.id}/respond`, { action, comment, signature_name: sig }); toast.success(accept ? "Quotation accepted and signed" : "Response sent"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md">
      <DialogHeader><DialogTitle>{accept ? "Accept & e-sign quotation" : action === "reject" ? "Reject quotation" : "Request changes"}</DialogTitle></DialogHeader>
      {accept ? <div className="space-y-3">
        <p className="text-sm text-muted-foreground">You are accepting {quote.number} R{quote.current_rev} for <b>{formatINR(quote.revisions.at(-1).total)}</b>. Type your full name as your electronic signature.</p>
        <Input value={sig} onChange={(e) => setSig(e.target.value)} placeholder="Your full name" data-testid="quote-signature-input" />
        {sig && <div className="rounded-md border bg-muted/40 p-3 text-center font-serif text-2xl italic" data-testid="quote-signature-preview">{sig}</div>}
        <label className="flex items-start gap-2 text-xs"><Checkbox checked={agree} onCheckedChange={(v) => setAgree(!!v)} data-testid="quote-agree-checkbox" />I agree that this typed name is my legally binding signature for this quotation.</label>
        <Textarea rows={2} placeholder="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
      </div> : <Textarea rows={3} placeholder="Tell the team what to change (required)" value={comment} onChange={(e) => setComment(e.target.value)} data-testid="quote-comment-input" />}
      <DialogFooter><Button onClick={go} disabled={accept ? sig.trim().length < 3 || !agree : !comment.trim()} data-testid="quote-respond-confirm">{accept ? "Sign & accept" : "Send"}</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function QuoteCard({ q, manages, isClient, onEdit, onSend, onRespond }) {
  const last = q.revisions.at(-1);
  const [label, cls] = Q_STATUS[q.status] || [q.status, ""];
  const pdf = (rev) => openPath(`/quotations/${q.id}/pdf?rev=${rev}`);
  return (
    <Card className="space-y-3 p-5" data-testid="quote-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><div className="font-mono text-xs text-muted-foreground">{q.number} · R{last?.rev}</div><h3 className="font-heading text-lg font-semibold">{q.title}</h3>
          <Badge className={cls} data-testid="quote-status">{label}</Badge></div>
        <div className="text-right"><div className="font-mono text-2xl font-bold" data-testid="quote-total">{formatINR(last?.total)}</div>
          <div className="text-xs text-muted-foreground">incl. GST {last?.tax_pct}% · valid till {formatDate(last?.valid_until)}</div></div>
      </div>
      {q.client_response && <div className="rounded-md bg-muted/50 p-3 text-sm" data-testid="quote-response">
        {q.client_response.action === "accept" ? <>Signed by <span className="font-serif text-base italic">{q.client_response.signature_name}</span> on {formatDateTime(q.client_response.at)}</>
          : <><b className="capitalize">{q.client_response.action.replace("_", " ")}</b>: {q.client_response.comment}</>}</div>}
      <div className="flex flex-wrap items-center gap-2">
        {q.revisions.map((r) => <Button key={r.rev} size="sm" variant="outline" onClick={() => pdf(r.rev)} data-testid={`quote-pdf-r${r.rev}`}><FileText className="h-4 w-4" /> R{r.rev} PDF</Button>)}
        <span className="flex-1" />
        {manages && q.status === "draft" && <><Button size="sm" variant="ghost" onClick={() => onEdit(q, "edit")} data-testid="quote-edit-btn"><PenLine className="h-4 w-4" /> Edit</Button>
          <Button size="sm" onClick={() => onSend(q)} data-testid="quote-send-btn"><Send className="h-4 w-4" /> Send to client</Button></>}
        {manages && ["sent", "changes_requested", "rejected"].includes(q.status) && <Button size="sm" variant="outline" onClick={() => onEdit(q, "revise")} data-testid="quote-revise-btn">New revision</Button>}
        {isClient && q.status === "sent" && <>
          <Button size="sm" onClick={() => onRespond(q, "accept")} data-testid="quote-accept-btn"><Check className="h-4 w-4" /> Accept & sign</Button>
          <Button size="sm" variant="outline" onClick={() => onRespond(q, "request_changes")} data-testid="quote-changes-btn"><MessageSquare className="h-4 w-4" /> Request changes</Button>
          <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => onRespond(q, "reject")} data-testid="quote-reject-btn"><X className="h-4 w-4" /> Reject</Button></>}
      </div>
    </Card>
  );
}

export function QuotationsTab({ project, user, manages }) {
  const [rows, setRows] = useState([]);
  const [editor, setEditor] = useState(null);
  const [respond, setRespond] = useState(null);
  const load = () => api.get(`/projects/${project.id}/quotations`).then((r) => setRows(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const send = async (q) => { try { await api.post(`/quotations/${q.id}/send`); toast.success("Sent to client"); load(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  const isClient = user.role === "client" && project.client_id === user.id;
  return (
    <div className="space-y-4" data-testid="quotations-tab">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="font-heading text-lg font-semibold">Quotations</h2>
        <p className="text-sm text-muted-foreground">{isClient ? "Review, request changes or accept with your e-signature." : "Branded quotations with numbered revisions."}</p></div>
        {manages && <Button onClick={() => setEditor({ mode: "new" })} data-testid="new-quote-btn"><Plus className="h-4 w-4" /> New quotation</Button>}</div>
      {rows.length === 0 && <Card className="p-8 text-center text-sm text-muted-foreground">No quotations yet.</Card>}
      {rows.map((q) => <QuoteCard key={q.id} q={q} manages={manages} isClient={isClient} onEdit={(x, mode) => setEditor({ quote: x, mode })} onSend={send} onRespond={(x, action) => setRespond({ quote: x, action })} />)}
      {editor && <QuoteEditor project={project} quote={editor.quote} mode={editor.mode} onClose={() => setEditor(null)} onDone={() => { setEditor(null); load(); }} />}
      {respond && <RespondDialog quote={respond.quote} action={respond.action} onClose={() => setRespond(null)} onDone={() => { setRespond(null); load(); }} />}
    </div>
  );
}
