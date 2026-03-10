#!/usr/bin/env python3
"""Doorstop操作ヘルパー — エージェント向けの単一コマンドインターフェース。

エージェントがDoorstopの操作を1コマンドで実行できるようにする。
すべてのコマンドはJSONで結果を返し、エージェントがパースしやすい形式にする。

Usage:
    python doorstop_ops.py <project-dir> <command> [options]

Commands:
    add              アイテムを追加する
    update           アイテムを更新する
    link             リンクを追加する
    unlink           リンクを削除する
    clear            suspectを解消する
    review           レビュー済みにする
    deactivate       アイテムを非活性化する（active: false）
    activate         アイテムを活性化する（active: true）
    deactivate-chain リンクチェーン全体を非活性化する（下流を検査して一括処理）
    activate-chain   リンクチェーン全体を活性化する
    list             アイテム一覧を取得する
    groups           グループ一覧を取得する
    tree             ツリー構造を取得する
    find             テキスト検索でアイテムを探す
"""

import argparse
import json
import os
import sys

try:
    import doorstop
except ImportError:
    print(json.dumps({"ok": False, "error": "doorstop がインストールされていません"}))
    sys.exit(1)

from ._common import (
    out, get_groups, find_item as _find_item_safe,
    find_doc_prefix as _find_prefix,
    item_to_dict, build_link_index,
)


def _find_item(tree, uid, include_inactive=False):
    item = _find_item_safe(tree, uid, include_inactive=include_inactive)
    if item is None:
        out({"ok": False, "error": f"UID '{uid}' が見つかりません"})
    return item


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_add(tree, args):
    """アイテムを追加する。"""
    doc = tree.find_document(args.document)
    kwargs = {}
    if args.level:
        kwargs["level"] = args.level

    item = doc.add_item(**kwargs)
    item.text = args.text
    if args.header:
        item.header = args.header
    if args.group:
        item.set("groups", [g.strip() for g in args.group.split(",") if g.strip()])
    if args.ref:
        item.ref = args.ref
    if args.references:
        refs = json.loads(args.references)
        item.set("references", refs)
    if args.priority:
        valid = ("critical", "high", "medium", "low")
        if args.priority not in valid:
            out({"ok": False, "error": f"priority は {valid} のいずれかを指定してください"})
            return
        item.set("priority", args.priority)
    if args.non_normative:
        item.set("normative", False)
    if args.derived:
        item.set("derived", True)

    # リンク（追加後に clear でフィンガープリントを保存し、suspect を防ぐ）
    link_uids = args.links or []
    for link_uid in link_uids:
        item.link(link_uid)
    if link_uids:
        item.clear(link_uids)

    item.save()

    out({
        "ok": True,
        "action": "add",
        "item": item_to_dict(item, args.document),
    })


def cmd_update(tree, args):
    """アイテムを更新する。"""
    item = _find_item(tree, args.uid)
    prefix = _find_prefix(tree, item)

    if args.text is not None:
        item.text = args.text
    if args.header is not None:
        item.header = args.header
    if args.group is not None:
        item.set("groups", [g.strip() for g in args.group.split(",") if g.strip()])
    if args.ref is not None:
        item.ref = args.ref
    if args.references is not None:
        refs = json.loads(args.references)
        item.set("references", refs)
    if args.priority is not None:
        valid = ("critical", "high", "medium", "low")
        if args.priority not in valid:
            out({"ok": False, "error": f"priority は {valid} のいずれかを指定してください"})
            return
        item.set("priority", args.priority)
    if args.set_normative:
        item.set("normative", True)
    elif args.set_non_normative:
        item.set("normative", False)

    item.save()

    out({
        "ok": True,
        "action": "update",
        "item": item_to_dict(item, prefix),
    })


def cmd_link(tree, args):
    """リンクを追加する。"""
    item = _find_item(tree, args.child)
    item.link(args.parent)
    item.clear([args.parent])
    item.save()
    prefix = _find_prefix(tree, item)

    out({
        "ok": True,
        "action": "link",
        "child": str(item.uid),
        "parent": args.parent,
        "item": item_to_dict(item, prefix),
    })


