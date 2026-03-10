// common.js — Shared: highlight, cell selection, toast, serve detection

function highlightItem(id) {
  document.querySelectorAll('.item-detail.highlighted').forEach(
    el => el.classList.remove('highlighted')
  );
  const el = document.getElementById(id);
  if (el) {
    el.classList.add('highlighted');
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

document.addEventListener('click', function(e) {
  const link = e.target.closest('a[href^="#detail-"]');
  if (link) {
    e.preventDefault();
    const id = link.getAttribute('href').substring(1);
    const uid = id.replace('detail-', '');
    history.replaceState(null, '', '#' + id);
    highlightItem(id);
    // Highlight the clicked cell in the matrix
    document.querySelectorAll('td.cell-selected').forEach(
      el => el.classList.remove('cell-selected')
    );
    const cell = document.querySelector('td[data-uid="' + uid + '"]');
    if (cell) cell.classList.add('cell-selected');
  }
});

window.addEventListener('hashchange', function() {
  const id = window.location.hash.substring(1);
  if (id.startsWith('detail-')) highlightItem(id);
});

if (window.location.hash && window.location.hash.startsWith('#detail-')) {
  setTimeout(function() { highlightItem(window.location.hash.substring(1)); }, 100);
}

// Serve mode: show action buttons if not file://
if (window.location.protocol !== 'file:') {
  document.querySelectorAll('.item-actions').forEach(el => el.style.display = 'block');
}

function showToast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast ' + (type || 'success');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}
