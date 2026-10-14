import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Phone, Mail } from "lucide-react";

const initials = (n) => (n || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

function Person({ p, label }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border p-3" data-testid="home-team-member">
      <Avatar className="h-10 w-10"><AvatarFallback className="bg-primary/10 text-primary">{initials(p.name)}</AvatarFallback></Avatar>
      <div className="min-w-0 flex-1"><div className="truncate font-medium">{p.name}</div><div className="text-xs text-muted-foreground">{label}</div></div>
      {p.phone && <a href={`tel:${p.phone.replace(/\s/g, "")}`} className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-50 text-emerald-700 hover:bg-emerald-100" aria-label="Call" data-testid="home-call-btn"><Phone className="h-4 w-4" /></a>}
      {p.email && <a href={`mailto:${p.email}`} className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary hover:bg-primary/20" aria-label="Email" data-testid="home-email-btn"><Mail className="h-4 w-4" /></a>}
    </div>
  );
}

export function TeamContactCard({ project }) {
  const team = [
    ...(project.project_manager ? [[project.project_manager, "Project Manager"]] : []),
    ...(project.engineers || []).map((e) => [e, "Site Engineer"]),
  ];
  return (
    <Card className="p-6" data-testid="home-team-card">
      <h2 className="font-heading text-lg font-bold">Your site team</h2>
      <p className="text-sm text-muted-foreground">Reach out anytime with questions.</p>
      <div className="mt-4 space-y-3">
        {team.length === 0 ? <p className="text-sm text-muted-foreground">Your team will be assigned soon.</p> : team.map(([p, l]) => <Person key={p.id} p={p} label={l} />)}
      </div>
    </Card>
  );
}
