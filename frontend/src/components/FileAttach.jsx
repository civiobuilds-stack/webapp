import { useState } from "react";
import { api, apiError, fileUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Loader2, Paperclip, X } from "lucide-react";
import { toast } from "sonner";

export async function uploadToProject(projectId, file) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("project_id", projectId);
  const { data } = await api.post("/files/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
  return data;
}

export function FileAttach({ projectId, value = [], onChange, multiple = true, accept = "image/*,application/pdf", testid = "file-attach" }) {
  const [busy, setBusy] = useState(false);
  const [names, setNames] = useState({});
  const handle = async (e) => {
    const files = Array.from(e.target.files || []);
    setBusy(true);
    const ids = multiple ? [...value] : [];
    const nm = { ...names };
    for (const f of files) {
      try { const d = await uploadToProject(projectId, f); ids.push(d.id); nm[d.id] = f.name; }
      catch (err) { toast.error(apiError(err.response?.data?.detail)); }
    }
    setNames(nm); onChange(ids); setBusy(false); e.target.value = "";
  };
  return (
    <div className="space-y-2">
      <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm hover:bg-muted" data-testid={`${testid}-label`}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />} {busy ? "Uploading…" : "Attach file (PDF / image)"}
        <input type="file" className="hidden" accept={accept} multiple={multiple} onChange={handle} data-testid={`${testid}-input`} />
      </label>
      {value.length > 0 && <div className="flex flex-wrap gap-2">{value.map((id) => (
        <span key={id} className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs">
          <a href={fileUrl(id)} target="_blank" rel="noreferrer" className="underline">{names[id] || "attachment"}</a>
          <Button type="button" size="icon" variant="ghost" className="h-4 w-4" onClick={() => onChange(value.filter((x) => x !== id))}><X className="h-3 w-3" /></Button>
        </span>))}</div>}
    </div>
  );
}
