'use strict';
// kit v112: the web board's strip for outside items in board/inbound/ that failed or waited longer than
// settings.inbound_alert_minutes. Names come from the tree listing; failures from tasks.json "inbound".failed.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});
const text = x => JSON.stringify(x, null, 2) + '\n';
const stamp = ms => new Date(ms).toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');

function board(rootExtra, inbound) {
  const root = { version: 4, layout: 'split', settings: { title: 'Test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: [], labels: [], client_info: {}, next_num: 2, archive: { files: {} }, ...rootExtra };
  const files = { 'tasks.json': text(root), 'cards/t_one.json': text({ id: 't_one', num: 1, title: 'First', column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a0' }) };
  inbound.forEach(n => { files['inbound/' + n] = '{}'; });
  const sha = p => crypto.createHash('sha1').update(files[p]).digest('hex');
  return async route => {
    const req = route.request(), u = new URL(req.url()), p = u.pathname.replace('/repos/acme/board', ''), m = req.method();
    const json = (body, status = 200) => route.fulfill({ status, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (p === '/user') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '' && m === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/board/tasks.json')) return json({ sha: sha('tasks.json'), encoding: 'base64', content: Buffer.from(files['tasks.json']).toString('base64') });
    if (p === '/git/ref/heads/main') return json({ object: { sha: 'head-1' } });
    if (p.startsWith('/git/commits/')) return json({ tree: { sha: 'root-1' } });
    if (p.startsWith('/git/trees/root-')) return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-1' }] });
    if (p.startsWith('/git/trees/board-')) return json({ truncated: false, tree: Object.keys(files).map(f => ({ path: f, type: 'blob', sha: sha(f), size: files[f].length })) });
    if (p.startsWith('/git/blobs/')) { const s = p.split('/').pop(), f = Object.keys(files).find(x => sha(x) === s); return json({ encoding: 'base64', content: Buffer.from(files[f]).toString('base64') }); }
    return json({ message: 'not mocked' }, 404);
  };
}

async function open(browser, base, api) {
  const page = await browser.newPage(); page.on('pageerror', e => console.error('page error:', e.message));
  await page.addInitScript(() => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', 'classic'); sessionStorage.setItem('kb_view', 'board'); });
  await page.route('https://api.test/**', api); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card, .todayhead'); return page;
}

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const now = Date.now(), fresh = stamp(now - 5 * 60000) + '-form-a.json', old = stamp(now - 5 * 3600000) + '-form-b.json', bad = stamp(now - 60000) + '-form-c.json';
    // a fresh item alone: no strip
    let page = await open(browser, base, board({}, [fresh]));
    assert.equal(await page.locator('#inboundBar').isHidden(), true, 'a fresh item shows nothing'); await page.close();
    // an old one and a failed one: one strip with both counts
    page = await open(browser, base, board({ inbound: { done: {}, failed: { [bad]: { error: 'bad JSON', since: '2026-10-29T00:00:00Z' } } } }, [fresh, old, bad]));
    const bar = page.locator('#inboundBar'); await bar.waitFor({ state: 'visible' });
    const words = await bar.textContent();
    assert.match(words, /1 could not be handled/); assert.match(words, /1 has waited 5 hours/); assert.match(words, /keeptrack\.py inbound --status/);
    await page.close();
    // a longer alert time hides the old item; the failure stays
    page = await open(browser, base, board({ settings: { title: 'Test', inbound_alert_minutes: 600 }, inbound: { failed: { [bad]: { error: 'x' } } } }, [old, bad]));
    await page.locator('#inboundBar').waitFor({ state: 'visible' });
    assert.doesNotMatch(await page.locator('#inboundBar').textContent(), /waited/); await page.close();
    console.log('inbound bar: ok');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
