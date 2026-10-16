import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { BrandLoader } from "@/components/BrandLoader";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ROLE_LABEL, isManager } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { UserPlus, Loader2, HardHat, User, Briefcase, Copy, Check } from "lucide-react";
import { toast } from "sonner";
import { InviteDialog, InviteList } from "@/components/InvitePanel";
import { EmployeesPanel } from "@/components/EmployeesPanel";
import { AccountsPanel } from "@/components/AccountsPanel";


export default function People() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [inviteKey, setInviteKey] = useState(0);

  const load = () => api.get("/users").then((r) => setUsers(r.data)).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  if (!isManager(user.role)) return <Navigate to="/" replace />;


  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold">People</h1>
          <p className="text-muted-foreground">Create and manage engineer and client accounts. They can then be assigned to projects.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <InviteDialog isAdmin={user.role === "admin"} onSent={() => setInviteKey((k) => k + 1)} />
          <AddPersonDialog isAdmin={user.role === "admin"} onCreated={load} />
        </div>
      </div>

      <InviteList refreshKey={inviteKey} />
      {(user.enterprise?.modules || []).includes("dpr") && <EmployeesPanel isAdmin={user.role === "admin"} refreshKey={users.length} />}

      {loading ? <BrandLoader fullScreen={false} /> : <AccountsPanel users={users} me={user} onChanged={load} />}
    </div>
  );
}

function genPassword() {
  const words = ["Build", "Civio", "Site", "Steel", "Brick", "Crane"];
  return words[Math.floor(Math.random() * words.length)] + "@" + Math.floor(1000 + Math.random() * 9000);
}

function AddPersonDialog({ isAdmin, onCreated }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(null);
  const [copied, setCopied] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", role: "site_engineer", password: genPassword(), job_title: "", job_description: "" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const reset = () => { setForm({ name: "", email: "", phone: "", role: "site_engineer", password: genPassword(), job_title: "", job_description: "" }); setCreated(null); setCopied(false); };

  const submit = async () => {
    if (!form.name || !form.email) { toast.error("Name and email are required."); return; }
    if ((form.phone || "").trim().length < 6) { toast.error("A phone number is required."); return; }
    setBusy(true);
    try {
      await api.post("/users", form);
      setCreated({ email: form.email, password: form.password, role: form.role, name: form.name });
      toast.success("Account created");
      onCreated();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const copyCreds = () => {
    navigator.clipboard?.writeText(`Email: ${created.email}\nPassword: ${created.password}`);
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };

  const roles = [
    { v: "site_engineer", l: "Site Engineer", icon: HardHat },
    { v: "client", l: "Client", icon: User },
    ...(isAdmin ? [{ v: "project_manager", l: "Project Manager", icon: Briefcase }] : []),
  ];

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset(); }}>
      <DialogTrigger asChild><Button data-testid="add-person-btn"><UserPlus className="h-4 w-4" /> Add person</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        {!created ? (
          <>
            <DialogHeader><DialogTitle>Create an account</DialogTitle></DialogHeader>
            <div className="space-y-4">
              <div className="space-y-1.5"><Label>Role</Label>
                <RadioGroup value={form.role} onValueChange={(v) => setForm({ ...form, role: v })} className={`grid gap-2 ${roles.length === 3 ? "grid-cols-3" : "grid-cols-2"}`}>
                  {roles.map((r) => (
                    <label key={r.v} className="flex cursor-pointer flex-col items-center gap-1 rounded-lg border bg-card px-2 py-3 text-center text-xs has-[:checked]:border-primary has-[:checked]:bg-primary/5" data-testid={`person-role-${r.v}`}>
                      <RadioGroupItem value={r.v} className="sr-only" />
                      <r.icon className="h-5 w-5" /> {r.l}
                    </label>
                  ))}
                </RadioGroup>
              </div>
              <div className="space-y-1.5"><Label>Full name</Label><Input value={form.name} onChange={set("name")} data-testid="person-name-input" /></div>
              <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={form.email} onChange={set("email")} data-testid="person-email-input" /></div>
              <div className="space-y-1.5"><Label>Phone number</Label><Input value={form.phone} onChange={set("phone")} required placeholder="+91 ..." data-testid="person-phone-input" /></div>
              <div className="grid grid-cols-2 gap-3"><div className="space-y-1.5"><Label>Job role</Label><Input value={form.job_title} onChange={set("job_title")} placeholder="e.g. Site supervisor" data-testid="person-job-title-input" /></div>
                <div className="space-y-1.5"><Label>Job description</Label><Input value={form.job_description} onChange={set("job_description")} data-testid="person-job-desc-input" /></div></div>
              <div className="space-y-1.5"><Label>Password</Label>
                <div className="flex gap-2">
                  <Input value={form.password} onChange={set("password")} data-testid="person-password-input" />
                  <Button type="button" variant="outline" onClick={() => setForm({ ...form, password: genPassword() })}>New</Button>
                </div>
              <p className="text-xs text-muted-foreground">They sign in directly with this email and password — no verification code.</p>
              </div>
            </div>
            <DialogFooter><Button onClick={submit} disabled={busy} data-testid="create-person-submit">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create account"}</Button></DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader><DialogTitle>Account ready ✅</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Share these sign-in details with <b>{created.name}</b> ({ROLE_LABEL[created.role]}). They can sign in right away. This password is shown only now.</p>
              <div className="rounded-xl border bg-muted/40 p-4 font-mono text-sm" data-testid="created-credentials">
                <div><span className="text-muted-foreground">Email:</span> {created.email}</div>
                <div><span className="text-muted-foreground">Password:</span> {created.password}</div>
              </div>
              <Button variant="outline" className="w-full" onClick={copyCreds} data-testid="copy-credentials-btn">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} {copied ? "Copied" : "Copy credentials"}
              </Button>
            </div>
            <DialogFooter className="gap-2 sm:gap-2">
              <Button variant="outline" onClick={reset} data-testid="add-another-btn">Add another</Button>
              <Button onClick={() => { setOpen(false); reset(); }} data-testid="done-person-btn">Done</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
