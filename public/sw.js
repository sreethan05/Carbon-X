/* CarbonX service worker — conservative offline shell.
   - App shell (navigations): network-first, fall back to cached /index.html
     so the SPA opens without connectivity (offline-first field use).
   - Static assets (scripts, styles, images, fonts): cache-first with network fallback.
   - API calls (/py-api, /bc-api, JSON data endpoints): strictly network-only.
     NEVER serve stale data for trust, marketplace, farmer, ledger, or financial state.
*/
const CACHE = "carbonx-shell-v2";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/manifest.json",
  "/icon.svg",
  "/icon-192.png",
  "/icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Non-GET requests are always network-only
  if (event.request.method !== "GET") return;

  // 1. API and dynamic data requests: STRICTLY network-only — never serve stale data
  const isApi =
    url.pathname.startsWith("/py-api") ||
    url.pathname.startsWith("/bc-api") ||
    url.pathname.startsWith("/api") ||
    url.pathname.startsWith("/ws") ||
    event.request.headers.get("accept")?.includes("application/json");

  if (isApi) {
    return; // Pass through to network directly; no SW caching
  }

  // 2. Navigation requests (SPA HTML): network-first, fallback to cached index.html
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put("/index.html", copy));
          }
          return res;
        })
        .catch(() => caches.match("/index.html"))
    );
    return;
  }

  // 3. Static assets: only cache same-origin static resources (scripts, styles, images, fonts)
  if (url.origin === self.location.origin) {
    const isStaticAsset =
      url.pathname.startsWith("/assets/") ||
      /\.(?:js|css|svg|png|jpg|jpeg|gif|webp|ico|woff|woff2|ttf|eot)$/i.test(url.pathname) ||
      SHELL.includes(url.pathname);

    if (isStaticAsset) {
      event.respondWith(
        caches.match(event.request).then(
          (cached) =>
            cached ||
            fetch(event.request).then((res) => {
              if (res.ok) {
                const copy = res.clone();
                caches.open(CACHE).then((cache) => cache.put(event.request, copy));
              }
              return res;
            })
        )
      );
    }
  }
});
