import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { CameraCapture } from "@/components/CameraCapture";
import { Plus, PackageCheck, Undo2, Check, X, PackagePlus } from "lucide-react";
import { toast } from "sonner";

const can = (p, a) => (p?.store || []).includes(a);
const run = async (fn, ok, done) => { try { await fn(); toast.success(ok); done(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };

function FormDialog({ title, fields, photo, projectId, onSubmit, onClose, testid }) {
  const [f, setF] = useState(Object.fromEntries(fields.map(([k, , , d]) => [k, d ?? ""])));
  const [photos, setPhotos] = useState([]);
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md" data-testid={testid}><DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {fields.map(([k, l, type]) => <div key={k} className="space-y-1.5"><Label>{l}</Label>
            <Input type={type || "text"} value={f[k]} onChange={(e) => setF({ ...f, [k]: type === "number" ? Number(e.target.value) : e.target.value })} data-testid={`${testid}-${k}`} /></div>)}
          {photo && <CameraCapture projectId={projectId} value={photos} onChange={setPhotos} label="Transaction photo (required)" />}
        </div>
        <DialogFooter><Button onClick={() => onSubmit({ ...f, ...(photo ? { photo_ids: photos } : {}) })} disabled={photo && !photos.length} data-testid={`${testid}-submit`}>Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RequestRow({ r, perms, setDlg, reload }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm" data-testid="store-request-row">
      <div><b>{r.item}</b> · {r.quantity} {r.unit} <Badge variant="outline" className="ml-1 capitalize">{r.kind}</Badge>
        <div className="text-xs text-muted-foreground">{r.requested_by_name} · need by {formatDate(r.required_date)}{r.kind === "tool" ? ` · return ${formatDate(r.expected_return)}` : ""} · issued {r.issued_qty}{r.kind === "tool" ? ` · returned ${r.returned_qty} · damaged ${r.damaged_qty} · lost ${r.lost_qty}` : ""}</div>
        {r.remarks && <div className="text-xs">{r.remarks}</div>}</div>
      <div className="flex items-center gap-1">
        <Badge variant="outline" data-testid="store-request-status">{r.status.replace("_", " ")}</Badge>
        {can(perms, "approve") && r.status === "requested" && <>
          <Button size="sm" onClick={() => run(() => api.post(`/store/requests/${r.id}/decision`, { action: "approve" }), "Approved", reload)} data-testid="store-approve-btn"><Check className="h-4 w-4" /></Button>
          <Button size="sm" variant="outline" onClick={() => run(() => api.post(`/store/requests/${r.id}/decision`, { action: "reject" }), "Rejected", reload)} data-testid="store-reject-btn"><X className="h-4 w-4" /></Button></>}
        {can(perms, "approve") && ["approved", "partially_issued"].includes(r.status) && <Button size="sm" onClick={() => setDlg({ type: "issue", r })} data-testid="store-issue-btn"><PackageCheck className="h-4 w-4" /> Issue</Button>}
        {can(perms, "approve") && r.kind === "tool" && ["issued", "partially_issued", "partially_returned"].includes(r.status) && <Button size="sm" variant="outline" onClick={() => setDlg({ type: "return", r })} data-testid="store-return-btn"><Undo2 className="h-4 w-4" /> Return</Button>}
      </div>
    </div>
  );
}

