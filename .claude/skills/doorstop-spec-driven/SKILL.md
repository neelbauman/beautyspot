---
name: doorstop-spec-driven
description: >
  仕様駆動開発（Specification-Driven Development）を自律的に実行するスキル。
  コーディングエージェントが、ユーザーの自然言語による要望を受け取り、
  Doorstopによる要件→仕様→実装→テストの全ライフサイクルを自動的に管理する。
  ユーザーは「〜を作って」「〜を直して」と言うだけでよい。
  エージェントがREQ/SPEC/IMPL/TSTアイテムの作成および修正・リンク・バリデーション・
  影響分析をすべて自動で行い、コードの実装・テストも並行して実施する。
  「機能を追加して」「バグを直して」「仕様を変更して」「リファクタリングして」
  のような開発リクエスト全般でトリガーすること。
  コードを書く前に必ずこのスキルを参照し、要件→仕様→設計→実装のトレーサビリティを守ること。
---

# 仕様駆動開発スキル（エージェント版）

コーディングエージェントが仕様駆動開発のライフサイクルを自律的に実行するための指示書。
ユーザーは気軽に要望を伝えるだけでよい。エージェントが要件登録・設計策定・実装・テスト・
トレーサビリティ管理・バリデーションをすべて自動で行う。

## 鉄則

1. **コードを書く前に設計文書を書く。** 初期導入時（[F]フロー）のみ例外
2. **テストを書いたらTSTを書く。** テストコードとTSTアイテムは常にペア
3. **変更したらimpact_analysisを回す。** 変更の影響を把握してから修正に入る
4. **バリデーションを最後に必ず実行する。** リンク漏れやカバレッジ低下を放置しない
5. 仕様変更時は `serve_app.py` を使いダッシュボードを起動し、レビューをユーザーに促す
6. **関連アイテムの探索には `trace_query.py` を使う。** doorstop YAMLをgrepしない
7. **派生要求は設計層のみで使う。** `derived: true` + 根拠明記。IMPL/TSTでの使用は禁止
8. **外部ファイル紐付けには `references` を使う。** `ref` ではなく `references` 属性。最大2–3ファイル
9. **仕様変更のコミットはドキュメント層ごとに分ける。** 詳細は「コミット粒度規約」を参照

## プロファイル

| プロファイル | 階層 | 適用場面 |
|---|---|---|
| `lite` | REQ → SPEC → IMPL/TST | 小規模（単体ライブラリ、個人開発） |
| `standard` | REQ → ARCH → SPEC → IMPL/TST | 中規模（複数サブシステム、チーム開発） |
| `full` | REQ → HLD → LLD → IMPL/TST | 大規模（規制産業、V字モデル準拠） |

詳細は `profiles/*.yml` を参照。

## セットアップ

```bash
uv add doorstop --dev
uv run python <skill-path>/scripts/init_project.py <project-dir> --profile lite
```

既存gitリポジトリは `--no-git-init` を付ける。

## ツリー構造の動的判断

**エージェントはツリー構造をハードコードしない。** 初動で `doorstop.build()` を呼び、
存在する文書に基づいて振る舞いを動的に決定する。

**最下位設計文書** = IMPL/TSTがリンクする直接の親（lite/standard: SPEC、full: LLD）。
以降「設計文書」はツリーに存在する設計層全体を指す。

## 判断フロー

```
ユーザーの発話
  ├─ 新機能・新要件？            → [A] 新規開発フロー
  ├─ 既存の変更・修正？          → [B] 変更フロー
  ├─ バグ修正？                  → [C] バグ修正フロー
  ├─ 状況確認？                  → [D] レポートフロー
  ├─ リリース前チェック？        → [E] リリースゲート
  └─ 既存プロジェクトへの初期導入？ → [F] 初期導入フロー
```

## [A] 新規開発フロー

