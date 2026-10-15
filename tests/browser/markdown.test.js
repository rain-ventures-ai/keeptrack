'use strict';
// Markdown in descriptions and comments (kit v62): headings, lists, checklist items, tables, quotes, code and emphasis
// render as safe DOM; HTML stays text; Raw shows the saved text; the editor has Write/Preview and a toolbar; card faces
// show the words without the marks. Run: node markdown.test.js

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const SHOTS = process.env.SHOTS || '';   // a folder: also save screenshots
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const text = x => JSON.stringify(x, null, 2) + '\n';
const root = { version: 4, layout: 'split', settings: { title: 'Mentions test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }, { github: 'sam', name: 'Sam' }], agents: [], clients: ['Acme'], labels: [{ name: 'urgent', color: '#dce1e7' }], client_info: {}, next_num: 4, archive: { files: {} } };
const card = (id, num, title, extra) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num, ...extra });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (same shape as split-storage.test.js).
class Github {
  constructor() {
    const c = (id, at, by, text) => ({ id, at, by, text });
    const _filler = Array.from({ length: 12 }, (_, i) => c('c_f' + i, `2026-10-0${1 + (i % 5)}T09:${String(10 + i).padStart(2, '0')}:00.000Z`, 'sam', 'Progress note ' + (i + 1) + '. '.repeat(1) + 'Some longer text so the stream needs to scroll. '.repeat(4)));
    this.files = { 'tasks.json': text({ ...root, next_num: 3 }),
      'cards/t_one.json': text(card('t_one', 1, 'Write the case study', { details: "## Why\nThe notifier is **live**; the phone app is *not* set up yet. See #2 and [the brief](https://example.test/brief).\n\n- [x] Code merged\n- [ ] Subscribe on the phone\n  - nested step with `ntfy.sh`\n1. first\n2. second\n\n| Option | Score | Why |\n| --- | --- | --- |\n| Keep public ntfy.sh | 8/10 | works now |\n| Self-host | 5/10 | more set-up |\n\n> a quote\n---\n```\n<b>code stays</b>\n```\n<img src=x onerror=\"window.__xss=1\"> and [bad](javascript:alert(1)) stay text. snake_case_name stays.", comments: [c('c_a', '2026-10-02T10:00:00.000Z', 'sam', '**Options**\n1. Keep it: 8/10\n2. Drop it: 3/10\n\n**Recommendation:** 1, because it works. Full review: [the review](https://example.test/review.md).')] })),
      'cards/t_two.json': text(card('t_two', 2, 'Book the workshop room')) };
    this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null; this.writes = 0;
  }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (method !== 'GET') this.writes++;
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/README.md')) return json({ message: 'Not Found' }, 404);
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
    if (p.startsWith('/contents/board/') && method === 'GET') { const rel = p.slice('/contents/board/'.length); return this.files[rel] ? json({ sha: this.sha(rel), encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }) : json({ message: 'Not Found' }, 404); }
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
  card(id = 't_one') { return this.files[`cards/${id}.json`] ? JSON.parse(this.files[`cards/${id}.json`]) : null; }
}

