import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import { CheckCircle2, Circle, Loader } from "lucide-react";
import { cn } from "@/lib/utils";

function phases(activities) {
  const map = {};
  activities.forEach((a) => {
    const p = (map[a.phase || "General"] ||= { name: a.phase || "General", w: 0, done: 0 });
    const w = a.weight || 1;
    p.w += w; p.done += w * (a.progress_percent || 0);
  });
  return Object.values(map).map((p) => ({ name: p.name, pct: Math.round(p.done / p.w) }));
}

function PhaseBar({ p }) {
  const state = p.pct >= 100 ? "done" : p.pct > 0 ? "active" : "todo";
  return (
    <div className="flex items-center gap-3" data-testid="home-phase">
      {state === "done" ? <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" /> : state === "active" ? <Loader className="h-5 w-5 shrink-0 text-[hsl(222_100%_56%)]" /> : <Circle className="h-5 w-5 shrink-0 text-muted-foreground/40" />}
      <div className="flex-1">
        <div className="flex justify-between text-sm"><span className="font-medium">{p.name}</span><span className="text-muted-foreground">{p.pct}%</span></div>
        <div className="mt-1 h-2 rounded-full bg-muted"><div className={cn("h-2 rounded-full transition-[width] duration-700", state === "done" ? "bg-emerald-500" : "bg-[hsl(222_100%_56%)]")} style={{ width: `${p.pct}%` }} /></div>
      </div>
    </div>
  );
}

export function BuildTimeline({ milestones, activities }) {
  return (
    <Card className="p-6" data-testid="home-timeline">
      <h2 className="font-heading text-lg font-bold">Build timeline</h2>
      <p className="text-sm text-muted-foreground">Key milestones for your home.</p>
      <ol className="relative mt-6 space-y-6 border-l-2 border-muted pl-6">
        {milestones.length === 0 && <li className="text-sm text-muted-foreground">Milestones will appear once your builder plans them.</li>}
        {milestones.map((m) => {
          const done = m.status === "completed";
          return (
            <li key={m.id} className="relative" data-testid="home-milestone">
              <span className={cn("absolute -left-[33px] flex h-4 w-4 items-center justify-center rounded-full ring-4 ring-background", done ? "bg-emerald-500" : "bg-muted-foreground/30")} />
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className={cn("font-semibold", done && "text-emerald-700")}>{m.name}</span>
                <span className="text-xs text-muted-foreground">{done ? "Completed" : "Due"} · {formatDate(m.due_date)}</span>
              </div>
            </li>
          );
        })}
      </ol>
      {activities.length > 0 && (
        <div className="mt-8 space-y-4 border-t pt-6">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Construction phases</h3>
          {phases(activities).map((p) => <PhaseBar key={p.name} p={p} />)}
        </div>
      )}
    </Card>
  );
}
