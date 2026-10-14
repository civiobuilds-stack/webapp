import { useEffect, useState } from "react";
import { api, apiError, fileUrl, getToken, API } from "@/lib/api";
import { isManager, formatDate, formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { FileText, Loader2, Download, FilePlus } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const TYPES = {
  progress: "Construction Progress Report",
  completion: "Project Completion Report",
  cost: "Project Cost Summary",
};

export function ReportsTab({ project, role }) {
  const manager = isManager(role);
  const [reports, setReports] = useState([]);
  const load = () => api.get(`/projects/${project.id}/reports`).then((r) => setReports(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);

  const reportUrl = (id) => `${API}/reports/${id}/download?auth=${getToken()}`;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h3 className="font-heading text-lg font-semibold">Reports</h3>
          <p className="text-sm text-muted-foreground">Civio-branded PDFs generated from live project data. Historical revisions are preserved.</p></div>
        {manager && <GenerateDialog projectId={project.id} onDone={load} />}
      </div>

      {reports.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-12 text-center text-muted-foreground"><FileText className="h-8 w-8" /> No reports generated yet.</Card>
      ) : (
        <div className="space-y-2">
          {reports.map((r) => (
            <Card key={r.id} className="flex flex-wrap items-center justify-between gap-3 p-4" data-testid="report-row">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><FileText className="h-5 w-5" /></div>
                <div>
                  <div className="font-medium">{r.title}</div>
                  <div className="text-xs text-muted-foreground">
                    Rev {r.revision} · {formatDateTime(r.generated_at)} · by {r.generated_by_name}
                    {r.period_start || r.period_end ? ` · ${formatDate(r.period_start)}–${formatDate(r.period_end)}` : ""}
                  </div>
                </div>
              </div>
              <a href={reportUrl(r.id)} target="_blank" rel="noreferrer" data-testid="download-report-btn">
                <Button variant="outline" size="sm"><Download className="h-4 w-4" /> Download</Button>
              </a>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function GenerateDialog({ projectId, onDone }) {
  const { user } = useAuth();
  const hasProcurement = (user?.enterprise?.modules || []).includes("procurement");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [type, setType] = useState("progress");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [rec, setRec] = useState("");

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/projects/${projectId}/reports`, { type, period_start: start || null, period_end: end || null, recommendations: rec });
      toast.success("Report generated"); setOpen(false); onDone();
      setStart(""); setEnd(""); setRec("");
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button data-testid="generate-report-btn"><FilePlus className="h-4 w-4" /> Generate report</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Generate PDF report</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Report type</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger data-testid="report-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>{Object.entries(TYPES).filter(([k]) => k !== "cost" || hasProcurement).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label>Period start (optional)</Label><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} data-testid="report-start-input" /></div>
            <div className="space-y-1.5"><Label>Period end (optional)</Label><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} data-testid="report-end-input" /></div>
          </div>
          {type === "completion" && (
            <div className="space-y-1.5"><Label>Recommendations / sign-off note</Label><Textarea value={rec} onChange={(e) => setRec(e.target.value)} rows={3} data-testid="report-rec-input" /></div>
          )}
        </div>
        <DialogFooter><Button onClick={submit} disabled={busy} data-testid="confirm-generate-report">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Generate & save"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
