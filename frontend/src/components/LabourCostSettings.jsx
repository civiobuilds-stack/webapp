import { useEffect, useState } from "react";
import { api, apiError, API, getToken } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileDown, Send, BellRing } from "lucide-react";
import { toast } from "sonner";

export function LabourCostSettings() {
  const [w, setW] = useState(null);
  const [logs, setLogs] = useState([]);
  const load = () => {
    api.get("/labour/wages").then((r) => setW(r.data)).catch(() => {});
    api.get("/labour-cost/logs").then((r) => setLogs(r.data)).catch(() => {});
  };
  useEffect(load, []);
  if (!w) return null;
  const save = async () => {
    try { await api.put("/labour/wages", { mason_rate: Number(w.mason_rate), helper_rate: Number(w.helper_rate) }); toast.success("Default wage rates saved"); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  const sendNow = async () => { await api.post("/labour-cost/send-now"); toast.success("Labour cost report queued"); setTimeout(load, 4000); };
  const remind = async () => {
    try { const { data } = await api.post("/store/overdue/remind-now"); toast.success(data.reminded ? `${data.reminded} overdue tool reminder(s) sent` : "No new overdue tools to remind today"); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Card className="space-y-4 p-6" data-testid="labour-cost-settings">
      <div><h3 className="font-heading font-bold">Labour wages & cost report</h3>
        <p className="text-sm text-muted-foreground">Company default daily rates. Each project can override these from its Attendance tab. The branded PDF is emailed to company admins every Saturday at 6 PM IST.</p></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5"><Label>Mason rate (Rs/day)</Label><Input type="number" min={0} value={w.mason_rate} onChange={(e) => setW({ ...w, mason_rate: e.target.value })} data-testid="wage-mason-input" /></div>
        <div className="space-y-1.5"><Label>Helper rate (Rs/day)</Label><Input type="number" min={0} value={w.helper_rate} onChange={(e) => setW({ ...w, helper_rate: e.target.value })} data-testid="wage-helper-input" /></div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button onClick={save} data-testid="wage-save-btn">Save rates</Button>
        <a href={`${API}/labour-cost/pdf?auth=${getToken()}`} target="_blank" rel="noreferrer"><Button variant="outline" data-testid="labour-cost-pdf-btn"><FileDown className="h-4 w-4" /> Download PDF</Button></a>
        <Button variant="outline" onClick={sendNow} data-testid="labour-cost-send-btn"><Send className="h-4 w-4" /> Email report now</Button>
        <Button variant="ghost" onClick={remind} data-testid="tool-remind-now-btn"><BellRing className="h-4 w-4" /> Send overdue tool reminders</Button>
      </div>
      <p className="text-xs text-muted-foreground">Overdue tool reminders also go out automatically every day at 9 AM IST (push + email, copied to the store in-charge / PM).</p>
      {logs.length > 0 && <div className="space-y-1 text-xs text-muted-foreground" data-testid="labour-cost-logs">{logs.slice(0, 5).map((l) => (
        <div key={l.id}>{formatDateTime(l.created_at)} · {l.trigger} · <b>{l.status}</b> · {l.recipients?.length || 0} recipient(s)</div>))}</div>}
    </Card>
  );
}
