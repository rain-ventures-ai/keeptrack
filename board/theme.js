// Runs in <head> before first paint so the chosen theme never flashes. Themes live in board.css as [data-theme="..."].
// "custom" is a theme imported from a DESIGN.md file (see designmd.js); its colours are saved in localStorage kb_custom.
(function () {
  var THEMES = ['auto', 'light', 'dark', 'midnight', 'sand',
    'paper', 'mono', 'iris', 'forest', 'ember', 'ink',          // 3-colour: paper, ink, hero
    'studio', 'newsprint', 'blueprint', 'graphite', 'custom'];  // 5-colour: paper, surface, line, ink, hero
  var root = document.documentElement, saved = 'auto';
  var scope = '', demo = new URLSearchParams(location.search).has('demo');
  function profile() { try { return JSON.parse(localStorage.getItem('kb_appearance:' + scope) || 'null'); } catch (e) { return null; } }
  function read(key, fallback) { var p = scope && profile(); if (p && p.enabled) return p[key] == null ? fallback : p[key]; try { return localStorage.getItem('kb_' + key) || fallback; } catch (e) { return fallback; } }
  function write(key, value) { try { var p = scope && profile(); if (p && p.enabled) { p[key] = value; localStorage.setItem('kb_appearance:' + scope, JSON.stringify(p)); } else localStorage.setItem('kb_' + key, value); } catch (e) {} }
  try { var q = new URLSearchParams(location.search), repo = q.get('repo') || localStorage.getItem('kb_repo'), boards = JSON.parse(localStorage.getItem('kb_boards') || '{}'), b = boards[repo] || {}; if (repo && !demo) scope = repo + ':' + (b.branch || q.get('branch') || localStorage.getItem('kb_branch') || 'master') + ':' + (b.path || q.get('path') || localStorage.getItem('kb_path') || 'board/tasks.json'); } catch (e) {}
  saved = read('theme', 'auto');
  if (THEMES.indexOf(saved) < 0) saved = 'auto';
  // Paint a custom theme's colours on <html>. Only the 3-5 picked colours, --on-hero and data-mode are set here;
  // lift, status colours (danger/ok/warn) and color-scheme come from board.css ([data-theme="custom"][data-mode="dark"]).
  // designmd.js calls this too (kbTheme.paintCustom), so there is one copy.
  function paintCustom(t) {
    if (!validCustom(t)) return false;
    var s = root.style;
    ['paper', 'surface', 'line', 'ink', 'hero'].forEach(function (k) { if (t[k]) s.setProperty('--' + k, t[k]); else s.removeProperty('--' + k); });
    s.setProperty('--on-hero', t.onHero || '#ffffff');
    root.setAttribute('data-mode', t.mode === 'dark' ? 'dark' : 'light');
    return true;
  }
  function validCustom(t) {
    if (!t || Object.prototype.toString.call(t) !== '[object Object]') return false;
    var hex = /^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
    if (!['paper', 'ink', 'hero'].every(function (k) { return typeof t[k] === 'string' && hex.test(t[k]); })) return false;
    return ['surface', 'line', 'onHero'].every(function (k) { return t[k] == null || (typeof t[k] === 'string' && hex.test(t[k])); });
  }
  function applyCustom() {
    var t = null; try { t = JSON.parse(read('custom', 'null')); } catch (e) {}
    if (!validCustom(t)) return false;
    paintCustom(t); return true;
  }
  function clearCustom() {   // --lift ... --warn and color-scheme: set inline by a designmd.js cached from before paintCustom
    ['--paper', '--surface', '--line', '--ink', '--hero', '--on-hero', '--lift', '--lift-pct', '--danger', '--ok', '--warn'].forEach(function (k) { root.style.removeProperty(k); });
    root.style.colorScheme = ''; root.removeAttribute('data-mode');
  }
  if (saved === 'custom' && !applyCustom()) saved = 'auto';
  root.setAttribute('data-theme', saved);
  var STYLES = ['classic', 'colorful'], style = 'classic';
  style = read('style', 'classic');
  if (STYLES.indexOf(style) < 0) style = 'classic';
  root.setAttribute('data-style', style);
  // Layout packs: how the navigation is arranged. Each pack is a [data-layout="..."] block in board.css over the same
  // buttons, so board.js never forks per layout. To add one: add its name here, an option in Settings, and its CSS block.
  var LAYOUTS = ['dock', 'classic'], layout = 'dock';
  try { layout = localStorage.getItem('kb_layout') || 'dock'; } catch (e) {}
  if (LAYOUTS.indexOf(layout) < 0) layout = 'dock';
  root.setAttribute('data-layout', layout);
  window.kbLayout = {
    list: LAYOUTS,
    set: function (l) { if (LAYOUTS.indexOf(l) < 0) return; root.setAttribute('data-layout', l); try { localStorage.setItem('kb_layout', l); } catch (e) {} },
    get: function () { return root.getAttribute('data-layout'); }
  };
  window.kbStyle = {
    set: function (s) { if (STYLES.indexOf(s) < 0) return; root.setAttribute('data-style', s); write('style', s); },
    get: function () { return root.getAttribute('data-style'); }
  };
  window.kbTheme = {
    list: THEMES,
    custom: function () { return read('custom', 'null'); },
    validateCustom: validCustom,
    saveCustom: function (t) { if (!validCustom(t)) throw new Error('Theme colours must be hex colours.'); write('custom', JSON.stringify(t)); },
    boardAppearance: function () { var p = scope && profile(); return !!(p && p.enabled); },
    useBoard: function (c) { scope = c && c.repo && !demo ? c.repo + ':' + c.branch + ':' + c.path : ''; var theme = read('theme', 'auto'); clearCustom(); if (THEMES.indexOf(theme) < 0 || (theme === 'custom' && !applyCustom())) theme = 'auto'; root.setAttribute('data-theme', theme); var st = read('style', 'classic'); root.setAttribute('data-style', STYLES.indexOf(st) >= 0 ? st : 'classic'); },
    enableBoard: function (enabled) { if (!scope) return; try { var p = profile(); if (!p) p = { theme: read('theme', 'auto'), style: read('style', 'classic'), custom: read('custom', 'null') }; p.enabled = !!enabled; localStorage.setItem('kb_appearance:' + scope, JSON.stringify(p)); } catch (e) {} var theme = read('theme', 'auto'); clearCustom(); if (THEMES.indexOf(theme) < 0 || (theme === 'custom' && !applyCustom())) theme = 'auto'; root.setAttribute('data-theme', theme); var st = read('style', 'classic'); root.setAttribute('data-style', STYLES.indexOf(st) >= 0 ? st : 'classic'); },
    paintCustom: paintCustom,
    set: function (t) {
      if (THEMES.indexOf(t) < 0) return;
      if (t === 'custom') { if (!applyCustom()) return; } else clearCustom();
      root.setAttribute('data-theme', t); write('theme', t);
    },
    get: function () { return root.getAttribute('data-theme'); }
  };
})();
