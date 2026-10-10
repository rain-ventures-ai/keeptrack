'use strict';
// The component catalogue (board/ui.html) renders every ui.js component, its interactive demos work, and the
// board itself still boots with icons.js + ui.js loaded in front of board.js.

const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname).replace(/^\/+/, '') || 'board/ui.html';
  const file = path.resolve(ROOT, rel); if (!file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => { if (err) res.writeHead(404).end(); else { res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(data); } });
});

const COMPONENTS = ['button', 'iconButton', 'pill', 'select', 'avatar', 'person', 'props', 'addRow', 'sheet', 'menu', 'section', 'tabs',
  'toast', 'banner', 'confirm', 'listRow', 'taskRow', 'check', 'empty'];

(async () => {
  await new Promise(ok => server.listen(0, '127.0.0.1', ok)); const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const errors = [], page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + '/board/ui.html'); await page.waitForFunction(() => window.catReady === true);
    const waitLog = async text => { await page.waitForFunction(t => document.getElementById('catLog').textContent === t, text); await page.evaluate(() => { document.getElementById('catLog').textContent = ''; }); };   // clear, so the next wait needs a fresh message

    // every component has a section with rendered ui- content
    for (const name of COMPONENTS) {
      const n = await page.locator(`section[data-component="${name}"] [class*="ui-"]`).count();
      assert.ok(n > 0, `section ${name} renders components`);
    }
    assert.deepEqual(await page.evaluate(() => Object.keys(window.ui).sort()), ['addRow', 'avatar', 'banner', 'button', 'check', 'closeMenu', 'colourFor', 'confirm', 'empty', 'icon', 'iconButton', 'initials', 'listRow', 'menu', 'person', 'pill', 'promptText', 'props', 'section', 'select', 'sheet', 'tabs', 'taskRow', 'toast', 'priority', 'priorityTone', 'due', 'dueInfo'].sort());
    assert.equal(await page.evaluate(() => window.ui.colourFor('alex') === window.ui.colourFor('ALEX')), true);
    // every button on the page has an accessible name
    const unnamed = await page.evaluate(() => [...document.querySelectorAll('#cat button')].filter(b => !(b.getAttribute('aria-label') || b.textContent.trim())).length);
    assert.equal(unnamed, 0, 'every button has an accessible name');
    assert.equal(await page.evaluate(() => { try { window.ui.iconButton({ icon: 'x' }); return 'no error'; } catch (e) { return 'error'; } }), 'error', 'iconButton requires a label');
    // theme picker lists every theme from theme.js
    assert.deepEqual(await page.locator('#catTheme option').evaluateAll(o => o.map(x => x.value)), await page.evaluate(() => window.kbTheme.list));

    // confirm resolves true on the confirm button, false on Cancel and on Escape
    await page.click('#catConfirm'); await page.getByRole('alertdialog').getByRole('button', { name: 'Move' }).click(); await waitLog('confirm true');
    await page.click('#catConfirm'); await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel' }).click(); await waitLog('confirm false');
    await page.click('#catConfirmDanger');
    assert.equal(await page.evaluate(() => document.activeElement.textContent), 'Cancel', 'a danger confirm focuses Cancel');
    await page.keyboard.press('Escape'); await waitLog('confirm false');
    assert.equal(await page.locator('dialog').count(), 0, 'confirm removes its dialog');
    // promptText returns the typed text, or null
    await page.click('#catPrompt'); await page.keyboard.type('2026-10-20'); await page.keyboard.press('Enter'); await waitLog('prompt "2026-10-20"');
    await page.click('#catPrompt'); await page.keyboard.press('Escape'); await waitLog('prompt null');

    // menu: opens with focus on the first item, arrows move, Escape closes and returns focus; outside click closes
    await page.click('#catMenuBtn');
    await page.waitForSelector('.ui-menu[role="menu"]');
    assert.equal(await page.getAttribute('#catMenuBtn', 'aria-expanded'), 'true');
    assert.equal(await page.evaluate(() => document.activeElement.textContent), 'Edit');
    await page.keyboard.press('ArrowDown'); assert.equal(await page.evaluate(() => document.activeElement.textContent), 'Duplicate');
    await page.keyboard.press('ArrowUp'); await page.keyboard.press('ArrowUp'); assert.equal(await page.evaluate(() => document.activeElement.textContent), 'Delete', 'arrows wrap');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.ui-menu').count(), 0, 'Escape closes the menu');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'catMenuBtn', 'focus returns to the anchor');
    assert.equal(await page.getAttribute('#catMenuBtn', 'aria-expanded'), 'false');
    await page.click('#catMenuBtn'); await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter'); await waitLog('menu duplicate');
    await page.click('#catMenuBtn'); await page.mouse.click(5, 880); assert.equal(await page.locator('.ui-menu').count(), 0, 'outside click closes');
    // only one menu at a time
    await page.click('#catMenuBtn'); await page.locator('section[data-component="menu"] button[aria-label="More"]').click();
    assert.equal(await page.locator('.ui-menu').count(), 1, 'one menu open at a time'); await page.keyboard.press('Escape');

    // tabs: arrow keys move selection and fire onChange
    await page.locator('#catTabs [role="tab"]').first().focus();
    await page.keyboard.press('ArrowRight'); await waitLog('tabs week');
    assert.equal(await page.getAttribute('#catTabs [data-value="week"]', 'aria-selected'), 'true');
    assert.equal(await page.getAttribute('#catTabs [data-value="today"]', 'tabindex'), '-1');
    await page.keyboard.press('ArrowLeft'); await page.keyboard.press('ArrowLeft'); await waitLog('tabs later');   // wraps

    // addRow: Enter adds, collapsed ghost expands and Escape collapses
    const add = page.locator('section[data-component="addRow"] .ui-addrow').first();
    await add.locator('input').fill('Write tests'); await add.locator('input').press('Enter'); await waitLog('add Write tests');
    assert.equal(await page.locator('#catAddList .ui-listrow').count(), 1); assert.equal(await add.locator('input').inputValue(), '');
    const ghostRow = page.locator('section[data-component="addRow"] .ui-addrow').nth(1);
    await ghostRow.locator('.ui-addrow__ghost').click(); assert.equal(await ghostRow.locator('input').isVisible(), true);
    await ghostRow.locator('input').press('Escape'); assert.equal(await ghostRow.locator('input').isVisible(), false); assert.equal(await ghostRow.locator('.ui-addrow__ghost').isVisible(), true);

    // toast: shows, queues one at a time, and the action works
    await page.click('#catToast'); await page.waitForSelector('.ui-toast:has-text("Saved")');
    await page.locator('section[data-component="toast"] button', { hasText: 'Toast with Undo' }).click();
    assert.equal(await page.locator('.ui-toast').count(), 1, 'one toast at a time');
    await page.locator('.ui-toast__action').click({ timeout: 8000 }); await waitLog('toast undo');

    // sheet: opens as a modal dialog, a menu inside it works, Escape closes
    await page.click('#catSheetRight'); await page.waitForSelector('dialog.ui-sheet--right[open]');
    await page.locator('dialog[open] button[aria-label="More actions"]').click(); await page.waitForSelector('dialog[open] .ui-menu');
    await page.keyboard.press('Escape'); assert.equal(await page.locator('dialog.ui-sheet--right[open]').count(), 1, 'Escape in a menu closes only the menu');
    await page.keyboard.press('Escape'); await page.waitForSelector('dialog.ui-sheet--right[open]', { state: 'detached' }).catch(() => {});
    assert.equal(await page.locator('dialog.ui-sheet--right[open]').count(), 0);

    assert.deepEqual(errors, [], 'no page errors on ui.html');
    await page.close();

    // phone width: no horizontal overflow, interactive controls are at least 44px tall
    const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const perr = []; phone.on('pageerror', e => perr.push(e.message));
    await phone.goto(base + '/board/ui.html'); await phone.waitForFunction(() => window.catReady === true);
    assert.ok(await phone.evaluate(() => [...document.querySelectorAll('#cat *')].every(e => e.getBoundingClientRect().right <= innerWidth + 1)), 'nothing wider than the phone');
    const small = await phone.evaluate(() => [...document.querySelectorAll('#cat .ui-btn, #cat .ui-iconbtn, #cat .ui-tab, #cat .ui-pill--button, #cat .ui-select__control, #cat .ui-addrow__ghost')]
      .filter(e => e.offsetParent && e.getBoundingClientRect().height < 44).map(e => e.className));
    assert.deepEqual(small, [], 'touch targets are 44px on phones');
    assert.deepEqual(perr, []); await phone.close();

    // the board still boots with icons.js + ui.js in front of board.js
    const board = await browser.newPage(), berr = []; board.on('pageerror', e => berr.push(e.message));
    await board.goto(base + '/board/index.html?demo=board'); await board.locator('#roBar').waitFor({ state: 'visible' });
    assert.equal(await board.evaluate(() => !!(window.ui && window.kbIcons && document.querySelector('header svg.i'))), true, 'icons render and ui is loaded');
    assert.equal(await board.locator('i[data-i]').count(), 0, 'every static icon placeholder was filled');
    assert.deepEqual(berr, [], 'no page errors on the board'); await board.close();

    // review regressions: a toast shown inside a confirm survives the confirm closing; removing an open confirm settles it
    const rg = await browser.newPage(), rerr = []; rg.on('pageerror', e => rerr.push(e.message));
    await rg.goto(base + '/board/ui.html'); await rg.waitForFunction(() => window.catReady === true);
    const shown = await rg.evaluate(async () => {
      const p = ui.confirm({ title: 'Delete?', body: 'Gone for good.' }); ui.toast('inside', { timeout: 0 });
      const d = document.querySelector('dialog[open]'); const described = !!document.getElementById(d.getAttribute('aria-describedby'));
      d.querySelector('.ui-sheet__foot button').click(); await p;
      ui.toast('after'); await new Promise(r => setTimeout(r, 50));
      return { described, texts: [...document.querySelectorAll('.ui-toast')].map(t => t.textContent) };
    });
    assert.ok(shown.described, 'confirm body is the dialog description');
    assert.ok(shown.texts.some(t => t.includes('inside') || t.includes('after')), 'toasts keep showing after the confirm closes: ' + JSON.stringify(shown.texts));
    assert.equal(await rg.evaluate(async () => { const p = ui.confirm({ title: 'X' }); document.querySelector('dialog[open]').remove(); return await Promise.race([p, new Promise(r => setTimeout(() => r('pending'), 500))]); }), false, 'removing an open confirm resolves it false');
    assert.deepEqual(rerr, []); await rg.close();

    // a page cached from before icons.js/ui.js existed loads only board.css + board.js: the board must still start
    const stale = await browser.newPage(), serr = []; stale.on('pageerror', e => serr.push(e.message));
    await stale.route('**/board/index.html*', async r => { const html = fs.readFileSync(path.join(ROOT, 'board/index.html'), 'utf8')
      .replace(/<script>[\s\S]*?var CSS = \[[\s\S]*?<\/script>/, '<link rel="stylesheet" href="board.css"><script src="board.js"></script>'); await r.fulfill({ contentType: 'text/html', body: html }); });
    await stale.goto(base + '/board/index.html?demo=board'); await stale.waitForFunction(() => window.ui && window.kbIcons && document.querySelector('.card, .todayhead'));
    assert.equal(await stale.evaluate(() => !!(window.ui && window.kbIcons)), true, 'board.js fetched icons.js and ui.js itself');
    assert.deepEqual(serr, [], 'no page errors on a stale page'); await stale.close();

    console.log('ui catalogue: all checks passed');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exit(1); });
