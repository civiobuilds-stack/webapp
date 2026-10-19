import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Car, MapPin } from "lucide-react";
import { toast } from "sonner";

export const TRIP_STATUS = {
  requested: "bg-amber-50 text-amber-800 border-amber-300", assigned: "bg-sky-50 text-sky-800 border-sky-300",
  in_progress: "bg-indigo-50 text-indigo-800 border-indigo-300", completed: "bg-emerald-50 text-emerald-800 border-emerald-300",
  rejected: "bg-rose-50 text-rose-800 border-rose-300", cancelled: "bg-slate-100 text-slate-700 border-slate-300",
};

export function TripCard({ t, actions }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 p-4" data-testid="trip-row">
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{formatDate(t.trip_date)} · {t.trip_time}</span>
          <Badge variant="outline" className={TRIP_STATUS[t.status]} data-testid="trip-status">{t.status.replace("_", " ")}</Badge></div>
        <div className="flex items-center gap-1 text-sm"><MapPin className="h-3.5 w-3.5 text-muted-foreground" />{t.pickup} → {t.drop}</div>
        <div className="text-xs text-muted-foreground">{t.project_name} · {t.purpose} · by {t.requested_by_name}{t.vehicle_type && t.vehicle_type !== "Any" ? ` · wants ${t.vehicle_type}` : ""}</div>
        {t.vehicle && <div className="flex items-center gap-1 text-xs font-medium" data-testid="trip-assignment"><Car className="h-3.5 w-3.5" />{t.vehicle.reg_no} ({t.vehicle.model}) · Driver {t.driver?.name}{t.driver?.phone ? ` · ${t.driver.phone}` : ""}</div>}
      </div>
      <div className="flex flex-wrap gap-1">{actions}</div>
    </div>
  );
}

export async function tripAction(id, action, remarks = "") {
  try { await api.post(`/vehicle-requests/${id}/status`, { action, remarks }); toast.success("Trip updated"); return true; }
  catch (e) { toast.error(apiError(e.response?.data?.detail)); return false; }
}

function RequestDialog({ project, onClose, onDone }) {
  const [f, setF] = useState({ purpose: "", pickup: "", drop: project.address || "", trip_date: new Date().toISOString().slice(0, 10), trip_time: "09:00", vehicle_type: "Any", notes: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { await api.post(`/projects/${project.id}/vehicle-requests`, f); toast.success("Vehicle requested — Accounts will assign a driver"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md">
      <DialogHeader><DialogTitle>Request a company vehicle</DialogTitle></DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1 sm:col-span-2"><Label>Purpose</Label><Input value={f.purpose} onChange={set("purpose")} placeholder="e.g. Material pickup from supplier" data-testid="trip-purpose-input" /></div>
        <div className="space-y-1"><Label>Pickup</Label><Input value={f.pickup} onChange={set("pickup")} data-testid="trip-pickup-input" /></div>
        <div className="space-y-1"><Label>Drop</Label><Input value={f.drop} onChange={set("drop")} data-testid="trip-drop-input" /></div>
        <div className="space-y-1"><Label>Date</Label><Input type="date" value={f.trip_date} onChange={set("trip_date")} data-testid="trip-date-input" /></div>
        <div className="space-y-1"><Label>Time</Label><Input type="time" value={f.trip_time} onChange={set("trip_time")} data-testid="trip-time-input" /></div>
        <div className="space-y-1 sm:col-span-2"><Label>Vehicle type</Label><Input value={f.vehicle_type} onChange={set("vehicle_type")} placeholder="Any / Car / Pickup / Truck" data-testid="trip-type-input" /></div>
        <div className="space-y-1 sm:col-span-2"><Label>Notes</Label><Textarea rows={2} value={f.notes} onChange={set("notes")} data-testid="trip-notes-input" /></div>
      </div>
      <DialogFooter><Button onClick={save} disabled={f.purpose.length < 3 || !f.pickup || !f.drop} data-testid="trip-submit-btn">Request vehicle</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

export function VehiclesTab({ project, user, perms }) {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const load = () => api.get(`/projects/${project.id}/vehicle-requests`).then((r) => setRows(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const cancel = async (id) => { if (await tripAction(id, "cancel")) load(); };
  return (
    <div className="space-y-4" data-testid="vehicles-tab">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="font-heading text-lg font-semibold">Vehicle requests</h2>
        <p className="text-sm text-muted-foreground">Accounts assigns a vehicle and driver; the driver is notified by push.</p></div>
        {(perms?.vehicles || []).includes("create") && <Button onClick={() => setOpen(true)} data-testid="new-trip-btn"><Plus className="h-4 w-4" /> Request vehicle</Button>}</div>
      <Card className="divide-y">
        {rows.length === 0 && <p className="p-4 text-sm text-muted-foreground">No vehicle requests yet.</p>}
        {rows.map((t) => <TripCard key={t.id} t={t} actions={["requested", "assigned"].includes(t.status) && t.requested_by === user.id &&
          <Button size="sm" variant="outline" onClick={() => cancel(t.id)} data-testid="trip-cancel-btn">Cancel</Button>} />)}
      </Card>
      {open && <RequestDialog project={project} onClose={() => setOpen(false)} onDone={() => { setOpen(false); load(); }} />}
    </div>
  );
}
