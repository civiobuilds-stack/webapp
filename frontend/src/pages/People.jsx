import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ROLE_LABEL, isManager } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { UserPlus, Loader2, HardHat, User, Briefcase, Copy, Check } from "lucide-react";
import { toast } from "sonner";

const initials = (n) => (n || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
const ROLE_ICON = { site_engineer: HardHat, client: User, project_manager: Briefcase, admin: Briefcase };

export default function People() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => api.get("/users").then((r) => setUsers(r.data)).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  if (!isManager(user.role)) return <Navigate to="/" replace />;

  const groups = [
    { role: "project_manager", label: "Project Managers" },
    { role: "site_engineer", label: "Site Engineers" },
    { role: "client", label: "Clients" },
    { role: "admin", label: "Owners / Admins" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-heading text-3xl font-bold">People</h1>
          <p className="text-muted-foreground">Create and manage engineer and client accounts. They can then be assigned to projects.</p>
        </div>
        <AddPersonDialog isAdmin={user.role === "admin"} onCreated={load} />
      </div>

      {loading ? (
        <div className="space-y-4">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}</div>
      ) : (
        <div className="space-y-6">
          {groups.map((g) => {
            const list = users.filter((u) => u.role === g.role);
            if (!list.length) return null;
            return (
              <div key={g.role}>
                <h2 className="mb-3 flex items-center gap-2 font-heading text-lg font-semibold">
                  {g.label} <Badge variant="secondary">{list.length}</Badge>
                </h2>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {list.map((u) => {
                    const Icon = ROLE_ICON[u.role] || User;
                    return (
                      <Card key={u.id} className="flex items-center gap-3 p-4" data-testid="person-card">
                        <Avatar className="h-11 w-11"><AvatarFallback className="bg-primary/10 text-primary">{initials(u.name)}</AvatarFallback></Avatar>
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium">{u.name}</div>
                          <div className="truncate text-xs text-muted-foreground">{u.email}</div>
                          {u.phone && <div className="truncate text-xs text-muted-foreground">{u.phone}</div>}
                        </div>
                        <Badge variant="secondary" className="shrink-0"><Icon className="mr-1 h-3 w-3" /> {ROLE_LABEL[u.role]}</Badge>
                      </Card>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
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
  const [form, setForm] = useState({ name: "", email: "", phone: "", role: "site_engineer", password: genPassword() });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const reset = () => { setForm({ name: "", email: "", phone: "", role: "site_engineer", password: genPassword() }); setCreated(null); setCopied(false); };

  const submit = async () => {
    if (!form.name || !form.email) { toast.error("Name and email are required."); return; }
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
              <div className="space-y-1.5"><Label>Phone (optional)</Label><Input value={form.phone} onChange={set("phone")} /></div>
              <div className="space-y-1.5"><Label>Temporary password</Label>
                <div className="flex gap-2">
                  <Input value={form.password} onChange={set("password")} data-testid="person-password-input" />
                  <Button type="button" variant="outline" onClick={() => setForm({ ...form, password: genPassword() })}>New</Button>
                </div>
                <p className="text-xs text-muted-foreground">Share this with the person; they can sign in immediately.</p>
              </div>
            </div>
            <DialogFooter><Button onClick={submit} disabled={busy} data-testid="create-person-submit">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create account"}</Button></DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader><DialogTitle>Account ready ✅</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Share these sign-in details with <b>{created.name}</b> ({ROLE_LABEL[created.role]}).</p>
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