export function StoreTab({ project, perms }) {
  const [reqs, setReqs] = useState([]);
  const [stock, setStock] = useState([]);
  const [txns, setTxns] = useState([]);
  const [dlg, setDlg] = useState(null);
  const pid = project.id;
  const load = () => {
    api.get(`/projects/${pid}/store/requests`).then((r) => setReqs(r.data)).catch(() => {});
    api.get(`/projects/${pid}/store/stock`).then((r) => setStock(r.data)).catch(() => {});
    api.get(`/projects/${pid}/store/transactions`).then((r) => setTxns(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [pid]);
  if (!can(perms, "view")) return <Card className="p-8 text-center text-sm text-muted-foreground">You don't have store access on this project.</Card>;
  const close = () => { setDlg(null); load(); };
  return (
    <div className="space-y-4" data-testid="store-tab">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-heading text-lg font-semibold">Store — materials & tools</h2>
        <div className="flex gap-2">
          {can(perms, "create") && <><Button onClick={() => setDlg({ type: "material" })} data-testid="new-material-request-btn"><Plus className="h-4 w-4" /> Material request</Button>
            <Button variant="outline" onClick={() => setDlg({ type: "tool" })} data-testid="new-tool-request-btn"><Plus className="h-4 w-4" /> Tool request</Button></>}
          {can(perms, "approve") && <Button variant="secondary" onClick={() => setDlg({ type: "receive" })} data-testid="receive-stock-btn"><PackagePlus className="h-4 w-4" /> Receive stock</Button>}
        </div></div>
      <Tabs defaultValue="requests">
        <TabsList><TabsTrigger value="requests">Requests</TabsTrigger><TabsTrigger value="stock" data-testid="store-stock-tab">Inventory</TabsTrigger><TabsTrigger value="txns" data-testid="store-txn-tab">Transactions</TabsTrigger></TabsList>
        <TabsContent value="requests" className="mt-3"><Card className="divide-y">{reqs.length === 0 && <p className="p-4 text-sm text-muted-foreground">No requests yet.</p>}
          {reqs.map((r) => <RequestRow key={r.id} r={r} perms={perms} setDlg={setDlg} reload={load} />)}</Card></TabsContent>
        <TabsContent value="stock" className="mt-3"><Card className="divide-y">{stock.length === 0 && <p className="p-4 text-sm text-muted-foreground">No stock recorded.</p>}
          {stock.map((s) => <div key={s.item_key} className="flex flex-wrap justify-between gap-2 p-3 text-sm" data-testid="stock-row"><span><b>{s.item}</b> <Badge variant="outline" className="capitalize">{s.kind}</Badge></span>
            <span>Available <b data-testid="stock-available">{s.available}</b> {s.unit} · issued out {s.issued_out} · consumed {s.consumed} · damaged {s.damaged} · lost {s.lost}</span></div>)}</Card></TabsContent>
        <TabsContent value="txns" className="mt-3"><Card className="divide-y">{txns.map((t) => <div key={t.id} className="p-3 text-sm" data-testid="store-txn-row">
          <b className="capitalize">{t.type}</b> · {t.quantity} {t.item} · to/from {t.responsible_person} · by {t.by_name} · {formatDateTime(t.at)} · {t.photo_ids.length} photo(s)</div>)}</Card></TabsContent>
      </Tabs>
      {(dlg?.type === "material" || dlg?.type === "tool") && <FormDialog testid="store-req" title={`New ${dlg.type} request`} projectId={pid} onClose={() => setDlg(null)}
        fields={[["item", "Item"], ["quantity", "Quantity", "number", 1], ["unit", "Unit", "text", "nos"], ["required_date", "Required date", "date"], ...(dlg.type === "tool" ? [["expected_return", "Expected return date", "date"]] : []), ["remarks", "Remarks"]]}
        onSubmit={(f) => run(() => api.post(`/projects/${pid}/store/requests`, { ...f, kind: dlg.type, required_date: f.required_date || null, expected_return: f.expected_return || null }), "Request raised", close)} />}
      {dlg?.type === "issue" && <FormDialog testid="store-issue" title={`Issue ${dlg.r.item}`} photo projectId={pid} onClose={() => setDlg(null)}
        fields={[["quantity", "Quantity", "number", dlg.r.quantity - dlg.r.issued_qty], ["responsible_person", "Issued to (responsible person)"], ["note", "Note"]]}
        onSubmit={(f) => run(() => api.post(`/store/requests/${dlg.r.id}/issue`, f), "Issued", close)} />}
      {dlg?.type === "return" && <FormDialog testid="store-return" title={`Return ${dlg.r.item}`} photo projectId={pid} onClose={() => setDlg(null)}
        fields={[["good", "Returned in good condition", "number", 0], ["damaged", "Damaged", "number", 0], ["lost", "Lost", "number", 0], ["responsible_person", "Returned by"], ["note", "Note"]]}
        onSubmit={(f) => run(() => api.post(`/store/requests/${dlg.r.id}/return`, f), "Return recorded", close)} />}
      {dlg?.type === "receive" && <FormDialog testid="store-receive" title="Receive stock into project store" photo projectId={pid} onClose={() => setDlg(null)}
        fields={[["item", "Item"], ["kind", "Kind (material/tool)", "text", "material"], ["quantity", "Quantity", "number", 1], ["unit", "Unit", "text", "nos"], ["responsible_person", "Received from / by"], ["note", "Note"]]}
        onSubmit={(f) => run(() => api.post(`/projects/${pid}/store/receive`, f), "Stock received", close)} />}
    </div>
  );
}
