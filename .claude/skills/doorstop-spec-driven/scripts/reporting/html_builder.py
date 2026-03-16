"""HTML生成の共通ユーティリティ。

validate_and_report.py と local_trace_view.py で共有する
アイテム属性取得・ステータスアイコン・マトリクスセル・詳細カード・
アセット読み込みなどを提供する。
"""

import html as _html
import os
from collections import defaultdict

try:
    import markdown as _md

    def render_markdown(text):
        return _md.markdown(text, extensions=["tables", "fenced_code"])
except ImportError:

    def render_markdown(text):
        return f"<p>{_html.escape(text)}</p>"


# Alias
h = _html.escape

try:  # noqa: E402
    from ..core._common import (
        get_ref as get_ref,
        get_references as get_references,
        get_references_display,
        is_derived,
        is_normative as is_normative,
        find_item,
        get_groups as _get_groups,
    )
except ImportError:
    # publish_docs.py 等からスタンドアロン実行時、reporting がトップレベル
    # パッケージとなるため相対インポートが失敗する。scripts/ が sys.path 上に
    # ある前提で絶対インポートにフォールバックする。
    from core._common import (  # type: ignore[no-redef]
        get_ref as get_ref,
        get_references as get_references,
        get_references_display,
        is_derived,
        is_normative as is_normative,
        find_item,
        get_groups as _get_groups,
    )


# ---------------------------------------------------------------------------
# Item attribute helpers
# ---------------------------------------------------------------------------

def get_groups(item):
    """グループ属性を取得する。未設定時は ["(未分類)"] を返す。"""
    return _get_groups(item, default=["(未分類)"])


# ---------------------------------------------------------------------------
# Suspect detection
# ---------------------------------------------------------------------------

def detect_suspect_uids(tree):
    """suspectリンクを持つアイテムのUIDセットを返す。active: falseのアイテムは除外。"""
    suspect = set()
    for doc in tree:
        for item in doc:
            if not item.active:
                continue
            for link in item.links:
                parent = find_item(tree, str(link))
                if parent is None or not parent.active:
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
# Children map
# ---------------------------------------------------------------------------

def build_children_map(tree, related_uids=None):
    """親UID → 子UIDリストの逆引きマップを構築する。active: falseのアイテムは除外。"""
    children_map = defaultdict(list)
    for doc in tree:
        for item in doc:
            if not item.active:
                continue
            if related_uids and str(item.uid) not in related_uids:
                continue
            for link in item.links:
                children_map[str(link)].append(str(item.uid))
    return children_map


# ---------------------------------------------------------------------------
# HTML fragment builders
# ---------------------------------------------------------------------------

def build_status_icons(is_suspect, is_reviewed):
    """ステータスアイコンHTML + ステータスセットを返す。"""
    icons = ""
    statuses = set()
    if is_suspect:
        icons += '<span class="suspect">⚠</span>'
        statuses.add("suspect")
    if is_reviewed:
        icons += '<span class="reviewed">✓</span>'
        statuses.add("reviewed")
    else:
        icons += '<span class="unreviewed">○</span>'
        statuses.add("unreviewed")
    return icons, statuses


def build_status_badge(is_suspect, is_reviewed):
    """詳細カード用のステータスバッジHTMLを返す。"""
    badge = ""
    if is_suspect:
        badge += '<span class="suspect">⚠ Suspect</span> '
    if is_reviewed:
        badge += '<span class="reviewed">✓ レビュー済</span>'
    else:
        badge += '<span class="unreviewed">○ 未レビュー</span>'
    return badge


def build_cell_class(is_suspect, is_reviewed):
    """マトリクスセルのCSSクラスを返す。"""
    if is_suspect:
        return "cell-suspect"
    if not is_reviewed:
        return "cell-unreviewed"
    return ""