def cmd_unlink(tree, args):
    """リンクを削除する。"""
    item = _find_item(tree, args.child)
    parent_uid = args.parent

    # リンクが存在するか確認
    existing = [str(link) for link in item.links]
    if parent_uid not in existing:
        out({
            "ok": False,
            "error": f"'{args.child}' は '{parent_uid}' へのリンクを持っていません"
                     f"（現在のリンク: {existing}）",
        })

    item.unlink(parent_uid)
    item.save()
    prefix = _find_prefix(tree, item)

    out({
        "ok": True,
        "action": "unlink",
        "child": str(item.uid),
        "removed_parent": parent_uid,
        "item": item_to_dict(item, prefix),
    })


def cmd_deactivate(tree, args):
    """アイテムを非活性化する（active: false）。"""
    results = []
    for uid in args.uids:
        item = _find_item(tree, uid)
        prefix = _find_prefix(tree, item)
        if not item.active:
            results.append({
                "uid": uid,
                "prefix": prefix,
                "changed": False,
                "reason": "既に非活性",
            })
            continue
        item.active = False
        item.save()
        results.append({
            "uid": uid,
            "prefix": prefix,
            "changed": True,
        })

    out({
        "ok": True,
        "action": "deactivate",
        "results": results,
        "deactivated_count": sum(1 for r in results if r["changed"]),
    })


def cmd_activate(tree, args):
    """アイテムを活性化する（active: true）。"""
    results = []
    for uid in args.uids:
        item = _find_item(tree, uid, include_inactive=True)
        prefix = _find_prefix(tree, item)
        if item.active:
            results.append({
                "uid": uid,
                "prefix": prefix,
                "changed": False,
                "reason": "既に活性",
            })
            continue
        item.active = True
        item.save()
        results.append({
            "uid": uid,
            "prefix": prefix,
            "changed": True,
        })

    out({
        "ok": True,
        "action": "activate",
        "results": results,
        "activated_count": sum(1 for r in results if r["changed"]),
    })


def _collect_downstream(uid, children_idx, visited=None, depth=0, max_depth=10):
    """下流アイテムを再帰的に収集する。"""
    if visited is None:
        visited = set()
    if uid in visited or depth > max_depth:
        return []
    visited.add(uid)
    result = []
    for child_item, child_prefix in children_idx.get(uid, []):
        child_uid = str(child_item.uid)
        result.append({
            "item": child_item,
            "uid": child_uid,
            "prefix": child_prefix,
            "depth": depth,
        })
        result.extend(
            _collect_downstream(child_uid, children_idx, visited, depth + 1, max_depth)
        )
    return result


def _has_other_active_parents(item, tree, exclude_uid):
    """指定UIDを除いた活性な親が存在するかを判定する。"""
    for link in item.links:
        link_uid = str(link)
        if link_uid == exclude_uid:
            continue
        parent = _find_item_safe(tree, link_uid)
        if parent is not None and parent.active:
            return True
    return False


def cmd_deactivate_chain(tree, args):
    """リンクチェーン全体を非活性化する。

    起点UIDを非活性化し、下流アイテムを検査して、
    他に活性な親を持たないアイテムを連鎖的に非活性化する。
    --force を指定すると、他に活性な親があっても強制的に非活性化する。
    """
    root_uid = args.uid
    root_item = _find_item(tree, root_uid)
    root_prefix = _find_prefix(tree, root_item)

    children_idx, _ = build_link_index(tree, include_inactive=True)

    # 起点を非活性化
    deactivated = []
    skipped = []

    if root_item.active:
        root_item.active = False
        root_item.save()
        deactivated.append({
            "uid": root_uid,
            "prefix": root_prefix,
            "reason": "起点アイテム",
            "depth": -1,
        })
    else:
        skipped.append({
            "uid": root_uid,
            "prefix": root_prefix,
            "reason": "既に非活性",
            "depth": -1,
        })

    # 下流を再帰探索し、非活性化すべきか検査
    downstream = _collect_downstream(root_uid, children_idx)

    for entry in downstream:
        item = entry["item"]
        uid = entry["uid"]
        prefix = entry["prefix"]
        depth = entry["depth"]

        if not item.active:
            skipped.append({
                "uid": uid,
                "prefix": prefix,
                "reason": "既に非活性",
                "depth": depth,
            })
            continue

        if not args.force and _has_other_active_parents(item, tree, root_uid):
            # 非活性化済みの親も除外して再チェック
            deactivated_uids = {d["uid"] for d in deactivated}
            has_active = False
            for link in item.links:
                link_uid = str(link)
                if link_uid in deactivated_uids:
                    continue
                parent = _find_item_safe(tree, link_uid)
                if parent is not None and parent.active:
                    has_active = True
                    break
            if has_active:
                skipped.append({
                    "uid": uid,
                    "prefix": prefix,
                    "reason": "他に活性な親リンクが存在",
                    "depth": depth,
                })
                continue

        item.active = False
        item.save()
        deactivated.append({
            "uid": uid,
            "prefix": prefix,
            "reason": "連鎖非活性化",
            "depth": depth,
        })

    out({
        "ok": True,
        "action": "deactivate-chain",
        "root": root_uid,
        "force": args.force,
        "deactivated": deactivated,
        "skipped": skipped,
        "deactivated_count": len(deactivated),
        "skipped_count": len(skipped),
    })


