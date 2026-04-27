/* ═══════════════════════════════════════════════════════════
   Brahm-Kosh Fuzzy Search  (/ or Cmd+K to open)
   All global keyboard shortcuts live here.
═══════════════════════════════════════════════════════════ */

window.Search = (() => {
  let _open = false;
  let _results = [];   // current result set
  let _cursor = -1;    // keyboard-selected index

  /* ── DOM refs (created lazily once) ── */
  let _overlay, _input, _list;

  function _build() {
    if (_overlay) return;

    _overlay = document.createElement('div');
    _overlay.id = 'search-overlay';
    _overlay.innerHTML = `
      <div id="search-modal">
        <div id="search-bar">
          <span class="material-symbols-outlined" style="color:#849495;font-size:18px">search</span>
          <input id="search-input" placeholder="Search files, symbols…" autocomplete="off" spellcheck="false">
          <kbd>ESC</kbd>
        </div>
        <div id="search-meta"></div>
        <div id="search-list"></div>
        <div id="search-footer">
          <span><kbd>↑↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>`;

    document.body.appendChild(_overlay);
    _input = document.getElementById('search-input');
    _list  = document.getElementById('search-list');

    _overlay.addEventListener('click', e => { if (e.target === _overlay) close(); });
    _input.addEventListener('input', () => _query(_input.value));
    _input.addEventListener('keydown', _onKey);
  }

  /* ── search logic ── */
  function _query(raw) {
    const q = raw.trim().toLowerCase();
    const meta = document.getElementById('search-meta');

    if (!q) {
      _results = [];
      _cursor  = -1;
      _list.innerHTML = '';
      meta.textContent = '';
      return;
    }

    if (!window.GlobalGraphData) { _list.innerHTML = ''; return; }

    const fileNodes = window.GlobalGraphData.nodes.filter(n => n.type === 'file');

    // Score: chars in query appear in order inside the path (fuzzy)
    function score(node) {
      const text = node.id.toLowerCase();
      let qi = 0, consecutive = 0, last = -1;
      let sc = 0;
      for (let i = 0; i < text.length && qi < q.length; i++) {
        if (text[i] === q[qi]) {
          consecutive = (i === last + 1) ? consecutive + 1 : 1;
          sc += consecutive;
          last = i;
          qi++;
        }
      }
      if (qi < q.length) return -1; // didn't match all chars
      // Boost exact name matches
      if (node.name.toLowerCase().startsWith(q)) sc += 100;
      return sc;
    }

    _results = fileNodes
      .map(n => ({ node: n, score: score(n) }))
      .filter(r => r.score >= 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 12)
      .map(r => r.node);

    _cursor = _results.length ? 0 : -1;
    meta.textContent = _results.length
      ? `${_results.length} result${_results.length > 1 ? 's' : ''}`
      : 'No results';

    _render();
  }

  function _render() {
    const heatCol = { Critical: '#FF0055', High: '#FF8C00', Medium: '#00F2FF', Low: '#00FF66', Optimal: '#00F2FF' };

    _list.innerHTML = _results.map((n, i) => {
      const parts = n.id.split('/');
      const name  = parts.pop();
      const dir   = parts.join('/');
      const hc    = heatCol[n.heat] || '#849495';
      const isActive = i === _cursor;
      return `
        <div class="sr-row${isActive ? ' sr-active' : ''}" data-idx="${i}">
          <span class="material-symbols-outlined" style="color:${hc};font-size:14px">description</span>
          <div class="sr-info">
            <span class="sr-name">${name}</span>
            <span class="sr-path">${dir || '.'}</span>
          </div>
          <div class="sr-right">
            <span class="sr-lang">${n.language || ''}</span>
            <span class="sr-heat" style="background:${hc}22;color:${hc};border-color:${hc}44">${n.heat}</span>
          </div>
        </div>`;
    }).join('');

    // Click handlers
    _list.querySelectorAll('.sr-row').forEach(row => {
      row.addEventListener('click', () => _select(+row.dataset.idx));
    });
  }

  function _onKey(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _cursor = Math.min(_cursor + 1, _results.length - 1);
      _render();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _cursor = Math.max(_cursor - 1, 0);
      _render();
    } else if (e.key === 'Enter') {
      if (_cursor >= 0) _select(_cursor);
    } else if (e.key === 'Escape') {
      close();
    }
  }

  function _select(idx) {
    const node = _results[idx];
    if (!node) return;
    close();
    // Switch to 3D tab first
    if (window.switchTab) window.switchTab('3d');
    if (window.focusFileNode) window.focusFileNode(node.id);
  }

  /* ── public ── */
  function open() {
    _build();
    _open = true;
    _overlay.classList.add('open');
    _input.value = '';
    _list.innerHTML = '';
    document.getElementById('search-meta').textContent = '';
    _cursor = -1;
    setTimeout(() => _input.focus(), 50);
  }

  function close() {
    if (_overlay) _overlay.classList.remove('open');
    _open = false;
  }

  function toggle() { _open ? close() : open(); }

  return { open, close, toggle };
})();


/* ══════════════════════════════════════════════════════════
   Global Keyboard Shortcuts
══════════════════════════════════════════════════════════ */
document.addEventListener('keydown', e => {
  // Don't fire inside text inputs / textareas / the CE editor
  const tag = document.activeElement?.tagName;
  const inInput = tag === 'INPUT' || tag === 'TEXTAREA';

  // Cmd+K or / → open search
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    Search.toggle();
    return;
  }
  if (e.key === '/' && !inInput && !document.getElementById('ce-overlay')?.classList.contains('open')) {
    e.preventDefault();
    Search.open();
    return;
  }

  if (inInput) return; // rest of shortcuts don't apply inside inputs

  // Esc → clear focus / close CE / close search
  if (e.key === 'Escape') {
    if (document.getElementById('search-overlay')?.classList.contains('open')) {
      Search.close();
    } else if (document.getElementById('ce-overlay')?.classList.contains('open')) {
      if (window.CE) CE.close();
    } else if (window.clearFocus) {
      window.clearFocus();
    }
    return;
  }

  // R → re-center camera
  if (e.key === 'r' || e.key === 'R') {
    if (window.GraphEngine) {
      window.GraphEngine.cameraPosition({ x: 0, y: 0, z: 300 }, { x: 0, y: 0, z: 0 }, 1000);
    }
    return;
  }

  // F → toggle fullscreen
  if (e.key === 'f' || e.key === 'F') {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
    return;
  }

  // 1 → 3D tab, 2 → list tab
  if (e.key === '1' && window.switchTab) { window.switchTab('3d');   return; }
  if (e.key === '2' && window.switchTab) { window.switchTab('list'); return; }
});
