// ===================================================================
// API helper
// ===================================================================
const API = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },
  async post(path, body) {
    const res = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: body ? JSON.stringify(body) : undefined,
    });
    return res.json();
  },
};

// ===================================================================
// Utility
// ===================================================================
const h = s => {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
};

function highlightMatch(text, query) {
  if (!query || !text) return h(text || '');
  const escaped = h(text);
  const escapedQ = h(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return escaped.replace(new RegExp('(' + escapedQ + ')', 'gi'), '<mark class="search-hit">$1</mark>');
}

function toast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast toast-' + (type || 'success');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// ===================================================================
// Mermaid — CDN loader with offline fallback
// ===================================================================
let mermaidReady = false;
let mermaidAPI = null;

function renderMermaidInElement(containerEl, prefixId) {
  if (!mermaidReady || !mermaidAPI || !containerEl) return;
  
  // Match standard markdown code blocks as well as explicit div/pre classes
  const blocks = containerEl.querySelectorAll('code.language-mermaid, code.mermaid, pre.mermaid, div.mermaid');
  blocks.forEach((block, idx) => {
    if (block.dataset.mermaidProcessed) return;
    block.dataset.mermaidProcessed = 'true';
    
    const id = 'mermaid-' + prefixId + '-' + idx + '-' + Date.now();
    const graphDef = block.textContent.trim();
    const target = (block.tagName === 'CODE' && block.parentElement && block.parentElement.tagName === 'PRE') ? block.parentElement : block;
    
    mermaidAPI.render(id, graphDef).then(({ svg }) => {
      const div = document.createElement('div');
      div.className = 'mermaid-diagram';
      div.style.textAlign = 'center';
      div.style.margin = '16px 0';
      div.innerHTML = svg;
      target.replaceWith(div);
    }).catch(err => {
      console.error('Mermaid render error:', err);
    });
  });
}

function renderMermaidInPanel(pid) {
  const ptv = document.getElementById('ptv-' + pid);
  renderMermaidInElement(ptv, 'panel-' + pid);
}

function renderAllMermaid() {
  if (typeof activePanels !== 'undefined') {
    activePanels.forEach(ps => renderMermaidInPanel(ps.id));
  }
  const docView = document.querySelector('.document-view');
  if (docView) {
    renderMermaidInElement(docView, 'doc');
  }
}

(async () => {
  const timeout = (ms) => new Promise((_, r) => setTimeout(() => r(new Error('timeout')), ms));
  try {
    const mod = await Promise.race([
      import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs'),
      timeout(5000),
    ]);
    mermaidAPI = mod.default;
    mermaidAPI.initialize({ startOnLoad: false, theme: 'default' });
    mermaidReady = true;
    console.log('Mermaid loaded (online mode)');
    // Render any panels that might have been opened before loading finished
    setTimeout(renderAllMermaid, 50);
  } catch (e) {
    console.warn('Mermaid unavailable (offline mode):', e.message);
  }
})();

// ===================================================================
// D3.js — CDN loader for tree graph view
// ===================================================================
let d3Ready = false;
let d3 = null;
(async () => {
  const timeout = (ms) => new Promise((_, r) => setTimeout(() => r(new Error('timeout')), ms));
  try {
    const mod = await Promise.race([
      import('https://cdn.jsdelivr.net/npm/d3@7/+esm'),
      timeout(8000),
    ]);
    d3 = mod;
    d3Ready = true;
    console.log('D3.js loaded (online mode)');
  } catch (e) {
    console.warn('D3.js unavailable (offline mode):', e.message);
  }
})();

// ===================================================================
// Rich Editor (TipTap) — CDN loader with offline fallback
// ===================================================================
let richEditorReady = false;
let RichEditor = {};
(async () => {
  const timeout = (ms) => new Promise((_, r) => setTimeout(() => r(new Error('timeout')), ms));
  try {
    const [coreMod, skMod, tdMod, tblMod, tblRowMod, tblHdrMod, tblCellMod, gfmMod] = await Promise.race([
      Promise.all([
        import('https://esm.sh/@tiptap/core@2'),
        import('https://esm.sh/@tiptap/starter-kit@2'),
        import('https://esm.sh/turndown@7'),
        import('https://esm.sh/@tiptap/extension-table@2'),
        import('https://esm.sh/@tiptap/extension-table-row@2'),
        import('https://esm.sh/@tiptap/extension-table-header@2'),
        import('https://esm.sh/@tiptap/extension-table-cell@2'),
        import('https://esm.sh/turndown-plugin-gfm@1.0.2'),
      ]),
      timeout(5000),
    ]);
    RichEditor = {
      Editor: coreMod.Editor,
      Extension: coreMod.Extension,
      StarterKit: skMod.StarterKit || skMod.default,
      TurndownService: tdMod.default || tdMod,
      Table: tblMod.Table || tblMod.default,
      TableRow: tblRowMod.TableRow || tblRowMod.default,
      TableHeader: tblHdrMod.TableHeader || tblHdrMod.default,
      TableCell: tblCellMod.TableCell || tblCellMod.default,
      gfmTables: gfmMod.tables || (gfmMod.default && gfmMod.default.tables),
    };
    richEditorReady = true;
    console.log('Rich editor loaded (online mode)');
  } catch (e) {
    console.warn('Rich editor unavailable (offline mode):', e.message);
  }
})();

async function forceReload() {
  const btn = document.getElementById('reload-btn');
  btn.disabled = true;
  btn.querySelector('span:last-child').textContent = 'Reloading...';
  try {
    await API.post('/api/reload');
    toast('Reloaded from disk');
    refreshCurrentView();
    refreshOtherPanels(null);
  } catch (e) {
    toast('Reload failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.querySelector('span:last-child').textContent = 'Reload';
  }
}

function coverageColor(pct) {
  if (pct === 100) return 'var(--success)';
  if (pct >= 50) return 'var(--warning)';
  return 'var(--error)';
}

function statusIcons(reviewed, suspect) {
  let s = '';
  if (suspect) s += '<span class="cell-status status-suspect">&#x26A0;</span>';
  if (reviewed) s += '<span class="cell-status status-reviewed">&#x2713;</span>';
  else s += '<span class="cell-status status-unreviewed">&#x25CB;</span>';
  return s;
}

function statusTags(reviewed, suspect, normative=true) {
  let s = '';
  if (!normative) s += '<span class="tag tag-non-normative">Non-normative</span> ';
  if (suspect) s += '<span class="tag tag-suspect">Suspect</span> ';
  if (reviewed) s += '<span class="tag tag-reviewed">Reviewed</span>';
  else s += '<span class="tag tag-unreviewed">Unreviewed</span>';
  return s;
}

// ===================================================================
// Router
// ===================================================================
let currentView = '';
let currentParam = '';

function route() {
  const hash = (location.hash || '#/').slice(1);
  const parts = hash.split('/').filter(Boolean);
  const view = parts[0] || 'dashboard';
  const param = parts.slice(1).join('/');

  // Only re-render if view changed (not for item panel opens)
  if (view === 'item') {
    openItemPanel(param);
    return;
  }

  currentView = view;
  currentParam = param;

  // Update sidebar active state
  document.querySelectorAll('#sidebar a').forEach(a => a.classList.remove('active'));
  const navKey = (view === 'group' || view === 'document') ? null : view === 'dashboard' ? 'dashboard' : view;
  if (navKey) {
    const el = document.querySelector(`[data-nav="${navKey}"]`);
    if (el) el.classList.add('active');
  }
  if (view === 'group') {
    document.querySelectorAll('#group-nav-list a').forEach(a => {
      a.classList.toggle('active', a.dataset.group === decodeURIComponent(param));
    });
  } else if (view === 'document') {
    document.querySelectorAll('#doc-nav-list a').forEach(a => {
      a.classList.toggle('active', a.dataset.doc === decodeURIComponent(param));
    });
  }

  closeItemPanel();

  switch (view) {
    case 'dashboard': renderDashboard(); break;
    case 'matrix': renderMatrix(); break;
    case 'group': renderGroup(decodeURIComponent(param)); break;
    case 'document': renderDocument(decodeURIComponent(param)); break;
    case 'tree': renderTreeGraph(decodeURIComponent(param)); break;
    case 'validation': renderValidation(); break;
    default: renderDashboard();
  }
}

window.addEventListener('hashchange', route);

// ===================================================================
// Sidebar group list
// ===================================================================
async function loadGroupNav() {
  const [groups, overview] = await Promise.all([
    API.get('/api/groups'),
    API.get('/api/overview'),
  ]);

  // Status summary at top of sidebar (clickable → matrix with filter)
  const totalUnreviewed = overview.review.total - overview.review.reviewed;
  const totalSuspects = overview.suspects;
  const statusEl = document.getElementById('nav-status-summary');
  if (totalUnreviewed > 0 || totalSuspects > 0) {
    let rows = '';
    if (totalUnreviewed > 0)
      rows += `<div class="nav-status-row nav-status-link" onclick="navigateToMatrixFiltered('unreviewed')"><span class="nav-status-dot unreviewed"></span> Unreviewed <span class="nav-status-count">${totalUnreviewed}</span></div>`;
    if (totalSuspects > 0)
      rows += `<div class="nav-status-row nav-status-link" onclick="navigateToMatrixFiltered('suspect')"><span class="nav-status-dot suspect"></span> Suspect <span class="nav-status-count">${totalSuspects}</span></div>`;
    statusEl.innerHTML = rows;
    statusEl.style.display = '';
  } else {
    statusEl.innerHTML = '<div class="nav-status-row nav-status-link" onclick="location.hash=\'#/matrix\'"><span class="nav-status-dot ok"></span> All clear</div>';
    statusEl.style.display = '';
  }

  // Document nav
  const docList = document.getElementById('doc-nav-list');
  if (docList) {
    docList.innerHTML = Object.keys(overview.documents).map(prefix => {
      return `<li><a href="#/document/${encodeURIComponent(prefix)}" data-doc="${h(prefix)}">${h(prefix)} <span class="group-badge">${overview.documents[prefix]}</span></a></li>`;
    }).join('');
  }

  // Group nav with unreviewed/suspect badges
  const list = document.getElementById('group-nav-list');
  list.innerHTML = Object.entries(groups).map(([name, info]) => {
    const unreviewed = info.items - info.reviewed;
    let badges = ``;
    if (unreviewed > 0)
      badges += `<span class="nav-badge-unreviewed" title="Unreviewed">${unreviewed}</span>`;
    if (info.suspect > 0)
      badges += `<span class="nav-badge-suspect" title="Suspect">${info.suspect}</span><span class="nav-badge-slash">/</span>`;
    badges += `<span class="group-badge">${info.items}</span>`;
    return `<li><a href="#/group/${encodeURIComponent(name)}" data-group="${h(name)}">${h(name)} ${badges}</a></li>`;
  }).join('');
}

// ===================================================================
// Views
// ===================================================================
const $main = () => document.getElementById('main');

// --- Dashboard ---
async function renderDashboard() {
  $main().innerHTML = '<div class="loading">Loading...</div>';
  const data = await API.get('/api/overview');
  const rv = data.review;
  const vs = data.validation_summary;

  let coverageHtml = '';
  for (const [pair, cov] of Object.entries(data.coverage)) {
    const color = coverageColor(cov.percentage);
    coverageHtml += `<tr>
      <td><strong>${h(pair)}</strong></td>
      <td>${cov.covered} / ${cov.total}</td>
      <td><span class="coverage-bar"><span class="coverage-fill" style="width:${cov.percentage}%;background:${color}"></span></span> <strong style="color:${color}">${cov.percentage}%</strong></td>
      <td style="font-size:0.85em;color:var(--text-secondary)">${cov.uncovered_items.length ? h(cov.uncovered_items.join(', ')) : '&#8212;'}</td>
    </tr>`;
    if (cov.by_group) {
      for (const [g, gd] of Object.entries(cov.by_group)) {
        const gc = coverageColor(gd.percentage);
        coverageHtml += `<tr style="font-size:0.88em">
          <td style="padding-left:28px">${h(pair)}</td>
          <td><span class="tag tag-group">${h(g)}</span> ${gd.covered}/${gd.total}</td>
          <td><span class="coverage-bar"><span class="coverage-fill" style="width:${gd.percentage}%;background:${gc}"></span></span> <span style="color:${gc}">${gd.percentage}%</span></td>
          <td style="font-size:0.85em;color:var(--text-secondary)">${gd.uncovered_items.length ? h(gd.uncovered_items.join(', ')) : '&#8212;'}</td>
        </tr>`;
      }
    }
  }

  let docsHtml = Object.entries(data.documents).map(([prefix, count]) =>
    `<div class="card"><div class="card-label">${h(prefix)}</div><div class="card-value">${count}</div></div>`
  ).join('');

  $main().innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
      <div class="page-title" style="margin-bottom:0;">Dashboard</div>
      <button id="btn-generate-report" class="btn" style="padding:6px 16px;">Generate HTML Report</button>
    </div>
    <div class="page-subtitle">Doorstop Traceability Overview</div>
    <div class="cards">
      ${docsHtml}
      <div class="card"><div class="card-label">Reviewed</div><div class="card-value ${rv.reviewed===rv.total?'success':''}">${rv.reviewed}/${rv.total}</div></div>
      <div class="card"><div class="card-label">Suspects</div><div class="card-value ${data.suspects?'suspect':'success'}">${data.suspects}</div></div>
      <div class="card"><div class="card-label">Errors</div><div class="card-value ${vs.errors?'error':'success'}">${vs.errors}</div></div>
      <div class="card"><div class="card-label">Warnings</div><div class="card-value ${vs.warnings?'warning':'success'}">${vs.warnings}</div></div>
    </div>

    <div class="section-title">Groups</div>
    <div class="cards" id="dash-groups"></div>

    <div class="section-title">Coverage</div>
    <table>
      <tr><th>Link Direction</th><th>Coverage</th><th>Rate</th><th>Uncovered</th></tr>
      ${coverageHtml}
    </table>
  `;

  // Group cards
  const groups = await API.get('/api/groups');
  document.getElementById('dash-groups').innerHTML = Object.entries(groups).map(([name, info]) => {
    const pct = info.items ? Math.round(info.reviewed / info.items * 100) : 0;
    return `<div class="card" style="cursor:pointer;min-width:150px" onclick="location.hash='#/group/${encodeURIComponent(name)}'">
      <div class="card-label"><span class="tag tag-group">${h(name)}</span></div>
      <div style="font-size:0.85em;margin-top:6px">${info.items} items, ${info.reviewed} reviewed${info.suspect ? ', <span style="color:var(--suspect)">' + info.suspect + ' suspect</span>' : ''}</div>
      <div style="margin-top:4px"><span class="coverage-bar" style="width:80px"><span class="coverage-fill" style="width:${pct}%;background:${coverageColor(pct)}"></span></span> ${pct}%</div>
    </div>`;
  }).join('');

  document.getElementById('btn-generate-report').addEventListener('click', async (e) => {
    const btn = e.target;
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = 'Generating...';
    try {
      const res = await API.post('/api/generate_report', {});
      if (!res.ok) throw new Error(res.error || 'Unknown error');
      if (res.report_url) {
          window.open(res.report_url, '_blank');
      } else {
          alert('Report generated successfully.');
      }
    } catch (err) {
      alert('Failed to generate report: ' + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
}

// --- Matrix ---
let matrixData = null;
let matrixFilters = { groups: new Set(), statuses: new Set(), authors: new Set(), query: '', sortCol: -1, sortDir: 'asc' };
let _pendingMatrixFilter = null;

function naturalCompare(a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

function navigateToMatrixFiltered(status) {
  _pendingMatrixFilter = status;
  if (location.hash === '#/matrix') {
    // Already on matrix — hashchange won't fire, so render directly
    renderMatrix();
  } else {
    location.hash = '#/matrix';
  }
}

async function renderMatrix() {
  $main().innerHTML = '<div class="loading">Loading...</div>';
  matrixData = await API.get('/api/matrix');
  if (_pendingMatrixFilter) {
    matrixFilters = { groups: new Set(), statuses: new Set([_pendingMatrixFilter]), authors: new Set(), query: '', sortCol: -1, sortDir: 'asc' };
    _pendingMatrixFilter = null;
  } else {
    matrixFilters = { groups: new Set(), statuses: new Set(), authors: new Set(), query: '', sortCol: -1, sortDir: 'asc' };
  }
  renderMatrixView();
}

// Full render: filter bar + table container + event listeners
function renderMatrixView() {
  if (!matrixData) return;
  const { rows } = matrixData;

  const allGroups = [...new Set(rows.flatMap(r => r.groups))].sort();
  const groupPills = allGroups.map(g =>
    `<span class="pill ${matrixFilters.groups.has(g)?'active':''}" onclick="toggleMatrixGroup('${h(g)}')">${h(g)}</span>`
  ).join('');

  const statusPills = ['reviewed','unreviewed','suspect'].map(s =>
    `<span class="pill ${matrixFilters.statuses.has(s)?'active':''}" onclick="toggleMatrixStatus('${s}')">${s==='reviewed'?'&#x2713; Reviewed':s==='unreviewed'?'&#x25CB; Unreviewed':'&#x26A0; Suspect'}</span>`
  ).join('');

  // Collect unique authors from all cells
  const allAuthors = [...new Set(
    rows.flatMap(r => Object.values(r.cells).filter(Boolean).map(c => c.author).filter(Boolean))
  )].sort();
  const authorPills = allAuthors.map(a =>
    `<span class="pill ${matrixFilters.authors.has(a)?'active':''}" onclick="toggleMatrixAuthor('${h(a)}')">${h(a)}</span>`
  ).join('');

  $main().innerHTML = `
    <div class="page-title">Traceability Matrix</div>
    <div class="page-subtitle">&#x2713;=Reviewed  &#x25CB;=Unreviewed  &#x26A0;=Suspect &mdash; Click UID for detail</div>

    <div class="filter-bar" id="matrix-group-bar">
      <label>Group:</label>
      <span class="pill ${matrixFilters.groups.size===0?'active':''}" onclick="clearMatrixGroups()">All</span>
      ${groupPills}
    </div>
    <div class="filter-bar" id="matrix-status-bar">
      <label>Status:</label>
      ${statusPills}
      <label style="margin-left:12px">Search:</label>
      <input class="search-input" id="matrix-search" type="text" placeholder="UID / header / text / ref / author / date" value="${h(matrixFilters.query)}">
    </div>
    ${allAuthors.length > 1 ? `<div class="filter-bar" id="matrix-author-bar">
      <label>Author:</label>
      <span class="pill ${matrixFilters.authors.size===0?'active':''}" onclick="clearMatrixAuthors()">All</span>
      ${authorPills}
    </div>` : ''}

    <div id="matrix-table-wrap"></div>
  `;

  // IME-safe event listeners — input element is never destroyed during typing
  const searchInput = document.getElementById('matrix-search');
  searchInput.addEventListener('input', (e) => {
    if (!e.isComposing) {
      matrixFilters.query = searchInput.value;
      renderMatrixTable();
    }
  });
  searchInput.addEventListener('compositionend', () => {
    matrixFilters.query = searchInput.value;
    renderMatrixTable();
  });

  renderMatrixTable();
}

// Partial render: only the table inside #matrix-table-wrap
function renderMatrixTable() {
  if (!matrixData) return;
  const { prefixes, rows } = matrixData;
  const wrap = document.getElementById('matrix-table-wrap');
  if (!wrap) return;

  const sortArrowHtml = (colIdx) => {
    const active = matrixFilters.sortCol === colIdx;
    return `<th class="sortable ${active?'sort-active':''}" onclick="toggleMatrixSort(${colIdx})">`;
  };
  let headerCells = `${sortArrowHtml(0)}Group<span class="sort-arrow">${matrixFilters.sortCol===0?(matrixFilters.sortDir==='asc'?'&#x25B2;':'&#x25BC;'):'&#x25B2;&#x25BC;'}</span></th>`;
  prefixes.forEach((p, i) => {
    const ci = i + 1;
    const active = matrixFilters.sortCol === ci;
    const arrowText = active ? (matrixFilters.sortDir==='asc'?'&#x25B2;':'&#x25BC;') : '&#x25B2;&#x25BC;';
    headerCells += `${sortArrowHtml(ci)}${h(p)}<span class="sort-arrow">${arrowText}</span></th>`;
  });

  // Filter rows
  let filtered = rows.filter(row => {
    if (matrixFilters.groups.size > 0 && !row.groups.some(g => matrixFilters.groups.has(g))) return false;
    if (matrixFilters.statuses.size > 0 && !row.statuses.some(s => matrixFilters.statuses.has(s))) return false;
    if (matrixFilters.authors.size > 0) {
      const matchesAuthor = Object.values(row.cells).some(cell =>
        cell && cell.author && matrixFilters.authors.has(cell.author)
      );
      if (!matchesAuthor) return false;
    }
    if (matrixFilters.query) {
      const q = matrixFilters.query.toLowerCase();
      const matchesAnyCell = Object.values(row.cells).some(cell => {
        if (!cell) return false;
        if (cell.uid.toLowerCase().includes(q)) return true;
        if (cell.header && cell.header.toLowerCase().includes(q)) return true;
        if (cell.text_preview && cell.text_preview.toLowerCase().includes(q)) return true;
        if (cell.ref && cell.ref.toLowerCase().includes(q)) return true;
        if (cell.references && cell.references.some(r => r.path && r.path.toLowerCase().includes(q))) return true;
        if (cell.author && cell.author.toLowerCase().includes(q)) return true;
        if (cell.created_at && cell.created_at.includes(q)) return true;
        if (cell.updated_at && cell.updated_at.includes(q)) return true;
        return false;
      });
      if (!matchesAnyCell) return false;
    }
    return true;
  });

  // Sort rows
  if (matrixFilters.sortCol >= 0) {
    const col = matrixFilters.sortCol;
    filtered.sort((a, b) => {
      let aKey, bKey;
      if (col === 0) {
        aKey = a.groups ? a.groups[0] : '';
        bKey = b.groups ? b.groups[0] : '';
      } else {
        const prefix = prefixes[col - 1];
        aKey = a.cells[prefix]?.uid || '';
        bKey = b.cells[prefix]?.uid || '';
      }
      const cmp = naturalCompare(aKey, bKey);
      return matrixFilters.sortDir === 'asc' ? cmp : -cmp;
    });
  }

  const q = matrixFilters.query;
  const hl = q ? ((text) => highlightMatch(text, q)) : h;

  let bodyRows = '';
  for (const row of filtered) {
    const groupTags = (row.groups || []).map(g => `<span class="tag tag-group">${h(g)}</span>`).join(' ');
    let cells = `<td>${groupTags}</td>`;
    for (const prefix of prefixes) {
      const cell = row.cells[prefix];
      if (cell) {
        const cellCls = cell.suspect ? 'cell-suspect' : (!cell.reviewed ? 'cell-unreviewed' : '');
        const refHtml = cell.ref ? `<br><span class="tag tag-ref">${hl(cell.ref)}</span>` : '';
        const headerHtml = cell.header ? `<span class="cell-header">${hl(cell.header)}</span>` : '';
        const textHtml = cell.text_preview ? `<span class="text-preview">${hl(cell.text_preview)}</span>` : '';
        cells += `<td class="${cellCls}" data-uid="${cell.uid}">
          <span class="cell-uid" onclick="handleCellClick(event,'${cell.uid}')">${hl(cell.uid)}</span>
          ${statusIcons(cell.reviewed, cell.suspect)}
          ${headerHtml}
          ${textHtml}
          ${refHtml}
        </td>`;
      } else {
        cells += '<td class="empty">&#8212;</td>';
      }
    }
    bodyRows += `<tr>${cells}</tr>`;
  }

  wrap.innerHTML = `
    <table>
      <tr>${headerCells}</tr>
      ${bodyRows || '<tr><td colspan="'+(prefixes.length+1)+'" class="empty">No matching items</td></tr>'}
    </table>
  `;
}

// Update only the pill active states without touching the search input
function updateMatrixPills() {
  if (!matrixData) return;
  const { rows } = matrixData;
  const allGroups = [...new Set(rows.flatMap(r => r.groups))].sort();

  const groupBar = document.getElementById('matrix-group-bar');
  if (groupBar) {
    groupBar.innerHTML = `
      <label>Group:</label>
      <span class="pill ${matrixFilters.groups.size===0?'active':''}" onclick="clearMatrixGroups()">All</span>
      ${allGroups.map(g =>
        `<span class="pill ${matrixFilters.groups.has(g)?'active':''}" onclick="toggleMatrixGroup('${h(g)}')">${h(g)}</span>`
      ).join('')}
    `;
  }

  const statusBar = document.getElementById('matrix-status-bar');
  if (statusBar) {
    const searchInput = document.getElementById('matrix-search');
    const hadFocus = document.activeElement === searchInput;
    const cursorPos = hadFocus && searchInput ? searchInput.selectionStart : 0;

    statusBar.innerHTML = `
      <label>Status:</label>
      ${ ['reviewed','unreviewed','suspect'].map(s =>
        `<span class="pill ${matrixFilters.statuses.has(s)?'active':''}" onclick="toggleMatrixStatus('${s}')">${s==='reviewed'?'&#x2713; Reviewed':s==='unreviewed'?'&#x25CB; Unreviewed':'&#x26A0; Suspect'}</span>`
      ).join('')}
      <label style="margin-left:12px">Search:</label>
      <input class="search-input" id="matrix-search" type="text" placeholder="UID / header / text / ref / author / date" value="${h(matrixFilters.query)}">
    `;

    // Re-attach search listeners
    const newInput = document.getElementById('matrix-search');
    newInput.addEventListener('input', (e) => {
      if (!e.isComposing) {
        matrixFilters.query = newInput.value;
        renderMatrixTable();
      }
    });
    newInput.addEventListener('compositionend', () => {
      matrixFilters.query = newInput.value;
      renderMatrixTable();
    });
    if (hadFocus) {
      newInput.focus();
      newInput.setSelectionRange(cursorPos, cursorPos);
    }
  }

  const authorBar = document.getElementById('matrix-author-bar');
  if (authorBar) {
    const allAuthors = [...new Set(
      rows.flatMap(r => Object.values(r.cells).filter(Boolean).map(c => c.author).filter(Boolean))
    )].sort();
    authorBar.innerHTML = `
      <label>Author:</label>
      <span class="pill ${matrixFilters.authors.size===0?'active':''}" onclick="clearMatrixAuthors()">All</span>
      ${allAuthors.map(a =>
        `<span class="pill ${matrixFilters.authors.has(a)?'active':''}" onclick="toggleMatrixAuthor('${h(a)}')">${h(a)}</span>`
      ).join('')}
    `;
  }
}

function toggleMatrixGroup(g) {
  if (matrixFilters.groups.has(g)) matrixFilters.groups.delete(g);
  else matrixFilters.groups.add(g);
  updateMatrixPills();
  renderMatrixTable();
}
function clearMatrixGroups() {
  matrixFilters.groups.clear();
  updateMatrixPills();
  renderMatrixTable();
}
function toggleMatrixAuthor(a) {
  if (matrixFilters.authors.has(a)) matrixFilters.authors.delete(a);
  else matrixFilters.authors.add(a);
  updateMatrixPills();
  renderMatrixTable();
}
function clearMatrixAuthors() {
  matrixFilters.authors.clear();
  updateMatrixPills();
  renderMatrixTable();
}
function toggleMatrixStatus(s) {
  if (matrixFilters.statuses.has(s)) matrixFilters.statuses.delete(s);
  else matrixFilters.statuses.add(s);
  updateMatrixPills();
  renderMatrixTable();
}
function toggleMatrixSort(colIdx) {
  if (matrixFilters.sortCol === colIdx) {
    matrixFilters.sortDir = matrixFilters.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    matrixFilters.sortCol = colIdx;
    matrixFilters.sortDir = 'asc';
  }
  renderMatrixTable();
}

// --- Group Detail ---
async function renderGroup(name) {
  $main().innerHTML = '<div class="loading">Loading...</div>';
  let data;
  try {
    data = await API.get('/api/group/' + encodeURIComponent(name));
  } catch {
    $main().innerHTML = `<div class="empty-state">Group "${h(name)}" not found.</div>`;
    return;
  }

  const items = data.items;
  const reviewed = items.filter(i => i.reviewed).length;
  const suspects = items.filter(i => i.suspect).length;

  // Coverage table
  let covHtml = '';
  for (const [pair, cov] of Object.entries(data.coverage)) {
    const color = coverageColor(cov.percentage);
    covHtml += `<tr>
      <td>${h(pair)}</td>
      <td>${cov.covered}/${cov.total}</td>
      <td><span class="coverage-bar"><span class="coverage-fill" style="width:${cov.percentage}%;background:${color}"></span></span> <strong style="color:${color}">${cov.percentage}%</strong></td>
      <td style="font-size:0.85em">${cov.uncovered_items.length ? h(cov.uncovered_items.join(', ')) : '&#8212;'}</td>
    </tr>`;
  }

  // Matrix
  const mat = data.matrix;
  let matHeader = '<th>Group</th>' + mat.prefixes.map(p => `<th>${h(p)}</th>`).join('');
  let matBody = '';
  for (const row of mat.rows) {
    const groupTags = (row.groups || []).map(g => `<span class="tag tag-group">${h(g)}</span>`).join(' ');
    let cells = `<td>${groupTags}</td>`;
    for (const prefix of mat.prefixes) {
      const cell = row.cells[prefix];
      if (cell) {
        const cellCls = cell.suspect ? 'cell-suspect' : (!cell.reviewed ? 'cell-unreviewed' : '');
        cells += `<td class="${cellCls}" data-uid="${cell.uid}">
          <span class="cell-uid" onclick="handleCellClick(event,'${cell.uid}')">${h(cell.uid)}</span>
          ${statusIcons(cell.reviewed, cell.suspect)}
          <span class="text-preview">${h(cell.text_preview)}</span>
        </td>`;
      } else {
        cells += '<td class="empty">&#8212;</td>';
      }
    }
    matBody += `<tr>${cells}</tr>`;
  }

  // Item list
  let itemsHtml = '';
  const byPrefix = {};
  for (const item of items) {
    (byPrefix[item.prefix] = byPrefix[item.prefix] || []).push(item);
  }
  for (const [prefix, pitems] of Object.entries(byPrefix)) {
    itemsHtml += `<div class="section-title"><span class="tag tag-prefix">${h(prefix)}</span> (${pitems.length})</div>`;
    for (const item of pitems) {
      itemsHtml += `<div style="padding:8px 0;border-bottom:1px solid #f1f3f4;display:flex;align-items:center;gap:8px">
        <span class="cell-uid" onclick="handleCellClick(event,'${item.uid}')" style="min-width:70px">${h(item.uid)}</span>
        ${statusTags(item.reviewed, item.suspect, item.normative)}
        <span class="text-preview" style="flex:1">${h(item.text_preview)}</span>
        ${item.ref ? '<span class="tag tag-ref">'+h(item.ref)+'</span>' : ''}
      </div>`;
    }
  }

  $main().innerHTML = `
    <div class="page-title">Group: ${h(name)}</div>
    <div class="page-subtitle">${items.length} items in chain</div>

    <div class="cards">
      <div class="card"><div class="card-label">Items</div><div class="card-value">${items.length}</div></div>
      <div class="card"><div class="card-label">Reviewed</div><div class="card-value ${reviewed===items.length?'success':''}">${reviewed}/${items.length}</div></div>
      <div class="card"><div class="card-label">Suspects</div><div class="card-value ${suspects?'suspect':'success'}">${suspects}</div></div>
    </div>

    <div class="section-title">Coverage (Local)</div>
    <table>
      <tr><th>Link Direction</th><th>Coverage</th><th>Rate</th><th>Uncovered</th></tr>
      ${covHtml || '<tr><td colspan="4" class="empty">No coverage data</td></tr>'}
    </table>

    <div class="section-title">Traceability Matrix</div>
    <table>
      <tr>${matHeader}</tr>
      ${matBody || '<tr><td colspan="'+(mat.prefixes.length+1)+'" class="empty">No items</td></tr>'}
    </table>

    <div class="section-title">Items</div>
    ${itemsHtml || '<div class="empty-state">No items</div>'}
  `;
}

// --- Document View ---
let docEditMode = false;

async function docReorder(uid, action, prefix) {
  try {
    const res = await API.post('/api/items/' + encodeURIComponent(uid) + '/reorder', { action });
    if (res.ok) {
      renderDocument(prefix);
    } else {
      alert("Error: " + res.error);
    }
  } catch (e) {
    alert("Reorder failed.");
  }
}

async function docInsert(uid, prefix) {
  try {
    const res = await API.post('/api/items/' + encodeURIComponent(uid) + '/insert', {});
    if (res.ok) {
      renderDocument(prefix);
    } else {
      alert("Error: " + res.error);
    }
  } catch (e) {
    alert("Insert failed.");
  }
}

async function docDelete(uid, prefix) {
  if (!confirm(`本当にアイテム ${uid} を削除しますか？\n（親アイテムの場合、子アイテムの整合性に影響する可能性があります）`)) return;
  try {
    const res = await API.post('/api/items/' + encodeURIComponent(uid) + '/delete', {});
    if (res.ok) {
      renderDocument(prefix);
    } else {
      alert("Error: " + res.error);
    }
  } catch (e) {
    alert("Delete failed.");
  }
}

function toggleDocEditMode(prefix) {
  docEditMode = !docEditMode;
  renderDocument(prefix);
}

async function renderDocument(prefix) {
  if (!document.getElementById('doc-view-container')) {
    $main().innerHTML = '<div class="loading">Loading...</div>';
  }
  let data;
  try {
    data = await API.get('/api/document/' + encodeURIComponent(prefix));
  } catch {
    $main().innerHTML = `<div class="empty-state">Document "${h(prefix)}" not found.</div>`;
    return;
  }

  const items = data.items;
  let docHtml = '';
  let mapHtml = '';

  for (const item of items) {
    const isHeading = !item.normative && item.level.endsWith('.0');
    const levelDepth = item.level.split('.').length;
    
    // Map entry
    const mapIndent = (levelDepth - 1) * 12;
    mapHtml += `
      <div class="doc-map-item" style="padding-left: ${mapIndent}px; display:flex; align-items:center; justify-content:space-between; margin-bottom: 4px; font-size: 0.9em;">
        <a href="javascript:void(0)" onclick="document.getElementById('doc-item-${item.uid}')?.scrollIntoView({behavior:'smooth'}); return false;" style="text-decoration:none; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1;" title="${h(item.header || item.uid)}">
          <span style="color:var(--text-secondary); margin-right:4px;">${h(item.level)}</span>
          ${h(item.header || item.uid)}
        </a>
        ${docEditMode ? `
        <div class="doc-map-actions" style="display:flex; gap:2px; margin-left:8px;">
          <button onclick="docReorder('${item.uid}', 'up', '${prefix}')" title="Up">↑</button>
          <button onclick="docReorder('${item.uid}', 'down', '${prefix}')" title="Down">↓</button>
          <button onclick="docReorder('${item.uid}', 'outdent', '${prefix}')" title="Outdent">←</button>
          <button onclick="docReorder('${item.uid}', 'indent', '${prefix}')" title="Indent">→</button>
          <button onclick="docInsert('${item.uid}', '${prefix}')" title="Insert after">+</button>
          <button onclick="docDelete('${item.uid}', '${prefix}')" title="Delete" style="color:#dc3545; border-color:#f5c6cb; background:#fff;">−</button>
        </div>
        ` : ''}
      </div>
    `;

    // Doc entry
    if (isHeading) {
      const H = levelDepth === 1 ? 'h1' : (levelDepth === 2 ? 'h2' : 'h3');
      docHtml += `
        <div id="doc-item-${item.uid}" class="doc-heading-block" style="margin-top: 32px; border-bottom: ${levelDepth === 1 ? '2px solid var(--primary)' : '1px solid var(--border)'}; padding-bottom: 8px; margin-bottom: 16px; scroll-margin-top: 60px;">
          <${H} style="margin:0; color: ${levelDepth === 1 ? 'var(--primary)' : 'inherit'}; font-size: ${levelDepth === 1 ? '1.8em' : (levelDepth === 2 ? '1.4em' : '1.2em')}">
            ${h(item.level)} ${h(item.header || '')} <span style="font-size:0.5em; font-weight:normal; color:var(--text-secondary); float:right; cursor:pointer;" onclick="handleCellClick(event,'${item.uid}')">${h(item.uid)}</span>
          </${H}>
          ${item.text_html ? `<div class="item-text" style="margin-top: 12px;">${item.text_html}</div>` : ''}
        </div>
      `;
    } else {
      const ml = (levelDepth - 1) * 20;
      docHtml += `
        <div id="doc-item-${item.uid}" class="doc-item-block" style="margin-left: ${ml}px; background: #fff; border: 1px solid var(--border); border-left: 3px solid ${item.normative ? 'var(--primary)' : '#ccc'}; border-radius: 4px; padding: 12px 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); scroll-margin-top: 60px;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 8px;">
            <div>
              <strong style="font-size: 1.1em; color: var(--text);">${h(item.level)} ${h(item.header || '')}</strong>
            </div>
            <div style="text-align:right">
              <span class="cell-uid" onclick="handleCellClick(event,'${item.uid}')" style="font-size:0.9em; background:var(--bg); padding:2px 6px; border-radius:4px; border:1px solid var(--border);">${h(item.uid)}</span>
            </div>
          </div>
          <div style="margin-bottom:8px;">
            ${(item.groups || []).filter(g => g !== '(未分類)').map(g => `<span class="tag tag-group">${h(g)}</span>`).join(' ')}
            ${statusTags(item.reviewed, item.suspect, item.normative)}
          </div>
          <div class="item-text">${item.text_html}</div>
          ${item.references && item.references.length ? `<div style="margin-top: 8px; font-size: 0.85em; color: var(--text-secondary);"><strong>Ref:</strong> ${item.references.map(r => h(r.path)).join(', ')}</div>` : ''}
          ${item.ref ? `<div style="margin-top: 8px; font-size: 0.85em; color: var(--text-secondary);"><strong>Ref:</strong> ${h(item.ref)}</div>` : ''}
        </div>
      `;
    }
  }

  $main().innerHTML = `
    <div class="page-title">Document: ${h(prefix)}</div>
    <div class="page-subtitle" style="margin-bottom: 24px;">Readable Specification View</div>

    <div id="doc-view-container" style="display:flex; gap: 24px; align-items: flex-start;">
      <div class="document-view" style="flex:1; min-width:0; max-width: 800px;">
        ${docHtml || '<div class="empty-state">No items</div>'}
      </div>
      <div class="document-map-sidebar" style="width: 380px; flex-shrink: 0; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 16px; position: sticky; top: 24px; max-height: calc(100vh - 100px); overflow-y: auto;">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:8px; margin-bottom:12px;">
          <h3 style="margin:0; font-size:1em; color:var(--text-secondary);">Document Map</h3>
          <button onclick="toggleDocEditMode('${prefix}')" class="btn ${docEditMode ? 'btn-danger' : 'btn-primary'}" style="padding: 4px 8px; font-size: 0.85em;">
            ${docEditMode ? 'Finish Editing' : 'Edit'}
          </button>
        </div>
        ${mapHtml}
      </div>
    </div>
  `;

  setTimeout(() => {
    const docView = document.querySelector('.document-view');
    if (docView) {
      renderMermaidInElement(docView, 'doc');
    }
  }, 0);
}

// --- Validation ---
async function renderValidation() {
  $main().innerHTML = '<div class="loading">Loading...</div>';
  const data = await API.get('/api/validation');

  const renderList = (items, cls) =>
    items.length ? items.map(i => `<div class="issue-item ${cls}">${h(i)}</div>`).join('')
    : `<div style="padding:8px 0;color:var(--success);font-weight:600">No issues.</div>`;

  $main().innerHTML = `
    <div class="page-title">Validation Results</div>
    <div class="page-subtitle">Structure, link, and reference checks</div>

    <div class="cards">
      <div class="card"><div class="card-label">Errors</div><div class="card-value ${data.errors.length?'error':'success'}">${data.errors.length}</div></div>
      <div class="card"><div class="card-label">Warnings</div><div class="card-value ${data.warnings.length?'warning':'success'}">${data.warnings.length}</div></div>
      <div class="card"><div class="card-label">Info</div><div class="card-value">${data.info.length}</div></div>
    </div>

    ${data.errors.length ? '<div class="section-title" style="color:var(--error)">Errors</div>' + renderList(data.errors, 'issue-error') : ''}
    ${data.warnings.length ? '<div class="section-title" style="color:#e37400">Warnings</div>' + renderList(data.warnings, 'issue-warning') : ''}
    ${data.info.length ? '<div class="section-title" style="color:var(--primary)">Info</div>' + renderList(data.info, 'issue-info') : ''}
  `;
}

// ===================================================================
// Item Panels — Multi-panel comparison support
// ===================================================================
// Ctrl+click or Shift+click on Parents/Children/Siblings link-chips
// opens a new panel side-by-side for comparison. Normal click navigates
// within the current panel.
// ===================================================================
let panelIdCounter = 0;
let activePanels = []; // { id, uid, editMode, el }

function handleCellClick(event, uid) {
  // Highlight clicked cell
  document.querySelectorAll('td.cell-selected').forEach(el => el.classList.remove('cell-selected'));
  const td = event.target.closest('td');
  if (td) td.classList.add('cell-selected');

  if (event.ctrlKey || event.metaKey || event.shiftKey) {
    event.preventDefault();
    addItemPanel(uid);
  } else {
    location.hash = '#/item/' + uid;
  }
}

function handlePanelItemClick(event, panelId, uid) {
  if (event.ctrlKey || event.metaKey || event.shiftKey) {
    event.preventDefault();
    event.stopPropagation();
    addItemPanel(uid);
  } else {
    navigateInPanel(panelId, uid);
  }
}

function handlePanelNav(event, panelId, targetUid) {
  if (event.ctrlKey || event.metaKey || event.shiftKey) {
    event.preventDefault();
    event.stopPropagation();
    addItemPanel(targetUid);
  } else {
    navigateInPanel(panelId, targetUid);
  }
}

function createPanelElement(panelId) {
  const el = document.createElement('div');
  el.className = 'item-panel';
  el.dataset.panelId = panelId;
  el.innerHTML = `
    <div class="item-panel-content" id="pc-${panelId}"><div class="loading">Loading...</div></div>
    <div class="panel-nav" id="pn-${panelId}"></div>
  `;
  return el;
}

function updateMainMargin() {
  // No-op: main area width should not change when item detail panels open/close.
  // Panels overlay on top of the main content instead.
}

async function openItemPanel(uid) {
  if (!uid) return;
  // Single panel already showing this uid — nothing to do
  if (activePanels.length === 1 && activePanels[0].uid === uid) return;
  // Single panel open — navigate within it
  if (activePanels.length === 1) {
    await navigateInPanel(activePanels[0].id, uid);
    return;
  }
  // Otherwise close all and open single
  closeAllPanels();
  await addItemPanel(uid);
}

async function addItemPanel(uid) {
  if (!uid) return;
  // Don't add duplicate — flash existing instead
  const existing = activePanels.find(p => p.uid === uid);
  if (existing) {
    existing.el.style.outlineColor = 'var(--primary)';
    setTimeout(() => { existing.el.style.outlineColor = 'transparent'; }, 800);
    return;
  }

  const id = panelIdCounter++;
  const container = document.getElementById('item-panels-container');
  const panelEl = createPanelElement(id);
  container.appendChild(panelEl);

  const ps = { id, uid, editMode: false, el: panelEl };
  activePanels.push(ps);

  container.classList.add('open');
  updateMainMargin();
  requestAnimationFrame(() => panelEl.classList.add('open'));

  try {
    const data = await API.get('/api/items/' + uid);
    renderPanelContent(ps, data);
  } catch {
    panelEl.querySelector('.item-panel-content').innerHTML =
      `<div class="empty-state">Item "${h(uid)}" not found.</div>`;
  }
}

async function navigateInPanel(panelId, targetUid) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) { openItemPanel(targetUid); return; }
  // Check if another panel already shows this uid
  const dup = activePanels.find(p => p.uid === targetUid && p.id !== panelId);
  if (dup) {
    dup.el.style.outlineColor = 'var(--primary)';
    setTimeout(() => { dup.el.style.outlineColor = 'transparent'; }, 800);
    return;
  }
  ps.uid = targetUid;
  ps.editMode = false;
  if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
  const contentEl = document.getElementById('pc-' + panelId);
  contentEl.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const data = await API.get('/api/items/' + targetUid);
    renderPanelContent(ps, data);
  } catch {
    contentEl.innerHTML = `<div class="empty-state">Item "${h(targetUid)}" not found.</div>`;
  }
}

function clearCellSelection() {
  document.querySelectorAll('td.cell-selected').forEach(el => el.classList.remove('cell-selected'));
}

function closePanel(panelId) {
  const idx = activePanels.findIndex(p => p.id === panelId);
  if (idx === -1) return;
  const ps = activePanels[idx];
  if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
  ps.el.classList.remove('open');
  setTimeout(() => {
    ps.el.remove();
    activePanels.splice(activePanels.findIndex(p => p.id === panelId), 1);
    updateMainMargin();
    if (activePanels.length === 0) {
      document.getElementById('item-panels-container').classList.remove('open');
      clearCellSelection();
      if (location.hash.startsWith('#/item/')) {
        const prev = '#/' + currentView + (currentParam ? '/' + currentParam : '');
        history.replaceState(null, '', prev);
      }
    }
  }, 300);
}

function closeAllPanels() {
  for (const ps of activePanels) { if (ps.editor) { ps.editor.destroy(); ps.editor = null; } }
  const container = document.getElementById('item-panels-container');
  container.innerHTML = '';
  container.classList.remove('open');
  activePanels = [];
  updateMainMargin();
  if (location.hash.startsWith('#/item/')) {
    const prev = '#/' + currentView + (currentParam ? '/' + currentParam : '');
    history.replaceState(null, '', prev);
  }
}

function closeItemPanel() { closeAllPanels(); clearCellSelection(); }

function renderPanelContent(ps, data) {
  if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
  ps.editMode = false;
  ps.originalHtml = data.text_html; // Store for editor initialization
  const pid = ps.id;
  const contentEl = document.getElementById('pc-' + pid);

  const chipHtml = (items) => items.length
    ? items.map(it =>
        `<a class="link-chip ${it.suspect?'suspect':''} ${!it.reviewed?'unreviewed':''}" onclick="handlePanelItemClick(event,${pid},'${it.uid}')">${h(it.uid)}${it.suspect?' &#x26A0;':''}${!it.reviewed?' &#x25CB;':''}</a>`
      ).join('')
    : '<span style="color:var(--text-secondary)">&#8212;</span>';

  const parentsHtml = chipHtml(data.parents);
  const childrenHtml = chipHtml(data.children);
  const siblingsHtml = chipHtml(data.siblings || []);

  contentEl.innerHTML = `
    <div class="panel-header">
      <div>
        <strong style="font-size:1.15em">${h(data.uid)}</strong>
        ${data.header ? `<span class="panel-header-title">${h(data.header)}</span>` : ''}
        <div style="margin-top:4px">
          <span class="tag tag-prefix">${h(data.prefix)}</span>
          ${(data.groups || []).map(g => `<span class="tag tag-group">${h(g)}</span>`).join(' ')}
        </div>
        ${(data.author || data.created_at || data.updated_at) ? `<div class="git-meta-inline">
          ${data.author ? `<span class="git-meta-item" title="Author">${h(data.author)}</span>` : ''}
          ${data.created_at ? `<span class="git-meta-item" title="Created">${h(data.created_at)}${data.created_commit ? ' <span class="git-commit-hash" title="Created: ' + h(data.created_commit) + '">' + h(data.created_commit.slice(0,7)) + '</span>' : ''}</span>` : ''}
          ${data.updated_at && data.updated_at !== data.created_at ? `<span class="git-meta-item" title="Updated">${h(data.updated_at)}${data.updated_commit ? ' <span class="git-commit-hash" title="Updated: ' + h(data.updated_commit) + '">' + h(data.updated_commit.slice(0,7)) + '</span>' : ''}</span>` : ''}
          ${data.updated_at && data.updated_at === data.created_at && data.updated_commit && data.updated_commit !== data.created_commit ? `<span class="git-meta-item" title="Updated commit"><span class="git-commit-hash" title="Updated: ${h(data.updated_commit)}">${h(data.updated_commit.slice(0,7))}</span></span>` : ''}
        </div>` : ''}
      </div>
      <button class="panel-close" onclick="closePanel(${pid})">&times;</button>
    </div>

    <div style="margin-bottom:12px">${statusTags(data.reviewed, data.suspect, data.normative)}</div>

    <div id="ptv-${pid}" class="item-text">${data.text_html}</div>
    <div id="pte-${pid}" class="hidden">
      <div class="edit-fields" style="margin-bottom: 12px; display: grid; gap: 8px;">
        <div><label style="font-size:0.85em;color:var(--text-secondary)">Groups (comma-separated):</label> <input type="text" id="p-groups-${pid}" value="${h(data.groups ? data.groups.filter(g => g !== '(未分類)').join(', ') : '')}" style="width:100%; padding:4px; border:1px solid var(--border); border-radius:4px;"></div>
        <div><label style="font-size:0.85em;color:var(--text-secondary)">Ref:</label> <input type="text" id="p-ref-${pid}" value="${h(data.ref || '')}" style="width:100%; padding:4px; border:1px solid var(--border); border-radius:4px;"></div>
        <div><label style="font-size:0.85em;color:var(--text-secondary)">References (JSON array, e.g. [{"path":"src/main.py","type":"file"}]):</label> <input type="text" id="p-references-${pid}" value="${h(data.references && data.references.length ? JSON.stringify(data.references) : '')}" style="width:100%; padding:4px; border:1px solid var(--border); border-radius:4px;"></div>
        <div style="display:flex; gap: 16px;">
          <label style="font-size:0.85em;color:var(--text-secondary)"><input type="checkbox" id="p-normative-${pid}" ${data.normative !== false ? 'checked' : ''}> Normative</label>
          <label style="font-size:0.85em;color:var(--text-secondary)"><input type="checkbox" id="p-derived-${pid}" ${data.derived ? 'checked' : ''}> Derived</label>
        </div>
      </div>
      <textarea id="pta-${pid}" class="editor-area">${h(data.text)}</textarea>
      <div id="prich-${pid}" class="tiptap-wrap hidden"></div>
      <div class="actions" style="margin-top:8px">
        <button class="btn btn-primary" id="psb-${pid}" onclick="panelSave(${pid})">Save</button>
        <button class="btn" onclick="panelCancelEdit(${pid})">Cancel</button>
        <button class="btn btn-sm" id="ptoggle-${pid}" onclick="panelToggleEditMode(${pid})" style="margin-left:auto; display:none;">Switch to Markdown</button>
      </div>
    </div>

    ${data.ref ? '<div class="meta-row"><span class="meta-label">ref:</span> <span class="tag tag-ref">' + h(data.ref) + '</span></div>' : ''}
    ${data.references && data.references.length ? '<div class="meta-row"><span class="meta-label">references:</span> <span class="tag tag-ref">' + data.references.map(r => h(r.path || '') + (r.type && r.type !== 'file' ? ' (' + h(r.type) + ')' : '')).join(', ') + '</span></div>' : ''}
    ${data.derived ? '<div class="meta-row"><span class="meta-label">derived:</span> <span class="tag" style="background:#e8f0fe;color:#1a73e8">true</span></div>' : ''}

    <div class="meta-row"><span class="meta-label">Parents:</span> <div class="link-list">${parentsHtml}</div></div>
    <div class="meta-row"><span class="meta-label">Children:</span> <div class="link-list">${childrenHtml}</div></div>
    <div class="meta-row"><span class="meta-label">Siblings:</span> <div class="link-list">${siblingsHtml}</div></div>

    <div class="actions" id="pa-${pid}">
      <button class="btn btn-edit" onclick="panelStartEdit(${pid})">Edit</button>
      <button class="btn btn-success" id="prb-${pid}" onclick="panelReview(${pid})" ${data.reviewed ? 'disabled' : ''}>Review</button>
      <button class="btn btn-warning" id="pcb-${pid}" onclick="panelClear(${pid})" ${data.suspect ? '' : 'disabled'}>Clear Suspect</button>
    </div>
  `;

  document.getElementById('pn-' + pid).innerHTML = `
    <button ${data.prev_uid ? `onclick="handlePanelNav(event,${pid},'${data.prev_uid}')"` : 'disabled'}>&larr; Prev${data.prev_uid ? ' (' + h(data.prev_uid) + ')' : ''}</button>
    <button ${data.next_uid ? `onclick="handlePanelNav(event,${pid},'${data.next_uid}')"` : 'disabled'}>Next${data.next_uid ? ' (' + h(data.next_uid) + ')' : ''} &rarr;</button>
  `;

  // Render Mermaid diagrams if available
  setTimeout(() => renderMermaidInPanel(pid), 0);
}

// ===================================================================
// Textarea enhancement (offline fallback)
// ===================================================================
function enhanceTextarea(ta) {
  if (ta._enhanced) return;
  ta._enhanced = true;
  ta.addEventListener('keydown', function(e) {
    if (e.key !== 'Tab') return;
    e.preventDefault();
    const s = this.selectionStart, end = this.selectionEnd, v = this.value;
    const ls = v.lastIndexOf('\n', s - 1) + 1;
    if (e.shiftKey) {
      const block = v.substring(ls, end);
      const dedented = block.replace(/^ {1,2}/gm, '');
      const firstRemoved = (block.match(/^ {1,2}/) || [''])[0].length;
      this.value = v.substring(0, ls) + dedented + v.substring(end);
      this.selectionStart = Math.max(ls, s - firstRemoved);
      this.selectionEnd = end - (block.length - dedented.length);
    } else if (s === end) {
      this.value = v.substring(0, s) + '  ' + v.substring(end);
      this.selectionStart = this.selectionEnd = s + 2;
    } else {
      const block = v.substring(ls, end);
      const indented = block.replace(/^/gm, '  ');
      this.value = v.substring(0, ls) + indented + v.substring(end);
      this.selectionStart = s + 2;
      this.selectionEnd = end + (indented.length - block.length);
    }
  });
}

// ===================================================================
// TipTap rich editor helpers
// ===================================================================
function createTiptapEditor(panelId, htmlContent) {
  const TabHandler = RichEditor.Extension.create({
    name: 'tabHandler',
    addKeyboardShortcuts() {
      return {
        'Tab': () => {
          if (this.editor.isActive('listItem')) return this.editor.commands.sinkListItem('listItem');
          if (this.editor.isActive('codeBlock')) return this.editor.commands.insertContent('  ');
          return false;
        },
        'Shift-Tab': () => {
          if (this.editor.isActive('listItem')) return this.editor.commands.liftListItem('listItem');
          return false;
        },
      };
    },
  });
  const editor = new RichEditor.Editor({
    element: document.getElementById('ptip-' + panelId),
    extensions: [
      RichEditor.StarterKit,
      TabHandler,
      RichEditor.Table.configure({ resizable: true }),
      RichEditor.TableRow,
      RichEditor.TableHeader,
      RichEditor.TableCell,
    ],
    content: htmlContent,
  });
  buildTiptapToolbar(panelId, editor);
  return editor;
}

function buildTiptapToolbar(panelId, editor) {
  const bar = document.getElementById('ptbar-' + panelId);
  const btns = [
    { label: 'B', cmd: () => editor.chain().focus().toggleBold().run(), active: () => editor.isActive('bold'), title: 'Bold (Ctrl+B)' },
    { label: 'I', cmd: () => editor.chain().focus().toggleItalic().run(), active: () => editor.isActive('italic'), title: 'Italic (Ctrl+I)' },
    { label: 'S', cmd: () => editor.chain().focus().toggleStrike().run(), active: () => editor.isActive('strike'), title: 'Strikethrough' },
    { label: '<>', cmd: () => editor.chain().focus().toggleCode().run(), active: () => editor.isActive('code'), title: 'Inline code' },
    'sep',
    { label: 'H1', cmd: () => editor.chain().focus().toggleHeading({level:1}).run(), active: () => editor.isActive('heading',{level:1}) },
    { label: 'H2', cmd: () => editor.chain().focus().toggleHeading({level:2}).run(), active: () => editor.isActive('heading',{level:2}) },
    { label: 'H3', cmd: () => editor.chain().focus().toggleHeading({level:3}).run(), active: () => editor.isActive('heading',{level:3}) },
    'sep',
    { label: '\u2022', cmd: () => editor.chain().focus().toggleBulletList().run(), active: () => editor.isActive('bulletList'), title: 'Bullet list' },
    { label: '1.', cmd: () => editor.chain().focus().toggleOrderedList().run(), active: () => editor.isActive('orderedList'), title: 'Numbered list' },
    'sep',
    { label: '```', cmd: () => editor.chain().focus().toggleCodeBlock().run(), active: () => editor.isActive('codeBlock'), title: 'Code block' },
    { label: '\u275d', cmd: () => editor.chain().focus().toggleBlockquote().run(), active: () => editor.isActive('blockquote'), title: 'Quote' },
    { label: '\u2014', cmd: () => editor.chain().focus().setHorizontalRule().run(), active: () => false, title: 'Horizontal rule' },
    'sep',
    { label: '\u25A4', cmd: () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(), active: () => editor.isActive('table'), title: 'Insert table' },
  ];
  for (const b of btns) {
    if (b === 'sep') {
      const sep = document.createElement('span');
      sep.className = 'tb-sep';
      bar.appendChild(sep);
      continue;
    }
    const btn = document.createElement('button');
    btn.textContent = b.label;
    btn.title = b.title || b.label;
    btn.type = 'button';
    btn.addEventListener('click', (ev) => { ev.preventDefault(); b.cmd(); });
    bar.appendChild(btn);
  }
  const updateState = () => {
    let i = 0;
    for (const b of btns) {
      if (b === 'sep') { i++; continue; }
      bar.children[i++].classList.toggle('is-active', b.active());
    }
  };
  editor.on('selectionUpdate', updateState);
  editor.on('transaction', updateState);
}

function tiptapToMarkdown(editor) {
  const html = editor.getHTML();
  const td = new RichEditor.TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
    bulletListMarker: '-',
    emDelimiter: '*',
    strongDelimiter: '**',
  });
  if (RichEditor.gfmTables) {
    td.use(RichEditor.gfmTables);
  }
  td.addRule('strikethrough', {
    filter: ['del', 's'],
    replacement: (content) => '~~' + content + '~~',
  });
  return td.turndown(html);
}

