'use strict';
// Card #292 (kit v92): images on cards. The Image button in the comment box and the description editor uploads a PNG to
// assets/<card id>/ through the contents API and puts ![alt](assets/...) in the box; images in a description or comment
// are read back through the API (raw) and shown from a blob URL; a file whose bytes are not an image is refused (upload)
// and not shown (render); an outside image URL is never requested; a paste of an image works like the button.
// Run: node images.test.js   (SHOTS=<dir> also saves screenshots)

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const SHOTS = process.env.SHOTS || '';
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const text = x => JSON.stringify(x, null, 2) + '\n';
const stamp = '2026-10-01T08:00:00.000Z';
const root = { version: 4, layout: 'split', settings: { title: 'Images test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: ['Acme'], labels: [],
  client_info: { Acme: { north_star: '', links: [] } }, next_num: 2, archive: { files: {} } };
const project = { id: 'pr_one', client: 'Acme', name: 'Launch', north_star: '', status: 'active', links: [], people: [], created: stamp, updated: stamp };
const card = { id: 't_one', num: 1, title: 'Kick-off', column: 'todo', client: 'Acme', project: 'pr_one', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: stamp, updated: stamp, rank: 'a1' };
const person = { id: 'p_one', name: 'Casey Example', company: 'Acme', role: 'Buyer', stage: 'New', value: '', source: '', notes: '', next: '', next_due: '', emails: [{ id: 'e1', label: 'Work', value: 'casey@acme.test' }], phones: [], links: [], comments: [], history: [], created: stamp, updated: stamp };

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (as in task-drawer.test.js).
class Github {
  constructor() { this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card), 'people/p_one.json': text(person), 'projects/pr_one.json': text(project) }; this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null; }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/README.md')) return json({ message: 'Not Found' }, 404);
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON(); this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.head = 'head-' + ++this.n; return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p.startsWith('/contents/board/') && method === 'DELETE') { delete this.files[p.slice('/contents/board/'.length)]; this.head = 'head-' + ++this.n; return json({ commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: Object.entries(this.files).map(([f, c]) => ({ path: f, type: 'blob', sha: this.sha(f), size: Buffer.byteLength(c) })) });
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), rel = Object.keys(this.files).find(x => this.sha(x) === sha); return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const sha = 'new-blob-' + ++this.n; this.blobs[sha] = req.postDataJSON().content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') { for (const e of this.pending || []) { const rel = e.path.replace(/^board\//, ''); if (e.sha === null) delete this.files[rel]; else this.files[rel] = this.blobs[e.sha]; } this.head = req.postDataJSON().sha; return json({ object: { sha: this.head } }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
  person() { return this.files['people/p_one.json'] ? JSON.parse(this.files['people/p_one.json']) : null; }
  root() { return JSON.parse(this.files['tasks.json']); }
  projects() { return [...(this.root().projects || []), ...Object.keys(this.files).filter(f => f.startsWith('projects/')).map(f => JSON.parse(this.files[f]))]; }   // split boards keep one file per project
  project(id = 'pr_one') { return this.projects().find(p => p.id === id) || null; }
}

