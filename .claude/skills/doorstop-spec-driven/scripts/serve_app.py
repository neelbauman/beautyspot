#!/usr/bin/env python3
"""REST API + SPA サーバー for Doorstop トレーサビリティレポート。

バックエンドで Doorstop tree を一元管理し、全ビュー（ダッシュボード・マトリクス・
グループビュー・アイテム詳細）が API からリアルタイムにデータを取得する。
Edit/Review/Clear 操作も API 経由でバックエンドに反映され、次回のデータ取得時に
全ビューへ自動的に伝播する。

Usage:
    python serve_app.py <project-dir> [--port 8080] [--strict]

API Endpoints:
    GET  /api/overview              ダッシュボード概要
    GET  /api/matrix[?group=NAME]   トレーサビリティマトリクス
    GET  /api/groups                グループ一覧
    GET  /api/group/<name>          グループ詳細
    GET  /api/items[?group=&prefix=] アイテム一覧
    GET  /api/items/<uid>           アイテム詳細
    GET  /api/validation            検証結果
    GET  /api/coverage              カバレッジ
    POST /api/items/<uid>/review    レビュー済みにする
    POST /api/items/<uid>/clear     suspect解消
    POST /api/items/<uid>/edit      テキスト編集
    POST /api/reload                YMLファイルを再読み込み
"""

import html as html_module
import json
import os
import re
import sys
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

try:
    import doorstop
except ImportError:
    print("ERROR: doorstop がインストールされていません。", file=sys.stderr)
    sys.exit(1)

try:
    import markdown as _md

    def render_markdown(text):
        return _md.markdown(text, extensions=["tables", "fenced_code"])
except ImportError:
    def render_markdown(text):
        return f"<p>{html_module.escape(text)}</p>"


# ===================================================================
# Data Store — Single Source of Truth
# ===================================================================

