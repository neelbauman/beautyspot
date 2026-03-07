#!/usr/bin/env python3
"""局所トレーサビリティビュー生成スクリプト。

特定のアイテムUID・グループを起点に、関連するREQ→SPEC→IMPL/TSTチェーンだけを
抽出してコンパクトなHTMLページを生成する。全体レポートと異なり、レビュー対象の
アイテムだけに集中できる。

起点の指定方法:
  --uid UID [UID...]     アイテムUIDを直接指定（上流・下流を自動追跡）
  --group GROUP          グループ名で絞り込み
  --all                  グループごとに個別HTMLを生成

出力:
  --output-dir DIR       出力先ディレクトリ（default: ./reports/local）
  --json                 JSON形式でも出力

Usage:
    python local_trace_view.py <project-dir> --uid REQ001
    python local_trace_view.py <project-dir> --uid SPEC003 SPEC004
    python local_trace_view.py <project-dir> --group CACHE
    python local_trace_view.py <project-dir> --all
"""

import argparse
import html
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

try:
    import doorstop
except ImportError:
    print("ERROR: doorstop がインストールされていません。", file=sys.stderr)
    sys.exit(1)

try:
    import markdown as _md

    def render_markdown(text):
        return _md.markdown(text, extensions=["tables", "fenced_code"])
except ImportError:
    def render_markdown(text):
        return f"<p>{html.escape(text)}</p>"


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def get_group(item):
    try:
        g = item.get("group")
        return g if g else "(未分類)"
    except (AttributeError, KeyError):
        return "(未分類)"


def get_ref(item):
    try:
        return item.ref or ""
    except (AttributeError, KeyError):
        return ""


def find_item(tree, uid_str):
    for doc in tree:
        try:
            return doc.find_item(uid_str)
        except Exception:
            continue
    return None


def find_doc_prefix(tree, item):
    for doc in tree:
        try:
            doc.find_item(str(item.uid))
            return doc.prefix
        except Exception:
            continue
    return "?"


def detect_suspect_uids(tree):
    """suspectリンクを持つアイテムのUIDセットを返す。"""
    suspect = set()
    for doc in tree:
        for item in doc:
            for link in item.links:
                parent = find_item(tree, str(link))
                if parent is None:
                    continue
                if (
                    link.stamp is not None
                    and link.stamp != ""
                    and link.stamp != parent.stamp()
                ):
                    suspect.add(str(item.uid))
                    break
    return suspect


# ---------------------------------------------------------------------------
# Link index
# ---------------------------------------------------------------------------

def build_link_index(tree):
    """children[parent_uid] = [child_item, ...]
       parents[child_uid]   = [parent_item, ...]
    """
    children = defaultdict(list)
    parents = defaultdict(list)
    for doc in tree:
        for item in doc:
            for link in item.links:
                uid_str = str(link)
                parent_item = find_item(tree, uid_str)
                if parent_item:
                    children[uid_str].append(item)
                    parents[str(item.uid)].append(parent_item)
    return children, parents


# ---------------------------------------------------------------------------
# Chain extraction
# ---------------------------------------------------------------------------

def trace_full_chain(uid, children_idx, parents_idx, tree):
    """指定UIDから上流・下流をすべてたどり、関連UIDの集合を返す。"""
    related = set()
    visited_up = set()
    visited_down = set()

    def go_up(u):
        if u in visited_up:
            return
        visited_up.add(u)
        related.add(u)
        for p in parents_idx.get(u, []):
            go_up(str(p.uid))

    def go_down(u):
        if u in visited_down:
            return
        visited_down.add(u)
        related.add(u)
        for c in children_idx.get(u, []):
            go_down(str(c.uid))

    go_up(uid)
    go_down(uid)
    return related


def collect_chains_by_uid(tree, uids, children_idx, parents_idx):
    """複数のUIDを起点にして、関連チェーン全体のUID集合を返す。"""
    all_related = set()
    for uid in uids:
        item = find_item(tree, uid)
        if item is None:
            print(f"WARNING: UID '{uid}' が見つかりません。", file=sys.stderr)
            continue
        all_related |= trace_full_chain(uid, children_idx, parents_idx, tree)
    return all_related


def collect_chains_by_group(tree, group):
    """指定グループに属する全アイテムのUID集合を返す。"""
    uids = set()
    for doc in tree:
        for item in doc:
            if get_group(item) == group:
                uids.add(str(item.uid))
    return uids