def cmd_activate_chain(tree, args):
    """リンクチェーン全体を活性化する。

    起点UIDを活性化し、下流アイテムを連鎖的に活性化する。
    """
    root_uid = args.uid
    root_item = _find_item(tree, root_uid, include_inactive=True)
    root_prefix = _find_prefix(tree, root_item)

    children_idx, _ = build_link_index(tree, include_inactive=True)

    activated = []
    skipped = []

    if not root_item.active:
        root_item.active = True
        root_item.save()
        activated.append({
            "uid": root_uid,
            "prefix": root_prefix,
            "reason": "起点アイテム",
            "depth": -1,
        })
    else:
        skipped.append({
            "uid": root_uid,
            "prefix": root_prefix,
            "reason": "既に活性",
            "depth": -1,
        })

    downstream = _collect_downstream(root_uid, children_idx)

    for entry in downstream:
        item = entry["item"]
        uid = entry["uid"]
        prefix = entry["prefix"]
        depth = entry["depth"]

        if item.active:
            skipped.append({
                "uid": uid,
                "prefix": prefix,
                "reason": "既に活性",
                "depth": depth,
            })
            continue

        item.active = True
        item.save()
        activated.append({
            "uid": uid,
            "prefix": prefix,
            "reason": "連鎖活性化",
            "depth": depth,
        })

    out({
        "ok": True,
        "action": "activate-chain",
        "root": root_uid,
        "activated": activated,
        "skipped": skipped,
        "activated_count": len(activated),
        "skipped_count": len(skipped),
    })


def cmd_clear(tree, args):
    """suspectリンクを解消する。"""
    cleared = []
    for uid in args.uids:
        item = _find_item(tree, uid)
        suspect_links = []
        for link in item.links:
            parent = _find_item_safe(tree, str(link))
            if parent:
                is_suspect = (
                    link.stamp is not None
                    and link.stamp != ""
                    and link.stamp != parent.stamp()
                )
                if is_suspect:
                    suspect_links.append(str(link))

        if suspect_links:
            item.clear(suspect_links)
            item.save()
            for sl in suspect_links:
                cleared.append({"item": uid, "link": sl})

    out({
        "ok": True,
        "action": "clear",
        "cleared": cleared,
        "count": len(cleared),
    })


def cmd_review(tree, args):
    """アイテムをレビュー済みにする。"""
    reviewed = []
    for uid in args.uids:
        item = _find_item(tree, uid)
        item.review()
        reviewed.append(uid)

    out({
        "ok": True,
        "action": "review",
        "reviewed": reviewed,
    })



def cmd_chain_review(tree, args):
    """アイテムチェーン全体を一括でreviewし、suspectをclearする。"""
    from _common import build_link_index
    children_map, parents_map = build_link_index(tree)
    
    visited = set()
    queue = list(args.uids)
    
    while queue:
        current_uid = queue.pop(0)
        if current_uid in visited:
            continue
        visited.add(current_uid)
        
        # Add parents (items that current_uid links to)
        # Actually parent_map maps child_uid -> list of (parent_item, prefix)
        # children_map maps parent_uid -> list of (child_item, prefix)
        for p_item, _ in parents_map.get(current_uid, []):
            queue.append(str(p_item.uid))
            
        # Add children (items that link to current_uid)
        for c_item, _ in children_map.get(current_uid, []):
            queue.append(str(c_item.uid))
            
    cleared = []
    reviewed = []
    for uid in visited:
        item = _find_item_safe(tree, uid)
        if not item:
            continue
        
        # Clear suspect links
        suspect_links = []
        for link in item.links:
            parent = _find_item_safe(tree, str(link))
            if parent:
                if (link.stamp is not None and link.stamp != "" and link.stamp != parent.stamp()):
                    suspect_links.append(str(link))
        if suspect_links:
            item.clear(suspect_links)
            for sl in suspect_links:
                cleared.append({"item": uid, "link": sl})
                
        # Review
        item.review()
        item.save()
        reviewed.append(uid)
        
    out({
        "ok": True,
        "action": "chain-review",
        "chain_size": len(visited),
        "cleared": cleared,
        "reviewed": reviewed
    })

