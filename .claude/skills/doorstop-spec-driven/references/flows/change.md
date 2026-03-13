# [B] 変更フロー

既存の仕様・設計・実装に対する変更要望があったとき。

## 手順

### 1. 現状把握

変更対象の関連アイテムを特定し、現在のトレーサビリティチェーンを把握する。

```bash
# UID が分かっている場合
trace_query.py <dir> chain <UID>

# ファイルパスから逆引きする場合
trace_query.py <dir> chain --file <path>
```

確認事項：
- 変更対象のアイテムはどの層か（REQ / 設計 / IMPL / TST）
- 上流（なぜ存在するか）と下流（何に影響するか）の範囲

### 2. 影響分析

変更がどこまで波及するかを事前にシミュレーションする。

```bash
# 変更予定のアイテムを指定して影響範囲を分析
impact_analysis.py <dir> --changed <UID>

# 既に変更を加えた場合は suspect 自動検出
impact_analysis.py <dir> --detect-suspects
```

**判断基準:**

| 影響範囲 | 対応 |
|---|---|
| 下流の IMPL/TST のみ影響 | そのまま続行 |
| 設計文書（SPEC/ARCH）にも影響 | 上位から順に修正 |
| 他グループのアイテムにも影響 | ユーザーに影響範囲を報告し、スコープを確認 |

### 3. ADR の検討

設計判断が変わる場合（技術選定の変更、アーキテクチャパターンの変更等）は、
既存の ADR を `superseded` に更新し、新しい ADR を作成する。
詳細は `concepts/adr.md` を参照。

### 4. 設計更新

上位から順に修正する。設計文書の変更は下流の suspect を発生させるため、
最初に設計を確定させてから実装・テストに進む。

- **lite**: SPEC を修正
- **standard**: ARCH → SPEC の順に修正
- **full**: HLD → LLD の順に修正

```bash
# 設計文書を更新（gherkin 属性も必要に応じて更新）
doorstop_ops.py <dir> update SPEC001 -t "更新後の仕様テキスト"
doorstop_ops.py <dir> update SPEC001 --gherkin "更新後の Gherkin シナリオ"
```

### 5. 実装・テスト修正

最終的に整合性が取れていれば、仕様・テスト・実装の **編集順序は問わない**。

- 影響を受ける IMPL の `references` 先（ソースコード）を修正する
- 影響を受ける TST の `references` 先（テストコード）を修正する
- 新たなエッジケースやシナリオがあればテストを追加する

### 6. IMPL/TST 更新

アイテムの text を更新し、関連アイテムとの整合性を確認した上で、
suspect を一括解消＆レビュー済みにする。

```bash
# アイテムの text を更新
doorstop_ops.py <dir> update IMPL001 -t "更新後の実装説明"
doorstop_ops.py <dir> update TST001 -t "更新後のテスト説明"

# チェーン全体を一括でレビュー済み + suspect 解消
doorstop_ops.py <dir> chain-review <UID>
doorstop_ops.py <dir> chain-clear <UID>
```

### 7. 用語辞書の確認

変更によりドメイン用語の意味が変わった場合、REQ 先頭の用語定義アイテムを更新する。
詳細は `concepts/glossary.md` を参照。

### 8. 検証

```bash
validate_and_report.py <dir> --strict
impact_analysis.py <dir> --detect-suspects
```

エラー 0 件、suspect 0 件を確認する。

### 9. コミット

仕様（設計）、テスト、実装の順番でコミットする。
詳細は `concepts/commit_convention.md` を参照。

```bash
# 設計変更
git add docs/specs/SPEC001.yml
git commit -m "spec: update SPEC001 change description"

# 実装追従
git add src/module.py docs/impl/IMPL001.yml
git commit -m "impl: update IMPL001 follow SPEC001 change"

# テスト追従
git add tests/test_module.py docs/tst/TST001.yml
git commit -m "test: update TST001 follow SPEC001 change"

# suspect 解消
git add docs/impl/IMPL001.yml docs/tst/TST001.yml
git commit -m "spec: clear suspects IMPL001 TST001"
```

### 10. 報告

影響範囲と修正結果を報告。suspect 0 件を確認する。

## 報告テンプレート

```
[GROUP] SPEC001 の仕様を変更しました。
  - 変更内容: ...
  - 影響範囲: IMPL001, TST001（修正済み）
  - テスト: 全件パス
  - トレーサビリティ: suspect 0件、カバレッジ 100%
```

ユーザーへの報告は技術用語を避け、件数・カバレッジ・suspect数を平易に伝える。
