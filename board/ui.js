// Keeptrack UI component library: small DOM factories that return elements (no framework, no build step).
// Exposes window.ui. Load after icons.js and before board.js; styles are in ui.css (class names start with "ui-").
// Rules every component follows: interactive parts are real <button type="button"> or form controls with an accessible
// name; no inline styles except dynamic custom properties (colours, and a menu's anchor position); icons come from icons.js.
// The catalogue page board/ui.html shows every component and variant.
(function () {
  'use strict';
  const icons = window.kbIcons || { svgIcon: () => document.createElement('span') };
  const PHONE = '(max-width: 760px)';
  let uid = 0;
  const nextId = p => `ui-${p}-${++uid}`;

  // ---- tiny helpers -------------------------------------------------------------------------------------------
  function h(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = String(text); return e; }
  function icon(name) { const s = icons.svgIcon(name); s.classList.add('ui-i'); return s; }
  function btn(cls, onClick) { const b = h('button', cls); b.type = 'button'; if (onClick) b.addEventListener('click', onClick); return b; }
  const append = (parent, x) => { if (x == null || x === false) return; if (Array.isArray(x)) x.forEach(c => append(parent, c)); else parent.append(x instanceof Node ? x : String(x)); };
  const srOnly = text => h('span', 'ui-sr', text);
  const TONES = ['neutral', 'accent', 'ok', 'warn', 'danger', 'info'];
  const tone = t => (TONES.includes(t) ? t : 'neutral');
  const safeHref = u => { try { const x = new URL(u, location.href); return ['https:', 'http:', 'mailto:', 'tel:'].includes(x.protocol) ? x.href : null; } catch { return null; } };

  // The board's only text-to-colour hash: one hue per name (case-insensitive). Avatars and person chips use colourFor; clients,
  // stages and board badges use hueFor with their own saturation and lightness. Key a person by their login, so they match everywhere.
  function hueFor(name) { let x = 0; for (const ch of String(name || '').toLowerCase()) x = (x * 31 + ch.charCodeAt(0)) % 360; return x; }
  function colourFor(name) { return `hsl(${hueFor(name)} 55% 45%)`; }
  function initials(name) {
    const s = String(name || '').replace(/^@/, '').trim(); if (!s) return '?';
    const w = s.split(/[\s._-]+/).filter(Boolean);
    return (w.length > 1 ? w[0][0] + w[1][0] : s.slice(0, 2)).toUpperCase();
  }

  // ---- buttons ------------------------------------------------------------------------------------------------
  function button({ label, variant = 'secondary', size = 'md', icon: ic, onClick, type = 'button', disabled = false, title } = {}) {
    const b = h('button', `ui-btn ui-btn--${['primary', 'secondary', 'ghost', 'danger'].includes(variant) ? variant : 'secondary'} ui-btn--${size === 'sm' ? 'sm' : 'md'}`);
    b.type = ['button', 'submit', 'reset'].includes(type) ? type : 'button';
    if (ic) b.append(icon(ic));
    if (label != null && label !== '') b.append(h('span', 'ui-btn__label', label));
    if (title) b.title = title;
    b.disabled = !!disabled;
    if (onClick) b.addEventListener('click', onClick);
    return b;
  }
  function iconButton({ icon: ic, label, onClick, variant = 'ghost', size = 'md', pressed } = {}) {
    if (!label) throw new Error('ui.iconButton needs a label (it becomes the aria-label and the tooltip)');
    const b = btn(`ui-iconbtn ui-iconbtn--${variant === 'danger' ? 'danger' : variant === 'secondary' ? 'secondary' : 'ghost'} ui-iconbtn--${size === 'sm' ? 'sm' : 'md'}`, onClick);
    b.setAttribute('aria-label', label); b.title = label; b.append(icon(ic || 'circle-help'));
    if (pressed != null) b.setAttribute('aria-pressed', String(!!pressed));
    return b;
  }

  // ---- pills and people ---------------------------------------------------------------------------------------
  // A pill is plain text, or a toggle/action button (onClick/pressed), optionally with a remove button.
  function chip(base, { content, label, tone: t, outline, color, onRemove, removeLabel, onClick, pressed }) {
    const cls = `${base} ui-pill--${tone(t)}` + (outline ? ' ui-pill--outline' : '') + (color ? ' ui-pill--color' : '');
    const interactive = !!onClick || pressed != null;
    const setPressed = (node, v) => { node.setAttribute('aria-pressed', String(!!v)); };
    let root, main;
    if (!onRemove) {
      root = interactive ? btn(cls + ' ui-pill--button', onClick) : h('span', cls);
      append(root, content); main = root;
    } else {
      root = h('span', cls + ' ui-pill--removable');
      main = interactive ? btn('ui-pill__main', onClick) : h('span', 'ui-pill__main');
      append(main, content); root.append(main);
      const x = btn('ui-pill__remove', e => { e.stopPropagation(); onRemove(e); });
      x.setAttribute('aria-label', removeLabel || `Remove ${label}`); x.title = x.getAttribute('aria-label'); x.append(icon('x'));
      root.append(x);
    }
    if (pressed != null && main.tagName === 'BUTTON') setPressed(main, pressed);
    if (color) root.style.setProperty('--ui-pill-c', color);
    return root;
  }
  function pill({ text, tone: t = 'neutral', outline = false, color, onRemove, removeLabel, onClick, pressed, icon: ic, size } = {}) {
    const content = []; if (ic) content.push(icon(ic)); content.push(h('span', 'ui-pill__text', text));
    return chip('ui-pill' + (size === 'sm' ? ' ui-pill--sm' : ''), { content, label: text, tone: t, outline, color, onRemove, removeLabel, onClick, pressed });
  }

  // ---- priority and due date: the one rendering of each, used by every view -------------------------------------
  // Priority: high = danger, medium = warn, low = ok; no priority counts as medium. compact: a coloured dot with the word for screen readers.
  const PRIO_TONE = { high: 'danger', medium: 'warn', low: 'ok' };
  const prioOf = p => (PRIO_TONE[p] ? p : 'medium');
  const priorityTone = p => PRIO_TONE[prioOf(p)];
  function priority(p, { compact = false, size } = {}) {
    const v = prioOf(p), word = v[0].toUpperCase() + v.slice(1);
    const e = compact ? h('span', `ui-pill ui-pill--${PRIO_TONE[v]} ui-prio ui-prio--dot`) : pill({ text: word, tone: PRIO_TONE[v], size });
    if (compact) e.append(srOnly(`${word} priority`)); else { e.classList.add('ui-prio'); e.title = `${word} priority`; }
    e.dataset.prio = v; return e;
  }
  // Due date: overdue = danger, today = warn, the next three days = accent, later = neutral. A finished task is never late.
  let dueFmt = null;
  function dueInfo(due, { done = false } = {}) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(due || '')); if (!m) return null;
    const d = new Date(+m[1], +m[2] - 1, +m[3]), t = new Date(); t.setHours(0, 0, 0, 0);
    const days = Math.round((d - t) / 86400000), nice = (dueFmt || (dueFmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }))).format(d);
    const word = days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : nice;
    if (done) return { state: 'done', tone: 'neutral', text: word, days };
    if (days < 0) return { state: 'overdue', tone: 'danger', text: `${nice} · overdue`, days };
    if (days === 0) return { state: 'today', tone: 'warn', text: word, days };
    if (days <= 3) return { state: 'soon', tone: 'accent', text: word, days };
    return { state: 'later', tone: 'neutral', text: word, days };
  }
  function due(date, { done = false, size, empty } = {}) {
    const i = dueInfo(date, { done });
    if (!i) { if (!empty) return null; const e = pill({ text: empty, tone: 'neutral', outline: true, size }); e.classList.add('ui-due'); e.dataset.due = 'none'; return e; }
    const e = pill({ text: i.text, tone: i.tone, icon: 'calendar', size }); e.classList.add('ui-due'); e.dataset.due = i.state; e.title = 'Due ' + String(date).slice(0, 10);
    return e;
  }
  function avatar(name, { size = 'md', title, key } = {}) {
    const a = h('span', `ui-avatar ui-avatar--${['sm', 'md', 'lg'].includes(size) ? size : 'md'}`, initials(name));
    a.setAttribute('role', 'img'); a.setAttribute('aria-label', String(name || 'Unknown')); a.title = title || String(name || '');
    a.style.setProperty('--ui-av-c', colourFor(key != null ? key : name));
    return a;
  }
  function person({ name, key, onRemove, removeLabel, pressed, onClick, sub } = {}) {
    const content = [avatar(name, { size: 'sm', key }), h('span', 'ui-pill__text', name)];
    if (sub) content.push(h('span', 'ui-person__sub', sub));
    const p = chip('ui-pill ui-person', { content, label: name, tone: 'neutral', onRemove, removeLabel, onClick, pressed });
    p.querySelector('.ui-avatar').setAttribute('aria-hidden', 'true');   // the name is already in the text
    return p;
  }

  // ---- select -------------------------------------------------------------------------------------------------
  // Returns a wrapper span; wrapper.control is the native <select>, and wrapper.value reads/writes it.
  function select({ value, options = [], label, tone: t, onChange, disabled = false } = {}) {
    if (!label) throw new Error('ui.select needs a label');
    const wrap = h('span', 'ui-select' + (t ? ` ui-select--${tone(t)}` : '')), sel = h('select', 'ui-select__control');
    sel.setAttribute('aria-label', label); sel.title = label; sel.disabled = !!disabled;
    options.forEach(o => { const opt = h('option', null, o.label != null ? o.label : o.value); opt.value = o.value; sel.append(opt); });
    if (value != null) sel.value = value;
    sel.addEventListener('change', () => onChange && onChange(sel.value, sel));
    wrap.append(sel, icon('chevron-down'));
    wrap.control = sel;
    Object.defineProperty(wrap, 'value', { get: () => sel.value, set: v => { sel.value = v; } });
    return wrap;
  }

  // ---- property list ------------------------------------------------------------------------------------------
  function props(rows = []) {
    const dl = h('dl', 'ui-props');
    rows.forEach(r => {
      const row = h('div', 'ui-props__row'), dt = h('dt', 'ui-props__label'), dd = h('dd', 'ui-props__value');
      if (r.icon) dt.append(icon(r.icon)); dt.append(h('span', null, r.label));
      append(dd, r.value); row.append(dt, dd); dl.append(row);
    });
    return dl;
  }

  // ---- add row ------------------------------------------------------------------------------------------------
  function addRow({ placeholder = 'Add…', buttonLabel = 'Add', onAdd, collapsed = false, ghostLabel, label } = {}) {
    const root = h('div', 'ui-addrow'), form = h('form', 'ui-addrow__form'), input = h('input', 'ui-input ui-addrow__input');
    input.type = 'text'; input.placeholder = placeholder; input.setAttribute('aria-label', label || ghostLabel || placeholder); input.enterKeyHint = 'done';
    const add = button({ label: buttonLabel, variant: 'primary', type: 'submit' });
    form.append(input, add); form.noValidate = true;
    let ghost = null;
    const setOpen = open => { if (!ghost) return; ghost.hidden = open; form.hidden = !open; ghost.setAttribute('aria-expanded', String(open)); };
    if (collapsed) {
      ghost = btn('ui-addrow__ghost', () => { setOpen(true); input.focus(); });
      ghost.append(icon('plus'), h('span', null, ghostLabel || buttonLabel));
      ghost.setAttribute('aria-expanded', 'false');
      root.append(ghost); setOpen(false);
    }
    form.addEventListener('submit', e => {
      e.preventDefault(); const v = input.value.trim(); if (!v) { input.focus(); return; }
      const r = onAdd ? onAdd(v) : undefined; if (r !== false) input.value = ''; input.focus();
    });
    input.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      e.preventDefault(); e.stopPropagation(); input.value = '';
      if (ghost) { setOpen(false); ghost.focus(); }
    });
    root.append(form);
    root.input = input; root.expand = () => setOpen(true); root.collapse = () => setOpen(false);
    return root;
  }

  // ---- sheet (dialog) -----------------------------------------------------------------------------------------
  function sheet({ title, actions = [], body, footer, side = 'right', onClose, label, removeOnClose = false } = {}) {
    const d = h('dialog', `ui-sheet ui-sheet--${side === 'center' ? 'center' : 'right'}`), head = h('header', 'ui-sheet__head');
    const hid = nextId('sheet'), t = h('h2', 'ui-sheet__title', title || ''); t.id = hid;
    if (title) d.setAttribute('aria-labelledby', hid); else d.setAttribute('aria-label', label || 'Dialog');
    const acts = h('div', 'ui-sheet__actions'); append(acts, actions);
    const close = iconButton({ icon: 'x', label: 'Close', onClick: () => api.close() });
    head.append(t, acts, close);
    const b = h('div', 'ui-sheet__body'); append(b, body);
    d.append(head, b);
    let f = null; if (footer) { f = h('footer', 'ui-sheet__foot'); append(f, footer); d.append(f); }
    d.addEventListener('click', e => { if (e.target === d) api.close(); });   // a click on the backdrop
    let settled = true, watch = null;
    const finish = () => {   // every way out of an open sheet ends here once: close(), Escape, backdrop, or the dialog being removed
      if (settled) return; settled = true; if (watch) { watch.disconnect(); watch = null; }
      closeMenu(); if (toastRegion && d.contains(toastRegion)) region();   // a toast shown inside this dialog moves back out before it goes
      if (onClose) onClose(d.returnValue); if (removeOnClose && d.isConnected) d.remove();
    };
    d.addEventListener('close', finish);
    const api = {
      el: d, body: b, footer: f,
      open() {
        if (!d.isConnected) document.body.append(d);
        if (!d.open) { d.showModal(); settled = false; }
        if (!watch && d.parentNode) { watch = new MutationObserver(() => { if (!d.isConnected) finish(); }); watch.observe(d.parentNode, { childList: true }); }
        return api;
      },
      close(v) { if (d.open) d.close(v == null ? '' : v); return api; }
    };
    d.uiSheet = api;
    return api;
  }

  // ---- menu ---------------------------------------------------------------------------------------------------
  // Anchored popover. One open at a time; arrows/Home/End move, Escape or Tab closes, a click outside closes.
  let openMenuState = null;
  const canPopover = typeof HTMLElement !== 'undefined' && Object.prototype.hasOwnProperty.call(HTMLElement.prototype, 'popover');
  function closeMenu(refocus = false) {
    const m = openMenuState; if (!m) return; openMenuState = null;
    document.removeEventListener('pointerdown', m.outside, true); window.removeEventListener('resize', m.place); window.removeEventListener('scroll', m.place, true);
    try { if (canPopover && m.el.matches(':popover-open')) m.el.hidePopover(); } catch {}
    m.el.remove(); m.anchor.setAttribute('aria-expanded', 'false');
    if (refocus && m.anchor.isConnected) m.anchor.focus();
  }
  function menu(anchor, items = [], { label } = {}) {
    if (openMenuState && openMenuState.anchor === anchor) { closeMenu(); return null; }   // second press toggles it shut
    closeMenu();
    const m = h('div', 'ui-menu'), mid = nextId('menu'); m.id = mid; m.setAttribute('role', 'menu');
    m.setAttribute('aria-label', label || anchor.getAttribute('aria-label') || anchor.textContent.trim() || 'Menu');
    const buttons = [];
    items.forEach(it => {
      if (it.separator) { const s = h('div', 'ui-menu__sep'); s.setAttribute('role', 'separator'); m.append(s); return; }
      const b = btn('ui-menu__item' + (it.danger ? ' ui-menu__item--danger' : ''));
      b.setAttribute('role', 'menuitem'); b.tabIndex = -1; b.disabled = !!it.disabled;
      if (it.icon) b.append(icon(it.icon)); b.append(h('span', null, it.label));
      b.addEventListener('click', () => { closeMenu(true); if (it.onSelect) it.onSelect(); });
      buttons.push(b); m.append(b);
    });
    const enabled = () => buttons.filter(b => !b.disabled);
    const focusAt = i => { const e = enabled(); if (e.length) e[(i + e.length) % e.length].focus(); else { m.tabIndex = -1; m.focus(); } };   // nothing enabled: focus the menu itself so Escape still closes only the menu
    m.addEventListener('keydown', e => {
      const e2 = enabled(), i = e2.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') { e.preventDefault(); focusAt(i + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); focusAt(i < 0 ? -1 : i - 1); }
      else if (e.key === 'Home') { e.preventDefault(); focusAt(0); }
      else if (e.key === 'End') { e.preventDefault(); focusAt(-1); }
      else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeMenu(true); }
      else if (e.key === 'Tab') closeMenu(false);
    });
    // Inside a modal dialog everything outside it is inert, so the menu lives in the anchor's dialog when it has one.
    (anchor.closest('dialog[open]') || document.body).append(m);
    if (canPopover) { m.popover = 'manual'; try { m.showPopover(); } catch {} }   // top layer: never clipped by an overflow parent
    const place = () => {
      if (window.matchMedia(PHONE).matches) return;   // phones: CSS shows it as a bottom sheet
      const r = anchor.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight, vw = window.innerWidth, vh = window.innerHeight;
      let x = r.left, y = r.bottom + 4;
      if (x + mw > vw - 8) x = Math.max(8, r.right - mw);
      if (y + mh > vh - 8 && r.top - mh - 4 > 8) y = r.top - mh - 4;
      m.style.setProperty('--ui-menu-x', Math.round(x) + 'px'); m.style.setProperty('--ui-menu-y', Math.round(y) + 'px');
    };
    place();
    const outside = e => { if (!m.contains(e.target) && !anchor.contains(e.target)) closeMenu(false); };
    openMenuState = { el: m, anchor, outside, place };
    document.addEventListener('pointerdown', outside, true); window.addEventListener('resize', place); window.addEventListener('scroll', place, true);
    anchor.setAttribute('aria-haspopup', 'menu'); anchor.setAttribute('aria-expanded', 'true'); anchor.setAttribute('aria-controls', mid);
    focusAt(0);
    return { el: m, close: () => closeMenu(true) };
  }

  // ---- section ------------------------------------------------------------------------------------------------
  // Returns the <section>; append content to section.body.
  function section({ title, count, action, collapsible = false, open = true, body } = {}) {
    const s = h('section', 'ui-section'), head = h('div', 'ui-section__head'), b = h('div', 'ui-section__body'), bid = nextId('sec');
    b.id = bid; append(b, body);
    const titleBits = [h('span', 'ui-section__text', title)];
    if (count != null) titleBits.push(h('span', 'ui-count', count));
    const hd = h('h3', 'ui-section__title');
    if (collapsible) {
      const t = btn('ui-section__toggle'); t.append(icon('chevron-right'), ...titleBits); t.setAttribute('aria-controls', bid);
      const set = v => { t.setAttribute('aria-expanded', String(v)); b.hidden = !v; s.classList.toggle('ui-section--closed', !v); };
      t.addEventListener('click', () => set(t.getAttribute('aria-expanded') !== 'true')); set(!!open);
      hd.append(t); s.toggle = set;
    } else hd.append(...titleBits);
    head.append(hd); if (action) { const a = h('div', 'ui-section__action'); append(a, action); head.append(a); }
    s.append(head, b); s.body = b;
    return s;
  }

  // ---- tabs ---------------------------------------------------------------------------------------------------
  // items: [{ value, label, count?, icon?, title? }]. A value that matches no item (e.g. '') selects nothing; the first tab then takes focus.
  function tabs({ items = [], value, onChange, style = 'segmented', label = 'Views' } = {}) {
    const list = h('div', `ui-tabs ui-tabs--${style === 'underline' ? 'underline' : 'segmented'}`); list.setAttribute('role', 'tablist'); list.setAttribute('aria-label', label);
    let cur = value != null ? value : (items[0] && items[0].value);
    const tabsEls = items.map(it => {
      const b = btn('ui-tab'); b.setAttribute('role', 'tab'); b.dataset.value = it.value; b.id = nextId('tab');
      if (it.icon) b.append(icon(it.icon));
      b.append(h('span', 'ui-tab__label', it.label)); if (it.count != null) b.append(h('span', 'ui-count', it.count));
      if (it.title) b.title = it.title;
      b.addEventListener('click', () => choose(it.value, true));
      list.append(b); return b;
    });
    function sync() {
      tabsEls.forEach(b => { const on = b.dataset.value === String(cur); b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; });
      if (tabsEls.length && !tabsEls.some(b => b.tabIndex === 0)) tabsEls[0].tabIndex = 0;
    }
    function choose(v, fire) { const changed = String(v) !== String(cur); cur = v; sync(); if (fire && changed && onChange) onChange(v); }
    list.addEventListener('keydown', e => {
      const i = tabsEls.indexOf(document.activeElement); if (i < 0) return;
      let j = null;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') j = (i + 1) % tabsEls.length;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') j = (i - 1 + tabsEls.length) % tabsEls.length;
      else if (e.key === 'Home') j = 0; else if (e.key === 'End') j = tabsEls.length - 1;
      if (j == null) return; e.preventDefault(); tabsEls[j].focus(); choose(items[j].value, true);
    });
    sync();
    list.select = v => choose(v, false);
    Object.defineProperty(list, 'value', { get: () => cur });
    return list;
  }

  // ---- toast --------------------------------------------------------------------------------------------------
  // One queue, one place: bottom centre, above the dock and the phone's safe area. One toast shows at a time.
  const toastQ = []; let toastRegion = null, toastCur = null;
  function region() {
    if (!toastRegion) { toastRegion = h('div', 'ui-toasts'); toastRegion.setAttribute('role', 'status'); toastRegion.setAttribute('aria-live', 'polite'); if (canPopover) toastRegion.popover = 'manual'; }
    const modal = [...document.querySelectorAll('dialog[open]')].filter(d => { try { return d.matches(':modal'); } catch { return false; } }).pop();
    const host = modal || document.body;
    if (toastRegion.parentNode !== host) { try { if (toastRegion.matches(':popover-open')) toastRegion.hidePopover(); } catch {} host.append(toastRegion); }
    if (canPopover) { try { if (toastRegion.matches(':popover-open')) toastRegion.hidePopover(); toastRegion.showPopover(); } catch {} }   // re-show: stays above newer dialogs
    return toastRegion;
  }
  // A toast shown inside a modal dialog moves back out when that dialog closes, so it stays visible.
  document.addEventListener('close', e => { if (toastRegion && toastCur && e.target instanceof HTMLDialogElement && e.target.contains(toastRegion)) region(); }, true);
  function pumpToast() {
    if (toastCur && !toastCur.el.isConnected) { clearTimeout(toastCur.timer); toastCur.done = true; toastCur = null; }   // its dialog was removed with it
    if (toastCur || !toastQ.length) return;
    const t = toastQ.shift(), r = region(); toastCur = t;
    r.append(t.el); requestAnimationFrame(() => t.el.classList.add('ui-toast--in'));
    if (t.timeout > 0) t.timer = setTimeout(() => t.dismiss(), t.timeout);
  }
  function toast(text, { action, timeout, tone: t } = {}) {
    const el = h('div', 'ui-toast' + (t ? ` ui-toast--${tone(t)}` : '')); el.append(h('span', 'ui-toast__text', text));
    const item = { el, timeout: timeout != null ? timeout : (action ? 6000 : 3500), timer: 0, done: false };
    item.dismiss = () => {
      if (item.done) return; item.done = true; clearTimeout(item.timer);
      const i = toastQ.indexOf(item); if (i >= 0) { toastQ.splice(i, 1); return; }
      el.remove(); if (toastCur === item) toastCur = null;
      if (!toastCur && !toastQ.length && toastRegion) { try { if (toastRegion.matches(':popover-open')) toastRegion.hidePopover(); } catch {} }
      pumpToast();
    };
    if (action) { const a = btn('ui-toast__action', () => { item.dismiss(); if (action.onClick) action.onClick(); }); a.textContent = action.label; el.append(a); }
    toastQ.push(item); pumpToast();
    return { el, dismiss: item.dismiss };
  }

  // ---- banner -------------------------------------------------------------------------------------------------
  const TONE_ICON = { info: 'info', accent: 'info', neutral: 'info', ok: 'circle-check', warn: 'triangle-alert', danger: 'circle-x' };
  function banner({ tone: t = 'info', text, action, onDismiss, icon: ic } = {}) {
    const tt = tone(t), b = h('div', `ui-banner ui-banner--${tt}`);
    b.setAttribute('role', tt === 'danger' || tt === 'warn' ? 'alert' : 'status');
    b.append(icon(ic || TONE_ICON[tt]));
    const txt = h('div', 'ui-banner__text'); append(txt, text); b.append(txt);
    if (action) b.append(action instanceof Node ? action : button({ label: action.label, size: 'sm', variant: 'secondary', onClick: action.onClick }));
    if (onDismiss) b.append(iconButton({ icon: 'x', label: 'Dismiss', size: 'sm', onClick: () => { b.remove(); onDismiss(); } }));
    return b;
  }

  // ---- confirm / promptText (replace window.confirm / window.prompt) -------------------------------------------
  function confirm({ title = 'Are you sure?', body, confirmLabel = 'OK', cancelLabel = 'Cancel', danger = false } = {}) {
    return new Promise(resolve => {
      let result = false;
      const cancel = button({ label: cancelLabel, variant: 'secondary', onClick: () => s.close() });
      const ok = button({ label: confirmLabel, variant: danger ? 'danger' : 'primary', onClick: () => { result = true; s.close(); } });
      const bodyEl = body == null ? null : (body instanceof Node ? body : h('p', 'ui-sheet__text', body));
      const s = sheet({ title, body: bodyEl, footer: [cancel, ok], side: 'center', removeOnClose: true, onClose: () => resolve(result) });
      s.el.classList.add('ui-sheet--alert'); s.el.setAttribute('role', 'alertdialog');
      if (bodyEl) { bodyEl.id = bodyEl.id || nextId('confirm'); s.el.setAttribute('aria-describedby', bodyEl.id); }
      s.open(); (danger ? cancel : ok).focus();
    });
  }
  function promptText({ title = 'Enter a value', label = 'Value', value = '', placeholder = '', confirmLabel = 'OK', cancelLabel = 'Cancel', body, type = 'text' } = {}) {
    return new Promise(resolve => {
      let result = null;
      const form = h('form', 'ui-field'), lid = nextId('prompt'), lab = h('label', 'ui-field__label', label), input = h('input', 'ui-input');
      lab.htmlFor = lid; input.id = lid; input.type = type; input.value = value; input.placeholder = placeholder; form.noValidate = true;
      if (body) form.append(body instanceof Node ? body : h('p', 'ui-sheet__text', body));
      form.append(lab, input);
      form.addEventListener('submit', e => { e.preventDefault(); result = input.value; s.close(); });
      const cancel = button({ label: cancelLabel, variant: 'secondary', onClick: () => s.close() });
      const ok = button({ label: confirmLabel, variant: 'primary', onClick: () => form.requestSubmit() });
      const s = sheet({ title, body: form, footer: [cancel, ok], side: 'center', removeOnClose: true, onClose: () => resolve(result) });
      s.el.classList.add('ui-sheet--alert');
      s.open(); input.focus(); input.select();
    });
  }

  // ---- list row -----------------------------------------------------------------------------------------------
  function listRow({ text, meta, href, onRemove, removeLabel, icon: ic } = {}) {
    const row = h('div', 'ui-listrow'), url = href ? safeHref(href) : null;
    const main = url ? h('a', 'ui-listrow__main') : h('span', 'ui-listrow__main');
    if (url) { main.href = url; if (/^https?:/.test(url)) { main.target = '_blank'; main.rel = 'noopener noreferrer'; } }
    if (ic) main.append(icon(ic));
    main.append(h('span', 'ui-listrow__text', text)); row.append(main);
    if (meta) row.append(h('span', 'ui-listrow__meta', meta));
    if (onRemove) row.append(iconButton({ icon: 'x', label: removeLabel || `Remove ${text}`, size: 'sm', onClick: onRemove }));
    return row;
  }

  // ---- task row (pure display) --------------------------------------------------------------------------------
  function taskRow(task = {}, { density = 'row', onOpen } = {}) {
    const dn = ['card', 'row', 'compact'].includes(density) ? density : 'row';
    const root = onOpen ? btn(`ui-task ui-task--${dn} ui-task--button`, () => onOpen(task)) : h('div', `ui-task ui-task--${dn}`);
    const prio = PRIO_TONE[task.priority] ? task.priority : '';
    if (prio) root.classList.add(`ui-task--${prio}`);
    const top = h('span', 'ui-task__top');
    if (task.num != null) top.append(h('span', 'ui-task__num', '#' + task.num));
    if (prio) { const p = priority(prio, { compact: dn === 'compact', size: 'sm' }); p.classList.add('ui-task__prio'); top.append(p); }
    const title = h('span', 'ui-task__title', task.title || 'Untitled');
    const meta = h('span', 'ui-task__meta'), dueEl = due(task.due, { done: !!task.done });
    if (dueEl) { dueEl.classList.add('ui-task__due'); meta.append(dueEl); }
    if (task.client) meta.append(h('span', 'ui-pill ui-pill--accent', task.client));
    (task.labels || []).forEach(l => {
      const name = typeof l === 'string' ? l : l.name, color = typeof l === 'object' && l ? l.color : null;
      const p = h('span', 'ui-pill ui-pill--neutral' + (color ? ' ui-pill--color' : ''), name); if (color) p.style.setProperty('--ui-pill-c', color); meta.append(p);
    });
    const total = +task.todoTotal || 0, doneN = Math.min(+task.todoDone || 0, total);
    if (total) {
      const c = h('span', 'ui-task__todos' + (doneN === total ? ' ui-task__todos--done' : '')); c.append(icon('square-check'), h('span', null, `${doneN}/${total}`)); c.title = `Checklist ${doneN} of ${total} done`;
      if (dn === 'card') { const bar = h('span', 'ui-task__bar'); bar.style.setProperty('--ui-pct', Math.round(doneN / total * 100) + '%'); c.append(bar); }
      meta.append(c);
    }
    root.append(top, title, meta);   // layout per density is in ui.css
    if (!meta.childNodes.length) meta.hidden = true;
    return root;
  }

  // ---- check result line --------------------------------------------------------------------------------------
  const CHECK = { ok: ['circle-check', 'OK'], bad: ['circle-x', 'Problem'], wait: ['loader-circle', 'Checking'], warn: ['triangle-alert', 'Warning'] };
  function check({ state = 'wait', text, fix } = {}) {
    const st = CHECK[state] ? state : 'wait', [ic, word] = CHECK[st], row = h('div', `ui-check ui-check--${st}`);
    row.append(icon(ic));
    const body = h('div', 'ui-check__body'), line = h('div', 'ui-check__text'); line.append(srOnly(word + ': ')); append(line, text); body.append(line);
    if (fix) { const f = h('div', 'ui-check__fix'); append(f, fix); body.append(f); }
    row.append(body);
    if (st === 'wait') row.setAttribute('aria-busy', 'true');
    return row;
  }

  // ---- empty state --------------------------------------------------------------------------------------------
  function empty({ text, action, icon: ic = 'inbox' } = {}) {
    const e = h('div', 'ui-empty'); e.append(icon(ic), h('p', 'ui-empty__text', text));
    if (action) e.append(action instanceof Node ? action : button({ label: action.label, icon: action.icon, variant: 'secondary', size: 'sm', onClick: action.onClick }));
    return e;
  }

  window.ui = Object.freeze({
    button, iconButton, pill, select, avatar, person, colourFor, hueFor, initials, props, addRow, sheet, menu, closeMenu,
    section, tabs, toast, banner, confirm, promptText, listRow, taskRow, check, empty, icon, priority, priorityTone, due, dueInfo
  });
})();
