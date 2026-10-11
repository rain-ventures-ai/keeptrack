// Lets the board show alerts on phones: Android browsers refuse `new Notification()` from a page and only allow a
// service worker to show one. It caches nothing and answers no requests; it only shows and handles taps on alerts.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('notificationclick', e => {
  e.notification.close(); const card = (e.notification.data || {}).card || '';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    if (list[0]) { list[0].postMessage({ kbOpenCard: card }); return list[0].focus(); }
    return self.clients.openWindow(self.registration.scope);
  }));
});
