import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { TripCard, tripAction } from "@/pages/project/VehiclesTab";
import { Play, CheckCircle2 } from "lucide-react";

export default function Trips() {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/my-trips").then((r) => setRows(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const act = async (id, a) => { if (await tripAction(id, a)) load(); };
  const active = rows.filter((t) => ["assigned", "in_progress"].includes(t.status));
  const done = rows.filter((t) => !["assigned", "in_progress"].includes(t.status));
  return (
    <div className="space-y-6" data-testid="trips-page">
      <div><p className="text-xs font-semibold uppercase tracking-widest text-accent">Driver</p><h1 className="font-heading text-3xl font-bold">My trips</h1></div>
      <Card className="divide-y">
        {active.length === 0 && <p className="p-4 text-sm text-muted-foreground">No upcoming trips. You'll get a push notification when one is assigned.</p>}
        {active.map((t) => <TripCard key={t.id} t={t} actions={t.status === "assigned"
          ? <Button size="sm" onClick={() => act(t.id, "start")} data-testid="trip-start-btn"><Play className="h-4 w-4" /> Start trip</Button>
          : <Button size="sm" onClick={() => act(t.id, "complete")} data-testid="trip-complete-btn"><CheckCircle2 className="h-4 w-4" /> Complete</Button>} />)}
      </Card>
      {done.length > 0 && <><h2 className="font-heading font-semibold">History</h2><Card className="divide-y">{done.map((t) => <TripCard key={t.id} t={t} />)}</Card></>}
    </div>
  );
}
