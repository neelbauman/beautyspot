"""ドキュメントツリーのバリデーションとカバレッジ計算。

validate_and_report.py から分離した純粋なロジック層。
doorstop ツリーの構造検証・マトリクス構築・カバレッジ計算を担う。
"""

import os
from collections import defaultdict

from _common import get_groups, get_references, is_derived, is_normative


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_tree(tree, strict=False, project_dir="."):
    """ドキュメントツリーを検証する。"""
    issues = {"errors": [], "warnings": [], "info": []}

    # 基本チェック
    for document in tree:
        for item in document:
            if not item.active:
                continue
            if not is_normative(item):
                continue
            if not item.text.strip():
                issues["warnings"].append(f"{item.uid}: テキストが空です")

    # 親子リンクの検証
    docs = {doc.prefix: doc for doc in tree}
    for document in tree:
        if not document.parent:
            continue
        parent_doc = docs.get(document.parent)
        if parent_doc is None:
            issues["errors"].append(
                f"{document.prefix}: 親ドキュメント '{document.parent}' が見つかりません"
            )
            continue

        parent_uids = {str(item.uid) for item in parent_doc if item.active and is_normative(item)}
        for item in document:
            if not item.active or not is_normative(item):
                continue
            linked_parents = [
                str(link) for link in item.links
                if str(link).startswith(document.parent)
            ]
            if not linked_parents:
                issues["warnings"].append(
                    f"{item.uid} [{get_groups(item)}]: "
                    f"親ドキュメント {document.parent} へのリンクがありません"
                )
            for link in linked_parents:
                link_uid = link.split(":")[0] if ":" in link else link
                if link_uid not in parent_uids:
                    issues["errors"].append(
                        f"{item.uid}: リンク先 {link_uid} が存在しません"
                    )

        # クロスグループリンク警告
        parent_groups = {str(i.uid): get_groups(i) for i in parent_doc if i.active and is_normative(i)}
        for item in document:
            if not item.active or not is_normative(item):
                continue
            child_groups = get_groups(item)
            if not child_groups or child_groups == ["(未分類)"]:
                continue
            for link in item.links:
                link_str = str(link)
                if link_str in parent_groups:
                    pgs = parent_groups[link_str]
                    if pgs and pgs != ["(未分類)"] and not set(child_groups).intersection(set(pgs)):
                        issues["warnings"].append(
                            f"{item.uid} [{', '.join(child_groups)}] → {link_str} [{', '.join(pgs)}]: "
                            f"クロスグループリンクです"
                        )

        # 逆方向チェック（strictモード）
        if strict:
            child_links = defaultdict(set)
            for item in document:
                if not item.active or not is_normative(item):
                    continue
                for link in item.links:
                    link_str = str(link)
                    if link_str.startswith(document.parent):
                        child_links[link_str].add(str(item.uid))
            for parent_item in parent_doc:
                if not parent_item.active or not is_normative(parent_item):
                    continue
                if str(parent_item.uid) not in child_links:
                    issues["warnings"].append(
                        f"{parent_item.uid} [{get_groups(parent_item)}]: "
                        f"子ドキュメント {document.prefix} からのリンクがありません"
                    )

    # references存在チェック（IMPL, TST）
    ref_docs = {"IMPL", "TST"}
    for document in tree:
        if document.prefix not in ref_docs:
            continue
        for item in document:
            if not item.active or not is_normative(item):
                continue
            refs = get_references(item)
            for ref_entry in refs:
                filepath = ref_entry.get("path", "")
                if not filepath:
                    continue
                filepath_clean = filepath.split("::")[0]
                full_path = os.path.join(project_dir, filepath_clean)
                if not os.path.exists(full_path):
                    issues["warnings"].append(
                        f"{item.uid}: references '{filepath}' のファイルが存在しません"
                    )

    # derived チェック
    design_prefixes = {"ARCH", "SPEC", "HLD", "LLD"}
    for document in tree:
        for item in document:
            if not item.active or not is_derived(item):
                continue
            if document.prefix in ("IMPL", "TST"):
                issues["errors"].append(
                    f"{item.uid}: IMPL/TST で derived: true は使用できません"
                )
            elif document.prefix == "REQ":
                issues["warnings"].append(
                    f"{item.uid}: REQ で derived: true が設定されています。"
                    f"REQは通常 derived にしません"
                )
            elif document.prefix in design_prefixes:
                text = item.text.strip().lower()
                if "派生要求の根拠" not in text and "派生" not in text and "derived" not in text:
                    issues["warnings"].append(
                        f"{item.uid}: derived: true ですが、text に派生要求の根拠が"
                        f"記載されていません"
                    )

    # レビュー状態チェック
    unreviewed = []
    for document in tree:
        for item in document:
            if item.active and is_normative(item) and not item.reviewed:
                unreviewed.append(str(item.uid))
    if unreviewed:
        issues["info"].append(
            f"未レビューアイテム: {len(unreviewed)}件 "
            f"({', '.join(unreviewed[:10])}{'...' if len(unreviewed) > 10 else ''})"
        )

    return issues


