"""CRUD・リンク操作コマンド。

含まれるコマンド:
  add      アイテムを追加する
  update   アイテムを更新する
  reorder  アイテムのレベルを変更し、他を自動で再配置する
  link     リンクを追加する
  unlink   リンクを削除する
"""
import json

from _common import out, find_doc_prefix as _find_prefix, item_to_dict
from ._util import _find_item


def cmd_add(tree, args):
    """アイテムを追加する。"""
    doc = tree.find_document(args.document)
    kwargs = {}
    level_val = args.insert or args.level
    if level_val:
        kwargs["level"] = level_val

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
        valid = ("critical", "high", "medium", "low", "none", "done")
        if args.priority not in valid:
            out({"ok": False, "error": f"priority は {valid} のいずれかを指定してください"})
            return
        item.set("priority", args.priority)
    if args.test_level:
        item.set("test_level", args.test_level)
    if args.non_normative:
        item.set("normative", False)
    if args.derived:
        item.set("derived", True)
    if args.gherkin:
        item.set("gherkin", args.gherkin)

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
        valid = ("critical", "high", "medium", "low", "none", "done")
        if args.priority not in valid:
            out({"ok": False, "error": f"priority は {valid} のいずれかを指定してください"})
            return
        item.set("priority", args.priority)
    if args.test_level is not None:
        item.set("test_level", args.test_level)
    if args.set_normative:
        item.set("normative", True)
    elif args.set_non_normative:
        item.set("normative", False)
    if args.gherkin is not None:
        item.set("gherkin", args.gherkin)

    item.save()

    out({
        "ok": True,
        "action": "update",
        "item": item_to_dict(item, prefix),
    })


def cmd_reorder(tree, args):
    """アイテムのレベルを変更し、他を自動で再配置する。"""
    item = _find_item(tree, args.uid)
    prefix = _find_prefix(tree, item)
    doc = tree.find_document(prefix)

    old_level = str(item.level)
    item.level = args.level
    item.save()

    doc.reorder(manual=False, automatic=True, keep=item)

    out({
        "ok": True,
        "action": "reorder",
        "uid": str(item.uid),
        "old_level": old_level,
        "new_level": str(item.level),
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
