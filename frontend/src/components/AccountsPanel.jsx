import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { ROLE_LABEL, formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { KeyRound, Pencil, UserX, UserCheck, Copy } from "lucide-react";
import { toast } from "sonner";

function JobDialog({ u, onClose, onDone }) {
  const [f, setF] = useState({ job_title: u.job_title || "", job_description: u.job_description || "" });
  const save = async () => {
    try { await api.put(`/users/${u.id}/job`, f); toast.success("Job details saved"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md" data-testid="job-dialog"><DialogHeader><DialogTitle>Job role · {u.name}</DialogTitle></DialogHeader>
      <div className="space-y-3"><div className="space-y-1.5"><Label>Job role</Label><Input value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })} data-testid="job-title-input" /></div>
        <div className="space-y-1.5"><Label>Job description</Label><Textarea rows={4} value={f.job_description} onChange={(e) => setF({ ...f, job_description: e.target.value })} data-testid="job-desc-input" /></div></div>
      <DialogFooter><Button onClick={save} data-testid="job-save-btn">Save</Button></DialogFooter></DialogContent></Dialog>
  );
}

function ResetResult({ r, onClose }) {
  const copy = () => { navigator.clipboard?.writeText(`Login ID: ${r.login_id}\nPassword: ${r.temporary_password}`); toast.success("Copied"); };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>New temporary password</DialogTitle></DialogHeader>
      <p className="text-sm text-muted-foreground">Shown only once. Share it securely — it cannot be viewed again.</p>
      <div className="rounded-xl border bg-muted/40 p-4 font-mono text-sm" data-testid="reset-credentials"><div>Login ID: {r.login_id}</div><div>Password: {r.temporary_password}</div></div>
      <DialogFooter><Button variant="outline" onClick={copy} data-testid="reset-copy-btn"><Copy className="h-4 w-4" /> Copy</Button><Button onClick={onClose}>Done</Button></DialogFooter></DialogContent></Dialog>
  );
}

export function AccountsPanel({ users, me, onChanged }) {
  const [job, setJob] = useState(null);
  const [reset, setReset] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const canManage = (u) => u.id !== me.id && (me.role === "admin" || !["admin", "project_manager"].includes(u.role)) && u.platform_role !== "super_admin";
  const doReset = async (u) => { try { const { data } = await api.post(`/users/${u.id}/reset-password`); setReset(data); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  const toggle = async () => {
    const u = confirm; setConfirm(null);
    try { await api.post(`/users/${u.id}/${u.is_active === false ? "reactivate" : "deactivate"}`); toast.success(u.is_active === false ? "Account reactivated" : "Removed from organisation (history kept)"); onChanged(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Card className="overflow-x-auto" data-testid="accounts-panel">
      <div className="p-4"><h2 className="font-heading text-lg font-semibold">Login accounts</h2>
        <p className="text-xs text-muted-foreground">People sign in with these login IDs and the password you set. Passwords are stored encrypted and never shown — use Reset password to issue a new one.</p></div>
      <table className="w-full text-sm"><thead><tr className="border-y bg-muted/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
        <th className="p-3">Name</th><th className="p-3">Login ID</th><th className="p-3">Role / job</th><th className="p-3">Status</th><th className="p-3">Last login</th><th className="p-3 text-right">Actions</th></tr></thead>
        <tbody>{users.map((u) => (
          <tr key={u.id} className="border-b last:border-0" data-testid="account-row">
            <td className="p-3 font-medium">{u.name}<div className="text-xs text-muted-foreground">{u.phone}</div></td>
            <td className="p-3 font-mono text-xs" data-testid="account-login-id">{u.email}</td>
            <td className="p-3"><Badge variant="secondary">{ROLE_LABEL[u.role]}</Badge>{u.job_title && <div className="mt-1 text-xs">{u.job_title}</div>}
              {u.job_description && <div className="line-clamp-2 max-w-xs text-xs text-muted-foreground">{u.job_description}</div>}</td>
            <td className="p-3">{u.is_active === false ? <Badge variant="outline" className="text-rose-600" data-testid="account-status">Removed</Badge> : <Badge className="bg-emerald-600 text-white" data-testid="account-status">Active</Badge>}</td>
            <td className="p-3 text-xs text-muted-foreground">{u.last_login_at ? formatDateTime(u.last_login_at) : "Never"}</td>
            <td className="p-3 text-right">{canManage(u) && <div className="flex justify-end gap-1">
              <Button size="sm" variant="ghost" onClick={() => setJob(u)} title="Edit job" data-testid="account-job-btn"><Pencil className="h-4 w-4" /></Button>
              {u.is_active !== false && <Button size="sm" variant="ghost" onClick={() => doReset(u)} title="Reset password" data-testid="account-reset-btn"><KeyRound className="h-4 w-4" /></Button>}
              <Button size="sm" variant="ghost" className={u.is_active === false ? "" : "text-rose-600"} onClick={() => setConfirm(u)} data-testid="account-toggle-btn">
                {u.is_active === false ? <UserCheck className="h-4 w-4" /> : <UserX className="h-4 w-4" />}</Button></div>}</td>
          </tr>))}</tbody></table>
      {job && <JobDialog u={job} onClose={() => setJob(null)} onDone={() => { setJob(null); onChanged(); }} />}
      {reset && <ResetResult r={reset} onClose={() => setReset(null)} />}
      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}><AlertDialogContent>
        <AlertDialogHeader><AlertDialogTitle>{confirm?.is_active === false ? "Reactivate" : "Remove"} {confirm?.name}?</AlertDialogTitle>
          <AlertDialogDescription>{confirm?.is_active === false ? "They will be able to sign in again." : "They will lose access and be removed from all projects. Their records, photos and audit history are kept."}</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={toggle} data-testid="account-toggle-confirm">Confirm</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent></AlertDialog>
    </Card>
  );
}
