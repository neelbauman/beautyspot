"""Doorstop操作ヘルパーパッケージ — エージェント向けの単一コマンドインターフェース。

コマンドグループ:
  [CRUD]     add, update, reorder, link, unlink  → crud.py
  [活性化]   activate, deactivate,
             activate-chain, deactivate-chain    → lifecycle.py
  [レビュー] clear, review,
             chain-review, chain-clear           → review.py
  [照会]     list, groups, tree, find            → query.py
"""
import argparse
import os
import sys

_CORE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

try:
    import doorstop
except ImportError:
    import json
    print(json.dumps({"ok": False, "error": "doorstop がインストールされていません"}))
    sys.exit(1)

from _common import out  # noqa: E402
from .crud import cmd_add, cmd_update, cmd_reorder, cmd_link, cmd_unlink  # noqa: E402
from .lifecycle import cmd_activate, cmd_deactivate, cmd_activate_chain, cmd_deactivate_chain  # noqa: E402
from .review import cmd_clear, cmd_review, cmd_chain_review, cmd_chain_clear  # noqa: E402
from .query import cmd_list, cmd_groups, cmd_tree, cmd_find  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Doorstop操作ヘルパー")
    parser.add_argument("project_dir", help="プロジェクトルート")
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="アイテム追加")
    p_add.add_argument("-d", "--document", required=True, help="ドキュメント（REQ/SPEC/IMPL/TST）")
    p_add.add_argument("-t", "--text", required=True, help="テキスト")
    p_add.add_argument("--header", help="ヘッダー")
    p_add.add_argument("-g", "--group", help="機能グループ")
    p_add.add_argument("-l", "--level", help="レベル")
    p_add.add_argument("--insert", help="指定したレベルに挿入し、以降を自動で後ろにずらす（--level と同じ挙動）")
    p_add.add_argument("-r", "--ref", help="参照ファイルパス")
    p_add.add_argument("--references", help='外部ファイル紐付け（JSON文字列。例: \'[{"path":"src/mod.py","type":"file"}]\'）')
    p_add.add_argument("--priority", choices=["critical", "high", "medium", "low", "none", "done"],
                       help="優先度（REQ/NFR に設定を推奨）")
    p_add.add_argument("--test-level", choices=["unit", "integration", "acceptance"],
                       help="テスト粒度（TST に設定。standard/full プロファイル用）")
    p_add.add_argument("--non-normative", action="store_true", help="非規範的アイテム（見出し等）として追加")
    p_add.add_argument("--derived", action="store_true", help="派生要求として追加")
    p_add.add_argument("--gherkin", help="Gherkin シナリオ（Given/When/Then 形式の振る舞い記述）")
    p_add.add_argument("--links", nargs="*", help="リンク先UID")

    # update
    p_upd = sub.add_parser("update", help="アイテム更新")
    p_upd.add_argument("uid", help="更新対象UID")
    p_upd.add_argument("-t", "--text", help="新テキスト")
    p_upd.add_argument("--header", help="新ヘッダー")
    p_upd.add_argument("-g", "--group", help="新グループ")
    p_upd.add_argument("-r", "--ref", help="新参照パス")
    p_upd.add_argument("--references", help='外部ファイル紐付け（JSON文字列）')
    p_upd.add_argument("--priority", choices=["critical", "high", "medium", "low", "none", "done"],
                       help="優先度の変更")
    p_upd.add_argument("--test-level", choices=["unit", "integration", "acceptance"],
                       help="テスト粒度の変更（TST 用）")
    p_upd.add_argument("--gherkin", help="Gherkin シナリオ（Given/When/Then 形式の振る舞い記述）")
    p_upd.add_argument("--set-normative", action="store_true", help="規範的アイテムに設定")
    p_upd.add_argument("--set-non-normative", action="store_true", help="非規範的アイテムに設定")

    # reorder
    p_reorder = sub.add_parser("reorder", help="アイテムのレベルを変更し、他を自動で再配置する")
    p_reorder.add_argument("uid", help="対象UID")
    p_reorder.add_argument("level", help="新しいレベル")

    # link
    p_link = sub.add_parser("link", help="リンク追加")
    p_link.add_argument("child", help="子アイテムUID")
    p_link.add_argument("parent", help="親アイテムUID")

    # unlink
    p_unlink = sub.add_parser("unlink", help="リンク削除")
    p_unlink.add_argument("child", help="子アイテムUID")
    p_unlink.add_argument("parent", help="削除する親リンクUID")

    # deactivate
    p_deact = sub.add_parser("deactivate", help="アイテム非活性化（active: false）")
    p_deact.add_argument("uids", nargs="+", help="対象UID")

    # activate
    p_act = sub.add_parser("activate", help="アイテム活性化（active: true）")
    p_act.add_argument("uids", nargs="+", help="対象UID")

    # deactivate-chain
    p_deact_chain = sub.add_parser("deactivate-chain", help="リンクチェーン全体を非活性化")
    p_deact_chain.add_argument("uid", help="起点UID")
    p_deact_chain.add_argument("--force", action="store_true",
                               help="他に活性な親があっても強制的に非活性化")

    # activate-chain
    p_act_chain = sub.add_parser("activate-chain", help="リンクチェーン全体を活性化")
    p_act_chain.add_argument("uid", help="起点UID")

    # clear
    p_clear = sub.add_parser("clear", help="suspect解消")
    p_clear.add_argument("uids", nargs="+", help="対象UID")

    # review
    p_review = sub.add_parser("review", help="レビュー済み")
    p_review.add_argument("uids", nargs="+", help="対象UID")

    # chain-review
    p_chain_review = sub.add_parser("chain-review", help="アイテムとその祖先（上流）を一括でレビュー済みにする")
    p_chain_review.add_argument("uids", nargs="+", help="対象UID")

    # chain-clear
    p_chain_clear = sub.add_parser("chain-clear", help="アイテムとその子孫（下流）のsuspectを一括解消する")
    p_chain_clear.add_argument("uids", nargs="+", help="対象UID")

    # list
    p_list = sub.add_parser("list", help="一覧取得")
    p_list.add_argument("-d", "--document", help="ドキュメント絞り込み")
    p_list.add_argument("-g", "--group", help="グループ絞り込み")

    # groups
    sub.add_parser("groups", help="グループ一覧")

    # tree
    sub.add_parser("tree", help="ツリー構造")

    # find
    p_find = sub.add_parser("find", help="テキスト検索")
    p_find.add_argument("query", help="検索クエリ")

    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    try:
        tree = doorstop.build()
    except Exception as e:
        out({"ok": False, "error": f"ツリー構築失敗: {e}"})
        return

    cmd_map = {
        "add": cmd_add,
        "update": cmd_update,
        "reorder": cmd_reorder,
        "link": cmd_link,
        "unlink": cmd_unlink,
        "deactivate": cmd_deactivate,
        "activate": cmd_activate,
        "deactivate-chain": cmd_deactivate_chain,
        "activate-chain": cmd_activate_chain,
        "clear": cmd_clear,
        "review": cmd_review,
        "chain-review": cmd_chain_review,
        "chain-clear": cmd_chain_clear,
        "list": cmd_list,
        "groups": cmd_groups,
        "tree": cmd_tree,
        "find": cmd_find,
    }

    cmd_map[args.command](tree, args)


if __name__ == "__main__":
    main()
