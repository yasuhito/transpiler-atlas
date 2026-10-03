'use strict';

(() => {
  const key = 'transpiler-atlas-theme';
  const modes = ['light', 'dark', 'system'];
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const read = () => {
    try {
      const saved = localStorage.getItem(key);
      return modes.includes(saved) ? saved : 'system';
    } catch { return 'system'; }
  };
  let mode = read();
  function apply() {
    document.documentElement.dataset.theme = mode === 'system' ? (media.matches ? 'dark' : 'light') : mode;
    const control = document.getElementById('theme');
    if (control) control.value = mode;
  }
  apply();
  media.addEventListener('change', apply);
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) { mode = read(); apply(); }
  });
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.getElementById('theme')?.addEventListener('change', event => {
      if (!modes.includes(event.target.value)) return;
      mode = event.target.value;
      try { localStorage.setItem(key, mode); } catch { /* file:// may block storage */ }
      apply();
    });
  });
})();
