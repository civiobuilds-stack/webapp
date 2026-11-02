import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { openPath } from "@/components/AuthImage";
import { useAuth } from "@/context/AuthContext";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollText, Download } from "lucide-react";

export function AuditTab({ project }) {
  const { user } = useAuth();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { api.get(`/projects/${project.id}/audit-log`).then((r) => setLogs(r.data)).catch(() => {}).finally(() => setLoading(false)); }, [project.id]);


  if (loading) return <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-heading text-lg font-semibold">Audit log</h3>
        {user.role === "admin" && (
          <a href="#" onClick={(e) => { e.preventDefault(); openPath(`/projects/${project.id}/audit-log/export`); }} data-testid="export-audit-csv-btn">
            <Button variant="outline" size="sm"><Download className="h-4 w-4" /> Export CSV</Button>
          </a>
        )}
      </div>
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
