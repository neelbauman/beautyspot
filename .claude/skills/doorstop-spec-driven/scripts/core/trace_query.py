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
    context <UID>       行動に必要な全文脈情報を一括取得（target/upstream/downstream/files/health）
    related-files <UID> 関連ファイルパスをドキュメント層別に取得
    search <PATTERN>    属性フィルタ付き高機能検索（正規表現対応）
    coverage            カバレッジ詳細（どのSPECがIMPL/TST未カバーか）
    suspects            全suspect一覧と要対応アクション
    gaps                リンク漏れ・ref未設定のアイテム一覧

Examples:
    python trace_query.py . status
    python trace_query.py . chain SPEC003
    python trace_query.py . chain --file src/beautyspot/core.py
    python trace_query.py . context SPEC003
    python trace_query.py . related-files SPEC003
    python trace_query.py . search "タイムアウト" --group auth --suspect
    python trace_query.py . coverage --group CACHE
    python trace_query.py . suspects
    python trace_query.py . gaps --document IMPL
"""

import argparse
import os
import re
from collections import defaultdict

try:
    import doorstop
except ImportError:
    from _common import out
    out({"ok": False, "error": "doorstop がインストールされていません"})

from _common import (
    out, get_groups, get_priority, get_references, is_derived, is_normative,
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



def cmd_context(tree, args):
    """指定UIDの全文脈情報を一括取得する。

    エージェントが「何を読み、何を変え、何をテストすべきか」を
    1回のコマンドで判断できるよう、以下を集約して返す:
      - target: 対象アイテムの詳細
      - upstream: 上流アイテム（要件の根拠）
      - downstream: 下流アイテム（実装・テスト）
      - related_files: 関連ファイルパス（source / test / upstream に分類）
      - health: suspect / unreviewed / missing_children の状態
    """
    children_idx, parents_idx = build_link_index(tree)

    root_item = find_item(tree, args.uid)
    if root_item is None:
        out({"ok": False, "error": f"UID '{args.uid}' が見つかりません"})

    uid = str(root_item.uid)
    prefix = find_doc_prefix(tree, root_item)

    # upstream（参照元の references も含める）
    upstream = []
    _trace_up(uid, parents_idx, upstream, visited=set(), rich=True)

    # downstream（references を含む）
    downstream = []
    _trace_down(uid, children_idx, downstream, visited=set())

    # related_files: downstream の references をドキュメント種別で分類
    source_files = []
    test_files = []
    upstream_files = []

    # 対象アイテム自身の references
    for ref in get_references(root_item):
        path = ref.get("path", "")
        if path:
            source_files.append(path)

    # downstream の references を分類
    for entry in downstream:
        for ref in entry.get("references", []):
            path = ref.get("path", "")
            if not path:
                continue
            if entry["prefix"] in ("TST",):
                if path not in test_files:
                    test_files.append(path)
            elif entry["prefix"] in ("IMPL",):
                if path not in source_files:
                    source_files.append(path)
            else:
                if path not in source_files:
                    source_files.append(path)

    # upstream の references
    for entry in upstream:
        for ref in entry.get("references", []):
            path = ref.get("path", "")
            if path and path not in upstream_files:
                upstream_files.append(path)

    # health: 下流のsuspect・未レビュー・子リンク不足を検出
    suspect_items = []
    unreviewed_items = []
    for entry in downstream:
        item = find_item(tree, entry["uid"])
        if item is None:
            continue
        if is_suspect(item, tree):
            suspect_items.append(entry["uid"])
        if not item.reviewed:
            unreviewed_items.append(entry["uid"])

    # 対象自身のsuspect・レビュー状態
    if is_suspect(root_item, tree):
        suspect_items.insert(0, uid)
    if not root_item.reviewed:
        unreviewed_items.insert(0, uid)

    # 子リンクの欠落（子ドキュメントが存在するのにリンクがない）
    has_children = bool(children_idx.get(uid))
    child_docs = [d for d in tree if d.parent == prefix]
    missing_children = bool(child_docs) and not has_children

    # gherkin 属性
    gherkin = None
    if hasattr(root_item, "get"):
        g = root_item.get("gherkin")
        if g:
            gherkin = g.strip() if isinstance(g, str) else g

    out({
        "ok": True,
        "action": "context",
        "target": {
            **item_summary(root_item, prefix, tree),
            "gherkin": gherkin,
        },
        "upstream": upstream,
        "downstream": downstream,
        "related_files": {
            "source": source_files,
            "test": test_files,
            "upstream": upstream_files,
        },
        "health": {
            "suspects": suspect_items,
            "unreviewed": unreviewed_items,
            "missing_children": missing_children,
            "suspect_count": len(suspect_items),
            "unreviewed_count": len(unreviewed_items),
        },
    })


def cmd_related_files(tree, args):
    """指定UIDに関連する全ファイルパスをドキュメント層別に返す。

    context より軽量。「このUIDに関連するコード・テストファイルを
    全部読みたい」というケースに特化した出力。
    """
    children_idx, parents_idx = build_link_index(tree)

    # --file による逆引きモード
    if getattr(args, "file", None):
        matched = _find_items_by_file(tree, args.file)
        if not matched:
            out({"ok": False, "error": f"ファイル '{args.file}' をreferencesに持つアイテムが見つかりません"})

        all_files = defaultdict(list)
        matched_uids = []
        for root_item, _prefix in matched:
            matched_uids.append(str(root_item.uid))
            _collect_files_for_item(
                tree, root_item, children_idx, parents_idx, all_files
            )

        out({
            "ok": True,
            "action": "related-files",
            "mode": "by_file",
            "file": args.file,
            "matched_uids": matched_uids,
            "files": dict(all_files),
        })

    # UID指定モード
    root_item = find_item(tree, args.uid)
    if root_item is None:
        out({"ok": False, "error": f"UID '{args.uid}' が見つかりません"})

    files = defaultdict(list)
    _collect_files_for_item(tree, root_item, children_idx, parents_idx, files)

    out({
        "ok": True,
        "action": "related-files",
        "mode": "by_uid",
        "uid": args.uid,
        "files": dict(files),
    })


def _collect_files_for_item(tree, root_item, children_idx, parents_idx, files):
    """アイテムの上流・下流を辿り、references のファイルパスを層別に収集する。"""
    uid = str(root_item.uid)
    prefix = find_doc_prefix(tree, root_item)

    # 自身の references
    for ref in get_references(root_item):
        path = ref.get("path", "")
        if path and path not in files[prefix]:
            files[prefix].append(path)

    # downstream
    downstream = []
    _trace_down(uid, children_idx, downstream, visited=set())
    for entry in downstream:
        for ref in entry.get("references", []):
            path = ref.get("path", "")
            if path and path not in files[entry["prefix"]]:
                files[entry["prefix"]].append(path)

    # upstream
    upstream = []
    _trace_up(uid, parents_idx, upstream, visited=set(), rich=True)
    for entry in upstream:
        for ref in entry.get("references", []):
            path = ref.get("path", "")
            if path and path not in files[entry["prefix"]]:
                files[entry["prefix"]].append(path)


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


def _trace_up(uid, parents_idx, result, visited, depth=0, rich=False):
    """上流を辿る。rich=True の場合は references も含め text を 200 文字まで取得する。"""
    if uid in visited or depth > 10:
        return
    visited.add(uid)
    for parent_item, parent_prefix in parents_idx.get(uid, []):
        parent_uid = str(parent_item.uid)
        entry = {
            "uid": parent_uid,
            "prefix": parent_prefix,
            "groups": get_groups(parent_item),
            "text": parent_item.text.strip()[:200 if rich else 120],
            "derived": is_derived(parent_item),
            "depth": depth,
        }
        if rich:
            entry["references"] = get_references(parent_item)
        result.append(entry)
        _trace_up(parent_uid, parents_idx, result, visited, depth + 1, rich=rich)


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
            priority = get_priority(item)
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