async function open(browser, base, { view = 'mentions', me = 'alex', viewport = { width: 1280, height: 900 }, theme = '' } = {}) {
  const api = new Github(), page = await browser.newPage({ viewport }), errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(([v, m, th]) => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', m); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_tour', 'done'); if (th) localStorage.setItem('kb_theme', th); sessionStorage.setItem('kb_view', v); }, [view, me, theme]);
  await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html');
  await page.waitForFunction(v => document.body.dataset.view === v && document.getElementById('board').childElementCount > 0, view);
  page.errors = errors; return page;
}

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await open(browser, base, { view: 'board' });
    await page.waitForSelector('.card');
    const face = await page.locator('.card .n').first().textContent();
    assert.ok(face.startsWith('Why\nThe notifier is live;'), 'the card face shows the words, not the marks: ' + JSON.stringify(face.slice(0, 60)));
    await page.evaluate(() => { location.hash = '#1'; }); await page.locator('#dlgCard[open]').waitFor();
    const v = page.locator('#cDescView');
    assert.equal(await v.locator('h4.mdh2').textContent(), 'Why');
    assert.equal(await v.locator('strong').first().textContent(), 'live'); assert.equal(await v.locator('em').first().textContent(), 'not');
    assert.equal(await v.locator('li.mdtask input[type=checkbox]').count(), 2); assert.equal(await v.locator('li.mdtask input:checked').count(), 1);
    assert.equal(await v.locator('ul ul li code').textContent(), 'ntfy.sh', 'nested list with inline code');
    assert.equal(await v.locator('ol > li').count(), 2);
    assert.deepEqual(await v.locator('table th').allTextContents(), ['Option', 'Score', 'Why']); assert.equal(await v.locator('table tbody tr').count(), 2);
    assert.equal(await v.locator('blockquote').textContent(), 'a quote'); assert.equal(await v.locator('hr').count(), 1);
    assert.equal(await v.locator('pre code').textContent(), '<b>code stays</b>');
    assert.equal(await v.locator('img, b, script').count(), 0, 'HTML is never parsed');
    assert.equal(await page.evaluate(() => window.__xss), undefined);
    assert.ok((await v.textContent()).includes('[bad](javascript:alert(1))'), 'a javascript: link stays text');
    assert.ok((await v.textContent()).includes('snake_case_name'), 'underscores inside words stay');
    assert.equal(await v.locator('a.mref').textContent(), '#2'); assert.equal(await v.locator('a[target=_blank]').textContent(), 'the brief');
    const cm = page.locator('#cmStream .cmcard[data-cid="c_a"] .cmbody');
    assert.equal(await cm.locator('ol li').count(), 2, 'comments render Markdown too'); assert.equal(await cm.locator('strong').first().textContent(), 'Options');
    // a page the comment links to: opens in a new tab, and one tap adds it to the card's links
    const rv = cm.locator('a', { hasText: 'the review' }); assert.equal(await rv.getAttribute('target'), '_blank');
    const addBtn = page.locator('#cmStream .cmcard[data-cid="c_a"] .cmlinkbtn'); assert.equal(await addBtn.count(), 1);
    assert.match(await addBtn.textContent(), /Add to card links: the review/);
    await addBtn.click();
    await page.waitForFunction(() => [...document.querySelectorAll('#cLinkList a')].some(a => a.href === 'https://example.test/review.md'));
    await page.waitForFunction(() => !document.querySelector('#cmStream .cmcard[data-cid="c_a"] .cmlinkbtn'));
    assert.equal(await page.locator('#cDescView .cmlinkbtn').count(), 0);
    await shot(page, 'md-formatted');
    // Raw: the saved text, for descriptions and comments, remembered in this browser
    await page.locator('#cRawBtn').click();
    assert.ok((await v.textContent()).startsWith('## Why'), 'raw shows the marks'); assert.equal(await v.locator('h4').count(), 0);
    assert.ok((await cm.textContent()).startsWith('**Options**'));
    assert.equal(await page.evaluate(() => localStorage.getItem('kb_md_raw')), '1');
    assert.equal((await page.locator('#cRawBtn').textContent()).trim(), 'Formatted');
    await page.locator('#cRawBtn').click(); assert.equal(await v.locator('h4').count(), 1);
    // Editor: toolbar wraps the selection, Preview renders, Save stores plain Markdown
    await page.locator('#cDescBtn').click(); await page.locator('#cDetails').waitFor();
    await page.locator('#cDetails').fill('plan'); await page.evaluate(() => { const t = document.getElementById('cDetails'); t.setSelectionRange(0, 4); });
    await page.locator('.mdtool[title="Bold"]').click();
    assert.equal(await page.locator('#cDetails').inputValue(), '**plan**');
    await page.locator('#cDetails').press('End'); await page.locator('#cDetails').type('\nstep one');
    await page.locator('.mdtool[title="Bulleted list"]').click();
    assert.equal(await page.locator('#cDetails').inputValue(), '**plan**\n- step one');
    await page.locator('#descPreview').click();
    assert.ok(await page.locator('#cDetails').isHidden()); assert.equal(await page.locator('#descPrev strong').textContent(), 'plan'); assert.equal(await page.locator('#descPrev li').textContent(), 'step one');
    await shot(page, 'md-preview');
    await page.locator('#descWrite').click(); assert.ok(await page.locator('#cDetails').isVisible());
    await page.locator('#cDescSave').click();
    await page.waitForFunction(() => document.querySelector('#cDescView strong') && document.querySelector('#cDescView strong').textContent === 'plan');
    // editor reopens on Write
    await page.locator('#cDescBtn').click(); assert.ok(await page.locator('#cDetails').isVisible()); assert.ok(await page.locator('#descPrev').isHidden());
    await page.locator('#cDescCancel').click();
    assert.deepEqual(page.errors, []); await page.close();
    // phone width, dark theme: the table scrolls inside its box, the page does not
    const ph = await open(browser, base, { view: 'board', viewport: { width: 390, height: 800 }, theme: 'dark' });
    await ph.waitForSelector('.card'); await ph.evaluate(() => { location.hash = '#1'; }); await ph.locator('#dlgCard[open]').waitFor();
    const over = await ph.evaluate(() => { const d = document.querySelector('#dlgCard .dbody') || document.querySelector('#dlgCard'); return d.scrollWidth - d.clientWidth; });
    assert.ok(over <= 1, 'no sideways scroll in the drawer: ' + over);
    await ph.waitForTimeout(500); await shot(ph, 'md-phone-dark'); assert.deepEqual(ph.errors, []); await ph.close();
    console.log('markdown: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