// ===================================================================
// Panel edit actions
// ===================================================================
function panelStartEdit(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) return;
  ps.editMode = true;
  document.getElementById('ptv-' + panelId).classList.add('hidden');
  document.getElementById('pte-' + panelId).classList.remove('hidden');
  document.getElementById('pa-' + panelId).classList.add('hidden');

  if (richEditorReady) {
    const ta = document.getElementById('pta-' + panelId);
    ta.classList.add('hidden');
    const richWrap = document.getElementById('prich-' + panelId);
    richWrap.classList.remove('hidden');
    richWrap.innerHTML = '<div class="tiptap-toolbar" id="ptbar-' + panelId + '"></div><div id="ptip-' + panelId + '"></div>';
    const htmlContent = ps.originalHtml || document.getElementById('ptv-' + panelId).innerHTML;
    ps.editor = createTiptapEditor(panelId, htmlContent);
    ps.useRich = true;
    ps.editor.commands.focus('end');
    const toggleBtn = document.getElementById('ptoggle-' + panelId);
    if (toggleBtn) {
      toggleBtn.style.display = 'inline-block';
      toggleBtn.textContent = 'Switch to Markdown';
    }
  } else {
    const ta = document.getElementById('pta-' + panelId);
    ta.classList.remove('hidden');
    enhanceTextarea(ta);
    ta.focus();
    ta.style.height = 'auto';
    ta.style.height = Math.max(150, ta.scrollHeight + 4) + 'px';
    ps.useRich = false;
  }
}

