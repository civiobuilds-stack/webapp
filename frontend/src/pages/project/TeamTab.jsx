import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { isManager, ROLE_LABEL } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { UserCog, Loader2, HardHat, Briefcase, User } from "lucide-react";
import { toast } from "sonner";

const initials = (n) => (n || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

export function TeamTab({ project, role, reload }) {
  const manager = isManager(role);
  const people = [
    project.project_manager && { ...project.project_manager, tag: "Project Manager", icon: Briefcase },
    project.client && { ...project.client, tag: "Client", icon: User },
    ...(project.engineers || []).map((e) => ({ ...e, tag: "Site Engineer", icon: HardHat })),
  ].filter(Boolean);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h3 className="font-heading text-lg font-semibold">Project team</h3><p className="text-sm text-muted-foreground">People with access to this project.</p></div>
        {manager && <ManageTeamDialog project={project} reload={reload} />}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {people.map((p) => (
          <Card key={p.id + p.tag} className="flex items-center gap-3 p-4" data-testid="team-member">
            <Avatar className="h-11 w-11"><AvatarFallback className="bg-primary/10 text-primary">{initials(p.name)}</AvatarFallback></Avatar>
            <div className="min-w-0 flex-1"><div className="truncate font-medium">{p.name}</div><div className="truncate text-xs text-muted-foreground">{p.email}</div></div>
            <Badge variant="secondary" className="shrink-0"><p.icon className="mr-1 h-3 w-3" /> {p.tag}</Badge>
          </Card>
        ))}
      </div>
    </div>
  );
}

function ManageTeamDialog({ project, reload }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [clients, setClients] = useState([]);
  const [engineers, setEngineers] = useState([]);
  const [clientId, setClientId] = useState(project.client_id || "");
  const [engIds, setEngIds] = useState(project.engineer_ids || []);

  useEffect(() => {
    if (!open) return;
    api.get("/users?role=client").then((r) => setClients(r.data)).catch(() => {});
    api.get("/users?role=site_engineer").then((r) => setEngineers(r.data)).catch(() => {});
  }, [open]);

  const toggle = (id) => setEngIds((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);

  const save = async () => {
    setBusy(true);
    try { await api.post(`/projects/${project.id}/assign`, { client_id: clientId || null, engineer_ids: engIds }); toast.success("Team updated"); setOpen(false); reload(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="outline" data-testid="manage-team-btn"><UserCog className="h-4 w-4" /> Manage team</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Manage project team</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Client</Label>
            <Select value={clientId} onValueChange={setClientId}>
              <SelectTrigger data-testid="team-client-select"><SelectValue placeholder="Link a client" /></SelectTrigger>
              <SelectContent>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5"><Label>Engineers</Label>
            <div className="flex flex-wrap gap-2">
              {engineers.map((e) => (
                <button key={e.id} type="button" onClick={() => toggle(e.id)} data-testid={`team-eng-${e.id}`}
                  className={`rounded-full border px-3 py-1 text-sm ${engIds.includes(e.id) ? "border-primary bg-primary text-primary-foreground" : "bg-card"}`}>{e.name}</button>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter><Button onClick={save} disabled={busy} data-testid="save-team-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save team"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