def build_matrix_cell(item, suspect_uids, ref_fn=get_references_display,
                      include_sort_key=False):
    """マトリクスの1セル(<td>)を生成する。

    Returns: (td_html, uid_str, statuses_set)
    """
    uid_str = str(item.uid)
    text_preview = item.text[:80] + ("..." if len(item.text) > 80 else "")
    ref = ref_fn(item)
    ref_html = f'<br><span class="ref-tag">{h(ref)}</span>' if ref else ""

    is_suspect = uid_str in suspect_uids
    is_reviewed = bool(item.reviewed)
    icons, statuses = build_status_icons(is_suspect, is_reviewed)
    cell_cls = build_cell_class(is_suspect, is_reviewed)

    sort_attr = f' data-sort-key="{h(uid_str)}"' if include_sort_key else ""
    td = (
        f'<td{sort_attr} data-uid="{h(uid_str)}" class="{cell_cls}">'
        f'<a href="#detail-{h(uid_str)}" style="text-decoration:none; color:inherit">'
        f'<strong>{h(uid_str)}</strong></a> '
        f'{icons}'
        f'<br><span class="text-preview">{h(text_preview)}</span>'
        f'{ref_html}</td>'
    )
    return td, uid_str, statuses


def build_detail_card(item, doc_prefix, suspect_uids, children_map, tree,
                      local_view_href=None):
    """アイテム詳細カード(<div class="item-detail">)を生成する。"""
    uid_str = str(item.uid)
    is_suspect = uid_str in suspect_uids
    is_reviewed = bool(item.reviewed)
    badge = build_status_badge(is_suspect, is_reviewed)
    groups = get_groups(item)

    # References
    ref = get_references_display(item)
    ref_line = (
        f'<p><strong>references:</strong> <span class="ref-tag">{h(ref)}</span></p>'
        if ref else ""
    )

    # Derived
    derived = is_derived(item)
    derived_line = (
        '<p><strong>derived:</strong> <span style="background:#e8f0fe;color:#1a73e8;padding:2px 8px;border-radius:4px;font-size:0.85em">true</span></p>'
        if derived else ""
    )

    # Parent links
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
    parents_str = ", ".join(parent_links) if parent_links else "\u2014"

    # Child links
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
    children_str = ", ".join(child_links) if child_links else "\u2014"

    # Text
    text_html = render_markdown(item.text)
    raw_text = (item.text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    # Statuses for filtering
    detail_statuses = []
    if is_suspect:
        detail_statuses.append("suspect")
    if is_reviewed:
        detail_statuses.append("reviewed")
    else:
        detail_statuses.append("unreviewed")
    detail_statuses_str = " ".join(detail_statuses)

    # Header extras
    prefix_tag = f'<span class="prefix-tag">{h(doc_prefix)}</span> ' if doc_prefix else ""
    local_link = ""
    if local_view_href:
        local_link = f'<a class="local-view-link" href="{h(local_view_href)}">局所ビュー →</a>'

    return f"""
    <div class="item-detail" id="detail-{h(uid_str)}" data-groups="{h(' '.join(groups))}" data-uid="{h(uid_str)}" data-statuses="{h(detail_statuses_str)}">
      <h3>{h(uid_str)} {prefix_tag}{''.join('<span class="group-tag">{h(g)}</span> ' for g in groups)} <span class="status-badge">{badge}</span>
        {local_link}
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
      {derived_line}
      <p><strong>親:</strong> {parents_str}</p>
      <p><strong>子:</strong> {children_str}</p>
      <div class="item-actions" data-uid="{h(uid_str)}">
        <button class="action-btn edit-btn" onclick="startEdit('{h(uid_str)}')">Edit</button>
        <button class="action-btn review-btn" onclick="doReview('{h(uid_str)}')">Review</button>
        <button class="action-btn clear-btn" onclick="doClear('{h(uid_str)}')">Clear</button>
      </div>
    </div>"""


# ---------------------------------------------------------------------------
# Asset loading
# ---------------------------------------------------------------------------

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def load_assets(*filenames):
    """assets/ ディレクトリからファイルを読み込み、結合して返す。"""
    parts = []
    for name in filenames:
        path = os.path.join(_ASSETS_DIR, name)
        with open(path, encoding="utf-8") as f:
            parts.append(f.read())
    return "\n".join(parts)


def assemble_html(title, css_files, body, js_files):
    """最終HTMLを組み立てる。"""
    css = load_assets(*css_files)
    js = load_assets(*js_files)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>{_html.escape(title)}</title>
<style>
{css}
</style>
</head>
<body>
{body}
<script>
{js}
</script>
</body>
</html>"""