async function panelToggleEditMode(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps || !richEditorReady) return;
  const toggleBtn = document.getElementById('ptoggle-' + panelId);
  const ta = document.getElementById('pta-' + panelId);
  const richWrap = document.getElementById('prich-' + panelId);

  if (ps.useRich) {
    const markdown = tiptapToMarkdown(ps.editor);
    ps.editor.destroy();
    ps.editor = null;
    ta.value = markdown;
    richWrap.classList.add('hidden');
    ta.classList.remove('hidden');
    enhanceTextarea(ta);
    ta.focus();
    ta.style.height = 'auto';
    ta.style.height = Math.max(150, ta.scrollHeight + 4) + 'px';
    ps.useRich = false;
    if (toggleBtn) toggleBtn.textContent = 'Switch to Rich Text';
  } else {
    toggleBtn.textContent = 'Loading...';
    toggleBtn.disabled = true;
    try {
      const markedMod = await import('https://esm.sh/marked@12');
      const html = markedMod.parse(ta.value);
      ta.classList.add('hidden');
      richWrap.classList.remove('hidden');
      richWrap.innerHTML = '<div class="tiptap-toolbar" id="ptbar-' + panelId + '"></div><div id="ptip-' + panelId + '"></div>';
      ps.editor = createTiptapEditor(panelId, html);
      ps.useRich = true;
      ps.editor.commands.focus('end');
      if (toggleBtn) toggleBtn.textContent = 'Switch to Markdown';
    } catch (e) {
      console.warn('Cannot load marked:', e);
      alert('Failed to load markdown parser. Cannot switch back to Rich Text.');
      if (toggleBtn) toggleBtn.textContent = 'Switch to Rich Text';
    } finally {
      toggleBtn.disabled = false;
    }
  }
}

