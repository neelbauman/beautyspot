#!/usr/bin/env python3
"""変更影響分析スクリプト。

変更されたDoorstopアイテムを起点に、トレーサビリティリンクを上流・下流に
たどって影響範囲を特定し、必要な対応アクションを提示する。

検出方式:
  --changed UID [UID...]    手動でアイテムUIDを指定
  --detect-suspects         Doorstopのsuspectリンクから自動検出
  --from-git [--base REF]   Git diffから変更されたYAMLファイルを自動検出

出力形式:
  コンソール出力（デフォルト）
  --json PATH               JSON形式で出力
  --html PATH               HTML形式で出力

Usage:
    python impact_analysis.py <project-dir> --detect-suspects
    python impact_analysis.py <project-dir> --from-git --base main
    python impact_analysis.py <project-dir> --changed SPEC001 SPEC002
    python impact_analysis.py <project-dir> --detect-suspects --json ./reports/impact.json
"""

import argparse
import html as html_mod
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

try:
    import doorstop
except ImportError:
    print("ERROR: doorstop がインストールされていません。", file=sys.stderr)
    sys.exit(1)

from _common import (
    get_groups, get_ref, find_item as find_item_in_tree,
    find_doc_prefix as _find_doc_prefix, build_link_index,
    build_doc_file_map,
)


# ---------------------------------------------------------------------------
# Detection: 変更アイテムの検出
# ---------------------------------------------------------------------------

def detect_by_uid(tree, uids):
    """手動指定されたUIDからアイテムを取得する。"""
    changed = []
    for uid in uids:
        item = find_item_in_tree(tree, uid)
        if item:
            changed.append(item)
        else:
            print(f"WARNING: UID '{uid}' が見つかりません。", file=sys.stderr)
    return changed


def detect_suspects(tree):
    """suspectリンクを持つアイテムから、変更された親アイテムを検出する。

    返すのは「変更された親アイテム」（suspectの原因側）。
    """
    changed_uids = set()
    for doc in tree:
        for item in doc:
            for link in item.links:
                uid_str = str(link)
                parent_item = find_item_in_tree(tree, uid_str)
                if parent_item is None:
                    continue
                is_suspect = (
                    link.stamp is not None
                    and link.stamp != ""
                    and link.stamp != parent_item.stamp()
                )
                if is_suspect:
                    changed_uids.add(uid_str)

    return [find_item_in_tree(tree, uid) for uid in sorted(changed_uids)]


