import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatINR } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { BillRow, BillActions, BILL_STATUS } from "@/pages/project/BillingTab";
import { TripCard, tripAction } from "@/pages/project/VehiclesTab";
import { Plus, Pencil } from "lucide-react";
import { ReasonDialog } from "@/components/ReasonDialog";
import { toast } from "sonner";

function BillsPanel({ user }) {
  const [data, setData] = useState({ bills: [], summary: {} });
  const [status, setStatus] = useState("all");
  const [dlg, setDlg] = useState(null);
  const [projects, setProjects] = useState({});
  const load = () => api.get("/bills", { params: status === "all" ? {} : { status } }).then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [status]);
  useEffect(() => { api.get("/projects").then((r) => setProjects(Object.fromEntries(r.data.map((p) => [p.id, p])))).catch(() => {}); }, []);
  const s = data.summary;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card className="p-4"><div className="text-xs text-muted-foreground">Pending approval</div><div className="font-mono text-lg font-bold" data-testid="acc-sum-pending">{formatINR(s.pending)}</div>
          <div className="text-[11px] text-muted-foreground">{s.count_pending_pm || 0} with PM · {s.count_pending_owner || 0} with Owner</div></Card>
        <Card className="p-4"><div className="text-xs text-muted-foreground">Approved, unpaid</div><div className="font-mono text-lg font-bold" data-testid="acc-sum-approved">{formatINR(s.approved)}</div></Card>
        <Card className="p-4"><div className="text-xs text-muted-foreground">Paid</div><div className="font-mono text-lg font-bold" data-testid="acc-sum-paid">{formatINR(s.paid)}</div></Card>
        <Select value={status} onValueChange={setStatus}><SelectTrigger className="h-auto" data-testid="acc-bill-filter"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="all">All bills</SelectItem>{Object.entries(BILL_STATUS).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}</SelectContent></Select>
      </div>
      <Card className="divide-y">
        {data.bills.length === 0 && <p className="p-4 text-sm text-muted-foreground">No bills. Accounts submits bills from a project's Billing tab.</p>}
        {data.bills.map((b) => <BillRow key={b.id} b={b} user={user} project={projects[b.project_id]} onAction={setDlg} showProject />)}
      </Card>
      <BillActions dlg={dlg} setDlg={setDlg} onDone={load} />
    </div>
  );
}

