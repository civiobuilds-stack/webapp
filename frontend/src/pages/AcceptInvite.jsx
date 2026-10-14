import { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { api, apiError, setToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ROLE_LABEL } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Building2, XCircle } from "lucide-react";
import { BrandLoader } from "@/components/BrandLoader";

export default function AcceptInvite() {
  const { token } = useParams();
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ name: "", phone: "", password: "", confirm: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/invites/token/${token}`)
      .then((r) => { setInfo(r.data); setForm((f) => ({ ...f, name: r.data.name, phone: r.data.phone || "" })); })
      .catch((e) => setInfo({ invalid: apiError(e.response?.data?.detail) }));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (form.password !== form.confirm) { setErr("Passwords do not match."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post(`/invites/token/${token}/accept`, { name: form.name, phone: form.phone, password: form.password });
      setToken(data.access_token);
      const me = await api.get("/auth/me");
      setUser(me.data);
      navigate("/");
    } catch (e) { setErr(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  if (!info) return <BrandLoader />;
  if (info.invalid) return (
    <div className="flex min-h-screen items-center justify-center p-6" data-testid="invite-invalid">
      <div className="max-w-sm text-center"><XCircle className="mx-auto h-10 w-10 text-rose-500" />
        <h1 className="mt-3 font-heading text-xl font-bold">Invite unavailable</h1>
        <p className="mt-1 text-sm text-muted-foreground">{info.invalid}</p>
        <Link to="/login" className="mt-4 inline-block font-semibold text-primary">Go to sign in</Link></div>
    </div>
  );
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm animate-fade-up" data-testid="accept-invite-page">
        <img src="/civio-logo.png" alt="CIVIO" className="h-9" />
        <div className="mt-6 flex items-center gap-3 rounded-xl border bg-card p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><Building2 className="h-5 w-5" /></div>
          <div><div className="text-xs text-muted-foreground">You're invited to join</div>
            <div className="font-heading font-bold" data-testid="invite-company">{info.company}</div>
            <div className="text-xs text-muted-foreground">as {ROLE_LABEL[info.role]}</div></div>
        </div>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <div className="space-y-1.5"><Label>Email</Label><Input value={info.email} disabled data-testid="invite-email" /></div>
          <div className="space-y-1.5"><Label>Full name</Label><Input value={form.name} onChange={set("name")} required data-testid="invite-name-input" /></div>
          <div className="space-y-1.5"><Label>Phone number</Label><Input type="tel" value={form.phone} onChange={set("phone")} required minLength={6} placeholder="+91 ..." data-testid="invite-phone-input" /></div>
          <div className="space-y-1.5"><Label>Create password</Label><Input type="password" value={form.password} onChange={set("password")} required minLength={6} data-testid="invite-password-input" /></div>
          <div className="space-y-1.5"><Label>Confirm password</Label><Input type="password" value={form.confirm} onChange={set("confirm")} required minLength={6} data-testid="invite-confirm-input" /></div>
          {err && <p className="text-sm font-medium text-destructive" data-testid="invite-error">{err}</p>}
          <Button type="submit" className="w-full" disabled={busy} data-testid="invite-accept-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Join workspace"}</Button>
        </form>
      </div>
    </div>
  );
}
