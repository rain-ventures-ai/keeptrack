// Runs in <head> before first paint so the chosen theme never flashes. Themes live in board.css as [data-theme="..."].
// "custom" is a theme imported from a DESIGN.md file (see designmd.js); its colours are saved in localStorage kb_custom.
(function () {
  var THEMES = ['auto', 'light', 'dark', 'midnight', 'sand',
    'paper', 'mono', 'iris', 'forest', 'ember', 'ink',          // 3-colour: paper, ink, hero
    'studio', 'newsprint', 'blueprint', 'graphite', 'custom'];  // 5-colour: paper, surface, line, ink, hero
  var root = document.documentElement, saved = 'auto';
  try { saved = localStorage.getItem('kb_theme') || 'auto'; } catch (e) {}
  if (THEMES.indexOf(saved) < 0) saved = 'auto';
  function applyCustom() {   // same variables as kbDesignMd.apply, kept here so there is no flash before designmd.js loads
    var t = null; try { t = JSON.parse(localStorage.getItem('kb_custom') || 'null'); } catch (e) {}
    if (!t || !t.paper || !t.ink || !t.hero) return false;
    var s = root.style, dark = t.mode === 'dark';
    ['paper', 'surface', 'line', 'ink', 'hero'].forEach(function (k) { if (t[k]) s.setProperty('--' + k, t[k]); });
    s.setProperty('--on-hero', t.onHero || '#ffffff'); s.setProperty('--lift', dark ? t.ink : '#ffffff'); s.setProperty('--lift-pct', dark ? '7%' : '70%');
    s.setProperty('--danger', dark ? '#ff7a70' : '#c8312b'); s.setProperty('--ok', dark ? '#4fd49c' : '#1d7f4e'); s.setProperty('--warn', dark ? '#e8b33a' : '#a96a00');
    s.colorScheme = dark ? 'dark' : 'light'; return true;
  }
  function clearCustom() { ['--paper', '--surface', '--line', '--ink', '--hero', '--on-hero', '--lift', '--lift-pct', '--danger', '--ok', '--warn'].forEach(function (k) { root.style.removeProperty(k); }); root.style.colorScheme = ''; }
  if (saved === 'custom' && !applyCustom()) saved = 'auto';
  root.setAttribute('data-theme', saved);
  var STYLES = ['classic', 'colorful'], style = 'classic';
  try { style = localStorage.getItem('kb_style') || 'classic'; } catch (e) {}
  if (STYLES.indexOf(style) < 0) style = 'classic';
  root.setAttribute('data-style', style);
  window.kbStyle = {
    set: function (s) { if (STYLES.indexOf(s) < 0) return; root.setAttribute('data-style', s); try { localStorage.setItem('kb_style', s); } catch (e) {} },
    get: function () { return root.getAttribute('data-style'); }
  };
  window.kbTheme = {
    list: THEMES,
    set: function (t) {
      if (THEMES.indexOf(t) < 0) return;
      if (t === 'custom') { if (!applyCustom()) return; } else clearCustom();
      root.setAttribute('data-theme', t); try { localStorage.setItem('kb_theme', t); } catch (e) {}
    },
    get: function () { return root.getAttribute('data-theme'); }
  };
})();
