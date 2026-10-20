import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Lightbulb, Send } from "lucide-react";
import { toast } from "sonner";

export const PRIORITY_CLS = { high: "bg-rose-50 text-rose-800 border-rose-300", medium: "bg-amber-50 text-amber-800 border-amber-300", low: "bg-slate-100 text-slate-700 border-slate-300" };

export default function FeatureRequest() {
  const [f, setF] = useState({ title: "", description: "", priority: "medium" });
  const [mine, setMine] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/feature-requests/mine").then((r) => setMine(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const submit = async () => {
    setBusy(true);
    try { await api.post("/feature-requests", f); toast.success("Thanks! Your request was sent to the CIVIO team."); setF({ title: "", description: "", priority: "medium" }); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <div className="max-w-2xl space-y-6" data-testid="feature-request-page">
      <div><p className="text-xs font-semibold uppercase tracking-widest text-accent">Feedback</p><h1 className="font-heading text-3xl font-bold">Request a feature</h1>
        <p className="text-sm text-muted-foreground">Tell the CIVIO team what would make your work easier.</p></div>
      <Card className="space-y-4 p-5">
        <div className="space-y-1.5"><Label>Title</Label><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="e.g. Export attendance to Excel" data-testid="feature-title-input" /></div>
        <div className="space-y-1.5"><Label>Description</Label><Textarea rows={5} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="What do you need and why?" data-testid="feature-description-input" /></div>
        <div className="space-y-1.5"><Label>Priority</Label>
          <Select value={f.priority} onValueChange={(v) => setF({ ...f, priority: v })}><SelectTrigger className="w-48" data-testid="feature-priority-select"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="low">Low</SelectItem><SelectItem value="medium">Medium</SelectItem><SelectItem value="high">High</SelectItem></SelectContent></Select></div>
        <Button onClick={submit} disabled={busy || f.title.trim().length < 3 || f.description.trim().length < 5} data-testid="feature-submit-btn"><Send className="h-4 w-4" /> Send request</Button>
      </Card>
      {mine.length > 0 && <div className="space-y-2"><h2 className="font-heading font-semibold">My requests</h2>
        <Card className="divide-y">{mine.map((r) => <div key={r.id} className="p-4" data-testid="my-feature-row">
          <div className="flex items-center gap-2"><Lightbulb className="h-4 w-4 text-accent" /><span className="font-medium">{r.title}</span><Badge variant="outline" className={PRIORITY_CLS[r.priority]}>{r.priority}</Badge></div>
          <p className="mt-1 text-sm text-muted-foreground">{r.description}</p><p className="text-xs text-muted-foreground">{formatDateTime(r.created_at)}</p></div>)}</Card></div>}
    </div>
  );
}

export function FeatureRequestsPanel() {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState("");
  useEffect(() => { api.get("/superadmin/feature-requests").then((r) => setRows(r.data)).catch(() => {}); }, []);
  const shown = rows.filter((r) => !q || `${r.title} ${r.description} ${r.user_name} ${r.user_email} ${r.enterprise_name}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="space-y-3" data-testid="sa-feature-requests">
      <div className="flex flex-wrap items-center gap-2"><Input className="max-w-xs" placeholder="Search requests" value={q} onChange={(e) => setQ(e.target.value)} data-testid="sa-feature-search" />
        <span className="text-xs text-muted-foreground" data-testid="sa-feature-count">{shown.length} requests</span></div>
      <Card className="divide-y">
        {shown.length === 0 && <p className="p-4 text-sm text-muted-foreground">No feature requests yet.</p>}
        {shown.map((r) => <div key={r.id} className="space-y-1 p-4" data-testid="sa-feature-row">
          <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{r.title}</span><Badge variant="outline" className={PRIORITY_CLS[r.priority]}>{r.priority}</Badge>
            <span className="text-xs text-muted-foreground">{formatDateTime(r.created_at)}</span></div>
          <p className="whitespace-pre-wrap text-sm">{r.description}</p>
          <p className="text-xs text-muted-foreground" data-testid="sa-feature-requester">{r.user_name} · {r.user_role} · {r.user_email}{r.user_phone ? ` · ${r.user_phone}` : ""} · {r.enterprise_name} ({r.business_type})</p>
        </div>)}
      </Card>
    </div>
  );
}