function panelCancelEdit(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (ps) {
    ps.editMode = false;
    if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
  }
  document.getElementById('ptv-' + panelId).classList.remove('hidden');
  document.getElementById('pte-' + panelId).classList.add('hidden');
  document.getElementById('pa-' + panelId).classList.remove('hidden');
}

async function panelSave(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) return;
  let text;
  if (ps.useRich && ps.editor) {
    text = tiptapToMarkdown(ps.editor);
  } else {
    text = document.getElementById('pta-' + panelId).value;
  }

  const groupsStr = document.getElementById('p-groups-' + panelId)?.value || '';
  const groups = groupsStr.split(',').map(g => g.trim()).filter(Boolean);
  const ref = document.getElementById('p-ref-' + panelId)?.value || '';
  const referencesStr = document.getElementById('p-references-' + panelId)?.value || '';
  let references = [];
  try {
    if (referencesStr.trim()) {
      references = JSON.parse(referencesStr);
      if (!Array.isArray(references)) throw new Error('References must be an array');
    }
  } catch (e) {
    alert("Invalid JSON in references field. It must be an array of objects.");
    return;
  }
  const normative = document.getElementById('p-normative-' + panelId)?.checked;
  const derived = document.getElementById('p-derived-' + panelId)?.checked;

  const btn = document.getElementById('psb-' + panelId);
  btn.disabled = true; btn.textContent = 'Saving...';
  try {
    const res = await API.post('/api/items/' + ps.uid + '/edit', { 
      text,
      groups,
      ref,
      references,
      normative,
      derived
    });
    if (res.ok) {
      if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
      ps.editMode = false;
      ps.useRich = false;
      toast(ps.uid + ' updated');
      refreshCurrentView();
      renderPanelContent(ps, res.item);
      refreshOtherPanels(panelId);
    } else {
      toast('Error: ' + res.error, 'error');
      btn.disabled = false; btn.textContent = 'Save';
    }
  } catch (e) {
    toast('Error: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = 'Save';
  }
}

