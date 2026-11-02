import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Camera, ImagePlus } from "lucide-react";

// Phones (and iPads) use the NATIVE camera via <input capture>. This works in every mobile browser,
// installed web apps (PWA) and in-app browsers, with no permission pop-up problems.
// Desktops use a live camera preview.
const isTouchDevice = () =>
  typeof window !== "undefined" &&
  ((window.matchMedia && window.matchMedia("(pointer: coarse)").matches) || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent));

// Shrinks a camera photo to <= maxSide px JPEG (phone photos are often 4-10 MB; the selfie API limit is 6 MB).
export async function shrinkImage(file, maxSide = 1280, quality = 0.82) {
  if (!file || !file.type || !file.type.startsWith("image/")) return file;
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
    const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
    const w = Math.max(1, Math.round(img.naturalWidth * scale));
    const h = Math.max(1, Math.round(img.naturalHeight * scale));
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    c.getContext("2d").drawImage(img, 0, 0, w, h);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", quality));
    if (!blob) return file;
    return new File([blob], `photo_${Date.now()}.jpg`, { type: "image/jpeg" });
  } catch {
    return file; // e.g. HEIC that this browser cannot decode: upload the original
  } finally {
    URL.revokeObjectURL(url);
  }
}

// facing: "environment" (back camera) or "user" (selfie). strict=true: no gallery choice offered.
export function CameraPicker({ facing = "environment", onPhoto, label = "Take photo", strict = true, disabled = false, testId = "camera-open-btn" }) {
  const nativeInput = useRef(null);
  const galleryInput = useRef(null);
  const video = useRef(null);
  const stream = useRef(null);
  const [live, setLive] = useState(false);
  const [ready, setReady] = useState(false);
  const [err, setErr] = useState("");

  const stopTracks = () => { if (stream.current) { stream.current.getTracks().forEach((t) => t.stop()); stream.current = null; } };
  const stop = () => { stopTracks(); setLive(false); setReady(false); };
  useEffect(() => stopTracks, []);

  // Attach the stream AFTER the <video> element exists, and wait until it really has frames.
  useEffect(() => {
    if (!live || !stream.current || !video.current) return undefined;
    const v = video.current;
    v.srcObject = stream.current;
    v.muted = true;
    const start = () => { v.play().then(() => setReady(true)).catch(() => setErr("Could not start the camera preview. Tap Cancel and try again.")); };
    v.addEventListener("loadedmetadata", start);
    if (v.readyState >= 1) start();
    return () => v.removeEventListener("loadedmetadata", start);
  }, [live]);

  const openLive = async () => {
    setErr("");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setErr("This browser cannot open the camera. Open the app in Chrome or Safari (not inside another app) over HTTPS.");
      return;
    }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: facing }, width: { ideal: 1280 } }, audio: false });
      setLive(true);
    } catch (e) {
      const n = e && e.name;
      setErr(n === "NotAllowedError" ? "Camera permission was denied. Allow the camera for this site in your browser settings, then tap the button again."
        : n === "NotFoundError" ? "No camera was found on this device."
        : "Could not open the camera. Close other apps that use the camera and try again.");
    }
  };

  const snap = async () => {
    const v = video.current;
    if (!v || !v.videoWidth) { setErr("The camera is still starting. Wait a second and tap Capture again."); return; }
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.85));
    stop();
    if (!blob) { setErr("Capture failed. Please try again."); return; }
    onPhoto(await shrinkImage(new File([blob], `photo_${Date.now()}.jpg`, { type: "image/jpeg" })));
  };

  const picked = async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (f) { setErr(""); onPhoto(await shrinkImage(f)); }
  };

  const begin = () => { setErr(""); if (isTouchDevice()) nativeInput.current && nativeInput.current.click(); else openLive(); };

  return (
    <div className="space-y-2">
      <input ref={nativeInput} type="file" accept="image/*" capture={facing} className="hidden" onChange={picked} data-testid="camera-native-input" />
      <input ref={galleryInput} type="file" accept="image/*" className="hidden" onChange={picked} data-testid="camera-fallback-input" />
      {!live && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={begin} data-testid={testId}><Camera className="h-4 w-4" /> {label}</Button>
          {!strict && <Button type="button" size="sm" variant="ghost" disabled={disabled} onClick={() => galleryInput.current && galleryInput.current.click()}><ImagePlus className="h-4 w-4" /> Choose from gallery</Button>}
        </div>
      )}
      {live && (
        <div className="space-y-2">
          <video ref={video} playsInline muted autoPlay className="w-full max-w-sm rounded-lg bg-black" data-testid="camera-video" />
          <div className="flex gap-2">
            <Button type="button" onClick={snap} disabled={!ready} data-testid="camera-snap-btn"><Camera className="h-4 w-4" /> Capture</Button>
            <Button type="button" variant="ghost" onClick={stop}>Cancel</Button>
          </div>
        </div>
      )}
      {err && <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900" data-testid="camera-blocked">{err}</div>}
    </div>
  );
}
