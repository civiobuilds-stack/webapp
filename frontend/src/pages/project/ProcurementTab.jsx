import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { isManager, formatINR, formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Plus, Loader2, Check, X, Lock, Trash2, Package, FileText } from "lucide-react";
import { toast } from "sonner";

const MR_STATUS = {
  requested: "bg-amber-50 text-amber-700 border-amber-300",
  authorized: "bg-emerald-50 text-emerald-700 border-emerald-300",
  rejected: "bg-rose-50 text-rose-700 border-rose-300",
  ordered: "bg-sky-50 text-sky-700 border-sky-300",
};
const PO_STATUS = {
  draft: "bg-slate-100 text-slate-600", approved: "bg-sky-50 text-sky-700",
  ordered: "bg-amber-50 text-amber-700", delivered: "bg-purple-50 text-purple-700",
  accepted: "bg-emerald-50 text-emerald-700", cancelled: "bg-rose-50 text-rose-700",
};
const INV_STATUS = { pending: "bg-amber-50 text-amber-700", paid: "bg-emerald-50 text-emerald-700", overdue: "bg-rose-50 text-rose-700" };

export function ProcurementTab({ project, role }) {
  const manager = isManager(role);
  const [cost, setCost] = useState(null);
  const [noAccess, setNoAccess] = useState(false);

  const loadCost = () => api.get(`/projects/${project.id}/cost-summary`)
    .then((r) => setCost(r.data)).catch((e) => { if (e.response?.status === 403) setNoAccess(true); });
  useEffect(() => { loadCost(); /* eslint-disable-next-line */ }, [project.id]);

  if (noAccess) return <Card className="p-10 text-center text-muted-foreground" data-testid="procurement-no-access">Budget & procurement details are not shared for this project.</Card>;

  return (
    <div className="space-y-5">
      <CostSummary cost={cost} />
      <Tabs defaultValue="requests">
        <TabsList>
          <TabsTrigger value="requests" data-testid="subtab-requests"><Package className="mr-1.5 h-4 w-4" /> Material Requests</TabsTrigger>
          <TabsTrigger value="pos" data-testid="subtab-pos"><FileText className="mr-1.5 h-4 w-4" /> Purchase Orders</TabsTrigger>
        </TabsList>
        <TabsContent value="requests" className="mt-4"><MaterialRequests project={project} role={role} onChange={loadCost} /></TabsContent>
        <TabsContent value="pos" className="mt-4"><PurchaseOrders project={project} manager={manager} onChange={loadCost} /></TabsContent>
      </Tabs>
    </div>
  );
}