async function panelReview(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) return;
  const btn = document.getElementById('prb-' + panelId);
  btn.disabled = true; btn.textContent = 'Processing...';
  try {
    const res = await API.post('/api/items/' + ps.uid + '/review');
    if (res.ok) {
      toast(ps.uid + ' reviewed');
      refreshCurrentView();
      renderPanelContent(ps, res.item);
      refreshOtherPanels(panelId);
    } else {
      toast('Error: ' + res.error, 'error');
      btn.disabled = false; btn.textContent = 'Review';
    }
  } catch (e) {
    toast('Error: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = 'Review';
  }
}

async function panelClear(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) return;
  const btn = document.getElementById('pcb-' + panelId);
  btn.disabled = true; btn.textContent = 'Processing...';
  try {
    const res = await API.post('/api/items/' + ps.uid + '/clear');
    if (res.ok) {
      toast(ps.uid + ' suspect cleared');
      refreshCurrentView();
      renderPanelContent(ps, res.item);
      refreshOtherPanels(panelId);
    } else {
      toast('Error: ' + res.error, 'error');
      btn.disabled = false; btn.textContent = 'Clear Suspect';
    }
  } catch (e) {
    toast('Error: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = 'Clear Suspect';
  }
}

async function refreshOtherPanels(excludeId) {
  for (const ps of activePanels) {
    if (ps.id === excludeId) continue;
    try {
      const data = await API.get('/api/items/' + ps.uid);
      renderPanelContent(ps, data);
    } catch { /* panel data may have been deleted */ }
  }
}

