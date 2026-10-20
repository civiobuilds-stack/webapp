import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatINR, formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Clock, LogOut, Lock, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export function TrialEnded() {
  const { logout } = useAuth();
  const [info, setInfo] = useState(null);
  const [plan, setPlan] = useState(null);
  const [msg, setMsg] = useState("");
  const load = () => api.get("/subscription/info").then((r) => setInfo(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const request = async () => {
    try { await api.post("/subscription/activation-request", { plan_id: plan, message: msg }); toast.success("Activation requested — the CIVIO team will contact you."); load(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  if (!info) return null;
  return (
    <div className="mx-auto max-w-4xl space-y-6 py-6" data-testid="trial-ended-screen">
      <div className="space-y-2">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-rose-100 text-rose-700"><Lock className="h-6 w-6" /></div>
        <h1 className="font-heading text-3xl font-bold">{info.base_state === "trial" ? "Your trial has ended" : "Your subscription has expired"}</h1>
        <p className="text-muted-foreground">{info.enterprise_name} — ended on {formatDate(info.end_date)}. All your projects and data are safe. Choose a plan and complete payment to restore full access.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {info.plans.map((p) => (
          <button key={p.id} type="button" onClick={() => setPlan(p.id)} className={`rounded-xl border p-5 text-left transition-colors ${plan === p.id ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`} data-testid={`trial-plan-${p.id}`}>
            <div className="flex items-center justify-between"><span className="font-heading text-lg font-semibold">{p.name}</span>{plan === p.id && <CheckCircle2 className="h-5 w-5 text-primary" />}</div>
            <div className="font-mono text-2xl font-bold">{formatINR(p.price_monthly)}<span className="text-sm font-normal text-muted-foreground">/{p.billing_period || "month"}</span></div>
            <p className="text-sm text-muted-foreground">{p.description}</p>
            <p className="mt-2 text-xs">{p.max_users} users · {p.max_projects} projects · {p.max_storage_mb} MB storage</p>
          </button>))}
      </div>
      <Card className="space-y-2 p-5"><div className="font-semibold">How to pay</div>
        <p className="whitespace-pre-wrap text-sm" data-testid="trial-payment-instructions">{info.payment_instructions || "Contact the CIVIO team to renew."}</p></Card>
      {info.activation_requested_at
        ? <Card className="flex items-center gap-2 border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-900" data-testid="activation-requested"><Clock className="h-4 w-4" /> Activation requested on {formatDate(info.activation_requested_at)}. We'll restore access once payment is confirmed.</Card>
        : <Card className="space-y-3 p-5"><Textarea rows={2} placeholder="Message for the CIVIO team (e.g. payment reference)" value={msg} onChange={(e) => setMsg(e.target.value)} data-testid="activation-message" />
          <Button onClick={request} data-testid="request-activation-btn">Request activation</Button></Card>}
      <Button variant="ghost" onClick={logout} data-testid="trial-logout-btn"><LogOut className="h-4 w-4" /> Sign out</Button>
    </div>
  );
}

export function SubscriptionBanner({ sub }) {
  const [hide, setHide] = useState(false);
  if (!sub || hide || sub.expired || sub.days_left == null || (sub.base_state !== "trial" && sub.days_left > 7)) return null;
  const d = sub.days_left;
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="subscription-banner">
      <span><Clock className="mr-1 inline h-4 w-4" />{sub.base_state === "trial" ? "Free trial" : "Subscription"} ends {d === 0 ? "today" : `in ${d} day${d === 1 ? "" : "s"}`} ({formatDate(sub.end_date)}). Renew to keep uninterrupted access.</span>
      <Button size="sm" variant="ghost" onClick={() => setHide(true)} data-testid="subscription-banner-close">Dismiss</Button>
    </div>
  );
}