# ---------------------------------------------------------------------------
# Matrix & Coverage
# ---------------------------------------------------------------------------

def build_traceability_matrix(tree):
    """トレーサビリティマトリクスを構築する。"""
    docs = list(tree)
    prefixes = [d.prefix for d in docs]
    matrix = []

    root_docs = [d for d in docs if not d.parent]
    for root_doc in root_docs:
        for item in root_doc:
            if not item.active or not is_normative(item):
                continue
            row = {root_doc.prefix: item, "_groups": get_groups(item)}
            matrix.append(row)

    def expand_children(doc, parent_prefix):
        child_docs = [d for d in docs if d.parent == doc.prefix]
        for child_doc in child_docs:
            link_map = defaultdict(list)
            for child_item in child_doc:
                if not child_item.active or not is_normative(child_item):
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

    return matrix, prefixes


def compute_coverage(tree):
    """ドキュメントペア別・グループ別のカバレッジを計算する。"""
    docs = {doc.prefix: doc for doc in tree}
    coverage = {}

    for doc in tree:
        if not doc.parent or doc.parent not in docs:
            continue
        parent_doc = docs[doc.parent]
        parent_uids = {str(item.uid) for item in parent_doc if item.active and is_normative(item)}
        covered_uids = set()

        for item in doc:
            if not item.active or not is_normative(item):
                continue
            for link in item.links:
                link_str = str(link)
                if link_str in parent_uids:
                    covered_uids.add(link_str)

        total = len(parent_uids)
        covered = len(covered_uids)
        pct = (covered / total * 100) if total > 0 else 0.0

        # グループ別
        group_cov = defaultdict(lambda: {"total": set(), "covered": set()})
        for pi in parent_doc:
            if pi.active and is_normative(pi):
                for g in get_groups(pi):
                    group_cov[g]["total"].add(str(pi.uid))
        for item in doc:
            if not item.active or not is_normative(item):
                continue
            for link in item.links:
                link_str = str(link)
                if link_str in parent_uids:
                    po = parent_doc.find_item(link_str)
                    for g in get_groups(po):
                        group_cov[g]["covered"].add(link_str)

        groups = {}
        for g, d in sorted(group_cov.items()):
            gt, gc = len(d["total"]), len(d["covered"])
            groups[g] = {
                "total": gt, "covered": gc, "uncovered": gt - gc,
                "percentage": round(gc / gt * 100, 1) if gt > 0 else 0.0,
                "uncovered_items": sorted(d["total"] - d["covered"]),
            }

        coverage[f"{doc.prefix} → {doc.parent}"] = {
            "total": total, "covered": covered, "uncovered": total - covered,
            "percentage": round(pct, 1),
            "uncovered_items": sorted(parent_uids - covered_uids),
            "by_group": groups,
        }

    return coverage
