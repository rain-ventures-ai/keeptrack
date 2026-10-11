// Runs in <head> before first paint so the chosen theme never flashes. Themes live in board.css as [data-theme="..."].
// "custom" is a theme imported from a DESIGN.md file (see designmd.js); its colours are saved in localStorage kb_custom.
(function () {
  var THEMES = ['auto', 'light', 'dark', 'midnight', 'sand',
    'paper', 'mono', 'iris', 'forest', 'ember', 'ink',          // 3-colour: paper, ink, hero
    'studio', 'newsprint', 'blueprint', 'graphite', 'custom'];  // 5-colour: paper, surface, line, ink, hero
  var root = document.documentElement, saved = 'auto';
  try { saved = localStorage.getItem('kb_theme') || 'auto'; } catch (e) {}
  if (THEMES.indexOf(saved) < 0) saved = 'auto';
  // Paint a custom theme's colours on <html>. Only the 3-5 picked colours, --on-hero and data-mode are set here;
  // lift, status colours (danger/ok/warn) and color-scheme come from board.css ([data-theme="custom"][data-mode="dark"]).
  // designmd.js calls this too (kbTheme.paintCustom), so there is one copy.
  function paintCustom(t) {
    var s = root.style;
    ['paper', 'surface', 'line', 'ink', 'hero'].forEach(function (k) { if (t[k]) s.setProperty('--' + k, t[k]); else s.removeProperty('--' + k); });
    s.setProperty('--on-hero', t.onHero || '#ffffff');
    root.setAttribute('data-mode', t.mode === 'dark' ? 'dark' : 'light');
  }
  function applyCustom() {
    var t = null; try { t = JSON.parse(localStorage.getItem('kb_custom') || 'null'); } catch (e) {}
    if (!t || !t.paper || !t.ink || !t.hero) return false;
    paintCustom(t); return true;
  }
  function clearCustom() {   // --lift ... --warn and color-scheme: set inline by a designmd.js cached from before paintCustom
    ['--paper', '--surface', '--line', '--ink', '--hero', '--on-hero', '--lift', '--lift-pct', '--danger', '--ok', '--warn'].forEach(function (k) { root.style.removeProperty(k); });
    root.style.colorScheme = ''; root.removeAttribute('data-mode');
  }
  if (saved === 'custom' && !applyCustom()) saved = 'auto';
  root.setAttribute('data-theme', saved);
  var STYLES = ['classic', 'colorful'], style = 'classic';
  try { style = localStorage.getItem('kb_style') || 'classic'; } catch (e) {}
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
    set: function (s) { if (STYLES.indexOf(s) < 0) return; root.setAttribute('data-style', s); try { localStorage.setItem('kb_style', s); } catch (e) {} },
    get: function () { return root.getAttribute('data-style'); }
  };
  window.kbTheme = {
    list: THEMES,
    paintCustom: paintCustom,
    set: function (t) {
      if (THEMES.indexOf(t) < 0) return;
      if (t === 'custom') { if (!applyCustom()) return; } else clearCustom();
      root.setAttribute('data-theme', t); try { localStorage.setItem('kb_theme', t); } catch (e) {}
    },
    get: function () { return root.getAttribute('data-theme'); }
  };
})();
