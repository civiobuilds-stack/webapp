import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Clock, XCircle, PauseCircle, RefreshCw, LogOut } from "lucide-react";

const COPY = {
  pending: { icon: Clock, tone: "text-amber-600 bg-amber-50", title: "Your workspace is under review",
    body: "Thanks for registering! Our team is verifying your company. You'll get an email as soon as it's approved." },
  rejected: { icon: XCircle, tone: "text-rose-600 bg-rose-50", title: "Registration not approved",
    body: "Unfortunately your workspace registration was not approved." },
  suspended: { icon: PauseCircle, tone: "text-slate-700 bg-slate-100", title: "Workspace suspended",
    body: "Access to this workspace has been paused. Please contact CIVIO support." },
};

export function PendingWorkspace() {
  const { user, setUser, logout } = useAuth();
  const ent = user.enterprise || {};
  const c = COPY[ent.status] || COPY.pending;
  const refresh = () => api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {});
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6" data-testid="pending-workspace">
      <div className="w-full max-w-md animate-fade-up rounded-2xl border bg-card p-8 text-center shadow-sm">
        <img src="/civio-logo.png" alt="CIVIO" className="mx-auto h-8" />
        <div className={`mx-auto mt-6 flex h-14 w-14 items-center justify-center rounded-full ${c.tone}`}><c.icon className="h-7 w-7" /></div>
        <h1 className="mt-4 font-heading text-xl font-bold" data-testid="pending-workspace-title">{c.title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{c.body}</p>
        {ent.status_reason && <p className="mt-3 rounded-lg bg-muted p-3 text-sm" data-testid="pending-workspace-reason">Reason: {ent.status_reason}</p>}
        <div className="mt-4 rounded-lg border p-3 text-left text-sm">
          <div className="font-semibold">{ent.name}</div>
          <div className="text-xs capitalize text-muted-foreground">{ent.business_type} construction · status: <span data-testid="pending-workspace-status">{ent.status}</span></div>
        </div>
        <div className="mt-6 flex gap-2">
          <Button variant="outline" className="flex-1" onClick={refresh} data-testid="pending-refresh-btn"><RefreshCw className="h-4 w-4" /> Check status</Button>
          <Button variant="ghost" className="flex-1" onClick={logout} data-testid="pending-logout-btn"><LogOut className="h-4 w-4" /> Sign out</Button>
        </div>
      </div>
    </div>
  );
}