// ===================================================================
// Tree Graph View — Interactive traceability graph
// ===================================================================

const TREE_COLORS = {
  REQ: '#4a90d9', ARCH: '#8b5cf6', SPEC: '#10b981',
  IMPL: '#f59e0b', TST: '#ef4444', DEFAULT: '#6b7280',
};

function prefixColor(prefix) {
  return TREE_COLORS[prefix] || TREE_COLORS.DEFAULT;
}

let treeState = {
  selectedNode: null,
  hops: 2,
  graphData: null,
  mode: 'ego',   // 'ego' | 'full'
  groupFilter: '',
  dragLine: null,
  dragSource: null,
};

async function renderTreeGraph(param) {
  const main = document.getElementById('main');

  if (!d3Ready) {
    main.innerHTML = `<div class="tree-landing">
      <h2>Tree Graph</h2>
      <p>D3.js の読み込みに失敗しました。オンライン環境で再試行してください。</p>
    </div>`;
    return;
  }

  // Landing page: group/item selection
  if (!param && !treeState.selectedNode) {
    const [overview, graphData] = await Promise.all([
      API.get('/api/overview'),
      API.get('/api/graph'),
    ]);
    treeState.graphData = graphData;

    const groups = overview.groups || [];
    const nodesByPrefix = {};
    graphData.nodes.forEach(n => {
      if (!nodesByPrefix[n.prefix]) nodesByPrefix[n.prefix] = [];
      nodesByPrefix[n.prefix].push(n);
    });

    main.innerHTML = `<div class="tree-landing">
      <h2>Tree Graph</h2>
      <p>ノードを選択してエゴセントリックビューを表示します。</p>
      <div class="tree-search-row">
        <input type="text" id="tree-uid-search" placeholder="UID またはヘッダーで検索..." class="tree-search-input">
        <label class="tree-hops-label">ホップ数:
          <input type="range" id="tree-hops-slider" min="1" max="4" value="${treeState.hops}" class="tree-hops-slider">
          <span id="tree-hops-val">${treeState.hops}</span>
        </label>
      </div>
      <div id="tree-search-results" class="tree-search-results"></div>
      <div class="tree-quick-filters">
        <h3>グループで絞り込み</h3>
        <div class="tree-group-pills">
          ${groups.map(g => `<button class="tree-pill" data-group="${h(g)}">${h(g)}</button>`).join('')}
        </div>
        <h3>ドキュメント全体</h3>
        <div class="tree-group-pills">
          ${graphData.layers.map(p => `<button class="tree-pill tree-pill-doc" data-prefix="${h(p)}" style="border-color:${prefixColor(p)}">${h(p)} (${(nodesByPrefix[p]||[]).length})</button>`).join('')}
        </div>
      </div>
    </div>`;

    // Search interaction
    const searchInput = document.getElementById('tree-uid-search');
    const searchResults = document.getElementById('tree-search-results');
    searchInput.addEventListener('input', (e) => {
      if (e.isComposing) return;
      filterTreeSearch(searchInput.value, graphData.nodes, searchResults);
    });
    searchInput.addEventListener('compositionend', () => {
      filterTreeSearch(searchInput.value, graphData.nodes, searchResults);
    });

    // Hops slider
    document.getElementById('tree-hops-slider').addEventListener('input', (e) => {
      treeState.hops = parseInt(e.target.value);
      document.getElementById('tree-hops-val').textContent = treeState.hops;
    });

    // Group pills
    main.querySelectorAll('.tree-pill[data-group]').forEach(btn => {
      btn.addEventListener('click', () => {
        const group = btn.dataset.group;
        const filtered = graphData.nodes.filter(n => n.groups.includes(group));
        renderTreeSVG(main, { nodes: filtered, edges: graphData.edges.filter(e => filtered.some(n => n.uid === e.child) && filtered.some(n => n.uid === e.parent)), layers: graphData.layers }, null);
      });
    });

    // Prefix pills
    main.querySelectorAll('.tree-pill-doc[data-prefix]').forEach(btn => {
      btn.addEventListener('click', () => {
        const prefix = btn.dataset.prefix;
        // Show nodes from this prefix + their direct parents/children
        const prefixNodes = new Set(graphData.nodes.filter(n => n.prefix === prefix).map(n => n.uid));
        const relatedUids = new Set(prefixNodes);
        graphData.edges.forEach(e => {
          if (prefixNodes.has(e.child)) relatedUids.add(e.parent);
          if (prefixNodes.has(e.parent)) relatedUids.add(e.child);
        });
        const nodes = graphData.nodes.filter(n => relatedUids.has(n.uid));
        const edges = graphData.edges.filter(e => relatedUids.has(e.child) && relatedUids.has(e.parent));
        renderTreeSVG(main, { nodes, edges, layers: graphData.layers }, null);
      });
    });

    setTimeout(() => searchInput.focus(), 100);
    return;
  }

  // Ego-centric view for a specific node
  const uid = param || treeState.selectedNode;
  if (uid) {
    treeState.selectedNode = uid;
    try {
      const data = await API.get(`/api/graph/ego/${uid}?hops=${treeState.hops}`);
      renderTreeSVG(main, data, uid);
    } catch {
      main.innerHTML = `<p>アイテム ${h(uid)} が見つかりません。</p>`;
    }
  }
}

