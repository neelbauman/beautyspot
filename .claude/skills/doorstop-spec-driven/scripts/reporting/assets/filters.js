// filters.js — Main report only: group/status filtering, matrix sorting, detail sorting

let activeGroups = new Set();
let activeStatuses = new Set();

function toggleGroup(btn) {
  const group = btn.dataset.group;
  const allBtn = document.querySelector('[data-group="__all__"]');
  if (activeGroups.has(group)) { activeGroups.delete(group); btn.classList.remove('active'); }
  else { activeGroups.add(group); btn.classList.add('active'); allBtn.classList.remove('active'); }
  if (activeGroups.size === 0) { showAllGroups(); return; }
  applyFilters();
}

function showAllGroups() {
  activeGroups.clear();
  document.querySelectorAll('.group-btn').forEach(b => b.classList.remove('active'));
  document.querySelector('[data-group="__all__"]').classList.add('active');
  applyFilters();
}

function toggleStatus(btn) {
  const status = btn.dataset.status;
  if (activeStatuses.has(status)) { activeStatuses.delete(status); btn.classList.remove('active'); }
  else { activeStatuses.add(status); btn.classList.add('active'); }
  applyFilters();
}

function naturalCompare(a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

let currentSortCol = -1;
let currentSortDir = 'asc';

function sortMatrix(colIndex) {
  if (currentSortCol === colIndex) {
    currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
  } else {
    currentSortCol = colIndex;
    currentSortDir = 'asc';
  }
  const table = document.getElementById('matrix-table');
  const rows = Array.from(table.querySelectorAll('tr[data-groups]'));
  rows.sort((a, b) => {
    const aKey = a.cells[colIndex]?.dataset.sortKey || '';
    const bKey = b.cells[colIndex]?.dataset.sortKey || '';
    const cmp = naturalCompare(aKey, bKey);
    return currentSortDir === 'asc' ? cmp : -cmp;
  });
  const tbody = rows[0]?.parentNode;
  if (tbody) rows.forEach(r => tbody.appendChild(r));

  table.querySelectorAll('th.sortable').forEach(th => {
    th.classList.remove('sort-active');
    th.querySelector('.sort-arrow').textContent = '▲▼';
  });
  const activeHeader = table.querySelector(`th[data-col="${colIndex}"]`);
  if (activeHeader) {
    activeHeader.classList.add('sort-active');
    activeHeader.querySelector('.sort-arrow').textContent = currentSortDir === 'asc' ? '▲' : '▼';
  }
}

function sortDetails() {
  const sel = document.getElementById('detail-sort-select').value;
  const [field, dir] = sel.split('-');
  const details = Array.from(document.querySelectorAll('.item-detail'));
  details.sort((a, b) => {
    let aKey, bKey;
    if (field === 'uid') {
      aKey = a.dataset.uid || '';
      bKey = b.dataset.uid || '';
    } else {
      aKey = a.dataset.groups || '';
      bKey = b.dataset.groups || '';
      if (aKey === bKey) {
        aKey = a.dataset.uid || '';
        bKey = b.dataset.uid || '';
      }
    }
    const cmp = naturalCompare(aKey, bKey);
    return dir === 'asc' ? cmp : -cmp;
  });
  const sortDiv = document.querySelector('.detail-sort');
  let insertPoint = sortDiv;
  details.forEach(d => {
    insertPoint.after(d);
    insertPoint = d;
  });
}

function applyFilters() {
  const idQuery = document.getElementById('id-search').value.trim().toUpperCase();

  // Matrix rows
  document.querySelectorAll('#matrix-table tr[data-groups]').forEach(row => {
    let show = true;
    const groups = (row.dataset.groups || '').split(' ').filter(Boolean);
    if (activeGroups.size > 0 && !groups.some(g => activeGroups.has(g))) show = false;
    if (show && activeStatuses.size > 0) {
      const rowStatuses = (row.dataset.statuses || '').split(' ');
      if (!rowStatuses.some(s => activeStatuses.has(s))) show = false;
    }
    if (show && idQuery) {
      const rowUids = (row.dataset.uids || '').toUpperCase();
      if (!idQuery.split(',').some(q => rowUids.includes(q.trim()))) show = false;
    }
    row.classList.toggle('hidden', !show);
  });

  // Item detail sections
  document.querySelectorAll('.item-detail').forEach(detail => {
    let show = true;
    const groups = (detail.dataset.groups || '').split(' ').filter(Boolean);
    if (activeGroups.size > 0 && !groups.some(g => activeGroups.has(g))) show = false;
    if (show && activeStatuses.size > 0) {
      const detailStatuses = (detail.dataset.statuses || '').split(' ');
      if (!detailStatuses.some(s => activeStatuses.has(s))) show = false;
    }
    if (show && idQuery) {
      const uid = (detail.dataset.uid || '').toUpperCase();
      if (!idQuery.split(',').some(q => uid.includes(q.trim()))) show = false;
    }
    detail.classList.toggle('hidden', !show);
  });

  // Coverage rows (group filter only)
  document.querySelectorAll('#coverage-table .coverage-group').forEach(row => {
    if (activeGroups.size === 0) row.classList.remove('hidden');
    else {
      const groups = (row.dataset.groups || '').split(' ').filter(Boolean);
      row.classList.toggle('hidden', !groups.some(g => activeGroups.has(g)));
    }
  });
  document.querySelectorAll('#coverage-table .coverage-total').forEach(row => {
    row.classList.remove('hidden');
  });
}
