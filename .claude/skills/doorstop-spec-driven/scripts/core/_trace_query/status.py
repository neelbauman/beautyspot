"""概況・カバレッジ・ギャップ照会コマンド。

含まれるコマンド:
  status    プロジェクト全体のサマリ（件数・カバレッジ・suspect数）
  coverage  カバレッジ詳細（どのSPECがIMPL/TST未カバーか）
  gaps      リンク漏れ・ref未設定のアイテム一覧
"""
from collections import defaultdict

from _common import (
    out, get_groups, get_references, is_normative, is_suspect,
    find_item, build_link_index, truncate_text,
)


def cmd_status(tree, args):
    """プロジェクト全体のサマリ。"""
    children_idx, _ = build_link_index(tree)

    # ドキュメントごとの統計
    doc_stats = {}
    all_items = []
    suspect_count = 0
    unreviewed_count = 0

    for doc in tree:
        items = [i for i in doc if is_normative(i)]
        reviewed = sum(1 for i in items if i.reviewed)
        suspects = sum(1 for i in items if is_suspect(i, tree))
        suspect_count += suspects
        unreviewed_count += len(items) - reviewed
        doc_stats[doc.prefix] = {
            "count": len(items),
            "reviewed": reviewed,
            "unreviewed": len(items) - reviewed,
            "suspects": suspects,
        }
        all_items.extend((i, doc.prefix) for i in items)

    # カバレッジ
    docs = {doc.prefix: doc for doc in tree}
    coverage = {}
    for doc in tree:
        if not doc.parent or doc.parent not in docs:
            continue
        parent_doc = docs[doc.parent]
        parent_uids = {str(i.uid) for i in parent_doc if is_normative(i)}
        covered = set()
        for item in doc:
            if not is_normative(item):
                continue
            for link in item.links:
                if str(link) in parent_uids:
                    covered.add(str(link))
        total = len(parent_uids)
        pct = round(len(covered) / total * 100, 1) if total > 0 else 100.0
        uncovered = sorted(parent_uids - covered)
        coverage[f"{doc.prefix} -> {doc.parent}"] = {
            "total": total,
            "covered": len(covered),
            "percentage": pct,
            "uncovered_uids": uncovered,
        }

    # グループ
    groups = sorted({g for i, _ in all_items for g in get_groups(i) if g != "(未分類)"})

    out({
        "ok": True,
        "action": "status",
        "documents": doc_stats,
        "total_items": sum(d["count"] for d in doc_stats.values()),
        "total_suspects": suspect_count,
        "total_unreviewed": unreviewed_count,
        "coverage": coverage,
        "groups": groups,
    })


def cmd_coverage(tree, args):
    """カバレッジ詳細。"""
    docs = {doc.prefix: doc for doc in tree}
    result = {}

    # グループフィルタの解析
    filter_groups = []
    if args.group:
        filter_groups = [g.strip() for g in args.group.split(",") if g.strip()]

    for doc in tree:
        if not doc.parent or doc.parent not in docs:
            continue
        parent_doc = docs[doc.parent]

        # グループフィルタ
        if filter_groups:
            parent_items = [i for i in parent_doc if any(fg in get_groups(i) for fg in filter_groups) and is_normative(i)]
        else:
            parent_items = [i for i in parent_doc if is_normative(i)]

        parent_uids = {str(i.uid) for i in parent_items}
        if not parent_uids:
            continue

        # カバー判定
        covered_map = defaultdict(list)  # parent_uid -> [child_uid, ...]
        uncovered = set(parent_uids)

        child_items = [i for i in doc if is_normative(i)]
        if filter_groups:
            child_items = [i for i in child_items if any(fg in get_groups(i) for fg in filter_groups)]

        for item in child_items:
            for link in item.links:
                link_str = str(link)
                if link_str in parent_uids:
                    covered_map[link_str].append(str(item.uid))
                    uncovered.discard(link_str)

        total = len(parent_uids)
        covered = total - len(uncovered)
        pct = round(covered / total * 100, 1) if total > 0 else 100.0

        # 未カバーアイテムの詳細
        uncovered_details = []
        for uid in sorted(uncovered):
            item = find_item(tree, uid)
            if item:
                uncovered_details.append({
                    "uid": uid,
                    "groups": get_groups(item),
                    "text": truncate_text(item.text.strip(), 120),
                })

        key = f"{doc.prefix} -> {doc.parent}"
        result[key] = {
            "total": total,
            "covered": covered,
            "percentage": pct,
            "uncovered_items": uncovered_details,
            "covered_map": dict(covered_map) if args.detail else None,
        }

    out({
        "ok": True,
        "action": "coverage",
        "group_filter": args.group,
        "relations": result,
    })


def cmd_gaps(tree, args):
    """リンク漏れ・ref未設定のアイテムを検出する。"""
    children_idx, _ = build_link_index(tree)

    missing_links = []    # 親リンクがあるべきなのに無いアイテム
    missing_refs = []     # ref必須(IMPL/TST)なのに未設定
    orphan_children = []  # 子から参照されていないアイテム

    # グループフィルタの解析
    filter_groups = []
    if args.group:
        filter_groups = [g.strip() for g in args.group.split(",") if g.strip()]

    for doc in tree:
        if args.document and doc.prefix != args.document:
            continue
        for item in doc:
            if not is_normative(item):
                continue
            if filter_groups:
                item_groups = get_groups(item)
                if not any(fg in item_groups for fg in filter_groups):
                    continue

            uid_str = str(item.uid)

            # 親リンクチェック（REQ以外は親リンク必須）
            if doc.parent and not item.links:
                missing_links.append({
                    "uid": uid_str,
                    "prefix": doc.prefix,
                    "groups": get_groups(item),
                    "text": truncate_text(item.text.strip(), 120),
                    "expected_parent_doc": doc.parent,
                    "issue": f"{doc.parent} へのリンクがありません",
                })

            # referencesチェック（IMPL/TSTはreferences必須）
            if doc.prefix in ("IMPL", "TST") and not get_references(item):
                missing_refs.append({
                    "uid": uid_str,
                    "prefix": doc.prefix,
                    "groups": get_groups(item),
                    "text": truncate_text(item.text.strip(), 120),
                    "issue": "references（ソース/テストファイルパス）が未設定",
                })

    # 子から参照されていないアイテム（SPEC で IMPL/TST が紐付いていない等）
    for doc in tree:
        if args.document and args.document not in (doc.prefix, None):
            continue
        # このドキュメントを親に持つ子ドキュメントがあるか
        child_docs = [d for d in tree if d.parent == doc.prefix]
        if not child_docs:
            continue
        for item in doc:
            if not is_normative(item):
                continue
            if filter_groups:
                item_groups = get_groups(item)
                if not any(fg in item_groups for fg in filter_groups):
                    continue
            uid_str = str(item.uid)
            if not children_idx.get(uid_str):
                orphan_children.append({
                    "uid": uid_str,
                    "prefix": doc.prefix,
                    "groups": get_groups(item),
                    "text": truncate_text(item.text.strip(), 120),
                    "issue": f"子ドキュメント（{', '.join(d.prefix for d in child_docs)}）"
                             f"からの参照がありません",
                })

    out({
        "ok": True,
        "action": "gaps",
        "document_filter": args.document,
        "group_filter": args.group,
        "missing_links": missing_links,
        "missing_refs": missing_refs,
        "orphan_items": orphan_children,
        "total_issues": len(missing_links) + len(missing_refs) + len(orphan_children),
    })