function filterTreeSearch(query, nodes, container) {
  if (!query || query.length < 1) {
    container.innerHTML = '';
    return;
  }
  const q = query.toLowerCase();
  const matches = nodes.filter(n =>
    n.uid.toLowerCase().includes(q) || (n.header && n.header.toLowerCase().includes(q))
  ).slice(0, 20);

  container.innerHTML = matches.map(n => `
    <div class="tree-search-item" data-uid="${h(n.uid)}">
      <span class="tree-tag" style="background:${prefixColor(n.prefix)}">${h(n.prefix)}</span>
      <strong>${h(n.uid)}</strong>
      <span class="tree-search-header">${h(n.header || '')}</span>
      ${n.suspect ? '<span class="tree-tag tree-tag-suspect">suspect</span>' : ''}
    </div>
  `).join('');

  container.querySelectorAll('.tree-search-item').forEach(el => {
    el.addEventListener('click', () => {
      treeState.selectedNode = el.dataset.uid;
      location.hash = '#/tree/' + el.dataset.uid;
    });
  });
}

function renderTreeSVG(main, data, centerUid) {
  const { nodes, edges, layers } = data;
  if (nodes.length === 0) {
    main.innerHTML = '<p>表示するノードがありません。</p>';
    return;
  }

  // Build a back-button + controls header
  const hopsHtml = centerUid ? `
    <label class="tree-hops-label">ホップ数:
      <input type="range" id="tree-hops-slider2" min="1" max="4" value="${treeState.hops}" class="tree-hops-slider">
      <span id="tree-hops-val2">${treeState.hops}</span>
    </label>` : '';

  main.innerHTML = `
    <div class="tree-toolbar">
      <button class="tree-back-btn" onclick="treeState.selectedNode=null;location.hash='#/tree'">&#8592; 一覧に戻る</button>
      ${centerUid ? `<span class="tree-center-label">中心: <strong>${h(centerUid)}</strong></span>` : ''}
      ${hopsHtml}
      <button class="tree-btn" id="tree-zoom-reset">ズームリセット</button>
    </div>
    <div id="tree-svg-container" class="tree-svg-container"></div>
    <div id="tree-detail-panel" class="tree-detail-panel" style="display:none;"></div>
    <div id="tree-context-menu" class="tree-context-menu" style="display:none;"></div>
  `;

  // Hops slider interaction
  const slider2 = document.getElementById('tree-hops-slider2');
  if (slider2) {
    slider2.addEventListener('change', (e) => {
      treeState.hops = parseInt(e.target.value);
      document.getElementById('tree-hops-val2').textContent = treeState.hops;
      if (treeState.selectedNode) {
        location.hash = '#/tree/' + treeState.selectedNode;
      }
    });
  }

  const container = document.getElementById('tree-svg-container');
  const rect = container.getBoundingClientRect();
  const width = rect.width || 900;
  const height = Math.max(500, window.innerHeight - 200);

  // Layout: assign x by layer, y by index within layer
  const nodeMap = new Map(nodes.map(n => [n.uid, { ...n }]));
  const layerNodes = {};
  nodes.forEach(n => {
    if (!layerNodes[n.prefix]) layerNodes[n.prefix] = [];
    layerNodes[n.prefix].push(n.uid);
  });

  // Order layers by the document hierarchy
  const orderedLayers = layers.filter(l => layerNodes[l]);
  const layerCount = orderedLayers.length || 1;
  const colWidth = width / (layerCount + 1);

  const positions = {};
  orderedLayers.forEach((layer, li) => {
    const uids = layerNodes[layer] || [];
    const rowHeight = Math.max(60, (height - 80) / (uids.length + 1));
    uids.forEach((uid, ri) => {
      positions[uid] = {
        x: colWidth * (li + 1),
        y: rowHeight * (ri + 1),
      };
    });
  });

  // D3 rendering
  const svg = d3.select(container).append('svg')
    .attr('width', width)
    .attr('height', height)
    .attr('class', 'tree-svg');

  const g = svg.append('g').attr('class', 'tree-root');

  // Zoom
  const zoom = d3.zoom()
    .scaleExtent([0.2, 3])
    .on('zoom', (event) => g.attr('transform', event.transform));
  svg.call(zoom);

  document.getElementById('tree-zoom-reset').addEventListener('click', () => {
    svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);
  });

  // Layer labels
  orderedLayers.forEach((layer, li) => {
    g.append('text')
      .attr('x', colWidth * (li + 1))
      .attr('y', 24)
      .attr('text-anchor', 'middle')
      .attr('class', 'tree-layer-label')
      .attr('fill', prefixColor(layer))
      .text(layer);
  });

  // Edges (draw first so they're behind nodes)
  const edgeGroup = g.append('g').attr('class', 'tree-edges');

  edges.forEach(e => {
    const p1 = positions[e.parent];
    const p2 = positions[e.child];
    if (!p1 || !p2) return;

    const path = edgeGroup.append('path')
      .attr('d', `M${p1.x + 60},${p1.y} C${(p1.x + p2.x) / 2 + 30},${p1.y} ${(p1.x + p2.x) / 2 - 30},${p2.y} ${p2.x - 60},${p2.y}`)
      .attr('class', 'tree-edge' + (e.suspect ? ' tree-edge-suspect' : ''))
      .attr('data-parent', e.parent)
      .attr('data-child', e.child)
      .attr('marker-end', 'url(#arrowhead)');

    // Right-click to unlink
    path.on('contextmenu', (event) => {
      event.preventDefault();
      showTreeContextMenu(event, e.child, e.parent);
    });

    // Hover highlight
    path.on('mouseenter', () => path.classed('tree-edge-hover', true))
      .on('mouseleave', () => path.classed('tree-edge-hover', false));
  });

  // Arrow marker
  svg.append('defs').append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '0 0 10 6')
    .attr('refX', 10).attr('refY', 3)
    .attr('markerWidth', 8).attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path').attr('d', 'M0,0 L10,3 L0,6 Z').attr('fill', '#999');

  // Drag-line marker (for creating links)
  svg.select('defs').append('marker')
    .attr('id', 'arrowhead-drag')
    .attr('viewBox', '0 0 10 6')
    .attr('refX', 10).attr('refY', 3)
    .attr('markerWidth', 8).attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path').attr('d', 'M0,0 L10,3 L0,6 Z').attr('fill', '#4a90d9');

  // Nodes
  const nodeGroup = g.append('g').attr('class', 'tree-nodes');

  nodes.forEach(n => {
    const pos = positions[n.uid];
    if (!pos) return;

    const ng = nodeGroup.append('g')
      .attr('transform', `translate(${pos.x - 55}, ${pos.y - 18})`)
      .attr('class', 'tree-node-group')
      .attr('data-uid', n.uid);

    // Node rectangle
    ng.append('rect')
      .attr('width', 110)
      .attr('height', 36)
      .attr('rx', 6)
      .attr('class', 'tree-node' +
        (n.uid === centerUid ? ' tree-node-center' : '') +
        (!n.normative ? ' tree-node-dim' : ''))
      .attr('fill', n.reviewed ? '#fff' : '#f3f4f6')
      .attr('stroke', prefixColor(n.prefix))
      .attr('stroke-width', n.uid === centerUid ? 3 : 1.5);

    // UID text
    ng.append('text')
      .attr('x', 55).attr('y', 15)
      .attr('text-anchor', 'middle')
      .attr('class', 'tree-node-uid')
      .text(n.uid);

    // Header text (truncated)
    const headerTxt = n.header ? (n.header.length > 12 ? n.header.slice(0, 11) + '...' : n.header) : '';
    ng.append('text')
      .attr('x', 55).attr('y', 29)
      .attr('text-anchor', 'middle')
      .attr('class', 'tree-node-header')
      .text(headerTxt);

    // Status icon
    if (n.suspect) {
      ng.append('text').attr('x', 98).attr('y', 13).attr('class', 'tree-status-icon').text('\u26a0');
    } else if (n.reviewed) {
      ng.append('text').attr('x', 98).attr('y', 13).attr('class', 'tree-status-icon tree-status-ok').text('\u2713');
    }

    // Connector circle (right side, for dragging to create links)
    ng.append('circle')
      .attr('cx', 110).attr('cy', 18)
      .attr('r', 5)
      .attr('class', 'tree-connector')
      .attr('fill', prefixColor(n.prefix));

    // Click → select + show detail
    ng.on('click', (event) => {
      event.stopPropagation();
      selectTreeNode(n.uid, data);
    });

    // Double-click → navigate to item detail
    ng.on('dblclick', (event) => {
      event.stopPropagation();
      location.hash = '#/item/' + n.uid;
    });

    // Drag from connector → create link
    const connector = ng.select('.tree-connector');
    connector.call(d3.drag()
      .on('start', function(event) {
        event.sourceEvent.stopPropagation();
        treeState.dragSource = n.uid;
        treeState.dragLine = g.append('line')
          .attr('class', 'tree-drag-line')
          .attr('x1', pos.x + 55).attr('y1', pos.y)
          .attr('x2', pos.x + 55).attr('y2', pos.y)
          .attr('marker-end', 'url(#arrowhead-drag)');
      })
      .on('drag', function(event) {
        if (treeState.dragLine) {
          const t = d3.zoomTransform(svg.node());
          const mx = (event.sourceEvent.offsetX - t.x) / t.k;
          const my = (event.sourceEvent.offsetY - t.y) / t.k;
          treeState.dragLine.attr('x2', mx).attr('y2', my);
        }
      })
      .on('end', function(event) {
        if (treeState.dragLine) {
          treeState.dragLine.remove();
          treeState.dragLine = null;
        }
        // Find drop target
        const t = d3.zoomTransform(svg.node());
        const mx = (event.sourceEvent.offsetX - t.x) / t.k;
        const my = (event.sourceEvent.offsetY - t.y) / t.k;
        let targetUid = null;
        nodes.forEach(tn => {
          const tp = positions[tn.uid];
          if (!tp) return;
          if (mx >= tp.x - 55 && mx <= tp.x + 55 && my >= tp.y - 18 && my <= tp.y + 18) {
            targetUid = tn.uid;
          }
        });
        if (targetUid && targetUid !== treeState.dragSource) {
          createTreeLink(treeState.dragSource, targetUid);
        }
        treeState.dragSource = null;
      })
    );
  });

  // Click empty space to deselect
  svg.on('click', () => {
    document.getElementById('tree-detail-panel').style.display = 'none';
    hideTreeContextMenu();
  });

  // Auto-fit: zoom to fit all nodes
  if (nodes.length > 0) {
    const xs = nodes.map(n => positions[n.uid]?.x).filter(Boolean);
    const ys = nodes.map(n => positions[n.uid]?.y).filter(Boolean);
    const minX = Math.min(...xs) - 80;
    const maxX = Math.max(...xs) + 80;
    const minY = Math.min(...ys) - 40;
    const maxY = Math.max(...ys) + 40;
    const bw = maxX - minX;
    const bh = maxY - minY;
    const scale = Math.min(width / bw, height / bh, 1.5) * 0.9;
    const tx = (width - bw * scale) / 2 - minX * scale;
    const ty = (height - bh * scale) / 2 - minY * scale;
    svg.call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
  }
}

