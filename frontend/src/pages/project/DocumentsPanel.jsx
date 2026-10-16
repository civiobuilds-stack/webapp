import { useEffect, useRef, useState } from "react";
import { api, apiError, fileUrl } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FileUp, FileText, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";

export function DocumentsPanel({ project, canAdd, canDelete }) {
  const [docs, setDocs] = useState([]);
  const [f, setF] = useState({ title: "", category: "drawing" });
  const [busy, setBusy] = useState(false);
  const ref = useRef();
  const load = () => api.get(`/projects/${project.id}/documents`).then((r) => setDocs(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [project.id]);
  const upload = async (file) => {
    if (!file) return;
    if (!f.title.trim()) { toast.error("Enter a title first"); return; }
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file); fd.append("project_id", project.id); fd.append("caption", f.title);
      const { data } = await api.post("/files/upload", fd);
      await api.post(`/projects/${project.id}/documents`, { file_id: data.id, title: f.title, category: f.category });
      toast.success("Saved to project"); setF({ ...f, title: "" }); load();
    } catch (e) { toast.error(apiError(e.response?.data?.detail)); } finally { setBusy(false); if (ref.current) ref.current.value = ""; }
  };
  const del = async (id) => { try { await api.delete(`/documents/${id}`); load(); } catch (e) { toast.error(apiError(e.response?.data?.detail)); } };
  return (
    <Card className="space-y-3 p-5" data-testid="documents-panel">
      <h3 className="font-heading font-semibold">Drawings & documents</h3>
      {canAdd && <div className="flex flex-wrap gap-2">
        <Input className="w-56" placeholder="Title, e.g. Ground floor plan" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="doc-title-input" />
        <Select value={f.category} onValueChange={(v) => setF({ ...f, category: v })}><SelectTrigger className="w-36" data-testid="doc-category-select"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="drawing">Drawing</SelectItem><SelectItem value="document">Document</SelectItem></SelectContent></Select>
        <input ref={ref} type="file" accept="image/*,application/pdf,.dwg,.doc,.docx,.xls,.xlsx" className="hidden" onChange={(e) => upload(e.target.files[0])} data-testid="doc-file-input" />
        <Button variant="outline" onClick={() => ref.current.click()} disabled={busy} data-testid="doc-upload-btn">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />} Upload</Button>
      </div>}
      {docs.length === 0 ? <p className="text-sm text-muted-foreground">No drawings or documents yet.</p> : <div className="divide-y">{docs.map((d) => (
        <div key={d.id} className="flex items-center justify-between gap-2 py-2" data-testid="doc-row">
          <a href={fileUrl(d.file_id)} target="_blank" rel="noreferrer" className="flex min-w-0 items-center gap-2 text-sm hover:underline"><FileText className="h-4 w-4 shrink-0" />
            <span className="truncate">{d.title}</span><Badge variant="secondary" className="capitalize">{d.category}</Badge></a>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">{d.uploaded_by_name} · {formatDate(d.created_at)}
            {canDelete && <Button size="sm" variant="ghost" onClick={() => del(d.id)} data-testid="doc-delete-btn"><Trash2 className="h-3.5 w-3.5" /></Button>}</div>
        </div>))}</div>}
    </Card>
  );
}
