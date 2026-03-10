#!/usr/bin/env python3
"""Doorstop操作ヘルパー — エージェント向けの単一コマンドインターフェース。

エージェントがDoorstopの操作を1コマンドで実行できるようにする。
すべてのコマンドはJSONで結果を返し、エージェントがパースしやすい形式にする。

Usage:
    python doorstop_ops.py <project-dir> <command> [options]

Commands:
    add       アイテムを追加する
    update    アイテムを更新する
    link      リンクを追加する
    clear     suspectを解消する
    review    レビュー済みにする
    list      アイテム一覧を取得する
    groups    グループ一覧を取得する
    tree      ツリー構造を取得する
    find      テキスト検索でアイテムを探す
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
    item_to_dict, build_link_index
)


def _find_item(tree, uid):
    item = _find_item_safe(tree, uid)
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
    p_upd.add_argument("--set-normative", action="store_true", help="規範的アイテムに設定")
    p_upd.add_argument("--set-non-normative", action="store_true", help="非規範的アイテムに設定")

    # link
    p_link = sub.add_parser("link", help="リンク追加")
    p_link.add_argument("child", help="子アイテムUID")
    p_link.add_argument("parent", help="親アイテムUID")

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
