import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatINR, formatDate, isManager } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ArrowLeft, MapPin, Calendar, IndianRupee, Flag } from "lucide-react";
import { ActivitiesTab } from "@/pages/project/ActivitiesTab";
import { ProgressTab } from "@/pages/project/ProgressTab";
import { DefectsTab } from "@/pages/project/DefectsTab";
import { PhotosTab } from "@/pages/project/PhotosTab";
import { TeamTab } from "@/pages/project/TeamTab";
import { AuditTab } from "@/pages/project/AuditTab";
import { ProcurementTab } from "@/pages/project/ProcurementTab";
import { ReportsTab } from "@/pages/project/ReportsTab";

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [project, setProject] = useState(null);
  const [milestones, setMilestones] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    api.get(`/projects/${id}`).then((r) => setProject(r.data)).catch(() => navigate("/projects")).finally(() => setLoading(false));
    api.get(`/projects/${id}/milestones`).then((r) => setMilestones(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  if (loading) return <div className="space-y-4"><Skeleton className="h-10 w-48" /><Skeleton className="h-40 rounded-2xl" /><Skeleton className="h-80 rounded-2xl" /></div>;
  if (!project) return null;

  const manager = isManager(user.role);
  const showValue = manager || project.client_budget_visible;

  return (
    <div className="space-y-6">
      <button onClick={() => navigate("/projects")} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" data-testid="back-to-projects"><ArrowLeft className="h-4 w-4" /> Projects</button>

      <Card className="overflow-hidden border-border/60">
        <div className="bg-[hsl(222_60%_11%)] p-6 text-white">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <Badge variant="outline" className="mb-2 border-white/30 font-mono text-white">{project.code}</Badge>
              <h1 className="font-heading text-2xl font-bold md:text-3xl">{project.name}</h1>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-white/70">
                <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4" /> {project.address || "—"}</span>
                <span className="flex items-center gap-1.5"><Calendar className="h-4 w-4" /> Due {formatDate(project.planned_completion_date)}</span>
                {showValue && project.contract_value ? <span className="flex items-center gap-1.5"><IndianRupee className="h-4 w-4" /> {formatINR(project.contract_value)}</span> : null}
              </div>
            </div>
            <div className="text-right">
              <Badge className="bg-[hsl(222_100%_56%)] text-white">{project.status}</Badge>
              <div className="mt-3 font-mono text-3xl font-bold">{project.progress_percent ?? 0}%</div>
              <div className="text-xs text-white/50">Overall (weighted)</div>
            </div>
          </div>
          <div className="mt-4"><Progress value={project.progress_percent ?? 0} className="h-2 bg-white/20" /></div>
        </div>
      </Card>

      <Tabs defaultValue="overview">
        <TabsList className="flex w-full flex-wrap justify-start gap-1 overflow-x-auto">
          <TabsTrigger value="overview" data-testid="tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="activities" data-testid="tab-activities">Activities</TabsTrigger>
          <TabsTrigger value="progress" data-testid="tab-progress">Progress</TabsTrigger>
          <TabsTrigger value="defects" data-testid="tab-defects">Defects</TabsTrigger>
          <TabsTrigger value="procurement" data-testid="tab-procurement">Procurement</TabsTrigger>
          <TabsTrigger value="reports" data-testid="tab-reports">Reports</TabsTrigger>
          <TabsTrigger value="photos" data-testid="tab-photos">Photos</TabsTrigger>
          <TabsTrigger value="team" data-testid="tab-team">Team</TabsTrigger>
          {manager && <TabsTrigger value="audit" data-testid="tab-audit">Audit Log</TabsTrigger>}
        </TabsList>

        <TabsContent value="overview" className="mt-5">
          <Overview project={project} milestones={milestones} showValue={showValue} />
        </TabsContent>
        <TabsContent value="activities" className="mt-5"><ActivitiesTab project={project} role={user.role} reload={load} /></TabsContent>
        <TabsContent value="progress" className="mt-5"><ProgressTab project={project} role={user.role} userId={user.id} /></TabsContent>
        <TabsContent value="defects" className="mt-5"><DefectsTab project={project} role={user.role} /></TabsContent>
        <TabsContent value="procurement" className="mt-5"><ProcurementTab project={project} role={user.role} /></TabsContent>
        <TabsContent value="reports" className="mt-5"><ReportsTab project={project} role={user.role} /></TabsContent>
        <TabsContent value="photos" className="mt-5"><PhotosTab project={project} /></TabsContent>
        <TabsContent value="team" className="mt-5"><TeamTab project={project} role={user.role} reload={load} /></TabsContent>
        {manager && <TabsContent value="audit" className="mt-5"><AuditTab project={project} /></TabsContent>}
      </Tabs>
    </div>
  );
}

function Overview({ project, milestones, showValue }) {
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Card className="p-6 lg:col-span-2">
        <h3 className="font-heading text-lg font-semibold">About this project</h3>
        <p className="mt-2 text-sm text-muted-foreground">{project.description || "No description provided."}</p>
        <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Info label="Type" value={project.type} />
          <Info label="Status" value={project.status} />
          <Info label="Start" value={formatDate(project.start_date)} />
          <Info label="Completion" value={formatDate(project.planned_completion_date)} />
          {showValue && <Info label="Contract value" value={formatINR(project.contract_value)} mono />}
          <Info label="Client" value={project.client?.name || "Not linked"} />
        </div>
      </Card>
      <Card className="p-6">
        <h3 className="flex items-center gap-2 font-heading text-lg font-semibold"><Flag className="h-4 w-4 text-accent" /> Milestones</h3>
        <div className="mt-4 space-y-4">
          {milestones.length === 0 ? <p className="text-sm text-muted-foreground">No milestones yet.</p> : milestones.map((m, i) => (
            <div key={m.id} className="relative flex gap-3 pb-1" data-testid="milestone-item">
              <div className="flex flex-col items-center">
                <span className={`h-3 w-3 rounded-full ${m.status === "completed" ? "bg-emerald-500" : "bg-muted-foreground/40"}`} />
                {i < milestones.length - 1 && <span className="mt-1 h-full w-px flex-1 bg-border" />}
              </div>
              <div className="-mt-1 pb-3">
                <div className="text-sm font-medium">{m.name}</div>
                <div className="text-xs text-muted-foreground">{formatDate(m.due_date)} · {m.status}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Info({ label, value, mono }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-sm font-medium ${mono ? "font-mono" : ""}`}>{value || "—"}</div>
    </div>
  );
}
