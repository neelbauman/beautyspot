# コミット粒度規約

ダッシュボードはアイテムごとにgitの作成日・更新日・作成者・コミットハッシュを表示する。
コミットの粒度がアイテムの変更履歴としての意味を持つため、
仕様駆動ライフサイクル内のコミットは **ドキュメント層の変更単位** で分ける。

## 基本ルール

```
1コミット = 1つのドキュメント層の変更
```

## コミットを分けるタイミング（必須）

| タイミング | コミット内容 | メッセージ例 |
|---|---|---|
| REQ追加・変更 | REQのYMLファイル | `spec: add REQ017 [LIFECYCLE]` |
| 設計策定・変更 | SPEC（+ARCH/HLD/LLD）のYMLファイル | `spec: add SPEC017 for REQ017` |
| 実装＋IMPL登録 | ソースコード + IMPLのYMLファイル | `impl: IMPL017 lifecycle gc policy` |
| テスト＋TST登録 | テストコード + TSTのYMLファイル | `test: TST017 lifecycle gc tests` |
| suspect解消・review | clear/reviewされたYMLファイル | `spec: clear suspects for SPEC012` |

## エージェントのコミット実行手順

各層の作業完了後、**対象ファイルだけを** ステージングしてコミットする。
`git add .` や `git add -A` は複数層のファイルを混在させるため使わない。

```bash
# ── REQ 追加後 ──────────────────────────────────────────
git add docs/reqs/REQ017.yml
git commit -m "spec: add REQ017 [GROUP]"

# ── SPEC 策定後 ──────────────────────────────────────────
git add docs/specs/SPEC017.yml
git commit -m "spec: add SPEC017 for REQ017"

# ── 実装後（ソースコード + IMPL YAML を同一コミット）──────
git add src/beautyspot/core.py docs/impl/IMPL017.yml
git commit -m "impl: IMPL017 lifecycle gc policy"

# ── テスト後（テストコード + TST YAML を同一コミット）──────
git add tests/integration/core/test_gc.py docs/tst/TST017.yml
git commit -m "test: TST017 lifecycle gc tests"

# ── suspect 解消後 ────────────────────────────────────────
git add docs/impl/IMPL017.yml docs/tst/TST017.yml
git commit -m "spec: clear suspects IMPL017 TST017"
```

ディレクトリパスはプロジェクト構造に合わせること（`doorstop_ops.py tree` で確認）。

## コミットをまとめてよいケース

- 同一層の複数アイテムを同時に変更した場合（例: SPEC001〜003を一括修正）
- IMPL + TST を同一コミットにまとめる（実装とテストは密結合のため許容）
- 開発途中の試行錯誤（WIP）— ただし最終的にはsquashまたは整理を推奨
- ツール・CI設定・ドキュメント生成など仕様アイテムに関係しない変更

## コミットメッセージ規約

```
<type>: <summary>

type:
  spec:  REQ/SPEC/ARCH/HLD/LLD のYML変更
  impl:  IMPL + ソースコード
  test:  TST + テストコード
  fix:   バグ修正（実装バグ）
  tool:  スキルスクリプト・CI・ツール変更
```

アイテムUIDをメッセージに含めると、git logからアイテムの変更履歴を追跡しやすくなる。

## 典型的なフローでの推奨コミット分割

```
[A] 新規開発の場合:
  commit 1: spec: add REQ017 [GROUP]           ← REQ層
  commit 2: spec: add SPEC017 for REQ017       ← SPEC層（ARCH/HLD/LLDも同様）
  commit 3: impl: IMPL017 + source code        ← IMPL層 + ソースコード
  commit 4: test: TST017 + test code           ← TST層 + テストコード

[B] 変更の場合:
  commit 1: spec: update SPEC003 hash algorithm ← 設計変更
  commit 2: impl: update IMPL003 + source code  ← 実装追従
  commit 3: test: update TST003 + test code     ← テスト追従
  commit 4: spec: clear suspects IMPL003 TST003 ← suspect解消
```

## なぜ分けるのか

1. **アイテム単位の変更追跡**: `updated_at` と `updated_commit` がそのアイテム固有の変更を指す
2. **影響分析との整合**: `impact_analysis.py --from-git` がコミット単位で変更を検出するため、層ごとに分かれていると因果関係が明確になる
3. **レビュー効率**: 設計変更と実装変更が分離されていると、レビュアーが段階的に確認できる

## エージェントへの指示

フロー [A]〜[C] の各ステップでコミットを作成する際は上記規約に従う。
ただし、ユーザーが明示的に「まとめてコミットして」「saveして」等と指示した場合はそちらを優先する。
