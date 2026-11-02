import { useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, apiError, API, getToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, Upload, Trash2, ImageIcon } from "lucide-react";
import { toast } from "sonner";
import { DigestSettingsCard } from "@/components/DigestSettingsCard";
import { LabourCostSettings } from "@/components/LabourCostSettings";
import { BrandLoader } from "@/components/BrandLoader";
import { AuthImage } from "@/components/AuthImage";

const FIELDS = [
  ["display_name", "Company name (shown on reports)"], ["tagline", "Tagline"], ["contact_email", "Contact email"],
  ["contact_phone", "Contact phone"], ["website", "Website"], ["address", "Address"],
];

function LogoCard({ hasLogo, onChange }) {
  const ref = useRef();
  const [busy, setBusy] = useState(false);
  const [v, setV] = useState(Date.now());
  const upload = async (file) => {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    setBusy(true);
    try { await api.post("/enterprise/logo", fd); toast.success("Logo updated"); setV(Date.now()); onChange(true); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); ref.current.value = ""; }
  };
  const remove = async () => { await api.delete("/enterprise/logo"); onChange(false); toast.success("Logo removed"); };
  return (
    <Card className="p-6" data-testid="logo-card">
      <h3 className="font-heading font-bold">Company logo</h3>
      <p className="text-sm text-muted-foreground">Appears on PDF reports and in your workspace. PNG or JPG, under 2 MB.</p>
      <div className="mt-4 flex items-center gap-4">
        <div className="flex h-24 w-24 items-center justify-center overflow-hidden rounded-xl border bg-muted/40">
          {hasLogo ? <AuthImage viewer={false} path={`/enterprise/logo?v=${v}`} alt="Company logo" className="h-full w-full object-contain p-1" data-testid="logo-preview" />
            : <ImageIcon className="h-8 w-8 text-muted-foreground" />}
        </div>
        <div className="flex flex-col gap-2">
          <input ref={ref} type="file" accept="image/png,image/jpeg" className="hidden" onChange={(e) => upload(e.target.files[0])} data-testid="logo-file-input" />
          <Button variant="outline" onClick={() => ref.current.click()} disabled={busy} data-testid="upload-logo-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload logo</Button>
          {hasLogo && <Button variant="ghost" className="text-rose-600" onClick={remove} data-testid="remove-logo-btn"><Trash2 className="h-4 w-4" /> Remove</Button>}
        </div>
      </div>
    </Card>
  );
}

export default function CompanySettings() {
  const { user, setUser } = useAuth();
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/enterprise/settings").then((r) => setS(r.data)); }, []);
  if (user.role !== "admin") return <Navigate to="/" replace />;
  if (!s) return <BrandLoader fullScreen={false} />;
  const refreshMe = () => api.get("/auth/me").then((r) => setUser(r.data));
  const save = async () => {
    setBusy(true);
    try {
      const body = {}; FIELDS.forEach(([k]) => { body[k] = s[k] || ""; });
      await api.put("/enterprise/settings", body); toast.success("Company settings saved"); refreshMe();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <div className="max-w-3xl space-y-6" data-testid="company-settings-page">
      <div>
        <h1 className="font-heading text-3xl font-bold">Company Settings</h1>
        <div className="text-muted-foreground">Your brand on every report. <Badge variant="outline" className="ml-1 capitalize">{s.business_type} workspace</Badge></div>
      </div>
      <LogoCard hasLogo={s.has_logo} onChange={(v) => { setS({ ...s, has_logo: v }); refreshMe(); }} />
      {s.business_type === "commercial" && <><DigestSettingsCard /><LabourCostSettings /></>}
      <Card className="space-y-4 p-6">
        <h3 className="font-heading font-bold">Company details</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          {FIELDS.map(([k, l]) => (
            <div key={k} className={`space-y-1.5 ${k === "address" ? "sm:col-span-2" : ""}`}><Label>{l}</Label>
              <Input value={s[k] || ""} onChange={(e) => setS({ ...s, [k]: e.target.value })} data-testid={`settings-${k}`} /></div>
          ))}
        </div>
        <Button onClick={save} disabled={busy || (s.display_name || "").trim().length < 2} data-testid="save-settings-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save changes"}</Button>
      </Card>
    </div>
  );
}
