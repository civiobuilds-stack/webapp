import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";

export function LifecycleDialog({ ent, onClose, onDone }) {
  const [trialEnd, setTrialEnd] = useState(ent.trial_end || "");
  const [days, setDays] = useState("");
  const [renew, setRenew] = useState(ent.subscription_expires_at || "");
  const go = async (body) => {
    try { await api.post(`/superadmin/enterprises/${ent.id}/lifecycle`, body); toast.success("Subscription updated"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md" data-testid="sa-lifecycle-dialog">
      <DialogHeader><DialogTitle>Trial & renewal — {ent.name}</DialogTitle></DialogHeader>
      <p className="text-xs text-muted-foreground">Current: <b className="capitalize">{ent.subscription?.state || "active"}</b>{ent.subscription?.end_date ? ` · ends ${formatDate(ent.subscription.end_date)}` : " · no end date"}</p>
      <div className="space-y-4">
        <div className="space-y-1.5"><Label>Set trial end date</Label><div className="flex gap-2">
          <Input type="date" value={trialEnd} onChange={(e) => setTrialEnd(e.target.value)} data-testid="sa-trial-end-input" />
          <Button variant="outline" disabled={!trialEnd} onClick={() => go({ action: "set_trial", trial_end: trialEnd })} data-testid="sa-set-trial-btn">Set</Button></div></div>
        <div className="space-y-1.5"><Label>Extend trial by days</Label><div className="flex gap-2">
          <Input type="number" min={1} value={days} onChange={(e) => setDays(e.target.value)} data-testid="sa-extend-days-input" />
          <Button variant="outline" disabled={!days} onClick={() => go({ action: "extend_trial", days: Number(days) })} data-testid="sa-extend-trial-btn">Extend</Button></div></div>
        <div className="space-y-1.5"><Label>Activate paid subscription — renewal date</Label><div className="flex gap-2">
          <Input type="date" value={renew} onChange={(e) => setRenew(e.target.value)} data-testid="sa-renewal-input" />
          <Button disabled={!renew} onClick={() => go({ action: "activate", renewal_date: renew })} data-testid="sa-activate-sub-btn">Activate</Button></div></div>
        <p className="text-xs text-muted-foreground">Access is restored immediately after extending or activating. Data is never deleted.</p>
      </div>
    </DialogContent></Dialog>
  );
}

export function BillingSettingsCard() {
  const [f, setF] = useState(null);
  useEffect(() => { api.get("/superadmin/settings/billing").then((r) => setF({ payment_instructions: r.data.payment_instructions || "", default_trial_days: r.data.default_trial_days ?? "" })).catch(() => {}); }, []);
  const save = async () => {
    try { await api.put("/superadmin/settings/billing", { payment_instructions: f.payment_instructions, default_trial_days: f.default_trial_days ? Number(f.default_trial_days) : null }); toast.success("Billing settings saved"); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  if (!f) return null;
  return (
    <Card className="space-y-3 p-5" data-testid="sa-billing-settings">
      <div className="font-heading font-semibold">Payment instructions & trial</div>
      <div className="space-y-1.5"><Label>Payment instructions (shown in reminder emails and on the Trial ended screen)</Label>
        <Textarea rows={4} value={f.payment_instructions} onChange={(e) => setF({ ...f, payment_instructions: e.target.value })} placeholder="Bank: … IFSC: … UPI: civio@bank — send the reference to …" data-testid="sa-payment-instructions" /></div>
      <div className="space-y-1.5"><Label>Default trial length for newly approved workspaces (days, blank = no trial)</Label>
        <Input type="number" min={1} className="max-w-[200px]" value={f.default_trial_days} onChange={(e) => setF({ ...f, default_trial_days: e.target.value })} data-testid="sa-default-trial-days" /></div>
      <Button onClick={save} data-testid="sa-billing-settings-save">Save</Button>
    </Card>
  );
}
