"""属性フィルタ付き高機能検索コマンド。

含まれるコマンド:
  search  テキスト検索（正規表現対応）＋多軸フィルタリング
"""
import re

from _common import (
    out, get_groups, get_priority, is_derived,
    is_normative, is_suspect, build_link_index, item_summary,
)


def cmd_search(tree, args):
    """属性フィルタ付き高機能検索。

    テキスト検索（正規表現対応）に加え、ドキュメント・グループ・
    suspect・unreviewed・gherkin有無・優先度・derived で絞り込める。
    """
    children_idx, _ = build_link_index(tree)

    # 正規表現パターンのコンパイル
    pattern = None
    if args.pattern:
        try:
            pattern = re.compile(args.pattern, re.IGNORECASE)
        except re.error as e:
            out({"ok": False, "error": f"正規表現エラー: {e}"})

    # フィルタ条件の解析
    filter_groups = []
    if args.group:
        filter_groups = [g.strip() for g in args.group.split(",") if g.strip()]

    filter_priorities = []
    if args.priority:
        filter_priorities = [p.strip() for p in args.priority.split(",") if p.strip()]

    filter_docs = []
    if args.document:
        filter_docs = [d.strip() for d in args.document.split(",") if d.strip()]

    results = []
    for doc in tree:
        # ドキュメントフィルタ
        if filter_docs and doc.prefix not in filter_docs:
            continue

        for item in doc:
            if not item.active:
                continue
            if not is_normative(item):
                continue

            # グループフィルタ
            if filter_groups:
                item_groups = get_groups(item)
                if not any(fg in item_groups for fg in filter_groups):
                    continue

            # 優先度フィルタ
            if filter_priorities:
                if get_priority(item) not in filter_priorities:
                    continue

            # suspect フィルタ
            if args.suspect and not is_suspect(item, tree):
                continue

            # unreviewed フィルタ
            if args.unreviewed and item.reviewed:
                continue

            # derived フィルタ
            if args.derived and not is_derived(item):
                continue

            # gherkin フィルタ
            if args.has_gherkin:
                gherkin = item.get("gherkin") if hasattr(item, "get") else None
                if not gherkin:
                    continue

            # テキストパターンフィルタ（text + header を対象）
            if pattern:
                text = (item.text or "") + " " + (item.header or "")
                # gherkin も検索対象に含める
                if hasattr(item, "get"):
                    g = item.get("gherkin")
                    if g and isinstance(g, str):
                        text += " " + g
                if not pattern.search(text):
                    continue

            results.append(item_summary(item, doc.prefix, tree))

    out({
        "ok": True,
        "action": "search",
        "pattern": args.pattern,
        "filters": {
            "document": filter_docs or None,
            "group": filter_groups or None,
            "priority": filter_priorities or None,
            "suspect": args.suspect,
            "unreviewed": args.unreviewed,
            "has_gherkin": args.has_gherkin,
            "derived": args.derived,
        },
        "count": len(results),
        "items": results,
    })