def get_all_groups(tree):
    return sorted({get_group(item) for doc in tree for item in doc})


# ---------------------------------------------------------------------------
# Traceability matrix (local)
# ---------------------------------------------------------------------------

def build_local_matrix(tree, related_uids):
    """related_uidsに含まれるアイテムだけでトレーサビリティマトリクスを構築する。"""
    docs = list(tree)
    prefixes = [d.prefix for d in docs]

    # related_uids に含まれるアイテムだけ取得
    items_by_prefix = defaultdict(list)
    for doc in docs:
        for item in doc:
            if str(item.uid) in related_uids:
                items_by_prefix[doc.prefix].append(item)

    # ルートドキュメントから行を構築
    root_docs = [d for d in docs if not d.parent]
    matrix = []
    for root_doc in root_docs:
        for item in items_by_prefix.get(root_doc.prefix, []):
            row = {root_doc.prefix: item, "_group": get_group(item)}
            matrix.append(row)

    def expand_children(doc, parent_prefix):
        child_docs = [d for d in docs if d.parent == doc.prefix]
        for child_doc in child_docs:
            link_map = defaultdict(list)
            for child_item in items_by_prefix.get(child_doc.prefix, []):
                for link in child_item.links:
                    link_str = str(link)
                    if link_str.startswith(parent_prefix):
                        link_map[link_str].append(child_item)

            new_rows = []
            for row in matrix:
                parent_item = row.get(parent_prefix)
                if parent_item and str(parent_item.uid) in link_map:
                    children = link_map[str(parent_item.uid)]
                    for i, child in enumerate(children):
                        if i == 0:
                            row[child_doc.prefix] = child
                        else:
                            new_row = dict(row)
                            new_row[child_doc.prefix] = child
                            new_rows.append(new_row)
            matrix.extend(new_rows)
            expand_children(child_doc, child_doc.prefix)

    for root_doc in root_docs:
        expand_children(root_doc, root_doc.prefix)

    return matrix, prefixes


# ---------------------------------------------------------------------------
# Coverage (local)
# ---------------------------------------------------------------------------

def compute_local_coverage(tree, related_uids):
    """related_uidsに限定したカバレッジを計算する。"""
    docs = {doc.prefix: doc for doc in tree}
    coverage = {}

    for doc in tree:
        if not doc.parent or doc.parent not in docs:
            continue
        parent_doc = docs[doc.parent]

        # 対象のみ
        parent_uids = {str(i.uid) for i in parent_doc if str(i.uid) in related_uids}
        if not parent_uids:
            continue

        covered = set()
        for item in doc:
            if str(item.uid) not in related_uids:
                continue
            for link in item.links:
                if str(link) in parent_uids:
                    covered.add(str(link))

        total = len(parent_uids)
        pct = (len(covered) / total * 100) if total > 0 else 0.0
        uncovered = sorted(parent_uids - covered)
        coverage[f"{doc.prefix} → {doc.parent}"] = {
            "total": total,
            "covered": len(covered),
            "uncovered": total - len(covered),
            "percentage": round(pct, 1),
            "uncovered_items": uncovered,
        }

    return coverage


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def _color(pct):
    if pct == 100:
        return "#4caf50"
    elif pct >= 50:
        return "#ff9800"
    else:
        return "#f44336"


