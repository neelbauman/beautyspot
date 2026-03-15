#!/usr/bin/env python3
"""Doorstopプロジェクトのバリデーションとトレーサビリティレポート生成。

構造検証、リンク整合性、ref存在チェック、機能グループ別カバレッジ、
レビュー状態の追跡を行い、HTMLトレーサビリティレポートを出力する。

Usage:
    python validate_and_report.py <project-dir> [--output-dir ./specification/reports] [--strict] [--json]
"""

import argparse
import json
import os
import sys
from datetime import datetime

try:
    import doorstop
except ImportError:
    from scripts.core._common import out
    out({"ok": False, "error": "doorstop がインストールされていません"})

from ..core._common import out
from ..core.validator import validate_tree, build_traceability_matrix, compute_coverage
from ..server.serve_app import serve
from ..reporting.html_builder import (
    h,
    get_groups,
    is_normative,
    detect_suspect_uids,
    build_children_map,
    build_matrix_cell,
    build_detail_card,
    assemble_html,
)
from .local_trace_view import (
    build_link_index,
    collect_chains_by_group,
    trace_full_chain,
    generate_local_html,
    get_all_groups,
    _generate_index,
)



# ---------------------------------------------------------------------------
# HTML Report Generation
# ---------------------------------------------------------------------------

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

    with open(f"{os.path.dirname(output_path)}/.gitignore", "w", encoding="utf-8") as f:
        f.write("*")

    all_groups = sorted({g for doc in tree for item in doc if item.active for g in get_groups(item) if g != "(未分類)"})
    suspect_uids = detect_suspect_uids(tree)

    # レビュー統計
    total_items = sum(1 for d in tree for item in d if item.active and is_normative(item))
    reviewed_items = sum(1 for d in tree for item in d if item.active and item.reviewed and is_normative(item))
    suspect_count = len(suspect_uids)

    # --- Body sections ---

    # Group filter buttons
    group_buttons = ''.join(
        f'<button class="group-btn" data-group="{h(g)}" onclick="toggleGroup(this)">{h(g)}</button>'
        for g in all_groups
    )

    # Coverage table rows
    coverage_rows = ""
    for pair, data in coverage.items():
        color = _color(data["percentage"])
        uncovered_str = ", ".join(data["uncovered_items"]) if data["uncovered_items"] else "\u2014"
        coverage_rows += f"""
        <tr class="coverage-total">
            <td><strong>{h(pair)}</strong></td>
            <td>\u2014</td>
            <td>{data['covered']} / {data['total']}</td>
            <td style="color:{color}; font-weight:bold">{data['percentage']}%</td>
            <td style="font-size:0.85em">{h(uncovered_str)}</td>
        </tr>"""
        for g, gd in data.get("by_group", {}).items():
            gc = _color(gd["percentage"])
            gu = ", ".join(gd["uncovered_items"]) if gd["uncovered_items"] else "\u2014"
            coverage_rows += f"""
        <tr class="coverage-group" data-group="{h(g)}">
            <td style="padding-left:30px">{h(pair)}</td>
            <td><span class="group-tag">{h(g)}</span></td>
            <td>{gd['covered']} / {gd['total']}</td>
            <td style="color:{gc}; font-weight:bold">{gd['percentage']}%</td>
            <td style="font-size:0.85em">{h(gu)}</td>
        </tr>"""

    # Issue section
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

    # Matrix header
    header_cells = '<th class="sortable" onclick="sortMatrix(0)" data-col="0">グループ<span class="sort-arrow">▲▼</span></th>'
    for i, p in enumerate(prefixes, 1):
        header_cells += f'<th class="sortable" onclick="sortMatrix({i})" data-col="{i}">{h(p)}<span class="sort-arrow">▲▼</span></th>'

    # Matrix rows
    matrix_rows = ""
    for row in matrix:
        groups = row.get("_groups", ["(未分類)"])
        group_tags = " ".join(f'<span class="group-tag">{h(g)}</span>' for g in groups)
        row_uids = []
        row_statuses = set()
        cells = f'<td data-sort-key="{groups[0]}">{group_tags}</td>'
        for prefix in prefixes:
            item = row.get(prefix)
            if item:
                td, uid_str, statuses = build_matrix_cell(
                    item, suspect_uids, include_sort_key=True,
                )
                cells += td
                row_uids.append(uid_str)
                row_statuses |= statuses
            else:
                cells += '<td data-sort-key="" class="empty">\u2014</td>'
        uids_attr = h(" ".join(row_uids))
        statuses_attr = h(" ".join(sorted(row_statuses)))
        matrix_rows += (
            f'<tr data-groups="{h(" ".join(groups))}" data-uids="{uids_attr}" '
            f'data-statuses="{statuses_attr}">{cells}</tr>'
        )

    # Children map & detail cards
    children_map = build_children_map(tree)
    item_detail_section = ""
    for doc in tree:
        for item in doc:
            if not item.active:
                continue
            groups = get_groups(item)
            safe_group = groups[0].replace("/", "_").replace(" ", "_").replace("(", "").replace(")", "") if groups else "none"
            local_view_href = f"local/trace_{safe_group}.html#detail-{item.uid}"
            item_detail_section += build_detail_card(
                item, doc_prefix=None, suspect_uids=suspect_uids,
                children_map=children_map, tree=tree,
                local_view_href=local_view_href,
            )

    # Assemble body
    body = f"""
<h1>トレーサビリティレポート</h1>
<p class="timestamp">生成日時: {now}</p>

<div class="summary">
  <div class="card"><h3>ドキュメント</h3><div class="value">{len(list(tree))}</div></div>
  <div class="card"><h3>総アイテム</h3><div class="value">{total_items}</div></div>
  <div class="card"><h3>グループ</h3><div class="value">{len(all_groups)}</div></div>
  <div class="card"><h3>レビュー済</h3><div class="value">{reviewed_items}/{total_items}</div></div>
  <div class="card"><h3>Suspect</h3><div class="value" style="color:{'#e65100' if suspect_count else '#4caf50'}">{suspect_count}</div></div>
  <div class="card"><h3>エラー</h3><div class="value" style="color:{'#d32f2f' if issues['errors'] else '#4caf50'}">{len(issues['errors'])}</div></div>
  <div class="card"><h3>警告</h3><div class="value" style="color:{'#f57c00' if issues['warnings'] else '#4caf50'}">{len(issues['warnings'])}</div></div>
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
  <input type="text" class="id-search" id="id-search" placeholder="例: SPEC001, REQ00" oninput="applyFilters()">
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
"""

    report_html = assemble_html(
        title="トレーサビリティレポート",
        css_files=["common.css", "report.css"],
        body=body,
        js_files=["common.js", "actions.js", "filters.js"],
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    return output_path


# ---------------------------------------------------------------------------
# Local views & server delegation
# ---------------------------------------------------------------------------

def _generate_local_views(tree, output_dir):
    """局所トレーサビリティビューをグループごとに自動生成する。"""
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
    serve(tree, os.getcwd(), port=port, strict=strict)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Doorstopプロジェクトのバリデーションとレポート生成"
    )
    parser.add_argument("project_dir", help="プロジェクトのルートディレクトリ")
    parser.add_argument("--output-dir", default="./specification/reports", help="レポート出力先")
    parser.add_argument("--strict", action="store_true",
                        help="全ての親アイテムに子リンクがあることを要求する")
    parser.add_argument("--json", action="store_true", help="JSON形式でもサマリを出力する")
    parser.add_argument("--serve", action="store_true",
                        help="ローカルサーバーを起動（Review/Clearボタンが有効になる）")
    parser.add_argument("--port", type=int, default=8080, help="サーバーポート (default: 8080)")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    try:
        tree = doorstop.build()
    except Exception as e:
        out({"ok": False, "error": f"ツリー構築失敗: {e}"})
        return

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
        total_items = sum(1 for d in tree for item in d if item.active and is_normative(item))
        reviewed_items = sum(
            1 for d in tree for item in d
            if item.active and item.reviewed and is_normative(item)
        )
        summary = {
            "timestamp": datetime.now().isoformat(),
            "documents": {doc.prefix: len([i for i in doc if i.active and is_normative(i)]) for doc in tree},
            "groups": sorted({get_groups(item) for doc in tree for item in doc if item.active}),
            "review_status": {"total": total_items, "reviewed": reviewed_items},
            "issues": issues,
            "coverage": coverage,
        }
        json_path = os.path.join(output_dir, "validation_summary.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=list)
        print(f"JSONサマリ: {json_path}")

    # コンソールサマリ
    total_items = sum(1 for d in tree for item in d if item.active and is_normative(item))
    reviewed_items = sum(
        1 for d in tree for item in d
        if item.active and item.reviewed and is_normative(item)
    )
    groups = sorted({g for doc in tree for item in doc if item.active for g in get_groups(item) if g != "(未分類)"})

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
