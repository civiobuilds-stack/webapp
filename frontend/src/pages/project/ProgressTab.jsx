import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { isManager, formatDateTime } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadges";
import { PhotoUpload, PhotoGrid } from "@/components/PhotoUpload";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Loader2, History, Check, X, RotateCcw, MessageSquareWarning } from "lucide-react";
import { toast } from "sonner";

export function ProgressTab({ project, role, userId }) {
  const [updates, setUpdates] = useState([]);
  const [activities, setActivities] = useState([]);
  const manager = isManager(role);

  const load = () => {
    api.get(`/projects/${project.id}/progress-updates`).then((r) => setUpdates(r.data)).catch(() => {});
    api.get(`/projects/${project.id}/activities`).then((r) => setActivities(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h3 className="font-heading text-lg font-semibold">Progress updates</h3>
          <p className="text-sm text-muted-foreground">Draft → Submitted → Reviewed → Pending Client → Approved.</p></div>
        {role === "site_engineer" && <SubmitDialog projectId={project.id} activities={activities} onDone={load} />}
      </div>

      {updates.length === 0 ? <Card className="p-10 text-center text-muted-foreground">No progress updates yet.</Card> : (
        <div className="space-y-3">
          {updates.map((u) => (
            <Card key={u.id} className="p-4" data-testid="progress-update-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={u.status} />
                    <Badge variant="outline" className="text-[11px]">v{u.version}</Badge>
                    {u.previous_version_id && <Badge variant="secondary" className="text-[11px]">Revision</Badge>}
                  </div>
                  <div className="mt-1.5 font-medium">{u.activity?.name || "Activity"}</div>
                  <div className="text-sm text-muted-foreground">{u.engineer?.name} · {formatDateTime(u.created_at)}</div>
                </div>
                <div className="text-right"><div className="font-mono text-2xl font-bold">{u.percent_complete}%</div><div className="text-xs text-muted-foreground">reported</div></div>
              </div>
              {u.notes && <p className="mt-3 rounded-lg bg-muted/50 p-3 text-sm">{u.notes}</p>}
              {u.photos?.length > 0 && <div className="mt-3"><PhotoGrid photos={u.photos} /></div>}
              {(u.pm_comment || u.client_comment) && (
                <div className="mt-3 space-y-2">
                  {u.pm_comment && <Comment label="PM" text={u.pm_comment} />}
                  {u.client_comment && <Comment label="Client" text={u.client_comment} />}
                </div>
              )}
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <HistoryDialog update={u} />
                {manager && ["submitted", "clarification_needed"].includes(u.status) && <ReviewActions update={u} onDone={load} />}
                {role === "client" && u.status === "pending_client_decision" && <ClientActions update={u} onDone={load} />}
                {role === "site_engineer" && u.engineer_id === userId && ["clarification_needed", "rejected"].includes(u.status) && !u.superseded_by && (
                  <ReviseDialog update={u} onDone={load} />
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function Comment({ label, text }) {
  return <div className="rounded-lg border-l-2 border-accent bg-accent/5 p-2.5 text-sm"><span className="font-semibold">{label}:</span> {text}</div>;
}

function SubmitDialog({ projectId, activities, onDone }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [activityId, setActivityId] = useState("");
  const [pct, setPct] = useState([0]);
  const [qty, setQty] = useState("");
  const [notes, setNotes] = useState("");
  const [photos, setPhotos] = useState([]);
  const mine = activities; // engineer sees project activities

  const submit = async () => {
    if (!activityId) { toast.error("Select an activity"); return; }
    setBusy(true);
    try {
      await api.post(`/projects/${projectId}/progress-updates`, { activity_id: activityId, percent_complete: pct[0], quantity_completed: qty ? Number(qty) : null, notes, photo_ids: photos, submit: true });
      toast.success("Progress update submitted"); setOpen(false); onDone();
      setActivityId(""); setPct([0]); setQty(""); setNotes(""); setPhotos([]);
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button data-testid="submit-progress-btn"><Plus className="h-4 w-4" /> Submit update</Button></DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
        <DialogHeader><DialogTitle>Submit progress update</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5"><Label>Activity</Label>
            <Select value={activityId} onValueChange={setActivityId}>
              <SelectTrigger data-testid="progress-activity-select"><SelectValue placeholder="Select activity" /></SelectTrigger>
              <SelectContent>{mine.map((a) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between"><Label>Percent complete</Label><span className="font-mono font-bold">{pct[0]}%</span></div>
            <Slider value={pct} onValueChange={setPct} max={100} step={5} data-testid="progress-percent-slider" />
          </div>
          <div className="space-y-1.5"><Label>Quantity completed (optional)</Label><Input type="number" value={qty} onChange={(e) => setQty(e.target.value)} data-testid="progress-qty-input" /></div>
          <div className="space-y-1.5"><Label>Site notes</Label><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} data-testid="progress-notes-input" /></div>
          <PhotoUpload projectId={projectId} value={photos} onChange={setPhotos} />
        </div>
        <DialogFooter><Button onClick={submit} disabled={busy} data-testid="confirm-submit-progress">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit for review"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReviewActions({ update, onDone }) {
  const [action, setAction] = useState(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try { await api.post(`/progress-updates/${update.id}/review`, { action, comment }); toast.success(`Update ${action}ed`); setAction(null); setComment(""); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!action} onOpenChange={(o) => !o && setAction(null)}>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => setAction("approve")} data-testid="pm-approve-btn"><Check className="h-4 w-4" /> Approve</Button>
        <Button size="sm" variant="outline" onClick={() => setAction("return")} data-testid="pm-return-btn"><RotateCcw className="h-4 w-4" /> Return</Button>
        <Button size="sm" variant="destructive" onClick={() => setAction("reject")} data-testid="pm-reject-btn"><X className="h-4 w-4" /> Reject</Button>
      </div>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle className="capitalize">{action} progress update</DialogTitle></DialogHeader>
        <div className="space-y-1.5"><Label>Comment {action !== "approve" ? "(for the engineer)" : "(optional)"}</Label>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3} data-testid="review-comment-input" /></div>
        <DialogFooter><Button onClick={run} disabled={busy} data-testid="confirm-review-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : `Confirm ${action}`}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ClientActions({ update, onDone }) {
  const [action, setAction] = useState(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!comment.trim()) { toast.error("A comment is required."); return; }
    setBusy(true);
    try { await api.post(`/progress-updates/${update.id}/client-decision`, { action, comment }); toast.success("Decision recorded"); setAction(null); setComment(""); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!action} onOpenChange={(o) => !o && setAction(null)}>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => setAction("approve")} data-testid="client-approve-btn"><Check className="h-4 w-4" /> Approve</Button>
        <Button size="sm" variant="destructive" onClick={() => setAction("reject")} data-testid="client-reject-btn"><X className="h-4 w-4" /> Reject</Button>
        <Button size="sm" variant="outline" onClick={() => setAction("clarify")} data-testid="client-clarify-btn"><MessageSquareWarning className="h-4 w-4" /> Clarify</Button>
      </div>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle className="capitalize">{action === "clarify" ? "Request clarification" : `${action} update`}</DialogTitle></DialogHeader>
        <div className="space-y-1.5"><Label>Your comment (required)</Label>
          <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3} data-testid="client-comment-input" /></div>
        <DialogFooter><Button onClick={run} disabled={busy} data-testid="confirm-client-decision">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit decision"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReviseDialog({ update, onDone }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pct, setPct] = useState([update.percent_complete]);
  const [notes, setNotes] = useState("");
  const [photos, setPhotos] = useState(update.photo_ids || []);

  const submit = async () => {
    setBusy(true);
    try { await api.post(`/progress-updates/${update.id}/revise`, { percent_complete: pct[0], notes, photo_ids: photos }); toast.success("Revision submitted"); setOpen(false); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm" variant="outline" data-testid="revise-btn"><RotateCcw className="h-4 w-4" /> Submit revision</Button></DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
        <DialogHeader><DialogTitle>Submit revision (v{update.version + 1})</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2"><div className="flex justify-between"><Label>Percent complete</Label><span className="font-mono font-bold">{pct[0]}%</span></div>
            <Slider value={pct} onValueChange={setPct} max={100} step={5} data-testid="revise-percent-slider" /></div>
          <div className="space-y-1.5"><Label>What changed</Label><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} data-testid="revise-notes-input" /></div>
          <PhotoUpload projectId={update.project_id} value={photos} onChange={setPhotos} />
        </div>
        <DialogFooter><Button onClick={submit} disabled={busy} data-testid="confirm-revise-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit revision"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function HistoryDialog({ update }) {
  return (
    <Dialog>
      <DialogTrigger asChild><Button size="sm" variant="ghost" data-testid="history-btn"><History className="h-4 w-4" /> History</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Approval history</DialogTitle></DialogHeader>
        <div className="space-y-4">
          {(update.history || []).map((h, i) => (
            <div key={i} className="flex gap-3" data-testid="history-entry">
              <div className="flex flex-col items-center"><span className="h-2.5 w-2.5 rounded-full bg-primary" />{i < update.history.length - 1 && <span className="mt-1 h-full w-px flex-1 bg-border" />}</div>
              <div className="-mt-0.5 pb-2"><div className="text-sm font-semibold capitalize">{h.status.replace(/_/g, " ")}</div>
                <div className="text-xs text-muted-foreground">{h.by} · {formatDateTime(h.at)}</div>
                {h.comment && <div className="mt-1 text-sm">{h.comment}</div>}</div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
