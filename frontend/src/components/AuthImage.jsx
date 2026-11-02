import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loader2, RotateCcw, ZoomIn, ZoomOut, Download, ImageOff } from "lucide-react";

const cache = new Map();

export async function loadBlob(path) {
  if (cache.has(path)) return cache.get(path);
  const p = api.get(path, { responseType: "blob" }).then((r) => ({ url: URL.createObjectURL(r.data), type: r.data.type || r.headers["content-type"] || "", blob: r.data }));
  cache.set(path, p);
  p.catch(() => cache.delete(path));
  return p;
}

const fileName = (path, type) => `${path.split("/").filter(Boolean).slice(-2).join("_")}${type.includes("pdf") ? ".pdf" : type.includes("csv") ? ".csv" : type.startsWith("image/") ? ".jpg" : ""}`;

export function openFile(fileId) { window.dispatchEvent(new CustomEvent("civio:view", { detail: { path: `/files/${fileId}/download` } })); }
export function openPath(path) { window.dispatchEvent(new CustomEvent("civio:view", { detail: { path } })); }

export function AuthImage({ fileId, path, thumb = false, className = "", alt = "", viewer = true, ...rest }) {
  const src = path || `/files/${fileId}/${thumb ? "thumb" : "download"}`;
  const [state, setState] = useState({ url: null, err: false });
  const load = useCallback(() => {
    setState({ url: null, err: false });
    loadBlob(src).then((b) => setState({ url: b.url, err: false })).catch(() => setState({ url: null, err: true }));
  }, [src]);
  useEffect(() => { load(); }, [load]);
  if (state.err) return (
    <div className={`flex flex-col items-center justify-center gap-1 bg-muted text-xs text-muted-foreground ${className}`} data-testid="auth-image-error">
      <ImageOff className="h-4 w-4" />
      <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={(e) => { e.preventDefault(); e.stopPropagation(); load(); }} data-testid="auth-image-retry"><RotateCcw className="h-3 w-3" /> Retry</Button>
    </div>);
  if (!state.url) return <div className={`flex items-center justify-center bg-muted ${className}`} data-testid="auth-image-loading"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>;
  const open = viewer && (fileId || path) ? (e) => { e.preventDefault(); e.stopPropagation(); fileId ? openFile(fileId) : openPath(path); } : undefined;
  return <img src={state.url} alt={alt} className={`${className} ${open ? "cursor-zoom-in" : ""}`} onClick={open} data-testid="auth-image" {...rest} />;
}

export function FileViewer() {
  const [path, setPath] = useState(null);
  const [file, setFile] = useState(null);
  const [err, setErr] = useState(false);
  const [zoom, setZoom] = useState(1);
  const load = useCallback((p) => {
    setFile(null); setErr(false); setZoom(1);
    loadBlob(p).then((b) => {
      if (!b.type.startsWith("image/") && !b.type.includes("pdf")) {
        const a = document.createElement("a"); a.href = b.url; a.download = fileName(p, b.type); a.click(); setPath(null); return;
      }
      setFile(b);
    }).catch(() => setErr(true));
  }, []);
  useEffect(() => {
    const h = (e) => { setPath(e.detail.path); load(e.detail.path); };
    window.addEventListener("civio:view", h);
    return () => window.removeEventListener("civio:view", h);
  }, [load]);
  const isImg = file?.type.startsWith("image/");
  return (
    <Dialog open={!!path} onOpenChange={(o) => !o && setPath(null)}>
      <DialogContent className="flex max-h-[95vh] max-w-[95vw] flex-col sm:max-w-5xl" data-testid="file-viewer">
        <DialogHeader><DialogTitle className="flex flex-wrap items-center gap-2 pr-6">{isImg ? "Photo" : "Document"}
          <span className="flex-1" />
          {isImg && <><Button size="icon" variant="outline" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} data-testid="viewer-zoom-out"><ZoomOut className="h-4 w-4" /></Button>
            <span className="w-12 text-center text-xs">{Math.round(zoom * 100)}%</span>
            <Button size="icon" variant="outline" onClick={() => setZoom((z) => Math.min(4, z + 0.25))} data-testid="viewer-zoom-in"><ZoomIn className="h-4 w-4" /></Button></>}
          {file && <Button size="sm" variant="outline" asChild><a href={file.url} download={fileName(path, file.type)} data-testid="viewer-download"><Download className="h-4 w-4" /> Download</a></Button>}
        </DialogTitle></DialogHeader>
        <div className="min-h-[50vh] flex-1 overflow-auto rounded-md bg-muted/40">
          {err && <div className="flex h-full flex-col items-center justify-center gap-2 p-10 text-sm" data-testid="viewer-error">Could not load the file.
            <Button size="sm" onClick={() => load(path)} data-testid="viewer-retry"><RotateCcw className="h-4 w-4" /> Retry</Button></div>}
          {!err && !file && <div className="flex h-full items-center justify-center p-10"><Loader2 className="h-6 w-6 animate-spin" /></div>}
          {isImg && <img src={file.url} alt="" style={{ width: `${zoom * 100}%`, maxWidth: "none" }} className="mx-auto block" data-testid="viewer-image" />}
          {file && !isImg && <iframe src={file.url} title="document" className="h-[75vh] w-full" data-testid="viewer-pdf" />}
        </div>
      </DialogContent>
    </Dialog>
  );
}
