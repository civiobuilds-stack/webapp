import { PushCard } from "@/components/PushCard";
import { useEffect, useState } from "react";
import { BrandLoader } from "@/components/BrandLoader";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Bell, CheckCheck, ClipboardCheck, AlertTriangle, UserPlus, FileCheck, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

const ICON = {
  review_required: ClipboardCheck, client_decision: ClipboardCheck, decision: FileCheck,
  defect: AlertTriangle, assignment: UserPlus, returned: ClipboardCheck, project: Inbox,
};

export default function Notifications() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => api.get("/notifications").then((r) => setItems(r.data.items)).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const markRead = async (n) => {
    if (!n.read) { await api.post(`/notifications/${n.id}/read`); }
    if (n.project_id) navigate(`/projects/${n.project_id}`);
    else load();
  };
  const markAll = async () => { await api.post("/notifications/read-all"); load(); };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="font-heading text-3xl font-bold">Notifications</h1><p className="text-muted-foreground">Updates across your projects.</p></div>
        <Button variant="outline" onClick={markAll} data-testid="mark-all-read-btn"><CheckCheck className="h-4 w-4" /> Mark all read</Button>
      </div>

      <PushCard />

      {loading ? (
        <BrandLoader fullScreen={false} />
      ) : items.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-12 text-center text-muted-foreground"><Bell className="h-8 w-8" />You're all caught up.</Card>
      ) : (
        <div className="space-y-2">
          {items.map((n) => {
            const Icon = ICON[n.type] || Bell;
            return (
              <button key={n.id} onClick={() => markRead(n)} data-testid="notification-item"
                className={cn("flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-colors hover:bg-muted/50", !n.read && "border-primary/30 bg-primary/5")}>
                <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", n.type === "defect" ? "bg-rose-100 text-rose-600" : "bg-primary/10 text-primary")}><Icon className="h-4 w-4" /></div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{n.message}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{formatDateTime(n.created_at)}</p>
                </div>
                {!n.read && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-primary" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
