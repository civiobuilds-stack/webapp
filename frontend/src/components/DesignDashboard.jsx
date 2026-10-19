import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PencilRuler, ArrowRight } from "lucide-react";

export function DesignDashboard() {
  const [d, setD] = useState(null);
  const navigate = useNavigate();
  useEffect(() => { api.get("/dashboard/design").then((r) => setD(r.data)).catch(() => {}); }, []);
  if (!d) return null;
  return (
    <div className="space-y-5" data-testid="design-dashboard">
      <p className="flex items-center gap-2 text-xs text-muted-foreground"><PencilRuler className="h-4 w-4" /> {d.role_label} dashboard · you upload {d.discipline} drawings · approvals go to Owner / PM</p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{d.cards.map((c) => (
        <Card key={c.key} className={`p-4 ${c.alert && c.count ? "border-rose-300 bg-rose-50" : ""}`} data-testid={`design-card-${c.key}`}>
          <div className="text-xs text-muted-foreground">{c.label}</div><div className="font-mono text-2xl font-bold">{c.count}</div></Card>))}</div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="divide-y"><div className="p-4 font-semibold">My projects</div>
          {d.projects.map((p) => <button key={p.id} onClick={() => navigate(`/projects/${p.id}?tab=drawings`)} className="flex w-full items-center justify-between p-4 text-left hover:bg-muted/50" data-testid="design-project-link">
            <span><span className="font-medium">{p.name}</span> <span className="font-mono text-xs text-muted-foreground">{p.code}</span></span>
            <span className="flex items-center gap-2 text-xs text-muted-foreground">{p.drawings} drawings <ArrowRight className="h-4 w-4" /></span></button>)}
          {d.projects.length === 0 && <p className="p-4 text-sm text-muted-foreground">You haven't been added to a project yet.</p>}</Card>
        <Card className="divide-y"><div className="p-4 font-semibold">Recent uploads</div>
          {d.recent.map((x) => <div key={x.id} className="flex items-center justify-between p-4 text-sm" data-testid="design-recent-row">
            <span><span className="font-mono">{x.drawing_no} R{x.rev}</span> · {x.title}<div className="text-xs text-muted-foreground">{formatDateTime(x.created_at)}</div></span>
            <Badge variant="outline" className="capitalize">{x.status}</Badge></div>)}
          {d.recent.length === 0 && <p className="p-4 text-sm text-muted-foreground">No drawings uploaded yet.</p>}</Card>
      </div>
    </div>
  );
}
