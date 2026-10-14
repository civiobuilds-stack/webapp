import { api } from "@/lib/api";

export const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

const toKey = (b64) => {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
};

export async function enablePush() {
  if (!pushSupported()) throw new Error("This browser does not support push. On iPhone, add CIVIO to the Home Screen first (iOS 16.4+).");
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Notification permission was not granted.");
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const { data } = await api.get("/push/public-key");
  const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: toKey(data.public_key) });
  const j = sub.toJSON();
  return (await api.post("/push/subscribe", { endpoint: j.endpoint, keys: j.keys })).data;
}

export async function disablePush() {
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  if (sub) { const j = sub.toJSON(); await api.post("/push/unsubscribe", { endpoint: j.endpoint, keys: j.keys }); await sub.unsubscribe(); }
}

// Refresh the device token for the signed-in user when permission was already granted.
export async function refreshPush() {
  try { if (pushSupported() && Notification.permission === "granted") await enablePush(); } catch { /* ignore */ }
}
