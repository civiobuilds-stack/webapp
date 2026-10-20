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
import { VehicleDialog, TripActions } from "@/pages/Fleet";

export const TRIP_STATUS = {
  requested: "bg-amber-50 text-amber-800 border-amber-300", approved: "bg-lime-50 text-lime-800 border-lime-300", assigned: "bg-sky-50 text-sky-800 border-sky-300",
  in_progress: "bg-indigo-50 text-indigo-800 border-indigo-300", returned: "bg-emerald-50 text-emerald-800 border-emerald-300", completed: "bg-emerald-50 text-emerald-800 border-emerald-300",
  rejected: "bg-rose-50 text-rose-800 border-rose-300", cancelled: "bg-slate-100 text-slate-700 border-slate-300",
};

export function TripCard({ t, actions }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 p-4" data-testid="trip-row">
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{formatDate(t.from_date || t.trip_date)}{t.to_date && t.to_date !== t.from_date ? ` → ${formatDate(t.to_date)}` : ""}</span>
          <Badge variant="outline" className={TRIP_STATUS[t.status]} data-testid="trip-status">{t.status.replace("_", " ")}</Badge></div>
        <div className="flex items-center gap-1 text-sm"><MapPin className="h-3.5 w-3.5 text-muted-foreground" />{t.destination || `${t.pickup} → ${t.drop}`}</div>
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
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ purpose: "", destination: "", from_date: today, to_date: today, vehicle_type: "Any", notes: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { await api.post(`/projects/${project.id}/vehicle-requests`, f); toast.success("Vehicle requested — sent to the PM for approval"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md">
      <DialogHeader><DialogTitle>Request a company vehicle</DialogTitle></DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1 sm:col-span-2"><Label>Purpose</Label><Input value={f.purpose} onChange={set("purpose")} placeholder="e.g. Material pickup from supplier" data-testid="trip-purpose-input" /></div>
        <div className="space-y-1 sm:col-span-2"><Label>Destination</Label><Input value={f.destination} onChange={set("destination")} data-testid="trip-destination-input" /></div>
        <div className="space-y-1"><Label>From</Label><Input type="date" value={f.from_date} onChange={set("from_date")} data-testid="trip-from-input" /></div>
        <div className="space-y-1"><Label>To</Label><Input type="date" value={f.to_date} onChange={set("to_date")} data-testid="trip-to-input" /></div>
        <div className="space-y-1 sm:col-span-2"><Label>Vehicle type</Label><Input value={f.vehicle_type} onChange={set("vehicle_type")} placeholder="Any / Car / Pickup / Truck" data-testid="trip-type-input" /></div>
        <div className="space-y-1 sm:col-span-2"><Label>Notes</Label><Textarea rows={2} value={f.notes} onChange={set("notes")} data-testid="trip-notes-input" /></div>
      </div>
      <DialogFooter><Button onClick={save} disabled={f.purpose.length < 3 || !f.destination} data-testid="trip-submit-btn">Request vehicle</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

export function VehiclesTab({ project, user, perms, manages }) {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [addV, setAddV] = useState(false);
  const load = () => api.get(`/projects/${project.id}/vehicle-requests`).then((r) => setRows(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const active = rows.filter((t) => ["assigned", "in_progress"].includes(t.status));
  const open_ = rows.filter((t) => ["requested", "approved"].includes(t.status));
  const past = rows.filter((t) => !["assigned", "in_progress", "requested", "approved"].includes(t.status));
  const list = (items, empty) => <Card className="divide-y">{items.length === 0 && <p className="p-4 text-sm text-muted-foreground">{empty}</p>}
    {items.map((t) => <TripCard key={t.id} t={t} actions={<TripActions t={t} user={user} manages={manages} reload={load} />} />)}</Card>;
  return (
    <div className="space-y-4" data-testid="vehicles-tab">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="font-heading text-lg font-semibold">Vehicles</h2>
        <p className="text-sm text-muted-foreground">Request → PM approves → PM/Owner assigns vehicle & driver → returned.</p></div>
        <div className="flex gap-2">{manages && <Button variant="outline" onClick={() => setAddV(true)} data-testid="project-add-vehicle-btn"><Plus className="h-4 w-4" /> Add to fleet</Button>}
          {(perms?.vehicles || []).includes("create") && <Button onClick={() => setOpen(true)} data-testid="new-trip-btn"><Plus className="h-4 w-4" /> Request vehicle</Button>}</div></div>
      <h3 className="text-sm font-semibold">Requests</h3>{list(open_, "No open requests.")}
      <h3 className="text-sm font-semibold">Vehicles assigned to this project</h3>{list(active, "No vehicles on this project right now.")}
      <h3 className="text-sm font-semibold">Trip history</h3>{list(past, "No past trips.")}
      {open && <RequestDialog project={project} onClose={() => setOpen(false)} onDone={() => { setOpen(false); load(); }} />}
      {addV && <VehicleDialog onClose={() => setAddV(false)} onDone={() => setAddV(false)} />}
    </div>
  );
}
