// actions.js — Shared CRUD operations: review, clear, edit, save

async function doReview(uid) {
  const btn = document.querySelector('[data-uid="'+uid+'"] .review-btn');
  btn.disabled = true; btn.textContent = '処理中...';
  try {
    const res = await fetch('/api/review/' + uid, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      const detail = document.getElementById('detail-' + uid);
      const badge = detail.querySelector('.status-badge');
      if (badge) {
        const old = badge.querySelectorAll('.suspect, .unreviewed, .reviewed');
        old.forEach(b => b.remove());
        const nb = document.createElement('span');
        nb.className = 'reviewed'; nb.textContent = '✓ レビュー済';
        badge.insertBefore(nb, badge.firstChild);
      }
      btn.textContent = '✓ Review済';
      showToast(uid + ' をレビュー済にしました');
    } else {
      btn.textContent = 'Review'; btn.disabled = false;
      showToast('エラー: ' + data.error, 'error');
    }
  } catch(e) {
    btn.textContent = 'Review'; btn.disabled = false;
    showToast('通信エラー: ' + e.message, 'error');
  }
}

async function doClear(uid) {
  const btn = document.querySelector('[data-uid="'+uid+'"] .clear-btn');
  btn.disabled = true; btn.textContent = '処理中...';
  try {
    const res = await fetch('/api/clear/' + uid, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      const detail = document.getElementById('detail-' + uid);
      const suspectBadge = detail.querySelector('.suspect');
      if (suspectBadge) suspectBadge.remove();
      btn.textContent = '✓ Clear済';
      showToast(uid + ' のsuspectリンクを解消しました');
    } else {
      btn.textContent = 'Clear'; btn.disabled = false;
      showToast('エラー: ' + data.error, 'error');
    }
  } catch(e) {
    btn.textContent = 'Clear'; btn.disabled = false;
    showToast('通信エラー: ' + e.message, 'error');
  }
}

function startEdit(uid) {
  document.querySelector('.item-text[data-uid="'+uid+'"]').classList.add('hidden');
  document.querySelector('.item-editor[data-uid="'+uid+'"]').classList.remove('hidden');
  const ta = document.querySelector('.edit-textarea[data-uid="'+uid+'"]');
  ta.focus();
  ta.style.height = 'auto';
  ta.style.height = Math.max(120, ta.scrollHeight + 4) + 'px';
}

function cancelEdit(uid) {
  document.querySelector('.item-editor[data-uid="'+uid+'"]').classList.add('hidden');
  document.querySelector('.item-text[data-uid="'+uid+'"]').classList.remove('hidden');
}

async function doSave(uid) {
  const ta = document.querySelector('.edit-textarea[data-uid="'+uid+'"]');
  const btn = document.querySelector('.item-editor[data-uid="'+uid+'"] .save-btn');
  btn.disabled = true; btn.textContent = '保存中...';
  try {
    const res = await fetch('/api/edit/' + uid, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: ta.value })
    });
    const data = await res.json();
    if (data.ok) {
      const textDiv = document.querySelector('.item-text[data-uid="'+uid+'"]');
      textDiv.innerHTML = data.html || ('<p>' + ta.value.replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/\n/g,'<br>') + '</p>');
      const detail = document.getElementById('detail-' + uid);
      const oldBadges = detail.querySelectorAll('.reviewed, .unreviewed');
      oldBadges.forEach(b => b.remove());
      const statusContainer = detail.querySelector('.status-badge');
      if (statusContainer) {
        const nb = document.createElement('span');
        nb.className = 'unreviewed'; nb.textContent = '○ 未レビュー';
        statusContainer.appendChild(nb);
      }
      cancelEdit(uid);
      btn.textContent = '保存'; btn.disabled = false;
      showToast(uid + ' のテキストを更新しました');
    } else {
      btn.textContent = '保存'; btn.disabled = false;
      showToast('エラー: ' + data.error, 'error');
    }
  } catch(e) {
    btn.textContent = '保存'; btn.disabled = false;
    showToast('通信エラー: ' + e.message, 'error');
  }
}
