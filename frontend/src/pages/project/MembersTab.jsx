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
import { UserPlus, Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { toast } from "sonner";

const LEVELS = {
  none: { label: "No Access", acts: [] },
  view: { label: "View", acts: ["view"] },
  create: { label: "Create", acts: ["view", "create", "submit"] },
  edit: { label: "Edit", acts: ["view", "create", "submit", "edit"] },
  approve: { label: "Approve", acts: ["view", "create", "submit", "edit", "approve", "export"] },
  delete: { label: "Delete (full)", acts: ["view", "create", "submit", "edit", "approve", "export", "delete"] },
};
const PAGE = 10;
const ENGINEER_DEFAULT = { dpr: ["view", "create", "edit", "submit"], attendance: ["view", "create"], store: ["view", "create"], vehicles: ["view", "create"] };
const levelOf = (acts = []) => {
  const key = Object.keys(LEVELS).find((k) => LEVELS[k].acts.length === acts.length && LEVELS[k].acts.every((a) => acts.includes(a)));
  return key || "custom";
};
const permLabel = (perms) => Object.entries(perms || {}).filter(([, v]) => v.length).map(([k, v]) => {
  const l = levelOf(v); return `${k}: ${l === "custom" ? v.join(", ") : LEVELS[l].label}`;
}).join(" · ");

function PermDialog({ project, meta, member, employees, onClose, onDone }) {
  const [uid, setUid] = useState(member?.user_id || "");
  const [resp, setResp] = useState(member?.responsibility || "");
  const [perms, setPerms] = useState(member?.permissions || { dpr: ["view"], attendance: ["create"] });
  const toggle = (m, a) => {
    const cur = perms[m] || [];
    setPerms({ ...perms, [m]: cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a] });
  };
  const setLevel = (m, l) => setPerms({ ...perms, [m]: [...LEVELS[l].acts] });
  const save = async () => {
    try { await api.put(`/projects/${project.id}/members/${uid}`, { responsibility: resp, permissions: perms }); toast.success("Permissions saved"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl"><DialogHeader><DialogTitle>{member ? "Edit member permissions" : "Assign employee to project"}</DialogTitle></DialogHeader>
        <div className="space-y-4">
          {!member && <div className="space-y-1.5"><Label>Employee</Label>
            <Select value={uid} onValueChange={(v) => { setUid(v); if ((project.engineer_ids || []).includes(v)) setPerms({ ...ENGINEER_DEFAULT }); }}><SelectTrigger data-testid="member-user-select"><SelectValue placeholder="Choose employee" /></SelectTrigger>
              <SelectContent>{employees.map((e) => <SelectItem key={e.id} value={e.id}>{e.name} · {e.designation || ROLE_LABEL[e.role]}</SelectItem>)}</SelectContent></Select></div>}
          <div className="space-y-1.5"><Label>Project responsibility</Label><Input value={resp} onChange={(e) => setResp(e.target.value)} placeholder="e.g. Structural supervisor, Block A" data-testid="member-responsibility-input" /></div>
          <div className="space-y-2">
            {meta.modules.map((m) => {
              const lvl = levelOf(perms[m]);
              return (
                <div key={m} className="rounded-lg border p-3" data-testid={`perm-module-${m}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium capitalize">{m}</span>
                    <Select value={lvl} onValueChange={(l) => l !== "custom" && setLevel(m, l)}>
                      <SelectTrigger className="w-44" data-testid={`perm-level-${m}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{Object.entries(LEVELS).map(([k, v]) => <SelectItem key={k} value={k} data-testid={`perm-level-${m}-${k}`}>{v.label}</SelectItem>)}
                        {lvl === "custom" && <SelectItem value="custom">Custom</SelectItem>}</SelectContent></Select>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">{meta.actions.map((a) => (
                    <label key={a} className="flex items-center gap-1.5 text-xs capitalize"><Checkbox checked={(perms[m] || []).includes(a)} onCheckedChange={() => toggle(m, a)} data-testid={`perm-${m}-${a}`} />{a}</label>))}</div>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-muted-foreground">Pick a level per module (No Access → Delete), or fine-tune with the boxes. Nothing is granted automatically.</p>
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
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const load = () => api.get(`/projects/${project.id}/members`).then((r) => setMembers(r.data)).catch(() => {});
  useEffect(() => { load(); if (meta.manages) api.get("/employees").then((r) => setEmployees(r.data)).catch(() => {}); /* eslint-disable-next-line */ }, [project.id]);
  const remove = async (uid) => { try { await api.delete(`/projects/${project.id}/members/${uid}`); toast.success("Member removed"); load(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  const done = () => { setDlg(null); load(); onChanged?.(); };
  const matched = members.filter((m) => !q || `${m.user?.name} ${m.user?.designation || ""} ${ROLE_LABEL[m.user?.role] || ""} ${m.responsibility}`.toLowerCase().includes(q.toLowerCase()));
  const pages = Math.max(1, Math.ceil(matched.length / PAGE));
  const cur = Math.min(page, pages - 1);
  return (
    <div className="space-y-4" data-testid="members-tab">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-heading text-lg font-semibold">Project members & permissions</h2>
        {meta.manages && <Button onClick={() => setDlg({})} data-testid="add-member-btn"><UserPlus className="h-4 w-4" /> Assign employee</Button>}</div>
      <div className="flex flex-wrap items-center gap-2"><Input className="max-w-xs" placeholder="Search members" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} data-testid="members-search-input" />
        <span className="text-xs text-muted-foreground" data-testid="members-count">{matched.length} members</span></div>
      <Card className="divide-y">
        {matched.length === 0 && <p className="p-4 text-sm text-muted-foreground">No project-specific members yet. Assigned engineers have default DPR and attendance access.</p>}
        {matched.slice(cur * PAGE, cur * PAGE + PAGE).map((m) => (
          <div key={m.user_id} className="flex flex-wrap items-center justify-between gap-2 p-4" data-testid="member-row">
            <div className="min-w-0"><div className="font-medium">{m.user?.name} <span className="text-xs text-muted-foreground">· {m.user?.designation || ROLE_LABEL[m.user?.role]}</span></div>
              <div className="text-xs text-muted-foreground">{m.responsibility || "—"}</div>
              <div className="mt-1 text-xs" data-testid="member-perm-summary">{permLabel(m.permissions) || "No access"}</div></div>
            {meta.manages && <div className="flex gap-1"><Button size="sm" variant="ghost" onClick={() => setDlg(m)} data-testid="edit-member-btn"><Pencil className="h-4 w-4" /></Button>
              <Button size="sm" variant="ghost" onClick={() => remove(m.user_id)} data-testid="remove-member-btn"><Trash2 className="h-4 w-4" /></Button></div>}
          </div>
        ))}
      </Card>
      {pages > 1 && <div className="flex items-center justify-end gap-2 text-sm">
        <Button size="sm" variant="outline" disabled={cur === 0} onClick={() => setPage(cur - 1)} data-testid="members-prev"><ChevronLeft className="h-4 w-4" /></Button>
        <span data-testid="members-page">Page {cur + 1} of {pages}</span>
        <Button size="sm" variant="outline" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)} data-testid="members-next"><ChevronRight className="h-4 w-4" /></Button></div>}
      {dlg && <PermDialog project={project} meta={meta} member={dlg.user_id ? dlg : null}
        employees={employees.filter((e) => e.role !== "admin" && e.id !== project.project_manager_id && !members.some((m) => m.user_id === e.id))} onClose={() => setDlg(null)} onDone={done} />}
    </div>
  );
}
