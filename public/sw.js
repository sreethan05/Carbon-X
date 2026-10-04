/* CarbonX service worker — conservative offline shell.
   - App shell ( navigations ): network-first, fall back to cached index.html
     so the SPA opens without connectivity (offline-first field use).
   - Static assets: cache-first (hashed filenames).
   - API calls (/py-api, /bc-api): network-only — never serve stale trust data.
*/
const CACHE = "carbonx-shell-v1";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (url.pathname.startsWith("/py-api") || url.pathname.startsWith("/bc-api")) {
    // Trust data (wallet, ledger, purchases): always network.
    // Exception: the public marketplace listing feed gets stale-while-revalidate
    // so the catalogue paints instantly on flaky rural connections.
    if (url.pathname.startsWith("/py-api/marketplace/listings") || url.pathname.startsWith("/py-api/fpos")) {
      event.respondWith((async () => {
        const cache = await caches.open("carbonx-api-v1");
        const cached = await cache.match(event.request);
        const network = fetch(event.request).then((res) => {
          if (res.ok) cache.put(event.request, res.clone());
          return res;
        }).catch(() => cached);
        return cached || network;
      })());
      return;
    }
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put("/index.html", copy));
          return res;
        })
        .catch(() => caches.match("/index.html"))
    );
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(event.request).then(
        (cached) =>
          cached ||
          fetch(event.request).then((res) => {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
            return res;
          })
      )
    );
  }
});
