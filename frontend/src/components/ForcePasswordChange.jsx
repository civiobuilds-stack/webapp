import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, KeyRound } from "lucide-react";

export function ForcePasswordChange() {
  const { setUser, logout } = useAuth();
  const [f, setF] = useState({ current: "", next: "", confirm: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    if (f.next !== f.confirm) { setErr("New passwords do not match."); return; }
    setBusy(true); setErr("");
    try {
      await api.post("/auth/change-password", { current_password: f.current, new_password: f.next });
      const me = await api.get("/auth/me"); setUser(me.data);
    } catch (e) { setErr(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6" data-testid="force-password-change">
      <form onSubmit={submit} className="w-full max-w-sm animate-fade-up space-y-4 rounded-2xl border bg-card p-8 shadow-sm">
        <img src="/civio-logo.png" alt="CIVIO" className="h-8" />
        <div className="flex items-center gap-2"><KeyRound className="h-5 w-5 text-primary" /><h1 className="font-heading text-xl font-bold">Set a new password</h1></div>
        <p className="text-sm text-muted-foreground">For security, please replace your initial password before continuing. Use at least 8 characters with letters and numbers.</p>
        <div className="space-y-1.5"><Label>Current password</Label><Input type="password" value={f.current} onChange={set("current")} required data-testid="pw-current-input" /></div>
        <div className="space-y-1.5"><Label>New password</Label><Input type="password" value={f.next} onChange={set("next")} required minLength={8} data-testid="pw-new-input" /></div>
        <div className="space-y-1.5"><Label>Confirm new password</Label><Input type="password" value={f.confirm} onChange={set("confirm")} required minLength={8} data-testid="pw-confirm-input" /></div>
        {err && <p className="text-sm font-medium text-destructive" data-testid="pw-error">{err}</p>}
        <Button type="submit" className="w-full" disabled={busy} data-testid="pw-submit-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Update password"}</Button>
        <Button type="button" variant="ghost" className="w-full" onClick={logout} data-testid="pw-logout-btn">Sign out</Button>
      </form>
    </div>
  );
}