def cmd_list(tree, args):
    """アイテム一覧を取得する。"""
    items = []
    
    # グループフィルタの解析
    filter_groups = []
    if args.group:
        filter_groups = [g.strip() for g in args.group.split(",") if g.strip()]
        
    for doc in tree:
        if args.document and doc.prefix != args.document:
            continue
        for item in doc:
            if filter_groups:
                item_groups = get_groups(item)
                if not any(fg in item_groups for fg in filter_groups):
                    continue
            items.append(item_to_dict(item, doc.prefix, tree=tree))

    out({
        "ok": True,
        "action": "list",
        "count": len(items),
        "items": items,
    })


def cmd_groups(tree, args):
    """グループ一覧を取得する。"""
    groups = {}
    for doc in tree:
        for item in doc:
            for g in get_groups(item):
                if g not in groups:
                    groups[g] = {"count": 0, "documents": set()}
                groups[g]["count"] += 1
                groups[g]["documents"].add(doc.prefix)

    result = {
        g: {"count": d["count"], "documents": sorted(d["documents"])}
        for g, d in sorted(groups.items())
    }

    out({
        "ok": True,
        "action": "groups",
        "groups": result,
    })


def cmd_tree(tree, args):
    """ツリー構造を取得する。"""
    docs = []
    for doc in tree:
        docs.append({
            "prefix": doc.prefix,
            "parent": doc.parent or None,
            "path": str(doc.path),
            "item_count": len(list(doc)),
        })

    out({
        "ok": True,
        "action": "tree",
        "documents": docs,
    })


def cmd_find(tree, args):
    """テキスト検索でアイテムを探す。"""
    query = args.query.lower()
    results = []
    for doc in tree:
        for item in doc:
            if query in item.text.lower() or (item.header and query in item.header.lower()):
                results.append(item_to_dict(item, doc.prefix, tree=tree))

    out({
        "ok": True,
        "action": "find",
        "query": args.query,
        "count": len(results),
        "items": results,
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
    p_add.add_argument("-r", "--ref", help="参照ファイルパス")
    p_add.add_argument("--references", help='外部ファイル紐付け（JSON文字列。例: \'[{"path":"src/mod.py","type":"file"}]\'）')
    p_add.add_argument("--priority", choices=["critical", "high", "medium", "low"],
                       help="優先度（REQ/NFR に設定を推奨）")
    p_add.add_argument("--non-normative", action="store_true", help="非規範的アイテム（見出し等）として追加")
    p_add.add_argument("--derived", action="store_true", help="派生要求として追加")
    p_add.add_argument("--links", nargs="*", help="リンク先UID")

    # update
    p_upd = sub.add_parser("update", help="アイテム更新")
    p_upd.add_argument("uid", help="更新対象UID")
    p_upd.add_argument("-t", "--text", help="新テキスト")
    p_upd.add_argument("--header", help="新ヘッダー")
    p_upd.add_argument("-g", "--group", help="新グループ")
    p_upd.add_argument("-r", "--ref", help="新参照パス")
    p_upd.add_argument("--references", help='外部ファイル紐付け（JSON文字列）')
    p_upd.add_argument("--priority", choices=["critical", "high", "medium", "low"],
                       help="優先度の変更")
    p_upd.add_argument("--set-normative", action="store_true", help="規範的アイテムに設定")
    p_upd.add_argument("--set-non-normative", action="store_true", help="非規範的アイテムに設定")

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
    p_chain_review = sub.add_parser("chain-review", help="アイテムチェーン全体を一括でreviewし、suspectをclearする")
    p_chain_review.add_argument("uids", nargs="+", help="起点となる対象UID")

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
        "link": cmd_link,
        "unlink": cmd_unlink,
        "deactivate": cmd_deactivate,
        "activate": cmd_activate,
        "deactivate-chain": cmd_deactivate_chain,
        "activate-chain": cmd_activate_chain,
        "clear": cmd_clear,
        "review": cmd_review,
        "chain-review": cmd_chain_review,
        "list": cmd_list,
        "groups": cmd_groups,
        "tree": cmd_tree,
        "find": cmd_find,
    }

    cmd_map[args.command](tree, args)


if __name__ == "__main__":
    main()
