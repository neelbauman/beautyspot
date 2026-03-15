"""チェーン・コンテキスト・関連ファイル照会コマンド。

含まれるコマンド:
  chain         指定UIDまたはファイルパスの上流→下流チェーン全体を表示
  context       指定UIDの全文脈情報を一括取得
  related-files 関連ファイルパスをドキュメント層別に取得
"""
from collections import defaultdict

from _common import (
    out, get_groups, get_references, is_derived, is_suspect,
    find_item, find_doc_prefix, item_summary, build_link_index, truncate_text,
)


def _find_items_by_file(tree, file_path):
    """ファイルパスをreferences属性から逆引きし、参照しているアイテムを返す。

    マッチ戦略（優先順）:
      1. 正規化後の完全一致
      2. file_path が参照パスのサフィックスに一致（例: "core.py" → "src/beautyspot/core.py"）
      3. 参照パスが file_path のサフィックスに一致（相対パスの表記ゆれ対応）
    """
    normalized = file_path.replace("\\", "/").rstrip("/")
    results = []
    for doc in tree:
        for item in doc:
            for ref in get_references(item):
                ref_path = ref.get("path", "").replace("\\", "/").rstrip("/")
                if not ref_path:
                    continue
                if (
                    ref_path == normalized
                    or ref_path.endswith("/" + normalized)
                    or normalized.endswith("/" + ref_path)
                ):
                    results.append((item, doc.prefix))
                    break  # 同一アイテムを重複追加しない
    return results


def _trace_up(uid, parents_idx, result, visited, depth=0, rich=False):
    """上流を辿る。rich=True の場合は references も含め text を 200 文字まで取得する。"""
    if uid in visited or depth > 10:
        return
    visited.add(uid)
    for parent_item, parent_prefix in parents_idx.get(uid, []):
        parent_uid = str(parent_item.uid)
        entry = {
            "uid": parent_uid,
            "prefix": parent_prefix,
            "groups": get_groups(parent_item),
            "text": truncate_text(parent_item.text.strip(), 200 if rich else 120),
            "derived": is_derived(parent_item),
            "depth": depth,
        }
        if rich:
            entry["references"] = get_references(parent_item)
        result.append(entry)
        _trace_up(parent_uid, parents_idx, result, visited, depth + 1, rich=rich)


def _trace_down(uid, children_idx, result, visited, depth=0):
    if uid in visited or depth > 10:
        return
    visited.add(uid)
    for child_item, child_prefix in children_idx.get(uid, []):
        child_uid = str(child_item.uid)
        result.append({
            "uid": child_uid,
            "prefix": child_prefix,
            "groups": get_groups(child_item),
            "text": truncate_text(child_item.text.strip(), 120),
            "references": get_references(child_item),
            "derived": is_derived(child_item),
            "depth": depth,
        })
        _trace_down(child_uid, children_idx, result, visited, depth + 1)


def _build_single_chain(tree, root_item, children_idx, parents_idx):
    """単一アイテムのチェーン情報を構築して返す。"""
    uid = str(root_item.uid)
    prefix = find_doc_prefix(tree, root_item)

    upstream = []
    _trace_up(uid, parents_idx, upstream, visited=set())

    downstream = []
    _trace_down(uid, children_idx, downstream, visited=set())

    chain_uids = {uid}
    for entry in upstream:
        chain_uids.add(entry["uid"])
    for entry in downstream:
        chain_uids.add(entry["uid"])

    layers = defaultdict(list)
    for doc in tree:
        for item in doc:
            uid_str = str(item.uid)
            if uid_str in chain_uids:
                layers[doc.prefix].append(item_summary(item, doc.prefix, tree))

    return {
        "root": item_summary(root_item, prefix, tree),
        "upstream": upstream,
        "downstream": downstream,
        "by_layer": dict(layers),
        "chain_size": len(chain_uids),
    }


def _collect_files_for_item(tree, root_item, children_idx, parents_idx, files):
    """アイテムの上流・下流を辿り、references のファイルパスを層別に収集する。"""
    uid = str(root_item.uid)
    prefix = find_doc_prefix(tree, root_item)

    # 自身の references
    for ref in get_references(root_item):
        path = ref.get("path", "")
        if path and path not in files[prefix]:
            files[prefix].append(path)

    # downstream
    downstream = []
    _trace_down(uid, children_idx, downstream, visited=set())
    for entry in downstream:
        for ref in entry.get("references", []):
            path = ref.get("path", "")
            if path and path not in files[entry["prefix"]]:
                files[entry["prefix"]].append(path)

    # upstream
    upstream = []
    _trace_up(uid, parents_idx, upstream, visited=set(), rich=True)
    for entry in upstream:
        for ref in entry.get("references", []):
            path = ref.get("path", "")
            if path and path not in files[entry["prefix"]]:
                files[entry["prefix"]].append(path)


def cmd_chain(tree, args):
    """指定UIDまたはファイルパスの上流→下流チェーン全体を表示する。"""
    children_idx, parents_idx = build_link_index(tree)

    # --file による逆引きモード
    if getattr(args, "file", None):
        matched = _find_items_by_file(tree, args.file)
        if not matched:
            out({"ok": False, "error": f"ファイル '{args.file}' をreferencesに持つアイテムが見つかりません"})

        chains = []
        for root_item, _prefix in matched:
            chain = _build_single_chain(tree, root_item, children_idx, parents_idx)
            chains.append(chain)

        out({
            "ok": True,
            "action": "chain",
            "mode": "by_file",
            "file": args.file,
            "chains": chains,
            "matched_count": len(chains),
        })

    # UID指定モード（従来の動作）
    if not args.uid:
        out({"ok": False, "error": "UID または --file のどちらかを指定してください"})

    root_item = find_item(tree, args.uid)
    if root_item is None:
        out({"ok": False, "error": f"UID '{args.uid}' が見つかりません"})

    chain = _build_single_chain(tree, root_item, children_idx, parents_idx)
    out({
        "ok": True,
        "action": "chain",
        "mode": "by_uid",
        **chain,
    })


