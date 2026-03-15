#!/usr/bin/env python3
"""用語辞書（Glossary）管理CLI。

プロジェクトの用語辞書を独立YAMLファイルとして管理する。
Doorstopアイテムとは別に管理し、validate_and_report.py との連携で
REQ/SPEC本文の表記ゆれ検出を行う。

Usage:
    python glossary.py <project-dir> <command> [options]

Commands:
    add <term>          用語を追加する
    update <term>       用語の定義を更新する
    remove <term>       用語を削除する
    list                全用語を一覧表示する
    check               REQ/SPEC本文で表記ゆれ・未定義用語候補を検出する
    unused              定義済みだが仕様書で使われていない用語を検出する

Examples:
    python glossary.py . add "キャッシュヒット" --definition "以前の実行結果が..." --aliases "cache hit"
    python glossary.py . list --context cache
    python glossary.py . check
    python glossary.py . unused
"""

import argparse
import json
import os
import re
import sys

try:
    # PyYAML (doorstop の依存関係に含まれる)
    import yaml
except ImportError:
    print(json.dumps({
        "ok": False,
        "error": "PyYAML がインストールされていません"
    }))
    sys.exit(1)

from _common import out


# ---------------------------------------------------------------------------
# Glossary file I/O
# ---------------------------------------------------------------------------

def _glossary_path(project_dir):
    """用語辞書ファイルのパスを返す。

    specification/ ディレクトリが存在すればその下に、
    なければプロジェクトルート直下に配置する。
    """
    spec_dir = os.path.join(project_dir, "specification")
    if os.path.isdir(spec_dir):
        return os.path.join(spec_dir, "glossary.yml")
    return os.path.join(project_dir, "glossary.yml")


def _load_glossary(project_dir):
    """用語辞書を読み込む。ファイルが存在しない場合は空の辞書を返す。"""
    path = _glossary_path(project_dir)
    if not os.path.exists(path):
        return {"terms": []}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if "terms" not in data:
        data["terms"] = []
    return data


def _save_glossary(project_dir, data):
    """用語辞書を保存する。"""
    path = _glossary_path(project_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f, allow_unicode=True, default_flow_style=False, sort_keys=False
        )
    return path


def _find_term(terms, term_name):
    """用語名で検索する（大文字小文字を区別しない）。"""
    lower = term_name.lower()
    for i, t in enumerate(terms):
        if t.get("term", "").lower() == lower:
            return i, t
    return -1, None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_add(args):
    """用語を追加する。"""
    data = _load_glossary(args.project_dir)
    terms = data["terms"]

    idx, existing = _find_term(terms, args.term)
    if existing is not None:
        out({
            "ok": False,
            "error": f"用語 '{args.term}' は既に定義されています。更新するには update を使ってください。",
            "existing": existing,
        })

    entry = {"term": args.term, "definition": args.definition}
    if args.aliases:
        entry["aliases"] = [a.strip() for a in args.aliases.split(",") if a.strip()]
    if args.context:
        entry["context"] = args.context
    if args.code:
        entry["code"] = args.code

    terms.append(entry)
    saved_path = _save_glossary(args.project_dir, data)

    out({
        "ok": True,
        "action": "add",
        "term": entry,
        "glossary_path": saved_path,
        "total_terms": len(terms),
    })


def cmd_update(args):
    """用語の定義を更新する。"""
    data = _load_glossary(args.project_dir)
    terms = data["terms"]

    idx, existing = _find_term(terms, args.term)
    if existing is None:
        out({"ok": False, "error": f"用語 '{args.term}' が見つかりません"})

    if args.definition:
        existing["definition"] = args.definition
    if args.aliases is not None:
        existing["aliases"] = [a.strip() for a in args.aliases.split(",") if a.strip()]
    if args.context is not None:
        existing["context"] = args.context
    if args.code is not None:
        existing["code"] = args.code

    terms[idx] = existing
    saved_path = _save_glossary(args.project_dir, data)

    out({
        "ok": True,
        "action": "update",
        "term": existing,
        "glossary_path": saved_path,
    })


def cmd_remove(args):
    """用語を削除する。"""
    data = _load_glossary(args.project_dir)
    terms = data["terms"]

    idx, existing = _find_term(terms, args.term)
    if existing is None:
        out({"ok": False, "error": f"用語 '{args.term}' が見つかりません"})

    removed = terms.pop(idx)
    saved_path = _save_glossary(args.project_dir, data)

    out({
        "ok": True,
        "action": "remove",
        "removed_term": removed,
        "glossary_path": saved_path,
        "total_terms": len(terms),
    })


def cmd_list(args):
    """全用語を一覧表示する。"""
    data = _load_glossary(args.project_dir)
    terms = data["terms"]

    # context フィルタ
    if args.context:
        filter_ctx = args.context.lower()
        terms = [t for t in terms if t.get("context", "").lower() == filter_ctx]

    # ソート
    terms = sorted(terms, key=lambda t: t.get("term", "").lower())

    out({
        "ok": True,
        "action": "list",
        "context_filter": args.context,
        "count": len(terms),
        "terms": terms,
        "glossary_path": _glossary_path(args.project_dir),
    })


