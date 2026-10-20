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
import { UserPlus, Loader2, Trash2, KeyRound, Search } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { PermDialog } from "@/pages/project/MembersTab";
import { toast } from "sonner";

const initials = (n) => (n || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
const TAG = ROLE_LABEL;
export function TeamTab({ project, role, reload, meta }) {
  const manager = isManager(role) && (!meta || meta.manages);
  const [confirm, setConfirm] = useState(null);
  const [q, setQ] = useState("");
  const [access, setAccess] = useState(null);
  const [members, setMembers] = useState({});
  const loadMembers = () => meta && api.get(`/projects/${project.id}/members`).then((r) => setMembers(Object.fromEntries(r.data.map((m) => [m.user_id, m])))).catch(() => {});
  useEffect(() => { loadMembers(); /* eslint-disable-next-line */ }, [project.id, meta?.manages]);
  const jobs = Object.fromEntries((project.team || []).map((t) => [t.user_id, t]));
  const seen = new Set();
  const people = [project.project_manager, project.client, ...(project.engineers || []), ...(project.team || []).map((t) => t.user), ...Object.values(members).map((m) => m.user)]
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
        <div className="flex gap-2">{manager && <GeofenceButton project={project} reload={reload} />}
          {manager && <AddPeopleDialog project={project} reload={reload} memberIds={Object.keys(members)} />}</div>
      </div>
      <div className="flex flex-wrap items-center gap-2"><Input className="max-w-xs" placeholder="Search team by name, role or job" value={q} onChange={(e) => setQ(e.target.value)} data-testid="team-search-input" />
        <span className="text-xs text-muted-foreground" data-testid="team-count">{matched.length} of {people.length} people</span></div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {matched.map((p) => (
          <Card key={p.id} className="flex items-start gap-3 p-4" data-testid="team-member">
            <Avatar className="h-11 w-11"><AvatarFallback className="bg-primary/10 text-primary">{initials(p.name)}</AvatarFallback></Avatar>
            <div className="min-w-0 flex-1"><div className="truncate font-medium">{p.name}</div><div className="truncate text-xs text-muted-foreground">{p.email}</div>
              {jobs[p.id]?.job_title && <div className="mt-1 text-xs font-medium" data-testid="team-job-title">{jobs[p.id].job_title}</div>}
              {jobs[p.id]?.job_description && <div className="line-clamp-2 text-xs text-muted-foreground">{jobs[p.id].job_description}</div>}</div>
            <div className="flex flex-col items-end gap-1"><Badge variant="secondary" className="shrink-0">{p.id === project.project_manager_id ? "Project Manager" : TAG[p.role]}</Badge>
              <div className="flex gap-1">{manager && meta && p.role !== "client" && p.role !== "admin" && p.id !== project.project_manager_id && <Button size="sm" variant="ghost" className="h-7" onClick={() => setAccess({ user_id: p.id, user: p, ...(members[p.id] || {}) })} data-testid="team-access-btn"><KeyRound className="h-3.5 w-3.5" /> Access</Button>}
              {manager && p.id !== project.project_manager_id && <Button size="sm" variant="ghost" className="h-7 text-rose-600" onClick={() => setConfirm(p)} data-testid="team-remove-btn"><Trash2 className="h-3.5 w-3.5" /></Button>}</div></div>
          </Card>
        ))}
      </div>
      {access && <PermDialog project={project} meta={meta} member={access} onClose={() => setAccess(null)} onDone={() => { setAccess(null); loadMembers(); }} />}
      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}><AlertDialogContent>
        <AlertDialogHeader><AlertDialogTitle>Remove {confirm?.name} from this project?</AlertDialogTitle>
          <AlertDialogDescription>They lose access to this project. Their past updates, photos and audit history are kept.</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="team-remove-confirm">Remove</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent></AlertDialog>
      {manager && <DeleteProject project={project} />}
    </div>
  );
}

