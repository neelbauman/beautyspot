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


def out(data):
    """JSON出力して終了。"""
    print(json.dumps(data, ensure_ascii=False, indent=2))
    sys.exit(0 if data.get("ok", True) else 1)


def get_group(item):
    try:
        g = item.get("group")
        return g if g else None
    except (AttributeError, KeyError):
        return None


def _is_suspect(item, tree):
    """アイテムがsuspect状態かどうかを判定する。"""
    for link in item.links:
        parent = _find_item_safe(tree, str(link))
        if parent is None:
            continue
        if (
            link.stamp is not None
            and link.stamp != ""
            and link.stamp != parent.stamp()
        ):
            return True
    return False


def item_to_dict(item, doc_prefix=None, tree=None):
    """アイテムをdictに変換。"""
    d = {
        "uid": str(item.uid),
        "prefix": doc_prefix or str(item.uid).rstrip("0123456789"),
        "text": item.text.strip(),
        "header": item.header.strip() if item.header else "",
        "group": get_group(item),
        "level": str(item.level),
        "ref": item.ref or "",
        "links": [str(link) for link in item.links],
        "active": item.active,
        "reviewed": bool(item.reviewed),
    }
    if tree is not None:
        d["suspect"] = _is_suspect(item, tree)
    return d


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
        item.set("group", args.group)
    if args.ref:
        item.ref = args.ref

    # リンク
    for link_uid in (args.links or []):
        item.link(link_uid)

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
        item.set("group", args.group)
    if args.ref is not None:
        item.ref = args.ref

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


def cmd_list(tree, args):
    """アイテム一覧を取得する。"""
    items = []
    for doc in tree:
        if args.document and doc.prefix != args.document:
            continue
        for item in doc:
            if args.group and get_group(item) != args.group:
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
            g = get_group(item) or "(未分類)"
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
# Helpers
# ---------------------------------------------------------------------------

def _find_item(tree, uid):
    for doc in tree:
        try:
            return doc.find_item(uid)
        except Exception:
            continue
    print(json.dumps({"ok": False, "error": f"UID '{uid}' が見つかりません"}))
    sys.exit(1)


def _find_item_safe(tree, uid):
    for doc in tree:
        try:
            return doc.find_item(uid)
        except Exception:
            continue
    return None


def _find_prefix(tree, item):
    for doc in tree:
        try:
            doc.find_item(str(item.uid))
            return doc.prefix
        except Exception:
            continue
    return "?"


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
    p_add.add_argument("--links", nargs="*", help="リンク先UID")

    # update
    p_upd = sub.add_parser("update", help="アイテム更新")
    p_upd.add_argument("uid", help="更新対象UID")
    p_upd.add_argument("-t", "--text", help="新テキスト")
    p_upd.add_argument("--header", help="新ヘッダー")
    p_upd.add_argument("-g", "--group", help="新グループ")
    p_upd.add_argument("-r", "--ref", help="新参照パス")

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

    cmd_map = {
        "add": cmd_add,
        "update": cmd_update,
        "link": cmd_link,
        "clear": cmd_clear,
        "review": cmd_review,
        "list": cmd_list,
        "groups": cmd_groups,
        "tree": cmd_tree,
        "find": cmd_find,
    }

    cmd_map[args.command](tree, args)


if __name__ == "__main__":
    main()
