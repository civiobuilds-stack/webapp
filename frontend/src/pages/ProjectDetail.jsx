import { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { BrandLoader } from "@/components/BrandLoader";
import { DprTab } from "@/pages/project/DprTab";
import { AttendanceTab } from "@/pages/project/AttendanceTab";
import { LabourSection } from "@/pages/project/LabourSection";
import { MembersTab } from "@/pages/project/MembersTab";
import { StoreTab } from "@/pages/project/StoreTab";
import { PassesTab } from "@/pages/project/PassesTab";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatINR, formatDate, isManager } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ArrowLeft, MapPin, Calendar, IndianRupee, Flag } from "lucide-react";
import { ActivitiesTab } from "@/pages/project/ActivitiesTab";
import { ProgressTab } from "@/pages/project/ProgressTab";
import { InspectionTab } from "@/pages/project/InspectionTab";
import { MaterialApprovalsTab } from "@/pages/project/MaterialApprovalsTab";
import { PhotosTab } from "@/pages/project/PhotosTab";
import { TeamTab } from "@/pages/project/TeamTab";
import { AuditTab } from "@/pages/project/AuditTab";
import { ProcurementTab } from "@/pages/project/ProcurementTab";
import { ReportsTab } from "@/pages/project/ReportsTab";
import { BillingTab } from "@/pages/project/BillingTab";
import { VehiclesTab } from "@/pages/project/VehiclesTab";
import { QuotationsTab } from "@/pages/project/QuotationsTab";
import { DrawingsTab } from "@/pages/project/DrawingsTab";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [project, setProject] = useState(null);
  const [milestones, setMilestones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchParams] = useSearchParams();
  const [perm, setPerm] = useState(null);
  const [tab, setTab] = useState(searchParams.get("tab") || "overview");
  useEffect(() => {
    const mods = user.enterprise?.modules || [];
    if (user.role !== "client" || mods.includes("res_dpr"))
      api.get(`/projects/${id}/my-permissions`).then((r) => setPerm(r.data)).catch(() => setPerm(null));
  }, [id, user]);

  const load = () => {
    api.get(`/projects/${id}`).then((r) => setProject(r.data)).catch(() => navigate("/projects")).finally(() => setLoading(false));
    api.get(`/projects/${id}/milestones`).then((r) => setMilestones(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  if (loading) return <BrandLoader fullScreen={false} />;
  if (!project) return null;

  const manager = isManager(user.role);
  const showValue = project.contract_value != null;
  const hasProcurement = (user.enterprise?.modules || []).includes("procurement");
  const commercial = (user.enterprise?.modules || []).includes("dpr") && user.role !== "client";
  const mods = user.enterprise?.modules || [];
  const hasInspection = mods.includes("inspection");
  const resDpr = mods.includes("res_dpr") && perm;
  const hasMaterials = mods.includes("material_approval");
  const hasQuotes = mods.includes("quotations") && (user.role === "client" || user.role === "admin" || (user.role === "project_manager" && (project.project_manager_id === user.id || project.created_by === user.id)));
  const hasDrawings = mods.includes("drawings");
  const manages = user.role === "admin" || (user.role === "project_manager" && (project.project_manager_id === user.id || project.created_by === user.id));
  const can = (m) => perm && (perm.permissions?.[m] || []).includes("view") && mods.includes(m);
  const MOD = { materials: "procurement", drawings: "documents", members: "team", procurement: "procurement", labour: "attendance" };
  const allow = (t) => {
    if (user.role === "client" || perm?.manages || ["audit", "quotations"].includes(t.v)) return true;
    if (!perm) return t.v === "overview";
    const acts = perm.permissions?.[MOD[t.v] || t.v] || [];
    return ["attendance", "labour"].includes(t.v) ? acts.length > 0 : acts.includes("view");
  };
  const tabs = [
    { v: "overview", l: "Overview" }, { v: "activities", l: "Activities" }, { v: "progress", l: "Progress" },
    hasInspection && { v: "inspection", l: "Inspection Checklist" }, resDpr && { v: "dpr", l: "DPR" },
    hasMaterials && { v: "materials", l: "Materials" }, hasQuotes && { v: "quotations", l: "Quotations" }, hasDrawings && { v: "drawings", l: "Drawings" },
    hasProcurement && { v: "procurement", l: "Procurement" }, !commercial && user.role !== "client" && { v: "labour", l: "Labour Attendance" }, { v: "reports", l: "Reports" }, { v: "photos", l: "Photos" }, { v: "team", l: "Team" },
    manager && { v: "audit", l: "Audit Log" },
    ...(commercial && perm ? [{ v: "dpr", l: "DPR" }, { v: "attendance", l: "Attendance" }, { v: "store", l: "Store" },
      { v: "passes", l: "Site Passes" }, can("billing") && { v: "billing", l: "Billing" }, can("vehicles") && { v: "vehicles", l: "Vehicles" }] : []),
  ].filter(Boolean).filter(allow);

  if (user.role === "pass_coordinator") return (
    <div className="space-y-6"><h1 className="font-heading text-2xl font-bold">{project.name} <span className="font-mono text-sm text-muted-foreground">{project.code}</span></h1>
      <PassesTab project={project} role={user.role} manages={false} /></div>
  );
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

      <Tabs value={tab} onValueChange={setTab}>
        <div className="md:hidden" data-testid="project-mobile-menu">
          <Select value={tab} onValueChange={setTab}><SelectTrigger className="h-12 text-base font-semibold" data-testid="project-mobile-menu-select"><SelectValue /></SelectTrigger>
            <SelectContent className="max-h-[70vh]">{tabs.map((t) => <SelectItem key={t.v} value={t.v} data-testid={`mobile-tab-${t.v}`}>{t.l}</SelectItem>)}</SelectContent></Select>
        </div>
        <TabsList className="hidden h-auto w-full flex-wrap justify-start gap-1 md:flex">
          {tabs.map((t) => <TabsTrigger key={t.v} value={t.v} data-testid={`tab-${t.v}`}>{t.l}</TabsTrigger>)}
        </TabsList>

        <TabsContent value="overview" className="mt-5">
          <Overview project={project} milestones={milestones} showValue={showValue} />
        </TabsContent>
        <TabsContent value="activities" className="mt-5"><ActivitiesTab project={project} role={user.role} reload={load} /></TabsContent>
        <TabsContent value="progress" className="mt-5"><ProgressTab project={project} role={user.role} userId={user.id} /></TabsContent>
        {hasInspection && <TabsContent value="inspection" className="mt-5"><InspectionTab project={project} role={user.role} /></TabsContent>}
        {resDpr && <TabsContent value="dpr" className="mt-5"><DprTab project={project} userId={user.id} perms={perm.permissions} manages={perm.manages} initialDpr={searchParams.get("dpr")} /></TabsContent>}
        {hasMaterials && <TabsContent value="materials" className="mt-5"><MaterialApprovalsTab project={project} role={user.role} userId={user.id} /></TabsContent>}
        {hasQuotes && <TabsContent value="quotations" className="mt-5"><QuotationsTab project={project} user={user} manages={manages} /></TabsContent>}
        {hasDrawings && <TabsContent value="drawings" className="mt-5"><DrawingsTab project={project} user={user} manages={manages} /></TabsContent>}
        {hasProcurement && <TabsContent value="procurement" className="mt-5"><ProcurementTab project={project} role={user.role} /></TabsContent>}
        {!commercial && user.role !== "client" && <TabsContent value="labour" className="mt-5"><LabourSection project={project} perms={perm?.permissions} manages={manages} month={new Date().toISOString().slice(0, 7)} /></TabsContent>}
        <TabsContent value="reports" className="mt-5"><ReportsTab project={project} role={user.role} /></TabsContent>
        <TabsContent value="photos" className="mt-5"><PhotosTab project={project} /></TabsContent>
        <TabsContent value="team" className="mt-5"><TeamTab project={project} role={user.role} reload={load} meta={perm} /></TabsContent>
        {manager && <TabsContent value="audit" className="mt-5"><AuditTab project={project} /></TabsContent>}
        {commercial && perm && <>
          <TabsContent value="dpr" className="mt-5"><DprTab project={project} userId={user.id} perms={perm.permissions} manages={perm.manages} initialDpr={searchParams.get("dpr")} /></TabsContent>
          <TabsContent value="attendance" className="mt-5"><AttendanceTab project={project} userId={user.id} perms={perm.permissions} manages={perm.manages} /></TabsContent>
          <TabsContent value="members" className="mt-5"><MembersTab project={project} meta={perm} /></TabsContent>
          <TabsContent value="passes" className="mt-5"><PassesTab project={project} role={user.role} manages={perm.manages} /></TabsContent>
          <TabsContent value="store" className="mt-5"><StoreTab project={project} perms={perm.permissions} meta={perm} /></TabsContent>
          {can("billing") && <TabsContent value="billing" className="mt-5"><BillingTab project={project} user={user} perms={perm.permissions} /></TabsContent>}
          {can("vehicles") && <TabsContent value="vehicles" className="mt-5"><VehiclesTab project={project} user={user} perms={perm.permissions} manages={manages} /></TabsContent>}
        </>}
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
