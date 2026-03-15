"""doorstop_ops サブモジュール共通のユーティリティ。"""
from _common import out, find_item as _find_item_safe


def _find_item(tree, uid, include_inactive=False):
    """UID でアイテムを検索し、見つからなければ JSON エラーを出力して終了する。"""
    item = _find_item_safe(tree, uid, include_inactive=include_inactive)
    if item is None:
        out({"ok": False, "error": f"UID '{uid}' が見つかりません"})
    return item