def cmd_context(tree, args):
    """指定UIDの全文脈情報を一括取得する。

    エージェントが「何を読み、何を変え、何をテストすべきか」を
    1回のコマンドで判断できるよう、以下を集約して返す:
      - target: 対象アイテムの詳細
      - upstream: 上流アイテム（要件の根拠）
      - downstream: 下流アイテム（実装・テスト）
      - related_files: 関連ファイルパス（source / test / upstream に分類）
      - health: suspect / unreviewed / missing_children の状態
    """
    children_idx, parents_idx = build_link_index(tree)

    root_item = find_item(tree, args.uid)
    if root_item is None:
        out({"ok": False, "error": f"UID '{args.uid}' が見つかりません"})

    uid = str(root_item.uid)
    prefix = find_doc_prefix(tree, root_item)

    # upstream（参照元の references も含める）
    upstream = []
    _trace_up(uid, parents_idx, upstream, visited=set(), rich=True)

    # downstream（references を含む）
    downstream = []
    _trace_down(uid, children_idx, downstream, visited=set())

    # related_files: downstream の references をドキュメント種別で分類
    source_files = []
    test_files = []
    upstream_files = []

    # 対象アイテム自身の references
    for ref in get_references(root_item):
        path = ref.get("path", "")
        if path:
            source_files.append(path)

    # downstream の references を分類
    for entry in downstream:
        for ref in entry.get("references", []):
            path = ref.get("path", "")
            if not path:
                continue
            if entry["prefix"] in ("TST",):
                if path not in test_files:
                    test_files.append(path)
            elif entry["prefix"] in ("IMPL",):
                if path not in source_files:
                    source_files.append(path)
            else:
                if path not in source_files:
                    source_files.append(path)

    # upstream の references
    for entry in upstream:
        for ref in entry.get("references", []):
            path = ref.get("path", "")
            if path and path not in upstream_files:
                upstream_files.append(path)

    # health: 下流のsuspect・未レビュー・子リンク不足を検出
    suspect_items = []
    unreviewed_items = []
    for entry in downstream:
        item = find_item(tree, entry["uid"])
        if item is None:
            continue
        if is_suspect(item, tree):
            suspect_items.append(entry["uid"])
        if not item.reviewed:
            unreviewed_items.append(entry["uid"])

    # 対象自身のsuspect・レビュー状態
    if is_suspect(root_item, tree):
        suspect_items.insert(0, uid)
    if not root_item.reviewed:
        unreviewed_items.insert(0, uid)

    # 子リンクの欠落（子ドキュメントが存在するのにリンクがない）
    has_children = bool(children_idx.get(uid))
    child_docs = [d for d in tree if d.parent == prefix]
    missing_children = bool(child_docs) and not has_children

    # gherkin 属性
    gherkin = None
    if hasattr(root_item, "get"):
        g = root_item.get("gherkin")
        if g:
            gherkin = g.strip() if isinstance(g, str) else g

    out({
        "ok": True,
        "action": "context",
        "target": {
            **item_summary(root_item, prefix, tree),
            "gherkin": gherkin,
        },
        "upstream": upstream,
        "downstream": downstream,
        "related_files": {
            "source": source_files,
            "test": test_files,
            "upstream": upstream_files,
        },
        "health": {
            "suspects": suspect_items,
            "unreviewed": unreviewed_items,
            "missing_children": missing_children,
            "suspect_count": len(suspect_items),
            "unreviewed_count": len(unreviewed_items),
        },
    })


def cmd_related_files(tree, args):
    """指定UIDに関連する全ファイルパスをドキュメント層別に返す。

    context より軽量。「このUIDに関連するコード・テストファイルを
    全部読みたい」というケースに特化した出力。
    """
    children_idx, parents_idx = build_link_index(tree)

    # --file による逆引きモード
    if getattr(args, "file", None):
        matched = _find_items_by_file(tree, args.file)
        if not matched:
            out({"ok": False, "error": f"ファイル '{args.file}' をreferencesに持つアイテムが見つかりません"})

        all_files = defaultdict(list)
        matched_uids = []
        for root_item, _prefix in matched:
            matched_uids.append(str(root_item.uid))
            _collect_files_for_item(
                tree, root_item, children_idx, parents_idx, all_files
            )

        out({
            "ok": True,
            "action": "related-files",
            "mode": "by_file",
            "file": args.file,
            "matched_uids": matched_uids,
            "files": dict(all_files),
        })

    # UID指定モード
    root_item = find_item(tree, args.uid)
    if root_item is None:
        out({"ok": False, "error": f"UID '{args.uid}' が見つかりません"})

    files = defaultdict(list)
    _collect_files_for_item(tree, root_item, children_idx, parents_idx, files)

    out({
        "ok": True,
        "action": "related-files",
        "mode": "by_uid",
        "uid": args.uid,
        "files": dict(files),
    })