class DoorstopDataStore:
    """Doorstop tree をラップし、全データへの統一アクセスを提供する。

    全ての読み取りと変更がこのクラスを経由する。
    変更操作後は自動でインデックスを再構築するため、
    次回の読み取りでは常に最新のデータが返される。

    外部でYMLファイルが編集された場合も、次回のAPIリクエスト時に
    mtimeの変化を検知してツリーを自動再ビルドする。
    """

    def __init__(self, tree, project_dir, strict=False):
        self.tree = tree
        self.project_dir = project_dir
        self.strict = strict
        self._yml_mtime_snapshot = self._scan_yml_mtimes()
        self._rebuild_indexes()

    # ---------------------------------------------------------------
    # YML file change detection
    # ---------------------------------------------------------------

    def _scan_yml_mtimes(self):
        """全ドキュメントディレクトリ内のYMLファイルのmtimeを収集する。"""
        snapshot = {}
        for doc in self.tree:
            doc_dir = doc.path
            if not os.path.isdir(doc_dir):
                continue
            for fname in os.listdir(doc_dir):
                if fname.endswith(".yml"):
                    fpath = os.path.join(doc_dir, fname)
                    try:
                        snapshot[fpath] = os.path.getmtime(fpath)
                    except OSError:
                        pass
        return snapshot

    def _has_yml_changes(self):
        """前回スナップショットからYMLファイルに変更があるか判定する。"""
        current = {}
        dirs = set()
        for doc in self.tree:
            if os.path.isdir(doc.path):
                dirs.add(doc.path)
        for doc_dir in dirs:
            for fname in os.listdir(doc_dir):
                if fname.endswith(".yml"):
                    fpath = os.path.join(doc_dir, fname)
                    try:
                        current[fpath] = os.path.getmtime(fpath)
                    except OSError:
                        pass
        return current != self._yml_mtime_snapshot

    def reload_if_changed(self):
        """YMLファイルに変更があればツリーを再ビルドする。変更有無を返す。"""
        if not self._has_yml_changes():
            return False
        self.tree = doorstop.build()
        self._yml_mtime_snapshot = self._scan_yml_mtimes()
        self._rebuild_indexes()
        return True

    def force_reload(self):
        """強制的にツリーを再ビルドする。"""
        self.tree = doorstop.build()
        self._yml_mtime_snapshot = self._scan_yml_mtimes()
        self._rebuild_indexes()

    # ---------------------------------------------------------------
    # Internal index management
    # ---------------------------------------------------------------

    def _rebuild_indexes(self):
        self._children_idx = defaultdict(list)
        self._parents_idx = defaultdict(list)
        for doc in self.tree:
            for item in doc:
                for link in item.links:
                    parent = self._find_item(str(link))
                    if parent:
                        self._children_idx[str(link)].append(item)
                        self._parents_idx[str(item.uid)].append(parent)

        self._suspect_uids = set()
        for doc in self.tree:
            for item in doc:
                for link in item.links:
                    parent = self._find_item(str(link))
                    if parent is None:
                        continue
                    if (
                        link.stamp is not None
                        and link.stamp != ""
                        and link.stamp != parent.stamp()
                    ):
                        self._suspect_uids.add(str(item.uid))
                        break

    def _find_item(self, uid_str):
        for doc in self.tree:
            try:
                return doc.find_item(uid_str)
            except Exception:
                continue
        return None

    def _get_group(self, item):
        try:
            g = item.get("group")
            return g if g else "(未分類)"
        except (AttributeError, KeyError):
            return "(未分類)"

    def _get_ref(self, item):
        try:
            return item.ref or ""
        except (AttributeError, KeyError):
            return ""

    def _find_prefix(self, item):
        uid_str = str(item.uid)
        for doc in self.tree:
            try:
                doc.find_item(uid_str)
                return doc.prefix
            except Exception:
                continue
        return "?"

    def _item_to_dict(self, item, prefix=None):
        uid_str = str(item.uid)
        if prefix is None:
            prefix = self._find_prefix(item)
        return {
            "uid": uid_str,
            "prefix": prefix,
            "group": self._get_group(item),
            "text": item.text,
            "text_html": render_markdown(item.text),
            "text_preview": item.text[:100] + ("..." if len(item.text) > 100 else ""),
            "ref": self._get_ref(item),
            "reviewed": bool(item.reviewed),
            "suspect": uid_str in self._suspect_uids,
            "active": bool(item.active),
            "parents": [
                {
                    "uid": str(p.uid),
                    "reviewed": bool(p.reviewed),
                    "suspect": str(p.uid) in self._suspect_uids,
                }
                for p in self._parents_idx.get(uid_str, [])
            ],
            "children": [
                {
                    "uid": str(c.uid),
                    "reviewed": bool(c.reviewed),
                    "suspect": str(c.uid) in self._suspect_uids,
                }
                for c in self._children_idx.get(uid_str, [])
            ],
        }

    def _item_summary(self, item, prefix=None):
        uid_str = str(item.uid)
        if prefix is None:
            prefix = self._find_prefix(item)
        return {
            "uid": uid_str,
            "prefix": prefix,
            "group": self._get_group(item),
            "text_preview": item.text[:80] + ("..." if len(item.text) > 80 else ""),
            "ref": self._get_ref(item),
            "reviewed": bool(item.reviewed),
            "suspect": uid_str in self._suspect_uids,
        }

    # ---------------------------------------------------------------
    # Read operations
    # ---------------------------------------------------------------

    def get_overview(self):
        docs = {}
        total = 0
        reviewed = 0
        for doc in self.tree:
            count = len(list(doc))
            docs[str(doc.prefix)] = count
            total += count
            reviewed += sum(1 for item in doc if item.reviewed)

        groups = sorted({self._get_group(item) for doc in self.tree for item in doc})
        validation = self.get_validation()
        coverage = self.get_coverage()

        return {
            "documents": docs,
            "total_items": total,
            "groups": groups,
            "review": {"total": total, "reviewed": reviewed},
            "suspects": len(self._suspect_uids),
            "suspect_uids": sorted(self._suspect_uids),
            "validation_summary": {
                "errors": len(validation["errors"]),
                "warnings": len(validation["warnings"]),
                "info": len(validation["info"]),
            },
            "coverage": coverage,
        }

    def get_validation(self):
        issues = {"errors": [], "warnings": [], "info": []}

        for document in self.tree:
            for item in document:
                if not item.text.strip():
                    issues["warnings"].append(f"{item.uid}: テキストが空です")
                if not item.active:
                    issues["warnings"].append(f"{item.uid}: 非アクティブです")

        docs = {doc.prefix: doc for doc in self.tree}
        for document in self.tree:
            if not document.parent:
                continue
            parent_doc = docs.get(document.parent)
            if parent_doc is None:
                issues["errors"].append(
                    f"{document.prefix}: 親ドキュメント '{document.parent}' が見つかりません"
                )
                continue

            parent_uids = {str(item.uid) for item in parent_doc}
            for item in document:
                linked_parents = [
                    str(link) for link in item.links
                    if str(link).startswith(document.parent)
                ]
                if not linked_parents:
                    issues["warnings"].append(
                        f"{item.uid} [{self._get_group(item)}]: "
                        f"親ドキュメント {document.parent} へのリンクがありません"
                    )
                for link in linked_parents:
                    link_uid = link.split(":")[0] if ":" in link else link
                    if link_uid not in parent_uids:
                        issues["errors"].append(
                            f"{item.uid}: リンク先 {link_uid} が存在しません"
                        )

            parent_groups = {str(i.uid): self._get_group(i) for i in parent_doc}
            for item in document:
                child_group = self._get_group(item)
                if child_group == "(未分類)":
                    continue
                for link in item.links:
                    link_str = str(link)
                    if link_str in parent_groups:
                        pg = parent_groups[link_str]
                        if pg != "(未分類)" and pg != child_group:
                            issues["warnings"].append(
                                f"{item.uid} [{child_group}] -> {link_str} [{pg}]: "
                                f"クロスグループリンクです"
                            )

            if self.strict:
                child_links = defaultdict(set)
                for item in document:
                    for link in item.links:
                        link_str = str(link)
                        if link_str.startswith(document.parent):
                            child_links[link_str].add(str(item.uid))
                for parent_item in parent_doc:
                    if str(parent_item.uid) not in child_links:
                        issues["warnings"].append(
                            f"{parent_item.uid} [{self._get_group(parent_item)}]: "
                            f"子ドキュメント {document.prefix} からのリンクがありません"
                        )

        ref_docs = {"IMPL", "TST"}
        for document in self.tree:
            if document.prefix not in ref_docs:
                continue
            for item in document:
                ref = self._get_ref(item)
                if not ref:
                    continue
                filepath = ref.split("::")[0]
                full_path = os.path.join(self.project_dir, filepath)
                if not os.path.exists(full_path):
                    issues["warnings"].append(
                        f"{item.uid}: ref '{ref}' のファイルが存在しません"
                    )

        unreviewed = []
        for document in self.tree:
            for item in document:
                if not item.reviewed:
                    unreviewed.append(str(item.uid))
        if unreviewed:
            issues["info"].append(
                f"未レビューアイテム: {len(unreviewed)}件 "
                f"({', '.join(unreviewed[:10])}{'...' if len(unreviewed) > 10 else ''})"
            )

        return issues

    def get_coverage(self):
        docs = {doc.prefix: doc for doc in self.tree}
        coverage = {}

        for doc in self.tree:
            if not doc.parent or doc.parent not in docs:
                continue
            parent_doc = docs[doc.parent]
            parent_uids = {str(item.uid) for item in parent_doc}
            covered_uids = set()

            for item in doc:
                for link in item.links:
                    link_str = str(link)
                    if link_str in parent_uids:
                        covered_uids.add(link_str)

            total = len(parent_uids)
            covered = len(covered_uids)
            pct = (covered / total * 100) if total > 0 else 0.0

            group_cov = defaultdict(lambda: {"total": set(), "covered": set()})
            for pi in parent_doc:
                group_cov[self._get_group(pi)]["total"].add(str(pi.uid))
            for item in doc:
                for link in item.links:
                    link_str = str(link)
                    if link_str in parent_uids:
                        po = parent_doc.find_item(link_str)
                        group_cov[self._get_group(po)]["covered"].add(link_str)

            groups = {}
            for g, d in sorted(group_cov.items()):
                gt, gc = len(d["total"]), len(d["covered"])
                groups[g] = {
                    "total": gt, "covered": gc, "uncovered": gt - gc,
                    "percentage": round(gc / gt * 100, 1) if gt > 0 else 0.0,
                    "uncovered_items": sorted(d["total"] - d["covered"]),
                }

            coverage[f"{doc.prefix} -> {doc.parent}"] = {
                "total": total, "covered": covered, "uncovered": total - covered,
                "percentage": round(pct, 1),
                "uncovered_items": sorted(parent_uids - covered_uids),
                "by_group": groups,
            }

        return coverage

    def get_matrix(self, group=None):
        docs = list(self.tree)
        prefixes = [str(d.prefix) for d in docs]
        matrix = []

        root_docs = [d for d in docs if not d.parent]
        for root_doc in root_docs:
            for item in root_doc:
                row = {root_doc.prefix: item, "_group": self._get_group(item)}
                matrix.append(row)

        def expand_children(doc, parent_prefix):
            child_docs = [d for d in docs if d.parent == doc.prefix]
            for child_doc in child_docs:
                link_map = defaultdict(list)
                for child_item in child_doc:
                    for link in child_item.links:
                        link_str = str(link)
                        if link_str.startswith(parent_prefix):
                            link_map[link_str].append(child_item)

                new_rows = []
                for row in matrix:
                    parent_item = row.get(parent_prefix)
                    if parent_item and str(parent_item.uid) in link_map:
                        children = link_map[str(parent_item.uid)]
                        for i, child in enumerate(children):
                            if i == 0:
                                row[child_doc.prefix] = child
                            else:
                                new_row = dict(row)
                                new_row[child_doc.prefix] = child
                                new_rows.append(new_row)
                matrix.extend(new_rows)
                expand_children(child_doc, child_doc.prefix)

        for root_doc in root_docs:
            expand_children(root_doc, root_doc.prefix)

        result_rows = []
        for row in matrix:
            g = row.get("_group", "(未分類)")
            if group and g != group:
                continue
            cells = {}
            statuses = set()
            uids = []
            for prefix in prefixes:
                item = row.get(prefix)
                if item:
                    uid_str = str(item.uid)
                    uids.append(uid_str)
                    is_suspect = uid_str in self._suspect_uids
                    is_reviewed = bool(item.reviewed)
                    if is_suspect:
                        statuses.add("suspect")
                    if is_reviewed:
                        statuses.add("reviewed")
                    else:
                        statuses.add("unreviewed")
                    cells[prefix] = {
                        "uid": uid_str,
                        "text_preview": item.text[:80] + ("..." if len(item.text) > 80 else ""),
                        "ref": self._get_ref(item),
                        "reviewed": is_reviewed,
                        "suspect": is_suspect,
                    }
                else:
                    cells[prefix] = None
            result_rows.append({
                "group": g,
                "cells": cells,
                "uids": uids,
                "statuses": sorted(statuses),
            })

        return {"prefixes": prefixes, "rows": result_rows}

    def get_groups(self):
        groups = defaultdict(lambda: {"items": 0, "reviewed": 0, "suspect": 0})
        for doc in self.tree:
            for item in doc:
                g = self._get_group(item)
                groups[g]["items"] += 1
                if item.reviewed:
                    groups[g]["reviewed"] += 1
                if str(item.uid) in self._suspect_uids:
                    groups[g]["suspect"] += 1
        return {g: dict(d) for g, d in sorted(groups.items())}

    def get_group_detail(self, group_name):
        group_uids = set()
        for doc in self.tree:
            for item in doc:
                if self._get_group(item) == group_name:
                    group_uids.add(str(item.uid))

        if not group_uids:
            return None

        expanded = set()
        for uid in group_uids:
            expanded |= self._trace_chain(uid)

        items = []
        for doc in self.tree:
            for item in doc:
                if str(item.uid) in expanded:
                    items.append(self._item_to_dict(item, doc.prefix))

        matrix = self.get_matrix(group=group_name)
        local_coverage = self._compute_local_coverage(expanded)

        return {
            "name": group_name,
            "item_count": len(items),
            "items": items,
            "matrix": matrix,
            "coverage": local_coverage,
        }

    def get_item(self, uid):
        item = self._find_item(uid)
        if item is None:
            return None
        data = self._item_to_dict(item)
        # Find prev/next and siblings in the same document
        for doc in self.tree:
            items = list(doc)
            for i, it in enumerate(items):
                if str(it.uid) == uid:
                    data["prev_uid"] = str(items[i - 1].uid) if i > 0 else None
                    data["next_uid"] = str(items[i + 1].uid) if i < len(items) - 1 else None
                    # Siblings = items sharing at least one parent
                    parent_uids = {str(p.uid) for p in self._parents_idx.get(uid, [])}
                    sibling_set = set()
                    for puid in parent_uids:
                        for child in self._children_idx.get(puid, []):
                            cuid = str(child.uid)
                            if cuid != uid:
                                sibling_set.add(cuid)
                    data["siblings"] = [
                        {
                            "uid": s_uid,
                            "reviewed": bool(self._find_item(s_uid).reviewed),
                            "suspect": s_uid in self._suspect_uids,
                        }
                        for s_uid in sorted(sibling_set)
                    ]
                    return data
        return data

    def get_all_items(self, group=None, prefix=None):
        items = []
        for doc in self.tree:
            if prefix and doc.prefix != prefix:
                continue
            for item in doc:
                if group and self._get_group(item) != group:
                    continue
                items.append(self._item_summary(item, doc.prefix))
        return items

    def _trace_chain(self, uid):
        related = set()
        visited_up = set()
        visited_down = set()

        def go_up(u):
            if u in visited_up:
                return
            visited_up.add(u)
            related.add(u)
            for p in self._parents_idx.get(u, []):
                go_up(str(p.uid))

        def go_down(u):
            if u in visited_down:
                return
            visited_down.add(u)
            related.add(u)
            for c in self._children_idx.get(u, []):
                go_down(str(c.uid))

        go_up(uid)
        go_down(uid)
        return related

    def _compute_local_coverage(self, related_uids):
        docs = {doc.prefix: doc for doc in self.tree}
        coverage = {}

        for doc in self.tree:
            if not doc.parent or doc.parent not in docs:
                continue
            parent_doc = docs[doc.parent]

            parent_uids = {str(i.uid) for i in parent_doc if str(i.uid) in related_uids}
            if not parent_uids:
                continue

            covered = set()
            for item in doc:
                if str(item.uid) not in related_uids:
                    continue
                for link in item.links:
                    if str(link) in parent_uids:
                        covered.add(str(link))

            total = len(parent_uids)
            pct = (len(covered) / total * 100) if total > 0 else 0.0
            uncovered = sorted(parent_uids - covered)
            coverage[f"{doc.prefix} -> {doc.parent}"] = {
                "total": total,
                "covered": len(covered),
                "uncovered": total - len(covered),
                "percentage": round(pct, 1),
                "uncovered_items": uncovered,
            }

        return coverage

    # ---------------------------------------------------------------
    # Mutation operations
    # ---------------------------------------------------------------

    def review_item(self, uid):
        item = self._find_item(uid)
        if item is None:
            return None, f"Item {uid} not found"
        item.review()
        self._rebuild_indexes()
        return self.get_item(uid), None

    def clear_item(self, uid):
        item = self._find_item(uid)
        if item is None:
            return None, f"Item {uid} not found"
        # 親アイテムが全てレビュー済みでなければ拒否
        unreviewed_parents = []
        for link in item.links:
            parent = self._find_item(str(link))
            if parent is not None and not parent.reviewed:
                unreviewed_parents.append(str(parent.uid))
        if unreviewed_parents:
            return None, (
                f"親アイテム {', '.join(unreviewed_parents)} が未レビューです。"
                f"先に親をレビューしてからclearしてください。"
            )
        item.clear()
        self._rebuild_indexes()
        return self.get_item(uid), None

    def edit_item(self, uid, text):
        item = self._find_item(uid)
        if item is None:
            return None, f"Item {uid} not found"
        item.text = text
        item.save()
        self._rebuild_indexes()
        return self.get_item(uid), None


