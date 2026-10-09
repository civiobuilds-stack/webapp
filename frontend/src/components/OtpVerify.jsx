import { useState, useRef } from "react";
import { useAuth, apiError } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Loader2, MailCheck } from "lucide-react";
import { toast } from "sonner";

export default function OtpVerify({ email, onVerified }) {
  const { verifyOtp, resendOtp } = useAuth();
  const [digits, setDigits] = useState(["", "", "", "", "", ""]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const refs = useRef([]);

  const code = digits.join("");

  const setDigit = (i, v) => {
    const c = v.replace(/\D/g, "").slice(-1);
    const next = [...digits];
    next[i] = c;
    setDigits(next);
    if (c && i < 5) refs.current[i + 1]?.focus();
  };

  const onKey = (i, e) => {
    if (e.key === "Backspace" && !digits[i] && i > 0) refs.current[i - 1]?.focus();
  };

  const onPaste = (e) => {
    const txt = (e.clipboardData.getData("text") || "").replace(/\D/g, "").slice(0, 6);
    if (txt) { setDigits(txt.padEnd(6, "").split("").slice(0, 6).map((c) => c || "")); e.preventDefault(); }
  };

  const verify = async (e) => {
    e?.preventDefault();
    if (code.length !== 6) { setErr("Enter the 6-digit code."); return; }
    setErr(""); setBusy(true);
    try { await verifyOtp(email, code); onVerified(); }
    catch (ex) { setErr(apiError(ex.response?.data?.detail) || "Verification failed."); }
    finally { setBusy(false); }
  };

  const resend = async () => {
    if (cooldown > 0) return;
    try {
      await resendOtp(email);
      toast.success("A new code has been emailed.");
      setCooldown(30);
      const t = setInterval(() => setCooldown((c) => { if (c <= 1) { clearInterval(t); return 0; } return c - 1; }), 1000);
    } catch (ex) { toast.error(apiError(ex.response?.data?.detail)); }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm animate-fade-up text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <MailCheck className="h-7 w-7" />
        </div>
        <h2 className="font-heading text-2xl font-bold">Verify your email</h2>
        <p className="mt-1 text-sm text-muted-foreground">We emailed a 6-digit code to <b>{email}</b>. Enter it below to activate your account.</p>

        <form onSubmit={verify} className="mt-6 space-y-4">
          <div className="flex justify-center gap-2" onPaste={onPaste}>
            {digits.map((d, i) => (
              <input
                key={i}
                ref={(el) => (refs.current[i] = el)}
                value={d}
                onChange={(e) => setDigit(i, e.target.value)}
                onKeyDown={(e) => onKey(i, e)}
                inputMode="numeric"
                maxLength={1}
                data-testid={`otp-digit-${i}`}
                className="h-12 w-11 rounded-xl border border-input bg-card text-center font-mono text-xl font-bold outline-none focus:border-primary focus:ring-2 focus:ring-ring/40"
              />
            ))}
          </div>
          {err && <p className="text-sm font-medium text-destructive" data-testid="otp-error">{err}</p>}
          <Button type="submit" className="w-full" disabled={busy} data-testid="otp-verify-btn">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Verify & continue"}
          </Button>
        </form>

        <p className="mt-4 text-sm text-muted-foreground">
          Didn't get it?{" "}
          <button onClick={resend} disabled={cooldown > 0} data-testid="otp-resend-btn"
            className="font-semibold text-primary hover:underline disabled:opacity-50">
            {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
          </button>
        </p>
      </div>
    </div>
  );
}
