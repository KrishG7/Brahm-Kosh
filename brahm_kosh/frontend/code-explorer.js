/* ═══════════════════════════════════════════════════════════════
   Brahm-Kosh Code Explorer
   Opens when a file node is clicked in the 3D graph.
   Features: source view, syntax highlight, symbol list,
             dependency map, edit mode, save, blast radius.
═══════════════════════════════════════════════════════════════ */

const CE = (() => {
  // ── state ────────────────────────────────────────────────────
  let state = {
    fileData: null,       // full /api/file response
    activeSymIdx: null,   // currently highlighted symbol index
    editMode: false,      // true when textarea is active
    dirty: false,         // unsaved changes flag
    sidebarTab: 'symbols' // 'symbols' | 'deps'
  };

  const heatColors = {
    Critical: '#FF0055', High: '#FF8C00', Medium: '#00F2FF',
    Low: '#00FF66', Optimal: '#00F2FF'
  };

  const langMap = {
    python: 'python', javascript: 'javascript', typescript: 'typescript',
    c: 'c', 'c++': 'cpp', cpp: 'cpp', java: 'java', go: 'go', rust: 'rust',
    dart: 'dart', php: 'php', html: 'html', css: 'css', sql: 'sql',
    r: 'r', 'c#': 'csharp', csharp: 'csharp'
  };

  const kindIcons = {
    function: '⚡', method: '🔹', class: '🔷',
    module: '📦', html_node: '🏷', css_rule: '🎨'
  };

  // ── DOM helpers ──────────────────────────────────────────────
  const $ = id => document.getElementById(id);

  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  // ── public: open explorer for a graph node ───────────────────
  function open(nodeData) {
    if (!nodeData || nodeData.type !== 'file') return;
    state = { fileData: null, activeSymIdx: null, editMode: false, dirty: false, sidebarTab: 'symbols' };

    _showOverlay();
    _setLoading(nodeData.name, nodeData.id);

    fetch(`/api/file?path=${encodeURIComponent(nodeData.id)}`)
      .then(r => r.json())
      .then(data => {
        state.fileData = data;
        _render(data);
      })
      .catch(err => _setError(err));
  }

  function close() {
    if (state.dirty && !confirm('You have unsaved changes. Close anyway?')) return;
    $('ce-overlay').classList.remove('open');
    state = { fileData: null, activeSymIdx: null, editMode: false, dirty: false, sidebarTab: 'symbols' };
  }

  // ── overlay ──────────────────────────────────────────────────
  function _showOverlay() {
    const ov = $('ce-overlay');
    ov.classList.add('open');
  }

  function _setLoading(name, path) {
    $('ce-title').textContent = name;
    $('ce-subtitle').textContent = path;
    $('ce-badges').innerHTML = '';
    $('ce-sidebar-content').innerHTML =
      '<div style="color:#849495;font-size:12px;padding:20px;text-align:center">Loading…</div>';
    $('ce-line-nums').textContent = '';
    $('ce-code-view').innerHTML = '<span style="color:#849495">Fetching source…</span>';
    $('ce-code-edit').value = '';
    $('ce-narration').classList.remove('visible');
    $('ce-blast-bar').classList.remove('visible');
    $('ce-save-status').textContent = '';
  }

  function _setError(err) {
    $('ce-code-view').innerHTML = `<span style="color:#ff0055">Error: ${err}</span>`;
    $('ce-sidebar-content').innerHTML = '';
  }

  // ── main render ──────────────────────────────────────────────
  function _render(d) {
    // Header
    $('ce-title').textContent = d.name;
    $('ce-subtitle').textContent = `${d.path}  ·  ${d.line_count} lines  ·  ${d.symbols.length} symbols`;

    const badges = $('ce-badges');
    badges.innerHTML = '';
    const langB = el('span', `ce-badge lang`);
    langB.textContent = d.language || 'Unknown';
    badges.appendChild(langB);
    const heatB = el('span', `ce-badge heat-${d.heat}`);
    heatB.textContent = d.heat;
    badges.appendChild(heatB);
    if (d.purpose) {
      const purB = el('span', 'ce-badge lang');
      purB.style.cssText = 'background:rgba(255,255,255,0.06);color:#ccc;border-color:rgba(255,255,255,0.1)';
      purB.textContent = d.purpose;
      badges.appendChild(purB);
    }
    // Domain badges — colored chips for each concern this file touches
    if (d.domains && d.domains.length) {
      d.domains.forEach(dom => {
        const b = el('span', 'ce-badge ce-domain');
        b.textContent = dom;
        b.style.cssText = 'background:rgba(168,85,247,0.15);color:#C084FC;border:1px solid rgba(168,85,247,0.4)';
        badges.appendChild(b);
      });
    }

    // Narration (collapsible)
    const narEl = $('ce-narration');
    if (d.narration) {
      narEl.innerHTML = `
        <div class="ce-strip-header" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none';this.querySelector('.ce-strip-chevron').classList.toggle('collapsed')">
          <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#00f2ff">📖 Narration</span>
          <span class="material-symbols-outlined ce-strip-chevron">expand_less</span>
        </div>
        <div class="ce-strip-body" style="margin-top:6px;font-size:12px;color:#adb5bd;line-height:1.6">${d.narration}</div>`;
      narEl.classList.add('visible');
    } else {
      narEl.classList.remove('visible');
    }

    // Source code
    _renderCode(d.source, d.language);

    // Sidebar
    _renderSidebar();

    // Refactor suggestions card (if file has disconnected symbol clusters)
    _renderRefactorCard(d);

    // Multi-hop impact panel (fetched separately)
    _renderImpactPanel(d);

    // Blast radius bar (legacy direct-deps row)
    _renderBlastBar(d);
  }

  // ── refactor suggestions ──────────────────────────────────────
  function _renderRefactorCard(d) {
    const card = $('ce-refactor');
    if (!card) return;
    if (!d.refactor || d.refactor.length < 2) {
      card.classList.remove('visible');
      card.innerHTML = '';
      return;
    }
    const groups = d.refactor.map((c, i) => {
      const members = c.members.slice(0, 5).join(', ') + (c.members.length > 5 ? `, +${c.members.length - 5}` : '');
      return `<div class="ce-refactor-group">
        <div class="ce-refactor-group-head">
          <span class="ce-refactor-num">${i + 1}</span>
          <span class="ce-refactor-purpose">${c.suggested_purpose}</span>
          <span class="ce-refactor-lines">L${c.line_start}–${c.line_end} · ${c.size} symbols</span>
        </div>
        <div class="ce-refactor-members">${members}</div>
      </div>`;
    }).join('');
    card.innerHTML = `
      <div class="ce-refactor-head">
        <span class="material-symbols-outlined" style="font-size:16px;color:#34D399">call_split</span>
        <span>Refactor suggestion</span>
        <span class="ce-refactor-count">${d.refactor.length} disjoint groups</span>
      </div>
      <div class="ce-refactor-body">These symbol groups never call each other — natural split points.</div>
      ${groups}
    `;
    card.classList.add('visible');
  }

  // ── multi-hop impact ──────────────────────────────────────────
  function _renderImpactPanel(d) {
    const card = $('ce-impact');
    if (!card) return;
    card.classList.remove('visible');
    card.innerHTML = '<div class="ce-impact-loading">Computing impact…</div>';
    fetch(`/api/impact?path=${encodeURIComponent(d.path)}`)
      .then(r => r.json())
      .then(impact => {
        const up = impact.upstream || {};
        const down = impact.downstream || {};
        if (!up.total_count && !down.total_count) {
          card.classList.remove('visible');
          card.innerHTML = '';
          return;
        }
        const upHops = _hopBreakdown(up);
        const downHops = _hopBreakdown(down);
        card.innerHTML = `
          <div class="ce-impact-head">
            <span class="material-symbols-outlined" style="font-size:16px;color:#FF8C00">radar</span>
            <span>Multi-hop impact</span>
          </div>
          <div class="ce-impact-grid">
            <div class="ce-impact-col">
              <div class="ce-impact-title" style="color:#FF8C00">⬅ If you change this</div>
              <div class="ce-impact-big">${up.total_count}</div>
              <div class="ce-impact-sub">files break (${up.direct.length} direct, ${up.indirect.length} indirect)</div>
              ${upHops}
            </div>
            <div class="ce-impact-col">
              <div class="ce-impact-title" style="color:#00F2FF">➡ This relies on</div>
              <div class="ce-impact-big">${down.total_count}</div>
              <div class="ce-impact-sub">files (${down.direct.length} direct, ${down.indirect.length} indirect)</div>
              ${downHops}
            </div>
          </div>
        `;
        card.classList.add('visible');

        // Make every listed file clickable — focuses that node in the graph
        card.querySelectorAll('.ce-impact-file').forEach(elem => {
          elem.addEventListener('click', () => {
            const path = elem.getAttribute('data-path');
            if (path) _pingNode(path);
          });
        });
      })
      .catch(() => {
        card.classList.remove('visible');
        card.innerHTML = '';
      });
  }

  // ── inline symbol usage expansion ─────────────────────────────
  function _toggleSymbolUsageList(card, symName) {
    const list = card.querySelector(`.ce-sym-usage-list[data-sym="${symName}"]`);
    if (!list) return;
    if (list.classList.contains('visible')) {
      list.classList.remove('visible');
      return;
    }
    if (!list.dataset.loaded) {
      list.classList.add('visible');
      list.innerHTML = '<div class="ce-impact-loading">Resolving usages…</div>';
      const path = encodeURIComponent(state.fileData.path);
      const sym = encodeURIComponent(symName);
      fetch(`/api/symbol-impact?file=${path}&symbol=${sym}`)
        .then(r => r.json())
        .then(data => {
          list.dataset.loaded = '1';
          if (!data.usage_count) {
            list.innerHTML = '<div style="font-size:11px;color:#6b7280;padding:6px 0;font-style:italic">No external references found.</div>';
            return;
          }
          const grouped = {};
          data.usages.forEach(u => {
            (grouped[u.file] = grouped[u.file] || []).push(u.line);
          });
          const rows = Object.entries(grouped).map(([file, lines]) => {
            const safe = file.replace(/"/g, '&quot;');
            const linesText = lines.slice(0, 4).join(', ') + (lines.length > 4 ? `, +${lines.length - 4}` : '');
            return `<div class="ce-sym-usage-row" data-path="${safe}"
                         title="Click to focus ${safe}">
                      <span class="ce-sym-usage-file">📄 ${file.split('/').pop()}</span>
                      <span class="ce-sym-usage-lines">L${linesText}</span>
                    </div>`;
          }).join('');
          list.innerHTML = `
            <div class="ce-sym-usage-summary">${data.usage_count} reference${data.usage_count === 1 ? '' : 's'} across ${data.file_count} file${data.file_count === 1 ? '' : 's'}</div>
            ${rows}
          `;
          list.querySelectorAll('.ce-sym-usage-row').forEach(row => {
            row.addEventListener('click', () => {
              const p = row.getAttribute('data-path');
              if (p) _pingNode(p);
            });
          });
        })
        .catch(() => {
          list.innerHTML = '<div style="font-size:11px;color:#ff0055;padding:6px 0">Failed to fetch usages.</div>';
        });
    } else {
      list.classList.add('visible');
    }
  }

  function _hopBreakdown(side) {
    if (!side || !side.by_hop) return '';
    const entries = Object.entries(side.by_hop).slice(0, 4);
    return entries.map(([hop, files]) => {
      const items = files.slice(0, 3).map(f => {
        const safe = f.replace(/"/g, '&quot;');
        return `<span class="ce-impact-file" data-path="${safe}" title="${safe}">${f.split('/').pop()}</span>`;
      }).join('');
      const more = files.length > 3 ? `<span class="ce-impact-more">+${files.length - 3}</span>` : '';
      return `<div class="ce-impact-hop"><span class="ce-impact-hop-label">hop ${hop}</span>${items}${more}</div>`;
    }).join('');
  }

  // ── code rendering ───────────────────────────────────────────
  function _renderCode(source, language) {
    const view = $('ce-code-view');
    const edit = $('ce-code-edit');

    edit.value = source;

    const lang = langMap[(language || '').toLowerCase()];
    let highlighted;
    if (lang && window.hljs && hljs.getLanguage(lang)) {
      try { highlighted = hljs.highlight(source, { language: lang }).value; }
      catch { highlighted = _escapeHtml(source); }
    } else {
      highlighted = _escapeHtml(source);
    }
    view.innerHTML = highlighted;

    const lines = source.split('\n');
    const syms  = state.fileData?.symbols || [];

    // Build per-line heat from symbols
    const lineHeat = {};
    const heatRank = { Critical: 4, High: 3, Medium: 2, Low: 1, Optimal: 0 };
    syms.forEach(sym => {
      const hc = heatColors[sym.heat];
      if (!hc) return;
      for (let i = sym.line_start; i <= sym.line_end; i++) {
        if (!lineHeat[i] || (heatRank[sym.heat] > heatRank[lineHeat[i].label])) {
          lineHeat[i] = { color: hc, label: sym.heat };
        }
      }
    });

    // Render line numbers + heatmap gutter
    let lineNumHtml = '';
    let gutterHtml  = '';
    lines.forEach((_, i) => {
      const li = i + 1;
      const h  = lineHeat[li];
      lineNumHtml += `<div id="ln-${li}">${li}</div>`;
      gutterHtml  += `<div style="height:1.65em;background:${h ? h.color + '55' : 'transparent'}"></div>`;
    });
    $('ce-line-nums').innerHTML = lineNumHtml;

    let gutter = $('ce-heat-gutter');
    if (!gutter) {
      gutter = document.createElement('div');
      gutter.id = 'ce-heat-gutter';
      const wrap = $('ce-code-wrap');
      wrap.insertBefore(gutter, wrap.firstChild);
    }
    gutter.innerHTML = gutterHtml;

    // Sticky symbol header — update on scroll
    const wrap = $('ce-code-wrap');
    let stickyEl = $('ce-sticky-sym');
    if (!stickyEl) {
      stickyEl = document.createElement('div');
      stickyEl.id = 'ce-sticky-sym';
      stickyEl.innerHTML = '<span class="material-symbols-outlined" style="font-size:13px">code</span><span id="ce-sticky-sym-name"></span>';
      $('ce-code-panel').insertBefore(stickyEl, wrap);
    }
    wrap.onscroll = () => {
      const scrollTop = wrap.scrollTop;
      const lineH = wrap.scrollHeight / (lines.length || 1);
      const curLine = Math.floor(scrollTop / lineH) + 1;
      const curSym = syms.slice().reverse().find(s => s.line_start <= curLine);
      if (curSym) {
        stickyEl.classList.add('visible');
        $('ce-sticky-sym-name').textContent = curSym.name;
      } else {
        stickyEl.classList.remove('visible');
      }
    };
  }

  function _escapeHtml(s) {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function _getCsrfToken() {
    const meta = document.querySelector('meta[name="brahm-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  // ── sidebar rendering ────────────────────────────────────────
  function _renderSidebar() {
    // Tabs
    $('ce-stab-symbols').className = `ce-stab ${state.sidebarTab==='symbols'?'active':''}`;
    $('ce-stab-deps').className = `ce-stab ${state.sidebarTab==='deps'?'active':''}`;

    const container = $('ce-sidebar-content');
    container.innerHTML = '';

    if (state.sidebarTab === 'symbols') {
      _renderSymbolList(container);
    } else {
      _renderDepList(container);
    }
  }

  function _renderSymbolList(container) {
    const d = state.fileData;
    if (!d.symbols || d.symbols.length === 0) {
      container.innerHTML = '<div style="color:#849495;font-size:12px;padding:16px;text-align:center">No symbols detected</div>';
      return;
    }

    d.symbols.forEach((sym, idx) => {
      const card = el('div', `ce-sym${state.activeSymIdx === idx ? ' active' : ''}`);
      card.id = `ce-sym-${idx}`;

      const hc = heatColors[sym.heat] || '#849495';
      const icon = kindIcons[sym.kind] || '▸';

      const usageBadge = (sym.usage_count && sym.usage_count > 0)
        ? `<span class="ce-sym-usage" data-sym="${sym.name}"
                title="Click to see who uses this symbol">
             🔗 ${sym.usage_count}
           </span>`
        : '';

      card.innerHTML = `
        <div class="ce-sym-name">${icon} ${sym.name} ${usageBadge}</div>
        <div class="ce-sym-meta">
          <span class="ce-sym-heat" style="background:${hc};box-shadow:0 0 6px ${hc}66"></span>
          <span class="ce-sym-kind">${sym.kind}</span>
          <span class="ce-sym-lines">L${sym.line_start}–${sym.line_end}</span>
          <span style="color:${hc};font-weight:700">${sym.complexity}</span>
        </div>
        ${sym.docstring ? `<div style="font-size:10px;color:#6b7280;margin-top:4px;font-style:italic;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${sym.docstring}</div>` : ''}
        ${sym.branch_count ? `<div style="font-size:10px;color:#849495;margin-top:3px">⎇ ${sym.branch_count} branches · depth ${sym.nesting_depth}</div>` : ''}
        <div class="ce-sym-usage-list" data-sym="${sym.name}"></div>
      `;

      card.addEventListener('click', (e) => {
        // Clicks on the usage badge should expand inline, not jump to source
        if (e.target.closest('.ce-sym-usage')) {
          e.stopPropagation();
          _toggleSymbolUsageList(card, sym.name);
          return;
        }
        _jumpToSymbol(idx);
      });
      container.appendChild(card);

      // Children (methods inside class)
      if (sym.children && sym.children.length) {
        sym.children.forEach(child => {
          const cc = el('div', 'ce-child-sym');
          const chc = heatColors[child.heat] || '#849495';
          cc.innerHTML = `
            <span style="color:${chc};font-size:10px">▸</span>
            <span class="ce-sym-name">${child.name}</span>
            <span style="font-size:10px;color:#849495;margin-left:auto">L${child.line_start}</span>
          `;
          cc.addEventListener('click', () => _jumpToLine(child.line_start));
          container.appendChild(cc);
        });
      }
    });
  }

  function _renderDepList(container) {
    const d = state.fileData;

    if (d.dependencies && d.dependencies.length) {
      container.appendChild(el('div', 'ce-sec-label', 'Imports (outgoing)'));
      d.dependencies.forEach(dep => {
        const row = el('div', 'ce-dep outgoing');
        row.innerHTML = `<span class="ce-dep-icon material-symbols-outlined" style="font-size:14px">arrow_forward</span><span style="font-size:11px;word-break:break-all">${dep}</span>`;
        row.addEventListener('click', () => _pingNode(dep));
        container.appendChild(row);
      });
    }

    if (d.dependents && d.dependents.length) {
      container.appendChild(el('div', 'ce-sec-label', 'Used by (incoming)'));
      d.dependents.forEach(dep => {
        const row = el('div', 'ce-dep incoming');
        row.innerHTML = `<span class="ce-dep-icon material-symbols-outlined" style="font-size:14px">arrow_back</span><span style="font-size:11px;word-break:break-all">${dep}</span>`;
        row.addEventListener('click', () => _pingNode(dep));
        container.appendChild(row);
      });
    }

    if (!d.dependencies?.length && !d.dependents?.length) {
      container.innerHTML = '<div style="color:#849495;font-size:12px;padding:16px;text-align:center">No dependencies detected</div>';
    }
  }

  // ── blast radius bar ─────────────────────────────────────────
  function _renderBlastBar(d) {
    const all = [...(d.dependencies || []), ...(d.dependents || [])];
    const uniqueFiles = [...new Set(all)];
    const bar = $('ce-blast-bar');
    if (uniqueFiles.length === 0) { bar.classList.remove('visible'); return; }

    $('ce-blast-count').textContent = uniqueFiles.length;
    $('ce-blast-files').textContent =
      uniqueFiles.slice(0, 4).map(f => f.split('/').pop()).join(', ')
      + (uniqueFiles.length > 4 ? ` +${uniqueFiles.length - 4} more` : '');
    bar.classList.add('visible');
  }

  // ── symbol jump ──────────────────────────────────────────────
  function _jumpToSymbol(idx) {
    const d = state.fileData;
    if (!d || !d.symbols[idx]) return;
    const sym = d.symbols[idx];
    state.activeSymIdx = idx;

    // Update sidebar highlight
    document.querySelectorAll('.ce-sym').forEach((el, i) => {
      el.classList.toggle('active', i === idx);
    });

    _jumpToLine(sym.line_start);
    _highlightRange(sym.line_start, sym.line_end);
  }

  function _jumpToLine(lineNum) {
    const ln = $(`ln-${lineNum}`);
    if (ln) {
      ln.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // Flash line number
      const orig = ln.style.color;
      ln.style.color = '#00f2ff';
      ln.style.fontWeight = '700';
      setTimeout(() => { ln.style.color = orig; ln.style.fontWeight = ''; }, 1500);
    }
  }

  function _highlightRange(start, end) {
    // Clear old
    document.querySelectorAll('.ce-hl-range').forEach(e => e.classList.remove('ce-hl-range'));
    // We can't trivially highlight specific lines inside hljs HTML,
    // so highlight the line numbers instead
    for (let i = start; i <= end; i++) {
      const ln = $(`ln-${i}`);
      if (ln) ln.style.color = '#00f2ff';
    }
    // Reset after a delay
    setTimeout(() => {
      for (let i = start; i <= end; i++) {
        const ln = $(`ln-${i}`);
        if (ln) ln.style.color = '';
      }
    }, 2000);
  }

  // ── ping node in 3D graph ────────────────────────────────────
  function _pingNode(path) {
    // If the 3D graph is available, fly to that node
    if (window.GraphEngine && window.GlobalGraphData) {
      const node = window.GlobalGraphData.nodes.find(n => n.id === path);
      if (node) {
        close();
        const dist = 90;
        const r = 1 + dist / Math.hypot(node.x || 0, node.y || 0, node.z || 0);
        window.GraphEngine.cameraPosition(
          { x: (node.x||0) * r, y: (node.y||0) * r, z: (node.z||0) * r },
          node, 1200
        );
      }
    }
  }

  // ── edit mode ────────────────────────────────────────────────
  function toggleEdit() {
    state.editMode = !state.editMode;
    const view = $('ce-code-view');
    const edit = $('ce-code-edit');
    const btn = $('ce-edit-btn');

    if (state.editMode) {
      // Switch to textarea
      view.style.display = 'none';
      edit.style.display = 'block';
      edit.value = state.fileData.source;
      edit.focus();
      btn.className = 'ce-btn ce-btn-danger';
      btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px">close</span> Cancel Edit';
      $('ce-save-btn').style.display = 'flex';
      $('ce-save-status').textContent = 'Edit mode active — changes not yet saved';

      // Live blast radius on change
      edit.addEventListener('input', _onEditChange);
    } else {
      // Cancel — restore original
      view.style.display = 'block';
      edit.style.display = 'none';
      btn.className = 'ce-btn ce-btn-ghost';
      btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px">edit</span> Edit';
      $('ce-save-btn').style.display = 'none';
      $('ce-save-status').textContent = '';
      state.dirty = false;
    }
  }

  function _onEditChange() {
    state.dirty = true;
    $('ce-save-status').textContent = '⚠ Unsaved changes';
    $('ce-save-status').style.color = '#ff8c00';
    // Show blast radius immediately on any edit
    _renderBlastBar(state.fileData);

    // Mark added/modified lines in gutter
    const oldLines = (state.fileData?.source || '').split('\n');
    const newLines = ($('ce-code-edit').value || '').split('\n');
    const lineNums = $('ce-line-nums');
    if (!lineNums) return;
    newLines.forEach((line, i) => {
      const ln = lineNums.children[i];
      if (!ln) return;
      ln.classList.remove('ln-added', 'ln-modified');
      if (i >= oldLines.length) {
        ln.classList.add('ln-added');
      } else if (line !== oldLines[i]) {
        ln.classList.add('ln-modified');
      }
    });
    // Clear removed lines (beyond new length)
    for (let i = newLines.length; i < lineNums.children.length; i++) {
      lineNums.children[i]?.classList.remove('ln-added', 'ln-modified');
    }
  }

  // ── save with unified-diff confirm ───────────────────────────
  function _ensureDiffModal() {
    if ($('ce-diff-modal')) return;
    const m = document.createElement('div');
    m.id = 'ce-diff-modal';
    m.innerHTML = `
      <div id="ce-diff-box">
        <div id="ce-diff-header">
          <span id="ce-diff-title">⚠ Review changes before saving</span>
          <button class="ce-btn ce-btn-ghost" onclick="document.getElementById('ce-diff-modal').classList.remove('open')">✕ Cancel</button>
        </div>
        <div id="ce-diff-content"></div>
        <div id="ce-diff-footer">
          <button class="ce-btn ce-btn-ghost" onclick="document.getElementById('ce-diff-modal').classList.remove('open')">Cancel</button>
          <button class="ce-btn ce-btn-success" id="ce-diff-confirm">✓ Confirm &amp; Save</button>
        </div>
      </div>`;
    document.body.appendChild(m);
  }

  function _buildDiff(oldSrc, newSrc) {
    const oldLines = oldSrc.split('\n');
    const newLines = newSrc.split('\n');
    const out = [];
    const maxCtx = 3;
    let i = 0, j = 0;
    // Simple line-by-line diff (LCS not needed for a display-only confirm)
    const n = Math.max(oldLines.length, newLines.length);
    const changes = [];
    for (let k = 0; k < n; k++) {
      const o = oldLines[k], nw = newLines[k];
      if (o === nw)       changes.push({ type: 'ctx', text: o ?? '' });
      else if (o === undefined) changes.push({ type: 'add', text: nw });
      else if (nw === undefined) changes.push({ type: 'remove', text: o });
      else { changes.push({ type: 'remove', text: o }); changes.push({ type: 'add', text: nw }); }
    }
    return changes.map(c => {
      const prefix = c.type === 'add' ? '+' : c.type === 'remove' ? '-' : ' ';
      const cls    = c.type === 'add' ? 'add' : c.type === 'remove' ? 'remove' : 'ctx';
      const esc    = c.text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      return `<div class="diff-line ${cls}">${prefix} ${esc}</div>`;
    }).join('');
  }

  function saveFile() {
    if (!state.fileData) return;
    const newSource = $('ce-code-edit').value;
    if (newSource === state.fileData.source) {
      $('ce-save-status').textContent = 'No changes to save.';
      return;
    }
    _ensureDiffModal();
    $('ce-diff-content').innerHTML = _buildDiff(state.fileData.source, newSource);
    $('ce-diff-modal').classList.add('open');
    $('ce-diff-confirm').onclick = () => {
      $('ce-diff-modal').classList.remove('open');
      _commitSave(newSource);
    };
  }

  function _commitSave(newSource) {
    $('ce-save-status').textContent = 'Saving…';
    $('ce-save-status').style.color = '#849495';
    fetch('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Brahm-Token': _getCsrfToken() },
      body: JSON.stringify({ path: state.fileData.path, source: newSource })
    })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        state.fileData.source = newSource;
        state.dirty = false;
        _renderCode(newSource, state.fileData.language);
        toggleEdit();
        $('ce-save-status').textContent = '✓ Saved';
        $('ce-save-status').style.color = '#00ff66';
        setTimeout(() => { $('ce-save-status').textContent = ''; }, 3000);
      } else {
        $('ce-save-status').textContent = `✗ ${res.error}`;
        $('ce-save-status').style.color = '#ff0055';
      }
    })
    .catch(err => {
      $('ce-save-status').textContent = `✗ Error: ${err}`;
      $('ce-save-status').style.color = '#ff0055';
    });
  }

  function switchSidebarTab(tab) {
    state.sidebarTab = tab;
    _renderSidebar();
  }

  // ── public API ───────────────────────────────────────────────
  return { open, close, toggleEdit, saveFile, switchSidebarTab };
})();

// Keyboard shortcut: Escape closes explorer
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') CE.close();
  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
    e.preventDefault();
    CE.saveFile();
  }
});
