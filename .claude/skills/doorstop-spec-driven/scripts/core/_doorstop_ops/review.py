"""レビュー・suspect解消コマンド。

含まれるコマンド:
  clear        suspectリンクを解消する
  review       アイテムをレビュー済みにする
  chain-review アイテムとその祖先（上流）を一括でレビュー済みにする
  chain-clear  アイテムとその子孫（下流）のsuspectを一括解消する
"""
from _common import out, find_item as _find_item_safe, build_link_index
from ._util import _find_item


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
    """アイテムとその祖先（上流）チェーンを一括で review する。

    SDD原則に基づき、指定されたアイテムとその上位仕様のみを確定させる。
    """
    _, parents_map = build_link_index(tree)

    visited = set()
    queue = list(args.uids)

    while queue:
        current_uid = queue.pop(0)
        if current_uid in visited:
            continue
        visited.add(current_uid)

        # 祖先（Parents）方向のみをたどる
        for p_item, _ in parents_map.get(current_uid, []):
            queue.append(str(p_item.uid))

    reviewed = []
    for uid in visited:
        item = _find_item_safe(tree, uid)
        if not item:
            continue
        item.review()
        item.save()
        reviewed.append(uid)

    out({
        "ok": True,
        "action": "chain-review",
        "scope": "upstream",
        "chain_size": len(visited),
        "reviewed": reviewed,
    })


def cmd_chain_clear(tree, args):
    """アイテムとその子孫（下流）チェーンの suspect を一括で clear する。

    実装やテストの修正完了後、下流への影響を承認するために使用する。
    """
    children_map, _ = build_link_index(tree)

    visited = set()
    queue = list(args.uids)

    while queue:
        current_uid = queue.pop(0)
        if current_uid in visited:
            continue
        visited.add(current_uid)

        # 子孫（Children）方向のみをたどる
        for c_item, _ in children_map.get(current_uid, []):
            queue.append(str(c_item.uid))

    cleared = []
    for uid in visited:
        item = _find_item_safe(tree, uid)
        if not item:
            continue

        suspect_links = []
        for link in item.links:
            parent = _find_item_safe(tree, str(link))
            if parent:
                if (link.stamp is not None and link.stamp != "" and link.stamp != parent.stamp()):
                    suspect_links.append(str(link))
        if suspect_links:
            item.clear(suspect_links)
            item.save()
            for sl in suspect_links:
                cleared.append({"item": uid, "link": sl})

    out({
        "ok": True,
        "action": "chain-clear",
        "scope": "downstream",
        "chain_size": len(visited),
        "cleared": cleared,
    })