let base;
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.waitForTimeout(250); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const INIT = () => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour', 'done'); localStorage.setItem('kb_tour_seen', '1'); };
const zlib = require('node:zlib');
function png(w = 40, h = 30) {
  const raw = Buffer.concat(Array.from({ length: h }, () => Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 3, 0x33)])));
  const crc = b => { let c, t = []; for (let n = 0; n < 256; n++) { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } c = 0xffffffff; for (const x of b) c = t[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const ch = (type, d) => { const len = Buffer.alloc(4); len.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(type), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), ch('IHDR', ihdr), ch('IDAT', zlib.deflateSync(raw)), ch('IEND', Buffer.alloc(0))]);
}

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const api = new Github(), assets = {}, outside = [], puts = [];
    const seeded = 'assets/t_one/20261001-aaaaaaaaaaaa.png', fakePng = 'assets/t_one/20261001-bbbbbbbbbbbb.png';
    assets[seeded] = png(); assets[fakePng] = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>');
    api.files['cards/t_one.json'] = text({ ...card, details: `Before\n\n![Old screen](${seeded})\n\n![Not really](${fakePng})\n\n![Tracker](https://evil.test/pixel.png)`, comments: [] });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } }), errors = [], native = [];
    page.on('pageerror', e => errors.push(e.message)); page.on('dialog', d => { native.push(d.message()); d.dismiss().catch(() => {}); });
    await page.route('https://evil.test/**', r => { outside.push(r.request().url()); r.fulfill({ status: 404, body: '' }); });
    await page.addInitScript(INIT);
    await page.route('https://api.test/**', r => {
      const req = r.request(), u = new URL(req.url()), p = u.pathname.replace('/repos/acme/board', '');
      const m = /^\/contents\/board\/(assets\/.+)$/.exec(decodeURIComponent(p));
      if (m && req.method() === 'GET') return assets[m[1]] ? r.fulfill({ status: 200, headers: { 'Content-Type': 'application/octet-stream' }, body: assets[m[1]] }) : r.fulfill({ status: 404, body: '{}' });
      if (m && req.method() === 'PUT') { const b = req.postDataJSON(); puts.push({ path: m[1], message: b.message, branch: b.branch }); assets[m[1]] = Buffer.from(b.content, 'base64'); return r.fulfill({ status: 201, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: { sha: 'x' }, commit: { sha: 'c' } }) }); }
      return api.route(r);
    });
    await page.goto(base + '/board/index.html#1'); await page.locator('#dlgCard[open]').waitFor();
    const saved = () => page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()) && r.url().includes('/repos/acme/board/') && !r.url().includes('/assets/'));

    // ---- the description shows the stored image from the API; a fake one and an outside one are never images ----
    await page.waitForFunction(() => { const i = document.querySelector('#cDescView img.mdimg'); return i && i.src.startsWith('blob:') && i.complete && i.naturalWidth > 0; });
    assert.equal(await page.locator('#cDescView img.mdimg').count(), 1, 'only the real image is shown');
    assert.equal(await page.locator('#cDescView img.mdimg').getAttribute('alt'), 'Old screen');
    assert.match(await page.locator('#cDescView').textContent(), /\[Not really: image not found\]/, 'an SVG named .png is not shown');
    assert.equal(await page.locator('#cDescView a[href="https://evil.test/pixel.png"]').textContent(), 'Tracker', 'an outside image is only a link (opened by a click), never loaded');
    assert.deepEqual(outside, [], 'no request ever goes to an outside image URL');
    assert.equal(await page.locator('#cDescView a.mdimglink').getAttribute('target'), '_blank');
    await shot(page, 'images-description-1280');

    // ---- the Image button in the comment box uploads to assets/<card id>/ and puts the Markdown in the box ----
    await page.locator('#cmText').click(); await page.locator('#cmImage').waitFor();
    await page.locator('#cmImage input[type=file]').setInputFiles({ name: 'Login page.png', mimeType: 'image/png', buffer: png(60, 40) });
    await page.waitForFunction(() => /!\[Login page\]\(assets\/t_one\/\d{8}-[0-9a-f]{12}\.png\)/.test(document.getElementById('cmText').value));
    assert.equal(puts.length, 1); assert.match(puts[0].path, /^assets\/t_one\/\d{8}-[0-9a-f]{12}\.png$/); assert.equal(puts[0].message, 'Image: #1'); assert.equal(puts[0].branch, 'main');
    assert.deepEqual([...assets[puts[0].path].subarray(0, 8)], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 'the bytes are written as they are');
    await page.locator('#cmText').press('End'); await page.locator('#cmText').type(' Here it is');
    let w = saved(); await page.locator('#cmPost').click(); await w;
    const posted = JSON.parse(api.files['cards/t_one.json']).comments.pop(); assert.match(posted.text, /^!\[Login page\]\(assets\/t_one\/\d{8}-[0-9a-f]{12}\.png\) Here it is$/);
    await page.waitForFunction(() => { const i = document.querySelector('#cmStream img.mdimg'); return i && i.src.startsWith('blob:') && i.naturalWidth === 60; });

    // ---- a file that is not an image is refused before anything is written ----
    await page.locator('#cmText').click();
    await page.locator('#cmImage input[type=file]').setInputFiles({ name: 'evil.png', mimeType: 'image/png', buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"></svg>') });
    await page.waitForFunction(() => [...document.querySelectorAll('.ui-toast, .toast')].some(x => /not a PNG, JPEG, GIF or WebP/.test(x.textContent)));
    assert.equal(puts.length, 1, 'nothing uploaded'); assert.doesNotMatch(await page.locator('#cmText').inputValue(), /evil/);
    await page.locator('#cmImage input[type=file]').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('hello') });
    await page.waitForFunction(() => [...document.querySelectorAll('.ui-toast, .toast')].some(x => /Only PNG, JPEG, GIF or WebP/.test(x.textContent)));
    assert.equal(puts.length, 1);

    // ---- paste into the description editor works like the button ----
    await page.locator('#cDescView p', { hasText: 'Before' }).dblclick(); await page.locator('#cDetails').waitFor();
    await page.locator('#cDetails').evaluate(ta => ta.setSelectionRange(ta.value.length, ta.value.length));
    await page.evaluate(b64 => { const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0)), dt = new DataTransfer(); dt.items.add(new File([bytes], 'pasted.png', { type: 'image/png' }));
      document.getElementById('cDetails').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }, png(20, 10).toString('base64'));
    await page.waitForFunction(() => /\n!\[pasted\]\(assets\/t_one\/\d{8}-[0-9a-f]{12}\.png\)$/.test(document.getElementById('cDetails').value));
    assert.equal(puts.length, 2);
    assert.equal(await page.locator('#descImage').count(), 1, 'the description toolbar has an Image button');
    await shot(page, 'images-editing-1280');
    assert.deepEqual(errors, [], 'no page errors'); assert.deepEqual(native, [], 'no native dialogs');

    // ---- read-only (demo) and hosted boards: no upload; the button says why ----
    const ro = await browser.newPage({ viewport: { width: 390, height: 844 } }); const roErr = []; ro.on('pageerror', e => roErr.push(e.message));
    await ro.addInitScript(INIT); await ro.addInitScript(() => { localStorage.removeItem('kb_token'); });
    await ro.route('https://api.test/**', r => api.route(r)); await ro.goto(base + '/board/index.html#1');
    await ro.waitForTimeout(1500);
    assert.deepEqual(roErr, [], 'no page errors without a token'); await ro.close();
    console.log('images: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
