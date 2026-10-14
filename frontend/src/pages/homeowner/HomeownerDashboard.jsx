import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fileUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatDate } from "@/lib/format";
import { Home, CalendarDays, ArrowRight } from "lucide-react";
import { BuildTimeline } from "@/pages/homeowner/BuildTimeline";
import { DecisionCards } from "@/pages/homeowner/DecisionCards";
import { TeamContactCard } from "@/pages/homeowner/TeamContactCard";

function ProgressRing({ value }) {
  const r = 52, c = 2 * Math.PI * r, off = c - (Math.min(100, value) / 100) * c;
  return (
    <svg viewBox="0 0 120 120" className="h-32 w-32 -rotate-90" data-testid="home-progress-ring">
      <circle cx="60" cy="60" r={r} strokeWidth="10" className="fill-none stroke-white/15" />
      <circle cx="60" cy="60" r={r} strokeWidth="10" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
        className="fill-none stroke-emerald-400 transition-[stroke-dashoffset] duration-1000" />
    </svg>
  );
}

function HomeHero({ project }) {
  return (
    <Card className="relative overflow-hidden border-0 bg-[hsl(222_60%_11%)] p-6 text-white md:p-8" data-testid="home-hero">
      <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-emerald-300"><Home className="h-4 w-4" /> Your home</p>
          <h1 className="mt-2 font-heading text-3xl font-bold md:text-4xl" data-testid="home-project-name">{project.name}</h1>
          <p className="mt-1 text-sm text-white/60">{project.address}</p>
          <div className="mt-4 flex flex-wrap gap-4 text-sm text-white/80">
            <span className="flex items-center gap-1.5"><CalendarDays className="h-4 w-4" /> Started {formatDate(project.start_date)}</span>
            <span className="flex items-center gap-1.5"><CalendarDays className="h-4 w-4" /> Handover {formatDate(project.planned_completion_date)}</span>
          </div>
        </div>
        <div className="relative flex items-center justify-center">
          <ProgressRing value={project.progress_percent || 0} />
          <div className="absolute text-center"><div className="font-heading text-3xl font-bold" data-testid="home-progress-value">{Math.round(project.progress_percent || 0)}%</div><div className="text-[10px] uppercase tracking-widest text-white/60">built</div></div>
        </div>
      </div>
    </Card>
  );
}

function PhotoStrip({ photos, onOpen }) {
  return (
    <Card className="p-5" data-testid="home-photos">
      <div className="flex items-center justify-between"><h2 className="font-heading text-lg font-bold">Latest site photos</h2>
        <button onClick={onOpen} className="flex items-center gap-1 text-sm font-semibold text-primary" data-testid="home-view-project-btn">Full project <ArrowRight className="h-4 w-4" /></button></div>
      {photos.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">Photos shared by your site team will appear here.</p> : (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {photos.slice(0, 8).map((p) => (
            <a key={p.id} href={fileUrl(p.id)} target="_blank" rel="noreferrer" className="group overflow-hidden rounded-xl">
              <img src={fileUrl(p.id)} alt={p.caption || "Site photo"} className="aspect-square w-full object-cover transition-transform duration-500 group-hover:scale-105" />
            </a>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function HomeownerDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [projects, setProjects] = useState(null);
  const [pid, setPid] = useState(null);
  const [d, setD] = useState(null);

  useEffect(() => { api.get("/projects").then((r) => { setProjects(r.data); setPid(r.data[0]?.id || null); }); }, []);
  const load = () => {
    if (!pid) return;
    Promise.all([
      api.get(`/projects/${pid}`), api.get(`/projects/${pid}/milestones`), api.get(`/projects/${pid}/activities`),
      api.get(`/projects/${pid}/progress-updates`), api.get(`/projects/${pid}/photos`),
    ]).then(([p, m, a, u, ph]) => setD({ project: p.data, milestones: m.data, activities: a.data, updates: u.data, photos: ph.data }));
  };
  useEffect(load, [pid]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!projects || (pid && !d)) return <div className="space-y-4"><Skeleton className="h-48 rounded-2xl" /><Skeleton className="h-72 rounded-2xl" /></div>;
  if (!pid) return (
    <Card className="p-10 text-center" data-testid="home-empty"><Home className="mx-auto h-10 w-10 text-primary" />
      <h1 className="mt-3 font-heading text-2xl font-bold">Welcome, {user.name.split(" ")[0]}</h1>
      <p className="mt-1 text-muted-foreground">Your home project will appear here once your builder links it to your account.</p></Card>
  );
  const pending = d.updates.filter((u) => u.status === "pending_client_decision");
  return (
    <div className="space-y-6" data-testid="homeowner-dashboard">
      {projects.length > 1 && (
        <Select value={pid} onValueChange={(v) => { setD(null); setPid(v); }}>
          <SelectTrigger className="w-72" data-testid="home-project-select"><SelectValue /></SelectTrigger>
          <SelectContent>{projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
        </Select>
      )}
      <HomeHero project={d.project} />
      <DecisionCards updates={pending} onDone={load} />
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <BuildTimeline milestones={d.milestones} activities={d.activities} />
        <TeamContactCard project={d.project} />
      </div>
      <PhotoStrip photos={d.photos} onOpen={() => navigate(`/projects/${pid}`)} />
    </div>
  );
}
