import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { UserPlus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

function PermDialog({ project, meta, member, employees, onClose, onDone }) {
  const [uid, setUid] = useState(member?.user_id || "");
  const [resp, setResp] = useState(member?.responsibility || "");
  const [perms, setPerms] = useState(member?.permissions || { dpr: ["view"], attendance: ["create"] });
  const toggle = (m, a) => {
    const cur = perms[m] || [];
    setPerms({ ...perms, [m]: cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a] });
  };
  const save = async () => {
    try { await api.put(`/projects/${project.id}/members/${uid}`, { responsibility: resp, permissions: perms }); toast.success("Permissions saved"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl"><DialogHeader><DialogTitle>{member ? "Edit member permissions" : "Assign employee to project"}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          {!member && <div className="space-y-1.5"><Label>Employee</Label>
            <Select value={uid} onValueChange={setUid}><SelectTrigger data-testid="member-user-select"><SelectValue placeholder="Choose employee" /></SelectTrigger>
              <SelectContent>{employees.map((e) => <SelectItem key={e.id} value={e.id}>{e.name} · {e.designation || ROLE_LABEL[e.role]}</SelectItem>)}</SelectContent></Select></div>}
          <div className="space-y-1.5"><Label>Project responsibility</Label><Input value={resp} onChange={(e) => setResp(e.target.value)} placeholder="e.g. Structural supervisor, Block A" data-testid="member-responsibility-input" /></div>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm"><thead><tr className="bg-muted/50"><th className="p-2 text-left">Module</th>{meta.actions.map((a) => <th key={a} className="p-2 capitalize">{a}</th>)}</tr></thead>
              <tbody>{meta.modules.map((m) => (
                <tr key={m} className="border-t"><td className="p-2 font-medium capitalize">{m}</td>
                  {meta.actions.map((a) => <td key={a} className="p-2 text-center"><Checkbox checked={(perms[m] || []).includes(a)} onCheckedChange={() => toggle(m, a)} data-testid={`perm-${m}-${a}`} /></td>)}</tr>
              ))}</tbody></table>
          </div>
          <p className="text-xs text-muted-foreground">Least privilege: only the boxes you tick are granted. Nothing is granted automatically.</p>
        </div>
        <DialogFooter><Button onClick={save} disabled={!uid} data-testid="member-save-btn">Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function MembersTab({ project, meta, onChanged }) {
  const [members, setMembers] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [dlg, setDlg] = useState(null);
  const load = () => api.get(`/projects/${project.id}/members`).then((r) => setMembers(r.data)).catch(() => {});
  useEffect(() => { load(); if (meta.manages) api.get("/employees").then((r) => setEmployees(r.data)).catch(() => {}); /* eslint-disable-next-line */ }, [project.id]);
  const remove = async (uid) => { try { await api.delete(`/projects/${project.id}/members/${uid}`); toast.success("Member removed"); load(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  const done = () => { setDlg(null); load(); onChanged?.(); };
  return (
    <div className="space-y-4" data-testid="members-tab">
      <div className="flex items-center justify-between"><h2 className="font-heading text-lg font-semibold">Project members & permissions</h2>
        {meta.manages && <Button onClick={() => setDlg({})} data-testid="add-member-btn"><UserPlus className="h-4 w-4" /> Assign employee</Button>}</div>
      <Card className="divide-y">
        {members.length === 0 && <p className="p-4 text-sm text-muted-foreground">No project-specific members yet. Assigned engineers have default DPR and attendance access.</p>}
        {members.map((m) => (
          <div key={m.user_id} className="flex flex-wrap items-center justify-between gap-2 p-4" data-testid="member-row">
            <div><div className="font-medium">{m.user?.name} <span className="text-xs text-muted-foreground">· {m.user?.designation || ROLE_LABEL[m.user?.role]}</span></div>
              <div className="text-xs text-muted-foreground">{m.responsibility || "—"}</div>
              <div className="mt-1 text-xs">{Object.entries(m.permissions || {}).map(([k, v]) => `${k}: ${v.join(", ")}`).join(" · ") || "No permissions"}</div></div>
            {meta.manages && <div className="flex gap-1"><Button size="sm" variant="ghost" onClick={() => setDlg(m)} data-testid="edit-member-btn"><Pencil className="h-4 w-4" /></Button>
              <Button size="sm" variant="ghost" onClick={() => remove(m.user_id)} data-testid="remove-member-btn"><Trash2 className="h-4 w-4" /></Button></div>}
          </div>
        ))}
      </Card>
      {dlg && <PermDialog project={project} meta={meta} member={dlg.user_id ? dlg : null} employees={employees} onClose={() => setDlg(null)} onDone={done} />}
    </div>
  );
}
