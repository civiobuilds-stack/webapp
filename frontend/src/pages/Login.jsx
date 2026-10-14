import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth, apiError } from "@/context/AuthContext";
import OtpVerify from "@/components/OtpVerify";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { HardHat, Loader2 } from "lucide-react";

const DEMO = [
  { label: "Owner / Admin", email: "civiobuilds@gmail.com", password: "CivioAdmin@2026" },
  { label: "Project Manager", email: "pm@civio.build", password: "CivioPM@2026" },
  { label: "Site Engineer", email: "engineer@civio.build", password: "CivioEng@2026" },
  { label: "Client", email: "client@civio.build", password: "CivioClient@2026" },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("login");
  const [pendingEmail, setPendingEmail] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try { const u = await login(email, password); navigate(u.platform_role === "super_admin" ? "/superadmin" : "/"); }
    catch (e) {
      const d = e.response?.data?.detail;
      if (e.response?.status === 403 && d?.code === "email_not_verified") {
        setPendingEmail(d.email || email.toLowerCase());
        setStage("otp");
      } else { setErr(apiError(d) || e.message); }
    }
    finally { setBusy(false); }
  };

  if (stage === "otp") return <OtpVerify email={pendingEmail} onVerified={() => navigate("/")} />;

  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const googleLogin = () => {
    const redirectUrl = window.location.origin + "/";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-[hsl(222_60%_11%)] p-12 lg:flex">
        <img src="https://images.unsplash.com/photo-1588543087280-2e13d9e5c391?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"
          alt="site" className="absolute inset-0 h-full w-full object-cover opacity-20" />
        <div className="relative flex items-center gap-3 text-white">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/95 p-1.5"><img src="/civio-icon.png" alt="CIVIO" className="h-full w-full object-contain" /></div>
          <div><div className="font-heading text-2xl font-extrabold tracking-tight">CIVIO</div>
            <div className="text-xs uppercase tracking-widest text-white/50">Your Build, Our Expertise</div></div>
        </div>
        <div className="relative text-white">
          <h1 className="font-heading text-4xl font-bold leading-tight">Construction project management, from initiation to handover.</h1>
          <p className="mt-4 max-w-md text-white/70">Connect project managers, site engineers and clients on one transparent, database-backed platform.</p>
        </div>
        <div className="relative text-xs text-white/40">© 2026 Civio Project Management Consultancy</div>
      </div>

      <div className="flex items-center justify-center bg-background p-6">
        <div className="w-full max-w-sm animate-fade-up">
          <div className="mb-8 lg:hidden"><img src="/civio-logo.png" alt="CIVIO" className="h-10" /></div>
          <h2 className="font-heading text-2xl font-bold">Welcome back</h2>
          <p className="mt-1 text-sm text-muted-foreground">Sign in to your Civio workspace.</p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="login-email-input" placeholder="you@company.com" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="login-password-input" placeholder="••••••••" />
            </div>
            {err && <p className="text-sm font-medium text-destructive" data-testid="login-error">{err}</p>}
            <Button type="submit" className="w-full" disabled={busy} data-testid="login-submit-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign in"}
            </Button>
          </form>

          <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px flex-1 bg-border" /> OR <span className="h-px flex-1 bg-border" />
          </div>
          <Button type="button" variant="outline" className="w-full" onClick={googleLogin} data-testid="google-login-btn">
            <svg className="h-4 w-4" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.76h3.57c2.08-1.92 3.28-4.74 3.28-8.09Z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.76c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"/><path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.22V7.04H2.18a11 11 0 0 0 0 9.9l3.66-2.84Z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.04l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38Z"/></svg>
            Continue with Google
          </Button>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            New company? <Link to="/register" className="font-semibold text-primary hover:underline" data-testid="goto-register">Register your workspace</Link>
          </p>

          <div className="mt-8 rounded-xl border bg-muted/40 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Demo accounts (click to fill)</p>
            <div className="grid grid-cols-2 gap-2">
              {DEMO.map((d) => (
                <button key={d.email} type="button" onClick={() => { setEmail(d.email); setPassword(d.password); }}
                  data-testid={`demo-${d.label.split(" ")[0].toLowerCase()}`}
                  className="rounded-lg border bg-card px-2.5 py-2 text-left text-xs transition-colors hover:border-primary">
                  <div className="font-semibold text-foreground">{d.label}</div>
                  <div className="truncate text-muted-foreground">{d.email}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
