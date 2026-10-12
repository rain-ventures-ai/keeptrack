// Keeptrack's app shell, per-board install manifests and phone notifications.
const SHELL_CACHE = 'keeptrack-shell-v1';
const CACHE_PREFIX = 'keeptrack-shell-';
const SHELL = ['index.html', 'board.css', 'ui.css', 'theme.js', 'designmd.js', 'pwa.js', 'icons.js', 'ui.js', 'board.js', 'vendor/minisearch-7.2.0.min.js', 'manifest.webmanifest', 'pwa/icon-180.png', 'pwa/icon-192.png', 'pwa/icon-512.png'];
const SCOPE = new URL(self.registration.scope);
const shellUrls = new Set(SHELL.map(path => new URL(path, SCOPE).pathname));

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith(CACHE_PREFIX) && key !== SHELL_CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});

const bounded = (value, fallback, max = 160) => typeof value === 'string' && value.length <= max ? value : fallback;
function boardManifest(url) {
  const p = url.searchParams, repo = bounded(p.get('repo'), ''), branch = bounded(p.get('branch'), 'master'), path = bounded(p.get('path'), 'board/tasks.json');
  const app = bounded(p.get('app'), 'keeptrack', 500), name = bounded(p.get('name'), 'Keeptrack', 80), short = bounded(p.get('short'), 'Keeptrack', 20);
  const colour = /^#[0-9a-f]{6}$/i.test(p.get('colour') || '') ? p.get('colour') : '#243447';
  const start = new URL('./', SCOPE), id = new URL('./', SCOPE);
  if (repo) { start.searchParams.set('repo', repo); start.searchParams.set('branch', branch); start.searchParams.set('path', path); }
  id.searchParams.set('installed', app);
  const icon = size => {
    const out = new URL(`pwa/icon-${size}.png`, SCOPE); if (app !== 'keeptrack') out.searchParams.set('app', app); return out.href;
  };
  return {
    id: id.href, name, short_name: short, description: 'People, follow-ups and tasks in your private GitHub board.',
    start_url: start.href, scope: SCOPE.href, display: 'standalone', background_color: '#0b1020', theme_color: colour,
    categories: ['productivity'], prefer_related_applications: false,
    icons: [
      { src: icon(192), sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
      { src: icon(512), sizes: '512x512', type: 'image/png', purpose: 'any maskable' }
    ]
  };
}

async function networkFirst(request, fallback) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok && shellUrls.has(new URL(request.url).pathname)) await cache.put(new URL(new URL(request.url).pathname, SCOPE.origin), response.clone());
    return response;
  } catch {
    return (await cache.match(fallback || request, { ignoreSearch: true })) || Response.error();
  }
}

self.addEventListener('fetch', event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== SCOPE.origin) return;
  if (url.pathname === new URL('manifest.webmanifest', SCOPE).pathname && url.search) {
    event.respondWith(Promise.resolve(new Response(JSON.stringify(boardManifest(url)), { headers: { 'Content-Type': 'application/manifest+json', 'Cache-Control': 'no-store' } })));
    return;
  }
  const icon = /\/pwa\/icon-(180|192|512)\.png$/.exec(url.pathname);
  if (icon && url.searchParams.has('app')) {
    event.respondWith(caches.match(request).then(hit => hit || fetch(new URL(`pwa/icon-${icon[1]}.png`, SCOPE))));
    return;
  }
  if (request.mode === 'navigate') { event.respondWith(networkFirst(request, 'index.html')); return; }
  if (shellUrls.has(url.pathname)) event.respondWith(networkFirst(request));
});

self.addEventListener('notificationclick', event => {
  event.notification.close(); const data = event.notification.data || {}, card = data.card || '';
  let target = new URL(data.url || self.registration.scope, SCOPE);
  if (target.origin !== SCOPE.origin || !target.pathname.startsWith(SCOPE.pathname)) target = new URL(self.registration.scope);
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    const match = list.find(client => { const current = new URL(client.url); return current.pathname === target.pathname && current.search === target.search; });
    if (match) { match.postMessage({ kbOpenCard: card }); return match.focus(); }
    return self.clients.openWindow(target.href);
  }));
});