1. **理解** — ユーザーの要望を要件文に変換する。曖昧な場合のみ確認
2. **分類** — 機能グループを決定（既存 or 新規）
3. **REQ登録** — `doorstop_ops.py add -d REQ -t "要件文" -g GROUP`
4. **設計策定** — 設計文書を上位から順に作成し、親へリンク。派生要求は `derived: true`
5. **実装** — 最下位設計文書に従ってコードを書く
6. **IMPL登録** — `doorstop_ops.py add -d IMPL --references '[...]' --links SPECXXX`
7. **テスト** — テストコードを書く
8. **TST登録** — `doorstop_ops.py add -d TST --references '[...]' --links SPECXXX`
9. **検証** — `validate_and_report.py --strict`。エラー0件を目指す
10. **報告** — 成果物ベースで簡潔に報告（Doorstopの内部構造は見せない）

操作コマンドは `doorstop_ops.py` を使う。アイテムの書き方は `references/item_writing_guide.md` を参照。

## [B] 変更フロー

1. **現状把握** — `trace_query.py chain <UID>` で関係性を把握
2. **影響分析** — `impact_analysis.py --changed <UID>` で波及範囲を特定
3. **設計更新** — 上位から順に修正（standard: ARCH → SPEC、full: HLD → LLD）
4. **実装修正** — コードを修正
5. **テスト修正** — テストを修正
6. **IMPL/TST更新** — アイテムを更新し、`doorstop_ops.py clear` でsuspect解消
7. **検証** — `validate_and_report.py --strict` + `impact_analysis.py --detect-suspects`
8. **報告** — 影響範囲と修正結果を報告。suspect 0件を確認

**順序厳守**: 設計→テスト→実装の順に修正する。テストや実装から修正する場合でも、必ず設計や仕様を追従させること。

## [C] バグ修正フロー

1. **原因特定** — どの設計文書/IMPLに関連するか特定
2. **判断** — 仕様バグ（設計通りだがユーザー期待と違う）→ [B]へ / 実装バグ（設計と実装が乖離）→ 続行
3. **コード修正** → **IMPL更新**（必要に応じて）
4. **再発防止テスト追加** → **TST登録**
5. **検証・報告**

## [D] レポートフロー

| やりたいこと | コマンド |
|---|---|
| プロジェクト全体サマリ | `trace_query.py <dir> status` |
| 特定UIDのチェーン | `trace_query.py <dir> chain <UID>` |
| カバレッジ詳細 | `trace_query.py <dir> coverage [--group GROUP]` |
| suspect一覧 | `trace_query.py <dir> suspects` |
| リンク漏れ検出 | `trace_query.py <dir> gaps [--document IMPL]` |
| CRUD操作 | `doorstop_ops.py <dir> add/update/link/clear/review` |
| 静的HTMLレポート | `validate_and_report.py <dir> --output-dir ./reports --strict` |
| ダッシュボード | `validate_and_report.py <dir> --serve [--port 8080]` |
| 影響分析 | `impact_analysis.py <dir> --detect-suspects [--json PATH]` |

ユーザーへの報告は技術用語を避け、件数・カバレッジ・suspect数を平易に伝える。

## [E] リリースゲート

| チェック | 必須 | コマンド |
|---|---|---|
| バリデーションエラー 0件 | はい | `validate_and_report.py --strict` |
| 全カバレッジ 100% | はい | `trace_query.py coverage` |
| suspect 0件 | はい | `impact_analysis.py --detect-suspects` |
| テスト全件パス | はい | プロジェクトのテストランナー |
| 未レビュー 0件 | 警告のみ | `trace_query.py status` |

## [F] 初期導入フロー（既存プロジェクトへの適用）

既にコードが存在するプロジェクトに仕様駆動開発を導入するとき。
鉄則1「コードを書く前に設計を書く」はこのフローでのみ例外とする。

1. **プロジェクト初期化** — `init_project.py <dir> --profile lite --no-git-init`
2. **コード読解** — 既存コードの構造・機能・テストを把握する
3. **REQ抽出** — 実装されている機能を要件として文書化（実態を記述、理想ではなく）
4. **設計文書作成** — コードの実態に基づいてSPEC（+ARCH）を作成
5. **IMPL紐付け** — 既存コードをIMPLアイテムとして登録し、`references` で紐づけ
6. **TST紐付け** — 既存テストをTSTアイテムとして登録し、`references` で紐づけ
7. **ベースライン確立** — 全アイテムの clear & review を実行
8. **検証** — `validate_and_report.py --strict` で整合性確認
9. **移行完了** — 以後は通常フロー（A〜E）に移行