# ===================================================================
# HTTP Handler
# ===================================================================

class ReportAPIHandler(BaseHTTPRequestHandler):
    store: DoorstopDataStore

    def do_GET(self):
        self.store.reload_if_changed()

        url = urlparse(self.path)
        path = url.path.rstrip("/")
        params = parse_qs(url.query)

        if path == "/api/overview":
            self._json_ok(self.store.get_overview())
        elif path == "/api/matrix":
            group = params.get("group", [None])[0]
            self._json_ok(self.store.get_matrix(group=group))
        elif path == "/api/groups":
            self._json_ok(self.store.get_groups())
        elif path.startswith("/api/group/"):
            name = path[len("/api/group/"):]
            data = self.store.get_group_detail(name)
            if data:
                self._json_ok(data)
            else:
                self._json_err(404, f"Group '{name}' not found")
        elif path == "/api/items":
            group = params.get("group", [None])[0]
            prefix = params.get("prefix", [None])[0]
            self._json_ok(self.store.get_all_items(group=group, prefix=prefix))
        elif path.startswith("/api/items/"):
            uid = path[len("/api/items/"):]
            data = self.store.get_item(uid)
            if data:
                self._json_ok(data)
            else:
                self._json_err(404, f"Item '{uid}' not found")
        elif path == "/api/validation":
            self._json_ok(self.store.get_validation())
        elif path == "/api/coverage":
            self._json_ok(self.store.get_coverage())
        elif path in ("", "/", "/index.html"):
            self._serve_html(SPA_HTML)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.rstrip("/") == "/api/reload":
            self.store.force_reload()
            self._json_ok({"ok": True, "message": "Tree reloaded"})
            return

        m = re.match(r"^/api/items/([\w]+)/(review|clear|edit)$", self.path)
        if not m:
            self._json_err(404, "Not found")
            return
        uid, action = m.groups()

        try:
            if action == "review":
                result, err = self.store.review_item(uid)
            elif action == "clear":
                result, err = self.store.clear_item(uid)
            elif action == "edit":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                text = body.get("text")
                if text is None:
                    self._json_err(400, "text is required")
                    return
                result, err = self.store.edit_item(uid, text)
            else:
                self._json_err(400, f"Unknown action: {action}")
                return

            if err:
                self._json_err(404, err)
            else:
                self._json_ok({"ok": True, "item": result})
        except Exception as e:
            self._json_err(500, str(e))

    def _json_ok(self, data):
        body = json.dumps(data, ensure_ascii=False, default=list).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_err(self, code, message):
        body = json.dumps({"ok": False, "error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self, html_content):
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"  [{self.log_date_time_string()}] {fmt % args}")


# ===================================================================
# SPA HTML
# ===================================================================

SPA_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Doorstop Traceability Dashboard</title>
<style>
:root {
  --primary: #1a73e8;
  --primary-dark: #1557b0;
  --primary-bg: #e8f0fe;
  --success: #1e8e3e;
  --success-bg: #e6f4ea;
  --warning: #f9ab00;
  --warning-bg: #fef7e0;
  --error: #d93025;
  --error-bg: #fce8e6;
  --suspect: #e65100;
  --suspect-bg: #fff3e0;
  --text: #202124;
  --text-secondary: #5f6368;
  --border: #dadce0;
  --bg: #f8f9fa;
  --surface: #fff;
  --sidebar-w: 240px;
  --panel-w: 520px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: var(--bg); color: var(--text); }

/* Layout */
#sidebar {
  position: fixed; top: 0; left: 0; bottom: 0; width: var(--sidebar-w);
  display: flex; flex-direction: column;
  background: var(--surface); border-right: 1px solid var(--border);
  overflow-y: auto; z-index: 100; padding: 16px 0;
}
#sidebar h2 {
  padding: 0 20px 16px; font-size: 1.1em; color: var(--primary);
  border-bottom: 1px solid var(--border); margin-bottom: 8px;
}
#sidebar ul { list-style: none; }
#sidebar > ul > li > a, #sidebar .nav-section-title {
  display: block; padding: 10px 20px; color: var(--text);
  text-decoration: none; font-size: 0.9em; border-left: 3px solid transparent;
  transition: all 0.15s;
}
#sidebar > ul > li > a:hover { background: var(--bg); }
#sidebar > ul > li > a.active {
  background: var(--primary-bg); color: var(--primary);
  border-left-color: var(--primary); font-weight: 600;
}
.nav-section-title {
  font-weight: 600; font-size: 0.8em !important; color: var(--text-secondary) !important;
  text-transform: uppercase; letter-spacing: 0.5px; margin-top: 12px !important;
  cursor: default;
}
#group-nav-list a {
  display: block; padding: 6px 20px 6px 32px; color: var(--text-secondary);
  text-decoration: none; font-size: 0.85em; transition: all 0.15s;
}
#group-nav-list a:hover { background: var(--bg); color: var(--text); }
#group-nav-list a.active { color: var(--primary); font-weight: 600; background: var(--primary-bg); }
.group-badge {
  display: inline-block; background: var(--primary-bg); color: var(--primary);
  padding: 1px 8px; border-radius: 10px; font-size: 0.75em; font-weight: 600;
  margin-left: 4px;
}

#main {
  margin-left: var(--sidebar-w); padding: 24px 32px; min-height: 100vh;
  transition: margin-right 0.3s;
}
/* Item Panels Container (multi-panel comparison support) */
#item-panels-container {
  position: fixed; top: 0; right: 0; bottom: 0;
  display: flex; z-index: 200; pointer-events: none;
}
#item-panels-container.open { pointer-events: auto; }
.item-panel {
  width: var(--panel-w); min-width: var(--panel-w);
  background: var(--surface); border-left: 1px solid var(--border);
  box-shadow: -4px 0 12px rgba(0,0,0,0.08);
  display: flex; flex-direction: column;
  transform: translateX(100%); transition: transform 0.3s ease, outline-color 0.3s;
  outline: 2px solid transparent;
}
.item-panel.open { transform: translateX(0); }
.item-panel-content {
  flex: 1; overflow-y: auto; padding: 20px;
}
.item-panel .panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding-bottom: 12px; border-bottom: 1px solid var(--border); margin-bottom: 16px;
}
.item-panel .panel-close {
  background: none; border: none; font-size: 1.5em; cursor: pointer;
  color: var(--text-secondary); line-height: 1;
}
.item-panel .panel-close:hover { color: var(--text); }
.item-panel .panel-nav {
  display: flex; justify-content: space-between; gap: 8px;
  padding: 10px 20px; border-top: 1px solid var(--border); background: var(--surface);
  flex-shrink: 0;
}
.item-panel .panel-nav button {
  background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  cursor: pointer; color: var(--text-secondary); font-size: 0.85em;
  padding: 6px 12px; line-height: 1.3; transition: background .15s, color .15s;
}
.item-panel .panel-nav button:hover:not(:disabled) { background: var(--bg); color: var(--text); }
.item-panel .panel-nav button:disabled { opacity: .35; cursor: default; }

/* Cards */
.cards { display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px 20px; flex: 1; min-width: 120px; text-align: center;
}
.card-label { font-size: 0.8em; color: var(--text-secondary); margin-bottom: 4px; }
.card-value { font-size: 1.6em; font-weight: 700; color: var(--primary); }
.card-value.success { color: var(--success); }
.card-value.warning { color: var(--warning); }
.card-value.error { color: var(--error); }
.card-value.suspect { color: var(--suspect); }

