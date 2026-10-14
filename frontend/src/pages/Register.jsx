import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth, apiError } from "@/context/AuthContext";
import OtpVerify from "@/components/OtpVerify";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Home, Building2, Check } from "lucide-react";
import { cn } from "@/lib/utils";

const TYPES = [
  { v: "residential", label: "Residential Construction", desc: "Homes, villas, apartments — client-focused progress & approvals.", icon: Home },
  { v: "commercial", label: "Commercial Construction", desc: "Offices, retail, industrial — full procurement & cost control.", icon: Building2 },
];

function TypePicker({ value, onChange }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {TYPES.map((t) => (
        <button type="button" key={t.v} onClick={() => onChange(t.v)} data-testid={`register-type-${t.v}`}
          className={cn("relative rounded-xl border bg-card p-3 text-left transition-colors hover:border-primary/60",
            value === t.v && "border-primary bg-primary/5 ring-1 ring-primary")}>
          {value === t.v && <Check className="absolute right-2 top-2 h-4 w-4 text-primary" />}
          <t.icon className="h-5 w-5 text-primary" />
          <div className="mt-2 text-sm font-semibold">{t.label}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{t.desc}</div>
        </button>
      ))}
    </div>
  );
}

export default function Register() {
  const { registerEnterprise } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ company_name: "", business_type: "", city: "", name: "", email: "", phone: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("form");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (!form.business_type) { setErr("Please choose your business type."); return; }
    if ((form.phone || "").trim().length < 6) { setErr("Please enter a valid phone number."); return; }
    setErr(""); setBusy(true);
    try { await registerEnterprise(form); setStage("otp"); }
    catch (e) { setErr(apiError(e.response?.data?.detail) || e.message); }
    finally { setBusy(false); }
  };

  if (stage === "otp") return <OtpVerify email={form.email.toLowerCase()} onVerified={() => navigate("/")} />;

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-lg animate-fade-up">
        <div className="mb-6"><img src="/civio-logo.png" alt="CIVIO" className="h-9" /></div>
        <h2 className="font-heading text-2xl font-bold">Register your company</h2>
        <p className="mt-1 text-sm text-muted-foreground">Create a CIVIO workspace. Our team reviews every registration before activation.</p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div className="space-y-1.5"><Label>Business type</Label><TypePicker value={form.business_type} onChange={(v) => setForm({ ...form, business_type: v })} /></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Company name</Label>
              <Input value={form.company_name} onChange={set("company_name")} required data-testid="register-company-input" /></div>
            <div className="space-y-1.5"><Label>City</Label>
              <Input value={form.city} onChange={set("city")} data-testid="register-city-input" /></div>
            <div className="space-y-1.5"><Label>Your full name</Label>
              <Input value={form.name} onChange={set("name")} required data-testid="register-name-input" /></div>
            <div className="space-y-1.5"><Label>Phone number</Label>
              <Input type="tel" value={form.phone} onChange={set("phone")} required placeholder="+91 ..." data-testid="register-phone-input" /></div>
            <div className="space-y-1.5"><Label>Work email</Label>
              <Input type="email" value={form.email} onChange={set("email")} required data-testid="register-email-input" /></div>
            <div className="space-y-1.5"><Label>Password</Label>
              <Input type="password" value={form.password} onChange={set("password")} required minLength={6} data-testid="register-password-input" /></div>
          </div>
          {err && <p className="text-sm font-medium text-destructive" data-testid="register-error">{err}</p>}
          <Button type="submit" className="w-full" disabled={busy} data-testid="register-submit-btn">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Register company"}
          </Button>
        </form>
        <p className="mt-4 text-center text-xs text-muted-foreground">Engineers & clients: ask your company admin to invite you.</p>
        <p className="mt-2 text-center text-sm text-muted-foreground">
          Already have an account? <Link to="/login" className="font-semibold text-primary hover:underline" data-testid="goto-login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