def generate_local_html(tree, related_uids, label, output_path, back_link=None):
    """局所トレーサビリティビューのHTMLを生成する。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    h = html.escape
    suspect_uids = detect_suspect_uids(tree)

    # children map for detail section
    children_map = defaultdict(list)
    for doc in tree:
        for item in doc:
            if str(item.uid) not in related_uids:
                continue
            for link in item.links:
                children_map[str(link)].append(str(item.uid))

    # Stats
    local_items = []
    for doc in tree:
        for item in doc:
            if str(item.uid) in related_uids:
                local_items.append((item, doc.prefix))
    total = len(local_items)
    reviewed = sum(
        1 for item, _ in local_items
        if item.reviewed
    )
    suspects_in_view = sum(
        1 for item, _ in local_items if str(item.uid) in suspect_uids
    )
    groups_in_view = sorted({get_group(item) for item, _ in local_items})
    doc_counts = defaultdict(int)
    for item, prefix in local_items:
        doc_counts[prefix] += 1

    # Matrix
    matrix, prefixes = build_local_matrix(tree, related_uids)

    # Coverage
    coverage = compute_local_coverage(tree, related_uids)

    # --- Build HTML pieces ---

    # Summary cards for doc types
    doc_count_cards = ""
    for p in prefixes:
        if doc_counts.get(p, 0) > 0:
            doc_count_cards += f"""
      <div class="card">
        <h3>{h(p)}</h3>
        <div class="value">{doc_counts[p]}</div>
      </div>"""

    # Coverage rows
    coverage_rows = ""
    for pair, data in coverage.items():
        color = _color(data["percentage"])
        uncov = ", ".join(data["uncovered_items"]) if data["uncovered_items"] else "—"
        coverage_rows += f"""
        <tr>
          <td>{h(pair)}</td>
          <td>{data['covered']} / {data['total']}</td>
          <td style="color:{color}; font-weight:bold">{data['percentage']}%</td>
          <td style="font-size:0.85em">{h(uncov)}</td>
        </tr>"""

    # Matrix rows
    header_cells = "<th>グループ</th>" + "".join(f"<th>{h(p)}</th>" for p in prefixes)
    matrix_rows = ""
    for row in matrix:
        group = h(row.get("_group", "(未分類)"))
        cells = f'<td><span class="group-tag">{group}</span></td>'
        for prefix in prefixes:
            item = row.get(prefix)
            if item:
                uid_str = str(item.uid)
                text_preview = item.text[:80] + ("..." if len(item.text) > 80 else "")
                ref = get_ref(item)
                ref_html = f'<br><span class="ref-tag">{h(ref)}</span>' if ref else ""
                is_suspect = uid_str in suspect_uids
                is_reviewed = bool(item.reviewed)
                status_icons = ""
                if is_suspect:
                    status_icons += '<span class="suspect">⚠</span>'
                if is_reviewed:
                    status_icons += '<span class="reviewed">✓</span>'
                else:
                    status_icons += '<span class="unreviewed">○</span>'
                cells += (
                    f'<td>'
                    f'<a href="#detail-{h(uid_str)}" style="text-decoration:none; color:inherit">'
                    f'<strong>{h(uid_str)}</strong></a> '
                    f'{status_icons}'
                    f'<br><span class="text-preview">{h(text_preview)}</span>'
                    f'{ref_html}</td>'
                )
            else:
                cells += '<td class="empty">—</td>'
        matrix_rows += f'<tr data-group="{group}">{cells}</tr>'

    # Detail cards
    detail_section = ""
    for doc in tree:
        for item in doc:
            uid_str = str(item.uid)
            if uid_str not in related_uids:
                continue
            is_suspect = uid_str in suspect_uids
            is_reviewed = bool(item.reviewed)
            badge = ""
            if is_suspect:
                badge += '<span class="suspect">⚠ Suspect</span> '
            if is_reviewed:
                badge += '<span class="reviewed">✓ レビュー済</span>'
            else:
                badge += '<span class="unreviewed">○ 未レビュー</span>'
            ref = get_ref(item)
            ref_line = (
                f'<p><strong>ref:</strong> <span class="ref-tag">{h(ref)}</span></p>'
                if ref else ""
            )
            group = get_group(item)
            parent_links = []
            for link in item.links:
                link_str = str(link)
                parent_item = find_item(tree, link_str)
                if parent_item and not parent_item.reviewed:
                    parent_links.append(
                        f'<a href="#detail-{h(link_str)}" class="link-unreviewed">{h(link_str)}</a>'
                        f' <span class="link-unreviewed-label">(未レビュー)</span>'
                    )
                else:
                    parent_links.append(
                        f'<a href="#detail-{h(link_str)}">{h(link_str)}</a>'
                    )
            parents_str = ", ".join(parent_links) if parent_links else "—"
            child_uids = children_map.get(uid_str, [])
            child_links = []
            for c in sorted(child_uids):
                if c in suspect_uids:
                    child_links.append(
                        f'<a href="#detail-{h(c)}" class="link-suspect">{h(c)}</a>'
                        f' <span class="link-suspect-label">(suspect)</span>'
                    )
                else:
                    child_links.append(
                        f'<a href="#detail-{h(c)}">{h(c)}</a>'
                    )
            children_str = ", ".join(child_links) if child_links else "—"
            text_html = render_markdown(item.text)
            raw_text = item.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            detail_section += f"""
    <div class="item-detail" id="detail-{h(uid_str)}" data-uid="{h(uid_str)}">
      <h3>{h(uid_str)}
        <span class="prefix-tag">{h(doc.prefix)}</span>
        <span class="group-tag">{h(group)}</span>
        <span class="status-badge">{badge}</span>
      </h3>
      <div class="item-text" data-uid="{h(uid_str)}">{text_html}</div>
      <div class="item-editor hidden" data-uid="{h(uid_str)}">
        <textarea class="edit-textarea" data-uid="{h(uid_str)}">{raw_text}</textarea>
        <div class="edit-actions">
          <button class="action-btn save-btn" onclick="doSave('{h(uid_str)}')">保存</button>
          <button class="action-btn cancel-btn" onclick="cancelEdit('{h(uid_str)}')">キャンセル</button>
        </div>
      </div>
      {ref_line}
      <p><strong>親:</strong> {parents_str}</p>
      <p><strong>子:</strong> {children_str}</p>
      <div class="item-actions" data-uid="{h(uid_str)}">
        <button class="action-btn edit-btn" onclick="startEdit('{h(uid_str)}')">Edit</button>
        <button class="action-btn review-btn" onclick="doReview('{h(uid_str)}')">Review</button>
        <button class="action-btn clear-btn" onclick="doClear('{h(uid_str)}')">Clear</button>
      </div>
    </div>"""

    # --- Assemble full HTML ---
    report = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>局所トレーサビリティ — {h(label)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1200px; margin: 0 auto; padding: 20px; background: #fafafa; }}
  h1 {{ border-bottom: 3px solid #00897b; padding-bottom: 10px; color: #00897b; }}
  h2 {{ color: #00897b; margin-top: 30px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; background: #fff; }}
  th {{ background: #00897b; color: #fff; padding: 10px; text-align: left; }}
  td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .text-preview {{ color: #666; font-size: 0.85em; }}
  .ref-tag {{ display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 1px 6px;
              border-radius: 3px; font-size: 0.75em; font-family: monospace; margin-top: 2px; }}
  .empty {{ color: #ccc; text-align: center; }}
  .reviewed {{ color: #4caf50; font-size: 0.8em; }}
  .unreviewed {{ color: #bdbdbd; font-size: 0.8em; }}
  .suspect {{ color: #e65100; font-size: 0.8em; font-weight: bold; }}
  .link-unreviewed {{ color: #9e9e9e; }}
  .link-unreviewed-label {{ color: #9e9e9e; font-size: 0.8em; }}
  .link-suspect {{ color: #e65100; }}
  .link-suspect-label {{ color: #e65100; font-size: 0.8em; font-weight: bold; }}
  .summary {{ display: flex; gap: 12px; margin: 15px 0; flex-wrap: wrap; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
           padding: 12px 18px; flex: 1; min-width: 80px; text-align: center; }}
  .card h3 {{ margin: 0 0 4px; font-size: 0.8em; color: #666; }}
  .card .value {{ font-size: 1.4em; font-weight: bold; color: #00897b; }}
  .timestamp {{ color: #999; font-size: 0.85em; }}
  .group-tag {{ display: inline-block; background: #e3f2fd; color: #1565c0; padding: 2px 8px;
                border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
  .prefix-tag {{ display: inline-block; background: #f3e5f5; color: #7b1fa2; padding: 2px 6px;
                 border-radius: 3px; font-size: 0.75em; }}
  .scope-label {{ display: inline-block; background: #e0f2f1; color: #00695c; padding: 4px 12px;
                  border-radius: 6px; font-size: 0.9em; font-weight: bold; margin-left: 10px; }}
  .item-detail {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
                  padding: 15px 20px; margin: 10px 0; }}
  .item-detail h3 {{ margin: 0 0 8px; font-size: 1.05em; }}
  .item-detail p {{ margin: 5px 0; color: #333; }}
  .item-detail a {{ color: #00897b; text-decoration: none; }}
  .item-detail a:hover {{ text-decoration: underline; }}
  .item-text {{ color: #333; line-height: 1.6; }}
  .item-text p {{ margin: 6px 0; }}
  .item-text code {{ background: #f5f5f5; padding: 1px 5px; border-radius: 3px;
                     font-size: 0.9em; font-family: monospace; }}
  .item-text pre {{ background: #f5f5f5; padding: 12px; border-radius: 6px;
                    overflow-x: auto; font-size: 0.85em; }}
  .item-text pre code {{ background: none; padding: 0; }}
  .item-text ul, .item-text ol {{ margin: 6px 0; padding-left: 24px; }}
  .item-text table {{ border-collapse: collapse; margin: 8px 0; }}
  .item-text table th, .item-text table td {{ border: 1px solid #ddd; padding: 6px 10px; }}
  .item-text table th {{ background: #f0f0f0; }}
  .back-nav {{ margin: 0 0 15px; padding: 8px 15px; background: #f5f5f5; border-radius: 8px;
               font-size: 0.85em; }}
  .back-nav a {{ color: #1a73e8; text-decoration: none; }}
  .back-nav a:hover {{ text-decoration: underline; }}
  .chain-nav {{ margin: 15px 0; padding: 10px 15px; background: #e0f2f1; border-radius: 8px;
                font-size: 0.9em; }}
  .chain-nav a {{ color: #00695c; text-decoration: none; margin: 0 6px; }}
  .chain-nav a:hover {{ text-decoration: underline; }}
  #matrix-table a:hover strong {{ text-decoration: underline; }}
  .item-detail {{ transition: border-color 0.3s, box-shadow 0.3s; }}
  .item-detail:target, .item-detail.highlighted {{
    border-color: #00897b;
    box-shadow: 0 0 0 3px rgba(0,137,123,0.2);
    animation: highlightFade 2s ease forwards;
  }}
  @keyframes highlightFade {{
    0% {{ background: #e0f2f1; }}
    100% {{ background: #fff; }}
  }}
  .item-actions {{ display: none; margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; }}
  .action-btn {{ padding: 6px 16px; border: 1px solid #ccc; border-radius: 6px;
                 background: #fff; cursor: pointer; font-size: 0.85em; margin-right: 8px;
                 transition: background 0.15s; }}
  .action-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .edit-btn {{ color: #1a73e8; border-color: #1a73e8; }}
  .edit-btn:hover:not(:disabled) {{ background: #e3f2fd; }}
  .review-btn {{ color: #4caf50; border-color: #4caf50; }}
  .review-btn:hover:not(:disabled) {{ background: #e8f5e9; }}
  .clear-btn {{ color: #e65100; border-color: #e65100; }}
  .clear-btn:hover:not(:disabled) {{ background: #fff3e0; }}
  .save-btn {{ color: #fff; background: #00897b; border-color: #00897b; }}
  .save-btn:hover:not(:disabled) {{ background: #00695c; }}
  .cancel-btn {{ color: #666; border-color: #999; }}
  .cancel-btn:hover {{ background: #f5f5f5; }}
  .item-editor {{ margin: 8px 0; }}
  .edit-textarea {{ width: 100%; min-height: 120px; padding: 10px; border: 1px solid #1a73e8;
                    border-radius: 6px; font-family: monospace; font-size: 0.9em;
                    line-height: 1.5; resize: vertical; box-sizing: border-box; }}
  .edit-textarea:focus {{ outline: none; box-shadow: 0 0 0 2px rgba(26,115,232,0.2); }}
  .edit-actions {{ margin-top: 8px; }}
  .hidden {{ display: none; }}
  .toast {{ position: fixed; bottom: 20px; right: 20px; padding: 12px 24px;
            border-radius: 8px; color: #fff; font-size: 0.9em; z-index: 1000;
            animation: toastFade 3s ease forwards; pointer-events: none; }}
  .toast.success {{ background: #4caf50; }}
  .toast.error {{ background: #d32f2f; }}
  @keyframes toastFade {{ 0% {{ opacity:0; transform:translateY(20px); }}
    10% {{ opacity:1; transform:translateY(0); }} 80% {{ opacity:1; }}
    100% {{ opacity:0; }} }}
  @media print {{
    body {{ max-width: 100%; padding: 10px; }}
    .chain-nav, .item-actions, .back-nav {{ display: none; }}
  }}
</style>
</head>
<body>
{f'<div class="back-nav"><a href="{back_link}">← 全体レポートに戻る</a></div>' if back_link else ''}
<h1>局所トレーサビリティビュー <span class="scope-label">{h(label)}</span></h1>
<p class="timestamp">生成日時: {now}</p>

<div class="summary">
  <div class="card">
    <h3>対象アイテム</h3>
    <div class="value">{total}</div>
  </div>
  {doc_count_cards}
  <div class="card">
    <h3>レビュー済</h3>
    <div class="value">{reviewed}/{total}</div>
  </div>
  <div class="card">
    <h3>Suspect</h3>
    <div class="value" style="color:{'#e65100' if suspects_in_view else '#4caf50'}">{suspects_in_view}</div>
  </div>
  <div class="card">
    <h3>グループ</h3>
    <div class="value">{', '.join(h(g) for g in groups_in_view)}</div>
  </div>
</div>

<div class="chain-nav">
  <strong>アイテム:</strong>
  {' '.join(f'<a href="#detail-{h(str(item.uid))}">{h(str(item.uid))}</a>' for item, _ in local_items)}
</div>

<h2>トレーサビリティマトリクス</h2>
<p style="font-size:0.85em; color:#888">✓=レビュー済 ○=未レビュー ⚠=Suspect（複数同時表示あり。IDクリックで詳細へ）</p>
<table id="matrix-table">
<tr>{header_cells}</tr>
{matrix_rows}
</table>

<h2>カバレッジ（局所）</h2>
<table>
<tr><th>リンク方向</th><th>カバー数</th><th>カバー率</th><th>未カバー</th></tr>
{coverage_rows}
</table>

<h2>アイテム詳細</h2>
{detail_section}

<script>
// --- Highlight on navigation ---
function highlightItem(id) {{
  document.querySelectorAll('.item-detail.highlighted').forEach(
    el => el.classList.remove('highlighted')
  );
  const el = document.getElementById(id);
  if (el) {{
    el.classList.add('highlighted');
    el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }}
}}

document.addEventListener('click', function(e) {{
  const link = e.target.closest('a[href^="#detail-"]');
  if (link) {{
    e.preventDefault();
    const id = link.getAttribute('href').substring(1);
    history.replaceState(null, '', '#' + id);
    highlightItem(id);
  }}
}});

window.addEventListener('hashchange', function() {{
  const id = window.location.hash.substring(1);
  if (id.startsWith('detail-')) highlightItem(id);
}});

if (window.location.hash && window.location.hash.startsWith('#detail-')) {{
  setTimeout(function() {{ highlightItem(window.location.hash.substring(1)); }}, 100);
}}

// サーブモード検出: file:// でなければボタン表示
if (window.location.protocol !== 'file:') {{
  document.querySelectorAll('.item-actions').forEach(el => el.style.display = 'block');
}}

function showToast(msg, type) {{
  const t = document.createElement('div');
  t.className = 'toast ' + (type || 'success');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}}

async function doReview(uid) {{
  const btn = document.querySelector('.item-actions[data-uid="'+uid+'"] .review-btn');
  btn.disabled = true; btn.textContent = '処理中...';
  try {{
    const res = await fetch('/api/review/' + uid, {{ method: 'POST' }});
    const data = await res.json();
    if (data.ok) {{
      const detail = document.getElementById('detail-' + uid);
      const badge = detail.querySelector('.status-badge');
      if (badge) {{
        // suspect + unreviewed/reviewed を全て消してレビュー済に置換
        const old = badge.querySelectorAll('.suspect, .unreviewed, .reviewed');
        old.forEach(b => b.remove());
        const nb = document.createElement('span');
        nb.className = 'reviewed'; nb.textContent = '✓ レビュー済';
        badge.insertBefore(nb, badge.firstChild);
      }}
      btn.textContent = '✓ Review済';
      showToast(uid + ' をレビュー済にしました');
    }} else {{
      btn.textContent = 'Review'; btn.disabled = false;
      showToast('エラー: ' + data.error, 'error');
    }}
  }} catch(e) {{
    btn.textContent = 'Review'; btn.disabled = false;
    showToast('通信エラー: ' + e.message, 'error');
  }}
}}

async function doClear(uid) {{
  const btn = document.querySelector('.item-actions[data-uid="'+uid+'"] .clear-btn');
  btn.disabled = true; btn.textContent = '処理中...';
  try {{
    const res = await fetch('/api/clear/' + uid, {{ method: 'POST' }});
    const data = await res.json();
    if (data.ok) {{
      const detail = document.getElementById('detail-' + uid);
      // suspectバッジだけを除去（reviewed/unreviewedはそのまま残す）
      const suspectBadge = detail.querySelector('.suspect');
      if (suspectBadge) suspectBadge.remove();
      btn.textContent = '✓ Clear済';
      showToast(uid + ' のsuspectを解消しました');
    }} else {{
      btn.textContent = 'Clear'; btn.disabled = false;
      showToast('エラー: ' + data.error, 'error');
    }}
  }} catch(e) {{
    btn.textContent = 'Clear'; btn.disabled = false;
    showToast('通信エラー: ' + e.message, 'error');
  }}
}}

function startEdit(uid) {{
  document.querySelector('.item-text[data-uid="'+uid+'"]').classList.add('hidden');
  document.querySelector('.item-editor[data-uid="'+uid+'"]').classList.remove('hidden');
  const ta = document.querySelector('.edit-textarea[data-uid="'+uid+'"]');
  ta.focus();
  // auto-resize
  ta.style.height = 'auto';
  ta.style.height = Math.max(120, ta.scrollHeight + 4) + 'px';
}}

function cancelEdit(uid) {{
  document.querySelector('.item-editor[data-uid="'+uid+'"]').classList.add('hidden');
  document.querySelector('.item-text[data-uid="'+uid+'"]').classList.remove('hidden');
}}

async function doSave(uid) {{
  const ta = document.querySelector('.edit-textarea[data-uid="'+uid+'"]');
  const btn = document.querySelector('.item-editor[data-uid="'+uid+'"] .save-btn');
  btn.disabled = true; btn.textContent = '保存中...';
  try {{
    const res = await fetch('/api/edit/' + uid, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ text: ta.value }})
    }});
    const data = await res.json();
    if (data.ok) {{
      const textDiv = document.querySelector('.item-text[data-uid="'+uid+'"]');
      textDiv.innerHTML = data.html || ('<p>' + ta.value.replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/\\n/g,'<br>') + '</p>');
      // ステータスを未レビュー+suspectに更新（suspectがあれば残す）
      const detail = document.getElementById('detail-' + uid);
      const oldBadges = detail.querySelectorAll('.reviewed, .unreviewed');
      oldBadges.forEach(b => b.remove());
      const statusContainer = detail.querySelector('.status-badge');
      if (statusContainer) {{
        const nb = document.createElement('span');
        nb.className = 'unreviewed'; nb.textContent = '○ 未レビュー';
        statusContainer.appendChild(nb);
      }}
      cancelEdit(uid);
      btn.textContent = '保存'; btn.disabled = false;
      showToast(uid + ' のテキストを更新しました');
    }} else {{
      btn.textContent = '保存'; btn.disabled = false;
      showToast('エラー: ' + data.error, 'error');
    }}
  }} catch(e) {{
    btn.textContent = '保存'; btn.disabled = false;
    showToast('通信エラー: ' + e.message, 'error');
  }}
}}
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    return output_path


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def write_local_json(tree, related_uids, label, output_path):
    """局所ビューのJSON出力。"""
    items = []
    for doc in tree:
        for item in doc:
            uid_str = str(item.uid)
            if uid_str not in related_uids:
                continue
            items.append({
                "uid": uid_str,
                "prefix": doc.prefix,
                "group": get_group(item),
                "text": item.text.strip(),
                "ref": get_ref(item),
                "links": [str(link) for link in item.links],
                "reviewed": bool(item.reviewed),
            })

    coverage = compute_local_coverage(tree, related_uids)

    report = {
        "timestamp": datetime.now().isoformat(),
        "label": label,
        "item_count": len(items),
        "items": items,
        "coverage": coverage,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return output_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="局所トレーサビリティビュー生成"
    )
    parser.add_argument("project_dir", help="プロジェクトのルートディレクトリ")

    scope = parser.add_argument_group("スコープ指定")
    scope.add_argument("--uid", nargs="+", metavar="UID",
                       help="起点となるアイテムUID（関連チェーンを自動追跡）")
    scope.add_argument("--group", metavar="GROUP",
                       help="グループ名で絞り込み")
    scope.add_argument("--all", action="store_true",
                       help="グループごとに個別ファイルを生成")

    out = parser.add_argument_group("出力")
    out.add_argument("--output-dir", default="./reports/local",
                     help="出力先ディレクトリ (default: ./reports/local)")
    out.add_argument("--json", action="store_true", dest="emit_json",
                     help="JSON形式でも出力")

    args = parser.parse_args()

    if not args.uid and not args.group and not args.all:
        parser.error("スコープを指定してください: --uid, --group, --all")

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    print("ドキュメントツリーを構築中...")
    tree = doorstop.build()

    children_idx, parents_idx = build_link_index(tree)
    output_dir = os.path.join(project_dir, args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    generated = []

    if args.all:
        # グループごとに個別生成
        all_groups = get_all_groups(tree)
        print(f"全グループ: {', '.join(all_groups)}")
        for group in all_groups:
            group_uids = collect_chains_by_group(tree, group)
            if not group_uids:
                continue
            # グループ内UIDの上流・下流も含める
            expanded = set()
            for uid in group_uids:
                expanded |= trace_full_chain(uid, children_idx, parents_idx, tree)
            label = f"グループ: {group}"
            safe_name = group.replace("/", "_").replace(" ", "_")
            html_path = os.path.join(output_dir, f"trace_{safe_name}.html")
            generate_local_html(tree, expanded, label, html_path)
            print(f"  {group}: {len(expanded)}件 → {html_path}")
            generated.append((group, html_path))
            if args.emit_json:
                json_path = os.path.join(output_dir, f"trace_{safe_name}.json")
                write_local_json(tree, expanded, label, json_path)

        # インデックスページを生成
        _generate_index(generated, output_dir)

    elif args.group:
        group_uids = collect_chains_by_group(tree, args.group)
        if not group_uids:
            print(f"グループ '{args.group}' のアイテムが見つかりません。")
            sys.exit(1)
        expanded = set()
        for uid in group_uids:
            expanded |= trace_full_chain(uid, children_idx, parents_idx, tree)
        label = f"グループ: {args.group}"
        safe_name = args.group.replace("/", "_").replace(" ", "_")
        html_path = os.path.join(output_dir, f"trace_{safe_name}.html")
        generate_local_html(tree, expanded, label, html_path)
        print(f"{len(expanded)}件 → {html_path}")
        if args.emit_json:
            json_path = os.path.join(output_dir, f"trace_{safe_name}.json")
            write_local_json(tree, expanded, label, json_path)

    elif args.uid:
        related = collect_chains_by_uid(tree, args.uid, children_idx, parents_idx)
        if not related:
            print("関連アイテムが見つかりません。")
            sys.exit(1)
        label = ", ".join(args.uid)
        safe_name = "_".join(args.uid)
        html_path = os.path.join(output_dir, f"trace_{safe_name}.html")
        generate_local_html(tree, related, label, html_path)
        print(f"{len(related)}件 → {html_path}")
        if args.emit_json:
            json_path = os.path.join(output_dir, f"trace_{safe_name}.json")
            write_local_json(tree, related, label, json_path)


def _generate_index(generated, output_dir):
    """--all 時のインデックスHTMLを生成する。"""
    h = html.escape
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    links = ""
    for group, path in generated:
        fname = os.path.basename(path)
        links += f'<li><a href="{h(fname)}">{h(group)}</a></li>\n'

    index_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>局所トレーサビリティ — インデックス</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 800px; margin: 0 auto; padding: 20px; background: #fafafa; }}
  h1 {{ border-bottom: 3px solid #00897b; padding-bottom: 10px; color: #00897b; }}
  .timestamp {{ color: #999; font-size: 0.85em; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ margin: 8px 0; }}
  a {{ display: inline-block; padding: 8px 16px; background: #fff; border: 1px solid #ddd;
       border-radius: 8px; color: #00897b; text-decoration: none; font-weight: bold;
       transition: background 0.15s; }}
  a:hover {{ background: #e0f2f1; }}
</style>
</head>
<body>
<h1>局所トレーサビリティビュー</h1>
<p class="timestamp">生成日時: {now}</p>
<p>グループごとに関連アイテムだけを表示したレビュー用ページです。</p>
<ul>
{links}
</ul>
</body>
</html>"""

    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"インデックス → {index_path}")


if __name__ == "__main__":
    main()
