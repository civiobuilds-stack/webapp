import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatINR, formatDate, isManager, ROLE_LABEL } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PlanUsageCard } from "@/components/PlanUsageCard";
import HomeownerDashboard from "@/pages/homeowner/HomeownerDashboard";
import { PendingMaterials } from "@/pages/project/MaterialApprovalsTab";
import {
  FolderKanban, ClipboardCheck, AlertTriangle, Bell, TrendingUp, ArrowRight, HardHat, Building2,
} from "lucide-react";

const ICONS = { projects: FolderKanban, pending_reviews: ClipboardCheck, pending_client_decisions: ClipboardCheck, open_defects: AlertTriangle, unread_notifications: Bell };

export default function DashboardRoute() {
  const { user } = useAuth();
  if (user.role === "client" && user.enterprise?.business_type === "residential") return <HomeownerDashboard />;
  return <Dashboard />;
}

function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.get("/dashboard/summary"), api.get("/projects")])
      .then(([s, p]) => { setSummary(s.data); setProjects(p.data); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const manager = isManager(user.role);
  const stats = manager
    ? [
        { key: "projects", label: "Active Projects", value: summary?.active_projects, icon: Building2 },
        { key: "pending_reviews", label: "Pending Reviews", value: summary?.pending_reviews, icon: ClipboardCheck, accent: summary?.pending_reviews > 0 },
        { key: "open_defects", label: "Failed Inspections", value: summary?.open_defects, icon: AlertTriangle, accent: summary?.open_defects > 0 },
        { key: "avg", label: "Avg. Progress", value: `${summary?.avg_progress ?? 0}%`, icon: TrendingUp },
      ]
    : user.role === "client"
    ? [
        { key: "projects", label: "My Projects", value: summary?.projects, icon: Building2 },
        { key: "pending", label: "Decisions Pending", value: summary?.pending_client_decisions, icon: ClipboardCheck, accent: summary?.pending_client_decisions > 0 },
        { key: "defects", label: "Failed Inspections", value: summary?.open_defects, icon: AlertTriangle },
        { key: "avg", label: "Avg. Progress", value: `${summary?.avg_progress ?? 0}%`, icon: TrendingUp },
      ]
    : [
        { key: "projects", label: "My Sites", value: summary?.projects, icon: HardHat },
        { key: "defects", label: "Failed Inspections", value: summary?.open_defects, icon: AlertTriangle, accent: summary?.open_defects > 0 },
        { key: "notif", label: "Notifications", value: summary?.unread_notifications, icon: Bell, accent: summary?.unread_notifications > 0 },
        { key: "avg", label: "Avg. Progress", value: `${summary?.avg_progress ?? 0}%`, icon: TrendingUp },
      ];

  return (
    <div className="space-y-8">
      <div className="animate-fade-up">
        <p className="text-xs font-semibold uppercase tracking-widest text-accent">{ROLE_LABEL[user.role]} workspace</p>
        <h1 className="mt-1 font-heading text-3xl font-bold md:text-4xl">Hello, {user.name.split(" ")[0]} 👋</h1>
        <p className="mt-1 text-muted-foreground">
          {manager ? "Here's the health of all your construction projects." : user.role === "client" ? "Track your project and respond to pending decisions." : "Your assigned sites and today's actions."}
        </p>
      </div>

      {user.role !== "site_engineer" && <PendingMaterials role={user.role} />}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 rounded-2xl" />)
          : stats.map((s, i) => (
              <Card key={s.key} data-testid={`stat-${s.key}`} className="animate-fade-up border-border/60 p-5" style={{ animationDelay: `${i * 60}ms` }}>
                <div className="flex items-center justify-between">
                  <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${s.accent ? "bg-rose-100 text-rose-600" : "bg-primary/10 text-primary"}`}>
                    <s.icon className="h-5 w-5" />
                  </div>
                  {s.accent && <span className="h-2 w-2 animate-pulse rounded-full bg-rose-500" />}
                </div>
                <div className="mt-4 font-mono text-3xl font-bold tracking-tight">{s.value ?? 0}</div>
                <div className="mt-0.5 text-sm text-muted-foreground">{s.label}</div>
              </Card>
            ))}
      </div>

      {user.role === "admin" && <PlanUsageCard />}

      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-heading text-xl font-semibold">{manager ? "All Projects" : user.role === "client" ? "My Projects" : "My Sites"}</h2>
          <button onClick={() => navigate("/projects")} data-testid="view-all-projects" className="flex items-center gap-1 text-sm font-semibold text-primary hover:underline">
            View all <ArrowRight className="h-4 w-4" />
          </button>
        </div>
        {loading ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-44 rounded-2xl" />)}</div>
        ) : projects.length === 0 ? (
          <Card className="p-10 text-center text-muted-foreground">No projects yet.</Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {projects.slice(0, 6).map((p) => <ProjectMiniCard key={p.id} p={p} onClick={() => navigate(`/projects/${p.id}`)} showValue={manager || p.client_budget_visible} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function ProjectMiniCard({ p, onClick, showValue }) {
  return (
    <Card onClick={onClick} data-testid="project-card-item" className="group cursor-pointer overflow-hidden border-border/60 p-5 transition-all hover:-translate-y-0.5 hover:shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Badge variant="outline" className="mb-2 font-mono text-[11px]">{p.code}</Badge>
          <h3 className="truncate font-heading text-base font-semibold group-hover:text-primary">{p.name}</h3>
          <p className="mt-0.5 truncate text-sm text-muted-foreground">{p.address || p.type}</p>
        </div>
      </div>
      <div className="mt-4">
        <div className="mb-1 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Progress</span>
          <span className="font-mono font-bold">{p.progress_percent ?? 0}%</span>
        </div>
        <Progress value={p.progress_percent ?? 0} className="h-2" />
      </div>
      <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
        <Badge variant="secondary">{p.status}</Badge>
        {showValue && p.contract_value ? <span className="font-mono font-semibold text-foreground">{formatINR(p.contract_value)}</span> : <span>Due {formatDate(p.planned_completion_date)}</span>}
      </div>
    </Card>
  );
}
