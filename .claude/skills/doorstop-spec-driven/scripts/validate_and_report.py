#!/usr/bin/env python3
"""Doorstopプロジェクトのバリデーションとトレーサビリティレポート生成。

REQ → SPEC → IMPL/TST の4階層対応。
構造検証、リンク整合性、ref存在チェック、機能グループ別カバレッジ、
レビュー状態の追跡を行い、HTMLトレーサビリティレポートを出力する。

Usage:
    python validate_and_report.py <project-dir> [--output-dir ./reports] [--strict] [--json]
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


def _find_item(tree, uid_str):
    for doc in tree:
        try:
            return doc.find_item(uid_str)
        except Exception:
            continue
    return None


def detect_suspect_items(tree):
    """suspectリンクを持つアイテムのUIDセットを返す。"""
    suspect_uids = set()
    for doc in tree:
        for item in doc:
            for link in item.links:
                parent_item = _find_item(tree, str(link))
                if parent_item is None:
                    continue
                if (
                    link.stamp is not None
                    and link.stamp != ""
                    and link.stamp != parent_item.stamp()
                ):
                    suspect_uids.add(str(item.uid))
                    break
    return suspect_uids


def validate_tree(tree, strict=False, project_dir="."):
    """ドキュメントツリーを検証する。"""
    issues = {"errors": [], "warnings": [], "info": []}

    # 基本チェック
    for document in tree:
        for item in document:
            if not item.text.strip():
                issues["warnings"].append(f"{item.uid}: テキストが空です")
            if not item.active:
                issues["warnings"].append(f"{item.uid}: 非アクティブです")

    # 親子リンクの検証
    docs = {doc.prefix: doc for doc in tree}
    for document in tree:
        if not document.parent:
            continue
        parent_doc = docs.get(document.parent)
        if parent_doc is None:
            issues["errors"].append(
                f"{document.prefix}: 親ドキュメント '{document.parent}' が見つかりません"
            )
            continue

        parent_uids = {str(item.uid) for item in parent_doc}
        for item in document:
            linked_parents = [
                str(link) for link in item.links
                if str(link).startswith(document.parent)
            ]
            if not linked_parents:
                issues["warnings"].append(
                    f"{item.uid} [{get_group(item)}]: "
                    f"親ドキュメント {document.parent} へのリンクがありません"
                )
            for link in linked_parents:
                link_uid = link.split(":")[0] if ":" in link else link
                if link_uid not in parent_uids:
                    issues["errors"].append(
                        f"{item.uid}: リンク先 {link_uid} が存在しません"
                    )

        # クロスグループリンク警告
        parent_groups = {str(i.uid): get_group(i) for i in parent_doc}
        for item in document:
            child_group = get_group(item)
            if child_group == "(未分類)":
                continue
            for link in item.links:
                link_str = str(link)
                if link_str in parent_groups:
                    pg = parent_groups[link_str]
                    if pg != "(未分類)" and pg != child_group:
                        issues["warnings"].append(
                            f"{item.uid} [{child_group}] → {link_str} [{pg}]: "
                            f"クロスグループリンクです"
                        )

        # 逆方向チェック（strictモード）
        if strict:
            child_links = defaultdict(set)
            for item in document:
                for link in item.links:
                    link_str = str(link)
                    if link_str.startswith(document.parent):
                        child_links[link_str].add(str(item.uid))
            for parent_item in parent_doc:
                if str(parent_item.uid) not in child_links:
                    issues["warnings"].append(
                        f"{parent_item.uid} [{get_group(parent_item)}]: "
                        f"子ドキュメント {document.prefix} からのリンクがありません"
                    )

    # ref存在チェック（IMPL, TST）
    ref_docs = {"IMPL", "TST"}
    for document in tree:
        if document.prefix not in ref_docs:
            continue
        for item in document:
            ref = get_ref(item)
            if not ref:
                continue
            # ファイルパス部分を抽出（:: 以降はクラス/関数名）
            filepath = ref.split("::")[0]
            full_path = os.path.join(project_dir, filepath)
            if not os.path.exists(full_path):
                issues["warnings"].append(
                    f"{item.uid}: ref '{ref}' のファイルが存在しません"
                )

    # レビュー状態チェック
    unreviewed = []
    for document in tree:
        for item in document:
            if not item.reviewed:
                unreviewed.append(str(item.uid))
    if unreviewed:
        issues["info"].append(
            f"未レビューアイテム: {len(unreviewed)}件 "
            f"({', '.join(unreviewed[:10])}{'...' if len(unreviewed) > 10 else ''})"
        )

    return issues


def build_traceability_matrix(tree):
    """トレーサビリティマトリクスを構築する。

    REQ → SPEC → IMPL/TST の構造で、SPECに2つの子がある場合も対応。
    """
    docs = list(tree)
    prefixes = [d.prefix for d in docs]
    matrix = []

    root_docs = [d for d in docs if not d.parent]
    for root_doc in root_docs:
        for item in root_doc:
            row = {root_doc.prefix: item, "_group": get_group(item)}
            matrix.append(row)

    def expand_children(doc, parent_prefix):
        child_docs = [d for d in docs if d.parent == doc.prefix]
        for child_doc in child_docs:
            link_map = defaultdict(list)
            for child_item in child_doc:
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


def compute_coverage(tree):
    """ドキュメントペア別・グループ別のカバレッジを計算する。"""
    docs = {doc.prefix: doc for doc in tree}
    coverage = {}

    for doc in tree:
        if not doc.parent or doc.parent not in docs:
            continue
        parent_doc = docs[doc.parent]
        parent_uids = {str(item.uid) for item in parent_doc}
        covered_uids = set()

        for item in doc:
            for link in item.links:
                link_str = str(link)
                if link_str in parent_uids:
                    covered_uids.add(link_str)

        total = len(parent_uids)
        covered = len(covered_uids)
        pct = (covered / total * 100) if total > 0 else 0.0

        # グループ別
        group_cov = defaultdict(lambda: {"total": set(), "covered": set()})
        for pi in parent_doc:
            group_cov[get_group(pi)]["total"].add(str(pi.uid))
        for item in doc:
            for link in item.links:
                link_str = str(link)
                if link_str in parent_uids:
                    po = parent_doc.find_item(link_str)
                    group_cov[get_group(po)]["covered"].add(link_str)

        groups = {}
        for g, d in sorted(group_cov.items()):
            gt, gc = len(d["total"]), len(d["covered"])
            groups[g] = {
                "total": gt, "covered": gc, "uncovered": gt - gc,
                "percentage": round(gc / gt * 100, 1) if gt > 0 else 0.0,
                "uncovered_items": sorted(d["total"] - d["covered"]),
            }

        coverage[f"{doc.prefix} → {doc.parent}"] = {
            "total": total, "covered": covered, "uncovered": total - covered,
            "percentage": round(pct, 1),
            "uncovered_items": sorted(parent_uids - covered_uids),
            "by_group": groups,
        }

    return coverage


def _color(pct):
    if pct == 100:
        return "#4caf50"
    elif pct >= 50:
        return "#ff9800"
    else:
        return "#f44336"


def generate_html_report(tree, issues, matrix, prefixes, coverage, output_path):
    """グループ・状態・IDフィルタ付きHTMLレポートを生成する。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    h = html.escape

    all_groups = sorted({get_group(item) for doc in tree for item in doc})
    suspect_uids = detect_suspect_items(tree)

    group_buttons = ''.join(
        f'<button class="group-btn" data-group="{h(g)}" onclick="toggleGroup(this)">{h(g)}</button>'
        for g in all_groups
    )

    # レビュー統計
    total_items = sum(len(list(d)) for d in tree)
    reviewed_items = sum(
        1 for d in tree for item in d
        if item.reviewed
    )
    suspect_count = len(suspect_uids)

    # カバレッジテーブル
    coverage_rows = ""
    for pair, data in coverage.items():
        color = _color(data["percentage"])
        uncovered_str = ", ".join(data["uncovered_items"]) if data["uncovered_items"] else "—"
        coverage_rows += f"""
        <tr class="coverage-total">
            <td><strong>{h(pair)}</strong></td>
            <td>—</td>
            <td>{data['covered']} / {data['total']}</td>
            <td style="color:{color}; font-weight:bold">{data['percentage']}%</td>
            <td style="font-size:0.85em">{h(uncovered_str)}</td>
        </tr>"""
        for g, gd in data.get("by_group", {}).items():
            gc = _color(gd["percentage"])
            gu = ", ".join(gd["uncovered_items"]) if gd["uncovered_items"] else "—"
            coverage_rows += f"""
        <tr class="coverage-group" data-group="{h(g)}">
            <td style="padding-left:30px">{h(pair)}</td>
            <td><span class="group-tag">{h(g)}</span></td>
            <td>{gd['covered']} / {gd['total']}</td>
            <td style="color:{gc}; font-weight:bold">{gd['percentage']}%</td>
            <td style="font-size:0.85em">{h(gu)}</td>
        </tr>"""

    # イシュー一覧
    error_items = "".join(f"<li class='error'>{h(e)}</li>" for e in issues["errors"])
    warning_items = "".join(f"<li class='warning'>{h(w)}</li>" for w in issues["warnings"])
    info_items = "".join(f"<li class='info'>{h(i)}</li>" for i in issues["info"])
    issue_section = ""
    if issues["errors"]:
        issue_section += f"<h3>エラー ({len(issues['errors'])}件)</h3><ul>{error_items}</ul>"
    if issues["warnings"]:
        issue_section += f"<h3>警告 ({len(issues['warnings'])}件)</h3><ul>{warning_items}</ul>"
    if issues["info"]:
        issue_section += f"<h3>情報</h3><ul>{info_items}</ul>"
    if not issues["errors"] and not issues["warnings"]:
        issue_section = "<p style='color:#4caf50; font-weight:bold'>問題は検出されませんでした。</p>"
        if issues["info"]:
            issue_section += f"<h3>情報</h3><ul>{info_items}</ul>"

    # トレーサビリティマトリクス
    header_cells = '<th class="sortable" onclick="sortMatrix(0)" data-col="0">グループ<span class="sort-arrow">▲▼</span></th>'
    for i, p in enumerate(prefixes, 1):
        header_cells += f'<th class="sortable" onclick="sortMatrix({i})" data-col="{i}">{h(p)}<span class="sort-arrow">▲▼</span></th>'
    matrix_rows = ""
    for row in matrix:
        group = h(row.get("_group", "(未分類)"))
        row_uids = []
        row_statuses = set()
        cells = f'<td data-sort-key="{group}"><span class="group-tag">{group}</span></td>'
        for prefix in prefixes:
            item = row.get(prefix)
            if item:
                uid_str = str(item.uid)
                row_uids.append(uid_str)
                text_preview = item.text[:80] + ("..." if len(item.text) > 80 else "")
                ref = get_ref(item)
                ref_html = f'<br><span class="ref-tag">{h(ref)}</span>' if ref else ""
                # レビュー状態（suspect と reviewed/unreviewed は独立）
                is_reviewed = bool(item.reviewed)
                is_suspect = uid_str in suspect_uids
                status_icons = ""
                if is_suspect:
                    status_icons += '<span class="suspect">⚠</span>'
                    row_statuses.add("suspect")
                if is_reviewed:
                    status_icons += '<span class="reviewed">✓</span>'
                    row_statuses.add("reviewed")
                else:
                    status_icons += '<span class="unreviewed">○</span>'
                    row_statuses.add("unreviewed")
                cells += (
                    f'<td data-sort-key="{h(uid_str)}">'
                    f'<a href="#detail-{h(uid_str)}" style="text-decoration:none; color:inherit">'
                    f'<strong>{h(uid_str)}</strong></a> '
                    f'{status_icons}'
                    f'<br><span class="text-preview">{h(text_preview)}</span>'
                    f'{ref_html}</td>'
                )
            else:
                cells += '<td data-sort-key="" class="empty">—</td>'
        uids_attr = h(" ".join(row_uids))
        statuses_attr = h(" ".join(sorted(row_statuses)))
        matrix_rows += (
            f'<tr data-group="{group}" data-uids="{uids_attr}" '
            f'data-statuses="{statuses_attr}">{cells}</tr>'
        )

    # 子リンクの逆引きマップを構築（親UID → 子UIDのリスト）
    children_map = defaultdict(list)
    for doc in tree:
        for item in doc:
            for link in item.links:
                children_map[str(link)].append(str(item.uid))

    # アイテム詳細セクション
    item_detail_section = ""
    for doc in tree:
        for item in doc:
            uid_str = str(item.uid)
            is_suspect = uid_str in suspect_uids
            is_reviewed = bool(item.reviewed)
            status_badge = ""
            if is_suspect:
                status_badge += '<span class="suspect">⚠ Suspect</span> '
            if is_reviewed:
                status_badge += '<span class="reviewed">✓ レビュー済</span>'
            else:
                status_badge += '<span class="unreviewed">○ 未レビュー</span>'
            ref = get_ref(item)
            ref_line = f'<p><strong>ref:</strong> <span class="ref-tag">{h(ref)}</span></p>' if ref else ""
            group = get_group(item)
            parent_links = []
            for link in item.links:
                link_str = str(link)
                parent_item = _find_item(tree, link_str)
                if parent_item and not parent_item.reviewed:
                    parent_links.append(
                        f'<a href="#detail-{h(link_str)}" class="link-unreviewed">{h(link_str)}</a>'
                        f' <span class="link-unreviewed-label">(\u672a\u30ec\u30d3\u30e5\u30fc)</span>'
                    )
                else:
                    parent_links.append(
                        f'<a href="#detail-{h(link_str)}">{h(link_str)}</a>'
                    )
            parents_str = ", ".join(parent_links) if parent_links else "\u2014"
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
            text_html = render_markdown(item.text)
            raw_text = item.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            safe_group = group.replace("/", "_").replace(" ", "_").replace("(", "").replace(")", "")
            local_view_href = f"local/trace_{safe_group}.html#detail-{uid_str}"
            detail_statuses = []
            if is_suspect:
                detail_statuses.append("suspect")
            if is_reviewed:
                detail_statuses.append("reviewed")
            else:
                detail_statuses.append("unreviewed")
            detail_statuses_str = " ".join(detail_statuses)
            item_detail_section += f"""
    <div class="item-detail" id="detail-{h(uid_str)}" data-group="{h(group)}" data-uid="{h(uid_str)}" data-statuses="{h(detail_statuses_str)}">
      <h3>{h(uid_str)} <span class="group-tag">{h(group)}</span> <span class="status-badge">{status_badge}</span>
        <a class="local-view-link" href="{h(local_view_href)}">局所ビュー →</a>
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

    report_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>トレーサビリティレポート</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1400px; margin: 0 auto; padding: 20px; background: #fafafa; }}
  h1 {{ border-bottom: 3px solid #1a73e8; padding-bottom: 10px; }}
  h2 {{ color: #1a73e8; margin-top: 30px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; background: #fff; }}
  th {{ background: #1a73e8; color: #fff; padding: 10px; text-align: left; }}
  td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .text-preview {{ color: #666; font-size: 0.85em; }}
  .ref-tag {{ display: inline-block; background: #f3e5f5; color: #7b1fa2; padding: 1px 6px;
              border-radius: 3px; font-size: 0.75em; font-family: monospace; margin-top: 2px; }}
  .empty {{ color: #ccc; text-align: center; }}
  .error {{ color: #d32f2f; }}
  .warning {{ color: #f57c00; }}
  .info {{ color: #1976d2; }}
  .reviewed {{ color: #4caf50; font-size: 0.8em; }}
  .unreviewed {{ color: #bdbdbd; font-size: 0.8em; }}
  .suspect {{ color: #e65100; font-size: 0.8em; font-weight: bold; }}
  .link-unreviewed {{ color: #9e9e9e; }}
  .link-unreviewed-label {{ color: #9e9e9e; font-size: 0.8em; }}
  .link-suspect {{ color: #e65100; }}
  .link-suspect-label {{ color: #e65100; font-size: 0.8em; font-weight: bold; }}
  .summary {{ display: flex; gap: 15px; margin: 15px 0; flex-wrap: wrap; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
           padding: 15px 20px; flex: 1; min-width: 100px; text-align: center; }}
  .card h3 {{ margin: 0 0 5px; font-size: 0.85em; color: #666; }}
  .card .value {{ font-size: 1.6em; font-weight: bold; color: #1a73e8; }}
  .timestamp {{ color: #999; font-size: 0.85em; }}
  .group-tag {{ display: inline-block; background: #e3f2fd; color: #1565c0; padding: 2px 8px;
                border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
  .filter-section {{ margin: 10px 0; }}
  .filter-section label {{ font-weight: bold; color: #555; margin-right: 10px; font-size: 0.9em; }}
  .group-filter {{ margin: 10px 0; }}
  .group-btn {{ margin: 3px; padding: 6px 14px; border: 1px solid #1a73e8; border-radius: 16px;
                background: #fff; color: #1a73e8; cursor: pointer; font-size: 0.85em; }}
  .group-btn.active {{ background: #1a73e8; color: #fff; }}
  .group-btn:hover {{ background: #e3f2fd; }}
  .group-btn.active:hover {{ background: #1565c0; }}
  .status-btn {{ margin: 3px; padding: 6px 14px; border: 1px solid #666; border-radius: 16px;
                 background: #fff; cursor: pointer; font-size: 0.85em; }}
  .status-btn[data-status="reviewed"] {{ color: #4caf50; border-color: #4caf50; }}
  .status-btn[data-status="reviewed"].active {{ background: #4caf50; color: #fff; }}
  .status-btn[data-status="unreviewed"] {{ color: #9e9e9e; border-color: #9e9e9e; }}
  .status-btn[data-status="unreviewed"].active {{ background: #9e9e9e; color: #fff; }}
  .status-btn[data-status="suspect"] {{ color: #e65100; border-color: #e65100; }}
  .status-btn[data-status="suspect"].active {{ background: #e65100; color: #fff; }}
  .status-btn:hover {{ opacity: 0.8; }}
  .id-search {{ padding: 6px 12px; border: 1px solid #ccc; border-radius: 16px;
                font-size: 0.85em; width: 220px; outline: none; }}
  .id-search:focus {{ border-color: #1a73e8; box-shadow: 0 0 0 2px rgba(26,115,232,0.15); }}
  .coverage-group {{ font-size: 0.9em; }}
  tr.hidden {{ display: none; }}
  .item-detail.hidden {{ display: none; }}
  #matrix-table th.sortable {{ cursor: pointer; user-select: none; position: relative; padding-right: 20px; }}
  #matrix-table th.sortable:hover {{ background: #1565c0; }}
  #matrix-table th .sort-arrow {{ position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
                                   font-size: 0.7em; opacity: 0.5; }}
  #matrix-table th.sort-active .sort-arrow {{ opacity: 1; }}
  .detail-sort {{ margin: 10px 0; display: flex; align-items: center; gap: 10px; }}
  .detail-sort label {{ font-weight: bold; color: #555; font-size: 0.9em; }}
  .detail-sort select {{ padding: 5px 10px; border: 1px solid #ccc; border-radius: 6px;
                          font-size: 0.85em; outline: none; }}
  .detail-sort select:focus {{ border-color: #1a73e8; }}
  #matrix-table a:hover strong {{ text-decoration: underline; }}
  .item-detail {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
                  padding: 15px 20px; margin: 10px 0; transition: border-color 0.3s, box-shadow 0.3s; }}
  .item-detail:target, .item-detail.highlighted {{
    border-color: #1a73e8;
    box-shadow: 0 0 0 3px rgba(26,115,232,0.2);
    animation: highlightFade 2s ease forwards;
  }}
  @keyframes highlightFade {{
    0% {{ background: #e3f2fd; }}
    100% {{ background: #fff; }}
  }}
  .item-detail h3 {{ margin: 0 0 8px; font-size: 1.1em; }}
  .item-detail p {{ margin: 5px 0; color: #333; }}
  .item-detail a {{ color: #1a73e8; text-decoration: none; }}
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
  .local-view-link {{ float: right; font-size: 0.75em; font-weight: normal; padding: 3px 10px;
                      background: #e0f2f1; color: #00695c; border-radius: 12px;
                      text-decoration: none; transition: background 0.15s; }}
  .local-view-link:hover {{ background: #b2dfdb; text-decoration: none; }}
  .item-actions {{ display: none; margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; }}
  .action-btn {{ padding: 6px 16px; border: 1px solid #ccc; border-radius: 6px;
                 background: #fff; cursor: pointer; font-size: 0.85em; margin-right: 8px;
                 transition: background 0.15s; }}
  .action-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .review-btn {{ color: #4caf50; border-color: #4caf50; }}
  .review-btn:hover:not(:disabled) {{ background: #e8f5e9; }}
  .edit-btn {{ color: #1a73e8; border-color: #1a73e8; }}
  .edit-btn:hover:not(:disabled) {{ background: #e3f2fd; }}
  .clear-btn {{ color: #e65100; border-color: #e65100; }}
  .clear-btn:hover:not(:disabled) {{ background: #fff3e0; }}
  .save-btn {{ color: #fff; background: #1a73e8; border-color: #1a73e8; }}
  .save-btn:hover:not(:disabled) {{ background: #1565c0; }}
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
</style>
</head>
<body>
<h1>トレーサビリティレポート</h1>
<p class="timestamp">生成日時: {now}</p>

<div class="summary">
  <div class="card">
    <h3>ドキュメント</h3>
    <div class="value">{len(list(tree))}</div>
  </div>
  <div class="card">
    <h3>総アイテム</h3>
    <div class="value">{total_items}</div>
  </div>
  <div class="card">
    <h3>グループ</h3>
    <div class="value">{len(all_groups)}</div>
  </div>
  <div class="card">
    <h3>レビュー済</h3>
    <div class="value">{reviewed_items}/{total_items}</div>
  </div>
  <div class="card">
    <h3>Suspect</h3>
    <div class="value" style="color:{'#e65100' if suspect_count else '#4caf50'}">{suspect_count}</div>
  </div>
  <div class="card">
    <h3>エラー</h3>
    <div class="value" style="color:{'#d32f2f' if issues['errors'] else '#4caf50'}">{len(issues['errors'])}</div>
  </div>
  <div class="card">
    <h3>警告</h3>
    <div class="value" style="color:{'#f57c00' if issues['warnings'] else '#4caf50'}">{len(issues['warnings'])}</div>
  </div>
</div>

<h2>フィルタ</h2>
<div class="filter-section">
  <label>グループ:</label>
  <div class="group-filter" style="display:inline">
    <button class="group-btn active" data-group="__all__" onclick="showAllGroups()">すべて</button>
    {group_buttons}
  </div>
</div>
<div class="filter-section">
  <label>状態:</label>
  <button class="status-btn" data-status="reviewed" onclick="toggleStatus(this)">✓ レビュー済</button>
  <button class="status-btn" data-status="unreviewed" onclick="toggleStatus(this)">○ 未レビュー</button>
  <button class="status-btn" data-status="suspect" onclick="toggleStatus(this)">⚠ Suspect</button>
</div>
<div class="filter-section">
  <label>アイテムID:</label>
  <input type="text" class="id-search" id="id-search" placeholder="例: SPEC001, REQ00"
         oninput="applyFilters()">
</div>

<h2>検証結果</h2>
{issue_section}

<h2>トレーサビリティマトリクス</h2>
<p style="font-size:0.85em; color:#888">✓=レビュー済　○=未レビュー　⚠=Suspect（複数同時表示あり。アイテムIDをクリックで詳細へ）</p>
<table id="matrix-table">
<tr>{header_cells}</tr>
{matrix_rows}
</table>

<h2>カバレッジ</h2>
<table id="coverage-table">
<tr><th>リンク方向</th><th>グループ</th><th>カバー数</th><th>カバー率</th><th>未カバーアイテム</th></tr>
{coverage_rows}
</table>

<h2 id="item-details">アイテム詳細</h2>
<div class="detail-sort">
  <label>ソート:</label>
  <select id="detail-sort-select" onchange="sortDetails()">
    <option value="uid-asc">アイテムID (昇順)</option>
    <option value="uid-desc">アイテムID (降順)</option>
    <option value="group-asc">グループ (昇順)</option>
    <option value="group-desc">グループ (降順)</option>
  </select>
</div>
{item_detail_section}

<script>
let activeGroups = new Set();
let activeStatuses = new Set();

function toggleGroup(btn) {{
  const group = btn.dataset.group;
  const allBtn = document.querySelector('[data-group="__all__"]');
  if (activeGroups.has(group)) {{ activeGroups.delete(group); btn.classList.remove('active'); }}
  else {{ activeGroups.add(group); btn.classList.add('active'); allBtn.classList.remove('active'); }}
  if (activeGroups.size === 0) {{ showAllGroups(); return; }}
  applyFilters();
}}

function showAllGroups() {{
  activeGroups.clear();
  document.querySelectorAll('.group-btn').forEach(b => b.classList.remove('active'));
  document.querySelector('[data-group="__all__"]').classList.add('active');
  applyFilters();
}}

function toggleStatus(btn) {{
  const status = btn.dataset.status;
  if (activeStatuses.has(status)) {{ activeStatuses.delete(status); btn.classList.remove('active'); }}
  else {{ activeStatuses.add(status); btn.classList.add('active'); }}
  applyFilters();
}}

function naturalCompare(a, b) {{
  return a.localeCompare(b, undefined, {{ numeric: true, sensitivity: 'base' }});
}}

let currentSortCol = -1;
let currentSortDir = 'asc';

function sortMatrix(colIndex) {{
  if (currentSortCol === colIndex) {{
    currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
  }} else {{
    currentSortCol = colIndex;
    currentSortDir = 'asc';
  }}
  const table = document.getElementById('matrix-table');
  const rows = Array.from(table.querySelectorAll('tr[data-group]'));
  rows.sort((a, b) => {{
    const aKey = a.cells[colIndex]?.dataset.sortKey || '';
    const bKey = b.cells[colIndex]?.dataset.sortKey || '';
    const cmp = naturalCompare(aKey, bKey);
    return currentSortDir === 'asc' ? cmp : -cmp;
  }});
  const tbody = rows[0]?.parentNode;
  if (tbody) rows.forEach(r => tbody.appendChild(r));

  // Update header indicators
  table.querySelectorAll('th.sortable').forEach(th => {{
    th.classList.remove('sort-active');
    th.querySelector('.sort-arrow').textContent = '▲▼';
  }});
  const activeHeader = table.querySelector(`th[data-col="${{colIndex}}"]`);
  if (activeHeader) {{
    activeHeader.classList.add('sort-active');
    activeHeader.querySelector('.sort-arrow').textContent = currentSortDir === 'asc' ? '▲' : '▼';
  }}
}}

function sortDetails() {{
  const sel = document.getElementById('detail-sort-select').value;
  const [field, dir] = sel.split('-');
  const container = document.getElementById('item-details');
  const details = Array.from(document.querySelectorAll('.item-detail'));
  details.sort((a, b) => {{
    let aKey, bKey;
    if (field === 'uid') {{
      aKey = a.dataset.uid || '';
      bKey = b.dataset.uid || '';
    }} else {{
      aKey = a.dataset.group || '';
      bKey = b.dataset.group || '';
      if (aKey === bKey) {{
        aKey = a.dataset.uid || '';
        bKey = b.dataset.uid || '';
      }}
    }}
    const cmp = naturalCompare(aKey, bKey);
    return dir === 'asc' ? cmp : -cmp;
  }});
  // Re-insert after the sort select's parent div
  const sortDiv = document.querySelector('.detail-sort');
  let insertPoint = sortDiv;
  details.forEach(d => {{
    insertPoint.after(d);
    insertPoint = d;
  }});
}}

function applyFilters() {{
  const idQuery = document.getElementById('id-search').value.trim().toUpperCase();

  // Matrix rows
  document.querySelectorAll('#matrix-table tr[data-group]').forEach(row => {{
    let show = true;

    // Group filter
    if (activeGroups.size > 0 && !activeGroups.has(row.dataset.group)) {{
      show = false;
    }}

    // Status filter
    if (show && activeStatuses.size > 0) {{
      const rowStatuses = (row.dataset.statuses || '').split(' ');
      const match = rowStatuses.some(s => activeStatuses.has(s));
      if (!match) show = false;
    }}

    // ID filter
    if (show && idQuery) {{
      const rowUids = (row.dataset.uids || '').toUpperCase();
      const match = idQuery.split(',').some(q => rowUids.includes(q.trim()));
      if (!match) show = false;
    }}

    row.classList.toggle('hidden', !show);
  }});

  // Item detail sections
  document.querySelectorAll('.item-detail').forEach(detail => {{
    let show = true;

    // Group filter
    if (activeGroups.size > 0 && !activeGroups.has(detail.dataset.group)) {{
      show = false;
    }}

    // Status filter
    if (show && activeStatuses.size > 0) {{
      const detailStatuses = (detail.dataset.statuses || '').split(' ');
      const match = detailStatuses.some(s => activeStatuses.has(s));
      if (!match) show = false;
    }}

    // ID filter
    if (show && idQuery) {{
      const uid = (detail.dataset.uid || '').toUpperCase();
      const match = idQuery.split(',').some(q => uid.includes(q.trim()));
      if (!match) show = false;
    }}

    detail.classList.toggle('hidden', !show);
  }});

  // Coverage rows (group filter only)
  document.querySelectorAll('#coverage-table .coverage-group').forEach(row => {{
    if (activeGroups.size === 0) {{ row.classList.remove('hidden'); }}
    else {{ row.classList.toggle('hidden', !activeGroups.has(row.dataset.group)); }}
  }});
  document.querySelectorAll('#coverage-table .coverage-total').forEach(row => {{
    row.classList.remove('hidden');
  }});
}}

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

// --- Serve mode: action buttons ---
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
  const btn = document.querySelector('[data-uid="'+uid+'"] .review-btn');
  btn.disabled = true; btn.textContent = '処理中...';
  try {{
    const res = await fetch('/api/review/' + uid, {{ method: 'POST' }});
    const data = await res.json();
    if (data.ok) {{
      const detail = document.getElementById('detail-' + uid);
      const badges = detail.querySelectorAll('.suspect, .unreviewed, .reviewed');
      // suspect + unreviewed/reviewed を全て消してレビュー済に置換
      const parent = badges.length > 0 ? badges[0].parentNode : null;
      badges.forEach(b => b.remove());
      if (parent) {{
        const newBadge = document.createElement('span');
        newBadge.className = 'reviewed';
        newBadge.textContent = '✓ レビュー済';
        parent.insertBefore(newBadge, parent.firstChild);
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
  const btn = document.querySelector('[data-uid="'+uid+'"] .clear-btn');
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
      showToast(uid + ' のsuspectリンクを解消しました');
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
      // suspect の後ろ（または先頭）に未レビューバッジを追加
      const statusContainer = detail.querySelector('.status-badge');
      if (statusContainer) {{
        const newBadge = document.createElement('span');
        newBadge.className = 'unreviewed';
        newBadge.textContent = '○ 未レビュー';
        statusContainer.appendChild(newBadge);
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
        f.write(report_html)
    return output_path


def _generate_local_views(tree, output_dir):
    """局所トレーサビリティビューをグループごとに自動生成する。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    try:
        from local_trace_view import (
            build_link_index,
            collect_chains_by_group,
            trace_full_chain,
            generate_local_html,
            get_all_groups,
            _generate_index,
        )
    except ImportError:
        print("WARNING: local_trace_view.py が見つかりません。局所ビューの生成をスキップします。")
        return
    finally:
        sys.path.pop(0)

    local_dir = os.path.join(output_dir, "local")
    os.makedirs(local_dir, exist_ok=True)

    children_idx, parents_idx = build_link_index(tree)
    all_groups = get_all_groups(tree)
    generated = []

    print("局所トレーサビリティビューを生成中...")
    for group in all_groups:
        group_uids = collect_chains_by_group(tree, group)
        if not group_uids:
            continue
        expanded = set()
        for uid in group_uids:
            expanded |= trace_full_chain(uid, children_idx, parents_idx, tree)
        label = f"グループ: {group}"
        safe_name = group.replace("/", "_").replace(" ", "_")
        html_path = os.path.join(local_dir, f"trace_{safe_name}.html")
        generate_local_html(tree, expanded, label, html_path,
                            back_link="../traceability_report.html")
        generated.append((group, html_path))

    _generate_index(generated, local_dir)
    print(f"局所ビュー: {len(generated)}グループ → {local_dir}/")


