import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { enablePush, disablePush, pushSupported } from "@/lib/push";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BellRing, Loader2 } from "lucide-react";
import { toast } from "sonner";

export function PushCard() {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/push/status").then((r) => setSt(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const run = async (fn, ok) => {
    setBusy(true);
    try { await fn(); toast.success(ok); load(); } catch (e) { toast.error(e.message || apiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const granted = pushSupported() && Notification.permission === "granted";
  return (
    <Card className="p-5" data-testid="push-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3"><BellRing className="h-5 w-5 text-primary" />
          <div><div className="font-semibold">Push notifications on this device</div>
            <div className="text-xs text-muted-foreground">Approvals and site updates only · {st?.devices ?? 0} device(s) registered</div></div></div>
        <div className="flex gap-2">
          {!granted ? <Button size="sm" disabled={busy} onClick={() => run(enablePush, "Push enabled on this device")} data-testid="enable-push-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Enable"}</Button>
            : <>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.post("/push/test"), "Test sent")} data-testid="test-push-btn">Send test</Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(disablePush, "Push disabled on this device")} data-testid="disable-push-btn">Disable</Button>
            </>}
        </div>
      </div>
      {st?.recent?.length > 0 && <p className="mt-2 text-xs text-muted-foreground" data-testid="push-last-status">Last delivery: {st.recent[0].status} · {formatDateTime(st.recent[0].created_at)}</p>}
    </Card>
  );
}
