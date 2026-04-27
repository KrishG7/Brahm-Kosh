/* ═══════════════════════════════════════════════════════════════
   Brahm-Kosh Graph Extras
   Runs AFTER the main Graph engine is initialised.
   Hooks in via window.onGraphReady (called at end of <script>).
═══════════════════════════════════════════════════════════════ */

// ── Auto-rotate: lean wrapper around Three.js OrbitControls.autoRotate ────────
//
// Don't override cameraPosition manually — the inline init code already enables
// `Graph.controls().autoRotate`. We just toggle that flag in response to user
// interaction and focus state. This avoids fighting the OrbitControls renderer
// for the camera and avoids the "30s later, camera teleports back" bug when a
// user has flown the camera to a focused node.
const AutoRotate = (() => {
  let _idleTimer = null;
  let _resumeAfterMs = 60000;  // resume rotating after a minute of idle
  let _wasEnabledByUser = true; // last desired state (toggled by interaction)

  function _controls() {
    return window.GraphEngine?.controls?.();
  }

  function _set(enabled) {
    const c = _controls();
    if (c) c.autoRotate = enabled;
  }

  function pause() {
    _wasEnabledByUser = false;
    _set(false);
    clearTimeout(_idleTimer);
  }

  function scheduleResume() {
    clearTimeout(_idleTimer);
    _idleTimer = setTimeout(() => {
      // Only resume if nothing is currently focused — never yank a focused
      // user's camera back to the origin.
      if (!window.SelectedNodeId) {
        _wasEnabledByUser = true;
        _set(true);
      }
    }, _resumeAfterMs);
  }

  let _inited = false;
  function init() {
    if (_inited) return;          // idempotent — refresh re-runs init()
    const el = document.getElementById('3d-graph');
    if (!el) return;
    _inited = true;
    ['mousedown', 'touchstart', 'wheel', 'keydown'].forEach(ev => {
      el.addEventListener(ev, () => {
        pause();
        scheduleResume();
      }, { passive: true });
    });
  }

  // Public API — called by focusFileNode/clearFocus so focus mode disables
  // the rotation while inspecting a file, then restores when focus clears.
  function suspendForFocus() { _set(false); }
  function maybeRestore()    { if (_wasEnabledByUser) _set(true); }

  return { init, pause, suspendForFocus, maybeRestore };
})();
window.AutoRotate = AutoRotate;

// ── First-interaction hint ────────────────────────────────────────────────────
let _hintInited = false;
function _initInteractionHint() {
  if (_hintInited) return;        // idempotent across refreshes
  _hintInited = true;
  const hint = document.getElementById('interaction-hint');
  if (!hint) return;
  let dismissed = false;
  const dismiss = () => {
    if (dismissed) return;
    dismissed = true;
    hint.style.opacity = '0';
    setTimeout(() => hint.remove(), 600);
  };
  setTimeout(dismiss, 6000);
  ['mousedown', 'touchstart', 'wheel'].forEach(ev =>
    document.getElementById('3d-graph')?.addEventListener(ev, dismiss, { once: true, passive: true })
  );
}

// ── Language filter chips ─────────────────────────────────────────────────────
//
// Semantics: `_active` is the set of languages currently being shown. When the
// set is empty (the default), ALL languages are visible — that's what the "All"
// chip means. Clicking a specific lang chip starts a positive filter; clicking
// it again removes it from the filter; clicking "All" resets.
//
// The chip's `active` class always mirrors the data state — clicking a
// deactivated chip activates it (visually highlighted) and adds the lang to
// the filter set. Previously the visual was inverted.
const LangFilter = (() => {
  let _active = new Set();  // empty = show all; otherwise show only these

  function _renderActiveStates(container) {
    const filteringNothing = _active.size === 0;
    container.querySelectorAll('.lang-chip').forEach(b => {
      const lang = b.dataset.lang;
      if (lang === '__all') {
        b.classList.toggle('active', filteringNothing);
      } else {
        b.classList.toggle('active', _active.has(lang));
      }
    });
  }

  function build(graphData) {
    const container = document.getElementById('lang-filter-chips');
    if (!container) return;

    const langs = [...new Set(
      graphData.nodes
        .filter(n => n.type === 'file' && n.language)
        .map(n => n.language)
    )].sort();

    if (langs.length < 2) { container.style.display = 'none'; return; }
    container.style.display = 'flex';

    // Drop any active filters that no longer exist (file set may have shrunk)
    for (const l of [..._active]) if (!langs.includes(l)) _active.delete(l);

    container.innerHTML =
      `<button class="lang-chip lang-chip-all" data-lang="__all">All</button>` +
      langs.map(l => `<button class="lang-chip" data-lang="${l}">${l}</button>`).join('');

    _renderActiveStates(container);

    container.querySelectorAll('.lang-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const lang = btn.dataset.lang;
        if (lang === '__all') {
          _active.clear();
        } else if (_active.has(lang)) {
          _active.delete(lang);
        } else {
          _active.add(lang);
        }
        _renderActiveStates(container);
        _apply();
      });
    });
  }

  function _apply() {
    window.activeLangFilters = _active;
    if (window.refreshGraphView) window.refreshGraphView();
  }

  return { build };
})();

