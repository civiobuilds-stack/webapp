import { useState } from "react";
import { api, apiError, fileUrl } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ThumbsUp, MessageSquareWarning, Loader2, PartyPopper } from "lucide-react";
import { toast } from "sonner";

function DecisionDialog({ update, action, onClose, onDone }) {
  const [comment, setComment] = useState(action === "approve" ? "Looks good, approved." : "");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await api.post(`/progress-updates/${update.id}/client-decision`, { action, comment }); toast.success(action === "approve" ? "Approved — thank you!" : "Change request sent to your team"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>{action === "approve" ? "Approve this work" : "Request changes"}</DialogTitle></DialogHeader>
        <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={4} placeholder={action === "approve" ? "Add a note (required)" : "What would you like changed or clarified?"} data-testid="home-decision-comment" />
        <DialogFooter><Button onClick={submit} disabled={busy || !comment.trim()} data-testid="home-decision-submit">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Send"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DecisionCard({ u, onPick }) {
  const photo = u.photos?.[0];
  return (
    <Card className="overflow-hidden border-2 border-[hsl(222_100%_56%)]/30" data-testid="home-decision-card">
      <div className="flex flex-col sm:flex-row">
        {photo && <img src={fileUrl(photo.id)} alt="Work evidence" className="h-40 w-full object-cover sm:h-auto sm:w-48" />}
        <div className="flex-1 p-5">
          <p className="text-xs font-semibold uppercase tracking-widest text-[hsl(222_100%_56%)]">Awaiting your approval</p>
          <h3 className="mt-1 font-heading text-xl font-bold">{u.activity?.name || "Work update"} — {u.percent_complete}% done</h3>
          <p className="mt-1 text-sm text-muted-foreground">{u.notes}</p>
          {u.pm_comment && <p className="mt-2 rounded-lg bg-muted p-2 text-xs"><b>Project manager:</b> {u.pm_comment}</p>}
          <p className="mt-2 text-xs text-muted-foreground">Submitted {formatDate(u.created_at)}</p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Button size="lg" className="h-12 bg-emerald-600 text-base hover:bg-emerald-700" onClick={() => onPick(u, "approve")} data-testid="home-approve-btn"><ThumbsUp className="h-5 w-5" /> Approve</Button>
            <Button size="lg" variant="outline" className="h-12 text-base" onClick={() => onPick(u, "clarify")} data-testid="home-request-changes-btn"><MessageSquareWarning className="h-5 w-5" /> Request changes</Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

export function DecisionCards({ updates, onDone, otherPending = 0 }) {
  const [pick, setPick] = useState(null);
  if (!updates.length && otherPending) return null;
  if (!updates.length) return (
    <Card className="flex items-center gap-3 p-5" data-testid="home-no-decisions"><PartyPopper className="h-6 w-6 text-emerald-600" />
      <div><div className="font-semibold">You're all caught up</div><div className="text-sm text-muted-foreground">No approvals are waiting on you right now.</div></div></Card>
  );
  return (
    <div className="space-y-4">
      {updates.map((u) => <DecisionCard key={u.id} u={u} onPick={(x, a) => setPick({ u: x, a })} />)}
      {pick && <DecisionDialog update={pick.u} action={pick.a} onClose={() => setPick(null)} onDone={() => { setPick(null); onDone(); }} />}
    </div>
  );
}