/* Tags */
.tag {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 0.78em; font-weight: 600;
}
.tag-group { background: var(--primary-bg); color: var(--primary); }
.tag-prefix { background: #f3e5f5; color: #7b1fa2; }
.tag-ref { background: #e8f5e9; color: #2e7d32; font-family: monospace; font-size: 0.72em; }
.tag-reviewed { background: var(--success-bg); color: var(--success); }
.tag-unreviewed { background: #f1f3f4; color: var(--text-secondary); }
.tag-suspect { background: var(--suspect-bg); color: var(--suspect); }

/* Table */
table { border-collapse: collapse; width: 100%; background: var(--surface); margin: 12px 0; }
th { background: var(--primary); color: #fff; padding: 10px 12px; text-align: left;
     font-size: 0.85em; font-weight: 600; position: sticky; top: 0; z-index: 10; }
th.sortable { cursor: pointer; user-select: none; padding-right: 22px; position: relative; }
th.sortable:hover { background: var(--primary-dark); }
th .sort-arrow { position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
                 font-size: 0.7em; opacity: 0.5; }
th.sort-active .sort-arrow { opacity: 1; }
td { border: 1px solid var(--border); padding: 8px 10px; vertical-align: top; font-size: 0.88em; }
tr:nth-child(even) { background: #f8f9fa; }
tr:hover { background: #eef3fc; }
td.empty { color: #ccc; text-align: center; }
.text-preview { color: var(--text-secondary); font-size: 0.85em; display: block; margin-top: 2px; }
.cell-uid { font-weight: 600; cursor: pointer; color: var(--text); }
.cell-uid:hover { color: var(--primary); text-decoration: underline; }
.cell-status { font-size: 0.78em; margin-left: 4px; }
.status-reviewed { color: var(--success); }
.status-unreviewed { color: #bdbdbd; }
.status-suspect { color: var(--suspect); font-weight: 700; }

/* Filters */
.filter-bar { margin: 12px 0; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.filter-bar label { font-weight: 600; font-size: 0.85em; color: var(--text-secondary); }
.pill {
  padding: 5px 14px; border: 1px solid var(--border); border-radius: 16px;
  background: var(--surface); cursor: pointer; font-size: 0.82em;
  transition: all 0.15s; user-select: none;
}
.pill:hover { background: var(--bg); }
.pill.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.pill.active:hover { background: var(--primary-dark); }
.search-input {
  padding: 6px 14px; border: 1px solid var(--border); border-radius: 16px;
  font-size: 0.85em; width: 200px; outline: none;
}
.search-input:focus { border-color: var(--primary); box-shadow: 0 0 0 2px rgba(26,115,232,0.15); }

/* Action Buttons */
.actions { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
.btn {
  padding: 7px 18px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--surface); cursor: pointer; font-size: 0.85em;
  transition: all 0.15s; font-weight: 500;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.btn-primary:hover:not(:disabled) { background: var(--primary-dark); }
.btn-success { color: var(--success); border-color: var(--success); }
.btn-success:hover:not(:disabled) { background: var(--success-bg); }
.btn-warning { color: var(--suspect); border-color: var(--suspect); }
.btn-warning:hover:not(:disabled) { background: var(--suspect-bg); }
.btn-edit { color: var(--primary); border-color: var(--primary); }
.btn-edit:hover:not(:disabled) { background: var(--primary-bg); }

/* Editor */
.editor-area {
  width: 100%; min-height: 150px; padding: 12px; border: 1px solid var(--primary);
  border-radius: 6px; font-family: monospace; font-size: 0.88em; line-height: 1.6;
  resize: vertical; box-sizing: border-box;
}
.editor-area:focus { outline: none; box-shadow: 0 0 0 2px rgba(26,115,232,0.2); }

/* TipTap Rich Editor */
.tiptap-wrap { border: 1px solid var(--primary); border-radius: 6px; overflow: hidden; }
.tiptap-wrap:focus-within { box-shadow: 0 0 0 2px rgba(26,115,232,0.2); }
.tiptap-toolbar {
  display: flex; gap: 2px; padding: 4px 6px; border-bottom: 1px solid var(--border);
  background: #f8f9fa; flex-wrap: wrap; align-items: center;
}
.tiptap-toolbar button {
  padding: 4px 7px; border: 1px solid transparent; border-radius: 4px;
  background: none; cursor: pointer; font-size: 12px; color: var(--text);
  line-height: 1.2; font-weight: 600;
}
.tiptap-toolbar button:hover { background: var(--primary-bg); }
.tiptap-toolbar button.is-active {
  background: var(--primary-bg); border-color: var(--primary); color: var(--primary);
}
.tiptap-toolbar .tb-sep {
  display: inline-block; width: 1px; height: 18px; background: var(--border); margin: 0 3px;
  vertical-align: middle;
}
.tiptap-wrap .ProseMirror {
  padding: 12px; min-height: 150px; max-height: 60vh; overflow-y: auto;
  outline: none; font-size: 0.92em; line-height: 1.7; color: var(--text);
}
.tiptap-wrap .ProseMirror > *:first-child { margin-top: 0; }
.tiptap-wrap .ProseMirror p { margin: 4px 0; }
.tiptap-wrap .ProseMirror h1 { font-size: 1.4em; margin: 16px 0 8px; font-weight: 600; }
.tiptap-wrap .ProseMirror h2 { font-size: 1.2em; margin: 14px 0 6px; font-weight: 600; }
.tiptap-wrap .ProseMirror h3 { font-size: 1.05em; margin: 12px 0 4px; font-weight: 600; }
.tiptap-wrap .ProseMirror ul, .tiptap-wrap .ProseMirror ol { padding-left: 24px; margin: 4px 0; }
.tiptap-wrap .ProseMirror li { margin: 2px 0; }
.tiptap-wrap .ProseMirror code {
  background: #f1f3f4; padding: 1px 5px; border-radius: 3px;
  font-family: monospace; font-size: 0.9em;
}
.tiptap-wrap .ProseMirror pre {
  background: #f1f3f4; padding: 12px; border-radius: 6px; margin: 8px 0;
  font-family: monospace; font-size: 0.85em; overflow-x: auto;
}
.tiptap-wrap .ProseMirror pre code { background: none; padding: 0; font-size: 1em; }
.tiptap-wrap .ProseMirror blockquote {
  border-left: 3px solid var(--primary); margin: 8px 0; padding-left: 12px;
  color: var(--text-secondary);
}
.tiptap-wrap .ProseMirror hr { border: none; border-top: 2px solid var(--border); margin: 12px 0; }

/* Item text (markdown rendered) */
.item-text { line-height: 1.7; color: var(--text); }
.item-text p { margin: 6px 0; }
.item-text code { background: #f1f3f4; padding: 1px 5px; border-radius: 3px;
                  font-size: 0.88em; font-family: monospace; }
.item-text pre { background: #f1f3f4; padding: 12px; border-radius: 6px;
                 overflow-x: auto; font-size: 0.85em; }
.item-text pre code { background: none; padding: 0; }
.item-text ul, .item-text ol { margin: 6px 0; padding-left: 24px; }
.item-text table { border-collapse: collapse; margin: 8px 0; }
.item-text table th, .item-text table td { border: 1px solid var(--border); padding: 6px 10px; }
.item-text table th { background: #f1f3f4; }

/* Link list in item detail */
.link-list { display: flex; gap: 6px; flex-wrap: wrap; margin: 4px 0; }
.link-chip {
  display: inline-block; padding: 3px 10px; border-radius: 12px;
  font-size: 0.82em; cursor: pointer; text-decoration: none; font-weight: 500;
  background: var(--bg); color: var(--text); border: 1px solid var(--border);
  transition: all 0.15s; user-select: none;
}
.link-chip:hover { background: var(--primary-bg); color: var(--primary); border-color: var(--primary); }
.link-chip.suspect { background: var(--suspect-bg); color: var(--suspect); border-color: var(--suspect); }
.link-chip.unreviewed { color: var(--text-secondary); }

/* Coverage */
.coverage-bar {
  display: inline-block; width: 60px; height: 8px; background: #e0e0e0;
  border-radius: 4px; overflow: hidden; vertical-align: middle; margin-right: 6px;
}
.coverage-fill { display: block; height: 100%; border-radius: 4px; transition: width 0.3s; }

/* Toast */
.toast {
  position: fixed; bottom: 20px; right: 20px; padding: 12px 24px;
  border-radius: 8px; color: #fff; font-size: 0.9em; z-index: 9999;
  animation: toastAnim 3s ease forwards; pointer-events: none;
}
.toast-success { background: var(--success); }
.toast-error { background: var(--error); }
@keyframes toastAnim {
  0% { opacity: 0; transform: translateY(20px); }
  8% { opacity: 1; transform: translateY(0); }
  75% { opacity: 1; }
  100% { opacity: 0; }
}

/* Loading */
.loading { text-align: center; padding: 40px; color: var(--text-secondary); }

/* Section */
.section-title { font-size: 1.15em; font-weight: 700; margin: 24px 0 8px; color: var(--text); }
.section-title:first-child { margin-top: 0; }
.page-title { font-size: 1.4em; font-weight: 700; margin-bottom: 4px; }
.page-subtitle { font-size: 0.88em; color: var(--text-secondary); margin-bottom: 16px; }

/* Issues */
.issue-item { padding: 6px 0; font-size: 0.88em; border-bottom: 1px solid #f1f3f4; }
.issue-error { color: var(--error); }
.issue-warning { color: #e37400; }
.issue-info { color: var(--primary); }

/* Misc */
.hidden { display: none !important; }
.empty-state { text-align: center; padding: 40px; color: var(--text-secondary); }
.meta-row { display: flex; gap: 8px; align-items: center; margin: 6px 0; font-size: 0.88em; }
.meta-label { font-weight: 600; color: var(--text-secondary); min-width: 40px; }

@media (max-width: 900px) {
  #sidebar { width: 56px; }
  #sidebar h2, #sidebar a span, #sidebar .nav-section-title, #group-nav-list { display: none; }
  #main { margin-left: 56px; padding: 16px; }
  .item-panel { width: 100% !important; min-width: 100% !important; }
  .item-panel:not(:last-child) { display: none; }
}
</style>
</head>
<body>

<nav id="sidebar">
  <h2>Doorstop Dashboard</h2>
  <ul>
    <li><a href="#/" data-nav="dashboard">Dashboard</a></li>
    <li><a href="#/matrix" data-nav="matrix">Matrix</a></li>
    <li><span class="nav-section-title">Groups</span></li>
  </ul>
  <ul id="group-nav-list"></ul>
  <ul>
    <li><a href="#/validation" data-nav="validation">Validation</a></li>
  </ul>
  <div style="padding:12px 16px; border-top:1px solid var(--border); margin-top:auto;">
    <button id="reload-btn" onclick="forceReload()" style="width:100%; padding:8px; border:1px solid var(--border); border-radius:6px; background:var(--bg); cursor:pointer; font-size:13px; display:flex; align-items:center; justify-content:center; gap:6px;" title="Reload from disk">
      <span style="font-size:16px;">&#x21bb;</span> <span>Reload</span>
    </button>
  </div>
</nav>

<main id="main">
  <div class="loading">Loading...</div>
</main>

<div id="item-panels-container"></div>

<script>
// ===================================================================
// API helper
// ===================================================================
const API = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },
  async post(path, body) {
    const res = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: body ? JSON.stringify(body) : undefined,
    });
    return res.json();
  },
};

// ===================================================================
// Utility
// ===================================================================
const h = s => {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
};

function toast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast toast-' + (type || 'success');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// ===================================================================
// Rich Editor (TipTap) — CDN loader with offline fallback
// ===================================================================
let richEditorReady = false;
let RichEditor = {};
(async () => {
  const timeout = (ms) => new Promise((_, r) => setTimeout(() => r(new Error('timeout')), ms));
  try {
    const [coreMod, skMod, tdMod] = await Promise.race([
      Promise.all([
        import('https://esm.sh/@tiptap/core@2'),
        import('https://esm.sh/@tiptap/starter-kit@2'),
        import('https://esm.sh/turndown@7'),
      ]),
      timeout(5000),
    ]);
    RichEditor = {
      Editor: coreMod.Editor,
      Extension: coreMod.Extension,
      StarterKit: skMod.StarterKit || skMod.default,
      TurndownService: tdMod.default || tdMod,
    };
    richEditorReady = true;
    console.log('Rich editor loaded (online mode)');
  } catch (e) {
    console.warn('Rich editor unavailable (offline mode):', e.message);
  }
})();

async function forceReload() {
  const btn = document.getElementById('reload-btn');
  btn.disabled = true;
  btn.querySelector('span:last-child').textContent = 'Reloading...';
  try {
    await API.post('/api/reload');
    toast('Reloaded from disk');
    refreshCurrentView();
    refreshOtherPanels(null);
  } catch (e) {
    toast('Reload failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.querySelector('span:last-child').textContent = 'Reload';
  }
}

function coverageColor(pct) {
  if (pct === 100) return 'var(--success)';
  if (pct >= 50) return 'var(--warning)';
  return 'var(--error)';
}

function statusIcons(reviewed, suspect) {
  let s = '';
  if (suspect) s += '<span class="cell-status status-suspect">&#x26A0;</span>';
  if (reviewed) s += '<span class="cell-status status-reviewed">&#x2713;</span>';
  else s += '<span class="cell-status status-unreviewed">&#x25CB;</span>';
  return s;
}

function statusTags(reviewed, suspect) {
  let s = '';
  if (suspect) s += '<span class="tag tag-suspect">Suspect</span> ';
  if (reviewed) s += '<span class="tag tag-reviewed">Reviewed</span>';
  else s += '<span class="tag tag-unreviewed">Unreviewed</span>';
  return s;
}

// ===================================================================
// Router
// ===================================================================
let currentView = '';
let currentParam = '';

function route() {
  const hash = (location.hash || '#/').slice(1);
  const parts = hash.split('/').filter(Boolean);
  const view = parts[0] || 'dashboard';
  const param = parts.slice(1).join('/');

  // Only re-render if view changed (not for item panel opens)
  if (view === 'item') {
    openItemPanel(param);
    return;
  }

  currentView = view;
  currentParam = param;

  // Update sidebar active state
  document.querySelectorAll('#sidebar a').forEach(a => a.classList.remove('active'));
  const navKey = view === 'group' ? null : view === 'dashboard' ? 'dashboard' : view;
  if (navKey) {
    const el = document.querySelector(`[data-nav="${navKey}"]`);
    if (el) el.classList.add('active');
  }
  if (view === 'group') {
    document.querySelectorAll('#group-nav-list a').forEach(a => {
      a.classList.toggle('active', a.dataset.group === decodeURIComponent(param));
    });
  }

  closeItemPanel();

  switch (view) {
    case 'dashboard': renderDashboard(); break;
    case 'matrix': renderMatrix(); break;
    case 'group': renderGroup(decodeURIComponent(param)); break;
    case 'validation': renderValidation(); break;
    default: renderDashboard();
  }
}

window.addEventListener('hashchange', route);

// ===================================================================
// Sidebar group list
// ===================================================================
async function loadGroupNav() {
  const groups = await API.get('/api/groups');
  const list = document.getElementById('group-nav-list');
  list.innerHTML = Object.entries(groups).map(([name, info]) =>
    `<li><a href="#/group/${encodeURIComponent(name)}" data-group="${h(name)}">${h(name)} <span class="group-badge">${info.items}</span></a></li>`
  ).join('');
}

// ===================================================================
// Views
// ===================================================================
const $main = () => document.getElementById('main');

// --- Dashboard ---
async function renderDashboard() {
  $main().innerHTML = '<div class="loading">Loading...</div>';
  const data = await API.get('/api/overview');
  const rv = data.review;
  const vs = data.validation_summary;

  let coverageHtml = '';
  for (const [pair, cov] of Object.entries(data.coverage)) {
    const color = coverageColor(cov.percentage);
    coverageHtml += `<tr>
      <td><strong>${h(pair)}</strong></td>
      <td>${cov.covered} / ${cov.total}</td>
      <td><span class="coverage-bar"><span class="coverage-fill" style="width:${cov.percentage}%;background:${color}"></span></span> <strong style="color:${color}">${cov.percentage}%</strong></td>
      <td style="font-size:0.85em;color:var(--text-secondary)">${cov.uncovered_items.length ? h(cov.uncovered_items.join(', ')) : '&#8212;'}</td>
    </tr>`;
    if (cov.by_group) {
      for (const [g, gd] of Object.entries(cov.by_group)) {
        const gc = coverageColor(gd.percentage);
        coverageHtml += `<tr style="font-size:0.88em">
          <td style="padding-left:28px">${h(pair)}</td>
          <td><span class="tag tag-group">${h(g)}</span> ${gd.covered}/${gd.total}</td>
          <td><span class="coverage-bar"><span class="coverage-fill" style="width:${gd.percentage}%;background:${gc}"></span></span> <span style="color:${gc}">${gd.percentage}%</span></td>
          <td style="font-size:0.85em;color:var(--text-secondary)">${gd.uncovered_items.length ? h(gd.uncovered_items.join(', ')) : '&#8212;'}</td>
        </tr>`;
      }
    }
  }

  let docsHtml = Object.entries(data.documents).map(([prefix, count]) =>
    `<div class="card"><div class="card-label">${h(prefix)}</div><div class="card-value">${count}</div></div>`
  ).join('');

  $main().innerHTML = `
    <div class="page-title">Dashboard</div>
    <div class="page-subtitle">Doorstop Traceability Overview</div>
    <div class="cards">
      ${docsHtml}
      <div class="card"><div class="card-label">Reviewed</div><div class="card-value ${rv.reviewed===rv.total?'success':''}">${rv.reviewed}/${rv.total}</div></div>
      <div class="card"><div class="card-label">Suspects</div><div class="card-value ${data.suspects?'suspect':'success'}">${data.suspects}</div></div>
      <div class="card"><div class="card-label">Errors</div><div class="card-value ${vs.errors?'error':'success'}">${vs.errors}</div></div>
      <div class="card"><div class="card-label">Warnings</div><div class="card-value ${vs.warnings?'warning':'success'}">${vs.warnings}</div></div>
    </div>

    <div class="section-title">Groups</div>
    <div class="cards" id="dash-groups"></div>

    <div class="section-title">Coverage</div>
    <table>
      <tr><th>Link Direction</th><th>Coverage</th><th>Rate</th><th>Uncovered</th></tr>
      ${coverageHtml}
    </table>
  `;

  // Group cards
  const groups = await API.get('/api/groups');
  document.getElementById('dash-groups').innerHTML = Object.entries(groups).map(([name, info]) => {
    const pct = info.items ? Math.round(info.reviewed / info.items * 100) : 0;
    return `<div class="card" style="cursor:pointer;min-width:150px" onclick="location.hash='#/group/${encodeURIComponent(name)}'">
      <div class="card-label"><span class="tag tag-group">${h(name)}</span></div>
      <div style="font-size:0.85em;margin-top:6px">${info.items} items, ${info.reviewed} reviewed${info.suspect ? ', <span style="color:var(--suspect)">' + info.suspect + ' suspect</span>' : ''}</div>
      <div style="margin-top:4px"><span class="coverage-bar" style="width:80px"><span class="coverage-fill" style="width:${pct}%;background:${coverageColor(pct)}"></span></span> ${pct}%</div>
    </div>`;
  }).join('');
}

// --- Matrix ---
let matrixData = null;
let matrixFilters = { groups: new Set(), statuses: new Set(), query: '', sortCol: -1, sortDir: 'asc' };

function naturalCompare(a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

async function renderMatrix() {
  $main().innerHTML = '<div class="loading">Loading...</div>';
  matrixData = await API.get('/api/matrix');
  matrixFilters = { groups: new Set(), statuses: new Set(), query: '', sortCol: -1, sortDir: 'asc' };
  renderMatrixView();
}

function renderMatrixView() {
  if (!matrixData) return;
  const prev = document.activeElement;
  const hadSearchFocus = prev && prev.classList.contains('search-input');
  const cursorPos = hadSearchFocus ? prev.selectionStart : 0;
  const { prefixes, rows } = matrixData;

  const allGroups = [...new Set(rows.map(r => r.group))].sort();
  const groupPills = allGroups.map(g =>
    `<span class="pill ${matrixFilters.groups.has(g)?'active':''}" onclick="toggleMatrixGroup('${h(g)}')">${h(g)}</span>`
  ).join('');

  const statusPills = ['reviewed','unreviewed','suspect'].map(s =>
    `<span class="pill ${matrixFilters.statuses.has(s)?'active':''}" onclick="toggleMatrixStatus('${s}')">${s==='reviewed'?'&#x2713; Reviewed':s==='unreviewed'?'&#x25CB; Unreviewed':'&#x26A0; Suspect'}</span>`
  ).join('');

  const sortArrowHtml = (colIdx) => {
    const active = matrixFilters.sortCol === colIdx;
    const arrow = active ? (matrixFilters.sortDir === 'asc' ? '&#x25B2;' : '&#x25BC;') : '&#x25B2;&#x25BC;';
    return `<th class="sortable ${active?'sort-active':''}" onclick="toggleMatrixSort(${colIdx})">`;
  };
  let headerCells = `${sortArrowHtml(0)}Group<span class="sort-arrow">${matrixFilters.sortCol===0?(matrixFilters.sortDir==='asc'?'&#x25B2;':'&#x25BC;'):'&#x25B2;&#x25BC;'}</span></th>`;
  prefixes.forEach((p, i) => {
    const ci = i + 1;
    const active = matrixFilters.sortCol === ci;
    const arrowText = active ? (matrixFilters.sortDir==='asc'?'&#x25B2;':'&#x25BC;') : '&#x25B2;&#x25BC;';
    headerCells += `${sortArrowHtml(ci)}${h(p)}<span class="sort-arrow">${arrowText}</span></th>`;
  });

  // Filter rows
  let filtered = rows.filter(row => {
    if (matrixFilters.groups.size > 0 && !matrixFilters.groups.has(row.group)) return false;
    if (matrixFilters.statuses.size > 0 && !row.statuses.some(s => matrixFilters.statuses.has(s))) return false;
    if (matrixFilters.query) {
      const q = matrixFilters.query.toUpperCase();
      if (!row.uids.some(u => u.toUpperCase().includes(q))) return false;
    }
    return true;
  });

  // Sort rows
  if (matrixFilters.sortCol >= 0) {
    const col = matrixFilters.sortCol;
    filtered.sort((a, b) => {
      let aKey, bKey;
      if (col === 0) {
        aKey = a.group || '';
        bKey = b.group || '';
      } else {
        const prefix = prefixes[col - 1];
        aKey = a.cells[prefix]?.uid || '';
        bKey = b.cells[prefix]?.uid || '';
      }
      const cmp = naturalCompare(aKey, bKey);
      return matrixFilters.sortDir === 'asc' ? cmp : -cmp;
    });
  }

  let bodyRows = '';
  for (const row of filtered) {
    let cells = `<td><span class="tag tag-group">${h(row.group)}</span></td>`;
    for (const prefix of prefixes) {
      const cell = row.cells[prefix];
      if (cell) {
        const refHtml = cell.ref ? `<br><span class="tag tag-ref">${h(cell.ref)}</span>` : '';
        cells += `<td>
          <span class="cell-uid" onclick="handleCellClick(event,'${cell.uid}')">${h(cell.uid)}</span>
          ${statusIcons(cell.reviewed, cell.suspect)}
          <span class="text-preview">${h(cell.text_preview)}</span>
          ${refHtml}
        </td>`;
      } else {
        cells += '<td class="empty">&#8212;</td>';
      }
    }
    bodyRows += `<tr>${cells}</tr>`;
  }

  $main().innerHTML = `
    <div class="page-title">Traceability Matrix</div>
    <div class="page-subtitle">&#x2713;=Reviewed  &#x25CB;=Unreviewed  &#x26A0;=Suspect &mdash; Click UID for detail</div>

    <div class="filter-bar">
      <label>Group:</label>
      <span class="pill ${matrixFilters.groups.size===0?'active':''}" onclick="clearMatrixGroups()">All</span>
      ${groupPills}
    </div>
    <div class="filter-bar">
      <label>Status:</label>
      ${statusPills}
      <label style="margin-left:12px">ID:</label>
      <input class="search-input" type="text" placeholder="e.g. SPEC001" value="${h(matrixFilters.query)}" oninput="matrixFilters.query=this.value;renderMatrixView()">
    </div>

    <table>
      <tr>${headerCells}</tr>
      ${bodyRows || '<tr><td colspan="'+(prefixes.length+1)+'" class="empty">No matching items</td></tr>'}
    </table>
  `;
  if (hadSearchFocus) {
    const inp = $main().querySelector('.search-input');
    if (inp) { inp.focus(); inp.setSelectionRange(cursorPos, cursorPos); }
  }
}

function toggleMatrixGroup(g) {
  if (matrixFilters.groups.has(g)) matrixFilters.groups.delete(g);
  else matrixFilters.groups.add(g);
  renderMatrixView();
}
function clearMatrixGroups() {
  matrixFilters.groups.clear();
  renderMatrixView();
}
function toggleMatrixStatus(s) {
  if (matrixFilters.statuses.has(s)) matrixFilters.statuses.delete(s);
  else matrixFilters.statuses.add(s);
  renderMatrixView();
}
function toggleMatrixSort(colIdx) {
  if (matrixFilters.sortCol === colIdx) {
    matrixFilters.sortDir = matrixFilters.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    matrixFilters.sortCol = colIdx;
    matrixFilters.sortDir = 'asc';
  }
  renderMatrixView();
}

// --- Group Detail ---
async function renderGroup(name) {
  $main().innerHTML = '<div class="loading">Loading...</div>';
  let data;
  try {
    data = await API.get('/api/group/' + encodeURIComponent(name));
  } catch {
    $main().innerHTML = `<div class="empty-state">Group "${h(name)}" not found.</div>`;
    return;
  }

  const items = data.items;
  const reviewed = items.filter(i => i.reviewed).length;
  const suspects = items.filter(i => i.suspect).length;

  // Coverage table
  let covHtml = '';
  for (const [pair, cov] of Object.entries(data.coverage)) {
    const color = coverageColor(cov.percentage);
    covHtml += `<tr>
      <td>${h(pair)}</td>
      <td>${cov.covered}/${cov.total}</td>
      <td><span class="coverage-bar"><span class="coverage-fill" style="width:${cov.percentage}%;background:${color}"></span></span> <strong style="color:${color}">${cov.percentage}%</strong></td>
      <td style="font-size:0.85em">${cov.uncovered_items.length ? h(cov.uncovered_items.join(', ')) : '&#8212;'}</td>
    </tr>`;
  }

  // Matrix
  const mat = data.matrix;
  let matHeader = '<th>Group</th>' + mat.prefixes.map(p => `<th>${h(p)}</th>`).join('');
  let matBody = '';
  for (const row of mat.rows) {
    let cells = `<td><span class="tag tag-group">${h(row.group)}</span></td>`;
    for (const prefix of mat.prefixes) {
      const cell = row.cells[prefix];
      if (cell) {
        cells += `<td>
          <span class="cell-uid" onclick="handleCellClick(event,'${cell.uid}')">${h(cell.uid)}</span>
          ${statusIcons(cell.reviewed, cell.suspect)}
          <span class="text-preview">${h(cell.text_preview)}</span>
        </td>`;
      } else {
        cells += '<td class="empty">&#8212;</td>';
      }
    }
    matBody += `<tr>${cells}</tr>`;
  }

  // Item list
  let itemsHtml = '';
  const byPrefix = {};
  for (const item of items) {
    (byPrefix[item.prefix] = byPrefix[item.prefix] || []).push(item);
  }
  for (const [prefix, pitems] of Object.entries(byPrefix)) {
    itemsHtml += `<div class="section-title"><span class="tag tag-prefix">${h(prefix)}</span> (${pitems.length})</div>`;
    for (const item of pitems) {
      itemsHtml += `<div style="padding:8px 0;border-bottom:1px solid #f1f3f4;display:flex;align-items:center;gap:8px">
        <span class="cell-uid" onclick="handleCellClick(event,'${item.uid}')" style="min-width:70px">${h(item.uid)}</span>
        ${statusTags(item.reviewed, item.suspect)}
        <span class="text-preview" style="flex:1">${h(item.text_preview)}</span>
        ${item.ref ? '<span class="tag tag-ref">'+h(item.ref)+'</span>' : ''}
      </div>`;
    }
  }

  $main().innerHTML = `
    <div class="page-title">Group: ${h(name)}</div>
    <div class="page-subtitle">${items.length} items in chain</div>

    <div class="cards">
      <div class="card"><div class="card-label">Items</div><div class="card-value">${items.length}</div></div>
      <div class="card"><div class="card-label">Reviewed</div><div class="card-value ${reviewed===items.length?'success':''}">${reviewed}/${items.length}</div></div>
      <div class="card"><div class="card-label">Suspects</div><div class="card-value ${suspects?'suspect':'success'}">${suspects}</div></div>
    </div>

    <div class="section-title">Coverage (Local)</div>
    <table>
      <tr><th>Link Direction</th><th>Coverage</th><th>Rate</th><th>Uncovered</th></tr>
      ${covHtml || '<tr><td colspan="4" class="empty">No coverage data</td></tr>'}
    </table>

    <div class="section-title">Traceability Matrix</div>
    <table>
      <tr>${matHeader}</tr>
      ${matBody || '<tr><td colspan="'+(mat.prefixes.length+1)+'" class="empty">No items</td></tr>'}
    </table>

    <div class="section-title">Items</div>
    ${itemsHtml || '<div class="empty-state">No items</div>'}
  `;
}

// --- Validation ---
async function renderValidation() {
  $main().innerHTML = '<div class="loading">Loading...</div>';
  const data = await API.get('/api/validation');

  const renderList = (items, cls) =>
    items.length ? items.map(i => `<div class="issue-item ${cls}">${h(i)}</div>`).join('')
    : `<div style="padding:8px 0;color:var(--success);font-weight:600">No issues.</div>`;

  $main().innerHTML = `
    <div class="page-title">Validation Results</div>
    <div class="page-subtitle">Structure, link, and reference checks</div>

    <div class="cards">
      <div class="card"><div class="card-label">Errors</div><div class="card-value ${data.errors.length?'error':'success'}">${data.errors.length}</div></div>
      <div class="card"><div class="card-label">Warnings</div><div class="card-value ${data.warnings.length?'warning':'success'}">${data.warnings.length}</div></div>
      <div class="card"><div class="card-label">Info</div><div class="card-value">${data.info.length}</div></div>
    </div>

    ${data.errors.length ? '<div class="section-title" style="color:var(--error)">Errors</div>' + renderList(data.errors, 'issue-error') : ''}
    ${data.warnings.length ? '<div class="section-title" style="color:#e37400">Warnings</div>' + renderList(data.warnings, 'issue-warning') : ''}
    ${data.info.length ? '<div class="section-title" style="color:var(--primary)">Info</div>' + renderList(data.info, 'issue-info') : ''}
  `;
}

// ===================================================================
// Item Panels — Multi-panel comparison support
// ===================================================================
// Ctrl+click or Shift+click on Parents/Children/Siblings link-chips
// opens a new panel side-by-side for comparison. Normal click navigates
// within the current panel.
// ===================================================================
let panelIdCounter = 0;
let activePanels = []; // { id, uid, editMode, el }

function handleCellClick(event, uid) {
  if (event.ctrlKey || event.metaKey || event.shiftKey) {
    event.preventDefault();
    addItemPanel(uid);
  } else {
    location.hash = '#/item/' + uid;
  }
}

function handlePanelItemClick(event, panelId, uid) {
  if (event.ctrlKey || event.metaKey || event.shiftKey) {
    event.preventDefault();
    event.stopPropagation();
    addItemPanel(uid);
  } else {
    navigateInPanel(panelId, uid);
  }
}

function handlePanelNav(event, panelId, targetUid) {
  if (event.ctrlKey || event.metaKey || event.shiftKey) {
    event.preventDefault();
    event.stopPropagation();
    addItemPanel(targetUid);
  } else {
    navigateInPanel(panelId, targetUid);
  }
}

function createPanelElement(panelId) {
  const el = document.createElement('div');
  el.className = 'item-panel';
  el.dataset.panelId = panelId;
  el.innerHTML = `
    <div class="item-panel-content" id="pc-${panelId}"><div class="loading">Loading...</div></div>
    <div class="panel-nav" id="pn-${panelId}"></div>
  `;
  return el;
}

function updateMainMargin() {
  const main = document.getElementById('main');
  const count = activePanels.length;
  if (count > 0) {
    main.style.marginRight = (count * 520) + 'px';
  } else {
    main.style.marginRight = '';
  }
}

async function openItemPanel(uid) {
  if (!uid) return;
  // Single panel already showing this uid — nothing to do
  if (activePanels.length === 1 && activePanels[0].uid === uid) return;
  // Single panel open — navigate within it
  if (activePanels.length === 1) {
    await navigateInPanel(activePanels[0].id, uid);
    return;
  }
  // Otherwise close all and open single
  closeAllPanels();
  await addItemPanel(uid);
}

async function addItemPanel(uid) {
  if (!uid) return;
  // Don't add duplicate — flash existing instead
  const existing = activePanels.find(p => p.uid === uid);
  if (existing) {
    existing.el.style.outlineColor = 'var(--primary)';
    setTimeout(() => { existing.el.style.outlineColor = 'transparent'; }, 800);
    return;
  }

  const id = panelIdCounter++;
  const container = document.getElementById('item-panels-container');
  const panelEl = createPanelElement(id);
  container.appendChild(panelEl);

  const ps = { id, uid, editMode: false, el: panelEl };
  activePanels.push(ps);

  container.classList.add('open');
  updateMainMargin();
  requestAnimationFrame(() => panelEl.classList.add('open'));

  try {
    const data = await API.get('/api/items/' + uid);
    renderPanelContent(ps, data);
  } catch {
    panelEl.querySelector('.item-panel-content').innerHTML =
      `<div class="empty-state">Item "${h(uid)}" not found.</div>`;
  }
}

async function navigateInPanel(panelId, targetUid) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) { openItemPanel(targetUid); return; }
  // Check if another panel already shows this uid
  const dup = activePanels.find(p => p.uid === targetUid && p.id !== panelId);
  if (dup) {
    dup.el.style.outlineColor = 'var(--primary)';
    setTimeout(() => { dup.el.style.outlineColor = 'transparent'; }, 800);
    return;
  }
  ps.uid = targetUid;
  ps.editMode = false;
  if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
  const contentEl = document.getElementById('pc-' + panelId);
  contentEl.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const data = await API.get('/api/items/' + targetUid);
    renderPanelContent(ps, data);
  } catch {
    contentEl.innerHTML = `<div class="empty-state">Item "${h(targetUid)}" not found.</div>`;
  }
}

function closePanel(panelId) {
  const idx = activePanels.findIndex(p => p.id === panelId);
  if (idx === -1) return;
  const ps = activePanels[idx];
  if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
  ps.el.classList.remove('open');
  setTimeout(() => {
    ps.el.remove();
    activePanels.splice(activePanels.findIndex(p => p.id === panelId), 1);
    updateMainMargin();
    if (activePanels.length === 0) {
      document.getElementById('item-panels-container').classList.remove('open');
      if (location.hash.startsWith('#/item/')) {
        const prev = '#/' + currentView + (currentParam ? '/' + currentParam : '');
        history.replaceState(null, '', prev);
      }
    }
  }, 300);
}

function closeAllPanels() {
  for (const ps of activePanels) { if (ps.editor) { ps.editor.destroy(); ps.editor = null; } }
  const container = document.getElementById('item-panels-container');
  container.innerHTML = '';
  container.classList.remove('open');
  activePanels = [];
  updateMainMargin();
  if (location.hash.startsWith('#/item/')) {
    const prev = '#/' + currentView + (currentParam ? '/' + currentParam : '');
    history.replaceState(null, '', prev);
  }
}

function closeItemPanel() { closeAllPanels(); }

function renderPanelContent(ps, data) {
  if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
  ps.editMode = false;
  const pid = ps.id;
  const contentEl = document.getElementById('pc-' + pid);

  const chipHtml = (items) => items.length
    ? items.map(it =>
        `<a class="link-chip ${it.suspect?'suspect':''} ${!it.reviewed?'unreviewed':''}" onclick="handlePanelItemClick(event,${pid},'${it.uid}')">${h(it.uid)}${it.suspect?' &#x26A0;':''}${!it.reviewed?' &#x25CB;':''}</a>`
      ).join('')
    : '<span style="color:var(--text-secondary)">&#8212;</span>';

  const parentsHtml = chipHtml(data.parents);
  const childrenHtml = chipHtml(data.children);
  const siblingsHtml = chipHtml(data.siblings || []);

  contentEl.innerHTML = `
    <div class="panel-header">
      <div>
        <strong style="font-size:1.15em">${h(data.uid)}</strong>
        <span class="tag tag-prefix">${h(data.prefix)}</span>
        <span class="tag tag-group">${h(data.group)}</span>
      </div>
      <button class="panel-close" onclick="closePanel(${pid})">&times;</button>
    </div>

    <div style="margin-bottom:12px">${statusTags(data.reviewed, data.suspect)}</div>

    <div id="ptv-${pid}" class="item-text">${data.text_html}</div>
    <div id="pte-${pid}" class="hidden">
      <textarea id="pta-${pid}" class="editor-area">${h(data.text)}</textarea>
      <div id="prich-${pid}" class="tiptap-wrap hidden"></div>
      <div class="actions" style="margin-top:8px">
        <button class="btn btn-primary" id="psb-${pid}" onclick="panelSave(${pid})">Save</button>
        <button class="btn" onclick="panelCancelEdit(${pid})">Cancel</button>
      </div>
    </div>

    ${data.ref ? '<div class="meta-row"><span class="meta-label">ref:</span> <span class="tag tag-ref">' + h(data.ref) + '</span></div>' : ''}

    <div class="meta-row"><span class="meta-label">Parents:</span> <div class="link-list">${parentsHtml}</div></div>
    <div class="meta-row"><span class="meta-label">Children:</span> <div class="link-list">${childrenHtml}</div></div>
    <div class="meta-row"><span class="meta-label">Siblings:</span> <div class="link-list">${siblingsHtml}</div></div>

    <div class="actions" id="pa-${pid}">
      <button class="btn btn-edit" onclick="panelStartEdit(${pid})">Edit</button>
      <button class="btn btn-success" id="prb-${pid}" onclick="panelReview(${pid})" ${data.reviewed ? 'disabled' : ''}>Review</button>
      <button class="btn btn-warning" id="pcb-${pid}" onclick="panelClear(${pid})" ${data.suspect ? '' : 'disabled'}>Clear Suspect</button>
    </div>
  `;

  document.getElementById('pn-' + pid).innerHTML = `
    <button ${data.prev_uid ? `onclick="handlePanelNav(event,${pid},'${data.prev_uid}')"` : 'disabled'}>&larr; Prev${data.prev_uid ? ' (' + h(data.prev_uid) + ')' : ''}</button>
    <button ${data.next_uid ? `onclick="handlePanelNav(event,${pid},'${data.next_uid}')"` : 'disabled'}>Next${data.next_uid ? ' (' + h(data.next_uid) + ')' : ''} &rarr;</button>
  `;
}

// ===================================================================
// Textarea enhancement (offline fallback)
// ===================================================================
function enhanceTextarea(ta) {
  if (ta._enhanced) return;
  ta._enhanced = true;
  ta.addEventListener('keydown', function(e) {
    if (e.key !== 'Tab') return;
    e.preventDefault();
    const s = this.selectionStart, end = this.selectionEnd, v = this.value;
    const ls = v.lastIndexOf('\n', s - 1) + 1;
    if (e.shiftKey) {
      const block = v.substring(ls, end);
      const dedented = block.replace(/^ {1,2}/gm, '');
      const firstRemoved = (block.match(/^ {1,2}/) || [''])[0].length;
      this.value = v.substring(0, ls) + dedented + v.substring(end);
      this.selectionStart = Math.max(ls, s - firstRemoved);
      this.selectionEnd = end - (block.length - dedented.length);
    } else if (s === end) {
      this.value = v.substring(0, s) + '  ' + v.substring(end);
      this.selectionStart = this.selectionEnd = s + 2;
    } else {
      const block = v.substring(ls, end);
      const indented = block.replace(/^/gm, '  ');
      this.value = v.substring(0, ls) + indented + v.substring(end);
      this.selectionStart = s + 2;
      this.selectionEnd = end + (indented.length - block.length);
    }
  });
}

// ===================================================================
// TipTap rich editor helpers
// ===================================================================
function createTiptapEditor(panelId, htmlContent) {
  const TabHandler = RichEditor.Extension.create({
    name: 'tabHandler',
    addKeyboardShortcuts() {
      return { 'Tab': () => true, 'Shift-Tab': () => true };
    },
  });
  const editor = new RichEditor.Editor({
    element: document.getElementById('ptip-' + panelId),
    extensions: [RichEditor.StarterKit, TabHandler],
    content: htmlContent,
  });
  buildTiptapToolbar(panelId, editor);
  return editor;
}

function buildTiptapToolbar(panelId, editor) {
  const bar = document.getElementById('ptbar-' + panelId);
  const btns = [
    { label: 'B', cmd: () => editor.chain().focus().toggleBold().run(), active: () => editor.isActive('bold'), title: 'Bold (Ctrl+B)' },
    { label: 'I', cmd: () => editor.chain().focus().toggleItalic().run(), active: () => editor.isActive('italic'), title: 'Italic (Ctrl+I)' },
    { label: 'S', cmd: () => editor.chain().focus().toggleStrike().run(), active: () => editor.isActive('strike'), title: 'Strikethrough' },
    { label: '<>', cmd: () => editor.chain().focus().toggleCode().run(), active: () => editor.isActive('code'), title: 'Inline code' },
    'sep',
    { label: 'H1', cmd: () => editor.chain().focus().toggleHeading({level:1}).run(), active: () => editor.isActive('heading',{level:1}) },
    { label: 'H2', cmd: () => editor.chain().focus().toggleHeading({level:2}).run(), active: () => editor.isActive('heading',{level:2}) },
    { label: 'H3', cmd: () => editor.chain().focus().toggleHeading({level:3}).run(), active: () => editor.isActive('heading',{level:3}) },
    'sep',
    { label: '\u2022', cmd: () => editor.chain().focus().toggleBulletList().run(), active: () => editor.isActive('bulletList'), title: 'Bullet list' },
    { label: '1.', cmd: () => editor.chain().focus().toggleOrderedList().run(), active: () => editor.isActive('orderedList'), title: 'Numbered list' },
    'sep',
    { label: '```', cmd: () => editor.chain().focus().toggleCodeBlock().run(), active: () => editor.isActive('codeBlock'), title: 'Code block' },
    { label: '\u275d', cmd: () => editor.chain().focus().toggleBlockquote().run(), active: () => editor.isActive('blockquote'), title: 'Quote' },
    { label: '\u2014', cmd: () => editor.chain().focus().setHorizontalRule().run(), active: () => false, title: 'Horizontal rule' },
  ];
  for (const b of btns) {
    if (b === 'sep') {
      const sep = document.createElement('span');
      sep.className = 'tb-sep';
      bar.appendChild(sep);
      continue;
    }
    const btn = document.createElement('button');
    btn.textContent = b.label;
    btn.title = b.title || b.label;
    btn.type = 'button';
    btn.addEventListener('click', (ev) => { ev.preventDefault(); b.cmd(); });
    bar.appendChild(btn);
  }
  const updateState = () => {
    let i = 0;
    for (const b of btns) {
      if (b === 'sep') { i++; continue; }
      bar.children[i++].classList.toggle('is-active', b.active());
    }
  };
  editor.on('selectionUpdate', updateState);
  editor.on('transaction', updateState);
}

function tiptapToMarkdown(editor) {
  const html = editor.getHTML();
  const td = new RichEditor.TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
    bulletListMarker: '-',
    emDelimiter: '*',
    strongDelimiter: '**',
  });
  td.addRule('strikethrough', {
    filter: ['del', 's'],
    replacement: (content) => '~~' + content + '~~',
  });
  return td.turndown(html);
}

// ===================================================================
// Panel edit actions
// ===================================================================
function panelStartEdit(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) return;
  ps.editMode = true;
  document.getElementById('ptv-' + panelId).classList.add('hidden');
  document.getElementById('pte-' + panelId).classList.remove('hidden');
  document.getElementById('pa-' + panelId).classList.add('hidden');

  if (richEditorReady) {
    const ta = document.getElementById('pta-' + panelId);
    ta.classList.add('hidden');
    const richWrap = document.getElementById('prich-' + panelId);
    richWrap.classList.remove('hidden');
    richWrap.innerHTML = '<div class="tiptap-toolbar" id="ptbar-' + panelId + '"></div><div id="ptip-' + panelId + '"></div>';
    const htmlContent = document.getElementById('ptv-' + panelId).innerHTML;
    ps.editor = createTiptapEditor(panelId, htmlContent);
    ps.useRich = true;
    ps.editor.commands.focus('end');
  } else {
    const ta = document.getElementById('pta-' + panelId);
    ta.classList.remove('hidden');
    enhanceTextarea(ta);
    ta.focus();
    ta.style.height = 'auto';
    ta.style.height = Math.max(150, ta.scrollHeight + 4) + 'px';
    ps.useRich = false;
  }
}

function panelCancelEdit(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (ps) {
    ps.editMode = false;
    if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
  }
  document.getElementById('ptv-' + panelId).classList.remove('hidden');
  document.getElementById('pte-' + panelId).classList.add('hidden');
  document.getElementById('pa-' + panelId).classList.remove('hidden');
}

async function panelSave(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) return;
  let text;
  if (ps.useRich && ps.editor) {
    text = tiptapToMarkdown(ps.editor);
  } else {
    text = document.getElementById('pta-' + panelId).value;
  }
  const btn = document.getElementById('psb-' + panelId);
  btn.disabled = true; btn.textContent = 'Saving...';
  try {
    const res = await API.post('/api/items/' + ps.uid + '/edit', { text });
    if (res.ok) {
      if (ps.editor) { ps.editor.destroy(); ps.editor = null; }
      ps.editMode = false;
      ps.useRich = false;
      toast(ps.uid + ' updated');
      refreshCurrentView();
      renderPanelContent(ps, res.item);
      refreshOtherPanels(panelId);
    } else {
      toast('Error: ' + res.error, 'error');
      btn.disabled = false; btn.textContent = 'Save';
    }
  } catch (e) {
    toast('Error: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = 'Save';
  }
}

async function panelReview(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) return;
  const btn = document.getElementById('prb-' + panelId);
  btn.disabled = true; btn.textContent = 'Processing...';
  try {
    const res = await API.post('/api/items/' + ps.uid + '/review');
    if (res.ok) {
      toast(ps.uid + ' reviewed');
      refreshCurrentView();
      renderPanelContent(ps, res.item);
      refreshOtherPanels(panelId);
    } else {
      toast('Error: ' + res.error, 'error');
      btn.disabled = false; btn.textContent = 'Review';
    }
  } catch (e) {
    toast('Error: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = 'Review';
  }
}

async function panelClear(panelId) {
  const ps = activePanels.find(p => p.id === panelId);
  if (!ps) return;
  const btn = document.getElementById('pcb-' + panelId);
  btn.disabled = true; btn.textContent = 'Processing...';
  try {
    const res = await API.post('/api/items/' + ps.uid + '/clear');
    if (res.ok) {
      toast(ps.uid + ' suspect cleared');
      refreshCurrentView();
      renderPanelContent(ps, res.item);
      refreshOtherPanels(panelId);
    } else {
      toast('Error: ' + res.error, 'error');
      btn.disabled = false; btn.textContent = 'Clear Suspect';
    }
  } catch (e) {
    toast('Error: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = 'Clear Suspect';
  }
}

async function refreshOtherPanels(excludeId) {
  for (const ps of activePanels) {
    if (ps.id === excludeId) continue;
    try {
      const data = await API.get('/api/items/' + ps.uid);
      renderPanelContent(ps, data);
    } catch { /* panel data may have been deleted */ }
  }
}

// ===================================================================
// Refresh current view after mutation
// ===================================================================
async function refreshCurrentView() {
  // Re-fetch sidebar group counts
  loadGroupNav();

  // Re-render current view
  switch (currentView) {
    case 'dashboard': renderDashboard(); break;
    case 'matrix':
      matrixData = await API.get('/api/matrix');
      renderMatrixView();
      break;
    case 'group': renderGroup(currentParam); break;
    case 'validation': renderValidation(); break;
  }
}

// ===================================================================
// Init
// ===================================================================
(async function init() {
  await loadGroupNav();
  route();
})();
</script>
</body>
</html>"""


# ===================================================================
# Entry point
# ===================================================================

def serve(tree, project_dir, port=8080, strict=False):
    """REST API + SPA サーバーを起動する。"""
    store = DoorstopDataStore(tree, project_dir, strict=strict)
    ReportAPIHandler.store = store

    server = HTTPServer(("127.0.0.1", port), ReportAPIHandler)
    print(f"\nDoorstop Dashboard: http://127.0.0.1:{port}/")
    print("  REST API + SPA mode")
    print("  All data is managed centrally in the backend.")
    print("  Edit/Review/Clear changes are reflected across all views.")
    print("  External YML edits are auto-detected on page reload.")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Doorstop Traceability REST API + SPA Server"
    )
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    parser.add_argument("--strict", action="store_true", help="Strict validation mode")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    print("Building document tree...")
    tree = doorstop.build()

    serve(tree, project_dir, port=args.port, strict=args.strict)


if __name__ == "__main__":
    main()
