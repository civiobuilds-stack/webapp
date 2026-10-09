import { Badge } from "@/components/ui/badge";
import { PROGRESS_STATUS, DEFECT_STATUS, SEVERITY } from "@/lib/format";
import { cn } from "@/lib/utils";

export function StatusBadge({ status }) {
  const c = PROGRESS_STATUS[status] || { label: status, cls: "bg-slate-100 text-slate-700 border-slate-300" };
  return (
    <Badge variant="outline" data-testid="progress-status-badge" className={cn("border font-semibold", c.cls)}>
      {c.label}
    </Badge>
  );
}

export function DefectStatusBadge({ status }) {
  const c = DEFECT_STATUS[status] || { label: status, cls: "bg-slate-100 text-slate-700 border-slate-300" };
  return (
    <Badge variant="outline" className={cn("border font-semibold", c.cls)}>{c.label}</Badge>
  );
}

export function SeverityBadge({ severity }) {
  const c = SEVERITY[severity] || SEVERITY.minor;
  return (
    <Badge data-testid="defect-severity-badge" className={cn("font-semibold", c.cls)}>{c.label}</Badge>
  );
}
