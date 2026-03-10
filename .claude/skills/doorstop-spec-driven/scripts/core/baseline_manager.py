#!/usr/bin/env python3
"""ベースライン管理スクリプト。

仕様のベースライン（スナップショット）を作成・一覧・差分表示する。
ベースラインはすべてのアクティブアイテムの現時点フィンガープリントを
JSON形式で記録し、バージョン間の差分追跡を可能にする。

ベースラインの保存場所: <specification-root>/.baselines/<name>.json

Usage:
    python baseline_manager.py <project-dir> create <name> [--tag] [--tag-name TAG]
    python baseline_manager.py <project-dir> list
    python baseline_manager.py <project-dir> diff <baseline1> <baseline2>
    python baseline_manager.py <project-dir> diff <baseline1> HEAD

Examples:
    python baseline_manager.py . create v1.0 --tag
    python baseline_manager.py . create sprint-3
    python baseline_manager.py . list
    python baseline_manager.py . diff v1.0 v2.0
    python baseline_manager.py . diff v1.0 HEAD
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import doorstop
except ImportError:
    from _common import out
    out({"ok": False, "error": "doorstop がインストールされていません"})
    sys.exit(1)

from _common import out, get_groups, get_priority


# ---------------------------------------------------------------------------
# Baseline Storage
# ---------------------------------------------------------------------------

BASELINES_DIR = ".baselines"


def _baselines_root(tree) -> Path:
    """ベースライン保存ディレクトリを返す。ツリーのルートを基準とする。"""
    # ツリーの最初のドキュメントのpathの親から2階層上がプロジェクトルート
    for doc in tree:
        doc_path = Path(str(doc.path))
        # .doorstop.yml がある親ディレクトリ
        spec_root = doc_path.parent
        return spec_root / BASELINES_DIR
    return Path(BASELINES_DIR)


def _baseline_path(baselines_root: Path, name: str) -> Path:
    return baselines_root / f"{name}.json"


def _git_current_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _git_tag(tag_name: str) -> bool:
    try:
        subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", f"Doorstop baseline: {tag_name}"],
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ---------------------------------------------------------------------------
# Snapshot: 現在のツリー状態をキャプチャ
# ---------------------------------------------------------------------------

def _snapshot_item(item, prefix: str) -> dict:
    """アイテムをスナップショット形式のdictに変換する。"""
    groups = get_groups(item)
    priority = get_priority(item)
    return {
        "uid": str(item.uid),
        "prefix": prefix,
        "header": item.header or "",
        "text_snippet": item.text.strip()[:80] if item.text else "",
        "groups": groups,
        "priority": priority,
        "active": item.active,
        "normative": bool(item.get("normative", True)),
        "stamp": item.stamp() or "",
        "reviewed": str(item.reviewed) if item.reviewed else None,
    }


def _take_snapshot(tree) -> dict:
    """ツリー全体のスナップショットを取得する。"""
    items = {}
    for doc in tree:
        prefix = doc.prefix
        for item in doc:
            uid = str(item.uid)
            items[uid] = _snapshot_item(item, prefix)
    return items


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_create(tree, args):
    """ベースラインを作成する。"""
    name = args.name
    baselines_root = _baselines_root(tree)
    baselines_root.mkdir(parents=True, exist_ok=True)
    path = _baseline_path(baselines_root, name)

    if path.exists() and not args.force:
        out({
            "ok": False,
            "error": f"ベースライン '{name}' は既に存在します。--force で上書きできます。",
        })
        return

    # Gitコミット取得
    git_commit = _git_current_commit()

    # Gitタグ付け
    git_tag = None
    if args.tag:
        tag_name = args.tag_name or name
        if _git_tag(tag_name):
            git_tag = tag_name
        else:
            print(f"WARNING: git tag '{tag_name}' の作成に失敗しました。", file=sys.stderr)

    # スナップショット取得
    snapshot = _take_snapshot(tree)
    active_count = sum(1 for v in snapshot.values() if v["active"])
    normative_count = sum(1 for v in snapshot.values() if v["active"] and v["normative"])

    baseline = {
        "name": name,
        "created_at": datetime.now().isoformat(),
        "git_commit": git_commit,
        "git_tag": git_tag,
        "summary": {
            "total_items": len(snapshot),
            "active_items": active_count,
            "normative_items": normative_count,
        },
        "items": snapshot,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)

    out({
        "ok": True,
        "action": "create",
        "name": name,
        "path": str(path),
        "git_commit": git_commit,
        "git_tag": git_tag,
        "summary": baseline["summary"],
    })


def cmd_list(tree, args):
    """ベースライン一覧を表示する。"""
    baselines_root = _baselines_root(tree)

    if not baselines_root.exists():
        out({"ok": True, "action": "list", "baselines": []})
        return

    baselines = []
    for path in sorted(baselines_root.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            baselines.append({
                "name": data.get("name", path.stem),
                "created_at": data.get("created_at"),
                "git_commit": data.get("git_commit"),
                "git_tag": data.get("git_tag"),
                "summary": data.get("summary", {}),
            })
        except (json.JSONDecodeError, KeyError):
            baselines.append({"name": path.stem, "error": "読み込み失敗"})

    out({"ok": True, "action": "list", "count": len(baselines), "baselines": baselines})


def cmd_diff(tree, args):
    """2つのベースライン間の差分を表示する。"""
    baselines_root = _baselines_root(tree)

    # base ロード
    base_name = args.baseline1
    base_path = _baseline_path(baselines_root, base_name)
    if not base_path.exists():
        out({"ok": False, "error": f"ベースライン '{base_name}' が見つかりません"})
        return
    with open(base_path, encoding="utf-8") as f:
        base_data = json.load(f)
    base_items = base_data["items"]

    # target ロード（HEAD の場合は現在のツリー）
    target_name = args.baseline2
    if target_name.upper() == "HEAD":
        target_items = _take_snapshot(tree)
        target_meta = {
            "name": "HEAD",
            "git_commit": _git_current_commit(),
            "created_at": datetime.now().isoformat(),
        }
    else:
        target_path = _baseline_path(baselines_root, target_name)
        if not target_path.exists():
            out({"ok": False, "error": f"ベースライン '{target_name}' が見つかりません"})
            return
        with open(target_path, encoding="utf-8") as f:
            target_data = json.load(f)
        target_items = target_data["items"]
        target_meta = {
            "name": target_data.get("name"),
            "git_commit": target_data.get("git_commit"),
            "created_at": target_data.get("created_at"),
        }

    # 差分計算
    base_uids = set(base_items.keys())
    target_uids = set(target_items.keys())

    added = []        # target に存在し base に存在しない
    removed = []      # base に存在し target に存在しない
    changed = []      # 両方に存在し stamp が変わった
    unchanged = []    # 両方に存在し stamp が同じ

    for uid in sorted(target_uids - base_uids):
        item = target_items[uid]
        if item["active"] and item["normative"]:
            added.append(item)

    for uid in sorted(base_uids - target_uids):
        item = base_items[uid]
        if item["active"] and item["normative"]:
            removed.append(item)

    for uid in sorted(base_uids & target_uids):
        b = base_items[uid]
        t = target_items[uid]
        if not (t["active"] and t["normative"]):
            continue
        if b["stamp"] != t["stamp"]:
            changed.append({
                "uid": uid,
                "prefix": t["prefix"],
                "header": t["header"],
                "groups": t["groups"],
                "priority": t["priority"],
                "base_stamp": b["stamp"][:8] if b["stamp"] else "",
                "target_stamp": t["stamp"][:8] if t["stamp"] else "",
                "text_changed": b["text_snippet"] != t["text_snippet"],
                "base_reviewed": b["reviewed"],
                "target_reviewed": t["reviewed"],
            })
        else:
            unchanged.append(uid)

    out({
        "ok": True,
        "action": "diff",
        "base": {"name": base_name, "git_commit": base_data.get("git_commit"), "created_at": base_data.get("created_at")},
        "target": target_meta,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": len(unchanged),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Doorstop ベースライン管理")
    parser.add_argument("project_dir", help="プロジェクトルートディレクトリ")
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="ベースラインを作成する")
    p_create.add_argument("name", help="ベースライン名（例: v1.0, sprint-3）")
    p_create.add_argument("--tag", action="store_true", help="Git タグを付ける")
    p_create.add_argument("--tag-name", default=None, help="Git タグ名（省略時はベースライン名を使用）")
    p_create.add_argument("--force", action="store_true", help="既存ベースラインを上書き")

    # list
    sub.add_parser("list", help="ベースライン一覧を表示する")

    # diff
    p_diff = sub.add_parser("diff", help="2つのベースライン間の差分を表示する")
    p_diff.add_argument("baseline1", help="比較元ベースライン名")
    p_diff.add_argument("baseline2", help="比較先ベースライン名（HEAD で現在の状態と比較）")

    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    try:
        tree = doorstop.build()
    except Exception as e:
        out({"ok": False, "error": f"ツリー構築失敗: {e}"})
        return

    cmd_map = {
        "create": cmd_create,
        "list": cmd_list,
        "diff": cmd_diff,
    }
    cmd_map[args.command](tree, args)


if __name__ == "__main__":
    main()