function CostSummary({ cost }) {
  if (!cost) return null;
  const cards = [
    { label: "Budget", value: cost.budget, accent: "text-foreground" },
    { label: "Committed", value: cost.committed, accent: "text-sky-700" },
    { label: "Actual (paid)", value: cost.actual, accent: "text-emerald-700" },
    { label: "Forecast", value: cost.forecast, accent: "text-amber-700" },
    { label: "Variance", value: cost.variance, accent: cost.variance < 0 ? "text-rose-700" : "text-emerald-700" },
  ];
  return (
    <div>
      <h3 className="mb-3 font-heading text-lg font-semibold">Cost summary (INR)</h3>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {cards.map((c) => (
          <Card key={c.label} className="p-4" data-testid={`cost-${c.label.split(" ")[0].toLowerCase()}`}>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{c.label}</div>
            <div className={`mt-1 font-mono text-lg font-bold ${c.accent}`}>{formatINR(c.value)}</div>
          </Card>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">Committed = approved/ordered POs. Actual = paid invoices. Figures mix estimates and verified transactions — not a certified accounting statement.</p>
    </div>
  );
}

function MaterialRequests({ project, role, onChange }) {
  const manager = isManager(role);
  const canRaise = manager || role === "site_engineer";
  const [items, setItems] = useState([]);
  const load = () => api.get(`/projects/${project.id}/material-requests`).then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);

  const decide = async (id, action) => {
    try { await api.post(`/material-requests/${id}/decision`, { action, comment: action === "authorize" ? "Approved" : "Not approved" }); toast.success(`Request ${action}d`); load(); onChange(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">{canRaise && <NewRequestDialog projectId={project.id} onDone={() => { load(); onChange(); }} />}</div>
      {items.length === 0 ? <Card className="p-8 text-center text-muted-foreground">No material requests.</Card> : items.map((m) => (
        <Card key={m.id} className="p-4" data-testid="material-request-row">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className={`border ${MR_STATUS[m.status] || ""}`}>{m.status}</Badge>
                <span className="font-medium">{m.item}</span>
              </div>
              <div className="mt-1 text-sm text-muted-foreground">{m.quantity} {m.unit} · needed by {formatDate(m.needed_by)} · by {m.requester?.name}</div>
              {m.notes && <div className="mt-1 text-sm">{m.notes}</div>}
              {m.decision_comment && <div className="mt-1 text-sm text-muted-foreground">PM: {m.decision_comment}</div>}
            </div>
            {manager && m.status === "requested" && (
              <div className="flex gap-2">
                <Button size="sm" onClick={() => decide(m.id, "authorize")} data-testid="authorize-mr-btn"><Check className="h-4 w-4" /> Authorize</Button>
                <Button size="sm" variant="destructive" onClick={() => decide(m.id, "reject")} data-testid="reject-mr-btn"><X className="h-4 w-4" /> Reject</Button>
              </div>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}

function NewRequestDialog({ projectId, onDone }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ item: "", quantity: "", unit: "nos", needed_by: "", notes: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async () => {
    if (!f.item || !f.quantity) { toast.error("Item and quantity are required."); return; }
    setBusy(true);
    try { await api.post(`/projects/${projectId}/material-requests`, { ...f, quantity: Number(f.quantity), needed_by: f.needed_by || null }); toast.success("Request raised"); setOpen(false); onDone(); setF({ item: "", quantity: "", unit: "nos", needed_by: "", notes: "" }); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm" data-testid="new-material-request-btn"><Plus className="h-4 w-4" /> Material request</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Raise material request</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Item / material</Label><Input value={f.item} onChange={set("item")} data-testid="mr-item-input" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Quantity</Label><Input type="number" value={f.quantity} onChange={set("quantity")} data-testid="mr-qty-input" /></div>
            <div className="space-y-1.5"><Label>Unit</Label><Input value={f.unit} onChange={set("unit")} /></div>
          </div>
          <div className="space-y-1.5"><Label>Needed by</Label><Input type="date" value={f.needed_by} onChange={set("needed_by")} /></div>
          <div className="space-y-1.5"><Label>Notes</Label><Textarea value={f.notes} onChange={set("notes")} rows={2} /></div>
        </div>
        <DialogFooter><Button onClick={submit} disabled={busy} data-testid="submit-mr-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Raise request"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PurchaseOrders({ project, manager, onChange }) {
  const [pos, setPos] = useState([]);
  const load = () => api.get(`/projects/${project.id}/purchase-orders`).then((r) => setPos(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);

  const setStatus = async (id, patch) => {
    try { await api.post(`/purchase-orders/${id}/status`, patch); toast.success("PO updated"); load(); onChange(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">{manager && <NewPODialog project={project} onDone={() => { load(); onChange(); }} />}</div>
      {pos.length === 0 ? <Card className="p-8 text-center text-muted-foreground">No purchase orders.</Card> : pos.map((po) => (
        <Card key={po.id} className="p-4" data-testid="po-row">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono text-[11px]">{po.po_number}</Badge>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${PO_STATUS[po.status] || ""}`}>{po.status}</span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${INV_STATUS[po.invoice_status] || ""}`}>invoice: {po.invoice_status}</span>
              </div>
              <div className="mt-1.5 font-medium">{po.supplier?.name || "Supplier"}</div>
              <div className="text-sm text-muted-foreground">{po.items?.map((i) => `${i.quantity} ${i.unit} ${i.description}`).join("; ")}</div>
            </div>
            <div className="text-right"><div className="font-mono text-lg font-bold">{formatINR(po.total_amount)}</div></div>
          </div>
          {manager && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3">
              <Select value={po.status} onValueChange={(v) => setStatus(po.id, { status: v })}>
                <SelectTrigger className="h-8 w-36 text-xs" data-testid="po-status-select"><SelectValue /></SelectTrigger>
                <SelectContent>{["draft", "approved", "ordered", "delivered", "accepted", "cancelled"].map((s) => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}</SelectContent>
              </Select>
              <Select value={po.invoice_status} onValueChange={(v) => setStatus(po.id, { invoice_status: v })}>
                <SelectTrigger className="h-8 w-36 text-xs" data-testid="po-invoice-select"><SelectValue /></SelectTrigger>
                <SelectContent>{["pending", "paid", "overdue"].map((s) => <SelectItem key={s} value={s} className="capitalize">invoice: {s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}

function NewPODialog({ project, onDone }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [suppliers, setSuppliers] = useState([]);
  const [supplierId, setSupplierId] = useState("");
  const [items, setItems] = useState([{ description: "", quantity: "", unit: "nos", rate: "" }]);
  const [notes, setNotes] = useState("");

  useEffect(() => { if (open) api.get("/suppliers").then((r) => setSuppliers(r.data)).catch(() => {}); }, [open]);

  const setItem = (idx, k, v) => setItems((p) => p.map((it, i) => i === idx ? { ...it, [k]: v } : it));
  const addItem = () => setItems((p) => [...p, { description: "", quantity: "", unit: "nos", rate: "" }]);
  const removeItem = (idx) => setItems((p) => p.filter((_, i) => i !== idx));
  const total = items.reduce((s, i) => s + (Number(i.quantity) || 0) * (Number(i.rate) || 0), 0);

  const submit = async () => {
    if (!supplierId) { toast.error("Select a supplier."); return; }
    const payloadItems = items.filter((i) => i.description).map((i) => ({ description: i.description, quantity: Number(i.quantity) || 0, unit: i.unit, rate: Number(i.rate) || 0 }));
    if (!payloadItems.length) { toast.error("Add at least one line item."); return; }
    setBusy(true);
    try { await api.post(`/projects/${project.id}/purchase-orders`, { supplier_id: supplierId, items: payloadItems, notes }); toast.success("Purchase order created"); setOpen(false); onDone(); setItems([{ description: "", quantity: "", unit: "nos", rate: "" }]); setSupplierId(""); setNotes(""); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm" data-testid="new-po-btn"><Plus className="h-4 w-4" /> Purchase order</Button></DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle>Create purchase order</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1.5"><Label>Supplier</Label>
              <Select value={supplierId} onValueChange={setSupplierId}>
                <SelectTrigger data-testid="po-supplier-select"><SelectValue placeholder="Select supplier" /></SelectTrigger>
                <SelectContent>{suppliers.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <AddSupplierDialog onAdded={(s) => { setSuppliers((p) => [...p, s]); setSupplierId(s.id); }} />
          </div>
          <div className="space-y-2">
            <Label>Line items</Label>
            {items.map((it, idx) => (
              <div key={idx} className="grid grid-cols-12 gap-2">
                <Input className="col-span-5" placeholder="Description" value={it.description} onChange={(e) => setItem(idx, "description", e.target.value)} data-testid={`po-item-desc-${idx}`} />
                <Input className="col-span-2" type="number" placeholder="Qty" value={it.quantity} onChange={(e) => setItem(idx, "quantity", e.target.value)} />
                <Input className="col-span-2" placeholder="Unit" value={it.unit} onChange={(e) => setItem(idx, "unit", e.target.value)} />
                <Input className="col-span-2" type="number" placeholder="Rate" value={it.rate} onChange={(e) => setItem(idx, "rate", e.target.value)} />
                <button type="button" className="col-span-1 flex items-center justify-center text-muted-foreground hover:text-rose-600" onClick={() => removeItem(idx)}><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
            <Button type="button" variant="ghost" size="sm" onClick={addItem}><Plus className="h-4 w-4" /> Add line</Button>
          </div>
          <div className="space-y-1.5"><Label>Notes</Label><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} /></div>
          <div className="flex items-center justify-between rounded-lg bg-muted/50 p-3"><span className="text-sm font-medium">Total</span><span className="font-mono text-lg font-bold">{formatINR(total)}</span></div>
        </div>
        <DialogFooter><Button onClick={submit} disabled={busy} data-testid="submit-po-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create PO"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddSupplierDialog({ onAdded }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", contact: "", categories: "" });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!f.name) { toast.error("Name required"); return; }
    setBusy(true);
    try { const { data } = await api.post("/suppliers", f); toast.success("Supplier added"); onAdded(data); setOpen(false); setF({ name: "", contact: "", categories: "" }); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button type="button" variant="outline" size="icon" data-testid="add-supplier-btn"><Plus className="h-4 w-4" /></Button></DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader><DialogTitle>Add supplier</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="supplier-name-input" /></div>
          <div className="space-y-1.5"><Label>Contact</Label><Input value={f.contact} onChange={(e) => setF({ ...f, contact: e.target.value })} /></div>
          <div className="space-y-1.5"><Label>Categories</Label><Input value={f.categories} onChange={(e) => setF({ ...f, categories: e.target.value })} /></div>
        </div>
        <DialogFooter><Button onClick={submit} disabled={busy} data-testid="submit-supplier-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
