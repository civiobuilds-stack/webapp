const CACHE = "civio-shell-v1";
const SHELL = ["/", "/civio-icon.png", "/civio-logo.png", "/manifest.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).pathname.startsWith("/api")) return;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/")));
  }
});
