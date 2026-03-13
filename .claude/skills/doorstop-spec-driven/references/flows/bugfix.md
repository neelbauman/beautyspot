# [C] バグ修正フロー

バグの報告や修正要望があったとき。

## 手順

### 1. 原因特定

バグの再現条件を確認し、関連するコード・設計文書・アイテムを特定する。

```bash
# ファイルパスから関連アイテムを逆引き
trace_query.py <dir> chain --file <buggy-file-path>

# テキスト検索で関連アイテムを探す
doorstop_ops.py <dir> find "関連キーワード"
```

### 2. 仕様バグか実装バグかを判別

| 種別 | 定義 | 対応 |
|---|---|---|
| **仕様バグ** | 設計通りに動作しているが、ユーザーの期待と異なる | → [B] 変更フローへ移行 |
| **実装バグ** | 設計と実装が乖離している | → 以下のステップを続行 |

判別方法：
1. SPEC（または ARCH/HLD/LLD）のアイテムを読み、仕様上の期待動作を確認する
2. 実際の動作と仕様を比較する
3. 仕様通りなら**仕様バグ**、仕様と異なるなら**実装バグ**

### 3. コード修正

実装バグの場合、SPEC に記述された仕様に合致するようにコードを修正する。

修正時の注意：
- 仕様に曖昧さがある場合は、修正と併せて SPEC のエッジケースや振る舞いを明確化する
- 修正範囲が広がる場合は、`impact_analysis.py --changed <UID>` で影響を確認する

### 4. 再発防止テスト追加

バグの再現テストを書き、修正後に通ることを確認する。

- テストは「バグが再発した場合に検知できる」ことを目的とする
- Gherkin がある SPEC の場合、再現シナリオを gherkin 属性に追記することも検討する

```bash
# TST アイテムを追加（テストコードとペア）
doorstop_ops.py <dir> add -d TST \
  -t "バグ再現テスト: [バグの概要]" \
  -g GROUP \
  --references '[{"path":"tests/test_xxx.py","type":"file"}]' \
  --links SPEC001
```

### 5. IMPL 更新

必要に応じて IMPL アイテムの text を更新する。
バグ修正の経緯や設計判断を「実装メモ」セクションに記録する。

```bash
doorstop_ops.py <dir> update IMPL001 -t "更新後のテキスト（バグ修正の経緯を追記）"
```

### 6. 検証

```bash
# テスト実行
uv run pytest tests/ -x -q

# トレーサビリティ検証
validate_and_report.py <dir> --strict
```

### 7. コミット

```bash
# テスト + TST アイテム
git add tests/test_xxx.py docs/tst/TST0XX.yml
git commit -m "test: TST0XX regression test for [bug summary]"

# バグ修正 + IMPL アイテム更新
git add src/module.py docs/impl/IMPL001.yml
git commit -m "fix: IMPL001 [bug summary]"

# SPEC 明確化がある場合
git add docs/specs/SPEC001.yml
git commit -m "spec: clarify SPEC001 edge case for [bug]"
```

### 8. 報告

修正内容と再発防止策を報告する。

## 報告テンプレート

```
[GROUP] バグを修正しました。
  - 原因: [仕様バグ/実装バグ] — [原因の説明]
  - 修正: src/xxx.py — [修正内容]
  - 再発防止: tests/test_xxx.py — テスト追加
  - トレーサビリティ: 全リンク済み、suspect 0件
```
