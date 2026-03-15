"""活性化・非活性化コマンド。

含まれるコマンド:
  activate          アイテムを活性化する（active: true）
  deactivate        アイテムを非活性化する（active: false）
  activate-chain    リンクチェーン全体を活性化する
  deactivate-chain  リンクチェーン全体を非活性化する
"""
from _common import out, find_item as _find_item_safe, find_doc_prefix as _find_prefix, build_link_index
from ._util import _find_item


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
