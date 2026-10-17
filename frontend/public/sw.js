/*
 * The member app's service worker. Its one job: the app opens with no signal,
 * so the member can still show their QR at the door (PLAN.md §4.2).
 *
 * Pages: network first, the last copy when offline. Build assets: cache first
 * (their names change with every build). The API is never cached.
 */
const CACHE = "gymbhai-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (
    url.pathname.startsWith("/_next/static/") ||
    /\.(png|svg|ico)$/.test(url.pathname)
  ) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
            return response;
          }),
      ),
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() =>
          caches
            .match(request)
            .then(
              (hit) =>
                hit || caches.match(url.pathname.split("/").slice(0, 2).join("/")),
            ),
        ),
    );
  }
});

/*
 * Notifications (PLAN.md §16.3, 8.3): reminders, notices and answers to
 * payments, sent by GymBhai's server. Tapping one opens the page it names,
 * reusing the app's window when it is already open.
 */
self.addEventListener("push", (event) => {
  let message = {};
  try {
    message = event.data ? event.data.json() : {};
  } catch {
    message = { title: "GymBhai", body: event.data ? event.data.text() : "" };
  }
  const scope = new URL(self.registration.scope).pathname.replace(/\/$/, "");
  event.waitUntil(
    self.registration.showNotification(message.title || "GymBhai", {
      body: message.body || "",
      icon: `/api/v1/m${scope}/logo`,
      badge: "/icon-192.png",
      tag: message.tag || undefined,
      data: { url: message.url || scope || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windows) => {
        // A window already on this gym's app: send it there.
        const gym = new URL(url).pathname.split("/").slice(0, 2).join("/");
        const open = windows.find((w) => new URL(w.url).pathname.startsWith(gym));
        if (!open) return self.clients.openWindow(url);
        return open
          .navigate(url)
          .then((w) => (w || open).focus())
          .catch(() => self.clients.openWindow(url));
      }),
  );
});
