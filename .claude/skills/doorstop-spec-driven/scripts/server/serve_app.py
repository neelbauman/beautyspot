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
import subprocess
import sys
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

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
    # Git metadata collection
    # ---------------------------------------------------------------

    def _collect_git_metadata(self):
        """全ドキュメントのYMLファイルについてgit logから作成日・更新日・作成者を取得する。

        Returns:
            dict: {relative_path: {"created_at": str, "updated_at": str, "author": str}}
        """
        meta = {}
        # Collect all document directories
        doc_dirs = []
        for doc in self.tree:
            if os.path.isdir(doc.path):
                doc_dirs.append(doc.path)
        if not doc_dirs:
            return meta

        # Build list of YML file paths relative to project_dir
        yml_files = []
        abs_to_rel = {}
        for doc_dir in doc_dirs:
            for fname in os.listdir(doc_dir):
                if fname.endswith(".yml") and not fname.startswith("."):
                    abs_path = os.path.join(doc_dir, fname)
                    rel_path = os.path.relpath(abs_path, self.project_dir)
                    yml_files.append(rel_path)
                    abs_to_rel[abs_path] = rel_path

        if not yml_files:
            return meta

        try:
            # Single git log command: get all commits touching spec YML files
            # Format: COMMIT|ISO-date|author-name|hash followed by name-status lines
            result = subprocess.run(
                ["git", "log", "--format=COMMIT|%aI|%aN|%H", "--name-status", "--"]
                + yml_files,
                capture_output=True, text=True, timeout=30,
                cwd=self.project_dir,
            )
            if result.returncode != 0:
                return meta

            # Parse output: track first (oldest) and last (newest) commit per file
            current_date = None
            current_author = None
            current_hash = None
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("COMMIT|"):
                    parts = line.split("|", 3)
                    current_date = parts[1] if len(parts) > 1 else None
                    current_author = parts[2] if len(parts) > 2 else None
                    current_hash = parts[3] if len(parts) > 3 else None
                    continue
                if current_date is None:
                    continue
                # Name-status line: e.g. "A\tspecification/reqs/REQ001.yml"
                # or "M\tspecification/reqs/REQ001.yml"
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                _, fpath = parts
                fpath = fpath.strip()
                if fpath not in meta:
                    # First encounter = most recent commit (git log is newest-first)
                    meta[fpath] = {
                        "created_at": current_date,
                        "updated_at": current_date,
                        "author": current_author,
                        "created_commit": current_hash,
                        "updated_commit": current_hash,
                    }
                else:
                    # Older commits: update created_at/author/commit (will keep being
                    # overwritten until we reach the oldest commit = file creation)
                    meta[fpath] = {
                        **meta[fpath],
                        "created_at": current_date,
                        "author": current_author,
                        "created_commit": current_hash,
                    }
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        # Convert ISO dates to short format (YYYY-MM-DD)
        for fpath, m in meta.items():
            for key in ("created_at", "updated_at"):
                if m.get(key) and "T" in m[key]:
                    m[key] = m[key].split("T")[0]

        self._git_meta = meta
        return meta

    def _get_git_meta_for_item(self, item):
        """アイテムのYMLファイルに対応するgitメタデータを返す。"""
        if not hasattr(self, "_git_meta"):
            return {}
        # Build the relative path for this item's YML file
        try:
            yml_path = item.path
            rel_path = os.path.relpath(yml_path, self.project_dir)
            return self._git_meta.get(rel_path, {})
        except (AttributeError, ValueError):
            return {}

    # ---------------------------------------------------------------
    # Internal index management
    # ---------------------------------------------------------------

    def _rebuild_indexes(self):
        self._children_idx = defaultdict(list)
        self._parents_idx = defaultdict(list)
        for doc in self.tree:
            for item in doc:
                if not item.active:
                    continue
                for link in item.links:
                    parent = self._find_item(str(link))
                    if parent and parent.active:
                        self._children_idx[str(link)].append(item)
                        self._parents_idx[str(item.uid)].append(parent)

        self._suspect_uids = set()
        for doc in self.tree:
            for item in doc:
                if not item.active:
                    continue
                for link in item.links:
                    parent = self._find_item(str(link))
                    if parent is None or not parent.active:
                        continue
                    if (
                        link.stamp is not None
                        and link.stamp != ""
                        and link.stamp != parent.stamp()
                    ):
                        self._suspect_uids.add(str(item.uid))
                        break

        self._collect_git_metadata()

    def _find_item(self, uid_str):
        for doc in self.tree:
            try:
                return doc.find_item(uid_str)
            except Exception:
                continue
        return None

    def _is_normative(self, item):
        try:
            val = item.get("normative")
            if val is None:
                return True
            return str(val).lower() != "false"
        except (AttributeError, KeyError):
            return True

    def _get_groups(self, item):
        try:
            g = item.get("groups")
            if isinstance(g, list):
                return g if g else ["(未分類)"]
            elif isinstance(g, str) and g:
                return [s.strip() for s in g.split(",") if s.strip()]
            g = item.get("group")
            if g:
                if isinstance(g, str):
                    return [s.strip() for s in g.split(",") if s.strip()]
                return [g]
            return ["(未分類)"]
        except (AttributeError, KeyError):
            return ["(未分類)"]

    def _get_ref(self, item):
        try:
            return item.ref or ""
        except (AttributeError, KeyError):
            return ""

    def _get_header(self, item):
        try:
            h = item.get("header")
            return h.strip() if h else ""
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
        # references attribute (list of dicts)
        references = []
        try:
            refs = item.get("references")
            if refs and isinstance(refs, list):
                references = refs
        except (AttributeError, KeyError):
            pass
        # derived flag
        derived = False
        try:
            derived = bool(item.get("derived"))
        except (AttributeError, KeyError):
            pass
        git = self._get_git_meta_for_item(item)
        return {
            "uid": uid_str,
            "prefix": prefix,
            "level": str(item.level),
            "header": self._get_header(item),
            "groups": self._get_groups(item),
            "text": item.text,
            "text_html": render_markdown(item.text),
            "text_preview": item.text[:100] + ("..." if len(item.text) > 100 else ""),
            "ref": self._get_ref(item),
            "references": references,
            "derived": derived,
            "normative": self._is_normative(item),
            "reviewed": bool(item.reviewed),
            "suspect": uid_str in self._suspect_uids,
            "active": bool(item.active),
            "created_at": git.get("created_at", ""),
            "updated_at": git.get("updated_at", ""),
            "author": git.get("author", ""),
            "created_commit": git.get("created_commit", ""),
            "updated_commit": git.get("updated_commit", ""),
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
        git = self._get_git_meta_for_item(item)
        return {
            "uid": uid_str,
            "prefix": prefix,
            "level": str(item.level),
            "header": self._get_header(item),
            "groups": self._get_groups(item),
            "text_preview": item.text[:80] + ("..." if len(item.text) > 80 else ""),
            "ref": self._get_ref(item),
            "normative": self._is_normative(item),
            "reviewed": bool(item.reviewed),
            "suspect": uid_str in self._suspect_uids,
            "created_at": git.get("created_at", ""),
            "updated_at": git.get("updated_at", ""),
            "author": git.get("author", ""),
        }

    # ---------------------------------------------------------------
    # Read operations
    # ---------------------------------------------------------------

    def get_overview(self):
        docs = {}
        total = 0
        reviewed = 0
        for doc in self.tree:
            count = sum(1 for item in doc if item.active and self._is_normative(item))
            docs[str(doc.prefix)] = count
            total += count
            reviewed += sum(1 for item in doc if item.active and item.reviewed and self._is_normative(item))

        groups = sorted({g for doc in self.tree for item in doc if item.active for g in self._get_groups(item) if g != "(未分類)"})
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
                if not item.active:
                    continue
                if not self._is_normative(item):
                    continue
                if not item.text.strip():
                    issues["warnings"].append(f"{item.uid}: テキストが空です")

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

            parent_uids = {str(item.uid) for item in parent_doc if item.active and self._is_normative(item)}
            for item in document:
                if not item.active or not self._is_normative(item):
                    continue
                linked_parents = [
                    str(link) for link in item.links
                    if str(link).startswith(document.parent)
                ]
                if not linked_parents:
                    issues["warnings"].append(
                        f"{item.uid} [{self._get_groups(item)}]: "
                        f"親ドキュメント {document.parent} へのリンクがありません"
                    )
                for link in linked_parents:
                    link_uid = link.split(":")[0] if ":" in link else link
                    if link_uid not in parent_uids:
                        issues["errors"].append(
                            f"{item.uid}: リンク先 {link_uid} が存在しません"
                        )

            parent_groups = {str(i.uid): self._get_groups(i) for i in parent_doc if i.active and self._is_normative(i)}
            for item in document:
                if not item.active or not self._is_normative(item):
                    continue
                child_groups = self._get_groups(item)
                if not child_groups or child_groups == ["(未分類)"]:
                    continue
                for link in item.links:
                    link_str = str(link)
                    if link_str in parent_groups:
                        pgs = parent_groups[link_str]
                        if pgs and pgs != ["(未分類)"] and not set(child_groups).intersection(set(pgs)):
                            issues["warnings"].append(
                                f"{item.uid} [{', '.join(child_groups)}] -> {link_str} [{', '.join(pgs)}]: "
                                f"クロスグループリンクです"
                            )

            if self.strict:
                child_links = defaultdict(set)
                for item in document:
                    if not item.active or not self._is_normative(item):
                        continue
                    for link in item.links:
                        link_str = str(link)
                        if link_str.startswith(document.parent):
                            child_links[link_str].add(str(item.uid))
                for parent_item in parent_doc:
                    if not parent_item.active or not self._is_normative(parent_item):
                        continue
                    if str(parent_item.uid) not in child_links:
                        issues["warnings"].append(
                            f"{parent_item.uid} [{self._get_groups(parent_item)}]: "
                            f"子ドキュメント {document.prefix} からのリンクがありません"
                        )

        ref_docs = {"IMPL", "TST"}
        for document in self.tree:
            if document.prefix not in ref_docs:
                continue
            for item in document:
                if not item.active or not self._is_normative(item):
                    continue
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
                if item.active and self._is_normative(item) and not item.reviewed:
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
            parent_uids = {str(item.uid) for item in parent_doc if item.active and self._is_normative(item)}
            covered_uids = set()

            for item in doc:
                if not item.active or not self._is_normative(item):
                    continue
                for link in item.links:
                    link_str = str(link)
                    if link_str in parent_uids:
                        covered_uids.add(link_str)

            total = len(parent_uids)
            covered = len(covered_uids)
            pct = (covered / total * 100) if total > 0 else 0.0

            group_cov = defaultdict(lambda: {"total": set(), "covered": set()})
            for pi in parent_doc:
                if pi.active and self._is_normative(pi):
                    for g in self._get_groups(pi):
                        group_cov[g]["total"].add(str(pi.uid))
            for item in doc:
                if not item.active or not self._is_normative(item):
                    continue
                for link in item.links:
                    link_str = str(link)
                    if link_str in parent_uids:
                        po = parent_doc.find_item(link_str)
                        for g in self._get_groups(po):
                            group_cov[g]["covered"].add(link_str)

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
                if not item.active or not self._is_normative(item):
                    continue
                row = {root_doc.prefix: item, "_groups": self._get_groups(item)}
                matrix.append(row)

        def expand_children(doc, parent_prefix):
            child_docs = [d for d in docs if d.parent == doc.prefix]
            for child_doc in child_docs:
                link_map = defaultdict(list)
                for child_item in child_doc:
                    if not child_item.active or not self._is_normative(child_item):
                        continue
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
            gs = row.get("_groups", ["(未分類)"])
            if group and group not in gs:
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
                    references = []
                    try:
                        refs = item.get("references")
                        if refs and isinstance(refs, list):
                            references = refs
                    except (AttributeError, KeyError):
                        pass
                    git = self._get_git_meta_for_item(item)
                    cells[prefix] = {
                        "uid": uid_str,
                        "header": self._get_header(item),
                        "text_preview": item.text[:80] + ("..." if len(item.text) > 80 else ""),
                        "ref": self._get_ref(item),
                        "references": references,
                        "reviewed": is_reviewed,
                        "suspect": is_suspect,
                        "created_at": git.get("created_at", ""),
                        "updated_at": git.get("updated_at", ""),
                        "author": git.get("author", ""),
                    }
                else:
                    cells[prefix] = None
            result_rows.append({
                "groups": gs,
                "cells": cells,
                "uids": uids,
                "statuses": sorted(statuses),
            })

        return {"prefixes": prefixes, "rows": result_rows}

    def get_groups(self):
        groups = defaultdict(lambda: {"items": 0, "reviewed": 0, "suspect": 0})
        for doc in self.tree:
            for item in doc:
                if not item.active:
                    continue
                for g in self._get_groups(item):
                    groups[g]["items"] += 1
                    if self._is_normative(item):
                        if item.reviewed:
                            groups[g]["reviewed"] += 1
                        if str(item.uid) in self._suspect_uids:
                            groups[g]["suspect"] += 1
        return {g: dict(d) for g, d in sorted(groups.items())}

    def get_group_detail(self, group_name):
        group_uids = set()
        for doc in self.tree:
            for item in doc:
                if not item.active:
                    continue
                if group_name in self._get_groups(item):
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
        if item is None or not item.active:
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
                if not item.active:
                    continue
                if group and group not in self._get_groups(item):
                    continue
                items.append(self._item_summary(item, doc.prefix))
        return items

    def get_document_detail(self, prefix):
        for doc in self.tree:
            if doc.prefix == prefix:
                items = []
                for item in doc:
                    if not item.active:
                        continue
                    items.append(self._item_to_dict(item, doc.prefix))
                # Sort by level (natural sort)
                import re
                def natural_sort_key(s):
                    return [int(text) if text.isdigit() else text.lower()
                            for text in re.split('([0-9]+)', s["level"])]
                items.sort(key=natural_sort_key)
                return {
                    "prefix": prefix,
                    "items": items
                }
        return None

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

            parent_uids = {str(i.uid) for i in parent_doc if i.active and str(i.uid) in related_uids and self._is_normative(i)}
            if not parent_uids:
                continue

            covered = set()
            for item in doc:
                if not item.active or str(item.uid) not in related_uids or not self._is_normative(item):
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
            name = unquote(path[len("/api/group/"):])
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
        elif path == "/api/documents":
            docs = [doc.prefix for doc in self.store.tree]
            self._json_ok(docs)
        elif path.startswith("/api/document/"):
            prefix = path[len("/api/document/"):]
            data = self.store.get_document_detail(prefix)
            if data:
                self._json_ok(data)
            else:
                self._json_err(404, f"Document '{prefix}' not found")
        elif path == "/api/validation":
            self._json_ok(self.store.get_validation())
        elif path == "/api/coverage":
            self._json_ok(self.store.get_coverage())
        elif path in ("", "/", "/index.html"):
            self._serve_html(_load_spa_html())
        elif path == "/api/download_report":
            report_path = os.path.join(self.store.project_dir, "specification", "reports", "publish", "specification.html")
            if os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    content = f.read()
                body = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="specification.html"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404, "Report not found. Please generate it first.")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.rstrip("/") == "/api/reload":
            self.store.force_reload()
            self._json_ok({"ok": True, "message": "Tree reloaded"})
            return

        if self.path.rstrip("/") == "/api/generate_report":
            self.store.force_reload()
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "publish_docs.py")
            cmd = [
                sys.executable,
                script_path,
                self.store.project_dir,
                "--single-file"
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                self._json_ok({"ok": True, "message": "Report generated successfully.", "report_url": "/api/download_report"})
            except subprocess.CalledProcessError as e:
                self._json_err(500, f"Failed to generate report: {e.stderr}")
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

    def log_message(self, format, *args):
        print(f"  [{self.log_date_time_string()}] {format % args}")


# ===================================================================
# SPA HTML — assembled from external assets
# ===================================================================

_SERVE_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _load_spa_html():
    """assets/spa.css と assets/spa.js を読み込み、インラインHTMLとして組み立てる。"""
    css_path = os.path.join(_SERVE_ASSETS_DIR, "spa.css")
    js_path = os.path.join(_SERVE_ASSETS_DIR, "spa.js")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    return _SPA_HTML_TEMPLATE.replace("/* __SPA_CSS__ */", css).replace("/* __SPA_JS__ */", js)


_SPA_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Doorstop Traceability Dashboard</title>
<style>
/* __SPA_CSS__ */
</style>
</head>
<body>

<nav id="sidebar">
  <h2>Doorstop Dashboard</h2>
  <div id="nav-status-summary"></div>
  <ul>
    <li><a href="#/" data-nav="dashboard">Dashboard</a></li>
    <li><a href="#/matrix" data-nav="matrix">Matrix</a></li>
    <li><span class="nav-section-title">Documents</span></li>
  </ul>
  <ul id="doc-nav-list"></ul>
  <ul>
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
/* __SPA_JS__ */
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