def _serve_report(report_path, tree, port, strict=False):
    """REST API + SPA サーバーを起動する（serve_app に委譲）。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    try:
        from serve_app import serve
    finally:
        sys.path.pop(0)
    serve(tree, os.getcwd(), port=port, strict=strict)


def main():
    parser = argparse.ArgumentParser(
        description="Doorstopプロジェクトのバリデーションとレポート生成"
    )
    parser.add_argument("project_dir", help="プロジェクトのルートディレクトリ")
    parser.add_argument("--output-dir", default="./reports", help="レポート出力先")
    parser.add_argument("--strict", action="store_true",
                        help="全ての親アイテムに子リンクがあることを要求する")
    parser.add_argument("--json", action="store_true", help="JSON形式でもサマリを出力する")
    parser.add_argument("--serve", action="store_true",
                        help="ローカルサーバーを起動（Review/Clearボタンが有効になる）")
    parser.add_argument("--port", type=int, default=8080, help="サーバーポート (default: 8080)")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    print("ドキュメントツリーを構築中...")
    tree = doorstop.build()

    print("バリデーション実行中...")
    issues = validate_tree(tree, strict=args.strict, project_dir=project_dir)

    print("トレーサビリティマトリクスを構築中...")
    matrix, prefixes = build_traceability_matrix(tree)

    print("カバレッジを計算中...")
    coverage = compute_coverage(tree)

    output_dir = os.path.join(project_dir, args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    html_path = os.path.join(output_dir, "traceability_report.html")
    generate_html_report(tree, issues, matrix, prefixes, coverage, html_path)
    print(f"HTMLレポート: {html_path}")

    # 局所トレーサビリティビューを自動生成
    _generate_local_views(tree, output_dir)

    if args.json:
        total_items = sum(len(list(d)) for d in tree)
        reviewed_items = sum(
            1 for d in tree for item in d
            if item.reviewed
        )
        summary = {
            "timestamp": datetime.now().isoformat(),
            "documents": {doc.prefix: len(list(doc)) for doc in tree},
            "groups": sorted({get_group(item) for doc in tree for item in doc}),
            "review_status": {"total": total_items, "reviewed": reviewed_items},
            "issues": issues,
            "coverage": coverage,
        }
        json_path = os.path.join(output_dir, "validation_summary.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=list)
        print(f"JSONサマリ: {json_path}")

    # コンソールサマリ
    total_items = sum(len(list(d)) for d in tree)
    reviewed_items = sum(
        1 for d in tree for item in d
        if item.reviewed
    )
    groups = sorted({get_group(item) for doc in tree for item in doc})

    print("\n===== バリデーション結果 =====")
    print(f"ドキュメント: {', '.join(d.prefix for d in tree)}")
    print(f"総アイテム数: {total_items}")
    print(f"機能グループ: {', '.join(groups)}")
    print(f"レビュー済: {reviewed_items}/{total_items}")
    print(f"エラー: {len(issues['errors'])}件  警告: {len(issues['warnings'])}件")

    if issues["errors"]:
        print("\n[エラー]")
        for e in issues["errors"]:
            print(f"  ✗ {e}")
    if issues["warnings"]:
        print("\n[警告]")
        for w in issues["warnings"]:
            print(f"  ⚠ {w}")
    if issues["info"]:
        print("\n[情報]")
        for i in issues["info"]:
            print(f"  ℹ {i}")

    print("\n[カバレッジ]")
    for pair, data in coverage.items():
        mark = "✓" if data["percentage"] == 100 else "△" if data["percentage"] >= 50 else "✗"
        print(f"  {mark} {pair}: {data['covered']}/{data['total']} ({data['percentage']}%)")
        if data.get("by_group"):
            for g, gd in data["by_group"].items():
                gm = "✓" if gd["percentage"] == 100 else "△" if gd["percentage"] >= 50 else "✗"
                print(f"      {gm} [{g}] {gd['covered']}/{gd['total']} ({gd['percentage']}%)")

    if args.serve:
        _serve_report(html_path, tree, port=args.port, strict=args.strict)
    else:
        sys.exit(1 if issues["errors"] else 0)


if __name__ == "__main__":
    main()
