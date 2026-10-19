import { useEffect, useState } from "react";
import { api, apiError, fileUrl } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { CameraCapture } from "@/components/CameraCapture";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, BadgeCheck } from "lucide-react";
import { toast } from "sonner";

const COLOR = { active: "bg-emerald-600", pending: "bg-amber-500", rejected: "bg-rose-600", revoked: "bg-slate-500" };
const today = () => new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);

function NewPass({ pid, onClose, onDone }) {
  const [f, setF] = useState({ pass_type: "labour", person_name: "", phone: "", id_proof: "", trade: "", valid_from: today(), valid_to: today() });
  const [photos, setPhotos] = useState([]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { await api.post(`/projects/${pid}/passes`, { ...f, photo_ids: photos }); toast.success("Site pass created"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md" data-testid="new-pass-dialog"><DialogHeader><DialogTitle>New site pass</DialogTitle></DialogHeader>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label>Type</Label><select className="h-9 w-full rounded-md border bg-transparent px-2 text-sm" value={f.pass_type} onChange={set("pass_type")} data-testid="pass-type-select"><option value="labour">Labour</option><option value="engineer">Engineer</option></select></div>
        <div className="space-y-1.5"><Label>Name</Label><Input value={f.person_name} onChange={set("person_name")} data-testid="pass-name-input" /></div>
        <div className="space-y-1.5"><Label>Phone</Label><Input value={f.phone} onChange={set("phone")} data-testid="pass-phone-input" /></div>
        <div className="space-y-1.5"><Label>ID proof no.</Label><Input value={f.id_proof} onChange={set("id_proof")} data-testid="pass-id-input" /></div>
        <div className="space-y-1.5"><Label>Trade / designation</Label><Input value={f.trade} onChange={set("trade")} data-testid="pass-trade-input" /></div>
        <div />
        <div className="space-y-1.5"><Label>Valid from</Label><Input type="date" value={f.valid_from} onChange={set("valid_from")} data-testid="pass-from-input" /></div>
        <div className="space-y-1.5"><Label>Valid to</Label><Input type="date" value={f.valid_to} onChange={set("valid_to")} data-testid="pass-to-input" /></div>
      </div>
      <CameraCapture projectId={pid} value={photos} onChange={setPhotos} label="Pass holder photo (required)" max={1} />
      <DialogFooter><Button onClick={save} disabled={!f.person_name || !photos.length} data-testid="pass-save-btn">Create pass</Button></DialogFooter></DialogContent></Dialog>
  );
}

export function PassesTab({ project, role, manages }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const load = () => api.get(`/projects/${project.id}/passes`).then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const staff = ["pass_coordinator", "admin", "project_manager"].includes(role);
  const act = async (p, action) => { try { await api.post(`/passes/${p.id}/decision`, { action }); toast.success(`Pass ${action}d`); load(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  return (
    <div className="space-y-4" data-testid="passes-tab">
      <div className="flex items-center justify-between"><div><h3 className="font-heading text-lg font-semibold">Site passes</h3><p className="text-sm text-muted-foreground">Labour and engineer passes. Pass Coordinator creates → PM approves.</p></div>
        {staff && <Button onClick={() => setOpen(true)} data-testid="new-pass-btn"><Plus className="h-4 w-4" /> New pass</Button>}</div>
      {items.length === 0 ? <Card className="p-10 text-center text-muted-foreground">No passes yet.</Card> : <div className="grid gap-3 sm:grid-cols-2">{items.map((p) => (
        <Card key={p.id} className="flex gap-3 p-4" data-testid="pass-card">
          {p.photo_ids?.[0] && <img src={fileUrl(p.photo_ids[0])} alt="" className="h-20 w-16 rounded-md object-cover" />}
          <div className="min-w-0 flex-1"><div className="flex items-center gap-2 font-mono text-xs"><BadgeCheck className="h-4 w-4" /> {p.pass_no}</div>
            <div className="font-medium">{p.person_name} <span className="text-xs capitalize text-muted-foreground">· {p.pass_type}{p.trade ? ` · ${p.trade}` : ""}</span></div>
            <div className="text-xs text-muted-foreground">{p.phone ? `${p.phone} · ` : ""}Valid {formatDate(p.valid_from)} – {formatDate(p.valid_to)}</div>
            <div className="mt-2 flex flex-wrap gap-1"><Badge className={`${COLOR[p.status]} capitalize text-white`} data-testid="pass-status">{p.status}</Badge>
              {manages && p.status === "pending" && <><Button size="sm" className="h-6" onClick={() => act(p, "approve")} data-testid="pass-approve-btn">Approve</Button>
                <Button size="sm" variant="outline" className="h-6" onClick={() => act(p, "reject")} data-testid="pass-reject-btn">Reject</Button></>}
              {staff && p.status === "active" && <Button size="sm" variant="ghost" className="h-6 text-rose-600" onClick={() => act(p, "revoke")} data-testid="pass-revoke-btn">Revoke</Button>}</div></div>
        </Card>))}</div>}
      {open && <NewPass pid={project.id} onClose={() => setOpen(false)} onDone={() => { setOpen(false); load(); }} />}
    </div>
  );
}
