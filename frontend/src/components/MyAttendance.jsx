import { useEffect, useMemo, useState } from "react";
import { api, apiError, API, getToken } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, LogIn, LogOut, MapPin, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { AuthImage } from "@/components/AuthImage";
import { CameraPicker } from "@/components/CameraPicker";

const time = (iso) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—");
const mapUrl = (c) => `https://www.google.com/maps?q=${c.lat},${c.lng}`;
const getGps = () => new Promise((res, rej) => navigator.geolocation
  ? navigator.geolocation.getCurrentPosition((p) => res(p.coords), () => rej(new Error("Location permission is required to mark attendance.")), { enableHighAccuracy: true, timeout: 15000 })
  : rej(new Error("This device has no GPS.")));

function SelfieCheckIn({ status, onDone }) {
  const [blob, setBlob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [pid, setPid] = useState(status.projects[0]?.id || "office");
  const preview = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  const submit = async () => {
    setBusy(true);
    try {
      const g = await getGps();
      const fd = new FormData();
      fd.append("selfie", new File([blob], `selfie_${Date.now()}.jpg`, { type: "image/jpeg" }));
      fd.append("lat", g.latitude); fd.append("lng", g.longitude); fd.append("accuracy", g.accuracy);
      fd.append("project_id", pid === "office" ? "" : pid);
      await api.post("/my-attendance/check-in", fd);
      toast.success("Checked in"); onDone();
    } catch (e) { toast.error(e.response ? apiError(e.response.data?.detail) : e.message); }
    finally { setBusy(false); }
  };
  const sel = status.projects.find((p) => p.id === pid);
  return (
    <Card className="space-y-4 p-5" data-testid="selfie-checkin">
      <div className="space-y-1.5"><Label>Where are you working today?</Label>
        <Select value={pid} onValueChange={setPid}><SelectTrigger data-testid="att-project-select"><SelectValue /></SelectTrigger>
          <SelectContent>{status.projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name} ({p.code}){p.location_required ? " · site location required" : ""}</SelectItem>)}
            <SelectItem value="office">Office / off-site</SelectItem></SelectContent></Select>
        {sel?.location_required && <p className="text-xs text-amber-700">You must be inside the site geofence to check in here.</p>}</div>
      {preview && <img src={preview} alt="selfie" className="w-full max-w-sm rounded-lg" data-testid="selfie-preview" />}
      {!blob && <CameraPicker facing="user" strict label="Take selfie" testId="selfie-open-btn" onPhoto={setBlob} />}
      {blob && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={submit} disabled={busy} data-testid="checkin-submit-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />} Check in with GPS</Button>
          <Button variant="outline" disabled={busy} onClick={() => setBlob(null)} data-testid="selfie-retake-btn"><RotateCcw className="h-4 w-4" /> Retake</Button>
        </div>
      )}
      <p className="text-xs text-muted-foreground">Take the selfie with your camera. Selfies are visible only to you, your project manager and the owner.</p>
    </Card>
  );
}

function Row({ r, showName }) {
  return (
    <div className="flex flex-wrap items-center gap-3 p-3" data-testid="att-row">
      <AuthImage path={`/my-attendance/${r.id}/selfie`} alt="" className="h-12 w-12 rounded-lg object-cover" data-testid="att-selfie" />
      <div className="min-w-0 flex-1">
        <div className="font-medium">{showName ? r.user_name : formatDate(r.date)} <span className="text-xs text-muted-foreground">· {r.project_name}</span></div>
        <div className="text-xs text-muted-foreground">In {time(r.check_in?.at)} · Out {time(r.check_out?.at)}{r.check_in?.distance_m != null ? ` · ${r.check_in.distance_m} m from site` : ""}</div>
      </div>
      <a href={mapUrl(r.check_in)} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary underline" data-testid="att-map-link"><MapPin className="h-3.5 w-3.5" /> Map</a>
    </div>
  );
}

function TeamAttendance() {
  const [date, setDate] = useState(new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }));
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/my-attendance/team", { params: { date } }).then((r) => setD(r.data)).catch(() => setD(null)); }, [date]);
  return (
    <div className="space-y-3" data-testid="team-attendance">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-heading text-lg font-semibold">Team attendance</h2>
        <Input type="date" className="w-44" value={date} onChange={(e) => setDate(e.target.value)} data-testid="team-att-date" /></div>
      <Card className="divide-y">
        {d?.records?.length === 0 && <p className="p-4 text-sm text-muted-foreground">No check-ins for this date.</p>}
        {d?.records?.map((r) => <Row key={r.id} r={r} showName />)}
      </Card>
      {d?.not_checked_in?.length > 0 && <div className="flex flex-wrap gap-2 text-xs"><span className="text-muted-foreground">Not checked in:</span>
        {d.not_checked_in.map((u) => <Badge key={u.id} variant="outline" data-testid="att-absent">{u.name}</Badge>)}</div>}
    </div>
  );
}

export default function MyAttendance() {
  const [status, setStatus] = useState(null);
  const [mine, setMine] = useState([]);
  const load = () => {
    api.get("/my-attendance/status").then((r) => setStatus(r.data)).catch(() => {});
    api.get("/my-attendance/mine").then((r) => setMine(r.data)).catch(() => {});
  };
  useEffect(load, []);
  const checkOut = async () => {
    try { const g = await getGps(); const fd = new FormData(); fd.append("lat", g.latitude); fd.append("lng", g.longitude);
      await api.post("/my-attendance/check-out", fd); toast.success("Checked out"); load(); }
    catch (e) { toast.error(e.response ? apiError(e.response.data?.detail) : e.message); }
  };
  if (!status) return null;
  const t = status.today;
  return (
    <div className="space-y-6" data-testid="my-attendance-page">
      <div><p className="text-xs font-semibold uppercase tracking-widest text-accent">Attendance</p><h1 className="font-heading text-3xl font-bold">My Attendance</h1></div>
      {!status.enabled && <Card className="p-5 text-sm text-muted-foreground" data-testid="att-not-enabled">Attendance is not switched on for you. Your project manager can enable it from the project Team tab.</Card>}
      {status.enabled && (t ? <Card className="flex flex-wrap items-center justify-between gap-3 p-5" data-testid="att-today">
        <div><div className="font-semibold">Checked in at {time(t.check_in.at)} · {t.project_name}</div>
          <div className="text-sm text-muted-foreground">{t.check_out ? `Checked out at ${time(t.check_out.at)}` : "Remember to check out when you leave."}</div></div>
        {!t.check_out && <Button onClick={checkOut} data-testid="checkout-btn"><LogOut className="h-4 w-4" /> Check out</Button>}
      </Card> : <SelfieCheckIn status={status} onDone={load} />)}
      {mine.length > 0 && <><h2 className="font-heading text-lg font-semibold">My history</h2><Card className="divide-y">{mine.map((r) => <Row key={r.id} r={r} />)}</Card></>}
      {status.can_review && <TeamAttendance />}
    </div>
  );
}
