import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth, apiError } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { HardHat, Loader2 } from "lucide-react";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "client" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try { await register(form); navigate("/"); }
    catch (e) { setErr(apiError(e.response?.data?.detail) || e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm animate-fade-up">
        <div className="mb-6 flex items-center gap-2"><HardHat className="h-6 w-6 text-primary" /><span className="font-heading text-xl font-extrabold">CIVIO BUILD</span></div>
        <h2 className="font-heading text-2xl font-bold">Create your account</h2>
        <p className="mt-1 text-sm text-muted-foreground">For clients and site engineers. PMs are added by an admin.</p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div className="space-y-1.5"><Label>Full name</Label>
            <Input value={form.name} onChange={set("name")} required data-testid="register-name-input" /></div>
          <div className="space-y-1.5"><Label>Email</Label>
            <Input type="email" value={form.email} onChange={set("email")} required data-testid="register-email-input" /></div>
          <div className="space-y-1.5"><Label>Password</Label>
            <Input type="password" value={form.password} onChange={set("password")} required minLength={6} data-testid="register-password-input" /></div>
          <div className="space-y-1.5"><Label>I am a</Label>
            <RadioGroup value={form.role} onValueChange={(v) => setForm({ ...form, role: v })} className="grid grid-cols-2 gap-2">
              {[["client", "Client"], ["site_engineer", "Site Engineer"]].map(([v, l]) => (
                <label key={v} className="flex cursor-pointer items-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary/5" data-testid={`register-role-${v}`}>
                  <RadioGroupItem value={v} /> {l}
                </label>
              ))}
            </RadioGroup>
          </div>
          {err && <p className="text-sm font-medium text-destructive" data-testid="register-error">{err}</p>}
          <Button type="submit" className="w-full" disabled={busy} data-testid="register-submit-btn">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create account"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-muted-foreground">
          Already have an account? <Link to="/login" className="font-semibold text-primary hover:underline" data-testid="goto-login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
