// Installable Keeptrack apps. A board gets its own manifest identity, launch URL and generated icon while
// continuing to use the one static GitHub Pages deployment. sw.js serves the per-board manifest.
(function () {
  'use strict';

  const q = new URLSearchParams(location.search);
  const boardPage = !q.has('demo') && !q.has('setup');
  const get = (key, fallback = '') => {
    const value = q.get(key);
    if (value) return value;
    if (!boardPage) return fallback;
    try { return localStorage.getItem('kb_' + key) || fallback; } catch { return fallback; }
  };
  const validRepo = value => /^[\w.-]+\/[\w.-]+$/.test(value || '');
  const validPath = value => /^[\w./-]+$/.test(value || '');
  const repo = boardPage && validRepo(get('repo')) ? get('repo') : '';
  const branch = validPath(get('branch', 'master')) ? get('branch', 'master') : 'master';
  const path = validPath(get('path', 'board/tasks.json')) ? get('path', 'board/tasks.json') : 'board/tasks.json';
  const boardKey = repo ? [repo, branch, path].join('|') : 'keeptrack';
  const appKey = btoa(boardKey).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const words = (repo ? repo.split('/').pop() : 'Keeptrack').split(/[-_.\s]+/).filter(Boolean);
  const titleCase = value => value.replace(/\b\w/g, letter => letter.toUpperCase());
  const boardName = repo ? titleCase(words.join(' ')) : 'Keeptrack';
  const appName = repo ? boardName + ' · Keeptrack' : 'Keeptrack';
  const shortName = boardName.slice(0, 12);
  const initials = (words.length > 1 ? words[0][0] + words[1][0] : (words[0] || 'KT').slice(0, 2)).toUpperCase();
  let hash = 2166136261;
  for (const ch of boardKey) { hash ^= ch.charCodeAt(0); hash = Math.imul(hash, 16777619); }
  const hue = Math.abs(hash >>> 0) % 360;
  const colour = `hsl(${hue} 58% 38%)`;
  const themeColour = hslToHex(hue, 58, 38);
  const standalone = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  let installPrompt = null;

  function hslToHex(h, s, l) {
    s /= 100; l /= 100;
    const a = s * Math.min(l, 1 - l), f = n => {
      const k = (n + h / 30) % 12;
      return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    };
    return '#' + [f(0), f(8), f(4)].map(x => Math.round(255 * x).toString(16).padStart(2, '0')).join('');
  }

  function iconUrl(size) {
    return new URL(`pwa/icon-${size}.png?app=${encodeURIComponent(appKey)}`, location.href).href;
  }

  async function cacheIcon(size) {
    if (!repo || !window.caches) return;
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = size;
    const cx = canvas.getContext('2d'); if (!cx) return;
    cx.fillStyle = colour; cx.fillRect(0, 0, size, size);
    const glow = cx.createRadialGradient(size * .2, size * .12, 0, size * .2, size * .12, size);
    glow.addColorStop(0, 'rgba(255,255,255,.24)'); glow.addColorStop(1, 'rgba(255,255,255,0)');
    cx.fillStyle = glow; cx.fillRect(0, 0, size, size);
    cx.fillStyle = '#fff'; cx.textAlign = 'center'; cx.textBaseline = 'middle';
    cx.font = `700 ${Math.round(size * .34)}px system-ui, sans-serif`; cx.fillText(initials, size / 2, size * .45);
    const w = size * .105, gap = size * .035, left = size / 2 - (w * 3 + gap * 2) / 2, top = size * .69;
    [0.12, 0.2, 0.08].forEach((height, i) => {
      cx.beginPath();
      if (cx.roundRect) cx.roundRect(left + i * (w + gap), top - size * height / 2, w, size * height, size * .018);
      else cx.rect(left + i * (w + gap), top - size * height / 2, w, size * height);
      cx.fill();
    });
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    if (blob) (await caches.open('keeptrack-icons-v1')).put(iconUrl(size), new Response(blob, { headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=31536000, immutable' } }));
  }

  function addManifest(dynamic) {
    const params = new URLSearchParams({ app: appKey, name: appName, short: shortName, colour: themeColour });
    if (repo) { params.set('repo', repo); params.set('branch', branch); params.set('path', path); }
    let manifest = document.querySelector('link[rel="manifest"]');
    if (!manifest) { manifest = document.createElement('link'); manifest.rel = 'manifest'; document.head.append(manifest); }
    manifest.href = dynamic ? `manifest.webmanifest?${params}` : 'manifest.webmanifest';
    let touch = document.querySelector('link[rel="apple-touch-icon"]');
    if (!touch) { touch = document.createElement('link'); touch.rel = 'apple-touch-icon'; document.head.append(touch); }
    touch.href = dynamic && repo ? iconUrl(180) : 'pwa/icon-192.png';
    let favicon = document.querySelector('link[rel="icon"]');
    if (!favicon) { favicon = document.createElement('link'); favicon.rel = 'icon'; favicon.type = 'image/png'; document.head.append(favicon); }
    favicon.href = dynamic && repo ? iconUrl(192) : 'pwa/icon-192.png';
    const theme = document.querySelector('meta[name="theme-color"]'); if (theme) theme.content = themeColour;
    const appleTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]'); if (appleTitle) appleTitle.content = boardName;
    window.dispatchEvent(new CustomEvent('kb-pwa-change'));
  }

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); installPrompt = event; window.dispatchEvent(new CustomEvent('kb-pwa-change'));
  });
  window.addEventListener('appinstalled', () => { installPrompt = null; window.dispatchEvent(new CustomEvent('kb-pwa-change')); });

  window.kbPwa = Object.freeze({
    boardName,
    installed: standalone,
    available: () => !standalone() && (!!installPrompt || ios),
    async install() {
      if (standalone()) return 'installed';
      if (!installPrompt) return ios ? 'ios' : 'browser';
      const prompt = installPrompt; installPrompt = null; await prompt.prompt();
      const choice = await prompt.userChoice; window.dispatchEvent(new CustomEvent('kb-pwa-change'));
      return choice.outcome === 'accepted' ? 'accepted' : 'dismissed';
    }
  });

  (async () => {
    if (!('serviceWorker' in navigator) || location.protocol === 'file:') { addManifest(false); return; }
    try {
      await Promise.all([cacheIcon(180), cacheIcon(192), cacheIcon(512)]);
      const previousController = navigator.serviceWorker.controller;
      const registration = await navigator.serviceWorker.register('sw.js', { scope: './', updateViaCache: 'none' });
      const changing = registration.installing || registration.waiting;
      if (changing && changing.state !== 'activated') await new Promise(resolve => {
        const done = () => { if (changing.state === 'activated' || changing.state === 'redundant') resolve(); };
        changing.addEventListener('statechange', done); setTimeout(resolve, 4000);
      });
      await navigator.serviceWorker.ready;
      if (!navigator.serviceWorker.controller || (changing && navigator.serviceWorker.controller === previousController)) await Promise.race([
        new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true })),
        new Promise(resolve => setTimeout(resolve, 3000))
      ]);
      addManifest(!!navigator.serviceWorker.controller);
    } catch { addManifest(false); }
  })();
})();
