'use strict';
// Each board is installable as its own PWA: stable identity and launch URL, board-specific icon, and an offline app shell.
// Run: node pwa.test.js
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => {
    if (err) res.writeHead(404).end();
    else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.setHeader('Cache-Control', 'no-cache'); res.end(data); }
  });
});

async function appDetails(page) {
  await page.waitForFunction(() => navigator.serviceWorker.controller && document.querySelector('link[rel="manifest"]')?.href.includes('app='), null, { timeout: 15000 });
  return page.evaluate(async () => {
    const url = document.querySelector('link[rel="manifest"]').href;
    const response = await fetch(url); return { url, type: response.headers.get('content-type'), manifest: await response.json() };
  });
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ channel: 'chromium' });
  try {
    const context = await browser.newContext(), page = await context.newPage();
    await page.addInitScript(() => localStorage.setItem('kb_tour_seen', '1'));
    await page.goto(`${origin}/board/index.html?repo=osouthgate/private-tasks&branch=main&path=board/tasks.json`);
    const first = await appDetails(page), a = first.manifest;
    assert.match(first.type, /^application\/manifest\+json/);
    assert.equal(a.name, 'Private Tasks · Keeptrack'); assert.equal(a.short_name, 'Private Task');
    assert.match(a.id, /[?&]installed=/); assert.match(a.start_url, /repo=osouthgate%2Fprivate-tasks/);
    assert.equal(a.display, 'standalone'); assert.equal(a.icons[0].sizes, '192x192'); assert.equal(a.icons[1].sizes, '512x512');
    const firstIcon = Buffer.from(await page.evaluate(async url => [...new Uint8Array(await (await fetch(url)).arrayBuffer())], a.icons[1].src));
    assert.equal(firstIcon.subarray(1, 4).toString(), 'PNG'); assert.ok(firstIcon.length > 1000);

    const cdp = await context.newCDPSession(page); await cdp.send('Page.enable');
    const parsed = await cdp.send('Page.getAppManifest');
    assert.equal(parsed.errors.length, 0); assert.equal(JSON.parse(parsed.data).name, a.name);
    await page.waitForFunction(() => window.kbSettings);
    await page.evaluate(() => {
      window.__pwaPrompted = 0; const event = new Event('beforeinstallprompt', { cancelable: true });
      event.prompt = async () => { window.__pwaPrompted++; }; event.userChoice = Promise.resolve({ outcome: 'accepted' }); window.dispatchEvent(event);
    });
    assert.equal(await page.locator('#btnInstall').evaluate(button => button.hidden), false);
    await page.locator('#btnInstall').evaluate(button => button.click());
    await page.waitForFunction(() => window.__pwaPrompted === 1);

    await page.goto(`${origin}/board/index.html?repo=rain-ventures-ai/client-work&branch=main&path=board/tasks.json`);
    const second = (await appDetails(page)).manifest;
    assert.equal(second.name, 'Client Work · Keeptrack'); assert.notEqual(second.id, a.id); assert.notEqual(second.icons[1].src, a.icons[1].src);
    const secondIcon = Buffer.from(await page.evaluate(async url => [...new Uint8Array(await (await fetch(url)).arrayBuffer())], second.icons[1].src));
    assert.notDeepEqual(secondIcon, firstIcon);

    // A demo never inherits the private board kept in localStorage into its install manifest.
    await page.goto(`${origin}/board/index.html?demo=crm`);
    const demo = (await appDetails(page)).manifest;
    assert.equal(demo.name, 'Keeptrack'); assert.doesNotMatch(demo.start_url, /repo=/);

    await context.setOffline(true); await page.reload({ waitUntil: 'domcontentloaded' });
    assert.equal(await page.title(), 'Keeptrack'); assert.equal(await page.locator('body').count(), 1);
    await page.waitForFunction(() => window.kbBoardMarkup && window.KeeptrackHosted && document.querySelector('#board').children.length > 0, null, { timeout: 15000 });   // every shell script ran offline, and the board drew
    await context.setOffline(false); await context.close();
    console.log('pwa: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(error => { console.error(error); process.exit(1); });
