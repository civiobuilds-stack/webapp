import { useEffect, useMemo, useState } from "react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { RotateCcw, Upload, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { AuthImage } from "@/components/AuthImage";
import { CameraPicker } from "@/components/CameraPicker";

// Camera-first capture: take photo -> preview -> retake / upload (with retry).
// Commercial workspaces: camera only. Others: gallery is also offered.
export function CameraCapture({ projectId, value = [], onChange, label = "Photos", max = 6 }) {
  const [mode, setMode] = useState("idle"); // idle | preview | uploading
  const [blob, setBlob] = useState(null);
  const { user } = useAuth();
  const cameraOnly = user?.enterprise?.business_type === "commercial";
  const preview = useMemo(() => (blob ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const upload = async (file) => {
    setMode("uploading");
    const fd = new FormData();
    fd.append("file", file, file.name || `site_${Date.now()}.jpg`);
    if (projectId) fd.append("project_id", projectId);
    try {
      const { data } = await api.post("/files/upload", fd);
      onChange([...value, data.id]);
      setBlob(null); setMode("idle"); toast.success("Photo saved");
    } catch (e) {
      toast.error(`${e.response ? apiError(e.response.data?.detail) : "Network problem - check your connection"} - tap Upload / Retry`);
      setMode("preview");
    }
  };

  return (
    <div className="space-y-2" data-testid="camera-capture">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
      </div>
      {mode === "idle" && value.length < max && (
        <CameraPicker facing="environment" strict={cameraOnly} onPhoto={(f) => { setBlob(f); setMode("preview"); }} label="Take photo" testId="camera-open-btn" />
      )}
      {preview && (mode === "preview" || mode === "uploading") && (
        <div className="space-y-2">
          <img src={preview} alt="preview" className="w-full max-w-sm rounded-lg" data-testid="camera-preview" />
          <div className="flex gap-2">
            <Button type="button" disabled={mode === "uploading"} onClick={() => upload(blob)} data-testid="camera-upload-btn">
              {mode === "uploading" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload / Retry
            </Button>
            <Button type="button" variant="outline" disabled={mode === "uploading"} onClick={() => { setBlob(null); setMode("idle"); }} data-testid="camera-retake-btn">
              <RotateCcw className="h-4 w-4" /> Retake
            </Button>
          </div>
        </div>
      )}
      {value.length > 0 && (
        <div className="grid grid-cols-4 gap-2">
          {value.map((id) => (
            <div key={id} className="relative aspect-square overflow-hidden rounded-lg border">
              <AuthImage thumb viewer={false} fileId={id} alt="" className="h-full w-full object-cover" />
              <button type="button" onClick={() => onChange(value.filter((v) => v !== id))} className="absolute right-1 top-1 rounded-full bg-black/60 p-1 text-white"><X className="h-3 w-3" /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
