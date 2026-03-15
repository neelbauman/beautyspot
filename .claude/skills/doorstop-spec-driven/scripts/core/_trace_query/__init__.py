"""AIコーディングエージェント向けトレーサビリティ照会CLIパッケージ。

コマンドグループ:
  [概況]    status, coverage, gaps   → status.py
  [トレース] chain, context,
             related-files           → chain.py
  [検索]    search                   → search.py
  [品質]    suspects, backlog        → quality.py
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
    from _common import out
    out({"ok": False, "error": "doorstop がインストールされていません"})

from _common import out  # noqa: E402
from .chain import cmd_chain, cmd_context, cmd_related_files  # noqa: E402
from .status import cmd_status, cmd_coverage, cmd_gaps  # noqa: E402
from .search import cmd_search  # noqa: E402
from .quality import cmd_suspects, cmd_backlog  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="AIエージェント向けトレーサビリティ照会CLI（JSON出力）"
    )
    parser.add_argument("project_dir", help="プロジェクトルート")
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="プロジェクト全体のサマリ")

    # chain
    p_chain = sub.add_parser("chain", help="UIDの上流→下流チェーン（UID指定またはファイル逆引き）")
    p_chain.add_argument("uid", nargs="?", default=None,
                         help="起点となるUID（--file と排他）")
    p_chain.add_argument("--file", metavar="PATH",
                         help="ファイルパスをreferencesから逆引き。該当するIMPL/TSTアイテムのチェーンを表示")

    # context
    p_ctx = sub.add_parser("context",
                           help="指定UIDの全文脈情報を一括取得（target/upstream/downstream/files/health）")
    p_ctx.add_argument("uid", help="対象UID")

    # related-files
    p_rf = sub.add_parser("related-files",
                          help="関連ファイルパスをドキュメント層別に取得")
    p_rf.add_argument("uid", nargs="?", default=None,
                      help="対象UID（--file と排他）")
    p_rf.add_argument("--file", metavar="PATH",
                      help="ファイルパスをreferencesから逆引き")

    # search
    p_search = sub.add_parser("search",
                              help="属性フィルタ付き高機能検索（正規表現対応）")
    p_search.add_argument("pattern", nargs="?", default=None,
                          help="検索パターン（正規表現、省略時は全件）")
    p_search.add_argument("-d", "--document",
                          help="ドキュメントで絞り込み（カンマ区切りで複数可）")
    p_search.add_argument("-g", "--group",
                          help="グループで絞り込み（カンマ区切りで複数可）")
    p_search.add_argument("--priority",
                          help="優先度で絞り込み（カンマ区切り: critical,high,medium,low）")
    p_search.add_argument("--suspect", action="store_true",
                          help="suspectアイテムのみ")
    p_search.add_argument("--unreviewed", action="store_true",
                          help="未レビューアイテムのみ")
    p_search.add_argument("--has-gherkin", action="store_true",
                          help="gherkin属性を持つアイテムのみ")
    p_search.add_argument("--derived", action="store_true",
                          help="派生要求のみ")

    # coverage
    p_cov = sub.add_parser("coverage", help="カバレッジ詳細")
    p_cov.add_argument("-g", "--group", help="グループで絞り込み")
    p_cov.add_argument("--detail", action="store_true",
                       help="カバー元のマッピングも出力")

    # suspects
    p_sus = sub.add_parser("suspects", help="全suspect一覧")
    p_sus.add_argument("-g", "--group", help="グループで絞り込み")

    # gaps
    p_gap = sub.add_parser("gaps", help="リンク漏れ・ref未設定")
    p_gap.add_argument("-d", "--document", help="ドキュメントで絞り込み")
    p_gap.add_argument("-g", "--group", help="グループで絞り込み")

    # backlog
    p_bl = sub.add_parser("backlog", help="優先度順のバックログ一覧（トリアージ用）")
    p_bl.add_argument("-d", "--document", default=None,
                      help="ドキュメントで絞り込み（デフォルト: REQ）")
    p_bl.add_argument("-g", "--group", help="グループで絞り込み")
    p_bl.add_argument("--all-docs", action="store_true",
                      help="REQ以外のドキュメントも含める")

    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    try:
        tree = doorstop.build()
    except Exception as e:
        out({"ok": False, "error": f"ツリー構築失敗: {e}"})
        return

    cmd_map = {
        "status": cmd_status,
        "chain": cmd_chain,
        "context": cmd_context,
        "related-files": cmd_related_files,
        "search": cmd_search,
        "coverage": cmd_coverage,
        "suspects": cmd_suspects,
        "gaps": cmd_gaps,
        "backlog": cmd_backlog,
    }

    cmd_map[args.command](tree, args)


if __name__ == "__main__":
    main()
