#!/usr/bin/env python3
"""AIコーディングエージェント向けトレーサビリティ照会CLI。

doorstop_ops.py がCRUD操作を担当するのに対し、本スクリプトは
トレーサビリティの「分析・照会」に特化する。
すべてのコマンドはJSON形式でstdoutに出力し、エージェントがパースしやすい。

Usage:
    python trace_query.py <project-dir> <command> [options]

Commands:
    status              プロジェクト全体のサマリ（件数・カバレッジ・suspect数）
    chain <UID>         指定UIDの上流→下流チェーン全体を表示
    chain --file PATH   ファイルパスをreferencesから逆引きし、該当アイテムのチェーンを表示
    coverage            カバレッジ詳細（どのSPECがIMPL/TST未カバーか）
    suspects            全suspect一覧と要対応アクション
    gaps                リンク漏れ・ref未設定のアイテム一覧

Examples:
    python trace_query.py . status
    python trace_query.py . chain SPEC003
    python trace_query.py . chain --file src/beautyspot/core.py
    python trace_query.py . coverage --group CACHE
    python trace_query.py . suspects
    python trace_query.py . gaps --document IMPL
"""

import argparse
import os
from collections import defaultdict

try:
    import doorstop
except ImportError:
    from _common import out
    out({"ok": False, "error": "doorstop がインストールされていません"})

from _common import (
    out, get_groups, get_references, is_derived, is_normative,
    find_item, find_doc_prefix, is_suspect, item_summary,
    build_link_index,
)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

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


def _find_items_by_file(tree, file_path):
    """ファイルパスをreferences属性から逆引きし、参照しているアイテムを返す。

    マッチ戦略（優先順）:
      1. 正規化後の完全一致
      2. file_path が参照パスのサフィックスに一致（例: "core.py" → "src/beautyspot/core.py"）
      3. 参照パスが file_path のサフィックスに一致（相対パスの表記ゆれ対応）
    """
    normalized = file_path.replace("\\", "/").rstrip("/")
    results = []
    for doc in tree:
        for item in doc:
            for ref in get_references(item):
                ref_path = ref.get("path", "").replace("\\", "/").rstrip("/")
                if not ref_path:
                    continue
                if (
                    ref_path == normalized
                    or ref_path.endswith("/" + normalized)
                    or normalized.endswith("/" + ref_path)
                ):
                    results.append((item, doc.prefix))
                    break  # 同一アイテムを重複追加しない
    return results


def _build_single_chain(tree, root_item, children_idx, parents_idx):
    """単一アイテムのチェーン情報を構築して返す。"""
    uid = str(root_item.uid)
    prefix = find_doc_prefix(tree, root_item)

    upstream = []
    _trace_up(uid, parents_idx, upstream, visited=set())

    downstream = []
    _trace_down(uid, children_idx, downstream, visited=set())

    chain_uids = {uid}
    for entry in upstream:
        chain_uids.add(entry["uid"])
    for entry in downstream:
        chain_uids.add(entry["uid"])

    layers = defaultdict(list)
    for doc in tree:
        for item in doc:
            uid_str = str(item.uid)
            if uid_str in chain_uids:
                layers[doc.prefix].append(item_summary(item, doc.prefix, tree))

    return {
        "root": item_summary(root_item, prefix, tree),
        "upstream": upstream,
        "downstream": downstream,
        "by_layer": dict(layers),
        "chain_size": len(chain_uids),
    }


def cmd_chain(tree, args):
    """指定UIDまたはファイルパスの上流→下流チェーン全体を表示する。"""
    children_idx, parents_idx = build_link_index(tree)

    # --file による逆引きモード
    if getattr(args, "file", None):
        matched = _find_items_by_file(tree, args.file)
        if not matched:
            out({"ok": False, "error": f"ファイル '{args.file}' をreferencesに持つアイテムが見つかりません"})

        chains = []
        for root_item, _prefix in matched:
            chain = _build_single_chain(tree, root_item, children_idx, parents_idx)
            chains.append(chain)

        out({
            "ok": True,
            "action": "chain",
            "mode": "by_file",
            "file": args.file,
            "chains": chains,
            "matched_count": len(chains),
        })

    # UID指定モード（従来の動作）
    if not args.uid:
        out({"ok": False, "error": "UID または --file のどちらかを指定してください"})

    root_item = find_item(tree, args.uid)
    if root_item is None:
        out({"ok": False, "error": f"UID '{args.uid}' が見つかりません"})

    chain = _build_single_chain(tree, root_item, children_idx, parents_idx)
    out({
        "ok": True,
        "action": "chain",
        "mode": "by_uid",
        **chain,
    })



