// DESIGN.md import and export for the Keeptrack board (proposal, 2026-10-08).
// DESIGN.md is Google's open format for design systems (github.com/google-labs-code/design.md, version "alpha"):
// YAML front matter with design tokens, then Markdown prose. Keeptrack reads only `name` and `colors`,
// maps them to its 5 roles (paper, surface, line, ink, hero), and themes.css derives the rest.
// No dependencies. Load after theme.js.
(function () {
  var ROLE_KEYS = {
    paper:   ['paper', 'background', 'bg', 'neutral', 'canvas', 'base'],
    surface: ['surface', 'card', 'surface-container', 'surface-container-lowest', 'container'],
    line:    ['line', 'border', 'outline', 'outline-variant', 'divider'],
    ink:     ['ink', 'text', 'foreground', 'on-background', 'on-surface', 'on-neutral'],
    hero:    ['hero', 'accent', 'brand', 'primary', 'tertiary', 'secondary']
  };

  // Small YAML reader for the front matter: top-level scalars and one level of nested maps. Enough for name and colors.
  function frontMatter(text) {
    var m = /^﻿?---\r?\n([\s\S]*?)\r?\n---\s*(\r?\n|$)/.exec(text);
    if (!m) return null;
    var out = {}, group = null;
    m[1].split(/\r?\n/).forEach(function (line) {
      var raw = line.replace(/\s+#.*$/, '');
      if (!raw.trim() || raw.trim().charAt(0) === '#') return;
      var kv = /^(\s*)([^:]+?):\s*(.*)$/.exec(raw); if (!kv) return;
      var indent = kv[1].length, key = kv[2].trim().replace(/^["']|["']$/g, ''), val = kv[3].trim().replace(/^["']|["']$/g, '');
      if (indent === 0) { if (val === '') { group = out[key] = {}; } else { out[key] = val; group = null; } }
      else if (group && indent <= 2 && val !== '') group[key] = val;
    });
    return out;
  }

  function toRgb(c) {   // any CSS colour to [r,g,b] 0..255, using the browser
    var cv = document.createElement('canvas'); cv.width = cv.height = 1; var x = cv.getContext('2d');
    x.fillStyle = '#000'; x.fillStyle = c; x.fillRect(0, 0, 1, 1); var d = x.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2]];
  }
  function hex(rgb) { return '#' + rgb.map(function (v) { return ('0' + v.toString(16)).slice(-2); }).join(''); }
  function lum(rgb) { var c = rgb.map(function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; }
  function contrast(a, b) { var x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
  function chroma(rgb) { return (Math.max.apply(null, rgb) - Math.min.apply(null, rgb)) / 255; }

  // DESIGN.md token -> Keeptrack roles. Named roles win; then sensible guesses from lightness and colourfulness.
  function toRoles(colors) {
    var all = {}, used = {};
    Object.keys(colors || {}).forEach(function (k) {
      var v = colors[k], ref = /^\{colors\.(.+)\}$/.exec(v); if (ref) v = colors[ref[1]];
      if (v) all[k.toLowerCase()] = toRgb(v);
    });
    var names = Object.keys(all); if (!names.length) throw new Error('No colors found in the DESIGN.md front matter.');
    function pick(role, test) {
      var keys = ROLE_KEYS[role];
      for (var i = 0; i < keys.length; i++) if (all[keys[i]] && !used[keys[i]] && (!test || test(all[keys[i]]))) { used[keys[i]] = 1; return all[keys[i]]; }
      return null;
    }
    var r = {};
    r.paper = pick('paper');
    if (!r.paper) { var lightest = names.slice().sort(function (a, b) { return lum(all[b]) - lum(all[a]); })[0]; r.paper = all[lightest]; used[lightest] = 1; }
    var dark = lum(r.paper) < 0.4;
    r.ink = pick('ink', function (c) { return contrast(c, r.paper) >= 4.5; });
    if (!r.ink) {   // best contrast against paper, else black or white
      var best = names.filter(function (n) { return !used[n]; }).sort(function (a, b) { return contrast(all[b], r.paper) - contrast(all[a], r.paper); })[0];
      if (best && contrast(all[best], r.paper) >= 7) { r.ink = all[best]; used[best] = 1; } else r.ink = dark ? [236, 236, 236] : [17, 17, 17];
    }
    r.hero = pick('hero', function (c) { return chroma(c) > 0.2; });
    if (!r.hero) {
      var vivid = names.filter(function (n) { return !used[n]; }).sort(function (a, b) { return chroma(all[b]) - chroma(all[a]); })[0];
      r.hero = vivid && chroma(all[vivid]) > 0.2 ? (used[vivid] = 1, all[vivid]) : r.ink;
    }
    r.surface = pick('surface'); r.line = pick('line');
    var out = { mode: dark ? 'dark' : 'light' };
    ['paper', 'surface', 'line', 'ink', 'hero'].forEach(function (k) { if (r[k]) out[k] = hex(r[k]); });
    out.onHero = contrast([255, 255, 255], r.hero) >= contrast(dark ? r.paper : r.ink, r.hero) ? '#ffffff' : hex(dark ? r.paper : r.ink);
    out.warnings = [];
    if (contrast(r.ink, r.paper) < 4.5) out.warnings.push('Text contrast is low (' + contrast(r.ink, r.paper).toFixed(1) + ':1).');
    if (contrast(r.hero, r.paper) < 3) out.warnings.push('The accent is hard to see on the page (' + contrast(r.hero, r.paper).toFixed(1) + ':1).');
    return out;
  }

  function parse(text) {
    var fm = frontMatter(text); if (!fm) throw new Error('This file has no YAML front matter (--- at the top).');
    var t = toRoles(fm.colors); t.name = fm.name || 'Imported theme'; return t;
  }

  // Apply a custom theme: CSS variables on <html>, data-theme="custom". Saved so theme.js can restore it before paint.
  function apply(t, save) {
    var s = document.documentElement.style;
    ['paper', 'surface', 'line', 'ink', 'hero'].forEach(function (k) { if (t[k]) s.setProperty('--' + k, t[k]); else s.removeProperty('--' + k); });
    s.setProperty('--on-hero', t.onHero);
    s.setProperty('--lift', t.mode === 'dark' ? t.ink : '#ffffff'); s.setProperty('--lift-pct', t.mode === 'dark' ? '7%' : '70%');
    s.setProperty('--danger', t.mode === 'dark' ? '#ff7a70' : '#c8312b'); s.setProperty('--ok', t.mode === 'dark' ? '#4fd49c' : '#1d7f4e'); s.setProperty('--warn', t.mode === 'dark' ? '#e8b33a' : '#a96a00');
    s.colorScheme = t.mode;
    document.documentElement.setAttribute('data-theme', 'custom');
    if (save !== false) try { localStorage.setItem('kb_custom', JSON.stringify(t)); localStorage.setItem('kb_theme', 'custom'); } catch (e) {}
  }

  // Export the current theme (built-in or custom) as a DESIGN.md file.
  function exportCurrent(name) {
    var cs = getComputedStyle(document.documentElement), keys = ['paper', 'surface', 'line', 'ink', 'hero'], lines = [];
    keys.forEach(function (k) { var v = cs.getPropertyValue('--' + k).trim() || cs.getPropertyValue({ paper: '--bg', surface: '--card', line: '--border', ink: '--text', hero: '--accent' }[k]).trim(); if (v) lines.push('  ' + k + ': "' + hex(toRgb(v)) + '"'); });
    var cur = document.documentElement.getAttribute('data-theme') || 'theme', saved = null;
    if (cur === 'custom') try { saved = JSON.parse(localStorage.getItem('kb_custom') || 'null'); } catch (e) {}
    name = name || (saved && saved.name) || 'Keeptrack ' + cur;
    return '---\nversion: alpha\nname: ' + name + '\ncolors:\n' + lines.join('\n') + '\n---\n\n# ' + name +
      '\n\n## Colors\n\n- **Paper:** page background.\n- **Surface:** cards, header and inputs.\n- **Line:** borders.\n- **Ink:** text and icons.\n- **Hero:** the one accent colour.\n';
  }

  window.kbDesignMd = { parse: parse, apply: apply, exportCurrent: exportCurrent, frontMatter: frontMatter };
})();
