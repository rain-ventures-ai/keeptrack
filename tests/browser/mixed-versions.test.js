'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { execSync } = require('node:child_process');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const FIXTURE = path.join(ROOT, 'tests/fixtures/v4_kit17');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };

function walkBoard(relDir = '') {
  const dir = path.join(FIXTURE, relDir);
  const out = {};
  for (const name of fs.readdirSync(dir)) {
    if (name === 'fixture.json') continue;
    const rel = relDir ? `${relDir}/${name}` : name;
    const full = path.join(dir, name);
    if (fs.statSync(full).isDirectory()) Object.assign(out, walkBoard(rel));
    else out[rel] = fs.readFileSync(full, 'utf8');
  }
  return out;
}

const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel);
  if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => {
    if (err) res.writeHead(404).end();
    else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); }
  });
});

class Github {
  constructor(files) {
    this.files = { ...files };
    this.head = 'head-1';
    this.n = 1;
    this.blobs = {};
    this.pending = null;
  }
  sha(p) { return require('node:crypto').createHash('sha1').update(this.files[p] || '').digest('hex'); }
  tree() { return Object.entries(this.files).map(([p, content]) => ({ path: p, type: 'blob', sha: this.sha(p), size: Buffer.byteLength(content) })); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200) => route.fulfill({ status, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/board/') && method === 'GET') {
      const rel = p.slice('/contents/board/'.length);
      if (!this.files[rel]) return json({ message: 'Not Found' }, 404);
      const content = this.files[rel];
      return json({ sha: this.sha(rel), size: Buffer.byteLength(content), encoding: 'base64', content: Buffer.from(content).toString('base64') });
    }
    if (p.startsWith('/contents/board/') && method === 'PUT') {
      const rel = p.slice('/contents/board/'.length);
      const b = req.postDataJSON();
      this.files[rel] = Buffer.from(b.content, 'base64').toString();
      this.head = 'head-' + ++this.n;
      return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } });
    }
    if (p.startsWith('/contents/board/') && method === 'DELETE') {
      const rel = p.slice('/contents/board/'.length);
      delete this.files[rel];
      this.head = 'head-' + ++this.n;
      return json({ commit: { sha: this.head, tree: { sha: 'root-' + this.n } } });
    }
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: this.tree() });
    if (p.startsWith('/git/blobs/') && method === 'GET') {
      const sha = p.split('/').pop();
      const rel = Object.keys(this.files).find(x => this.sha(x) === sha);
      return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') });
    }
    if (p === '/git/blobs' && method === 'POST') { const b = req.postDataJSON(); const sha = 'blob-' + ++this.n; this.blobs[sha] = b.content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') {
      for (const e of this.pending || []) {
        const rel = e.path.replace(/^board\//, '');
        if (e.sha === null) delete this.files[rel];
        else this.files[rel] = this.blobs[e.sha];
      }
      this.head = req.postDataJSON().sha;
      return json({ object: { sha: this.head } });
    }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
}

(async () => {
  const legacyJs = execSync('git show 400c9bc:board/board.js', { cwd: ROOT, encoding: 'utf8' });
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github(walkBoard());
    const page = await browser.newPage();
    await page.addInitScript(() => {
      localStorage.setItem('kb_repo', 'acme/board');
      localStorage.setItem('kb_branch', 'main');
      localStorage.setItem('kb_path', 'board/tasks.json');
      localStorage.setItem('kb_token', 'test');
      localStorage.setItem('kb_me', 'alex');
      localStorage.setItem('kb_api', 'https://api.test');
      localStorage.setItem('kb_view', 'board');
    });
    await page.route('https://api.test/**', r => api.route(r));
    await page.route('**/board/board.js', route => route.fulfill({ status: 200, contentType: 'text/javascript', body: legacyJs }));
    await page.goto(base + '/board/index.html');
    await page.waitForSelector('.card');
    assert.ok(api.files['projects/pr_pilot01ab.json'], 'project file present before edit');
    await page.locator('.card').first().dblclick();
    await page.locator('#cTitle').fill('Call Acme (legacy page edit)');
    const saved = page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().includes('/repos/acme/board/'));
    await page.locator('#cTitle').blur();
    await saved;
    assert.ok(api.files['projects/pr_pilot01ab.json'], 'project file must survive a v16 web save');
    const proj = JSON.parse(api.files['projects/pr_pilot01ab.json']);
    assert.equal(proj.name, 'Pilot rollout');
    const card = JSON.parse(api.files['cards/t_first.json']);
    assert.match(card.title, /legacy page edit/);
    await page.close();

    const current = await browser.newPage();
    await current.addInitScript(() => {
      localStorage.setItem('kb_repo', 'acme/board');
      localStorage.setItem('kb_branch', 'main');
      localStorage.setItem('kb_path', 'board/tasks.json');
      localStorage.setItem('kb_token', 'test');
      localStorage.setItem('kb_me', 'alex');
      localStorage.setItem('kb_api', 'https://api.test');
      localStorage.setItem('kb_view', 'board');
    });
    await current.route('https://api.test/**', r => api.route(r));
    await current.goto(base + '/board/index.html');
    await current.waitForSelector('.card');
    assert.ok(await current.locator('.card').filter({ hasText: 'legacy page edit' }).count());
    await current.close();
    console.log('mixed-versions: ok');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
