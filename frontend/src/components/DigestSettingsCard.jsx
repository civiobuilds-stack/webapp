import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function DigestSettingsCard() {
  const [s, setS] = useState(null);
  const [managers, setManagers] = useState([]);
  const [logs, setLogs] = useState([]);
  const load = () => {
    api.get("/digest/settings").then((r) => setS(r.data)).catch(() => {});
    api.get("/digest/logs").then((r) => setLogs(r.data)).catch(() => {});
  };
  useEffect(() => { load(); api.get("/users").then((r) => setManagers(r.data.filter((u) => ["admin", "project_manager"].includes(u.role)))).catch(() => {}); }, []);
  if (!s) return null;
  const save = async () => {
    try { await api.put("/digest/settings", { enabled: s.enabled, day_of_week: s.day_of_week, hour: s.hour, timezone: s.timezone, recipient_ids: s.recipient_ids }); toast.success("Digest schedule saved"); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const sendNow = async () => { await api.post("/digest/send-now"); toast.success("Digest queued — check the log shortly"); setTimeout(load, 4000); };
  const toggle = (id) => setS({ ...s, recipient_ids: s.recipient_ids.includes(id) ? s.recipient_ids.filter((x) => x !== id) : [...s.recipient_ids, id] });
  return (
    <Card className="space-y-4 p-6" data-testid="digest-settings-card">
      <div className="flex items-center justify-between"><h3 className="font-heading font-bold">Weekly progress digest</h3>
        <Switch checked={s.enabled} onCheckedChange={(v) => setS({ ...s, enabled: v })} data-testid="digest-enabled-switch" /></div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5"><Label>Day</Label>
          <Select value={String(s.day_of_week)} onValueChange={(v) => setS({ ...s, day_of_week: Number(v) })}><SelectTrigger data-testid="digest-day-select"><SelectValue /></SelectTrigger>
            <SelectContent>{DAYS.map((d, i) => <SelectItem key={d} value={String(i)}>{d}</SelectItem>)}</SelectContent></Select></div>
        <div className="space-y-1.5"><Label>Hour (0–23)</Label><Input type="number" min={0} max={23} value={s.hour} onChange={(e) => setS({ ...s, hour: Number(e.target.value) })} data-testid="digest-hour-input" /></div>
        <div className="space-y-1.5"><Label>Timezone</Label><Input value={s.timezone} onChange={(e) => setS({ ...s, timezone: e.target.value })} data-testid="digest-timezone-input" /></div>
      </div>
      <div className="space-y-1.5"><Label>Recipients (none selected = all admins & PMs)</Label>
        <div className="grid gap-2 sm:grid-cols-2">{managers.map((m) => (
          <label key={m.id} className="flex items-center gap-2 text-sm"><Checkbox checked={s.recipient_ids.includes(m.id)} onCheckedChange={() => toggle(m.id)} data-testid={`digest-recipient-${m.id}`} /> {m.name}</label>
        ))}</div></div>
      <div className="flex gap-2"><Button onClick={save} data-testid="digest-save-btn">Save schedule</Button><Button variant="outline" onClick={sendNow} data-testid="digest-send-now-btn">Send now</Button></div>
      {logs.length > 0 && <div className="space-y-1 text-xs text-muted-foreground" data-testid="digest-logs">{logs.slice(0, 5).map((l) => (
        <div key={l.id}>{formatDateTime(l.created_at)} · {l.trigger} · <b>{l.status}</b> · {l.recipients?.length || 0} recipient(s)</div>))}</div>}
    </Card>
  );
}
