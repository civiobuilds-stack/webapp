import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { isManager, ROLE_LABEL } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Label } from "@/components/ui/label";
import { UserPlus, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

const initials = (n) => (n || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
const TAG = ROLE_LABEL;
const PAGE = 12;

export function TeamTab({ project, role, reload }) {
  const manager = isManager(role);
  const [confirm, setConfirm] = useState(null);
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const jobs = Object.fromEntries((project.team || []).map((t) => [t.user_id, t]));
  const seen = new Set();
  const people = [project.project_manager, project.client, ...(project.engineers || []), ...(project.team || []).map((t) => t.user)]
    .filter((p) => p && !seen.has(p.id) && seen.add(p.id));
  const matched = people.filter((p) => !q || `${p.name} ${p.email} ${TAG[p.role] || ""} ${jobs[p.id]?.job_title || ""}`.toLowerCase().includes(q.toLowerCase()));
  const remove = async () => {
    const p = confirm; setConfirm(null);
    try { await api.delete(`/projects/${project.id}/team/${p.id}`); toast.success(`${p.name} removed from project`); reload(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h3 className="font-heading text-lg font-semibold">Project team</h3><p className="text-sm text-muted-foreground">People with access to this project.</p></div>
        {manager && <AddPeopleDialog project={project} reload={reload} />}
      </div>
      <div className="flex flex-wrap items-center gap-2"><Input className="max-w-xs" placeholder="Search team by name, role or job" value={q} onChange={(e) => { setQ(e.target.value); setLimit(PAGE); }} data-testid="team-search-input" />
        <span className="text-xs text-muted-foreground" data-testid="team-count">{matched.length} of {people.length} people</span></div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {matched.slice(0, limit).map((p) => (
          <Card key={p.id} className="flex items-start gap-3 p-4" data-testid="team-member">
            <Avatar className="h-11 w-11"><AvatarFallback className="bg-primary/10 text-primary">{initials(p.name)}</AvatarFallback></Avatar>
            <div className="min-w-0 flex-1"><div className="truncate font-medium">{p.name}</div><div className="truncate text-xs text-muted-foreground">{p.email}</div>
              {jobs[p.id]?.job_title && <div className="mt-1 text-xs font-medium" data-testid="team-job-title">{jobs[p.id].job_title}</div>}
              {jobs[p.id]?.job_description && <div className="line-clamp-2 text-xs text-muted-foreground">{jobs[p.id].job_description}</div>}</div>
            <div className="flex flex-col items-end gap-1"><Badge variant="secondary" className="shrink-0">{p.id === project.project_manager_id ? "Project Manager" : TAG[p.role]}</Badge>
              {manager && p.id !== project.project_manager_id && <Button size="sm" variant="ghost" className="h-7 text-rose-600" onClick={() => setConfirm(p)} data-testid="team-remove-btn"><Trash2 className="h-3.5 w-3.5" /></Button>}</div>
          </Card>
        ))}
      </div>
      {matched.length > limit && <Button variant="outline" className="w-full" onClick={() => setLimit(limit + PAGE)} data-testid="team-show-more">Show more ({matched.length - limit} remaining)</Button>}
      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}><AlertDialogContent>
        <AlertDialogHeader><AlertDialogTitle>Remove {confirm?.name} from this project?</AlertDialogTitle>
          <AlertDialogDescription>They lose access to this project. Their past updates, photos and audit history are kept.</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="team-remove-confirm">Remove</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent></AlertDialog>
      {manager && <DeleteProject project={project} />}
    </div>
  );
}

function AddPeopleDialog({ project, reload }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [people, setPeople] = useState([]);
  const [f, setF] = useState({ user_id: "", job_title: "", job_description: "" });
  useEffect(() => { if (open) api.get("/users").then((r) => setPeople(r.data.filter((u) => u.is_active !== false && u.role !== "admin" && u.id !== project.project_manager_id && u.id !== project.client_id && !(project.engineer_ids || []).includes(u.id) && !(u.role === "client" && project.client_id)))).catch(() => {}); }, [open]);
  const pick = (id) => { const u = people.find((x) => x.id === id); setF({ user_id: id, job_title: u?.job_title || "", job_description: u?.job_description || "" }); };
  const save = async () => {
    setBusy(true);
    try { await api.post(`/projects/${project.id}/team`, f); toast.success("Added to project"); setOpen(false); setF({ user_id: "", job_title: "", job_description: "" }); reload(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button data-testid="add-people-btn"><UserPlus className="h-4 w-4" /> Add people</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Add people to project</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Person</Label>
            <Select value={f.user_id} onValueChange={pick}><SelectTrigger data-testid="add-people-select"><SelectValue placeholder="Choose from your company" /></SelectTrigger>
              <SelectContent>{["project_manager", "site_engineer", "architect", "structural_engineer", "client"].map((r) => people.filter((u) => u.role === r).map((u) => (
                <SelectItem key={u.id} value={u.id}>{u.name} · {ROLE_LABEL[u.role]}{u.job_title ? ` · ${u.job_title}` : ""}</SelectItem>)))}</SelectContent></Select></div>
          <div className="space-y-1.5"><Label>Job role on this project</Label><Input value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })} placeholder="e.g. Structural engineer" data-testid="add-people-job-title" /></div>
          <div className="space-y-1.5"><Label>Job description</Label><Textarea rows={3} value={f.job_description} onChange={(e) => setF({ ...f, job_description: e.target.value })} data-testid="add-people-job-desc" /></div>
        </div>
        <DialogFooter><Button onClick={save} disabled={busy || !f.user_id} data-testid="add-people-save">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add to project"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteProject({ project }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const del = async () => {
    try { await api.post(`/projects/${project.id}/delete`, { confirm_code: code }); toast.success("Project deleted (records retained)"); navigate("/projects"); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Card className="border-rose-200 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><div className="font-medium text-rose-700">Delete project</div>
        <p className="text-xs text-muted-foreground">Hides the project for everyone. Reports, photos and audit history are retained.</p></div>
        <Button variant="outline" className="border-rose-300 text-rose-700" onClick={() => setOpen(true)} data-testid="delete-project-btn"><Trash2 className="h-4 w-4" /> Delete project</Button></div>
      <Dialog open={open} onOpenChange={setOpen}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>Delete {project.name}?</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">Type the project code <b className="font-mono">{project.code}</b> to confirm.</p>
        <Input value={code} onChange={(e) => setCode(e.target.value)} data-testid="delete-project-code" />
        <DialogFooter><Button className="bg-rose-600 text-white hover:bg-rose-700" disabled={code !== project.code} onClick={del} data-testid="delete-project-confirm">Delete</Button></DialogFooter></DialogContent></Dialog>
    </Card>
  );
}
