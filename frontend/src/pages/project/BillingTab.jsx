import { useEffect, useState } from "react";
import { api, apiError, fileUrl } from "@/lib/api";
import { formatINR, formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { FileAttach } from "@/components/FileAttach";
import { Plus, Check, X, IndianRupee, Paperclip } from "lucide-react";
import { toast } from "sonner";

export const BILL_STATUS = {
  pending_pm: { label: "Awaiting PM", cls: "bg-amber-50 text-amber-800 border-amber-300" },
  pending_owner: { label: "Awaiting Owner", cls: "bg-sky-50 text-sky-800 border-sky-300" },
  approved: { label: "Approved", cls: "bg-emerald-50 text-emerald-800 border-emerald-300" },
  paid: { label: "Paid", cls: "bg-emerald-600 text-white border-emerald-600" },
  rejected: { label: "Rejected", cls: "bg-rose-50 text-rose-800 border-rose-300" },
};
const EMPTY = { vendor_name: "", bill_no: "", bill_date: new Date().toISOString().slice(0, 10), due_date: "", category: "Material", description: "", amount: "", gst_amount: "", file_ids: [] };

function BillForm({ project, bill, onClose, onDone }) {
  const [f, setF] = useState(bill ? { ...EMPTY, ...bill, due_date: bill.due_date || "" } : EMPTY);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    const body = { ...f, amount: Number(f.amount), gst_amount: Number(f.gst_amount || 0), due_date: f.due_date || null };
    try {
      if (bill) await api.put(`/bills/${bill.id}`, body); else await api.post(`/projects/${project.id}/bills`, body);
      toast.success(bill ? "Bill resubmitted" : "Bill submitted to PM"); onDone();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
      <DialogHeader><DialogTitle>{bill ? `Correct ${bill.ref_no}` : "Submit vendor bill"}</DialogTitle></DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1 sm:col-span-2"><Label>Vendor</Label><Input value={f.vendor_name} onChange={set("vendor_name")} data-testid="bill-vendor-input" /></div>
        <div className="space-y-1"><Label>Bill / invoice no.</Label><Input value={f.bill_no} onChange={set("bill_no")} data-testid="bill-no-input" /></div>
        <div className="space-y-1"><Label>Category</Label><Input value={f.category} onChange={set("category")} data-testid="bill-category-input" /></div>
        <div className="space-y-1"><Label>Bill date</Label><Input type="date" value={f.bill_date} onChange={set("bill_date")} data-testid="bill-date-input" /></div>
        <div className="space-y-1"><Label>Due date</Label><Input type="date" value={f.due_date} onChange={set("due_date")} data-testid="bill-due-input" /></div>
        <div className="space-y-1"><Label>Amount (₹, before GST)</Label><Input type="number" value={f.amount} onChange={set("amount")} data-testid="bill-amount-input" /></div>
        <div className="space-y-1"><Label>GST (₹)</Label><Input type="number" value={f.gst_amount} onChange={set("gst_amount")} data-testid="bill-gst-input" /></div>
        <div className="space-y-1 sm:col-span-2"><Label>Description</Label><Textarea rows={2} value={f.description} onChange={set("description")} data-testid="bill-desc-input" /></div>
        <div className="sm:col-span-2"><FileAttach projectId={project.id} value={f.file_ids} onChange={(ids) => setF({ ...f, file_ids: ids })} testid="bill-attach" /></div>
      </div>
      <p className="text-xs text-muted-foreground">Approval order: Project Manager → Owner. Payment can be recorded only after both approve.</p>
      <DialogFooter><Button onClick={save} disabled={!f.vendor_name || !f.bill_no || !f.amount} data-testid="bill-submit-btn">{bill ? "Resubmit" : "Submit for approval"}</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function ActionDialog({ dlg, onClose, onDone }) {
  const [remarks, setRemarks] = useState("");
  const [paid, setPaid] = useState({ paid_on: new Date().toISOString().slice(0, 10), payment_ref: "" });
  const go = async () => {
    try {
      if (dlg.kind === "paid") await api.post(`/bills/${dlg.bill.id}/paid`, paid);
      else await api.post(`/bills/${dlg.bill.id}/decision`, { action: dlg.kind, remarks });
      toast.success("Updated"); onDone();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md">
      <DialogHeader><DialogTitle className="capitalize">{dlg.kind === "paid" ? "Record payment" : `${dlg.kind} ${dlg.bill.ref_no}`}</DialogTitle></DialogHeader>
      {dlg.kind === "paid" ? <div className="space-y-3">
        <div className="space-y-1"><Label>Paid on</Label><Input type="date" value={paid.paid_on} onChange={(e) => setPaid({ ...paid, paid_on: e.target.value })} data-testid="bill-paid-date" /></div>
        <div className="space-y-1"><Label>Payment reference (UTR / cheque)</Label><Input value={paid.payment_ref} onChange={(e) => setPaid({ ...paid, payment_ref: e.target.value })} data-testid="bill-paid-ref" /></div>
      </div> : <Textarea rows={3} placeholder={dlg.kind === "reject" ? "Reason (required)" : "Remarks (optional)"} value={remarks} onChange={(e) => setRemarks(e.target.value)} data-testid="bill-remarks-input" />}
      <DialogFooter><Button onClick={go} disabled={dlg.kind === "reject" && !remarks.trim()} data-testid="bill-action-confirm">Confirm</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

export function BillRow({ b, user, project, onAction, onEdit, showProject }) {
  const pmTurn = b.status === "pending_pm" && (project?.project_manager_id ? user.id === project.project_manager_id : user.role === "admin");
  const ownerTurn = b.status === "pending_owner" && user.role === "admin";
  const canPay = b.status === "approved" && ["accounts", "admin"].includes(user.role);
  const st = BILL_STATUS[b.status];
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 p-4" data-testid="bill-row">
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-muted-foreground">{b.ref_no}</span>
          <span className="font-medium">{b.vendor_name}</span><Badge variant="outline" className={st.cls} data-testid="bill-status">{st.label}</Badge></div>
        <div className="text-xs text-muted-foreground">{showProject && `${b.project_name} · `}Bill {b.bill_no} · {formatDate(b.bill_date)} · {b.category}{b.due_date ? ` · due ${formatDate(b.due_date)}` : ""}</div>
        {b.description && <div className="text-xs">{b.description}</div>}
        <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">{(b.history || []).map((h, i) => <span key={i}>{h.status.replace("_", " ")} · {h.by}{h.remarks ? ` — ${h.remarks}` : ""}</span>)}</div>
        {b.file_ids?.length > 0 && <div className="flex gap-2">{b.file_ids.map((id, i) => <a key={id} href={fileUrl(id)} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary underline"><Paperclip className="h-3 w-3" />File {i + 1}</a>)}</div>}
      </div>
      <div className="flex flex-col items-end gap-2">
        <div className="font-mono text-lg font-bold" data-testid="bill-total">{formatINR(b.total)}</div>
        <div className="flex flex-wrap justify-end gap-1">
          {(pmTurn || ownerTurn) && <><Button size="sm" onClick={() => onAction({ kind: "approve", bill: b })} data-testid="bill-approve-btn"><Check className="h-4 w-4" />{pmTurn ? "PM approve" : "Owner approve"}</Button>
            <Button size="sm" variant="outline" onClick={() => onAction({ kind: "reject", bill: b })} data-testid="bill-reject-btn"><X className="h-4 w-4" />Reject</Button></>}
          {canPay && <Button size="sm" variant="outline" onClick={() => onAction({ kind: "paid", bill: b })} data-testid="bill-paid-btn"><IndianRupee className="h-4 w-4" />Mark paid</Button>}
          {b.status === "rejected" && onEdit && <Button size="sm" variant="outline" onClick={() => onEdit(b)} data-testid="bill-edit-btn">Correct & resubmit</Button>}
        </div>
      </div>
    </div>
  );
}

export function BillActions({ dlg, setDlg, onDone }) {
  return dlg ? <ActionDialog dlg={dlg} onClose={() => setDlg(null)} onDone={() => { setDlg(null); onDone(); }} /> : null;
}

export function BillingTab({ project, user, perms }) {
  const [bills, setBills] = useState([]);
  const [form, setForm] = useState(null);
  const [dlg, setDlg] = useState(null);
  const can = (a) => (perms?.billing || []).includes(a);
  const load = () => api.get(`/projects/${project.id}/bills`).then((r) => setBills(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const sum = (sts) => bills.filter((b) => sts.includes(b.status)).reduce((a, b) => a + b.total, 0);
  return (
    <div className="space-y-4" data-testid="billing-tab">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="font-heading text-lg font-semibold">Billing</h2>
        <p className="text-sm text-muted-foreground">Vendor bills need Project Manager then Owner approval.</p></div>
        {can("create") && <Button onClick={() => setForm({})} data-testid="new-bill-btn"><Plus className="h-4 w-4" /> New bill</Button>}</div>
      <div className="grid grid-cols-3 gap-3">
        {[["Pending approval", ["pending_pm", "pending_owner"]], ["Approved, unpaid", ["approved"]], ["Paid", ["paid"]]].map(([l, s]) => (
          <Card key={l} className="p-4"><div className="text-xs text-muted-foreground">{l}</div><div className="font-mono text-lg font-bold" data-testid={`bill-sum-${s[0]}`}>{formatINR(sum(s))}</div></Card>))}
      </div>
      <Card className="divide-y">
        {bills.length === 0 && <p className="p-4 text-sm text-muted-foreground">No bills yet.</p>}
        {bills.map((b) => <BillRow key={b.id} b={b} user={user} project={project} onAction={setDlg} onEdit={can("edit") ? (x) => setForm({ bill: x }) : null} />)}
      </Card>
      {form && <BillForm project={project} bill={form.bill} onClose={() => setForm(null)} onDone={() => { setForm(null); load(); }} />}
      <BillActions dlg={dlg} setDlg={setDlg} onDone={load} />
    </div>
  );
}
