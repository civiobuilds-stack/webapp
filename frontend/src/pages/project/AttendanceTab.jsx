import { useEffect, useState } from "react";
import { api, apiError, API, getToken } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { LogIn, LogOut, FileDown, Pencil } from "lucide-react";
import { toast } from "sonner";
import { LabourSection } from "@/pages/project/LabourSection";

const t = (v) => (v ? new Date(v).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—");
const local = (v) => (v ? new Date(new Date(v).getTime() + 5.5 * 3600e3).toISOString().slice(0, 16) : "");
const toIso = (v) => (v ? new Date(v + ":00+05:30").toISOString() : null);
const can = (p, a) => (p?.attendance || []).includes(a);

function CorrectDialog({ row, onClose, onDone }) {
  const [f, setF] = useState({ check_in: local(row.check_in), check_out: local(row.check_out), reason: "" });
  const save = async () => {
    try { await api.post(`/attendance/${row.id}/correct`, { check_in: toIso(f.check_in), check_out: toIso(f.check_out), reason: f.reason }); toast.success("Attendance corrected"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>Correct attendance — {row.user_name}, {formatDate(row.date)}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Check-in (IST)</Label><Input type="datetime-local" value={f.check_in} onChange={(e) => setF({ ...f, check_in: e.target.value })} data-testid="att-correct-in" /></div>
          <div className="space-y-1.5"><Label>Check-out (IST)</Label><Input type="datetime-local" value={f.check_out} onChange={(e) => setF({ ...f, check_out: e.target.value })} data-testid="att-correct-out" /></div>
          <div className="space-y-1.5"><Label>Reason (audited)</Label><Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} data-testid="att-correct-reason" /></div>
        </div>
        <DialogFooter><Button onClick={save} disabled={f.reason.trim().length < 3} data-testid="att-correct-save">Save correction</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AttendanceTab({ project, userId, perms, manages }) {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [rows, setRows] = useState([]);
  const [sum, setSum] = useState(null);
  const [fix, setFix] = useState(null);
  const load = () => {
    api.get(`/projects/${project.id}/attendance`, { params: { month } }).then((r) => setRows(r.data)).catch(() => {});
    if (can(perms, "view")) api.get(`/projects/${project.id}/attendance/summary`, { params: { month } }).then((r) => setSum(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id, month]);
  const todayIst = new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);
  const mine = rows.find((r) => r.user_id === userId && r.date === todayIst);
  const punch = async (kind) => {
    try { await api.post(`/projects/${project.id}/attendance/${kind}`, {}); toast.success(kind === "check-in" ? "Checked in" : "Checked out"); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <div className="space-y-4" data-testid="attendance-tab">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-heading text-lg font-semibold">Attendance</h2>
        <div className="flex flex-wrap items-center gap-2">
          {can(perms, "create") && (!mine ? <Button onClick={() => punch("check-in")} data-testid="check-in-btn"><LogIn className="h-4 w-4" /> Check in</Button>
            : !mine.check_out ? <Button variant="outline" onClick={() => punch("check-out")} data-testid="check-out-btn"><LogOut className="h-4 w-4" /> Check out</Button>
            : <Badge variant="outline" data-testid="attendance-done">Done for today · {mine.hours}h</Badge>)}
          <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-40" data-testid="attendance-month" />
          {can(perms, "export") && <a href={`${API}/projects/${project.id}/attendance/export?month=${month}&auth=${getToken()}`}><Button variant="secondary" data-testid="attendance-export-btn"><FileDown className="h-4 w-4" /> CSV</Button></a>}
        </div>
      </div>
      {sum && (
        <Card className="p-5" data-testid="attendance-summary">
          <div className="flex flex-wrap gap-6 text-sm"><span><b className="font-mono text-xl">{sum.today_present}</b> present today</span>
            <span><b className="font-mono text-xl">{sum.person_days}</b> person-days</span><span><b className="font-mono text-xl">{sum.total_hours}</b> hours</span></div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {sum.people.map((p) => <div key={p.user_id} className="rounded-lg border p-2 text-sm"><b>{p.name}</b> · {p.days} days · {p.hours}h{p.corrections ? ` · ${p.corrections} corrected` : ""}</div>)}
          </div>
        </Card>
      )}
      <Card className="divide-y">
        {rows.length === 0 && <p className="p-4 text-sm text-muted-foreground">No attendance recorded for this month.</p>}
        {rows.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm" data-testid="attendance-row">
            <span><b>{r.user_name}</b> · {formatDate(r.date)}</span>
            <span className="flex items-center gap-3">{t(r.check_in)} → {t(r.check_out)} · {r.hours}h
              {r.corrected && <Badge variant="outline">corrected</Badge>}
              {can(perms, "approve") && <Button size="sm" variant="ghost" onClick={() => setFix(r)} data-testid="att-correct-btn"><Pencil className="h-4 w-4" /></Button>}</span>
          </div>
        ))}
      </Card>
      <LabourSection project={project} perms={perms} manages={manages} month={month} />
      {fix && <CorrectDialog row={fix} onClose={() => setFix(null)} onDone={() => { setFix(null); load(); }} />}
    </div>
  );
}
