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
    python impact_analysis.py <project-dir> --detect-suspects --json ./specification/reports/impact.json
"""

import argparse
import os
import subprocess
import sys

try:
    import doorstop
except ImportError:
    from _common import out
    out({"ok": False, "error": "doorstop がインストールされていません"})

from _common import (
    out, get_groups, get_ref, get_references, truncate_text,
    find_item as find_item_in_tree,
    find_doc_prefix as _find_doc_prefix, build_link_index,
    build_doc_file_map,
)
from impact_output import print_console, write_json, write_html


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

def analyze_impact(tree, changed_items, project_dir="."):
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
                            "text": truncate_text(child_item.text.strip(), 100),
                            "ref": get_ref(child_item),
                        })

        # アクション生成（人間向け + 機械向け）
        actions = _generate_actions(item, doc_prefix, downstream, suspect_children)
        action_plan = _generate_action_plan(
            item, doc_prefix, downstream, suspect_children, project_dir
        )

        results.append({
            "uid": uid,
            "prefix": doc_prefix,
            "groups": get_groups(item),
            "text": truncate_text(item.text.strip(), 120),
            "ref": get_ref(item),
            "references": get_references(item),
            "upstream": upstream,
            "downstream": downstream,
            "suspect_children": suspect_children,
            "actions": actions,
            "action_plan": action_plan,
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
            "text": truncate_text(parent_item.text.strip(), 100),
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
            "text": truncate_text(child_item.text.strip(), 100),
            "ref": get_ref(child_item),
            "references": get_references(child_item),
            "depth": depth,
        }
        result.append(entry)
        _trace_downstream(child_uid, children_idx, result, visited, depth + 1)


def _generate_actions(changed_item, doc_prefix, downstream, suspects):
    """対応アクションリストを生成する。"""
    actions = []

    # 1. 変更アイテム自体のレビュー（SDD原則: まず仕様を確定させる）
    actions.append(f"{str(changed_item.uid)} を doorstop review {str(changed_item.uid)} でレビュー済みに更新")

    # 2. suspectアイテムに対するアクション（仕様確定後の実装・テスト修正）
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

    # 3. 下流にIMPL/TSTがあるがsuspectでない場合（新規リンクや未レビュー等）
    suspect_uids = {s["uid"] for s in suspects}
    for d in downstream:
        if d["uid"] not in suspect_uids:
            if d["prefix"] in ("IMPL", "TST"):
                actions.append(f"{d['uid']} の内容が変更と整合しているか確認")

    return actions


def _generate_action_plan(changed_item, doc_prefix, downstream, suspects, project_dir):
    """エージェントが直接実行できる構造化アクションプランを生成する。

    返却値:
        {
            "review_commands": [...],   # レビュー系コマンド
            "clear_commands": [...],    # suspect解消コマンド
            "files_to_check": [...],    # 確認すべきファイルパス
            "validation": "..."         # 最終検証コマンド
        }
    """
    # script_dir = os.path.dirname(os.path.abspath(__file__))
    # ops = os.path.join(script_dir, "doorstop_ops.py")
    # validate = os.path.join(os.path.dirname(script_dir), "reporting", "validate_and_report.py")

    uid = str(changed_item.uid)
    review_commands = []
    clear_commands = []
    files_to_check = set()

    # 1. 変更アイテム自体のレビュー
    review_commands.append(f"doorstop_ops.py {project_dir} review {uid}")

    # 2. 変更アイテムの references
    for ref in get_references(changed_item):
        path = ref.get("path", "")
        if path:
            files_to_check.add(path)

    # 3. suspect アイテムの解消
    suspect_uids = []
    for s in suspects:
        suspect_uids.append(s["uid"])
        # suspect の references を確認対象に追加
        for ref in s.get("references", []):
            path = ref.get("path", "")
            if path:
                files_to_check.add(path)
        # ref フォールバック
        if s.get("ref"):
            files_to_check.add(s["ref"])

    if suspect_uids:
        clear_commands.append(
            f"doorstop_ops.py {project_dir} chain-clear {uid}"
        )
        review_commands.append(
            f"doorstop_ops.py {project_dir} chain-review {uid}"
        )

    # 4. 下流の非suspect IMPL/TST のファイルも確認対象に
    suspect_uid_set = set(suspect_uids)
    for d in downstream:
        if d["uid"] not in suspect_uid_set and d["prefix"] in ("IMPL", "TST"):
            for ref in d.get("references", []):
                path = ref.get("path", "")
                if path:
                    files_to_check.add(path)
            if d.get("ref"):
                files_to_check.add(d["ref"])

    return {
        "review_commands": review_commands,
        "clear_commands": clear_commands,
        "files_to_check": sorted(files_to_check),
        "validation": f"validate_and_report.py {project_dir} --strict",
    }


def _auto_execute(results, project_dir):
    """action_plan の review/clear コマンドを自動実行する。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ops_script = os.path.join(script_dir, "doorstop_ops.py")

    executed = []
    errors = []

    for r in results:
        ap = r.get("action_plan", {})
        # uid = r["uid"]

        # clear を先に実行（suspect 解消）
        for cmd_str in ap.get("clear_commands", []):
            parts = cmd_str.split()
            # "doorstop_ops.py <dir> chain-clear <UID>" の形式
            if len(parts) >= 4:
                subcmd = parts[2]  # chain-clear
                target_uids = parts[3:]
                real_cmd = [
                    sys.executable, ops_script, project_dir, subcmd
                ] + target_uids
                try:
                    _ = subprocess.run(
                        real_cmd, capture_output=True, text=True, check=True
                    )
                    executed.append(cmd_str)
                    print(f"  ✓ {cmd_str}")
                except subprocess.CalledProcessError as e:
                    errors.append({"command": cmd_str, "error": e.stderr.strip()})
                    print(f"  ✗ {cmd_str}: {e.stderr.strip()}")

        # review を実行
        for cmd_str in ap.get("review_commands", []):
            parts = cmd_str.split()
            if len(parts) >= 4:
                subcmd = parts[2]
                target_uids = parts[3:]
                real_cmd = [
                    sys.executable, ops_script, project_dir, subcmd
                ] + target_uids
                try:
                    _ = subprocess.run(
                        real_cmd, capture_output=True, text=True, check=True
                    )
                    executed.append(cmd_str)
                    print(f"  ✓ {cmd_str}")
                except subprocess.CalledProcessError as e:
                    errors.append({"command": cmd_str, "error": e.stderr.strip()})
                    print(f"  ✗ {cmd_str}: {e.stderr.strip()}")

    print(f"\n自動実行完了: {len(executed)}件成功, {len(errors)}件失敗")
    if errors:
        for e in errors:
            print(f"  失敗: {e['command']} — {e['error']}")


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

    # 自動実行
    auto = parser.add_argument_group("自動実行")
    auto.add_argument("--auto-execute", action="store_true",
                      help="推奨アクション（review/clear）を自動実行する")

    args = parser.parse_args()

    # 検出方式が1つも指定されていない場合
    if not args.changed and not args.detect_suspects and not args.from_git:
        parser.error("検出方式を少なくとも1つ指定してください: "
                     "--changed, --detect-suspects, --from-git")

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    print("ドキュメントツリーを構築中...")
    try:
        tree = doorstop.build()
    except Exception as e:
        out({"ok": False, "error": f"ツリー構築失敗: {e}"})
        return

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
    results = analyze_impact(tree, changed_items, project_dir)

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

    # 自動実行: review/clear コマンドを実行
    if args.auto_execute:
        _auto_execute(results, project_dir)


if __name__ == "__main__":
    main()
