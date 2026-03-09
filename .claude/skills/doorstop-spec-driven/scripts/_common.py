"""共通ユーティリティ — doorstop-spec-driven スクリプト群の共有モジュール。

全スクリプト（trace_query, doorstop_ops, impact_analysis, validate_and_report）
で使われるヘルパー関数を一元管理する。
"""

import json
import os
import sys
from collections import defaultdict


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def out(data):
    """JSON出力して終了。"""
    print(json.dumps(data, ensure_ascii=False, indent=2))
    sys.exit(0 if data.get("ok", True) else 1)


# ---------------------------------------------------------------------------
# Item attribute accessors
# ---------------------------------------------------------------------------

def get_group(item, default=None):
    """アイテムの group 属性を取得する。

    Args:
        default: group が未設定の場合に返す値。
                 trace_query 等では None、validate_and_report では "(未分類)" を使う。
    """
    try:
        g = item.get("group")
        return g if g else default
    except (AttributeError, KeyError):
        return default


def get_ref(item):
    """アイテムの ref 属性を取得する。"""
    try:
        return item.ref or ""
    except (AttributeError, KeyError):
        return ""


def get_references(item):
    """references 属性（辞書型リスト）を取得する。なければ ref からフォールバック。"""
    try:
        refs = item.get("references")
        if refs and isinstance(refs, list):
            return refs
    except (AttributeError, KeyError):
        pass
    ref = get_ref(item)
    if ref:
        return [{"path": ref, "type": "file"}]
    return []


def get_references_display(item):
    """references を表示用文字列にする。"""
    refs = get_references(item)
    if not refs:
        return ""
    return ", ".join(r.get("path", "") for r in refs if r.get("path"))


def is_derived(item):
    """アイテムが派生要求（derived: true）かどうかを判定する。"""
    try:
        return bool(item.get("derived"))
    except (AttributeError, KeyError):
        return False


def is_normative(item):
    """アイテムが規範的（要件）かどうかを判定する。デフォルトはTrue。"""
    try:
        val = item.get("normative")
        if val is None:
            return True
        return str(val).lower() != "false"
    except (AttributeError, KeyError):
        return True


# ---------------------------------------------------------------------------
# Tree navigation
# ---------------------------------------------------------------------------

def find_item(tree, uid_str):
    """UID文字列からアイテムを検索する。見つからなければ None。"""
    for doc in tree:
        try:
            return doc.find_item(uid_str)
        except Exception:
            continue
    return None


def find_doc_prefix(tree, item):
    """アイテムが所属するドキュメントのプレフィックスを返す。"""
    uid_str = str(item.uid)
    for doc in tree:
        try:
            doc.find_item(uid_str)
            return doc.prefix
        except Exception:
            continue
    return "?"


def is_suspect(item, tree):
    """アイテムがsuspect状態かどうかを判定する。"""
    for link in item.links:
        parent = find_item(tree, str(link))
        if parent is None:
            continue
        if (
            link.stamp is not None
            and link.stamp != ""
            and link.stamp != parent.stamp()
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Link index
# ---------------------------------------------------------------------------

def build_link_index(tree):
    """上流・下流のリンクインデックスを構築する。

    Returns:
        children: {parent_uid: [(child_item, child_doc_prefix), ...]}
        parents:  {child_uid: [(parent_item, parent_doc_prefix), ...]}
    """
    children = defaultdict(list)
    parents = defaultdict(list)
    for doc in tree:
        for item in doc:
            for link in item.links:
                uid_str = str(link)
                parent_item = find_item(tree, uid_str)
                if parent_item:
                    children[uid_str].append((item, doc.prefix))
                    parents[str(item.uid)].append(
                        (parent_item, find_doc_prefix(tree, parent_item))
                    )
    return children, parents


# ---------------------------------------------------------------------------
# Item serialization
# ---------------------------------------------------------------------------

def item_summary(item, prefix=None, tree=None):
    """アイテムのコンパクトなdict表現（照会用）。"""
    d = {
        "uid": str(item.uid),
        "prefix": prefix or (find_doc_prefix(tree, item) if tree else "?"),
        "group": get_group(item),
        "header": item.header.strip() if item.header else "",
        "text": item.text.strip()[:200],
        "references": get_references(item),
        "derived": is_derived(item),
        "normative": is_normative(item),
        "links": [str(link) for link in item.links],
        "reviewed": bool(item.reviewed),
    }
    if tree is not None:
        d["suspect"] = is_suspect(item, tree)
    return d


def item_to_dict(item, doc_prefix=None, tree=None):
    """アイテムの完全なdict表現（CRUD操作用）。"""
    d = {
        "uid": str(item.uid),
        "prefix": doc_prefix or str(item.uid).rstrip("0123456789"),
        "text": item.text.strip(),
        "header": item.header.strip() if item.header else "",
        "group": get_group(item),
        "level": str(item.level),
        "references": get_references(item),
        "normative": is_normative(item),
        "links": [str(link) for link in item.links],
        "active": item.active,
        "reviewed": bool(item.reviewed),
    }
    if tree is not None:
        d["suspect"] = is_suspect(item, tree)
    return d


# ---------------------------------------------------------------------------
# Document path utilities
# ---------------------------------------------------------------------------

def build_doc_file_map(tree, project_dir):
    """ドキュメントツリーからファイルパス → UID のマッピングを構築する。

    Git diff で変更されたファイルから doorstop アイテムを特定するために使う。
    ドキュメントの実際のパスを使うため、--docs-dir のカスタムにも対応する。
    """
    file_to_uid = {}
    for doc in tree:
        doc_rel = os.path.relpath(str(doc.path), project_dir)
        for item in doc:
            uid_str = str(item.uid)
            # doorstop は {UID}.yml 形式でファイルを保存する
            for ext in (".yml", ".yaml"):
                filepath = os.path.join(doc_rel, f"{uid_str}{ext}")
                # パス区切りを正規化
                filepath = filepath.replace("\\", "/")
                file_to_uid[filepath] = uid_str
    return file_to_uid