function GeofenceButton({ project, reload }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ lat: project.geofence?.lat ?? "", lng: project.geofence?.lng ?? "", radius_m: project.geofence?.radius_m ?? 200 });
  const here = () => navigator.geolocation?.getCurrentPosition((p) => setF({ ...f, lat: p.coords.latitude, lng: p.coords.longitude }), () => toast.error("Allow location access to use your current position."));
  const save = async () => {
    try { await api.put(`/projects/${project.id}/geofence`, { lat: Number(f.lat), lng: Number(f.lng), radius_m: Number(f.radius_m) }); toast.success("Site location saved"); setOpen(false); reload(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="outline" data-testid="geofence-btn">{project.geofence ? "Site location ✓" : "Set site location"}</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>Site location (geofence)</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">Used when a member's attendance requires site location.</p>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1"><Label>Latitude</Label><Input value={f.lat} onChange={(e) => setF({ ...f, lat: e.target.value })} data-testid="geofence-lat" /></div>
          <div className="space-y-1"><Label>Longitude</Label><Input value={f.lng} onChange={(e) => setF({ ...f, lng: e.target.value })} data-testid="geofence-lng" /></div>
          <div className="col-span-2 space-y-1"><Label>Radius (metres, 20–5000)</Label><Input type="number" value={f.radius_m} onChange={(e) => setF({ ...f, radius_m: e.target.value })} data-testid="geofence-radius" /></div>
        </div>
        <DialogFooter><Button variant="outline" onClick={here} data-testid="geofence-here-btn">Use my location</Button>
          <Button onClick={save} disabled={f.lat === "" || f.lng === ""} data-testid="geofence-save-btn">Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddPeopleDialog({ project, reload, memberIds = [] }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [people, setPeople] = useState([]);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState({});
  const [job, setJob] = useState("");
  const onProject = new Set([project.project_manager_id, project.client_id, ...(project.engineer_ids || []), ...(project.team || []).filter((t) => !t.removed_at).map((t) => t.user_id), ...memberIds]);
  useEffect(() => { if (open) { setPicked({}); setQ(""); api.get("/users").then((r) => setPeople(r.data.filter((u) => u.is_active !== false && u.role !== "admin" && !onProject.has(u.id) && !(u.role === "client" && project.client_id)))).catch(() => {}); } /* eslint-disable-next-line */ }, [open]);
  const shown = people.filter((u) => !q || `${u.name} ${u.email} ${ROLE_LABEL[u.role] || ""} ${u.designation || ""}`.toLowerCase().includes(q.toLowerCase()));
  const ids = Object.keys(picked).filter((k) => picked[k]);
  const save = async () => {
    setBusy(true);
    let ok = 0;
    for (const id of ids) {
      const u = people.find((x) => x.id === id);
      try { await api.post(`/projects/${project.id}/team`, { user_id: id, job_title: job || u?.job_title || ROLE_LABEL[u?.role] || "", job_description: u?.job_description || "" }); ok += 1; }
      catch (e) { toast.error(`${u?.name}: ${apiError(e.response?.data?.detail)}`); }
    }
    setBusy(false);
    if (ok) { toast.success(`${ok} ${ok === 1 ? "person" : "people"} added to project`); setOpen(false); setJob(""); reload(); }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button data-testid="add-people-btn"><UserPlus className="h-4 w-4" /> Add people</Button></DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle>Add people to project</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="relative"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input className="pl-8" placeholder="Search everyone in your company" value={q} onChange={(e) => setQ(e.target.value)} data-testid="add-people-search" /></div>
          <div className="max-h-72 divide-y overflow-y-auto rounded-lg border" data-testid="add-people-list">
            {shown.length === 0 && <p className="p-3 text-sm text-muted-foreground">No one else to add.</p>}
            {shown.map((u) => <label key={u.id} className="flex cursor-pointer items-center gap-3 p-2.5 hover:bg-muted/50" data-testid="add-people-option">
              <Checkbox checked={!!picked[u.id]} onCheckedChange={(v) => setPicked({ ...picked, [u.id]: !!v })} data-testid={`add-people-check-${u.id}`} />
              <div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{u.name}</div><div className="truncate text-xs text-muted-foreground">{u.email}</div></div>
              <Badge variant="secondary">{ROLE_LABEL[u.role] || u.role}</Badge></label>)}
          </div>
          <div className="space-y-1.5"><Label>Role label on this project (optional)</Label><Input value={job} onChange={(e) => setJob(e.target.value)} placeholder="Defaults to each person's role" data-testid="add-people-job-title" /></div>
        </div>
        <DialogFooter><Button onClick={save} disabled={busy || !ids.length} data-testid="add-people-save">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : `Add ${ids.length || ""} to project`}</Button></DialogFooter>
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
