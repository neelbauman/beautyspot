#!/usr/bin/env python3
"""要件の一括インポートスクリプト。

YAML/JSON/CSV形式の要件リストをDoorstopに一括登録する。

Usage:
    python bulk_import.py <project-dir> <input-file> --document SYS [--link-to SYS001]

入力ファイル形式:

--- YAML ---
- text: "システムはユーザー認証を提供すること"
  header: "ユーザー認証"
  level: "1.0"
  group: "AUTH"
  links: []

--- JSON ---
[
  {"text": "システムはユーザー認証を提供すること", "header": "ユーザー認証", "level": "1.0", "group": "AUTH"}
]

--- CSV ---
text,header,level,group,links
"システムはユーザー認証を提供すること","ユーザー認証","1.0","AUTH",""
"""

import argparse
import csv
import json
import os
import sys

import yaml

try:
    import doorstop
except ImportError:
    print("ERROR: doorstop がインストールされていません。", file=sys.stderr)
    sys.exit(1)


def load_items_yaml(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else [data]


def load_items_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def load_items_csv(filepath):
    items = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item = {"text": row.get("text", "").strip()}
            if row.get("header"):
                item["header"] = row["header"].strip()
            if row.get("level"):
                item["level"] = row["level"].strip()
            if row.get("links"):
                item["links"] = [
                    s.strip() for s in row["links"].split(";") if s.strip()
                ]
            if row.get("group"):
                item["groups"] = [s.strip() for s in row["group"].split(",") if s.strip()]
            items.append(item)
    return items


def load_items(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".yml", ".yaml"):
        return load_items_yaml(filepath)
    elif ext == ".json":
        return load_items_json(filepath)
    elif ext == ".csv":
        return load_items_csv(filepath)
    else:
        print(f"ERROR: 未対応の拡張子: {ext}（.yaml/.json/.csvを使用してください）", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="要件の一括インポート")
    parser.add_argument("project_dir", help="プロジェクトのルートディレクトリ")
    parser.add_argument("input_file", help="インポート元ファイル（YAML/JSON/CSV）")
    parser.add_argument(
        "--document", "-d", required=True,
        help="インポート先のドキュメントプレフィックス（例: SYS, SRD, TST）"
    )
    parser.add_argument(
        "--link-to", "-l", action="append", default=[],
        help="全アイテムに共通で張るリンク先UID（繰り返し指定可）"
    )
    parser.add_argument(
        "--group", "-g", default=None,
        help="全アイテムに共通で設定する機能グループ（例: AUTH, PAY）"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="実際には登録せず、インポート内容を表示するだけ"
    )
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    items_data = load_items(os.path.abspath(args.input_file))
    print(f"{len(items_data)}件の要件をインポートします → {args.document}")

    if args.dry_run:
        for i, data in enumerate(items_data, 1):
            print(f"  [{i}] {data.get('header', '(ヘッダーなし)')}: {data['text'][:60]}...")
        print("\n--dry-run のため実際の登録は行いません。")
        return

    tree = doorstop.build()
    doc = tree.find_document(args.document)

    created = []
    for data in items_data:
        kwargs = {}
        if "level" in data:
            kwargs["level"] = data["level"]

        item = doc.add_item(**kwargs)
        item.text = data["text"]
        if "header" in data:
            item.header = data["header"]

        # 個別リンク
        links = data.get("links", [])
        if isinstance(links, str):
            links = [s.strip() for s in links.split(";") if s.strip()]
        for link in links:
            item.link(link)

        # 共通リンク
        for link in args.link_to:
            item.link(link)

        # 機能グループ: 個別指定 > コマンドライン共通指定
        groups_str = data.get("group") or args.group
        if groups_str:
            item.set("groups", [s.strip() for s in groups_str.split(",") if s.strip()])

        item.save()
        created.append(item)
        print(f"  追加: {item.uid} - {data['text'][:50]}...")

    print(f"\n{len(created)}件のアイテムを {args.document} に登録しました。")
    print("登録されたUID:")
    for item in created:
        print(f"  {item.uid}")


if __name__ == "__main__":
    main()
