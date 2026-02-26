# 整合性チェックスクリプト（check_spec_coverage.py）

プロジェクトの `scripts/check_spec_coverage.py` として生成するスクリプトのテンプレートと解説。

## 生成するスクリプト

```python
#!/usr/bin/env python3
"""
DoorstopのSPEC IDとGherkinの@タグの整合性をチェックするスクリプト。

使い方:
  python scripts/check_spec_coverage.py
  python scripts/check_spec_coverage.py --strict  # 孤児タグがあれば非ゼロ終了
"""
import os
import re
import sys
import glob
import yaml
import argparse
from pathlib import Path


def get_doorstop_ids(docs_dir: str, prefix: str) -> set[str]:
    """Doorstopドキュメントディレクトリから有効なIDセットを取得する"""
    ids = set()
    pattern = os.path.join(docs_dir, f"{prefix}*.yml")
    for filepath in glob.glob(pattern):
        filename = Path(filepath).stem  # 例: SPEC001
        # .doorstop設定ファイルはスキップ
        if filename.startswith('.'):
            continue
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
            if data and data.get('active', True):
                ids.add(filename.upper())
        except Exception:
            # パースできないファイルはIDとして採用しない
            pass
    return ids


def get_gherkin_tags(features_dir: str, prefix: str) -> dict[str, list[str]]:
    """featuresディレクトリからSPEC系タグを抽出する。{tag: [ファイルパス]}"""
    tag_map: dict[str, list[str]] = {}
    pattern = re.compile(rf'@({re.escape(prefix)}\d+)', re.IGNORECASE)
    
    for filepath in glob.glob(os.path.join(features_dir, '**/*.feature'), recursive=True):
        with open(filepath) as f:
            content = f.read()
        for match in pattern.finditer(content):
            tag = match.group(1).upper()
            tag_map.setdefault(tag, []).append(filepath)
    
    return tag_map


def main():
    parser = argparse.ArgumentParser(description='Doorstop-Gherkin整合性チェック')
    parser.add_argument('--specs-dir', default='specs', help='SPECドキュメントのディレクトリ')
    parser.add_argument('--features-dir', default='features', help='featuresディレクトリ')
    parser.add_argument('--prefix', default='SPEC', help='SPECのIDプレフィックス')
    parser.add_argument('--strict', action='store_true', help='問題があれば非ゼロ終了')
    args = parser.parse_args()

    exit_code = 0

    # --- 1. Doorstop上の有効なSPEC IDを取得 ---
    spec_ids = get_doorstop_ids(args.specs_dir, args.prefix)
    if not spec_ids:
        print(f"⚠️  {args.specs_dir}/ にSPECが見つかりません。パスを確認してください。")
        sys.exit(1)

    # --- 2. Gherkin内のタグを取得 ---
    tag_map = get_gherkin_tags(args.features_dir, args.prefix)

    # --- 3. 孤児タグの検出（Gherkinにあって、Doorstopにない） ---
    orphan_tags = {tag for tag in tag_map if tag not in spec_ids}
    if orphan_tags:
        print("❌ 孤児タグ（Doorstopに存在しないSPEC IDがGherkinで使われています）:")
        for tag in sorted(orphan_tags):
            for f in tag_map[tag]:
                print(f"   @{tag}  ←  {f}")
        exit_code = 1
    else:
        print("✅ 孤児タグなし: すべてのGherkinタグはDoorstopに存在します")

    # --- 4. カバレッジの算出（Doorstopにあって、Gherkinにない） ---
    covered = spec_ids & set(tag_map.keys())
    uncovered = spec_ids - covered
    coverage_pct = len(covered) / len(spec_ids) * 100 if spec_ids else 0

    print(f"\n📊 SPECカバレッジ: {len(covered)}/{len(spec_ids)} ({coverage_pct:.1f}%)")

    if uncovered:
        print("⚠️  Gherkinシナリオが未作成のSPEC:")
        for spec_id in sorted(uncovered):
            print(f"   {spec_id}")
        if args.strict:
            exit_code = 1
    else:
        print("✅ 全SPECにGherkinシナリオが存在します")

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
```

---

## 依存パッケージ

```
pyyaml
```

```bash
pip install pyyaml
```

---

## GitHub Actions での利用例

```yaml
# .github/workflows/spec-check.yml
name: Spec Coverage Check

on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pyyaml
      - run: python scripts/check_spec_coverage.py --strict
```

---

## カスタマイズポイント

- `--prefix`: SPECプレフィックスが異なる場合（例: `--prefix US` で `@US001` 形式）
- `--strict`: CIで失敗させたい場合（デフォルトは警告のみ）
- REQ側のカバレッジもチェックしたい場合: `get_doorstop_ids` を `reqs/` と `REQ` で追加実行する
