import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { PackagePlus, Warehouse, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

function ReceiveDialog({ onClose, onDone }) {
  const [f, setF] = useState({ item: "", kind: "material", quantity: 1, unit: "nos", responsible_person: "", note: "" });
  const set = (k) => (e) => setF({ ...f, [k]: k === "quantity" ? Number(e.target.value) : e.target.value });
  const save = async () => {
    try { await api.post("/store/company/receive", { ...f, photo_ids: [] }); toast.success("Stock added to company store"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md" data-testid="company-receive-dialog"><DialogHeader><DialogTitle>Receive stock into company store</DialogTitle></DialogHeader>
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2 space-y-1.5"><Label>Item</Label><Input value={f.item} onChange={set("item")} data-testid="company-receive-item" /></div>
        <div className="space-y-1.5"><Label>Kind</Label><select className="h-9 w-full rounded-md border bg-transparent px-3 text-sm" value={f.kind} onChange={set("kind")} data-testid="company-receive-kind"><option value="material">material</option><option value="tool">tool</option></select></div>
        <div className="space-y-1.5"><Label>Quantity</Label><Input type="number" value={f.quantity} onChange={set("quantity")} data-testid="company-receive-qty" /></div>
        <div className="space-y-1.5"><Label>Unit</Label><Input value={f.unit} onChange={set("unit")} data-testid="company-receive-unit" /></div>
        <div className="space-y-1.5"><Label>Received from / by</Label><Input value={f.responsible_person} onChange={set("responsible_person")} data-testid="company-receive-person" /></div>
        <div className="col-span-2 space-y-1.5"><Label>Remarks</Label><Input value={f.note} onChange={set("note")} /></div>
      </div>
      <DialogFooter><Button onClick={save} disabled={!f.item || !f.responsible_person || !(f.quantity > 0)} data-testid="company-receive-submit">Add stock</Button></DialogFooter></DialogContent></Dialog>
  );
}

export default function CompanyStore() {
  const [d, setD] = useState(null);
  const [recv, setRecv] = useState(false);
  const load = () => api.get("/store/company").then((r) => setD(r.data)).catch((e) => toast.error(apiError(e.response?.data?.detail)));
  useEffect(() => { load(); }, []);
  if (!d) return null;
  return (
    <div className="space-y-6" data-testid="company-store-page">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="flex items-center gap-2 font-heading text-3xl font-bold"><Warehouse className="h-7 w-7" /> Company Store</h1>
        <p className="text-muted-foreground">One company-wide inventory. Engineer requests → PM approves → Store In-charge issues with camera photos.</p></div>
        {d.can_edit && <Button onClick={() => setRecv(true)} data-testid="company-receive-btn"><PackagePlus className="h-4 w-4" /> Receive stock</Button>}</div>
      {d.shortages.length > 0 && <Card className="space-y-2 border-rose-300 p-4" data-testid="company-shortages"><div className="flex items-center gap-2 font-semibold text-rose-700"><AlertTriangle className="h-4 w-4" /> Shortages needing action</div>
        {d.shortages.map((r) => <div key={r.id} className="text-sm" data-testid="shortage-row"><b>{r.item}</b> · short {r.shortage_qty} {r.unit} of {r.quantity} requested · {r.project_name} · {r.requested_by_name}</div>)}</Card>}
      <Tabs defaultValue="stock"><TabsList><TabsTrigger value="stock" data-testid="company-stock-tab">Inventory</TabsTrigger><TabsTrigger value="pending" data-testid="company-pending-tab">Pending ({d.pending.length})</TabsTrigger><TabsTrigger value="txns" data-testid="company-txn-tab">Transactions</TabsTrigger></TabsList>
        <TabsContent value="stock" className="mt-3"><Card className="divide-y">{d.stock.length === 0 && <p className="p-4 text-sm text-muted-foreground">No stock yet.</p>}
          {d.stock.map((s) => <div key={s.item_key} className="flex flex-wrap justify-between gap-2 p-3 text-sm" data-testid="company-stock-row"><span><b>{s.item}</b> <Badge variant="outline" className="capitalize">{s.kind}</Badge></span>
            <span>Available <b data-testid="company-stock-available">{s.available}</b> {s.unit} · issued out {s.issued_out} · consumed {s.consumed} · damaged {s.damaged} · lost {s.lost}</span></div>)}</Card></TabsContent>
        <TabsContent value="pending" className="mt-3"><Card className="divide-y">{d.pending.length === 0 && <p className="p-4 text-sm text-muted-foreground">Nothing pending.</p>}
          {d.pending.map((r) => <a key={r.id} href={`/projects/${r.project_id}?tab=store`} className="block p-3 text-sm hover:bg-muted/40" data-testid="company-pending-row"><b>{r.item}</b> · {r.quantity} {r.unit} · {r.project_name} · {r.requested_by_name}
            <Badge variant="outline" className="ml-2">{r.pending_return ? "return to verify" : r.status.replace("_", " ")}</Badge></a>)}</Card></TabsContent>
        <TabsContent value="txns" className="mt-3"><Card className="divide-y">{d.transactions.map((t) => <div key={t.id} className="p-3 text-sm" data-testid="company-txn-row">
          <b className="capitalize">{t.type}</b> · {t.quantity} {t.item} · {t.project_name} · {t.responsible_person} · by {t.by_name} · {formatDateTime(t.at)} · {t.photo_ids.length} photo(s)</div>)}</Card></TabsContent>
      </Tabs>
      {recv && <ReceiveDialog onClose={() => setRecv(false)} onDone={() => { setRecv(false); load(); }} />}
    </div>
  );
}
