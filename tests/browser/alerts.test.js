'use strict';
// Alerts on a phone: Android browsers refuse `new Notification()` from a page, so the board falls back to a service worker (board/sw.js).
// Here the constructor is made to throw as it does on Android; the test alert must still arrive, as a service-worker notification.
// A blocked permission says what to do about it. Run: node alerts.test.js
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}/board/index.html?demo=crm`;
  const browser = await chromium.launch();
  try {
    // 1. Android: the constructor throws, permission is granted. The test alert is shown by the service worker.
    {
      const ctx = await browser.newContext({ permissions: ['notifications'], viewport: { width: 390, height: 844 } }), page = await ctx.newPage(), errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(() => {
        const Real = window.Notification;
        function Android() { throw new TypeError("Failed to construct 'Notification': Illegal constructor. Use ServiceWorkerRegistration.showNotification() instead."); }
        window.__shown = []; const show = ServiceWorkerRegistration.prototype.showNotification; ServiceWorkerRegistration.prototype.showNotification = function (t, o) { window.__shown.push({ title: t, body: o.body }); return show.call(this, t, o); };
        Android.permission = Real.permission; Android.requestPermission = () => Promise.resolve('granted'); window.Notification = Android;
        localStorage.setItem('kb_alerts', JSON.stringify({ on: true, kinds: ['mention'] })); localStorage.setItem('kb_tour_seen', '1');
      });
      await page.goto(base); await page.waitForFunction(() => window.kbSettings);
      await page.evaluate(() => window.kbSettings.open('alerts')); await page.locator('#alTest').click();
      await page.waitForFunction(() => window.__shown.length === 1, null, { timeout: 10000 }); const n = await page.evaluate(() => window.__shown[0]);
      assert.deepEqual(n, { title: 'Test alert', body: 'Board alerts work in this browser.' });
      assert.deepEqual(errors, []); await ctx.close();
    }
    // 2. Blocked: the page says it is blocked and what to do on a phone.
    {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } }), page = await ctx.newPage();
      await page.addInitScript(() => { Object.defineProperty(Notification, 'permission', { get: () => 'denied' }); localStorage.setItem('kb_alerts', JSON.stringify({ on: true, kinds: ['mention'] })); localStorage.setItem('kb_tour_seen', '1'); });
      await page.goto(base); await page.waitForFunction(() => window.kbSettings);
      await page.evaluate(() => window.kbSettings.open('alerts')); await page.locator('#alOn').check();   // the demo board keeps settings in memory, so switch alerts on here
      const t = await page.locator('#alPerm').textContent();
      assert.match(t, /blocked for this page/); assert.match(t, /padlock/); assert.match(t, /Android/); assert.equal(await page.locator('#alChip').textContent(), 'Blocked');
      await ctx.close();
    }
    console.log('alerts: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