// ── Domain chip filter ────────────────────────────────────────────────────────
const DomainFilter = (() => {
  let _active = null; // null = show all

  function build(graphData) {
    const container = document.getElementById('domain-filter-chips');
    if (!container) return;

    const domains = [...new Set(
      graphData.nodes
        .filter(n => n.type === 'file' && n.domains?.length)
        .flatMap(n => n.domains)
    )].sort();

    if (!domains.length) { container.style.display = 'none'; return; }
    container.style.display = 'flex';

    const domainIcons = {
      database: '🗄', ui: '🎨', network: '🌐', auth: '🔐',
      config: '⚙', test: '🧪', util: '🔧', model: '📐', api: '🔌',
    };

    container.innerHTML =
      `<span style="font-size:10px;color:#849495;text-transform:uppercase;letter-spacing:.1em;align-self:center">Domain:</span>` +
      domains.map(d =>
        `<button class="domain-chip${_active === d ? ' active' : ''}" data-domain="${d}">${domainIcons[d] || '◆'} ${d}</button>`
      ).join('') +
      `<button class="domain-chip${!_active ? ' active' : ''}" data-domain="__all">All</button>`;

    container.querySelectorAll('.domain-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const d = btn.dataset.domain;
        _active = (d === '__all' || _active === d) ? null : d;
        container.querySelectorAll('.domain-chip').forEach(b => b.classList.remove('active'));
        const activeBtn = d === '__all' || _active === null
          ? container.querySelector('[data-domain="__all"]')
          : container.querySelector(`[data-domain="${_active}"]`);
        activeBtn?.classList.add('active');
        _apply();
      });
    });
  }

  function _apply() {
    window.activeDomainFilter = _active;
    if (window.refreshGraphView) window.refreshGraphView();
  }

  return { build };
})();

// ── Cluster labels (folder name text floating near cluster centroid) ───────────
const ClusterLabels = (() => {
  let _labels = [];
  let _rafId  = null;

  function _centroid(nodes) {
    if (!nodes.length) return { x: 0, y: 0, z: 0 };
    let sx = 0, sy = 0, sz = 0;
    nodes.forEach(n => { sx += n.x || 0; sy += n.y || 0; sz += n.z || 0; });
    return { x: sx / nodes.length, y: sy / nodes.length, z: sz / nodes.length };
  }

  // Single rAF loop — never spawns a duplicate. Reads `_labels` fresh each
  // frame, so swapping the labels via update() is naturally picked up.
  function _positionLoop() {
    if (!_labels.length || !window.GraphEngine) {
      _rafId = null;
      return;
    }
    const G = window.GraphEngine;
    const gd = G.graphData();
    // Build a parent → live-nodes map once per frame instead of N filters
    const buckets = {};
    for (const n of gd.nodes) {
      if (n.type === 'file' && typeof n.x === 'number' && n.parent) {
        (buckets[n.parent] = buckets[n.parent] || []).push(n);
      }
    }
    _labels.forEach(({ label, folderId }) => {
      const liveNodes = buckets[folderId];
      if (!liveNodes || !liveNodes.length) {
        label.style.display = 'none';
        return;
      }
      const c = _centroid(liveNodes);
      const screen = G.graph2ScreenCoords(c.x, c.y, c.z);
      if (!screen) return;
      label.style.left = `${screen.x}px`;
      label.style.top  = `${screen.y}px`;
      label.style.display = 'block';
    });
    _rafId = requestAnimationFrame(_positionLoop);
  }

  function _remove() {
    if (_rafId !== null) {
      cancelAnimationFrame(_rafId);
      _rafId = null;
    }
    _labels.forEach(({ label }) => label.remove());
    _labels = [];
  }

  function update(graphData) {
    _remove();
    if (!window.GraphEngine) return;
    const host = document.getElementById('3d-graph');
    if (!host) return;

    const folderFiles = {};
    graphData.nodes.forEach(n => {
      if (n.type === 'file' && n.parent) {
        (folderFiles[n.parent] = folderFiles[n.parent] || []).push(n);
      }
    });

    Object.entries(folderFiles).forEach(([folderId, files]) => {
      if (files.length < 2) return;
      const folderNode = graphData.nodes.find(n => n.id === folderId);
      if (!folderNode || folderId === 'root') return;

      const label = document.createElement('div');
      label.className = 'cluster-label';
      label.textContent = folderNode.name;
      host.appendChild(label);
      _labels.push({ label, folderId });
    });

    if (_labels.length && _rafId === null) {
      _rafId = requestAnimationFrame(_positionLoop);
    }
  }

  return { update };
})();

