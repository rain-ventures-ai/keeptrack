'use strict';

// The main views on the shared ui.js components: every view renders without page errors on a phone and a desktop;
// priority and due dates are the shared ui.priority / ui.due pills everywhere; a person's avatar has one colour in
// every view (and in the task drawer); the tab strips are ui.tabs with arrow-key navigation; the header popovers
// close each other, and Escape closes the open one and returns the focus to its trigger.
// Uses the built-in demo boards (?demo=board, ?demo=crm), so no GitHub mock is needed.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.md': 'text/markdown' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/index.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const PHONE = { width: 390, height: 844 }, DESKTOP = { width: 1280, height: 860 };
const VIEWS = [['today', 'crm'], ['people', 'crm'], ['pipeline', 'crm'], ['board', 'board'], ['list', 'board'], ['cal', 'board'], ['sched', 'board'], ['activity', 'board']];
let base;

async function open(browser, { demo = 'board', view = 'board', viewport = DESKTOP, layout = 'classic' } = {}) {
  const phone = viewport.width < 700;
  const ctx = await browser.newContext({ viewport, isMobile: phone, hasTouch: phone }), page = await ctx.newPage(), errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => { errors.push('native dialog: ' + d.message()); d.dismiss().catch(() => {}); });
  await page.addInitScript(([v, l]) => { localStorage.setItem('kb_layout', l); localStorage.setItem('kb_tour', 'done'); sessionStorage.setItem('kb_view', v); }, [view, layout]);
  await page.goto(`${base}/board/index.html?demo=${demo}`); await page.locator('#roBar').waitFor({ state: 'visible' });
  await page.waitForFunction(v => document.body.dataset.view === v && document.getElementById('board').childElementCount > 0, view);
  page.errors = errors; page.done = () => ctx.close(); return page;
}
const bg = (page, sel) => page.locator(sel).first().evaluate(e => getComputedStyle(e).backgroundColor);

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    // 1. Every view renders with no page errors at 390 and 1280 (dock layout on the phone, classic on the desktop).
    for (const [viewport, layout] of [[PHONE, 'dock'], [DESKTOP, 'classic']]) for (const [view, demo] of VIEWS) {
      const page = await open(browser, { demo, view, viewport, layout });
      assert.deepEqual(page.errors, [], `${view} at ${viewport.width}px: no page errors`);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), true, `${view} at ${viewport.width}px: no sideways scroll`);
      await page.done();
    }

    // 2. One priority and one due-date rendering: the shared pill classes in every task view, none of the old ones.
    {
      const page = await open(browser, { view: 'board' });
      const OLD = '.prio, .pr:not(a), .tprio, .pdue, .chip.due, .chip.late, .circ[class*="p-"], .pill[class*="p-"], .dots i, .emptycol, .seg, .stabs button[data-tab], .agpill';
      const check = async (where, rowSel) => {
        assert.equal(await page.locator(OLD).count(), 0, `${where}: no old priority/due/tab classes`);
        const prios = await page.locator(`${rowSel} .ui-prio`).evaluateAll(xs => xs.map(x => ({ p: x.dataset.prio, cls: x.className })));
        assert(prios.length > 0, `${where}: priority pills`);
        const tone = { high: 'ui-pill--danger', medium: 'ui-pill--warn', low: 'ui-pill--ok' };
        prios.forEach(x => { assert.match(x.cls, /\bui-pill\b/, `${where}: priority is a ui-pill`); assert(x.cls.includes(tone[x.p]), `${where}: ${x.p} priority uses ${tone[x.p]} (${x.cls})`); });
      };
      const dueTones = async (where, rowSel) => {
        const dues = await page.locator(`${rowSel} .ui-due`).evaluateAll(xs => xs.map(x => ({ s: x.dataset.due, cls: x.className, text: x.textContent })));
        assert(dues.length > 0, `${where}: due pills`);
        const tone = { overdue: 'ui-pill--danger', today: 'ui-pill--warn', soon: 'ui-pill--accent', later: 'ui-pill--neutral', done: 'ui-pill--neutral' };
        dues.forEach(x => { assert.match(x.cls, /\bui-pill\b/); assert(x.cls.includes(tone[x.s]), `${where}: ${x.s} due date uses ${tone[x.s]} (${x.cls})`); });
        return dues;
      };
      await check('kanban', '.card .top'); const cardDues = await dueTones('kanban', '.card .foot');
      assert(cardDues.some(x => x.s === 'overdue' && /overdue/.test(x.text)), 'an overdue card says so in words');
      assert(cardDues.some(x => x.s === 'today' && x.text === 'Today'), 'a card due today says Today');
      const highOnCard = await page.locator('.card .ui-prio[data-prio="high"]').first().evaluate(e => getComputedStyle(e).color);
      await page.locator('#viewSw [data-view="list"]').click(); await page.waitForSelector('.trow');
      await check('list', '.trow .c-prio'); await dueTones('list', '.trow .c-due');
      assert.equal(await page.locator('.trow .c-prio .ui-prio[data-prio="high"]').first().evaluate(e => getComputedStyle(e).color), highOnCard, 'high priority has the same colour on a card and in the list');
      await page.locator('#viewSw [data-view="sched"]').click(); await page.waitForSelector('.sitem');
      await check('schedule', '.sitem'); await dueTones('schedule overdue group', '.sday.overdue .sitem');
      await page.locator('#viewSw [data-view="cal"]').click(); await page.waitForSelector('.calcell');
      assert(await page.locator('.calcell .pill .ui-prio.ui-prio--dot.ui-pill').count() > 0, 'calendar tasks carry the compact priority pill');
      await page.done();
      const crm = await open(browser, { demo: 'crm', view: 'today' });
      assert(await crm.locator('.ttoday .ui-prio.ui-pill').count() > 0, 'Today task rows use the priority pill');
      assert(await crm.locator('.prow .ui-due.ui-pill').count() > 0, 'Today people rows use the due pill');
      await crm.locator('#viewSw [data-view="pipeline"]').click(); await crm.waitForSelector('.pcard');
      assert(await crm.locator('.pcard .ui-due.ui-pill').count() > 0, 'pipeline cards use the due pill');
      await crm.done();
    }

    // 3. A person's avatar has one colour everywhere: kanban card, list row, header filter and the task drawer's person chip.
    {
      const page = await open(browser, { view: 'board' });
      const who = await page.locator('.card .foot .ui-avatar').first().getAttribute('aria-label');
      const login = await page.locator('.card .foot .ui-avatar').first().getAttribute('title');   // "@login (Name)"
      const onCard = await bg(page, `.card .foot .ui-avatar[aria-label="${who}"]`);
      // the header strip can redraw (refit) between finding the avatar and reading it, so read both in one go once it is there
      const hdr = await page.waitForFunction(who => { const a = document.querySelector(`.pq .ui-avatar[aria-label="${who}"]`); const c = a && getComputedStyle(a).backgroundColor; return c || false; }, who).then(h => h.jsonValue());
      assert.equal(hdr, onCard, 'header filter avatar matches the card');
      await page.locator('.card', { has: page.locator(`.foot .ui-avatar[aria-label="${who}"]`) }).first().locator('.t').dblclick(); await page.locator('#dlgCard[open]').waitFor();
      assert.equal(await bg(page, `#cWho .ui-avatar`), onCard, `the drawer's person chip for ${login} matches the card`);
      await page.keyboard.press('Escape'); await page.locator('#dlgCard').waitFor({ state: 'hidden' });
      await page.locator('#viewSw [data-view="list"]').click(); await page.waitForSelector('.trow');
      assert.equal(await bg(page, `.trow .c-people .ui-avatar[aria-label="${who}"]`), onCard, 'list row avatar matches the card');
      await page.done();
    }

    // 4. Tabs: ui.tabs with aria-selected and arrow keys (header views, dock section strip, Activity range, phone column tabs).
    {
      const page = await open(browser, { view: 'board' });
      assert.equal(await page.locator('#viewSw [role="tablist"].viewgroup').count(), 3, 'three header view groups, each a tablist');
      assert.equal(await page.locator('#viewSw [aria-selected="true"]').count(), 1, 'one selected view');
      await page.locator('#viewSw [data-view="board"]').focus(); await page.keyboard.press('ArrowRight');
      await page.waitForFunction(() => document.body.dataset.view === 'list');
      assert.equal(await page.evaluate(() => document.activeElement.dataset.view), 'list', 'focus moves with the selection');
      assert.equal(await page.locator('#viewSw [data-view="list"]').getAttribute('aria-selected'), 'true');
      await page.keyboard.press('End'); await page.waitForFunction(() => document.body.dataset.view === 'activity');
      await page.keyboard.press('Home'); await page.waitForFunction(() => document.body.dataset.view === 'board');
      assert.equal(await page.locator('#viewSw [data-view="people"]').getAttribute('tabindex'), '0', 'a group with nothing selected keeps its first tab reachable');
      // Activity range: arrow keys re-render the view and the focus stays on the range
      await page.locator('#viewSw [data-view="activity"]').click(); await page.waitForSelector('.actseg');
      await page.locator('.actseg [aria-selected="true"]').focus(); const before = await page.locator('.actseg [aria-selected="true"]').textContent();
      await page.keyboard.press('ArrowRight'); await page.waitForFunction(b => { const a = document.activeElement; return a && a.closest('.actseg') && a.getAttribute('aria-selected') === 'true' && a.textContent !== b; }, before);
      // Settings tabs (tabPrefs, tabBoard, tabConn, tabAgents) switch their panels
      await page.locator('#btnSettings').click(); await page.locator('#tabConn').click();
      assert.equal(await page.locator('#tabConn').getAttribute('aria-selected'), 'true'); assert.equal(await page.locator('#panelConn').isVisible(), true); assert.equal(await page.locator('#panelPrefs').isHidden(), true);
      await page.locator('#tabConn').focus(); await page.keyboard.press('ArrowLeft'); assert.equal(await page.locator('#panelBoard').isVisible(), true, 'arrow keys switch settings sections');
      await page.done();
      const phone = await open(browser, { view: 'board', viewport: PHONE, layout: 'dock' });
      assert.deepEqual(await phone.locator('#subnav [role="tab"]').allTextContents(), ['Kanban', 'List', 'Calendar', 'Schedule', 'Activity']);
      const cols = phone.locator('#tabs [role="tab"]'); assert(await cols.count() >= 2, 'column tabs');
      await cols.first().click(); await cols.first().focus(); await phone.keyboard.press('ArrowRight');
      const second = await cols.nth(1).getAttribute('data-value');
      await phone.waitForFunction(id => document.querySelector(`.col[data-col="${id}"]`).classList.contains('active'), second);
      assert.equal(await cols.nth(1).getAttribute('aria-selected'), 'true', 'arrow keys move between columns on a phone');
      assert.deepEqual(phone.errors, []); await phone.done();
    }

    // 5. Popovers: opening one closes the other; Escape closes and refocuses the trigger; a click outside closes.
    {
      const page = await open(browser, { view: 'board' });
      await page.locator('#btnFilter').click(); assert.equal(await page.locator('#filterPop').isVisible(), true); assert.equal(await page.locator('#btnFilter').getAttribute('aria-expanded'), 'true');
      await page.locator('#boardBtn').click(); assert.equal(await page.locator('#boardPop').isVisible(), true);
      assert.equal(await page.locator('#filterPop').isHidden(), true, 'opening the board switcher closes the filters');
      assert.equal(await page.locator('#btnFilter').getAttribute('aria-expanded'), 'false');
      await page.keyboard.press('Escape'); assert.equal(await page.locator('#boardPop').isHidden(), true, 'Escape closes');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'boardBtn', 'Escape returns the focus to the trigger'); assert.equal(await page.locator('#boardBtn').getAttribute('aria-expanded'), 'false');
      await page.locator('#btnFilter').click(); await page.locator('#fPrio').selectOption('high'); assert.equal(await page.locator('#filterPop').isVisible(), true, 'using the filters keeps them open');
      await page.locator('#board').click({ position: { x: 5, y: 5 } }); assert.equal(await page.locator('#filterPop').isHidden(), true, 'a click outside closes');
      const more = await page.locator('.cpill.more'); if (await more.count()) { await more.click(); assert.equal(await page.locator('#clientPop').isVisible(), true); await page.locator('#btnFilter').click(); assert.equal(await page.locator('#clientPop').isHidden(), true, 'the filters close the client list'); await page.keyboard.press('Escape'); }
      assert.deepEqual(page.errors, []); await page.done();
      const narrow = await open(browser, { view: 'board', viewport: { width: 700, height: 800 } });
      await narrow.locator('#btnMore').click(); assert.deepEqual((await narrow.locator('#morePop button:not([data-head-action="btnInbox"])').allTextContents()).map(s => s.trim()), ['Undo last change', 'Copy board', 'Refresh board', 'Install this board', 'Help', 'Show me around', 'Settings'], 'More lists the header actions');
      assert.equal(await narrow.locator('#morePop [data-head-action="btnInbox"]').isHidden(), true, 'the Review Inbox item shows only when the board turns the Inbox on');
      assert.equal(await narrow.locator('#morePop [data-head-action="btnUndo"]').isDisabled(), true, 'Undo is disabled when there is nothing to undo');
      await narrow.locator('#btnFilter').click(); assert.equal(await narrow.locator('#morePop').isHidden(), true); assert.equal(await narrow.locator('#filterPop').isVisible(), true);
      await narrow.keyboard.press('Escape'); assert.equal(await narrow.locator('#filterPop').isHidden(), true); await narrow.done();
      const dock = await open(browser, { view: 'board', viewport: PHONE, layout: 'dock' });
      await dock.locator('#dockMenu').click(); assert.equal(await dock.locator('#dockPop').isVisible(), true);
      assert.deepEqual((await dock.locator('#dockPop button:not([data-head-action="btnInbox"])').allTextContents()).map(s => s.trim()), ['Undo last change', 'Copy board', 'Refresh board', 'Install this board', 'Help', 'Show me around', 'Settings'], 'the dock menu has the same items');
      assert.equal(await dock.locator('#dockPop [data-head-action="btnInbox"]').isHidden(), true, 'and keeps the Review Inbox hidden while it is off');
      assert.equal(await dock.locator('#dockPop [data-head-action="btnUndo"]').isDisabled(), true, 'mobile Undo is disabled when there is nothing to undo');
      await dock.locator('#btnFilter').click(); assert.equal(await dock.locator('#dockPop').isHidden(), true, 'filters close the dock menu');
      await dock.locator('#dockMenu').click(); await dock.keyboard.press('Escape'); assert.equal(await dock.locator('#dockPop').isHidden(), true); assert.equal(await dock.evaluate(() => document.activeElement.id), 'dockMenu');
      assert.deepEqual(dock.errors, []); await dock.done();
    }

    // Back and Forward move between views, and out of a card to the view it was opened from
    {
      const p = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }); await p.addInitScript(() => { try { localStorage.setItem('kb_tour_seen', '1'); } catch {} });
      await p.goto(base + '/board/index.html?demo=board'); await p.locator('#roBar').waitFor({ state: 'visible' });
      const at = () => p.evaluate(() => ({ view: document.body.dataset.view, card: document.getElementById('dlgCard').open }));
      const until = (v, card) => p.waitForFunction(([v, card]) => document.body.dataset.view === v && document.getElementById('dlgCard').open === card, [v, card]);
      assert.equal((await at()).view, 'today');
      await p.locator('#dock .dtab[data-grp="tasks"]').click(); await until('board', false);
      await p.locator('.card:visible .t').first().click(); await until('board', true);
      await p.goBack(); await until('board', false);
      await p.goBack(); await until('today', false);
      await p.goForward(); await until('board', false);
      await p.goForward(); await until('board', true);
      assert.deepEqual(await at(), { view: 'board', card: true }, 'Forward reopens the card on its view');
      await p.close();
    }

    console.log('views: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
