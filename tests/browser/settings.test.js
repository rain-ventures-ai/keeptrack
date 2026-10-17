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
    if (this.extra && Object.hasOwn(this.extra, p) && method === 'GET') { const x = this.extra[p]; return x === 404 ? json({ message: 'Not Found' }, 404) : json(Array.isArray(x) ? x : { content: Buffer.from(text(x)).toString('base64') }); }
    if (p === '/contents/automation/routines' && method === 'GET') return json((this.routines || []).map((_, i) => ({ type: 'file', name: `routine_${i}.json` })));
    if (/^\/contents\/automation\/routines\/routine_\d+\.json$/.test(p) && method === 'GET') return json({ content: Buffer.from(text(this.routines[Number(/routine_(\d+)/.exec(p)[1])])).toString('base64') });
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
async function open(browser, { width = 1280, height = 860, token = 'test', demo = false, repo = 'acme/board', query = '' } = {}) {
  const api = new Github(), page = await browser.newPage({ viewport: { width, height } }), errors = [];
  page.on('pageerror', e => errors.push(e.message)); page.on('dialog', d => { errors.push('native dialog: ' + d.message()); d.dismiss(); });
  await page.addInitScript(([token, repo]) => {
    if (repo) { localStorage.setItem('kb_repo', repo); localStorage.setItem('kb_branch', 'main'); localStorage.setItem('kb_path', 'board/tasks.json'); localStorage.setItem('kb_me', 'alex'); localStorage.setItem('kb_api', 'https://api.test'); }
    if (token) localStorage.setItem('kb_token', token);
    localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); sessionStorage.setItem('kb_view', 'board');
    window.__copied = ''; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async t => { window.__copied = t; } } });
  }, [token, demo ? '' : repo]);
  await page.route('https://api.test/**', r => api.route(r));
  await page.goto(base + '/board/index.html' + (demo ? '?demo=board' : query));
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
    // Saved routine reports are not live scheduler state; setup only copies a scoped, approval-first prompt.
    {
      const page = await open(browser, { width: 390, height: 844 });
      page.api.routines = [
        { id: 'notes_alex', name: 'Meeting notes', owner: 'alex', board_repo: 'acme/board', branch: 'main', board_path: 'board/tasks.json', purpose: 'Review meeting actions', status: 'active', runtime: 'Local Codex', schedule: 'Mon 10:30', timezone: 'Europe/London', management_url: 'https://example.test/manage', last_successful_run_at: '2026-10-12T09:00:00Z', last_started_at: '2026-10-12T08:59:00Z', connections: [{ provider: 'Drive', account_label: 'Work', access: 'read-only' }], last_run: { status: 'success', summary: 'Reviewed three meetings', counts: { documents_checked: 3, proposals: 2 } } },
        { id: 'cleanup_alex', name: 'Cleanup proposals', status: 'unverified', last_successful_run_at: 'not-a-time', current_run: { started_at: '2026-10-12T10:00:00Z' }, connections: 'malformed' },
        { id: 'other', name: 'Other board path', board_repo: 'acme/board', branch: 'main', board_path: 'other/tasks.json' }, null
      ];
      await page.evaluate(() => document.getElementById('btnSettings').click()); await page.locator('#tabAgents').click();
      await page.waitForFunction(() => document.querySelectorAll('.routine-card').length === 2);
      assert.deepEqual(await page.locator('.routine-card h4').allTextContents(), ['Meeting notes', 'Cleanup proposals']);
      assert.match(await page.locator('.routine-card').first().textContent(), /Recorded active/);
      assert.match(await page.locator('.routine-card').first().textContent(), /Last reported run: Succeeded — Reviewed three meetings/);
      assert.match(await page.locator('.routine-card').nth(1).textContent(), /check the runner before assuming it is still working/);
      assert.match(await page.locator('.routine-card').nth(1).textContent(), /legacy scope; verify before running/);
      assert.equal(await page.locator('.routine-card__details').first().getAttribute('open'), null);
      assert.equal(await page.locator('.routine-card').first().locator('a').getAttribute('href'), 'https://example.test/manage');
      const localTime = await page.evaluate(() => new Date('2026-10-12T09:00:00Z').toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }));
      assert.match(await page.locator('.routine-card').first().textContent(), new RegExp(localTime.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
      await page.locator('.routine-card__details').first().locator('summary').click();
      assert.deepEqual(await page.locator('.routine-counts dd').allTextContents(), ['3', '2']);
      const writes = page.api.writes;
      await page.locator('#routineWorkflow').selectOption('cleanup'); await page.locator('#routineGoals').fill('Is this going to make money soon?'); await page.locator('#routineSchedule').fill('Mon Wed Fri 10:30 Europe/London');
      await page.locator('#routineSetupCopy').click(); await page.waitForFunction(() => window.__copied.includes('safe board cleanup proposals'));
      const prompt = await page.evaluate(() => window.__copied);
      assert.match(prompt, /Board: acme\/board; branch: main; board path: board\/tasks.json; owner: alex/);
      assert.match(prompt, /Is this going to make money soon\?/); assert.match(prompt, /Mon Wed Fri 10:30 Europe\/London/);
      assert.match(prompt, /before provisioning or enabling anything/); assert.match(prompt, /never silently delete or archive/);
      assert.match(prompt, /specific message/); assert.match(prompt, /register.*real ID/);
      assert.equal(page.api.writes, writes, 'copying setup does not write to GitHub or create a schedule');
      const overflow = await page.evaluate(() => document.getElementById('dlgSettings').scrollWidth - document.getElementById('dlgSettings').clientWidth);
      assert.equal(overflow, 0, 'routine cards and setup fit a phone width');
      assert.deepEqual(page.errors, []); await page.close();
    }
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

      // 3b. Members: rename, add and remove an email, set a time zone, add and remove a member. Bad input never saves.
      assert.deepEqual(await page.locator('#memBox .memrow').first().locator('.memtags .ui-pill').allTextContents(), ['You', 'Upgrade owner']);
      assert.equal(await page.locator('#memBox .memrow').first().getByRole('button', { name: 'Remove' }).isDisabled(), true, 'the upgrade owner cannot be removed');
      const writes = () => page.api.writes, alex = () => page.locator('#memBox .memrow').first(), saved = () => page.waitForResponse(r => ['PUT', 'PATCH'].includes(r.request().method()));
      w = saved(); await alex().locator('.memhead input').fill('Alex R'); await alex().locator('.memhead input').blur(); await w;
      assert.equal(page.api.root().people[0].name, 'Alex R');
      let before = writes();
      await alex().getByRole('button', { name: 'Add email' }).click(); await alex().locator('.ui-addrow__input').fill('not-an-email'); await alex().locator('.ui-addrow__input').press('Enter');
      await page.getByText('is not an email address').waitFor(); assert.equal(writes(), before, 'a bad address is not saved');
      w = saved(); await alex().locator('.ui-addrow__input').fill('alex@work.example'); await alex().locator('.ui-addrow__input').press('Enter'); await w;
      assert.deepEqual(page.api.root().people[0].emails, ['alex@work.example']);
      await page.waitForFunction(() => document.querySelector('#memBox .memmail .ui-pill__text')?.textContent === 'alex@work.example');
      before = writes(); await alex().getByLabel('Time zone of @alex').fill('Mars/Base'); await alex().getByLabel('Time zone of @alex').blur();
      await page.getByText('is not a time zone').waitFor(); assert.equal(writes(), before, 'a bad time zone is not saved');
      w = saved(); await alex().getByLabel('Time zone of @alex').fill('europe/london'); await alex().getByLabel('Time zone of @alex').blur(); await w;
      assert.equal(page.api.root().people[0].timezone, 'Europe/London');
      await page.locator('#memBox').getByRole('button', { name: 'Add a member' }).click(); w = saved();
      await page.locator('#memBox .ui-addrow__input').last().fill('@bea'); await page.locator('#memBox .ui-addrow__input').last().press('Enter'); await w;
      assert.deepEqual(page.api.root().people.map(p => p.github), ['alex', 'bea']); assert.equal(page.api.root().people[1].name, 'bea');
      await page.waitForFunction(() => document.querySelectorAll('#memBox .memrow').length === 2);
      assert.equal(page.api.root().people[0].own_companies, undefined, 'company links are never inferred');
      await alex().getByLabel('Link an own company for @alex').focus();
      w = saved(); await alex().getByLabel('Link an own company for @alex').selectOption('Acme'); await w;
      assert.deepEqual(page.api.root().people[0].own_companies, ['Acme']);
      await page.locator('#memBox .memrow').nth(1).getByLabel('Link an own company for @bea').focus();
      w = saved(); await page.locator('#memBox .memrow').nth(1).getByLabel('Link an own company for @bea').selectOption('Acme'); await w;
      await page.waitForFunction(() => document.querySelector('#memBox .memrow[data-gh="bea"] [aria-label="Remove @bea"]').disabled);
      assert.equal(await page.locator('#memBox .memrow').nth(1).getByRole('button', { name: 'Remove @bea', exact: true }).isDisabled(), true);
      await page.locator('#memBox .memrow').nth(1).getByRole('button', { name: 'Unlink own company Acme from @bea' }).click();
      let unlink = page.getByRole('alertdialog'); await unlink.waitFor(); assert.match(await unlink.textContent(), /Still protected for @alex/);
      w = saved(); await unlink.getByRole('button', { name: 'Unlink', exact: true }).click(); await w;
      assert.equal(page.api.root().people[1].own_companies, undefined);
      await alex().locator('.memcompanies .ui-pill').first().click(); await page.locator('#dlgClient[open]').waitFor();
      assert.match(await page.locator('#clIdentity').textContent(), /Your company.*@alex/);
      await page.locator('#clClose').click(); await page.evaluate(() => window.kbSettings.open('members'));
      await alex().getByRole('button', { name: 'Unlink own company Acme from @alex' }).click(); unlink = page.getByRole('alertdialog'); await unlink.waitFor();
      assert.match(await unlink.textContent(), /tasks.*projects.*CRM employer references/);
      w = saved(); await unlink.getByRole('button', { name: 'Unlink', exact: true }).click(); await w;
      assert(page.api.root().clients.includes('Acme'), 'unlinking never removes the company');
      w = saved(); await page.locator('#memBox .memrow').nth(1).getByRole('button', { name: 'Remove' }).click();
      const rm = page.getByRole('alertdialog'); await rm.waitFor(); await rm.getByRole('button', { name: 'Remove', exact: true }).click(); await w;
      assert.deepEqual(page.api.root().people.map(p => p.github), ['alex']);
      await page.evaluate(() => window.kbSettings.open('members')); await settle(page);
      assert.equal(await inView(page, 'memSec'), true, "'members' opens the Members section");
      await shot(page, 'settings-board-members');

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
      assert.deepEqual(await page.locator('#agChooser .schip').allTextContents(), ['Off', 'In your app', 'Not marked']);
      await page.locator('#sUseEmail').check(); assert.equal(await page.locator('#agEmailChip').textContent(), 'Marked as set up'); assert.equal(await page.evaluate(() => localStorage.getItem('kb_email_sync')), '1');
      await page.locator('#agChooser .agpick').nth(2).click(); await page.waitForTimeout(600); assert.equal(await inView(page, 'agEmail'), true, 'the chooser scrolls to Email contact sync');
      assert.equal(await page.locator('#dlgSettings [id^="ag"] .sprompt button', { hasText: 'Copy setup prompt' }).count() >= 2, true, 'one setup-prompt helper, one label');

      // 7. At 1280px the tab list sits left of the panel.
      const lay = await page.evaluate(() => { const t = document.querySelector('#dlgSettings .stabs').getBoundingClientRect(), p = document.getElementById('panelAgents').getBoundingClientRect(); return { tr: t.right, pl: p.left, th: t.height }; });
      assert(lay.tr <= lay.pl, 'two columns: the tab list is left of the panel'); assert(lay.th > 100, 'the tab list is vertical');
      assert.equal(await page.locator('#dlgSettings [role=tablist]').first().getAttribute('aria-orientation'), 'vertical', 'the vertical tab list says so');
      await page.setViewportSize({ width: 390, height: 844 }); await settle(page);
      assert.equal(await page.locator('#dlgSettings [role=tablist]').first().getAttribute('aria-orientation'), 'horizontal');
      await page.setViewportSize({ width: 1280, height: 860 }); await settle(page);
      assert.deepEqual([...new Set(await page.locator('#dlgSettings .setsec__scope').allTextContents())].sort(), ['Shared board: shared with everyone on the board. ', 'This browser: saved in this browser only. '], 'the scope tag reads as one phrase');
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

    // 10b. ?setup ("Create my own board") in a browser that already has a board with no token: Connection says the settings
    // are for the current board, keeps its form folded, and offers a way back to it.
    {
      const page = await open(browser, { width: 390, height: 844, token: '', query: '?setup' });
      assert.equal(await page.locator('#dlgSettings').getAttribute('open'), null, 'setup never opens Settings by itself');
      await page.evaluate(() => window.kbSettings.open('connect')); await settle(page);
      assert.equal(await page.locator('#bEditFold').getAttribute('open'), null, 'the old board form stays folded during setup');
      assert.match(await page.locator('#bState').textContent(), /setting up a new board.*acme\/board/);
      assert.match(await page.locator('#bState').textContent(), /Back to acme\/board/);
      await page.locator('#bState button', { hasText: 'Back to acme/board' }).click(); await page.waitForURL(/repo=acme\/board/);
      assert.equal(new URL(page.url()).searchParams.has('setup'), false, 'Back leaves setup');
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
      let writing = 0;   // writes started (each held 1.5s), so the label save below is still in flight when Save & connect is clicked
      await page.route('https://api.test/**', async r => { if (r.request().method() !== 'GET') { writing++; await new Promise(z => setTimeout(z, 1500)); } return page.api.route(r); });
      await page.evaluate(() => window.kbSettings.open('labels')); await page.locator('#labelBox .lbrow').first().waitFor();
      await page.locator('#labelBox input[aria-label="New label name"]').fill('urgent'); await page.locator('#labelBox button', { hasText: 'Add label' }).click();
      await page.evaluate(() => window.kbSettings.open('conn'));
      for (let i = 0; i < 100 && !writing; i++) await page.waitForTimeout(20);
      assert.ok(writing, how + ': the label save is in flight');
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
      assert.deepEqual({ repo: ls.repo, branch: ls.branch, tok: ls.tok }, { repo: 'acme/board', branch: 'main', tok: 'test' }, how + ': nothing switched');
      const query = new URLSearchParams(ls.url); assert.deepEqual(['repo', 'branch', 'path'].map(k => query.get(k)), ['acme/board', 'main', 'board/tasks.json'], how + ': address names its own board'); assert.equal(query.has('token'), false);
      assert.ok(page.api.root().labels.some(l => l.name === 'urgent'), how + ': the queued save still finished');
      assert.equal(await page.locator('#sSave').isDisabled(), false); assert.equal(await page.locator('#sSave').textContent(), 'Save & connect');
      assert.deepEqual(page.errors, []); await page.close();
    }

    // 14. A settings code round trip keeps the current board's own keys (email sync, routine steps) that travel only inside kb_boards.
    {
      const page = await open(browser);
      await page.evaluate(() => { localStorage.setItem('kb_email_sync', '1'); localStorage.setItem('kb_claude_steps', '3'); localStorage.setItem('kb_claude_ok', '1'); });
      await page.reload(); await page.waitForSelector('.card');   // a tab reads its board's keys once, at start-up
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
    // 15. Backlog auto-research (kit v60): off by default; the switch and "Cards each run" save settings.backlog_research.
    {
      const page = await open(browser);
      await page.evaluate(() => window.kbSettings.open('board')); await settle(page);
      assert.equal(await page.locator('#sResearch').isChecked(), false, 'off by default');
      assert.equal(await page.locator('#sResearchN').inputValue(), '2', 'two cards each run by default');
      await page.locator('#sResearch').check();
      await page.waitForFunction(() => !document.getElementById('sResearch').disabled);
      assert.deepEqual(page.api.root().settings.backlog_research, { enabled: true, per_run: 2 });
      await page.locator('#sResearchN').fill('4'); await page.locator('#sResearchN').dispatchEvent('change');
      await page.waitForFunction(() => !document.getElementById('sResearchN').disabled);
      assert.deepEqual(page.api.root().settings.backlog_research, { enabled: true, per_run: 4 });
      await page.locator('#sResearchN').fill('40'); await page.locator('#sResearchN').dispatchEvent('change'); await settle(page);
      assert.deepEqual(page.api.root().settings.backlog_research, { enabled: true, per_run: 4 }, 'out of range: nothing saved');
      assert.equal(await page.locator('#sResearchN').inputValue(), '4', 'and the box shows the stored value again');
      await page.locator('#sResearch').uncheck();
      await page.waitForFunction(() => !document.getElementById('sResearch').disabled);
      assert.deepEqual(page.api.root().settings.backlog_research, { enabled: false, per_run: 4 });
      assert.equal(page.api.root().settings.title, 'Settings test', 'other settings stay');
      assert.deepEqual(page.errors, []); await page.close();
    }
    // 16. The Automations page (header button, #view=automations): one row per pack (icon, name, summary, state); a row opens
    // its details in a drawer, as a card does, with a node diagram of what it does; read only; every step is a command to copy,
    // nothing is written; pack text is shown as text; no sideways scroll at 390px.
    {
      const page = await open(browser, { width: 390, height: 844 });
      const man = (slug, name, extra = {}) => ({ schema: 'keeptrack-automation/1', slug, name, summary: 'Summary of ' + name, version: '1.0.0', needs: [{ id: 'board.read', routes: [] }], writes: ['proposals'], never: [], every: '1d', check: { file: 'check.py', network: false, tools: [] }, ...extra });
      const reg = (slug, owner, status, more = {}) => ({ id: `auto-${slug}-${owner}`, owner, status, board_repo: 'acme/board', branch: 'main', board_path: 'board/tasks.json', automation: { slug, every: '1d', setup: { status: status === 'unverified' ? 'blocked' : 'ready', notes: status === 'unverified' ? ['probe-failed'] : [] } }, ...more });
      const flow = [{ kind: 'trigger', title: 'Every morning' }, { kind: '__proto__', title: 'Hidden' }, { kind: 'read', title: '<b>Read</b> the board', text: 'Open cards only' }, { kind: 'output', title: 'Review Inbox' }];
      page.api.extra = {
        '/contents/board/automations': [{ type: 'dir', name: 'stale-cards-nudge' }, { type: 'dir', name: 'email-to-tasks' }, { type: 'dir', name: 'notes-folder-to-tasks' }, { type: 'dir', name: 'broken' }, { type: 'file', name: 'README.md' }, { type: 'dir', name: '../evil' }],
        '/contents/automations': [{ type: 'dir', name: 'my-pack' }],
        '/contents/board/automations/stale-cards-nudge/manifest.json': man('stale-cards-nudge', 'Stale cards nudge', { flow, never: ['delete', '__proto__'] }),
        '/contents/board/automations/email-to-tasks/manifest.json': man('email-to-tasks', 'Email to tasks', { every: '6h', needs: [{ id: 'gmail.read', routes: [] }], check: { file: 'check.py', network: true, tools: ['gog'] } }),
        '/contents/board/automations/notes-folder-to-tasks/manifest.json': man('notes-folder-to-tasks', '<img src=x onerror=alert(1)>', { config: { notes_dir: { type: 'path', required: true } } }),
        '/contents/board/automations/broken/manifest.json': 404,
        '/contents/automations/my-pack/manifest.json': man('my-pack', 'My pack', { check: undefined, needs: Array.from({ length: 500 }, (_, i) => ({ id: 'x' + i, routes: [] })) }),
      };
      page.api.routines = [];
      const regs = { 'auto-stale-cards-nudge-alex.json': reg('stale-cards-nudge', 'alex', 'active', { last_run: { status: 'success', summary: 'Two nudges proposed' }, last_successful_run_at: { toString: null } }),
        'auto-email-to-tasks-alex.json': reg('email-to-tasks', 'alex', 'unverified'), 'auto-my-pack-sam.json': reg('my-pack', 'sam', 'paused'), 'auto-my-pack-alex.json': reg('my-pack', 'alex', 'retired'),
        'auto-notes-folder-to-tasks-alex.json': reg('notes-folder-to-tasks', 'alex', 'active', { branch: 'other' }), 'auto-broken-alex.json': reg('broken', 'alex', '__proto__', { last_run: { status: 'constructor' } }),
        'auto-gone-pack-alex.json': reg('gone-pack', 'alex', 'active') };
      page.api.extra['/contents/automation/routines'] = Object.keys(regs).map(name => ({ type: 'file', name }));
      Object.entries(regs).forEach(([n, r]) => { page.api.extra['/contents/automation/routines/' + n] = r; });
      const before = page.api.writes;
      await page.evaluate(() => document.getElementById('btnAutos').click());
      await page.waitForFunction(() => document.querySelectorAll('.autorow').length === 6);
      assert.equal(await page.evaluate(() => document.getElementById('board').className), 'v-automations');
      assert.equal(await page.locator('#board .autocard, #board .aflow').count(), 0, 'the list shows no workflow: that is in the details');
      assert.match(await page.evaluate(() => location.hash), /view=automations/, 'the page has its own link');
      assert.deepEqual(await page.locator('.autorow h3').allTextContents(), ['Stale cards nudge', 'Email to tasks', '<img src=x onerror=alert(1)>', 'broken', 'My pack', 'gone-pack'], 'pack text is shown as text; an install without a pack still shows');
      assert.equal(await page.locator('.autorow img').count(), 0, 'no markup from pack text');
      assert.deepEqual(await page.locator('.autorow__state').allTextContents(), ['On', 'Needs setup', 'Not installed', 'Pack has a problem', 'Not installed', 'Pack missing'], 'each row says its state');
      assert.match(await page.locator('.autorow').first().textContent(), /Summary of Stale cards nudge/, 'a row carries the one-line summary');
      assert.match(await page.locator('.autos__count').textContent(), /5 available · 2 on for you/, 'an install whose pack is gone still counts: it still runs');
      const rows = page.locator('.autorow'), sheet = page.locator('#dlgAuto .autocard');
      const opened = async i => {   // open row i's details drawer (closing any other first) and return its content
        if (await page.evaluate(() => document.getElementById('dlgAuto').open)) { await page.locator('#auClose').click(); await page.waitForFunction(() => !document.getElementById('dlgAuto').open); }
        await rows.nth(i).click(); await page.waitForFunction(() => document.getElementById('dlgAuto').open); return sheet; };
      const cards = { nth: i => ({ locator: sel => ({ count: async () => (await opened(i)).locator(sel).count(), textContent: async () => (await opened(i)).locator(sel).textContent(),
        getAttribute: async a => (await opened(i)).locator(sel).getAttribute(a), evaluateAll: async f => (await opened(i)).locator(sel).evaluateAll(f) }) }) };
      const txt = async i => (await (await opened(i)).textContent()).replace(/\s+/g, ' ');
      const nodes = async i => cards.nth(i).locator('.aflow__node').evaluateAll(xs => xs.map(x => x.dataset.kind + ':' + x.querySelector('.aflow__title').textContent));
      assert.deepEqual(await nodes(0), ['trigger:Once a day', 'read:<b>Read</b> the board', 'output:Review Inbox'], 'the manifest flow is drawn; an unknown kind is dropped; the install interval names the trigger');
      assert.deepEqual(await nodes(1), ['trigger:Once a day', 'read:Read Gmail (read only)', 'check:Find what is new', 'agent:Do the work', 'output:Review Inbox'], 'with no flow, the steps come from the schedule, needs and check');
      assert.equal((await nodes(4)).length, 8, 'a pack with 500 needs still draws at most 8 steps'); assert.equal((await nodes(4))[5], 'check:No cheap check');
      assert.equal(await cards.nth(4).locator('.autocard__fact').count(), 10, 'and at most 8 "Reads" chips, plus its schedule and "AI runs every time"');
      const copy = async (i, label) => { await (await opened(i)).locator('button', { hasText: label }).click(); return page.evaluate(() => window.__copied); };
      assert.match(await txt(0), /On/); assert.match(await txt(0), /Last run: Succeeded — Two nudges proposed/); assert.match(await txt(0), /Last success: never/, 'an odd date value does not break the card'); assert.equal(await cards.nth(0).locator('.autocard__never').textContent(), 'Never: delete anything', 'an unknown never value is not shown');
      assert.doesNotMatch(await txt(0), /Hidden/);
      assert.match(await txt(1), /Needs setup/); assert.match(await txt(1), /Reads Gmail \(read only\)/); assert.match(await txt(1), /Uses the network/); assert.match(await txt(1), /local check of its access failed/);
      assert.match(await txt(2), /Not installed/, 'an install for another branch does not count here'); assert.match(await txt(3), /Pack has a problem/); assert.match(await txt(3), /status unknown/, 'odd status values do not break the page');
      assert.match(await txt(5), /Pack missing/); assert.equal(await copy(5, 'Uninstall it'), 'python3 board/keeptrack.py automation uninstall gone-pack --owner alex');
      assert.match(await txt(4), /Your own/); assert.match(await txt(4), /Not installed/, 'a retired install counts as not installed'); assert.match(await txt(4), /Also on for @sam/); assert.match(await txt(4), /AI runs every time/);
      assert.equal(await copy(0, 'Turn it off'), 'python3 board/keeptrack.py automation disable stale-cards-nudge --owner alex');
      assert.equal(await copy(1, 'Check its access'), 'python3 board/keeptrack.py automation setup email-to-tasks --owner alex --runtime local');
      assert.equal(await copy(2, 'Install it'), "python3 board/keeptrack.py automation install notes-folder-to-tasks --owner alex --set 'notes_dir=REPLACE-WITH-notes_dir'");
      assert.equal(await (await opened(2)).locator('button', { hasText: 'Try it first' }).count(), 0, 'no dry run while a required setting is missing');
      assert.equal(await copy(4, 'Try it first'), 'python3 board/keeptrack.py automation dry-run my-pack --owner alex');
      assert.equal(await copy(3, 'Check the pack'), 'python3 board/keeptrack.py automation validate board/automations/broken');
      assert.match(await copy(1, 'Ask my assistant'), /board\/automations\/email-to-tasks\/SETUP\.md/);
      assert.equal(await cards.nth(1).locator('a.autocard__link').getAttribute('href'), 'https://github.com/acme/board/blob/main/board/automations/email-to-tasks/SETUP.md');
      assert.equal(await page.evaluate(() => getComputedStyle(document.getElementById('dlgAuto')).display), 'flex', 'the details open in a drawer');
      await page.keyboard.press('Escape'); await page.waitForFunction(() => !document.getElementById('dlgAuto').open);
      await page.locator('.autos__tools button', { hasText: 'Make your own' }).click(); assert.match(await page.evaluate(() => window.__copied), /keeptrack-automation-create/);
      assert.equal(page.api.writes, before, 'the page writes nothing');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth && [...document.querySelectorAll('.autorow')].every(x => x.scrollWidth <= x.clientWidth + 1)), true, 'no sideways scroll at 390px');
      await shot(page, 'automations');
      await rows.nth(1).click(); await page.waitForFunction(() => document.getElementById('dlgAuto').open);
      assert.equal(await page.evaluate(() => [...document.querySelectorAll('#dlgAuto .autocard, #dlgAuto .aflow')].every(x => x.scrollWidth <= x.clientWidth + 1)), true, 'the details drawer does not scroll sideways at 390px');
      await page.waitForTimeout(350); await shot(page, 'automation-details'); await page.locator('#auClose').click();
      assert.deepEqual(page.errors, []); await page.close();
    }
    // 17. The routine register leaves automation installs to the Automations page; the old Settings deep link opens a button to it.
    // The demo board shows the kit's packs as examples, from a #view=automations link, with their diagrams and no commands.
    {
      const page = await open(browser);
      page.api.extra = { '/contents/board/automations': 404, '/contents/automations': 404 };
      page.api.routines = [{ id: 'notes_alex', name: 'Meeting notes', board_repo: 'acme/board', branch: 'main', board_path: 'board/tasks.json' }, { id: 'auto-x-alex', name: 'auto x', automation: { slug: 'x' } }];
      await page.evaluate(() => window.kbSettings.open('automations')); await settle(page);
      assert.equal(await visiblePanel(page), 'panelAgents'); assert.equal(await inView(page, 'agAutomations'), true, 'the deep link scrolls to the Automations section');
      await page.waitForFunction(() => document.querySelectorAll('.routine-card').length === 1);
      assert.match(await page.locator('#routineRegister').textContent(), /Automations have their own page/);
      assert.doesNotMatch(await page.locator('#routineRegister').textContent(), /other board contexts/);
      await page.locator('#autoOpen').click();
      await page.waitForFunction(() => document.getElementById('board').className === 'v-automations' && !document.getElementById('dlgSettings').open);
      await page.waitForFunction(() => document.querySelectorAll('.autorow').length === 3);
      assert.match(await page.locator('.autos__note').textContent(), /no automation packs yet/, 'a board without packs previews the kit and says to upgrade');
      await page.locator('.autorow').first().click(); await page.waitForFunction(() => document.getElementById('dlgAuto').open);
      assert.equal(await page.locator('#dlgAuto .autocard button', { hasText: 'Copy the upgrade command' }).count(), 1, 'its details copy the upgrade command');
      await page.locator('#auClose').click();
      assert.deepEqual(page.errors, []); await page.close();
      const demo = await browser.newPage({ viewport: { width: 1280, height: 900 } }), errs = []; demo.on('pageerror', e => errs.push(e.message));
      await demo.addInitScript(() => { localStorage.setItem('kb_layout', 'classic'); localStorage.setItem('kb_tour_seen', '1'); });
      await demo.goto(base + '/board/index.html?demo=board#view=automations');
      await demo.waitForFunction(() => document.querySelectorAll('.autorow').length === 3);
      assert.deepEqual(await demo.locator('.autorow__state').allTextContents(), ['Example', 'Example', 'Example']);
      for (let i = 0; i < 3; i++) {
        await demo.locator('.autorow').nth(i).click(); await demo.waitForFunction(() => document.getElementById('dlgAuto').open);
        assert.equal(await demo.locator('#dlgAuto .aflow__node').count(), 5, 'each built-in pack draws its five steps in its details');
        assert.equal(await demo.locator('#dlgAuto .autocard__actions').count(), 0, 'the demo copies no commands');
        await demo.locator('#auClose').click(); await demo.waitForFunction(() => !document.getElementById('dlgAuto').open);
      }
      assert.deepEqual(errs, []); await demo.close();
    }
    console.log('settings: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