def detect_from_git(tree, project_dir, base_ref=None):
    """Git diffから変更されたDoorstopアイテムを検出する。"""
    if base_ref:
        cmd = ["git", "diff", base_ref, "--name-only"]
    else:
        cmd = ["git", "diff", "HEAD", "--name-only"]

    try:
        result = subprocess.run(
            cmd, cwd=project_dir, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError:
        result = subprocess.run(
            ["git", "diff", "--staged", "--name-only"],
            cwd=project_dir, capture_output=True, text=True
        )

    changed_files = [f.replace("\\", "/") for f in result.stdout.strip().split("\n") if f]

    # ドキュメントツリーの実際のパスからマッピングを構築
    file_to_uid = build_doc_file_map(tree, project_dir)

    changed = []
    for filepath in changed_files:
        uid_str = file_to_uid.get(filepath)
        if uid_str:
            item = find_item_in_tree(tree, uid_str)
            if item:
                changed.append(item)
    return changed


# ---------------------------------------------------------------------------
# Analysis: 影響範囲の分析
# ---------------------------------------------------------------------------

def analyze_impact(tree, changed_items):
    """変更されたアイテムの影響範囲を分析する。"""
    children_idx, parents_idx = build_link_index(tree)

    results = []
    for item in changed_items:
        uid = str(item.uid)
        doc_prefix = _find_doc_prefix(tree, item)

        # 上流追跡（この変更の原因）
        upstream = []
        _trace_upstream(uid, parents_idx, upstream, visited=set())

        # 下流追跡（この変更の影響先）
        downstream = []
        _trace_downstream(uid, children_idx, downstream, visited=set())

        # suspect判定
        suspect_children = []
        for child_item, child_prefix in children_idx.get(uid, []):
            for link in child_item.links:
                if str(link) == uid:
                    is_suspect = (
                        link.stamp is not None
                        and link.stamp != ""
                        and link.stamp != item.stamp()
                    )
                    if is_suspect:
                        suspect_children.append({
                            "uid": str(child_item.uid),
                            "prefix": child_prefix,
                            "groups": get_groups(child_item),
                            "text": child_item.text.strip()[:100],
                            "ref": get_ref(child_item),
                        })

        # アクション生成
        actions = _generate_actions(item, doc_prefix, downstream, suspect_children)

        results.append({
            "uid": uid,
            "prefix": doc_prefix,
            "groups": get_groups(item),
            "text": item.text.strip()[:120],
            "ref": get_ref(item),
            "upstream": upstream,
            "downstream": downstream,
            "suspect_children": suspect_children,
            "actions": actions,
        })

    return results


def _trace_upstream(uid, parents_idx, result, visited, depth=0):
    if uid in visited or depth > 10:
        return
    visited.add(uid)
    for parent_item, parent_prefix in parents_idx.get(uid, []):
        parent_uid = str(parent_item.uid)
        entry = {
            "uid": parent_uid,
            "prefix": parent_prefix,
            "groups": get_groups(parent_item),
            "text": parent_item.text.strip()[:100],
            "depth": depth,
        }
        result.append(entry)
        _trace_upstream(parent_uid, parents_idx, result, visited, depth + 1)


def _trace_downstream(uid, children_idx, result, visited, depth=0):
    if uid in visited or depth > 10:
        return
    visited.add(uid)
    for child_item, child_prefix in children_idx.get(uid, []):
        child_uid = str(child_item.uid)
        entry = {
            "uid": child_uid,
            "prefix": child_prefix,
            "groups": get_groups(child_item),
            "text": child_item.text.strip()[:100],
            "ref": get_ref(child_item),
            "depth": depth,
        }
        result.append(entry)
        _trace_downstream(child_uid, children_idx, result, visited, depth + 1)


def _generate_actions(changed_item, doc_prefix, downstream, suspects):
    """対応アクションリストを生成する。"""
    actions = []

    # suspectアイテムに対するアクション
    for s in suspects:
        if s["prefix"] == "IMPL":
            actions.append(
                f"{s['uid']} の実装を確認・修正し、doorstop clear {s['uid']} でsuspect解消"
            )
        elif s["prefix"] == "TST":
            actions.append(
                f"{s['uid']} のテストを確認・修正し、doorstop clear {s['uid']} でsuspect解消"
            )
        else:
            actions.append(
                f"{s['uid']} を確認し、doorstop clear {s['uid']} でsuspect解消"
            )

    # 下流にIMPL/TSTがあるがsuspectでない場合（新規リンクや未レビュー等）
    suspect_uids = {s["uid"] for s in suspects}
    for d in downstream:
        if d["uid"] not in suspect_uids:
            if d["prefix"] in ("IMPL", "TST"):
                actions.append(f"{d['uid']} の内容が変更と整合しているか確認")

    # 変更アイテム自体のレビュー
    actions.append(f"{str(changed_item.uid)} を doorstop review {str(changed_item.uid)} でレビュー済みに更新")

    return actions


# ---------------------------------------------------------------------------
# Output: コンソール
# ---------------------------------------------------------------------------

def print_console(results, tree):
    """コンソールに影響分析結果を出力する。"""
    if not results:
        print("変更されたアイテムは検出されませんでした。")
        return

    print(f"\n{'='*60}")
    print("  変更影響分析レポート")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  変更アイテム: {len(results)}件")
    print(f"{'='*60}")

    for r in results:
        print(f"\n{'─'*60}")
        print(f"■ {r['uid']} [{'/'.join(r.get('groups', ['?']))}] ({r['prefix']})")
        print(f"  {r['text']}")
        if r["ref"]:
            print(f"  ref: {r['ref']}")

        if r["upstream"]:
            print("\n  [上流 ← なぜ変わった？]")
            for u in r["upstream"]:
                indent = "    " + "  " * u["depth"]
                print(f"{indent}← {u['uid']} [{'/'.join(u.get('groups', ['?']))}] ({u['prefix']})")
                print(f"{indent}  {u['text']}")

        if r["downstream"] or r["suspect_children"]:
            print("\n  [下流 → 何に影響する？]")
            for d in r["downstream"]:
                indent = "    " + "  " * d["depth"]
                suspect_mark = " ⚠ suspect" if d["uid"] in {s["uid"] for s in r["suspect_children"]} else ""
                print(f"{indent}→ {d['uid']} [{'/'.join(d.get('groups', ['?']))}] ({d['prefix']}){suspect_mark}")
                print(f"{indent}  {d['text']}")
                if d.get("ref"):
                    print(f"{indent}  ref: {d['ref']}")

        if r["actions"]:
            print("\n  [対応アクション]")
            for i, action in enumerate(r["actions"], 1):
                print(f"    {i}. {action}")

    # グループ別サマリ
    group_impact = defaultdict(lambda: {"changed": 0, "suspect": 0, "affected": 0})
    for r in results:
        for g in r["groups"]:
            group_impact[g]["changed"] += 1
        for s in r["suspect_children"]:
            for g in s["groups"]:
                group_impact[g]["suspect"] += 1
        for d in r["downstream"]:
            for g in d["groups"]:
                group_impact[g]["affected"] += 1

    print(f"\n{'─'*60}")
    print("[グループ別影響サマリ]")
    for g, data in sorted(group_impact.items()):
        print(f"  {g}: 変更={data['changed']}  suspect={data['suspect']}  影響={data['affected']}")

    print()


# ---------------------------------------------------------------------------
# Output: JSON
# ---------------------------------------------------------------------------

def write_json(results, output_path):
    """JSON形式で影響分析結果を出力する。"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "changed_items": len(results),
            "total_suspects": sum(len(r["suspect_children"]) for r in results),
            "total_downstream": sum(len(r["downstream"]) for r in results),
            "total_actions": sum(len(r["actions"]) for r in results),
        },
        "impacts": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"JSON出力: {output_path}")


# ---------------------------------------------------------------------------
# Output: HTML
# ---------------------------------------------------------------------------

def write_html(results, output_path):
    """HTML形式で影響分析レポートを出力する。"""
    h = html_mod.escape
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_suspects = sum(len(r["suspect_children"]) for r in results)
    total_downstream = sum(len(r["downstream"]) for r in results)
    total_actions = sum(len(r["actions"]) for r in results)

    # グループ別サマリ
    group_impact = defaultdict(lambda: {"changed": 0, "suspect": 0, "affected": 0})
    for r in results:
        for g in r["groups"]:
            group_impact[g]["changed"] += 1
        for s in r["suspect_children"]:
            for g in s["groups"]:
                group_impact[g]["suspect"] += 1
        for d in r["downstream"]:
            for g in d["groups"]:
                group_impact[g]["affected"] += 1

    group_rows = ""
    for g, d in sorted(group_impact.items()):
        group_rows += f"<tr><td><span class='group-tag'>{h(g)}</span></td>"
        group_rows += f"<td>{d['changed']}</td><td>{d['suspect']}</td><td>{d['affected']}</td></tr>"

    # 変更アイテム詳細
    impact_cards = ""
    for r in results:
        # 上流
        upstream_html = ""
        if r["upstream"]:
            items_html = ""
            for u in r["upstream"]:
                items_html += (
                    f"<div class='trace-item' style='margin-left:{u['depth']*20}px'>"
                    f"← <strong>{h(u['uid'])}</strong> "
                    f"<span class='group-tag'>{h('/'.join(u.get('groups', ['?'])))}</span> "
                    f"<span class='prefix-tag'>{h(u['prefix'])}</span>"
                    f"<br><span class='text-preview'>{h(u['text'])}</span></div>"
                )
            upstream_html = f"<h4>上流 ← なぜ変わった？</h4>{items_html}"

        # 下流
        suspect_uids = {s["uid"] for s in r["suspect_children"]}
        downstream_html = ""
        if r["downstream"]:
            items_html = ""
            for d in r["downstream"]:
                suspect_cls = " suspect" if d["uid"] in suspect_uids else ""
                suspect_badge = " <span class='suspect-badge'>⚠ suspect</span>" if d["uid"] in suspect_uids else ""
                ref_html = f"<br><span class='ref-tag'>{h(d.get('ref', ''))}</span>" if d.get("ref") else ""
                items_html += (
                    f"<div class='trace-item{suspect_cls}' style='margin-left:{d['depth']*20}px'>"
                    f"→ <strong>{h(d['uid'])}</strong> "
                    f"<span class='group-tag'>{h('/'.join(d.get('groups', ['?'])))}</span> "
                    f"<span class='prefix-tag'>{h(d['prefix'])}</span>"
                    f"{suspect_badge}"
                    f"<br><span class='text-preview'>{h(d['text'])}</span>"
                    f"{ref_html}</div>"
                )
            downstream_html = f"<h4>下流 → 何に影響する？</h4>{items_html}"

        # アクション
        actions_html = ""
        if r["actions"]:
            al = "".join(f"<li>{h(a)}</li>" for a in r["actions"])
            actions_html = f"<h4>対応アクション</h4><ol>{al}</ol>"

        ref_html = f"<br><span class='ref-tag'>{h(r['ref'])}</span>" if r["ref"] else ""

        _r_groups_str = '/'.join(r.get('groups', ['?']))
        impact_cards += f"""
        <div class="impact-card" data-group="{h(_r_groups_str)}">
            <div class="impact-header">
                <strong>{h(r['uid'])}</strong>
                <span class="group-tag">{h(_r_groups_str)}</span>
                <span class="prefix-tag">{h(r['prefix'])}</span>
            </div>
            <div class="impact-body">
                <p>{h(r['text'])}{ref_html}</p>
                {upstream_html}
                {downstream_html}
                {actions_html}
            </div>
        </div>"""

    report_html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>変更影響分析レポート</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1200px; margin: 0 auto; padding: 20px; background: #fafafa; }}
  h1 {{ border-bottom: 3px solid #e65100; padding-bottom: 10px; color: #e65100; }}
  h2 {{ color: #e65100; margin-top: 30px; }}
  h4 {{ margin: 12px 0 6px; color: #555; font-size: 0.95em; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; background: #fff; }}
  th {{ background: #e65100; color: #fff; padding: 8px 12px; text-align: left; }}
  td {{ border: 1px solid #ddd; padding: 8px 12px; }}
  .summary {{ display: flex; gap: 15px; margin: 15px 0; flex-wrap: wrap; }}
  .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
           padding: 15px 20px; flex: 1; min-width: 100px; text-align: center; }}
  .card h3 {{ margin: 0 0 5px; font-size: 0.85em; color: #666; }}
  .card .value {{ font-size: 1.6em; font-weight: bold; color: #e65100; }}
  .timestamp {{ color: #999; font-size: 0.85em; }}
  .group-tag {{ display: inline-block; background: #e3f2fd; color: #1565c0; padding: 2px 8px;
                border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
  .prefix-tag {{ display: inline-block; background: #f3e5f5; color: #7b1fa2; padding: 2px 6px;
                 border-radius: 3px; font-size: 0.75em; }}
  .ref-tag {{ display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 1px 6px;
              border-radius: 3px; font-size: 0.75em; font-family: monospace; }}
  .suspect-badge {{ background: #fff3e0; color: #e65100; padding: 1px 6px; border-radius: 3px;
                    font-size: 0.8em; font-weight: bold; }}
  .impact-card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
                  margin: 15px 0; overflow: hidden; }}
  .impact-header {{ background: #fff3e0; padding: 12px 16px; border-bottom: 1px solid #ddd; }}
  .impact-body {{ padding: 12px 16px; }}
  .trace-item {{ padding: 6px 10px; margin: 4px 0; border-left: 3px solid #ddd; }}
  .trace-item.suspect {{ border-left-color: #e65100; background: #fff8e1; }}
  .text-preview {{ color: #666; font-size: 0.85em; }}
  ol {{ padding-left: 20px; }}
  li {{ margin: 4px 0; }}
</style>
</head>
<body>
<h1>変更影響分析レポート</h1>
<p class="timestamp">生成日時: {now}</p>

<div class="summary">
  <div class="card">
    <h3>変更アイテム</h3>
    <div class="value">{len(results)}</div>
  </div>
  <div class="card">
    <h3>Suspect</h3>
    <div class="value" style="color:{'#e65100' if total_suspects else '#4caf50'}">{total_suspects}</div>
  </div>
  <div class="card">
    <h3>影響先</h3>
    <div class="value">{total_downstream}</div>
  </div>
  <div class="card">
    <h3>要アクション</h3>
    <div class="value">{total_actions}</div>
  </div>
</div>

<h2>グループ別影響サマリ</h2>
<table>
<tr><th>グループ</th><th>変更</th><th>Suspect</th><th>影響先</th></tr>
{group_rows}
</table>

<h2>変更アイテム詳細</h2>
{impact_cards}

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    print(f"HTMLレポート: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Doorstop変更影響分析")
    parser.add_argument("project_dir", help="プロジェクトのルートディレクトリ")

    # 検出方式（複数同時指定可）
    detect = parser.add_argument_group("検出方式")
    detect.add_argument("--changed", nargs="+", metavar="UID",
                        help="変更されたアイテムのUIDを手動指定")
    detect.add_argument("--detect-suspects", action="store_true",
                        help="suspectリンクから変更アイテムを自動検出")
    detect.add_argument("--from-git", action="store_true",
                        help="Git diffから変更アイテムを自動検出")
    detect.add_argument("--base", default=None, metavar="REF",
                        help="Git diff の比較元（デフォルト: HEAD）")

    # 出力形式
    output = parser.add_argument_group("出力形式")
    output.add_argument("--json", metavar="PATH", dest="json_path",
                        help="JSON形式で出力するファイルパス")
    output.add_argument("--html", metavar="PATH", dest="html_path",
                        help="HTML形式で出力するファイルパス")

    args = parser.parse_args()

    # 検出方式が1つも指定されていない場合
    if not args.changed and not args.detect_suspects and not args.from_git:
        parser.error("検出方式を少なくとも1つ指定してください: "
                     "--changed, --detect-suspects, --from-git")

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    print("ドキュメントツリーを構築中...")
    tree = doorstop.build()

    # 変更アイテムを収集（複数方式を統合、重複排除）
    changed_map = {}  # uid -> item

    if args.changed:
        print(f"手動指定: {', '.join(args.changed)}")
        for item in detect_by_uid(tree, args.changed):
            changed_map[str(item.uid)] = item

    if args.detect_suspects:
        print("suspectリンクを検出中...")
        for item in detect_suspects(tree):
            changed_map[str(item.uid)] = item

    if args.from_git:
        base_label = args.base or "HEAD"
        print(f"Git diff ({base_label}) から検出中...")
        for item in detect_from_git(tree, project_dir, args.base):
            changed_map[str(item.uid)] = item

    changed_items = list(changed_map.values())
    print(f"変更アイテム: {len(changed_items)}件")

    if not changed_items:
        print("変更されたアイテムは検出されませんでした。")
        return

    # 影響分析
    print("影響範囲を分析中...")
    results = analyze_impact(tree, changed_items)

    # 出力
    print_console(results, tree)

    if args.json_path:
        json_path = os.path.join(project_dir, args.json_path)
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        write_json(results, json_path)

    if args.html_path:
        html_path = os.path.join(project_dir, args.html_path)
        os.makedirs(os.path.dirname(html_path), exist_ok=True)
        write_html(results, html_path)


if __name__ == "__main__":
    main()
