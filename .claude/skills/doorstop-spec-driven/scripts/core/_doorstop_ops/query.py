"""読み取り専用照会コマンド。

含まれるコマンド:
  list    アイテム一覧を取得する
  groups  グループ一覧を取得する
  tree    ツリー構造を取得する
  find    テキスト検索でアイテムを探す
"""
from _common import out, get_groups, item_to_dict


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
