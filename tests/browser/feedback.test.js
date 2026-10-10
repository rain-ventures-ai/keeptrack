'use strict';

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

const root = { version: 4, layout: 'split', settings: { title: 'Test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: ['codex'], clients: ['Acme'], labels: [{ name: 'pale', color: '#dce1e7' }, { name: 'dark', color: '#334155' }], client_info: {}, next_num: 3, archive: { files: {} } };
const cards = {
  'cards/t_one.json': { id: 't_one', num: 1, title: 'First', column: 'todo', client: 'Acme', priority: 'high', due: '', labels: ['pale', 'dark'], assignees: ['alex'], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a0' },
  'cards/t_two.json': { id: 't_two', num: 2, title: 'Second', column: 'todo', client: '', priority: 'medium', due: '', labels: [], assignees: [], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-02T08:00:00.000Z', updated: '2026-10-02T08:00:00.000Z', rank: 'a1' },
};
const person = { id: 'p_one', name: 'Casey Example', company: 'Acme', role: '', email: '', phone: '', linkedin: '', stage: 'New', value: '', source: '', notes: '', next: '', next_due: '', links: [], comments: [], history: [], created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z' };
const text = x => JSON.stringify(x, null, 2) + '\n';

class Github {
  constructor(v4 = true) { this.v4 = v4; this.files = v4 ? { 'tasks.json': text(root), ...Object.fromEntries(Object.entries(cards).map(([k, v]) => [k, text(v)])), 'people/p_one.json': text(person) } : { 'tasks.json': text({ ...root, version: 3, layout: undefined, tasks: Object.values(cards), contacts: [person] }) }; this.readme = null; this.head = 'head-1'; this.n = 1; this.calls = []; this.blobs = {}; this.pending = null; this.failPatch = false; this.denyRepo = false; this.visibleRepos = [{ full_name: 'acme/another-board', permissions: { push: true } }]; }
  sha(p) { return require('node:crypto').createHash('sha1').update(this.files[p] || '').digest('hex'); }   // content-addressed, like git
  tree() { return Object.entries(this.files).map(([p, content]) => ({ path: p, type: 'blob', sha: this.sha(p), size: Buffer.byteLength(content) })); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', ''); this.calls.push({ method, path: p + u.search, body: req.postDataJSON?.(), auth: req.headers()['authorization'] || '' });
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/user/repos') && method === 'GET') return json(this.visibleRepos);
    if (p === '' && method === 'GET') return this.denyRepo ? json({ message: 'Not Found' }, 404) : json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p.startsWith('/contents/README.md') && method === 'GET') {
      if (this.readme == null) return json({ message: 'Not Found' }, 404);
      return json({ sha: 'readme-sha', size: Buffer.byteLength(this.readme), encoding: 'base64', content: Buffer.from(this.readme).toString('base64') });
    }
    if (p.startsWith('/contents/README.md') && method === 'PUT') { const b = req.postDataJSON(); this.readme = Buffer.from(b.content, 'base64').toString(); return json({ content: { sha: 'readme-sha' }, commit: { sha: 'readme-commit' } }); }
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') {
      if (!this.files['tasks.json']) return json({ message: 'Not Found' }, 404);
      return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') }, 200, { ETag: '"tasks"' });
    }
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON(); this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.head = 'head-' + ++this.n; return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p.startsWith('/contents/board/') && method === 'DELETE') { const rel = p.slice('/contents/board/'.length); delete this.files[rel]; this.head = 'head-' + ++this.n; return json({ commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
    if (p === '/git/ref/heads/main' && method === 'GET') return json({ object: { sha: this.head } }, 200, { ETag: '"' + this.head + '"' });
    if (p.startsWith('/git/commits/') && method === 'GET') return json({ tree: { sha: 'root-' + this.n } });
    if (p.startsWith('/git/trees/root-') && method === 'GET') return json({ tree: [{ path: 'board', type: 'tree', sha: 'board-' + this.n }] });
    if (p.startsWith('/git/trees/board-') && method === 'GET') return json({ truncated: false, tree: this.tree() });
    if (p.startsWith('/git/blobs/') && method === 'GET') { const sha = p.split('/').pop(), rel = Object.keys(this.files).find(x => this.sha(x) === sha); return json({ encoding: 'base64', content: Buffer.from(this.files[rel]).toString('base64') }); }
    if (p === '/git/blobs' && method === 'POST') { const b = req.postDataJSON(), sha = 'new-blob-' + ++this.n; this.blobs[sha] = b.content; return json({ sha }); }
    if (p === '/git/trees' && method === 'POST') { this.pending = req.postDataJSON().tree; return json({ sha: 'new-tree-' + ++this.n }); }
    if (p === '/git/commits' && method === 'POST') return json({ sha: 'new-commit-' + ++this.n });
    if (p === '/git/refs/heads/main' && method === 'PATCH') { if (this.failPatch) { this.failPatch = false; this.head = 'racing-head'; return json({ message: 'Reference update failed' }, 422); }
      for (const e of this.pending || []) { const rel = e.path.replace(/^board\//, ''); if (e.sha === null) delete this.files[rel]; else this.files[rel] = this.blobs[e.sha]; } this.head = req.postDataJSON().sha; return json({ object: { sha: this.head } }); }
    return json({ message: 'not mocked: ' + method + ' ' + p }, 404);
  }
}


// Feedback components on the board: destructive actions ask with ui.confirm (Cancel keeps, Confirm removes and saves),
// saved changes offer Undo through ui.toast, and no native confirm/prompt/alert ever opens.
async function openBoard(browser, api, { layout = 'classic', viewport = { width: 1280, height: 860 } } = {}) {
  const page = await browser.newPage({ viewport }), native = [];
  page.on('dialog', d => { native.push(d.type() + ': ' + d.message()); d.dismiss().catch(() => {}); });
  page.on('pageerror', e => console.error('page error:', e.message));
  await page.addInitScript(l => { localStorage.setItem('kb_repo', 'acme/board'); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_token', 'test'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); localStorage.setItem('kb_layout', l); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board'); }, layout);
  await page.route('https://api.test/**', r => api.route(r)); await page.goto(base + '/board/index.html'); await page.waitForSelector('.card, .todayhead');
  page.native = native; return page;
}
const waitFor = async (page, fn, what) => { for (let i = 0; i < 80 && !fn(); i++) await page.waitForTimeout(100); assert(fn(), what); };
const writes = api => api.calls.filter(c => ['PUT', 'PATCH', 'DELETE', 'POST'].includes(c.method)).length;

let base;
(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`; const browser = await chromium.launch({ headless: true });
  try {
    // 1. Delete a person: the confirm is an in-page alertdialog; Cancel keeps them and writes nothing.
    {
      const api = new Github(true), page = await openBoard(browser, api);
      await page.locator('#viewSw button[data-view="people"]').click(); await page.locator('.prow', { hasText: 'Casey Example' }).click();
      await page.locator('#dlgContact').waitFor({ state: 'visible' });
      const before = writes(api);
      await page.locator('#pDelete').click();
      const ask = page.getByRole('alertdialog'); await ask.waitFor();
      assert.match(await ask.textContent(), /Delete person\?.*Delete the person “Casey Example”\?.*Undo button/s);
      assert.equal(await ask.getByRole('button', { name: 'Cancel' }).evaluate(b => b === document.activeElement), true, 'a destructive confirm focuses Cancel');
      assert.match(await ask.getByRole('button', { name: 'Delete' }).getAttribute('class'), /ui-btn--danger/, 'the confirm button is the danger variant');
      await ask.getByRole('button', { name: 'Cancel' }).click();
      await ask.waitFor({ state: 'detached' }); await page.waitForTimeout(300);
      assert.equal(writes(api), before, 'Cancel writes nothing'); assert.ok(api.files['people/p_one.json'], 'Cancel keeps the person');
      assert.equal(await page.locator('#dlgContact').getAttribute('open'), '', 'the person drawer stays open after Cancel');

      // Escape also cancels.
      await page.locator('#pDelete').click(); await ask.waitFor(); await page.keyboard.press('Escape'); await ask.waitFor({ state: 'detached' });
      assert.ok(api.files['people/p_one.json'], 'Escape keeps the person');

      // 2. Confirm removes them; the change is saved, then an Undo toast appears and puts them back.
      await page.locator('#pDelete').click(); await ask.waitFor(); await ask.getByRole('button', { name: 'Delete' }).click();
      await waitFor(page, () => !api.files['people/p_one.json'], 'Delete removes the person file');
      const undo = page.locator('.ui-toast.kb-undo'); await undo.waitFor();
      assert.match(await undo.textContent(), /Delete person: Casey Example/);
      assert.equal(await page.locator('#toast:visible, #undoSnack:visible').count(), 0, 'the old toast and snackbar never show');
      await undo.getByRole('button', { name: 'Undo' }).click();
      await waitFor(page, () => !!api.files['people/p_one.json'], 'Undo restores the person file');
      assert.equal(JSON.parse(api.files['people/p_one.json']).name, 'Casey Example');
      await page.locator('.ui-toast', { hasText: 'Undid: Delete person: Casey Example' }).waitFor();
      assert.equal(await undo.count(), 0, 'the Undo toast goes once used');
      assert.deepEqual(page.native, [], 'no native dialog opened');
      await page.close();
    }
    // 3. Settings → Labels: removing a label asks first (Cancel keeps it), then removes it from the board and its card.
    {
      const api = new Github(true), page = await openBoard(browser, api);
      await page.locator('#btnSettings').click(); await page.locator('#labelBox .lbrow').first().waitFor();
      const before = writes(api), remove = () => page.locator('#labelBox [aria-label="Delete label pale"]').click();
      await remove(); const ask = page.getByRole('alertdialog'); await ask.waitFor();
      assert.match(await ask.textContent(), /Remove label\?.*Remove the “pale” label from 1 task\?/s);
      await ask.getByRole('button', { name: 'Cancel' }).click(); await ask.waitFor({ state: 'detached' }); await page.waitForTimeout(300);
      assert.equal(writes(api), before); assert.deepEqual(JSON.parse(api.files['tasks.json']).labels.map(l => l.name), ['pale', 'dark']);
      await remove(); await ask.waitFor(); await ask.getByRole('button', { name: 'Remove' }).click();
      await waitFor(page, () => JSON.parse(api.files['tasks.json']).labels.every(l => l.name !== 'pale'), 'the label is removed from the board');
      assert.deepEqual(JSON.parse(api.files['cards/t_one.json']).labels, ['dark'], 'and from the card');
      assert.deepEqual(page.native, [], 'no native dialog opened');
      await page.close();
    }
    // 4. Phones with the dock: the Undo toast sits above the dock, and a later plain toast() also uses ui.toast.
    {
      const api = new Github(true), page = await openBoard(browser, api, { layout: 'dock', viewport: { width: 390, height: 844 } });
      await page.locator('#subnav button', { hasText: 'Kanban' }).click();
      await page.locator('.card', { hasText: 'First' }).locator('.t').click(); await page.locator('#dlgCard').waitFor({ state: 'visible' });
      await page.locator('#cCol').selectOption('done'); await waitFor(page, () => JSON.parse(api.files['cards/t_one.json']).column === 'done', 'moved');
      await page.locator('#cClose').click();
      const undo = page.locator('.ui-toast.kb-undo'); await undo.waitFor(); await page.waitForTimeout(250);
      const box = await page.evaluate(() => ({ toast: document.querySelector('.ui-toast.kb-undo').getBoundingClientRect().toJSON(), dock: document.querySelector('#dock').getBoundingClientRect().toJSON(), vw: innerWidth }));
      assert(box.toast.bottom <= box.dock.top, 'the Undo toast is above the dock: ' + JSON.stringify(box));
      assert(box.toast.left >= 0 && box.toast.right <= box.vw, 'the Undo toast fits the phone width');
      await undo.getByRole('button', { name: 'Undo' }).click();
      await waitFor(page, () => JSON.parse(api.files['cards/t_one.json']).column === 'todo', 'Undo moves it back');
      assert.equal(await page.locator('.ui-toast').count(), 1, 'one toast at a time');
      assert.deepEqual(page.native, [], 'no native dialog opened');
      await page.close();
    }
    console.log('feedback browser tests passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