注意事項:
- 一度にすべて網羅しなくてよい。主要機能から段階的に導入する
- 既存テストがない機能はTSTアイテムのみ作成し、テストは後日追加でもよい
- ベースライン確立前のsuspectは過渡期ノイズであり、一括clearする

## ドキュメント属性

| 属性 | 対象 | 説明 |
|---|---|---|
| `text` | 全アイテム | 内容（必須） |
| `group` | 全アイテム | 機能グループ: AUTH, PAY, USR 等（必須） |
| `links` | REQ以外 | 親へのリンク（`derived: true` の場合は空でもよい） |
| `derived` | 設計層のみ | 派生要求フラグ。`text` に根拠セクション必須 |
| `references` | IMPL/TST | 外部ファイル紐付け（辞書型リスト、最大2–3ファイル） |
| `test_level` | TST（standard/full） | `unit` / `integration` / `acceptance` |

`references` は `[{"path": "src/mod.py", "type": "file"}]` 形式。
`conftest.py`, `__init__.py`, 共通ユーティリティは含めない。

詳細は `references/doorstop_reference.md`、書き方は `references/item_writing_guide.md` を参照。

## コミット粒度規約

ダッシュボードはアイテムごとにgitの作成日・更新日・作成者・コミットハッシュを表示する。
コミットの粒度がアイテムの変更履歴としての意味を持つため、
仕様駆動の変更フローではコミットを **ドキュメント層の変更単位** で分ける。

### コミットを分けるタイミング（必須）

| タイミング | コミット内容 | メッセージ例 |
|---|---|---|
| REQ追加・変更 | REQのYMLファイル | `spec: add REQ017 [LIFECYCLE]` |
| 設計策定・変更 | SPEC（+ARCH/HLD/LLD）のYMLファイル | `spec: add SPEC017 for REQ017` |
| 実装＋IMPL登録 | ソースコード + IMPLのYMLファイル | `impl: IMPL017 lifecycle gc policy` |
| テスト＋TST登録 | テストコード + TSTのYMLファイル | `test: TST017 lifecycle gc tests` |
| suspect解消・review | clear/reviewされたYMLファイル | `spec: clear suspects for SPEC012` |

### コミットをまとめてよいケース

- 同一層の複数アイテムを同時に変更した場合（例: SPEC001〜003を一括修正）
- IMPL + TST を同一コミットにまとめる（実装とテストは密結合のため許容）
- 開発途中の試行錯誤（WIP）— ただし最終的にはsquashまたは整理を推奨
- ツール・CI設定・ドキュメント生成など仕様アイテムに関係しない変更

### コミットメッセージ規約

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

### エージェントへの指示

フロー [A]〜[C] の各ステップでコミットを作成する際は上記規約に従う。
ただし、ユーザーが明示的に「まとめてコミットして」「saveして」等と指示した場合はそちらを優先する。

## エージェントの振る舞い規約

### やること
- 初動でツリー構造を読み取り、プロファイルを動的に判断する
- 関連アイテムの探索には `trace_query.py chain <UID>` を使う
- 操作は `doorstop_ops.py` を優先する（Python API直接操作より簡潔）
- 設計層が複数ある場合は上位から順に作成・修正する
- 変更時は必ず影響分析を先に実行する
- 最後にバリデーションを実行しエラー0件を確認する
- ユーザーへの報告はDoorstopの内部構造を隠し、成果物ベースで伝える

### やらないこと
- ユーザーにDoorstop操作を要求する
- 設計文書なしでコードを書き始める（初期導入[F]を除く）
- doorstop YAMLファイルをgrep/手動検索する（`trace_query.py` を使う）
- IMPL/TSTで `derived: true` を使う
- `ref` 属性を使う（`references` に統一）
- suspect未解消のまま次のタスクに移る
- ツリーに存在しない文書タイプを作成しようとする
