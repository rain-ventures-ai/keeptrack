'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const OUT = '/opt/cursor/artifacts/screenshots';
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };

const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel);
  if (!file.startsWith(ROOT + path.sep)) {
    res.writeHead(403).end();
    return;
  }
  fs.readFile(file, (err, data) => {
    if (err) res.writeHead(404).end();
    else {
      res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
      res.end(data);
    }
  });
});

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await page.goto(`${base}/board/index.html?demo=crm`);
  await page.locator('#roBar').waitFor({ state: 'visible' });
  await page.waitForTimeout(500);

  await page.screenshot({ path: path.join(OUT, 'demo-board-project-filter.png'), fullPage: false });

  async function openClientDetails(name) {
    const pill = page.locator('.cpill', { hasText: name });
    if (await pill.count() && await pill.locator('.cpillgo').count()) {
      await pill.locator('.cpillgo').click();
      return;
    }
    const more = page.locator('.cpill.more');
    if (await more.count()) {
      await more.click();
      const row = page.locator('#clientPop .cmenurow').filter({ hasText: name });
      await row.locator('button.detail').click();
      return;
    }
    throw new Error('client not found: ' + name);
  }
  await openClientDetails('Harbour Foods');
  await page.locator('#dlgClient').waitFor({ state: 'visible' });
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, 'demo-client-north-star.png'), fullPage: false });
  await page.locator('#clClose').click();

  await page.locator('#btnFilter').click();
  await page.locator('#filterPop').waitFor({ state: 'visible' });
  const projFilter = page.locator('#fProject');
  const opts = await projFilter.locator('option').allTextContents();
  if (opts.length > 1) {
    await projFilter.selectOption({ index: 1 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(OUT, 'demo-filter-by-project.png'), fullPage: false });
  }
  await page.locator('#btnFilter').click();

  await openClientDetails('Harbour Foods');
  await page.locator('#dlgClient .prowbtn').first().click();
  await page.locator('#dlgProject').waitFor({ state: 'visible' });
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, 'demo-project-drawer.png'), fullPage: false });

  await browser.close();
  server.close();
  console.log('Wrote screenshots to', OUT);
})();
