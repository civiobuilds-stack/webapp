import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollText } from "lucide-react";

export function AuditTab({ project }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { api.get(`/projects/${project.id}/audit-log`).then((r) => setLogs(r.data)).catch(() => {}).finally(() => setLoading(false)); }, [project.id]);

  if (loading) return <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)}</div>;

  return (
    <div className="space-y-4">
      <h3 className="font-heading text-lg font-semibold">Audit log</h3>
      {logs.length === 0 ? <Card className="p-10 text-center text-muted-foreground">No activity recorded.</Card> : (
        <Card className="divide-y p-0">
          {logs.map((l) => (
            <div key={l.id} className="flex items-start gap-3 p-4" data-testid="audit-entry">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted"><ScrollText className="h-4 w-4 text-muted-foreground" /></div>
              <div className="min-w-0 flex-1">
                <p className="text-sm"><span className="font-semibold">{l.actor_name}</span> {l.action} {l.details && <span className="text-muted-foreground">· {l.details}</span>}</p>
                <p className="text-xs text-muted-foreground">{formatDateTime(l.created_at)}</p>
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
