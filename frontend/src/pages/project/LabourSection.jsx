import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { CameraCapture } from "@/components/CameraCapture";
import { AuthImage } from "@/components/AuthImage";
import { MapPin, LogIn, LogOut } from "lucide-react";
import { toast } from "sonner";

const gps = () => new Promise((res, rej) => navigator.geolocation
  ? navigator.geolocation.getCurrentPosition((p) => res({ lat: p.coords.latitude, lng: p.coords.longitude }), () => rej(new Error("Location permission is required for site attendance.")), { enableHighAccuracy: true, timeout: 15000 })
  : rej(new Error("GPS is not available on this device.")));

function PunchDialog({ project, row, onClose, onDone }) {
  const [f, setF] = useState({ labour_incharge: row?.labour_incharge || "", masons: row?.masons ?? 0, helpers: row?.helpers ?? 0 });
  const [photos, setPhotos] = useState([]);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const loc = await gps();
      const body = { ...f, ...loc, photo_id: photos[0] };
      if (row) await api.post(`/labour/${row.id}/check-out`, body); else await api.post(`/projects/${project.id}/labour/check-in`, body);
      toast.success(row ? "Labour checked out" : "Labour checked in"); onDone();
    } catch (e) { toast.error(e.response ? apiError(e.response.data?.detail) : e.message); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md" data-testid="labour-dialog"><DialogHeader><DialogTitle>{row ? "Labour check-out" : "Labour check-in"}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Labour in-charge</Label><Input value={f.labour_incharge} disabled={!!row} onChange={(e) => setF({ ...f, labour_incharge: e.target.value })} data-testid="labour-incharge-input" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Masons</Label><Input type="number" min={0} value={f.masons} onChange={(e) => setF({ ...f, masons: Number(e.target.value) })} data-testid="labour-masons-input" /></div>
            <div className="space-y-1.5"><Label>Helpers</Label><Input type="number" min={0} value={f.helpers} onChange={(e) => setF({ ...f, helpers: Number(e.target.value) })} data-testid="labour-helpers-input" /></div>
          </div>
          <CameraCapture projectId={project.id} value={photos} onChange={setPhotos} max={1} label="Gang photo (required)" />
          <p className="flex items-center gap-1 text-xs text-muted-foreground"><MapPin className="h-3 w-3" /> Your GPS location is checked against the site geofence.</p>
        </div>
        <DialogFooter><Button onClick={save} disabled={busy || !photos.length} data-testid="labour-save-btn">Confirm</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function GeofenceForm({ project, fence, onDone }) {
  const [f, setF] = useState(fence || { lat: "", lng: "", radius_m: 200 });
  const here = () => gps().then((l) => setF({ ...f, ...l })).catch((e) => toast.error(e.message));
  const save = async () => { try { await api.put(`/projects/${project.id}/geofence`, { lat: Number(f.lat), lng: Number(f.lng), radius_m: Number(f.radius_m) }); toast.success("Geofence saved"); onDone(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  return (
    <div className="flex flex-wrap items-end gap-2" data-testid="geofence-form">
      {[["lat", "Site latitude"], ["lng", "Site longitude"], ["radius_m", "Radius (m)"]].map(([k, l]) => <div key={k} className="space-y-1"><Label className="text-xs">{l}</Label>
        <Input className="w-36" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`geofence-${k}`} /></div>)}
      <Button variant="outline" onClick={here} data-testid="geofence-here-btn"><MapPin className="h-4 w-4" /> Use my location</Button>
      <Button onClick={save} data-testid="geofence-save-btn">Save geofence</Button>
    </div>
  );
}

export function LabourSection({ project, perms, manages, month }) {
  const [d, setD] = useState(null);
  const [dlg, setDlg] = useState(null);
  const load = () => api.get(`/projects/${project.id}/labour`, { params: { month } }).then((r) => setD(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id, month]);
  if (!d) return null;
  const create = (perms?.attendance || []).includes("create");
  return (
    <Card className="space-y-3 p-5" data-testid="labour-section">
      <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-heading font-bold">Labour attendance (masons & helpers)</h3>
        {create && d.geofence && <Button onClick={() => setDlg({})} data-testid="labour-checkin-btn"><LogIn className="h-4 w-4" /> Labour check-in</Button>}</div>
      {manages && <GeofenceForm project={project} fence={d.geofence} onDone={load} />}
      {!d.geofence && !manages && <p className="text-sm text-muted-foreground">The project manager has not set the site geofence yet.</p>}
      <p className="text-sm">This month: <b>{d.totals.masons}</b> mason-days · <b>{d.totals.helpers}</b> helper-days</p>
      <div className="divide-y rounded-lg border">{d.rows.map((r) => (
        <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm" data-testid="labour-row">
          <span className="flex items-center gap-2">{[r.check_in?.photo_id, r.check_out?.photo_id].filter(Boolean).map((id) => <AuthImage key={id} thumb fileId={id} className="h-10 w-10 rounded object-cover" alt="labour" />)}
            <span><b>{r.labour_incharge}</b> · {formatDate(r.date)} · {r.masons} masons · {r.helpers} helpers · in {r.check_in.distance_m} m from site</span></span>
          {r.check_out ? <span className="text-xs text-muted-foreground">out · {r.check_out.masons}M/{r.check_out.helpers}H</span>
            : create && <Button size="sm" variant="outline" onClick={() => setDlg(r)} data-testid="labour-checkout-btn"><LogOut className="h-4 w-4" /> Check out</Button>}
        </div>))}</div>
      {dlg && <PunchDialog project={project} row={dlg.id ? dlg : null} onClose={() => setDlg(null)} onDone={() => { setDlg(null); load(); }} />}
    </Card>
  );
}