// ── Watch-mode "changed files" banner ─────────────────────────────────────────
const ChangedBanner = (() => {
  let _timer = null;

  function show(files) {
    let banner = document.getElementById('changed-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'changed-banner';
      document.querySelector('main')?.appendChild(banner);
    }
    const names = files.slice(0, 4).map(f => f.split('/').pop()).join(', ');
    const extra = files.length > 4 ? ` +${files.length - 4} more` : '';
    banner.innerHTML = `
      <span class="material-symbols-outlined" style="font-size:14px">sync</span>
      <strong>${files.length} file${files.length > 1 ? 's' : ''} updated:</strong> ${names}${extra}`;
    banner.classList.add('visible');
    clearTimeout(_timer);
    _timer = setTimeout(() => banner.classList.remove('visible'), 5000);
  }

  return { show };
})();

// ── Collapsible arch panel sections ──────────────────────────────────────────
// Idempotent: each section is wired exactly once. initGraphExtras() runs
// on every SSE refresh; without the dataset guard, every refresh stacked
// another chevron + click handler, so each click toggled the section 2×
// (visually no change).
function makeCollapsible() {
  const panel = document.getElementById('ai-panel');
  if (!panel) return;
  panel.querySelectorAll('.arch-section').forEach((section, idx) => {
    if (section.dataset.collapsibleInited === '1') return;
    const header = section.querySelector('.arch-section-header');
    const body   = section.querySelector('.arch-section-body');
    if (!header || !body) return;

    // Defensive: drop any chevron a previous (buggy) run left behind.
    header.querySelectorAll('.arch-chevron').forEach(c => c.remove());

    const chevron = document.createElement('span');
    chevron.className = 'material-symbols-outlined arch-chevron';
    chevron.textContent = idx === 0 ? 'expand_less' : 'expand_more';
    header.appendChild(chevron);

    if (idx > 0) body.style.display = 'none';

    header.style.cursor = 'pointer';
    header.addEventListener('click', () => {
      const isOpen = body.style.display !== 'none';
      body.style.display = isOpen ? 'none' : 'block';
      chevron.textContent = isOpen ? 'expand_more' : 'expand_less';
    });

    section.dataset.collapsibleInited = '1';
  });
}

// ── Expose init hook ─────────────────────────────────────────────────────────
window.initGraphExtras = function(graphData) {
  AutoRotate.init();
  _initInteractionHint();
  LangFilter.build(graphData);
  DomainFilter.build(graphData);
  ClusterLabels.update(graphData);
  makeCollapsible();
};

// When graph data refreshes (SSE) — rebuild labels + filter chips
window._onGraphRefreshed = function(graphData) {
  LangFilter.build(graphData);
  DomainFilter.build(graphData);
  ClusterLabels.update(graphData);

  // Detect changed files by comparing node mtime… or if the server
  // passes a `changed` list in the SSE payload, use that.
  // For now we read from the SSE detail if available.
};

window._reportChangedFiles = function(files) {
  ChangedBanner.show(files);
};
