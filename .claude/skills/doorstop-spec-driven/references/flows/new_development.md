# [A] 新規開発フロー

ユーザーが新機能の追加や新要件の実装を要望したとき。

## 手順

1. **理解** — ユーザーの要望を要件文に変換する。曖昧な場合のみ確認
2. **分類** — 機能グループと優先度を決定（既存グループ or 新規、`--priority` を設定）。FR（機能要件）か NFR（非機能要件）かを判別する（判断基準は `concepts/nfr.md` を参照）
3. **用語確認** — 新しいドメイン概念が登場する場合、`glossary.py add` で用語辞書を更新し、`glossary.py sync` で REQ に反映する（詳細は `concepts/glossary.md`）
4. **REQ登録** — `doorstop_ops.py add -d REQ -t "要件文" -g GROUP --priority high`
5. **設計策定** — 設計文書を上位から順に作成し、親へリンク。派生要求は `derived: true`。NFR制約がある場合は設計文書から NFR アイテムへもリンクする。振る舞いの定義が必要な文書には **gherkin 属性** に Given/When/Then 形式でシナリオを記述する
6. **実装・テスト** — 最下位設計文書に従ってコードとテストを書く（編集の順序は問わない）。gherkin のシナリオを TST のテストケースに変換する
7. **IMPL/TST登録** — `doorstop_ops.py add` でそれぞれ登録し、最下位設計にリンク
8. **レビュー** — `doorstop_ops.py chain-review <UID>` で関連アイテム全体を一括レビュー済みにする
9. **検証** — `validate_and_report.py --strict`。エラー0件を目指す
10. **コミット** — 仕様(設計)、テスト、実装の順番でコミットし、テストファーストの考え方を履歴に残す（詳細は `concepts/commit_convention.md`）
11. **ベースライン更新** — リリースポイントで `baseline_manager.py create <version> --tag`
12. **報告** — 成果物ベースで簡潔に報告（Doorstopの内部構造は見せない）

> **ADR**: 上記のどの段階でも、重要な意思決定があれば ADR を作成する（`doorstop_ops.py add -d ADR ...`）。
> ADR は独立文書であり、`links` で判断対象のアイテム（REQ/ARCH/SPEC/IMPL等）を指す。
> 詳細は `concepts/adr.md` を参照。

操作コマンドは `doorstop_ops.py` を使う。アイテムの書き方は `item_writing_guide.md` を参照。

## 設計策定の詳細

プロファイルに応じて設計文書の層数が異なる。

**liteプロファイル:**
1. 各REQに対して1つ以上のSPECを作成する
2. SPEC → REQ のリンクを張る

**standardプロファイル:**
1. 各REQに対して1つ以上のARCHを作成する（コンポーネント設計）
2. 各ARCHに対して1つ以上のSPECを作成する（モジュール設計）
3. ARCH → REQ、SPEC → ARCH のリンクを張る

**fullプロファイル:**
1. 各REQに対して1つ以上のHLDを作成する（サブシステム設計）
2. 各HLDに対して1つ以上のLLDを作成する（モジュール設計）
3. HLD → REQ、LLD → HLD のリンクを張る

## IMPL/TST 登録の詳細

**SPEC（gherkin 付き）:**
```bash
doorstop_ops.py <dir> add -d SPEC -t "仕様テキスト" --header "機能名" -g GROUP --links REQ001 \
  --gherkin "Scenario: 正常系
  Given 前提条件
  When 操作
  Then 期待結果

Scenario: 異常系
  Given 前提条件
  When エラーを引き起こす操作
  Then エラーが返る"
```

**IMPL:**
```bash
doorstop_ops.py <dir> add -d IMPL -t "実装の概要説明" -g GROUP \
  --references '[{"path":"src/module.py","type":"file"}]' --links SPEC001
```

**TST:**
```bash
doorstop_ops.py <dir> add -d TST -t "テスト手順と期待結果" -g GROUP \
  --references '[{"path":"tests/test_module.py","type":"file"}]' --links SPEC001
```

standard/fullでは `--test-level unit|integration|acceptance` を設定する。

## 報告テンプレート

```
[GROUP] 機能名を実装しました。
  - src/xxx.py — 実装概要
  - tests/test_xxx.py — テストN件（全件パス）
  - トレーサビリティ: 全リンク済み、カバレッジ100%
```