function selectTreeNode(uid, graphData) {
  hideTreeContextMenu();
  const panel = document.getElementById('tree-detail-panel');
  const node = graphData.nodes.find(n => n.uid === uid);
  if (!node) return;

  // Find parents and children from edges
  const parents = graphData.edges.filter(e => e.child === uid).map(e => {
    const pn = graphData.nodes.find(n => n.uid === e.parent);
    return { uid: e.parent, suspect: e.suspect, header: pn ? pn.header : '' };
  });
  const children = graphData.edges.filter(e => e.parent === uid).map(e => {
    const cn = graphData.nodes.find(n => n.uid === e.child);
    return { uid: e.child, suspect: e.suspect, header: cn ? cn.header : '' };
  });

  // Build list of all items NOT currently linked for add-link dropdown
  const allParentUids = new Set(parents.map(p => p.uid));

  panel.style.display = 'block';
  panel.innerHTML = `
    <div class="tree-detail-header">
      <span class="tree-tag" style="background:${prefixColor(node.prefix)}">${h(node.prefix)}</span>
      <strong>${h(uid)}</strong> ${h(node.header || '')}
      ${node.suspect ? '<span class="tree-tag tree-tag-suspect">suspect</span>' : ''}
      ${node.reviewed ? '<span class="tree-tag tree-tag-reviewed">reviewed</span>' : ''}
      <div class="tree-detail-actions">
        <button class="tree-btn tree-btn-sm" onclick="treeState.selectedNode='${uid}';location.hash='#/tree/${uid}'">中心に設定</button>
        <button class="tree-btn tree-btn-sm" onclick="location.hash='#/item/${uid}'">詳細を開く</button>
      </div>
    </div>
    <div class="tree-detail-links">
      <div class="tree-detail-col">
        <h4>親リンク (${parents.length})</h4>
        ${parents.length === 0 ? '<span class="tree-dim">なし</span>' :
          parents.map(p => `
            <div class="tree-link-item">
              <span class="tree-link-uid" onclick="treeState.selectedNode='${p.uid}';location.hash='#/tree/${p.uid}'">${h(p.uid)}</span>
              <span class="tree-dim">${h(p.header)}</span>
              ${p.suspect ? '<span class="tree-tag tree-tag-suspect">suspect</span>' : ''}
              <button class="tree-unlink-btn" title="リンク削除" onclick="removeTreeLink('${uid}','${p.uid}')">&times;</button>
            </div>
          `).join('')}
        <div class="tree-add-link-row">
          <input type="text" id="tree-add-parent-input" placeholder="親UID を入力..." class="tree-add-input">
          <button class="tree-btn tree-btn-sm" onclick="addTreeLinkFromInput('${uid}')">+ リンク追加</button>
        </div>
      </div>
      <div class="tree-detail-col">
        <h4>子リンク (${children.length})</h4>
        ${children.length === 0 ? '<span class="tree-dim">なし</span>' :
          children.map(c => `
            <div class="tree-link-item">
              <span class="tree-link-uid" onclick="treeState.selectedNode='${c.uid}';location.hash='#/tree/${c.uid}'">${h(c.uid)}</span>
              <span class="tree-dim">${h(c.header)}</span>
              ${c.suspect ? '<span class="tree-tag tree-tag-suspect">suspect</span>' : ''}
              <button class="tree-unlink-btn" title="リンク削除" onclick="removeTreeLink('${c.uid}','${uid}')">&times;</button>
            </div>
          `).join('')}
      </div>
    </div>
  `;
}

function showTreeContextMenu(event, childUid, parentUid) {
  hideTreeContextMenu();
  const menu = document.getElementById('tree-context-menu');
  menu.style.display = 'block';
  menu.style.left = event.pageX + 'px';
  menu.style.top = event.pageY + 'px';
  menu.innerHTML = `
    <div class="tree-ctx-item" onclick="removeTreeLink('${childUid}','${parentUid}')">
      リンク削除: ${h(childUid)} &rarr; ${h(parentUid)}
    </div>
    <div class="tree-ctx-item" onclick="treeState.selectedNode='${childUid}';location.hash='#/tree/${childUid}'">
      ${h(childUid)} を中心に表示
    </div>
    <div class="tree-ctx-item" onclick="treeState.selectedNode='${parentUid}';location.hash='#/tree/${parentUid}'">
      ${h(parentUid)} を中心に表示
    </div>
  `;

  // Close on click outside
  setTimeout(() => document.addEventListener('click', hideTreeContextMenu, { once: true }), 0);
}

function hideTreeContextMenu() {
  const menu = document.getElementById('tree-context-menu');
  if (menu) menu.style.display = 'none';
}

async function createTreeLink(sourceUid, targetUid) {
  // sourceUid = child (drag from), targetUid = parent (drop to)
  // Confirm direction with user
  const childUid = sourceUid;
  const parentUid = targetUid;
  if (!confirm(`リンクを作成しますか?\n${childUid} → ${parentUid} (子→親)`)) return;
  try {
    const res = await API.post(`/api/items/${childUid}/link`, { parent: parentUid });
    if (res.ok) {
      toast('リンクを作成しました', 'success');
      // Re-render
      if (treeState.selectedNode) {
        location.hash = '#/tree/' + treeState.selectedNode;
        renderTreeGraph(treeState.selectedNode);
      } else {
        renderTreeGraph('');
      }
    } else {
      toast(res.error || 'エラーが発生しました', 'error');
    }
  } catch (e) {
    toast('リンク作成に失敗しました: ' + e.message, 'error');
  }
}

async function removeTreeLink(childUid, parentUid) {
  hideTreeContextMenu();
  if (!confirm(`リンクを削除しますか?\n${childUid} → ${parentUid}`)) return;
  try {
    const res = await API.post(`/api/items/${childUid}/unlink`, { parent: parentUid });
    if (res.ok) {
      toast('リンクを削除しました', 'success');
      if (treeState.selectedNode) {
        renderTreeGraph(treeState.selectedNode);
      } else {
        renderTreeGraph('');
      }
    } else {
      toast(res.error || 'エラーが発生しました', 'error');
    }
  } catch (e) {
    toast('リンク削除に失敗しました: ' + e.message, 'error');
  }
}

async function addTreeLinkFromInput(childUid) {
  const input = document.getElementById('tree-add-parent-input');
  const parentUid = input.value.trim();
  if (!parentUid) return;
  await createTreeLink(childUid, parentUid);
}

// ===================================================================
// Refresh current view after mutation
// ===================================================================
async function refreshCurrentView() {
  // Re-fetch sidebar group counts
  loadGroupNav();

  // Re-render current view
  switch (currentView) {
    case 'dashboard': renderDashboard(); break;
    case 'matrix':
      matrixData = await API.get('/api/matrix');
      renderMatrixView();
      break;
    case 'group': renderGroup(decodeURIComponent(currentParam)); break;
    case 'document': renderDocument(decodeURIComponent(currentParam)); break;
    case 'tree': renderTreeGraph(decodeURIComponent(currentParam)); break;
    case 'validation': renderValidation(); break;
  }
}

// ===================================================================
// Init
// ===================================================================
(async function init() {
  await loadGroupNav();
  route();
})();
