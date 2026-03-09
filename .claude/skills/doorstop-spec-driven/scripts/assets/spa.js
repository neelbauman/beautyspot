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

function toast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast toast-' + (type || 'success');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// ===================================================================
// Rich Editor (TipTap) — CDN loader with offline fallback
// ===================================================================
let richEditorReady = false;
let RichEditor = {};
(async () => {
  const timeout = (ms) => new Promise((_, r) => setTimeout(() => r(new Error('timeout')), ms));
  try {
    const [coreMod, skMod, tdMod] = await Promise.race([
      Promise.all([
        import('https://esm.sh/@tiptap/core@2'),
        import('https://esm.sh/@tiptap/starter-kit@2'),
        import('https://esm.sh/turndown@7'),
      ]),
      timeout(5000),
    ]);
    RichEditor = {
      Editor: coreMod.Editor,
      Extension: coreMod.Extension,
      StarterKit: skMod.StarterKit || skMod.default,
      TurndownService: tdMod.default || tdMod,
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

function statusTags(reviewed, suspect) {
  let s = '';
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
  const navKey = view === 'group' ? null : view === 'dashboard' ? 'dashboard' : view;
  if (navKey) {
    const el = document.querySelector(`[data-nav="${navKey}"]`);
    if (el) el.classList.add('active');
  }
  if (view === 'group') {
    document.querySelectorAll('#group-nav-list a').forEach(a => {
      a.classList.toggle('active', a.dataset.group === decodeURIComponent(param));
    });
  }

  closeItemPanel();

  switch (view) {
    case 'dashboard': renderDashboard(); break;
    case 'matrix': renderMatrix(); break;
    case 'group': renderGroup(decodeURIComponent(param)); break;
    case 'validation': renderValidation(); break;
    default: renderDashboard();
  }
}

window.addEventListener('hashchange', route);

// ===================================================================
// Sidebar group list
// ===================================================================
async function loadGroupNav() {
  const groups = await API.get('/api/groups');
  const list = document.getElementById('group-nav-list');
  list.innerHTML = Object.entries(groups).map(([name, info]) =>
    `<li><a href="#/group/${encodeURIComponent(name)}" data-group="${h(name)}">${h(name)} <span class="group-badge">${info.items}</span></a></li>`
  ).join('');
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
    <div class="page-title">Dashboard</div>
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
}

// --- Matrix ---
let matrixData = null;
let matrixFilters = { groups: new Set(), statuses: new Set(), query: '', sortCol: -1, sortDir: 'asc' };

function naturalCompare(a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

async function renderMatrix() {
  $main().innerHTML = '<div class="loading">Loading...</div>';
  matrixData = await API.get('/api/matrix');
  matrixFilters = { groups: new Set(), statuses: new Set(), query: '', sortCol: -1, sortDir: 'asc' };
  renderMatrixView();
}

function renderMatrixView() {
  if (!matrixData) return;
  const prev = document.activeElement;
  const hadSearchFocus = prev && prev.classList.contains('search-input');
  const cursorPos = hadSearchFocus ? prev.selectionStart : 0;
  const { prefixes, rows } = matrixData;

  const allGroups = [...new Set(rows.map(r => r.group))].sort();
  const groupPills = allGroups.map(g =>
    `<span class="pill ${matrixFilters.groups.has(g)?'active':''}" onclick="toggleMatrixGroup('${h(g)}')">${h(g)}</span>`
  ).join('');

  const statusPills = ['reviewed','unreviewed','suspect'].map(s =>
    `<span class="pill ${matrixFilters.statuses.has(s)?'active':''}" onclick="toggleMatrixStatus('${s}')">${s==='reviewed'?'&#x2713; Reviewed':s==='unreviewed'?'&#x25CB; Unreviewed':'&#x26A0; Suspect'}</span>`
  ).join('');

  const sortArrowHtml = (colIdx) => {
    const active = matrixFilters.sortCol === colIdx;
    const arrow = active ? (matrixFilters.sortDir === 'asc' ? '&#x25B2;' : '&#x25BC;') : '&#x25B2;&#x25BC;';
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
    if (matrixFilters.groups.size > 0 && !matrixFilters.groups.has(row.group)) return false;
    if (matrixFilters.statuses.size > 0 && !row.statuses.some(s => matrixFilters.statuses.has(s))) return false;
    if (matrixFilters.query) {
      const q = matrixFilters.query.toUpperCase();
      if (!row.uids.some(u => u.toUpperCase().includes(q))) return false;
    }
    return true;
  });

  // Sort rows
  if (matrixFilters.sortCol >= 0) {
    const col = matrixFilters.sortCol;
    filtered.sort((a, b) => {
      let aKey, bKey;
      if (col === 0) {
        aKey = a.group || '';
        bKey = b.group || '';
      } else {
        const prefix = prefixes[col - 1];
        aKey = a.cells[prefix]?.uid || '';
        bKey = b.cells[prefix]?.uid || '';
      }
      const cmp = naturalCompare(aKey, bKey);
      return matrixFilters.sortDir === 'asc' ? cmp : -cmp;
    });
  }

  let bodyRows = '';
  for (const row of filtered) {
    let cells = `<td><span class="tag tag-group">${h(row.group)}</span></td>`;
    for (const prefix of prefixes) {
      const cell = row.cells[prefix];
      if (cell) {
        const cellCls = cell.suspect ? 'cell-suspect' : (!cell.reviewed ? 'cell-unreviewed' : '');
        const refHtml = cell.ref ? `<br><span class="tag tag-ref">${h(cell.ref)}</span>` : '';
        cells += `<td class="${cellCls}" data-uid="${cell.uid}">
          <span class="cell-uid" onclick="handleCellClick(event,'${cell.uid}')">${h(cell.uid)}</span>
          ${statusIcons(cell.reviewed, cell.suspect)}
          <span class="text-preview">${h(cell.text_preview)}</span>
          ${refHtml}
        </td>`;
      } else {
        cells += '<td class="empty">&#8212;</td>';
      }
    }
    bodyRows += `<tr>${cells}</tr>`;
  }

  $main().innerHTML = `
    <div class="page-title">Traceability Matrix</div>
    <div class="page-subtitle">&#x2713;=Reviewed  &#x25CB;=Unreviewed  &#x26A0;=Suspect &mdash; Click UID for detail</div>

    <div class="filter-bar">
      <label>Group:</label>
      <span class="pill ${matrixFilters.groups.size===0?'active':''}" onclick="clearMatrixGroups()">All</span>
      ${groupPills}
    </div>
    <div class="filter-bar">
      <label>Status:</label>
      ${statusPills}
      <label style="margin-left:12px">ID:</label>
      <input class="search-input" type="text" placeholder="e.g. SPEC001" value="${h(matrixFilters.query)}" oninput="matrixFilters.query=this.value;renderMatrixView()">
    </div>

    <table>
      <tr>${headerCells}</tr>
      ${bodyRows || '<tr><td colspan="'+(prefixes.length+1)+'" class="empty">No matching items</td></tr>'}
    </table>
  `;
  if (hadSearchFocus) {
    const inp = $main().querySelector('.search-input');
    if (inp) { inp.focus(); inp.setSelectionRange(cursorPos, cursorPos); }
  }
}

function toggleMatrixGroup(g) {
  if (matrixFilters.groups.has(g)) matrixFilters.groups.delete(g);
  else matrixFilters.groups.add(g);
  renderMatrixView();
}
function clearMatrixGroups() {
  matrixFilters.groups.clear();
  renderMatrixView();
}
function toggleMatrixStatus(s) {
  if (matrixFilters.statuses.has(s)) matrixFilters.statuses.delete(s);
  else matrixFilters.statuses.add(s);
  renderMatrixView();
}
function toggleMatrixSort(colIdx) {
  if (matrixFilters.sortCol === colIdx) {
    matrixFilters.sortDir = matrixFilters.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    matrixFilters.sortCol = colIdx;
    matrixFilters.sortDir = 'asc';
  }
  renderMatrixView();
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
    let cells = `<td><span class="tag tag-group">${h(row.group)}</span></td>`;
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
        ${statusTags(item.reviewed, item.suspect)}
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
  const main = document.getElementById('main');
  const count = activePanels.length;
  if (count > 0) {
    main.style.marginRight = (count * 520) + 'px';
  } else {
    main.style.marginRight = '';
  }
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
        <span class="tag tag-prefix">${h(data.prefix)}</span>
        <span class="tag tag-group">${h(data.group)}</span>
      </div>
      <button class="panel-close" onclick="closePanel(${pid})">&times;</button>
    </div>

    <div style="margin-bottom:12px">${statusTags(data.reviewed, data.suspect)}</div>

    <div id="ptv-${pid}" class="item-text">${data.text_html}</div>
    <div id="pte-${pid}" class="hidden">
      <textarea id="pta-${pid}" class="editor-area">${h(data.text)}</textarea>
      <div id="prich-${pid}" class="tiptap-wrap hidden"></div>
      <div class="actions" style="margin-top:8px">
        <button class="btn btn-primary" id="psb-${pid}" onclick="panelSave(${pid})">Save</button>
        <button class="btn" onclick="panelCancelEdit(${pid})">Cancel</button>
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
      return { 'Tab': () => true, 'Shift-Tab': () => true };
    },
  });
  const editor = new RichEditor.Editor({
    element: document.getElementById('ptip-' + panelId),
    extensions: [RichEditor.StarterKit, TabHandler],
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
    const htmlContent = document.getElementById('ptv-' + panelId).innerHTML;
    ps.editor = createTiptapEditor(panelId, htmlContent);
    ps.useRich = true;
    ps.editor.commands.focus('end');
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
  const btn = document.getElementById('psb-' + panelId);
  btn.disabled = true; btn.textContent = 'Saving...';
  try {
    const res = await API.post('/api/items/' + ps.uid + '/edit', { text });
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
    case 'group': renderGroup(currentParam); break;
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
