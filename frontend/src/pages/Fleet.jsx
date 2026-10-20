import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ReasonDialog } from "@/components/ReasonDialog";
import { TripCard, tripAction } from "@/pages/project/VehiclesTab";
import { Plus, Pencil, Car, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const EMPTY = { reg_no: "", model: "", vehicle_type: "Car", capacity: "", driver_name: "", driver_phone: "", insurance_expiry: "", permit_expiry: "", status: "active" };
const soon = (d) => d && d <= new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);

export function VehicleDialog({ v, onClose, onDone }) {
  const [f, setF] = useState({ ...EMPTY, ...(v || {}), insurance_expiry: v?.insurance_expiry || "", permit_expiry: v?.permit_expiry || "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    const body = { ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, f[k]])), insurance_expiry: f.insurance_expiry || null, permit_expiry: f.permit_expiry || null };
    try { if (v?.id) await api.put(`/vehicles/${v.id}`, body); else await api.post("/vehicles", body); toast.success("Vehicle saved"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg"><DialogHeader><DialogTitle>{v?.id ? "Edit vehicle" : "Add vehicle to company fleet"}</DialogTitle></DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1"><Label>Registration no.</Label><Input value={f.reg_no} onChange={set("reg_no")} placeholder="MH12AB1234" data-testid="veh-reg-input" /></div>
        <div className="space-y-1"><Label>Make & model</Label><Input value={f.model} onChange={set("model")} data-testid="veh-model-input" /></div>
        <div className="space-y-1"><Label>Type</Label><Input value={f.vehicle_type} onChange={set("vehicle_type")} placeholder="Car / Pickup / Truck" data-testid="veh-type-input" /></div>
        <div className="space-y-1"><Label>Capacity</Label><Input value={f.capacity} onChange={set("capacity")} placeholder="7 seats / 2 T" data-testid="veh-cap-input" /></div>
        <div className="space-y-1"><Label>Driver name</Label><Input value={f.driver_name} onChange={set("driver_name")} data-testid="veh-driver-name" /></div>
        <div className="space-y-1"><Label>Driver phone</Label><Input value={f.driver_phone} onChange={set("driver_phone")} data-testid="veh-driver-phone" /></div>
        <div className="space-y-1"><Label>Insurance expiry</Label><Input type="date" value={f.insurance_expiry} onChange={set("insurance_expiry")} data-testid="veh-insurance" /></div>
        <div className="space-y-1"><Label>Permit expiry</Label><Input type="date" value={f.permit_expiry} onChange={set("permit_expiry")} data-testid="veh-permit" /></div>
        <div className="space-y-1 sm:col-span-2"><Label>Status</Label>
          <Select value={f.status} onValueChange={(x) => setF({ ...f, status: x })}><SelectTrigger data-testid="veh-status-select"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="maintenance">Under maintenance</SelectItem><SelectItem value="inactive">Deactivated</SelectItem></SelectContent></Select></div>
      </div>
      <DialogFooter><Button onClick={save} disabled={f.reg_no.length < 3 || !f.model} data-testid="veh-save-btn">Save</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

export function AssignDialog({ trip, onClose, onDone }) {
  const [vehicles, setVehicles] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [f, setF] = useState({ vehicle_id: "", driver_id: "none", remarks: "" });
  useEffect(() => {
    api.get("/vehicles").then((r) => setVehicles(r.data.filter((v) => v.status === "active"))).catch(() => {});
    api.get("/drivers").then((r) => setDrivers(r.data)).catch(() => {});
  }, []);
  const save = async () => {
    try { await api.post(`/vehicle-requests/${trip.id}/assign`, { ...f, driver_id: f.driver_id === "none" ? null : f.driver_id }); toast.success("Vehicle assigned — everyone notified"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>Assign vehicle & driver</DialogTitle></DialogHeader>
      <p className="text-sm text-muted-foreground">{formatDate(trip.from_date)} → {formatDate(trip.to_date)} · {trip.destination}</p>
      <div className="space-y-3">
        <Select value={f.vehicle_id} onValueChange={(x) => setF({ ...f, vehicle_id: x })}><SelectTrigger data-testid="assign-vehicle-select"><SelectValue placeholder="Choose an available vehicle" /></SelectTrigger>
          <SelectContent>{vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.reg_no} · {v.model} ({v.vehicle_type}){v.driver_name ? ` · ${v.driver_name}` : ""}</SelectItem>)}</SelectContent></Select>
        <Select value={f.driver_id} onValueChange={(x) => setF({ ...f, driver_id: x })}><SelectTrigger data-testid="assign-driver-select"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="none">Vehicle's own driver</SelectItem>{drivers.map((d) => <SelectItem key={d.id} value={d.id}>{d.name} (app user){d.phone ? ` · ${d.phone}` : ""}</SelectItem>)}</SelectContent></Select>
        <Input placeholder="Remarks (optional)" value={f.remarks} onChange={(e) => setF({ ...f, remarks: e.target.value })} data-testid="assign-remarks-input" />
      </div>
      <DialogFooter><Button onClick={save} disabled={!f.vehicle_id} data-testid="assign-save-btn">Assign</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

export function TripActions({ t, user, manages, reload }) {
  const [assign, setAssign] = useState(false);
  const [rej, setRej] = useState(false);
  const decide = async (action, remarks = "") => {
    setRej(false);
    try { await api.post(`/vehicle-requests/${t.id}/decision`, { action, remarks }); toast.success(action === "approve" ? "Approved" : "Rejected"); reload(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const act = async (a) => { if (await tripAction(t.id, a)) reload(); };
  return <>
    {manages && t.status === "requested" && <><Button size="sm" onClick={() => decide("approve")} data-testid="trip-approve-btn">Approve</Button>
      <Button size="sm" variant="outline" onClick={() => setRej(true)} data-testid="trip-reject-btn">Reject</Button></>}
    {manages && ["approved", "assigned"].includes(t.status) && <Button size="sm" onClick={() => setAssign(true)} data-testid="trip-assign-btn">{t.status === "assigned" ? "Reassign" : "Assign vehicle"}</Button>}
    {(manages || t.driver?.id === user.id) && ["assigned", "in_progress"].includes(t.status) && <Button size="sm" variant="outline" onClick={() => act("return")} data-testid="trip-return-btn">Mark returned</Button>}
    {["requested", "approved"].includes(t.status) && t.requested_by === user.id && <Button size="sm" variant="ghost" onClick={() => act("cancel")} data-testid="trip-cancel-btn">Cancel</Button>}
    {assign && <AssignDialog trip={t} onClose={() => setAssign(false)} onDone={() => { setAssign(false); reload(); }} />}
    {rej && <ReasonDialog title="Reject vehicle request" testid="trip-reject" onClose={() => setRej(false)} onConfirm={(r) => decide("reject", r)} />}
  </>;
}

export function FleetStatusCard() {
  const [rows, setRows] = useState(null);
  const navigate = useNavigate();
  useEffect(() => { api.get("/fleet/status").then((r) => setRows(r.data)).catch(() => setRows(null)); }, []);
  if (!rows?.length) return null;
  return (
    <Card className="divide-y" data-testid="fleet-status-card">
      <div className="flex items-center justify-between p-4"><span className="flex items-center gap-2 font-semibold"><Car className="h-4 w-4" /> Vehicles on site</span>
        <Button size="sm" variant="ghost" onClick={() => navigate("/fleet")} data-testid="fleet-open-btn">Open fleet</Button></div>
      {rows.map((v) => <div key={v.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm" data-testid="fleet-status-row">
        <span><span className="font-mono font-semibold">{v.reg_no}</span> <span className="text-xs text-muted-foreground">{v.model}</span></span>
        {v.current ? <span className="text-xs">At <b>{v.current.project_name}</b> · {v.current.destination} · Driver {v.current.driver?.name}{v.current.driver?.phone ? ` (${v.current.driver.phone})` : ""} · till {formatDate(v.current.to_date)}</span>
          : <Badge variant="secondary">{v.status === "active" ? "Available" : v.status}</Badge>}
      </div>)}
    </Card>
  );
}

export default function Fleet({ user }) {
  const [vehicles, setVehicles] = useState([]);
  const [trips, setTrips] = useState([]);
  const [dlg, setDlg] = useState(null);
  const load = () => {
    api.get("/vehicles").then((r) => setVehicles(r.data)).catch(() => {});
    api.get("/vehicle-requests").then((r) => setTrips(r.data)).catch(() => {});
  };
  useEffect(load, []);
  return (
    <div className="space-y-6" data-testid="fleet-page">
      <div className="flex flex-wrap items-end justify-between gap-2"><div><p className="text-xs font-semibold uppercase tracking-widest text-accent">Fleet</p>
        <h1 className="font-heading text-3xl font-bold">Company Vehicles</h1></div>
        <Button onClick={() => setDlg({})} data-testid="add-vehicle-btn"><Plus className="h-4 w-4" /> Add vehicle</Button></div>
      <FleetStatusCard />
      <div className="grid gap-5 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-3"><h2 className="font-heading font-semibold">Vehicle requests</h2>
          <Card className="divide-y">{trips.length === 0 && <p className="p-4 text-sm text-muted-foreground">No requests yet.</p>}
            {trips.map((t) => <TripCard key={t.id} t={t} actions={<TripActions t={t} user={user} manages reload={load} />} />)}</Card></div>
        <div className="space-y-3 lg:col-span-2"><h2 className="font-heading font-semibold">Fleet ({vehicles.length})</h2>
          <Card className="divide-y">{vehicles.length === 0 && <p className="p-4 text-sm text-muted-foreground">No vehicles yet.</p>}
            {vehicles.map((v) => <div key={v.id} className="flex items-start justify-between gap-2 p-3" data-testid="vehicle-row">
              <div className="min-w-0"><div className="font-mono text-sm font-semibold">{v.reg_no}</div>
                <div className="text-xs text-muted-foreground">{v.model} · {v.vehicle_type}{v.capacity ? ` · ${v.capacity}` : ""}{v.driver_name ? ` · ${v.driver_name} ${v.driver_phone || ""}` : ""}</div>
                {(soon(v.insurance_expiry) || soon(v.permit_expiry)) && <div className="flex items-center gap-1 text-xs text-rose-600" data-testid="vehicle-expiry-warning"><AlertTriangle className="h-3 w-3" />
                  {soon(v.insurance_expiry) ? `Insurance ${formatDate(v.insurance_expiry)} ` : ""}{soon(v.permit_expiry) ? `Permit ${formatDate(v.permit_expiry)}` : ""}</div>}</div>
              <div className="flex items-center gap-1"><Badge variant={v.status === "active" ? "secondary" : "outline"}>{v.status}</Badge>
                <Button size="icon" variant="ghost" onClick={() => setDlg({ v })} data-testid="edit-vehicle-btn"><Pencil className="h-4 w-4" /></Button></div></div>)}</Card></div>
      </div>
      {dlg && <VehicleDialog v={dlg.v} onClose={() => setDlg(null)} onDone={() => { setDlg(null); load(); }} />}
    </div>
  );
}
