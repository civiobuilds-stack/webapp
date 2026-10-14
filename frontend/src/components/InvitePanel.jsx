import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { ROLE_LABEL, formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Mail, Loader2, Copy, X } from "lucide-react";
import { toast } from "sonner";

const STATUS = { pending: "bg-amber-50 text-amber-800 border-amber-300", accepted: "bg-emerald-50 text-emerald-800 border-emerald-300",
  revoked: "bg-slate-100 text-slate-600 border-slate-300", expired: "bg-rose-50 text-rose-700 border-rose-300" };

export function InviteDialog({ isAdmin, onSent }) {
  const empty = { name: "", email: "", phone: "", role: "site_engineer" };
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const submit = async () => {
    setBusy(true);
    try { const r = await api.post("/invites", form); setSent(r.data); onSent(); toast.success(r.data.emailed ? "Invite emailed" : "Invite created — copy the link to share"); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const close = (o) => { setOpen(o); if (!o) { setForm(empty); setSent(null); } };
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogTrigger asChild><Button variant="outline" data-testid="invite-person-btn"><Mail className="h-4 w-4" /> Invite by email</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>{sent ? "Invite sent" : "Invite a team member"}</DialogTitle></DialogHeader>
        {sent ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{sent.emailed ? `We emailed ${sent.email} a link to join.` : "Email delivery failed — share this link manually."} The link expires in 7 days.</p>
            <div className="break-all rounded-lg border bg-muted/40 p-3 font-mono text-xs" data-testid="invite-link">{sent.invite_link}</div>
            <Button variant="outline" className="w-full" onClick={() => { navigator.clipboard?.writeText(sent.invite_link); toast.success("Link copied"); }} data-testid="copy-invite-link-btn"><Copy className="h-4 w-4" /> Copy link</Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5"><Label>Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger data-testid="invite-role-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="site_engineer">Site Engineer</SelectItem>
                  <SelectItem value="client">Client</SelectItem>
                  {isAdmin && <SelectItem value="project_manager">Project Manager</SelectItem>}
                </SelectContent>
              </Select></div>
            <div className="space-y-1.5"><Label>Full name</Label><Input value={form.name} onChange={set("name")} data-testid="invite-form-name" /></div>
            <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={form.email} onChange={set("email")} data-testid="invite-form-email" /></div>
            <div className="space-y-1.5"><Label>Phone (optional)</Label><Input value={form.phone} onChange={set("phone")} data-testid="invite-form-phone" /></div>
          </div>
        )}
        {!sent && <DialogFooter><Button onClick={submit} disabled={busy || !form.name || !form.email} data-testid="send-invite-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Send invite"}</Button></DialogFooter>}
      </DialogContent>
    </Dialog>
  );
}

export function InviteList({ refreshKey }) {
  const [items, setItems] = useState([]);
  const load = () => api.get("/invites").then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); }, [refreshKey]);
  const revoke = async (id) => {
    try { await api.delete(`/invites/${id}`); toast.success("Invite revoked"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  if (!items.length) return null;
  return (
    <div data-testid="invite-list">
      <h2 className="mb-3 font-heading text-lg font-semibold">Invitations</h2>
      <Card className="divide-y">
        {items.map((i) => (
          <div key={i.id} className="flex flex-wrap items-center justify-between gap-3 p-4" data-testid="invite-row">
            <div className="min-w-0"><div className="font-medium">{i.name} <span className="text-xs text-muted-foreground">· {ROLE_LABEL[i.role]}</span></div>
              <div className="truncate text-xs text-muted-foreground">{i.email} · invited {formatDate(i.created_at)} by {i.invited_by_name}</div></div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className={STATUS[i.status]} data-testid="invite-status">{i.status}</Badge>
              {i.status === "pending" && <Button size="sm" variant="ghost" onClick={() => revoke(i.id)} data-testid="revoke-invite-btn"><X className="h-4 w-4" /></Button>}
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
}
