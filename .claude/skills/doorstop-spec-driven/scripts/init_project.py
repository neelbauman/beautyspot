#!/usr/bin/env python3
"""Doorstop仕様駆動開発プロジェクトの初期化スクリプト。

プロファイルに基づいてドキュメントツリーを作成する。

Profiles:
  lite     — REQ → SPEC → IMPL/TST（小規模開発、デフォルト）
  standard — REQ → ARCH → SPEC → IMPL/TST（中規模開発）
  full     — REQ → HLD → LLD → IMPL/TST（大規模開発、V字モデル準拠）

Usage:
    python init_project.py <project-dir> [--profile lite|standard|full] [--docs-dir ./specification] [--digits 3]
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml


def run(cmd, cwd=None):
    """コマンドを実行し、結果を返す。"""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {' '.join(cmd)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def is_git_repo(path):
    """指定パスがgitリポジトリかどうか判定する。"""
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=path,
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def load_profile(profile_name):
    """プロファイルYAMLを読み込む。"""
    profiles_dir = Path(__file__).parent.parent / "profiles"
    profile_path = profiles_dir / f"{profile_name}.yml"

    if not profile_path.exists():
        available = [p.stem for p in profiles_dir.glob("*.yml")]
        print(
            f"ERROR: プロファイル '{profile_name}' が見つかりません。"
            f" 利用可能: {', '.join(sorted(available))}",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(profile_path) as f:
        return yaml.safe_load(f)


def _configure_attributes(yml_path, is_req_or_nfr=False, is_adr=False):
    """doorstop create で生成された .doorstop.yml に attributes セクションを追加する。

    defaults / reviewed / publish を設定する。
    REQ/NFR ドキュメントでは priority を reviewed に追加し、
    優先度変更が再レビューをトリガーするようにする。
    ADR ドキュメントでは status を追加する。
    """
    with open(yml_path) as f:
        config = yaml.safe_load(f)

    reviewed_attrs = ["groups"]
    publish_attrs = ["groups"]
    defaults = {"groups": []}

    if is_req_or_nfr:
        reviewed_attrs.append("priority")
        publish_attrs.append("priority")
        defaults["priority"] = "medium"

    if is_adr:
        reviewed_attrs.append("status")
        publish_attrs.append("status")
        defaults["status"] = "accepted"

    config["attributes"] = {
        "defaults": defaults,
        "reviewed": reviewed_attrs,
        "publish": publish_attrs,
    }

    with open(yml_path, "w") as f:
        yaml.dump(
            config, f, default_flow_style=False, allow_unicode=True, sort_keys=False
        )


def main():
    parser = argparse.ArgumentParser(
        description="Doorstop仕様駆動開発プロジェクトを初期化する"
    )
    parser.add_argument("project_dir", help="プロジェクトのルートディレクトリ")
    parser.add_argument(
        "--profile",
        default="lite",
        choices=["lite", "standard", "full"],
        help="ドキュメント階層のプロファイル（デフォルト: lite）",
    )
    parser.add_argument(
        "--digits", type=int, default=3, help="アイテムUIDの桁数（デフォルト: 3）"
    )
    parser.add_argument(
        "--separator", default="", help="プレフィックスと番号の区切り文字（デフォルト: なし）"
    )
    parser.add_argument(
        "--docs-dir",
        default="./specification",
        help="ドキュメントツリーのベースディレクトリ（デフォルト: ./specification）",
    )
    parser.add_argument(
        "--no-git-init",
        action="store_true",
        help="gitリポジトリの初期化をスキップする",
    )
    parser.add_argument(
        "--with-nfr",
        action="store_true",
        help="非機能要件（NFR）ドキュメントを作成する（standard/full推奨）",
    )
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.makedirs(project_dir, exist_ok=True)

    # Git初期化
    if not args.no_git_init and not is_git_repo(project_dir):
        print(f"Gitリポジトリを初期化: {project_dir}")
        run(["git", "init"], cwd=project_dir)
        run(["git", "commit", "--allow-empty", "-m", "Initial commit"], cwd=project_dir)
    elif not is_git_repo(project_dir):
        print(
            "ERROR: gitリポジトリではありません。"
            "--no-git-initを外すか、先にgit initしてください。",
            file=sys.stderr,
        )
        sys.exit(1)

    # プロファイル読み込み
    profile = load_profile(args.profile)
    print(f"プロファイル: {profile['name']} — {profile['description'].strip().splitlines()[0]}")

    digits = str(args.digits)
    sep_args = ["--separator", args.separator] if args.separator else []
    docs_dir = args.docs_dir

    # ドキュメントツリー作成
    for doc in profile["tree"]:
        prefix = doc["prefix"]
        path = f"{docs_dir}/{doc['path']}"
        parent = doc.get("parent")

        cmd = ["doorstop", "create", prefix, path, "-d", digits]
        if parent:
            cmd += ["--parent", parent]
        cmd += sep_args

        print(f"  ドキュメント作成: {prefix}（{doc['role']}）")
        run(cmd, cwd=project_dir)

        # .doorstop.yml に attributes セクションを追加
        yml_path = Path(project_dir) / docs_dir / doc["path"] / ".doorstop.yml"
        is_req_or_nfr = prefix in ("REQ", "NFR")
        is_adr = prefix == "ADR"
        _configure_attributes(yml_path, is_req_or_nfr=is_req_or_nfr, is_adr=is_adr)
        print("    attributes 設定完了")

    # NFR ドキュメント作成（オプション）
    if args.with_nfr:
        nfr_path = f"{docs_dir}/nfr"
        cmd = ["doorstop", "create", "NFR", nfr_path, "-d", digits]
        cmd += sep_args
        print("  ドキュメント作成: NFR（非機能要件）")
        run(cmd, cwd=project_dir)
        yml_path = Path(project_dir) / nfr_path / ".doorstop.yml"
        _configure_attributes(yml_path, is_req_or_nfr=True)
        print("    attributes 設定完了（NFR: parent=null, priority を reviewed に含む）")

    # 検証
    print("\n--- ドキュメントツリー ---")
    output = run(["doorstop"], cwd=project_dir)
    print(output)

    # 次のステップ表示
    print(f"\nプロジェクトを初期化しました: {project_dir}")
    print(f"プロファイル: {args.profile}\n")

    print("ドキュメント階層:")
    _print_tree(profile["tree"])

    print("\n次のステップ:")
    for doc in profile["tree"]:
        print(f"  doorstop add {doc['prefix']:4s}  →  {doc['role']}")

    if profile.get("guidance", {}).get("test_levels"):
        print("\nテストレベル属性:")
        print("  item.set('test_level', 'unit')         # 単体テスト")
        print("  item.set('test_level', 'integration')  # 結合テスト")
        print("  item.set('test_level', 'acceptance')   # 受入テスト")

    print("\n機能グループと優先度の設定:")
    print("  doorstop_ops.py add -d REQ -t '要件' -g AUTH --priority high")
    print("  # 優先度: critical / high / medium（デフォルト） / low / none / done")

    if args.with_nfr:
        print("\nNFR ドキュメントが作成されました:")
        print("  doorstop_ops.py add -d NFR -t '非機能要件' -g PERF --priority high")
        print("  設計ドキュメント（ARCH/SPEC）はNFRアイテムへリンクして制約を明示できます")

    print("\nトリアージ（優先度確認）:")
    print("  trace_query.py . backlog               # REQ を優先度順に表示")
    print("  trace_query.py . backlog --all-docs    # 全ドキュメントを優先度順に表示")


def _print_tree(tree_defs):
    """ツリー構造を視覚的に表示する。"""
    # parent → children のマップを構築
    children = {}
    roots = []
    for doc in tree_defs:
        parent = doc.get("parent")
        if parent is None:
            roots.append(doc)
        else:
            children.setdefault(parent, []).append(doc)

    def _print_node(doc, indent=""):
        prefix = doc["prefix"]
        role = doc["role"]
        print(f"{indent}{prefix}（{role}）")
        kids = children.get(prefix, [])
        for i, kid in enumerate(kids):
            is_last = i == len(kids) - 1
            connector = "└── " if is_last else "├── "
            _print_node(kid, indent + connector if not indent else indent.rstrip("└── ├── ") + ("    " if is_last else "│   ") + connector)

    # シンプルなインデント表示
    for doc in tree_defs:
        depth = _get_depth(doc, tree_defs)
        # indent = "    " * depth
        prefix = "└── " if depth > 0 else ""
        # 同じ親を持つ兄弟の最後かどうか
        parent = doc.get("parent")
        siblings = [d for d in tree_defs if d.get("parent") == parent]
        if len(siblings) > 1 and doc != siblings[-1]:
            prefix = "├── " if depth > 0 else ""
        print(f"  {'│   ' * max(0, depth - 1)}{prefix}{doc['prefix']}（{doc['role']}）")


def _get_depth(doc, tree_defs):
    """ツリー内でのドキュメントの深度を計算する。"""
    depth = 0
    parent = doc.get("parent")
    while parent:
        depth += 1
        parent_doc = next((d for d in tree_defs if d["prefix"] == parent), None)
        parent = parent_doc.get("parent") if parent_doc else None
    return depth


if __name__ == "__main__":
    main()
