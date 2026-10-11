'use strict';
// The Settings dialog (#dlgSettings): four tabs (Preferences, Board, Connection, Agents & integrations) built from one section
// template, with a faked GitHub API. Clicking Settings opens Preferences; the app opens Connection itself only for a board with
// no token; every old deep link lands on the right tab and section; a Preferences change and a Board change save where they
// should; Health runs inline; exporting settings and forgetting the token ask first; nothing scrolls sideways at 390px and the
// tab strip is never clipped; the demo board shows a read-only banner; no native dialog ever opens.
// Run: node settings.test.js   (SHOTS=<dir> also saves screenshots)

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
const root = { version: 4, layout: 'split', settings: { title: 'Settings test' }, columns: [{ id: 'todo', name: 'To do' }, { id: 'in-progress', name: 'In progress' }, { id: 'done', name: 'Done' }], people: [{ github: 'alex', name: 'Alex' }], agents: [], clients: ['Acme'], labels: [{ name: 'pale', color: '#dce1e7' }], client_info: {}, next_num: 2, archive: { files: {} } };
const card = (id, num, title) => ({ id, num, title, column: 'todo', client: '', priority: 'medium', due: '', labels: ['pale'], assignees: ['alex'], details: '', links: [], contacts: [], todos: [], comments: [], history: [], claim: null, created: '2026-10-01T08:00:00.000Z', updated: '2026-10-01T08:00:00.000Z', rank: 'a' + num });

