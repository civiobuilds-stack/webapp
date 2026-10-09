import { useState } from "react";
import { api, apiError, fileUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2, Upload, X, ImagePlus } from "lucide-react";
import { toast } from "sonner";

export function PhotoUpload({ projectId, value = [], onChange, label = "Site photos" }) {
  const [busy, setBusy] = useState(false);

  const handle = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setBusy(true);
    const ids = [...value];
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      if (projectId) fd.append("project_id", projectId);
      try {
        const { data } = await api.post("/files/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
        ids.push(data.id);
      } catch (err) {
        toast.error(apiError(err.response?.data?.detail));
      }
    }
    onChange(ids);
    setBusy(false);
    e.target.value = "";
  };

  const remove = (id) => onChange(value.filter((v) => v !== id));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
        <label className="inline-flex">
          <input type="file" accept="image/*" multiple capture="environment" className="hidden" onChange={handle} data-testid="photo-upload-input" />
          <Button type="button" asChild variant="outline" size="sm" disabled={busy}>
            <span data-testid="photo-upload-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
              <span className="ml-1.5">Add photo</span>
            </span>
          </Button>
        </label>
      </div>
      {value.length > 0 && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {value.map((id) => (
            <div key={id} className="relative aspect-square overflow-hidden rounded-lg border bg-muted">
              <img src={fileUrl(id)} alt="upload" className="h-full w-full object-cover" />
              <button type="button" onClick={() => remove(id)} data-testid="remove-photo-btn"
                className="absolute right-1 top-1 rounded-full bg-black/60 p-1 text-white hover:bg-black/80">
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function PhotoGrid({ photoIds = [], photos = [] }) {
  const items = photos.length ? photos.map((p) => p.id) : photoIds;
  if (!items.length) return <p className="text-sm text-muted-foreground">No photos attached.</p>;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
      {items.map((id) => (
        <a key={id} href={fileUrl(id)} target="_blank" rel="noreferrer"
          className="group relative aspect-square overflow-hidden rounded-xl border bg-muted">
          <img src={fileUrl(id)} alt="site" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" />
        </a>
      ))}
    </div>
  );
}
