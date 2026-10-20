/*
 * The door kiosk's service worker (PLAN.md §19.2): the kiosk opens and keeps
 * letting people in with no internet. It keeps the kiosk page, its build
 * assets and members' photos, nothing else: no staff page, no API answer.
 * The roster and the scans waiting to be sent live in the page's own storage.
 */
const SHELL = "kiosk-shell-v1";
const PHOTOS = "kiosk-photos-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("kiosk-") && k !== SHELL && k !== PHOTOS)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function cacheFirst(request, cacheName, key) {
  return caches.open(cacheName).then((cache) =>
    cache.match(key).then(
      (hit) =>
        hit ||
        fetch(request).then((response) => {
          if (response.ok) cache.put(key, response.clone());
          return response;
        }),
    ),
  );
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== location.origin) return;

  // A member's photo: its address changes with the photo, its signature with
  // the hour, so it is kept by address alone.
  if (url.pathname.startsWith("/api/v1/files/")) {
    event.respondWith(cacheFirst(request, PHOTOS, url.pathname));
    return;
  }
  if (url.pathname.startsWith("/api/")) return;

  // Build assets: their names change with every build.
  if (url.pathname.startsWith("/_next/static/") || /\.(png|svg|ico)$/.test(url.pathname)) {
    event.respondWith(cacheFirst(request, SHELL, request));
    return;
  }

  // The kiosk page: the network first, the last copy with no internet.
  if (request.mode === "navigate" && url.pathname.startsWith("/kiosk")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(SHELL).then((cache) => cache.put("/kiosk", copy));
          return response;
        })
        .catch(() => caches.match("/kiosk")),
    );
  }
});