// A small GitHub: contents API for reads and single-file writes, git data API for multi-file commits (as in task-drawer.test.js),
// plus what Health reads: the branch, the kit version and the rate limit.
class Github {
  constructor() { this.files = { 'tasks.json': text(root), 'cards/t_one.json': text(card('t_one', 1, 'First')) }; this.head = 'head-1'; this.n = 1; this.blobs = {}; this.pending = null; this.writes = 0; }
  sha(p) { return crypto.createHash('sha1').update(this.files[p] || '').digest('hex'); }
  async route(route) {
    const req = route.request(), u = new URL(req.url()), method = req.method(), p = u.pathname.replace('/repos/acme/board', '');
    const json = (body, status = 200) => route.fulfill({ status, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (method !== 'GET') this.writes++;
    if (p === '/user' && method === 'GET') return json({ login: 'alex' });
    if (p.startsWith('/user/repos')) return json([]);
    if (p === '/rate_limit') return json({ resources: { core: { remaining: 4900, limit: 5000 } } });
    if (p === '' && method === 'GET') return json({ full_name: 'acme/board', private: true, permissions: { push: true }, default_branch: 'main' });
    if (p === '/branches/main') return json({ name: 'main' });
    if (p.startsWith('/contents/board/KIT_VERSION')) return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/plain' }, body: '999' });
    if (p.startsWith('/contents/README.md')) return json({ message: 'Not Found' }, 404);
    if (p.startsWith('/contents/board/tasks.json') && method === 'GET') return json({ sha: this.sha('tasks.json'), size: Buffer.byteLength(this.files['tasks.json']), encoding: 'base64', content: Buffer.from(this.files['tasks.json']).toString('base64') });
    if (p.startsWith('/contents/board/') && method === 'PUT') { const rel = p.slice('/contents/board/'.length), b = req.postDataJSON(); this.files[rel] = Buffer.from(b.content, 'base64').toString(); this.head = 'head-' + ++this.n; return json({ content: { sha: this.sha(rel) }, commit: { sha: this.head, tree: { sha: 'root-' + this.n } } }); }
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
  root() { return JSON.parse(this.files['tasks.json']); }
}

let base;
const shot = async (page, name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + '.png') }); } };
const TABS = ['Prefs', 'Board', 'Conn', 'Agents'];
async function open(browser, { width = 1280, height = 860, token = 'test', demo = false, repo = 'acme/board' } = {}) {
  const api = new Github(), page = await browser.newPage({ viewport: { width, height } }), errors = [];
  page.on('pageerror', e => errors.push(e.message)); page.on('dialog', d => { errors.push('native dialog: ' + d.message()); d.dismiss(); });
  await page.addInitScript(([token, repo]) => {
    if (repo) { localStorage.setItem('kb_repo', repo); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); }
    if (token) localStorage.setItem('kb_token', token);
    localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board');
    window.__copied = ''; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async t => { window.__copied = t; } } });
  }, [token, demo ? '' : repo]);
  await page.route('https://api.test/**', r => api.route(r));
  await page.goto(base + '/board/index.html' + (demo ? '?demo=board' : ''));
  if (token && !demo) await page.waitForSelector('.card'); else await page.waitForTimeout(800);
  page.errors = errors; page.api = api; return page;
}
const selected = page => page.evaluate(() => (document.querySelector('#setTabs [aria-selected="true"], #dlgSettings .stabs [aria-selected="true"]') || {}).id);
const visiblePanel = page => page.evaluate(() => [...document.querySelectorAll('#dlgSettings [role=tabpanel]')].filter(p => !p.hidden).map(p => p.id).join());
const inView = (page, id) => page.evaluate(id => { const d = document.getElementById('dlgSettings').getBoundingClientRect(), r = document.getElementById(id).getBoundingClientRect(); return r.top >= d.top - 1 && r.top < d.bottom - 40; }, id);
async function settle(page) { await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))); await page.waitForTimeout(80); }

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // 1. Clicking Settings opens Preferences, every time, whatever tab was open before.
    {
      const page = await open(browser);
      await page.locator('#btnSettings').click(); await page.locator('#dlgSettings[open]').waitFor();   // a real click on the header button
      assert.equal(await selected(page), 'tabPrefs'); assert.equal(await visiblePanel(page), 'panelPrefs');
      await page.locator('#tabAgents').click(); assert.equal(await visiblePanel(page), 'panelAgents'); await page.locator('#sClose').click();
      await page.evaluate(() => document.getElementById('btnSettings').click()); assert.equal(await selected(page), 'tabPrefs', 'Settings opens on Preferences again');
      // the section template: icon + title, scope tag, purpose, Learn more; buttons are ui.button
      const sec = page.locator('#secLook');
      assert.equal(await sec.locator('.ui-section__title .ui-i').count(), 1); assert.match(await sec.locator('.setsec__scope').textContent(), /This browser/);
      assert.match(await sec.locator('.setsec__learn').getAttribute('href'), /\/docs\/help\/getting-started\.md$/);
      assert.match(await page.locator('#colSet .setsec__scope').textContent(), /Shared board/);
      const plain = await page.evaluate(() => [...document.querySelectorAll('#dlgSettings [role=tabpanel] button:not([class*="ui-"]):not(.cwh):not(.agpick)')].map(b => b.outerHTML.slice(0, 120)));
      assert.deepEqual(plain, [], 'every settings button is a ui.button');
      assert.equal(await page.locator('#sDone').count(), 0, 'no sticky Done footer');

      // 2. A Preferences change (theme) is saved in this browser and applied at once.
      await page.locator('#sTheme').selectOption('dark');
      assert.equal(await page.evaluate(() => localStorage.getItem('kb_theme')), 'dark'); assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'dark');
      // Notifications live in Preferences now (the old Alerts tab)
      assert.equal(await page.locator('#alOn').isVisible(), true); assert.equal(await page.locator('#alChip').textContent(), 'Off');

      // 3. A Board change saves to the shared board file: add a label, and add a column.
      await page.locator('#tabBoard').click(); await page.locator('#labelBox .lbrow').first().waitFor();
      let w = page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()));
      await page.locator('#labelBox input[aria-label="New label name"]').fill('urgent'); await page.locator('#labelBox button', { hasText: 'Add label' }).click(); await w;
      await page.waitForFunction(() => [...document.querySelectorAll('#labelBox input[aria-label^="Rename label"]')].some(i => i.value === 'urgent'));
      assert(page.api.root().labels.some(l => l.name === 'urgent'), 'the new label is in the board file');
      w = page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()));
      await page.locator('#colNew').fill('Review'); await page.locator('#colAdd').click(); await w;
      assert.deepEqual(page.api.root().columns.map(c => c.name), ['To do', 'In progress', 'Review', 'Done']);

      // 4. Health runs inline: "Test these values" in the connection form stays on Connection and fills the Health list.
      await page.locator('#tabConn').click(); assert.equal(await page.locator('#bThisChip').textContent(), 'Connected');
      await page.locator('#bEditBtn').click(); await page.locator('#sTest').click();
      await page.waitForFunction(() => /All good|problem|warning/.test(document.getElementById('ckChip').textContent));
      assert.equal(await selected(page), 'tabConn', 'Test these values does not change tab'); assert.equal(await page.locator('#ckList .ck').first().isVisible(), true);
      assert.match(await page.locator('#ckChip').textContent(), /^All good/, 'every check passes on the fake API: ' + await page.locator('#ckList').textContent());
      await page.locator('#ckRun').click(); await page.waitForFunction(() => /^All good/.test(document.getElementById('ckChip').textContent) && !document.getElementById('ckRun').disabled);
      assert.equal(await page.locator('#ckCopy').isVisible(), true);

      // 5. Moving settings and forgetting the token ask first; Cancel does nothing.
      await page.locator('#secAdv .ui-section__toggle').click(); await page.locator('#xCode').scrollIntoViewIfNeeded();
      assert.match(await page.locator('#sDanger .ui-banner--danger').textContent(), /secrets/);
      for (const id of ['xCode', 'xLink']) {
        await page.locator('#' + id).click(); const ask = page.getByRole('alertdialog'); await ask.waitFor();
        assert.match(await ask.textContent(), /not encrypted/); await ask.locator('button', { hasText: 'Cancel' }).click(); await ask.waitFor({ state: 'detached' });
        assert.equal(await page.evaluate(() => window.__copied), '', id + ': Cancel copies nothing');
      }
      await page.locator('#xCode').click(); await page.getByRole('alertdialog').locator('button', { hasText: 'Copy settings code' }).click();
      await page.waitForFunction(() => /^kbcfg1\./.test(window.__copied));
      await page.locator('#sForget').click(); const fa = page.getByRole('alertdialog'); await fa.waitFor(); assert.match(await fa.textContent(), /Forget this board token/);
      await fa.locator('button', { hasText: 'Cancel' }).click(); await fa.waitFor({ state: 'detached' });
      assert.equal(await page.evaluate(() => localStorage.getItem('kb_token')), 'test', 'Cancel keeps the token'); assert.equal(await page.locator('#dlgSettings').getAttribute('open'), '');

      // 6. Agents & integrations: the chooser lists three integrations with status chips and takes you to each section.
      await page.locator('#tabAgents').click();
      assert.deepEqual(await page.locator('#agChooser .agpick b').allTextContents(), ['@claude in task comments', 'Claude or Codex in your chat app', 'Email contact sync']);
      assert.deepEqual(await page.locator('#agChooser .schip').allTextContents(), ['Off', 'In your app', 'Off']);
      await page.locator('#sUseEmail').check(); assert.equal(await page.locator('#agEmailChip').textContent(), 'On'); assert.equal(await page.evaluate(() => localStorage.getItem('kb_email_sync')), '1');
      await page.locator('#agChooser .agpick').nth(2).click(); await page.waitForTimeout(600); assert.equal(await inView(page, 'agEmail'), true, 'the chooser scrolls to Email contact sync');
      assert.equal(await page.locator('#dlgSettings [id^="ag"] .sprompt button', { hasText: 'Copy setup prompt' }).count() >= 2, true, 'one setup-prompt helper, one label');

      // 7. At 1280px the tab list sits left of the panel.
      const lay = await page.evaluate(() => { const t = document.querySelector('#dlgSettings .stabs').getBoundingClientRect(), p = document.getElementById('panelAgents').getBoundingClientRect(); return { tr: t.right, pl: p.left, th: t.height }; });
      assert(lay.tr <= lay.pl, 'two columns: the tab list is left of the panel'); assert(lay.th > 100, 'the tab list is vertical');
      await shot(page, 'settings-1280-agents');
      assert.deepEqual(page.errors, []); await page.close();
    }

    // 8. Every old deep link lands on the right tab and section.
    {
      const page = await open(browser, { width: 390, height: 844 });
      const links = [['general', 'tabPrefs'], ['alerts', 'tabPrefs', 'secAlerts'], ['boards', 'tabConn', 'secBoards'], ['conn', 'tabConn', 'bThis'], ['checks', 'tabConn', 'secHealth'],
        ['claude', 'tabAgents', 'agClaude'], ['email', 'tabAgents', 'agEmail'], ['archive', 'tabBoard', 'secArchive'], ['labels', 'tabBoard', 'labelSec'], ['columns', 'tabBoard', 'colSet'], ['move', 'tabConn', 'secMove'], ['board', 'tabBoard'], ['agents', 'tabAgents']];
      for (const [name, tab, sec] of links) {
        await page.evaluate(n => window.kbSettings.open(n), name); await settle(page); await page.waitForTimeout(150);
        assert.equal(await selected(page), tab, `settingsTab('${name}') opens ${tab}`);
        if (sec) assert.equal(await inView(page, sec), true, `settingsTab('${name}') shows ${sec}`);
        if (name === 'conn') { assert.equal(await page.locator('#bEditFold').getAttribute('open'), '', "'conn' opens the connection form"); assert.equal(await page.evaluate(() => document.activeElement.id), 'sToken'); }
        if (name === 'checks') await page.waitForFunction(() => document.querySelectorAll('#ckList .ck').length > 3, null, { timeout: 15000 });
        if (name === 'move') assert.equal(await page.locator('#xPaste').isVisible(), true, "'move' opens Advanced");
        await page.locator('#sClose').click();
      }
      // entry points elsewhere: Help → agent setup, the board switcher's "Manage boards…"
      await page.evaluate(() => document.getElementById('btnHelp').click()); await page.locator('#hAgentSetup').click(); assert.equal(await selected(page), 'tabAgents'); await page.locator('#sClose').click();

      // 9. Phone: no sideways scroll on any tab (with every fold open), and the tab strip is never clipped.
      await page.evaluate(() => document.getElementById('btnSettings').click());
      for (const t of TABS) {
        await page.locator('#tab' + t).click();
        await page.evaluate(() => { const p = document.querySelector('#dlgSettings [role=tabpanel]:not([hidden])'); p.querySelectorAll('details').forEach(d => { d.open = true; }); p.querySelectorAll('.ui-section__toggle[aria-expanded=false]').forEach(b => b.click()); });
        if (t === 'Agents') await page.locator('#sUseClaude').check();
        await settle(page);
        const m = await page.evaluate(() => { const d = document.getElementById('dlgSettings'), s = document.querySelector('#dlgSettings .stabs'), sr = s.getBoundingClientRect();
          return { dlg: d.scrollWidth - d.clientWidth, doc: document.documentElement.scrollWidth - window.innerWidth, strip: s.scrollWidth - s.clientWidth,
            out: [...s.querySelectorAll('.ui-tab')].filter(b => { const r = b.getBoundingClientRect(); return r.left < sr.left - 0.5 || r.right > sr.right + 0.5; }).map(b => b.id),
            wide: [...document.querySelectorAll('#dlgSettings [role=tabpanel]:not([hidden]) *')].filter(x => x.offsetParent && x.getBoundingClientRect().right > d.getBoundingClientRect().right + 0.5).map(x => x.id || x.className).slice(0, 5) }; });
        assert(m.dlg <= 1 && m.doc <= 0, `${t} at 390px scrolls sideways (${m.dlg}px, page ${m.doc}px): ${m.wide}`);
        assert(m.strip <= 1 && !m.out.length, `the tab strip is clipped at 390px (${m.strip}px, ${m.out})`);
        await shot(page, 'settings-390-' + t.toLowerCase());
      }
      assert.deepEqual(page.errors, []); await page.close();
    }

    // 10. A board with no token: the app opens Settings itself, on Connection with the form open.
    {
      const page = await open(browser, { width: 390, height: 844, token: '' }); await page.locator('#dlgSettings[open]').waitFor();
      assert.equal(await selected(page), 'tabConn'); assert.equal(await page.locator('#bEditFold').getAttribute('open'), ''); assert.equal(await page.locator('#bThisChip').textContent(), 'No token');
      assert.equal(await page.locator('#sTokenReuse').count(), 1);
      await page.locator('#sClose').click(); await page.evaluate(() => document.getElementById('btnSettings').click()); assert.equal(await selected(page), 'tabPrefs', 'a click on Settings still opens Preferences');
      assert.deepEqual(page.errors, []); await page.close();
    }

    // 11. No board yet: Connection shows the Add-a-board wizard first and the manual form folded.
    {
      const page = await open(browser, { width: 1280, height: 860, token: '', repo: '' });
      await page.evaluate(() => window.kbSettings.open('connect')); await settle(page);
      const order = await page.evaluate(() => [...document.querySelectorAll('#panelConn > .setsec')].filter(s => !s.hidden).map(s => s.id));
      assert.equal(order[0], 'secBoards', 'the wizard comes first: ' + order); assert.equal(await page.locator('#bWiz').isVisible(), true);
      assert.equal(await page.locator('#bEditFold').getAttribute('open'), null, 'the manual form is folded'); assert.match(await page.locator('#bEditBtn').textContent(), /by hand/);
      assert.equal(await page.locator('#secHealth').isHidden(), true); assert.match(await page.locator('#bState').textContent(), /No board yet/);
      assert.deepEqual(page.errors, []); await page.close();
    }

    // 12. The demo board: a read-only banner instead of "No board connected" and an open form.
    {
      const page = await open(browser, { width: 390, height: 844, demo: true }); await page.locator('.card').first().waitFor();
      await page.evaluate(() => document.getElementById('btnSettings').click()); await page.locator('#tabConn').click();
      assert.match(await page.locator('#bState .ui-banner').textContent(), /read-only demo/); assert.equal(await page.locator('#bThis').isHidden(), true); assert.equal(await page.locator('#secHealth').isHidden(), true);
      await page.locator('#tabBoard').click(); assert.match(await page.locator('#sBoardRo .ui-banner').textContent(), /Demo board/); assert.equal(await page.locator('#colAdd').isDisabled(), true);
      await shot(page, 'settings-390-demo-board');
      assert.deepEqual(page.errors, []); await page.close();
    }
    // 13. "Save & connect" to another repo waits for queued saves (button disabled, says so); Cancel or closing Settings
    // meanwhile abandons it, and an uninterrupted one switches with the values typed before the wait.
    for (const how of ['cancel', 'esc', 'wait']) {
      const page = await open(browser);
      await page.route('https://api.test/**', async r => { if (r.request().method() !== 'GET') await new Promise(z => setTimeout(z, 1500)); return page.api.route(r); });
      await page.evaluate(() => window.kbSettings.open('labels')); await page.locator('#labelBox .lbrow').first().waitFor();
      await page.locator('#labelBox input[aria-label="New label name"]').fill('urgent'); await page.locator('#labelBox button', { hasText: 'Add label' }).click();
      await page.evaluate(() => window.kbSettings.open('conn'));
      await page.locator('#sRepo').fill('acme/other'); await page.locator('#sBranch').fill('dev'); await page.locator('#sToken').fill('tok2');
      await page.locator('#sSave').click();
      assert.equal(await page.locator('#sSave').isDisabled(), true, how + ': Save & connect is disabled while waiting');
      assert.match(await page.locator('#sSave').textContent(), /^Waiting for 1 change to save…$/);
      if (how === 'cancel') await page.locator('#sCancel').click();
      if (how === 'esc') await page.keyboard.press('Escape');
      if (how === 'wait') {
        await page.waitForURL(/repo=acme\/other/, { timeout: 10000 }); await page.waitForTimeout(300);
        const ls = await page.evaluate(() => ({ repo: localStorage.getItem('kb_repo'), boards: JSON.parse(localStorage.getItem('kb_boards')) }));
        assert.equal(ls.repo, 'acme/other'); assert.equal(ls.boards['acme/other'].branch, 'dev'); assert.equal(ls.boards['acme/other'].token, 'tok2', 'the typed token is kept');
        assert.equal(ls.boards['acme/board'].token, 'test', 'the old board keeps its token');
        assert.ok(page.api.root().labels.some(l => l.name === 'urgent'), 'the queued save finished on the old board first');
        await page.close(); continue;
      }
      await page.waitForTimeout(3000);   // the queued save has finished by now
      const ls = await page.evaluate(() => ({ repo: localStorage.getItem('kb_repo'), branch: localStorage.getItem('kb_branch'), tok: localStorage.getItem('kb_token'), url: location.search }));
      assert.deepEqual(ls, { repo: 'acme/board', branch: 'main', tok: 'test', url: '' }, how + ': nothing switched');
      assert.ok(page.api.root().labels.some(l => l.name === 'urgent'), how + ': the queued save still finished');
      assert.equal(await page.locator('#sSave').isDisabled(), false); assert.equal(await page.locator('#sSave').textContent(), 'Save & connect');
      assert.deepEqual(page.errors, []); await page.close();
    }

    // 14. A settings code round trip keeps the current board's own keys (email sync, routine steps) that travel only inside kb_boards.
    {
      const page = await open(browser);
      await page.evaluate(() => { localStorage.setItem('kb_email_sync', '1'); localStorage.setItem('kb_claude_steps', '3'); localStorage.setItem('kb_claude_ok', '1'); });
      await page.evaluate(() => window.kbSettings.open('move')); await page.locator('#xCode').click();
      await page.getByRole('alertdialog').locator('button', { hasText: 'Copy settings code' }).click(); await page.waitForFunction(() => /^kbcfg1\./.test(window.__copied));
      const code = await page.evaluate(() => window.__copied); await page.close();
      const other = await open(browser);   // another device: same board, none of those keys
      await other.evaluate(() => window.kbSettings.open('move')); await other.locator('#xPaste').fill(code); await other.locator('#xImport').click();
      const nav = other.waitForNavigation(); await other.getByRole('alertdialog').locator('button', { hasText: 'Import' }).click(); await nav; await other.waitForSelector('.card');
      const got = await other.evaluate(() => ({ email: localStorage.getItem('kb_email_sync'), steps: localStorage.getItem('kb_claude_steps'), ok: localStorage.getItem('kb_claude_ok'), entry: JSON.parse(localStorage.getItem('kb_boards'))['acme/board'] }));
      assert.deepEqual([got.email, got.steps, got.ok], ['1', '3', '1'], 'imported per-board keys are live');
      assert.deepEqual([got.entry.email_sync, got.entry.claude_steps, got.entry.claude_ok], ['1', '3', '1'], 'and stay in kb_boards after the load-time stash');
      assert.deepEqual(other.errors, []); await other.close();
    }
    console.log('settings: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