function VehicleDialog({ v, onClose, onDone }) {
  const [f, setF] = useState(v || { reg_no: "", model: "", vehicle_type: "Car", capacity: "", status: "active" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { if (v) await api.put(`/vehicles/${v.id}`, f); else await api.post("/vehicles", f); toast.success("Vehicle saved"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>{v ? "Edit vehicle" : "Add vehicle"}</DialogTitle></DialogHeader>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1"><Label>Registration no.</Label><Input value={f.reg_no} onChange={set("reg_no")} placeholder="MH12AB1234" data-testid="veh-reg-input" /></div>
        <div className="space-y-1"><Label>Model</Label><Input value={f.model} onChange={set("model")} data-testid="veh-model-input" /></div>
        <div className="space-y-1"><Label>Type</Label><Input value={f.vehicle_type} onChange={set("vehicle_type")} data-testid="veh-type-input" /></div>
        <div className="space-y-1"><Label>Capacity</Label><Input value={f.capacity} onChange={set("capacity")} placeholder="e.g. 7 seats / 2 T" data-testid="veh-cap-input" /></div>
        <div className="space-y-1 sm:col-span-2"><Label>Status</Label>
          <Select value={f.status} onValueChange={(x) => setF({ ...f, status: x })}><SelectTrigger data-testid="veh-status-select"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="maintenance">Under maintenance</SelectItem></SelectContent></Select></div>
      </div>
      <DialogFooter><Button onClick={save} disabled={f.reg_no.length < 3 || !f.model} data-testid="veh-save-btn">Save</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function AssignDialog({ trip, vehicles, drivers, onClose, onDone }) {
  const [f, setF] = useState({ vehicle_id: trip.vehicle?.id || "", driver_id: trip.driver?.id || "", remarks: "" });
  const save = async () => {
    try { await api.post(`/vehicle-requests/${trip.id}/assign`, f); toast.success("Driver assigned and notified"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>Assign vehicle & driver</DialogTitle></DialogHeader>
      <p className="text-sm text-muted-foreground">{trip.trip_date} {trip.trip_time} · {trip.pickup} → {trip.drop}</p>
      <div className="space-y-3">
        <Select value={f.vehicle_id} onValueChange={(x) => setF({ ...f, vehicle_id: x })}><SelectTrigger data-testid="assign-vehicle-select"><SelectValue placeholder="Choose vehicle" /></SelectTrigger>
          <SelectContent>{vehicles.filter((v) => v.status === "active").map((v) => <SelectItem key={v.id} value={v.id}>{v.reg_no} · {v.model} ({v.vehicle_type})</SelectItem>)}</SelectContent></Select>
        <Select value={f.driver_id} onValueChange={(x) => setF({ ...f, driver_id: x })}><SelectTrigger data-testid="assign-driver-select"><SelectValue placeholder="Choose driver" /></SelectTrigger>
          <SelectContent>{drivers.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}{d.phone ? ` · ${d.phone}` : ""}</SelectItem>)}</SelectContent></Select>
        {drivers.length === 0 && <p className="text-xs text-rose-600">No drivers yet. Add a person with the Driver role from People.</p>}
        <Input placeholder="Remarks (optional)" value={f.remarks} onChange={(e) => setF({ ...f, remarks: e.target.value })} data-testid="assign-remarks-input" />
      </div>
      <DialogFooter><Button onClick={save} disabled={!f.vehicle_id || !f.driver_id} data-testid="assign-save-btn">Assign</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function FleetPanel() {
  const [vehicles, setVehicles] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [trips, setTrips] = useState([]);
  const [vdlg, setVdlg] = useState(null);
  const [assign, setAssign] = useState(null);
  const [rejecting, setRejecting] = useState(null);
  const load = () => {
    api.get("/vehicles").then((r) => setVehicles(r.data)).catch(() => {});
    api.get("/drivers").then((r) => setDrivers(r.data)).catch(() => {});
    api.get("/vehicle-requests").then((r) => setTrips(r.data)).catch(() => {});
  };
  useEffect(load, []);
  const reject = (t) => setRejecting(t);
  const doReject = async (r) => { const t = rejecting; setRejecting(null); if (await tripAction(t.id, "reject", r)) load(); };
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-3 lg:col-span-2">
        <h3 className="font-heading font-semibold">Vehicle requests</h3>
        <Card className="divide-y">
          {trips.length === 0 && <p className="p-4 text-sm text-muted-foreground">No requests yet.</p>}
          {trips.map((t) => <TripCard key={t.id} t={t} actions={["requested", "assigned"].includes(t.status) && <>
            <Button size="sm" onClick={() => setAssign(t)} data-testid="trip-assign-btn">{t.status === "assigned" ? "Reassign" : "Assign"}</Button>
            <Button size="sm" variant="outline" onClick={() => reject(t)} data-testid="trip-reject-btn">Reject</Button></>} />)}
        </Card>
      </div>
      <div className="space-y-3">
        <div className="flex items-center justify-between"><h3 className="font-heading font-semibold">Fleet</h3>
          <Button size="sm" onClick={() => setVdlg({})} data-testid="add-vehicle-btn"><Plus className="h-4 w-4" /> Vehicle</Button></div>
        <Card className="divide-y">
          {vehicles.length === 0 && <p className="p-4 text-sm text-muted-foreground">No vehicles yet.</p>}
          {vehicles.map((v) => <div key={v.id} className="flex items-center justify-between p-3" data-testid="vehicle-row">
            <div><div className="font-mono text-sm font-semibold">{v.reg_no}</div><div className="text-xs text-muted-foreground">{v.model} · {v.vehicle_type}{v.capacity ? ` · ${v.capacity}` : ""}</div></div>
            <div className="flex items-center gap-1"><Badge variant={v.status === "active" ? "secondary" : "outline"}>{v.status}</Badge>
              <Button size="icon" variant="ghost" onClick={() => setVdlg({ v })} data-testid="edit-vehicle-btn"><Pencil className="h-4 w-4" /></Button></div></div>)}
        </Card>
        <h3 className="font-heading font-semibold">Drivers</h3>
        <Card className="divide-y">{drivers.length === 0 ? <p className="p-4 text-sm text-muted-foreground">Add drivers from People (role: Driver).</p> :
          drivers.map((d) => <div key={d.id} className="p-3 text-sm" data-testid="driver-row">{d.name} <span className="text-xs text-muted-foreground">{d.phone}</span></div>)}</Card>
      </div>
      {rejecting && <ReasonDialog title="Reject vehicle request" testid="trip-reject" onClose={() => setRejecting(null)} onConfirm={doReject} />}
      {vdlg && <VehicleDialog v={vdlg.v} onClose={() => setVdlg(null)} onDone={() => { setVdlg(null); load(); }} />}
      {assign && <AssignDialog trip={assign} vehicles={vehicles} drivers={drivers} onClose={() => setAssign(null)} onDone={() => { setAssign(null); load(); }} />}
    </div>
  );
}

export default function Accounts() {
  const { user } = useAuth();
  const [sp] = useSearchParams();
  return (
    <div className="space-y-6" data-testid="accounts-page">
      <div><p className="text-xs font-semibold uppercase tracking-widest text-accent">Accounts</p>
        <h1 className="font-heading text-3xl font-bold">Billing & Fleet</h1></div>
      <Tabs defaultValue={sp.get("tab") || "bills"}>
        <TabsList><TabsTrigger value="bills" data-testid="acc-tab-bills">Bills</TabsTrigger><TabsTrigger value="fleet" data-testid="acc-tab-fleet">Vehicles & Drivers</TabsTrigger></TabsList>
        <TabsContent value="bills" className="mt-5"><BillsPanel user={user} /></TabsContent>
        <TabsContent value="fleet" className="mt-5"><FleetPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
