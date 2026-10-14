import { useEffect, useRef, useState } from "react";
import { api, apiError, fileUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Camera, RotateCcw, Upload, Loader2, ImagePlus, X } from "lucide-react";
import { toast } from "sonner";

// Camera-first capture: live camera → capture → preview → retake / upload (with retry). Gallery only if camera is unavailable.
export function CameraCapture({ projectId, value = [], onChange, label = "Photos", max = 6 }) {
  const video = useRef(null);
  const stream = useRef(null);
  const [mode, setMode] = useState("idle"); // idle | live | preview | uploading | fallback
  const [blob, setBlob] = useState(null);
  const stop = () => { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; };
  useEffect(() => stop, []);
  const open = async () => {
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      setMode("live");
      setTimeout(() => { if (video.current) { video.current.srcObject = stream.current; video.current.play(); } }, 0);
    } catch { setMode("fallback"); toast.message("Camera unavailable or permission denied — choose a photo from your device instead."); }
  };
  const snap = () => {
    const v = video.current, c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight; c.getContext("2d").drawImage(v, 0, 0);
    c.toBlob((b) => { setBlob(b); setMode("preview"); stop(); }, "image/jpeg", 0.85);
  };
  const upload = async (file) => {
    setMode("uploading");
    const fd = new FormData(); fd.append("file", file, file.name || `site_${Date.now()}.jpg`); fd.append("project_id", projectId);
    try { const { data } = await api.post("/files/upload", fd); onChange([...value, data.id]); setBlob(null); setMode("idle"); toast.success("Photo saved"); }
    catch (e) { toast.error(`${apiError(e.response?.data?.detail)} — tap Retry`); setMode(file instanceof File ? "fallback" : "preview"); }
  };
  const preview = blob ? URL.createObjectURL(blob) : null;
  return (
    <div className="space-y-2" data-testid="camera-capture">
      <div className="flex items-center justify-between"><span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
        {mode === "idle" && value.length < max && <Button type="button" size="sm" variant="outline" onClick={open} data-testid="camera-open-btn"><Camera className="h-4 w-4" /> Take photo</Button>}</div>
      {mode === "live" && <div className="space-y-2"><video ref={video} playsInline muted className="w-full rounded-lg bg-black" data-testid="camera-video" />
        <div className="flex gap-2"><Button type="button" onClick={snap} data-testid="camera-snap-btn"><Camera className="h-4 w-4" /> Capture</Button>
          <Button type="button" variant="ghost" onClick={() => { stop(); setMode("idle"); }}>Cancel</Button></div></div>}
      {(mode === "preview" || (mode === "uploading" && preview)) && <div className="space-y-2"><img src={preview} alt="preview" className="w-full rounded-lg" data-testid="camera-preview" />
        <div className="flex gap-2"><Button type="button" disabled={mode === "uploading"} onClick={() => upload(new File([blob], `site_${Date.now()}.jpg`, { type: "image/jpeg" }))} data-testid="camera-upload-btn">
          {mode === "uploading" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload / Retry</Button>
          <Button type="button" variant="outline" onClick={() => { setBlob(null); open(); }} data-testid="camera-retake-btn"><RotateCcw className="h-4 w-4" /> Retake</Button></div></div>}
      {mode === "fallback" && <label className="inline-flex"><input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files[0] && upload(e.target.files[0])} data-testid="camera-fallback-input" />
        <Button type="button" asChild size="sm" variant="outline"><span><ImagePlus className="h-4 w-4" /> Choose from gallery</span></Button></label>}
      {value.length > 0 && <div className="grid grid-cols-4 gap-2">{value.map((id) => (
        <div key={id} className="relative aspect-square overflow-hidden rounded-lg border"><img src={fileUrl(id)} alt="" className="h-full w-full object-cover" />
          <button type="button" onClick={() => onChange(value.filter((v) => v !== id))} className="absolute right-1 top-1 rounded-full bg-black/60 p-1 text-white"><X className="h-3 w-3" /></button></div>))}</div>}
    </div>
  );
}
