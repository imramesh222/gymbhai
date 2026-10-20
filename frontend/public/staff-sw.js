/*
 * The staff dashboard's service worker (PLAN.md §18.6): notifications about
 * what members did, and nothing else. Unlike the member app's (sw.js) it keeps
 * no copies of pages: staff screens hold members' details, and a desk
 * computer is shared.
 */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let message = {};
  try {
    message = event.data ? event.data.json() : {};
  } catch {
    message = { title: "GymBhai", body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(message.title || "GymBhai", {
      body: message.body || "",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      // A newer one of the same kind replaces the last, and still rings.
      tag: message.tag || undefined,
      renotify: Boolean(message.tag),
      data: { url: message.url || "/staff" },
    }),
  );
});

/* Tapping one opens its list, in the dashboard's window if one is open. */
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/staff", self.location.origin)
    .href;
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windows) => {
        const open = windows.find((w) => new URL(w.url).pathname.startsWith("/staff"));
        if (!open) return self.clients.openWindow(url);
        return open
          .navigate(url)
          .then((w) => (w || open).focus())
          .catch(() => self.clients.openWindow(url));
      }),
  );
});
