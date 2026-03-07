#!/usr/bin/env python3
"""Doorstop仕様駆動開発プロジェクトの初期化スクリプト。

SYS → SRD → TST の3階層ドキュメントツリーを作成する。

Usage:
    python init_project.py <project-dir> [--docs-dir ./reqs] [--digits 3] [--separator ""] [--no-git-init]
"""

import argparse
import os
import subprocess
import sys


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


def main():
    parser = argparse.ArgumentParser(
        description="Doorstop仕様駆動開発プロジェクトを初期化する"
    )
    parser.add_argument("project_dir", help="プロジェクトのルートディレクトリ")
    parser.add_argument(
        "--digits", type=int, default=3, help="アイテムUIDの桁数（デフォルト: 3）"
    )
    parser.add_argument(
        "--separator", default="", help="プレフィックスと番号の区切り文字（デフォルト: なし）"
    )
    parser.add_argument(
        "--docs-dir",
        default="./reqs",
        help="ドキュメントツリーのベースディレクトリ（デフォルト: ./reqs）",
    )
    parser.add_argument(
        "--no-git-init",
        action="store_true",
        help="gitリポジトリの初期化をスキップする",
    )
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.makedirs(project_dir, exist_ok=True)

    # Git初期化
    if not args.no_git_init and not is_git_repo(project_dir):
        print(f"Gitリポジトリを初期化: {project_dir}")
        run(["git", "init"], cwd=project_dir)
        # 最低1つのコミットが必要
        run(["git", "commit", "--allow-empty", "-m", "Initial commit"], cwd=project_dir)
    elif not is_git_repo(project_dir):
        print("ERROR: gitリポジトリではありません。--no-git-initを外すか、先にgit initしてください。", file=sys.stderr)
        sys.exit(1)

    digits = str(args.digits)
    sep_args = ["--separator", args.separator] if args.separator else []

    # ドキュメント階層の定義
    docs_dir = args.docs_dir
    documents = [
        {
            "prefix": "REQ",
            "path": f"{docs_dir}/req",
            "parent": None,
            "desc": "要件（What: 何を実現するか）",
        },
        {
            "prefix": "SPEC",
            "path": f"{docs_dir}/spec",
            "parent": "REQ",
            "desc": "仕様（How: どう実現するか）",
        },
        {
            "prefix": "IMPL",
            "path": f"{docs_dir}/impl",
            "parent": "SPEC",
            "desc": "実装（Build: 何を作ったか）",
        },
        {
            "prefix": "TST",
            "path": f"{docs_dir}/tst",
            "parent": "SPEC",
            "desc": "テスト（Verify: どう検証するか）",
        },
    ]

    for doc in documents:
        cmd = ["doorstop", "create", doc["prefix"], doc["path"], "-d", digits]
        if doc["parent"]:
            cmd += ["--parent", doc["parent"]]
        cmd += sep_args

        print(f"ドキュメント作成: {doc['prefix']}（{doc['desc']}）")
        run(cmd, cwd=project_dir)

    # 検証
    print("\n--- ドキュメントツリー ---")
    output = run(["doorstop"], cwd=project_dir)
    print(output)

    print(f"\nプロジェクトを初期化しました: {project_dir}")
    print("次のステップ:")
    print("  1. doorstop add REQ    →  要件を追加（What: 何を実現するか）")
    print("  2. doorstop add SPEC   →  仕様を追加（How: どう実現するか）")
    print("  3. doorstop add IMPL   →  実装を追加（Build: 何を作ったか）")
    print("  4. doorstop add TST    →  テストを追加（Verify: どう検証するか）")
    print("  5. doorstop link SPEC001 REQ001  →  トレーサビリティリンクを設定")
    print()
    print("機能グループの設定（Python API）:")
    print("  item.set('group', 'AUTH')  # AUTH, PAY, USR など")
    print("  item.save()")


if __name__ == "__main__":
    main()
