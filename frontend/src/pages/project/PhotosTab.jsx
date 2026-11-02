import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ImageOff } from "lucide-react";
import { AuthImage, openFile } from "@/components/AuthImage";

export function PhotosTab({ project }) {
  const [photos, setPhotos] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.get(`/projects/${project.id}/photos`).then((r) => setPhotos(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [project.id]);

  if (loading) return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="aspect-square rounded-xl" />)}</div>;

  return (
    <div className="space-y-4">
      <h3 className="font-heading text-lg font-semibold">Site photo gallery</h3>
      {photos.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-12 text-center text-muted-foreground"><ImageOff className="h-8 w-8" /> No site photos uploaded yet.</Card>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
          {photos.map((p) => (
            <a key={p.id} href="#" onClick={(e) => { e.preventDefault(); openFile(p.id); }} data-testid="gallery-photo"
              className="group relative aspect-square overflow-hidden rounded-xl border bg-muted">
              <AuthImage thumb viewer={false} fileId={p.id} alt={p.caption || "site"} className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" />
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-2">
                <div className="truncate text-[11px] text-white">{p.caption || p.original_filename}</div>
                <div className="text-[10px] text-white/60">{formatDateTime(p.created_at)}</div>
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
