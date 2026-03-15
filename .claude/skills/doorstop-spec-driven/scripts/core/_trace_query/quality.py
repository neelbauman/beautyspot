"""品質・バックログ照会コマンド。

含まれるコマンド:
  suspects  全suspect一覧と要対応アクション
  backlog   優先度順のバックログ一覧（トリアージ用）
"""

from _common import (
    out, get_groups, get_priority, get_references, is_normative,
    is_suspect, find_item, find_doc_prefix, build_link_index, truncate_text,
)


def _suggest_action(item, prefix):
    """suspectアイテムに対する推奨アクションを生成する。"""
    uid = str(item.uid)
    refs = get_references(item)
    ref_str = ", ".join(r["path"] for r in refs) if refs else ""
    if prefix == "IMPL":
        base = f"{uid} の実装を確認・修正"
        if ref_str:
            base += f"（{ref_str}）"
        return base + f" → doorstop clear {uid}"
    elif prefix == "TST":
        base = f"{uid} のテストを確認・修正"
        if ref_str:
            base += f"（{ref_str}）"
        return base + f" → doorstop clear {uid}"
    elif prefix == "SPEC":
        return f"{uid} の仕様が親REQの変更と整合するか確認 → doorstop clear {uid}"
    else:
        return f"{uid} を確認 → doorstop clear {uid}"


def cmd_suspects(tree, args):
    """全suspect一覧と要対応アクション。"""
    children_idx, _ = build_link_index(tree)
    suspects = []

    # グループフィルタの解析
    filter_groups = []
    if args.group:
        filter_groups = [g.strip() for g in args.group.split(",") if g.strip()]

    for doc in tree:
        for item in doc:
            if not is_normative(item):
                continue
            if filter_groups:
                item_groups = get_groups(item)
                if not any(fg in item_groups for fg in filter_groups):
                    continue
            if not is_suspect(item, tree):
                continue

            # どのリンクがsuspectか特定
            suspect_links = []
            for link in item.links:
                parent = find_item(tree, str(link))
                if parent is None:
                    continue
                if (
                    link.stamp is not None
                    and link.stamp != ""
                    and link.stamp != parent.stamp()
                ):
                    suspect_links.append({
                        "parent_uid": str(link),
                        "parent_prefix": find_doc_prefix(tree, parent),
                        "parent_text": truncate_text(parent.text.strip(), 100),
                    })

            action = _suggest_action(item, doc.prefix)

            suspects.append({
                "uid": str(item.uid),
                "prefix": doc.prefix,
                "groups": get_groups(item),
                "text": truncate_text(item.text.strip(), 120),
                "references": get_references(item),
                "suspect_links": suspect_links,
                "action": action,
            })

    out({
        "ok": True,
        "action": "suspects",
        "group_filter": args.group,
        "count": len(suspects),
        "items": suspects,
    })


def cmd_backlog(tree, args):
    """REQ（および任意のドキュメント）のアイテムを優先度順に一覧表示する。

    priority 属性の値に基づいてソートする:
        critical > high > medium > low > (未設定 = medium 扱い)
    """
    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4, "done": 5}

    # グループフィルタ
    filter_groups = []
    if args.group:
        filter_groups = [g.strip() for g in args.group.split(",") if g.strip()]

    # ドキュメントフィルタ（デフォルト: REQ のみ）
    target_docs = [args.document] if args.document else ["REQ"]
    if args.all_docs:
        target_docs = None  # 全ドキュメント

    items = []
    children_idx, _ = build_link_index(tree)

    for doc in tree:
        if target_docs and doc.prefix not in target_docs:
            continue
        for item in doc:
            if not item.active:
                continue
            if not is_normative(item):
                continue
            if filter_groups:
                item_groups = get_groups(item)
                if not any(fg in item_groups for fg in filter_groups):
                    continue

            uid = str(item.uid)
            priority = get_priority(item)
            coverage_ok = bool(children_idx.get(uid))  # 子アイテムが存在するか

            items.append({
                "uid": uid,
                "prefix": doc.prefix,
                "header": item.header or "",
                "groups": get_groups(item),
                "priority": priority,
                "has_children": coverage_ok,
                "text": truncate_text(item.text.strip(), 100),
            })

    # 優先度→UID順にソート
    items.sort(key=lambda x: (PRIORITY_ORDER.get(x["priority"], 2), x["uid"]))

    # 優先度別集計
    priority_summary = {}
    for p in ("critical", "high", "medium", "low", "none", "done"):
        priority_summary[p] = sum(1 for i in items if i["priority"] == p)

    out({
        "ok": True,
        "action": "backlog",
        "document_filter": target_docs,
        "group_filter": args.group,
        "count": len(items),
        "priority_summary": priority_summary,
        "items": items,
    })