def _trace_up(uid, parents_idx, result, visited, depth=0):
    if uid in visited or depth > 10:
        return
    visited.add(uid)
    for parent_item, parent_prefix in parents_idx.get(uid, []):
        parent_uid = str(parent_item.uid)
        result.append({
            "uid": parent_uid,
            "prefix": parent_prefix,
            "groups": get_groups(parent_item),
            "text": parent_item.text.strip()[:120],
            "derived": is_derived(parent_item),
            "depth": depth,
        })
        _trace_up(parent_uid, parents_idx, result, visited, depth + 1)


def _trace_down(uid, children_idx, result, visited, depth=0):
    if uid in visited or depth > 10:
        return
    visited.add(uid)
    for child_item, child_prefix in children_idx.get(uid, []):
        child_uid = str(child_item.uid)
        result.append({
            "uid": child_uid,
            "prefix": child_prefix,
            "groups": get_groups(child_item),
            "text": child_item.text.strip()[:120],
            "references": get_references(child_item),
            "derived": is_derived(child_item),
            "depth": depth,
        })
        _trace_down(child_uid, children_idx, result, visited, depth + 1)


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
                    "text": item.text.strip()[:120],
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
                        "parent_text": parent.text.strip()[:100],
                    })

            action = _suggest_action(item, doc.prefix)

            suspects.append({
                "uid": str(item.uid),
                "prefix": doc.prefix,
                "groups": get_groups(item),
                "text": item.text.strip()[:120],
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


def cmd_backlog(tree, args):
    """REQ（および任意のドキュメント）のアイテムを優先度順に一覧表示する。

    priority 属性の値に基づいてソートする:
        critical > high > medium > low > (未設定 = medium 扱い)
    """
    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

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
            priority = item.get("priority") or "medium"
            coverage_ok = bool(children_idx.get(uid))  # 子アイテムが存在するか

            items.append({
                "uid": uid,
                "prefix": doc.prefix,
                "header": item.header or "",
                "groups": get_groups(item),
                "priority": priority,
                "has_children": coverage_ok,
                "text": item.text.strip()[:100],
            })

    # 優先度→UID順にソート
    items.sort(key=lambda x: (PRIORITY_ORDER.get(x["priority"], 2), x["uid"]))

    # 優先度別集計
    priority_summary = {}
    for p in ("critical", "high", "medium", "low"):
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


def cmd_gaps(tree, args):
    """リンク漏れ・ref未設定のアイテムを検出する。"""
    children_idx, _ = build_link_index(tree)

    missing_links = []   # 親リンクがあるべきなのに無いアイテム
    missing_refs = []    # ref必須(IMPL/TST)なのに未設定
    orphan_children = [] # 子から参照されていないアイテム
    
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
                    "text": item.text.strip()[:120],
                    "expected_parent_doc": doc.parent,
                    "issue": f"{doc.parent} へのリンクがありません",
                })

            # referencesチェック（IMPL/TSTはreferences必須）
            if doc.prefix in ("IMPL", "TST") and not get_references(item):
                missing_refs.append({
                    "uid": uid_str,
                    "prefix": doc.prefix,
                    "groups": get_groups(item),
                    "text": item.text.strip()[:120],
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
                    "text": item.text.strip()[:120],
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
        "coverage": cmd_coverage,
        "suspects": cmd_suspects,
        "gaps": cmd_gaps,
        "backlog": cmd_backlog,
    }

    cmd_map[args.command](tree, args)


if __name__ == "__main__":
    main()
