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
  --output-dir DIR       出力先ディレクトリ（default: ./specification/reports/local）
  --json                 JSON形式でも出力

Usage:
    python local_trace_view.py <project-dir> --uid REQ001
    python local_trace_view.py <project-dir> --uid SPEC003 SPEC004
    python local_trace_view.py <project-dir> --group CACHE
    python local_trace_view.py <project-dir> --all
"""

import argparse
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

from .html_builder import (
    h,
    get_groups,
    get_ref,
    find_item,
    detect_suspect_uids,
    build_children_map,
    build_matrix_cell,
    build_detail_card,
    assemble_html,
)


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
            if not item.active:
                continue
            for link in item.links:
                uid_str = str(link)
                parent_item = find_item(tree, uid_str)
                if parent_item and parent_item.active:
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
    """指定グループに属する全アイテムのUID集合を返す。active: falseのアイテムは除外。"""
    uids = set()
    for doc in tree:
        for item in doc:
            if not item.active:
                continue
            if group in get_groups(item):
                uids.add(str(item.uid))
    return uids


def get_all_groups(tree):
    return sorted({g for doc in tree for item in doc if item.active for g in get_groups(item) if g != "(未分類)"})


# ---------------------------------------------------------------------------
# Traceability matrix (local)
# ---------------------------------------------------------------------------

def build_local_matrix(tree, related_uids):
    """related_uidsに含まれるアイテムだけでトレーサビリティマトリクスを構築する。"""
    docs = list(tree)
    prefixes = [d.prefix for d in docs]

    items_by_prefix = defaultdict(list)
    for doc in docs:
        for item in doc:
            if item.active and str(item.uid) in related_uids:
                items_by_prefix[doc.prefix].append(item)

    root_docs = [d for d in docs if not d.parent]
    matrix = []
    for root_doc in root_docs:
        for item in items_by_prefix.get(root_doc.prefix, []):
            row = {root_doc.prefix: item, "_groups": get_groups(item)}
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

        parent_uids = {str(i.uid) for i in parent_doc if i.active and str(i.uid) in related_uids}
        if not parent_uids:
            continue

        covered = set()
        for item in doc:
            if not item.active or str(item.uid) not in related_uids:
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
    suspect_uids = detect_suspect_uids(tree)

    # Children map & stats
    children_map = build_children_map(tree, related_uids=related_uids)

    local_items = []
    for doc in tree:
        for item in doc:
            if item.active and str(item.uid) in related_uids:
                local_items.append((item, doc.prefix))
    total = len(local_items)
    reviewed = sum(1 for item, _ in local_items if item.reviewed)
    suspects_in_view = sum(
        1 for item, _ in local_items if str(item.uid) in suspect_uids
    )
    groups_in_view = sorted({g for item, _ in local_items for g in get_groups(item) if g != "(未分類)"})
    doc_counts = defaultdict(int)
    for item, prefix in local_items:
        doc_counts[prefix] += 1

    # Matrix & coverage
    matrix, prefixes = build_local_matrix(tree, related_uids)
    coverage = compute_local_coverage(tree, related_uids)

    # --- Build HTML pieces ---

    # Doc count cards
    doc_count_cards = ""
    for p in prefixes:
        if doc_counts.get(p, 0) > 0:
            doc_count_cards += f"""
      <div class="card"><h3>{h(p)}</h3><div class="value">{doc_counts[p]}</div></div>"""

    # Coverage rows
    coverage_rows = ""
    for pair, data in coverage.items():
        color = _color(data["percentage"])
        uncov = ", ".join(data["uncovered_items"]) if data["uncovered_items"] else "\u2014"
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
        groups = row.get("_groups", ["(未分類)"])
        group_tags = " ".join(f'<span class="group-tag">{h(g)}</span>' for g in groups)
        cells = f'<td>{group_tags}</td>'
        for prefix in prefixes:
            item = row.get(prefix)
            if item:
                td, _, _ = build_matrix_cell(
                    item, suspect_uids, ref_fn=get_ref,
                )
                cells += td
            else:
                cells += '<td class="empty">\u2014</td>'
        matrix_rows += f'<tr data-groups="{h(" ".join(groups))}">{cells}</tr>'

    # Detail cards
    detail_section = ""
    for doc in tree:
        for item in doc:
            if not item.active:
                continue
            uid_str = str(item.uid)
            if uid_str not in related_uids:
                continue
            detail_section += build_detail_card(
                item, doc_prefix=doc.prefix, suspect_uids=suspect_uids,
                children_map=children_map, tree=tree,
            )

    # Chain navigation
    chain_links = ' '.join(
        f'<a href="#detail-{h(str(item.uid))}">{h(str(item.uid))}</a>'
        for item, _ in local_items
    )

    # Back navigation
    back_nav = ""
    if back_link:
        back_nav = f'<div class="back-nav"><a href="{back_link}">← 全体レポートに戻る</a></div>'

    # Assemble body
    body = f"""
{back_nav}
<h1>局所トレーサビリティビュー <span class="scope-label">{h(label)}</span></h1>
<p class="timestamp">生成日時: {now}</p>

<div class="summary">
  <div class="card"><h3>対象アイテム</h3><div class="value">{total}</div></div>
  {doc_count_cards}
  <div class="card"><h3>レビュー済</h3><div class="value">{reviewed}/{total}</div></div>
  <div class="card"><h3>Suspect</h3><div class="value" style="color:{'#e65100' if suspects_in_view else '#4caf50'}">{suspects_in_view}</div></div>
  <div class="card"><h3>グループ</h3><div class="value">{', '.join(h(g) for g in groups_in_view)}</div></div>
</div>

<div class="chain-nav">
  <strong>アイテム:</strong>
  {chain_links}
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
"""

    report = assemble_html(
        title=f"局所トレーサビリティ — {label}",
        css_files=["common.css", "local.css"],
        body=body,
        js_files=["common.js", "actions.js"],
    )

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
            if not item.active:
                continue
            uid_str = str(item.uid)
            if uid_str not in related_uids:
                continue
            items.append({
                "uid": uid_str,
                "prefix": doc.prefix,
                "groups": get_groups(item),
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
# Index page
# ---------------------------------------------------------------------------

def _generate_index(generated, output_dir):
    """--all 時のインデックスHTMLを生成する。"""
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
    out.add_argument("--output-dir", default="./specification/reports/local",
                     help="出力先ディレクトリ (default: ./specification/reports/local)")
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
        all_groups = get_all_groups(tree)
        print(f"全グループ: {', '.join(all_groups)}")
        for group in all_groups:
            group_uids = collect_chains_by_group(tree, group)
            if not group_uids:
                continue
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


if __name__ == "__main__":
    main()