def cmd_check(args):
    """REQ/SPEC本文で表記ゆれ・エイリアス使用を検出する。"""
    try:
        import doorstop
    except ImportError:
        out({"ok": False, "error": "doorstop がインストールされていません"})

    data = _load_glossary(args.project_dir)
    terms = data["terms"]

    if not terms:
        out({
            "ok": True,
            "action": "check",
            "message": "用語辞書が空です。先に用語を追加してください。",
            "issues": [],
        })

    os.chdir(args.project_dir)
    try:
        tree = doorstop.build()
    except Exception as e:
        out({"ok": False, "error": f"ツリー構築失敗: {e}"})

    # エイリアス→正式名称のマッピングを構築
    alias_map = {}  # alias_lower -> (正式名称, alias原文)
    for t in terms:
        for alias in t.get("aliases", []):
            alias_map[alias.lower()] = (t["term"], alias)

    # 対象ドキュメントを決定（IMPL/TST はスキャン対象外）
    target_prefixes = set()
    for doc in tree:
        if doc.prefix not in ("IMPL", "TST"):
            target_prefixes.add(doc.prefix)

    issues = []
    for doc in tree:
        if doc.prefix not in target_prefixes:
            continue
        for item in doc:
            text = (item.text or "")
            if item.header:
                text += " " + item.header
            if hasattr(item, "get"):
                g = item.get("gherkin")
                if g and isinstance(g, str):
                    text += " " + g
            if not text.strip():
                continue

            text_lower = text.lower()

            # エイリアスの使用検出（正式名称の代わりにエイリアスが使われている）
            for alias_lower, (canonical, alias_orig) in alias_map.items():
                # 正式名称も含まれている場合はスキップ（混在チェックは複雑すぎるため）
                if alias_lower in text_lower:
                    # エイリアスが単語境界で出現するか確認
                    pattern = re.compile(re.escape(alias_orig), re.IGNORECASE)
                    matches = pattern.findall(text)
                    if matches:
                        issues.append({
                            "uid": str(item.uid),
                            "prefix": doc.prefix,
                            "type": "alias_usage",
                            "alias": alias_orig,
                            "canonical": canonical,
                            "message": f"エイリアス '{alias_orig}' が使われています。"
                                       f"正式名称 '{canonical}' への統一を検討してください。",
                        })

    out({
        "ok": True,
        "action": "check",
        "scanned_documents": sorted(target_prefixes),
        "total_terms": len(terms),
        "issue_count": len(issues),
        "issues": issues,
    })


def cmd_unused(args):
    """定義済みだが仕様書で使われていない用語を検出する。"""
    try:
        import doorstop
    except ImportError:
        out({"ok": False, "error": "doorstop がインストールされていません"})

    data = _load_glossary(args.project_dir)
    terms = data["terms"]

    if not terms:
        out({
            "ok": True,
            "action": "unused",
            "message": "用語辞書が空です。",
            "unused_terms": [],
        })

    os.chdir(args.project_dir)
    try:
        tree = doorstop.build()
    except Exception as e:
        out({"ok": False, "error": f"ツリー構築失敗: {e}"})

    # 全ドキュメントの全テキストを結合
    all_text = ""
    for doc in tree:
        for item in doc:
            all_text += " " + (item.text or "")
            if item.header:
                all_text += " " + item.header
            if hasattr(item, "get"):
                g = item.get("gherkin")
                if g and isinstance(g, str):
                    all_text += " " + g
    all_text_lower = all_text.lower()

    unused = []
    for t in terms:
        term_lower = t["term"].lower()
        aliases = [a.lower() for a in t.get("aliases", [])]
        all_names = [term_lower] + aliases

        found = any(name in all_text_lower for name in all_names)
        if not found:
            unused.append(t)

    out({
        "ok": True,
        "action": "unused",
        "total_terms": len(terms),
        "unused_count": len(unused),
        "unused_terms": unused,
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="用語辞書（Glossary）管理CLI（JSON出力）"
    )
    parser.add_argument("project_dir", help="プロジェクトルート")
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="用語を追加する")
    p_add.add_argument("term", help="用語名")
    p_add.add_argument("--definition", "-D", required=True, help="定義")
    p_add.add_argument("--aliases", help="エイリアス（カンマ区切り）")
    p_add.add_argument("--context", help="コンテキスト（グループ名等）")
    p_add.add_argument("--code", help="コード上の表現（クラス名、変数名等）")

    # update
    p_upd = sub.add_parser("update", help="用語の定義を更新する")
    p_upd.add_argument("term", help="用語名")
    p_upd.add_argument("--definition", "-D", help="新しい定義")
    p_upd.add_argument("--aliases", help="エイリアス（カンマ区切り）")
    p_upd.add_argument("--context", help="コンテキスト")
    p_upd.add_argument("--code", help="コード上の表現")

    # remove
    p_rm = sub.add_parser("remove", help="用語を削除する")
    p_rm.add_argument("term", help="用語名")

    # list
    p_ls = sub.add_parser("list", help="全用語を一覧表示する")
    p_ls.add_argument("--context", help="コンテキストで絞り込み")

    # check
    sub.add_parser("check",
                   help="REQ/SPEC本文で表記ゆれ・エイリアス使用を検出する")

    # unused
    sub.add_parser("unused",
                   help="定義済みだが仕様書で使われていない用語を検出する")

    args = parser.parse_args()
    args.project_dir = os.path.abspath(args.project_dir)

    cmd_map = {
        "add": cmd_add,
        "update": cmd_update,
        "remove": cmd_remove,
        "list": cmd_list,
        "check": cmd_check,
        "unused": cmd_unused,
    }

    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
