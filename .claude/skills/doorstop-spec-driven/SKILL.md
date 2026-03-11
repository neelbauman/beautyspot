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
6. **関連アイテムの探索には `trace_query.py` を使う。** doorstop YAMLをgrepしない。ファイルパスからの逆引きは `chain --file` を使う
7. **派生要求は設計層のみで使う。** `derived: true` + 根拠明記。IMPL/TSTでの使用は禁止
8. **外部ファイル紐付けには `references` を使う。** `ref` ではなく `references` 属性。最大2–3ファイル
9. **仕様変更のコミットはドキュメント層ごとに分ける。** 詳細は `references/dev_lifecycle.md` を参照

## エージェントの振る舞い規約

- **仕様書の構造化**: 序文、背景、用語定義、章の見出しなど「システムが直接実装する要件ではないもの」には `--non-normative` を指定してアイテムを作成すること。
- **報告の簡潔化**: 内部構造は見せず、成果物ベースでユーザーに報告すること。
- **ツリー構造の動的判断**: 初動で `doorstop.build()` を呼び、存在する文書に基づいて振る舞いを動的に決定する。ツリー構造をハードコードしない。
- **最下位設計文書** = IMPL/TSTがリンクする直接の親（lite/standard: SPEC、full: LLD）。

## プロファイル

| プロファイル | 階層 | 適用場面 |
|---|---|---|
| `lite` | REQ → SPEC → IMPL/TST | 小規模（単体ライブラリ、個人開発） |
| `standard` | REQ/NFR → ARCH → SPEC → IMPL/TST | 中規模（複数サブシステム、チーム開発） |
| `full` | REQ/NFR → HLD → LLD → IMPL/TST | 大規模（規制産業、V字モデル準拠） |

詳細は `profiles/*.yml` を参照。

## セットアップ

```bash
uv add doorstop --dev
uv run python <skill-path>/scripts/init_project.py <project-dir> --profile lite

# NFRドキュメントも作成する場合（standard/full推奨）:
uv run python <skill-path>/scripts/init_project.py <project-dir> --profile standard --with-nfr
```

既存gitリポジトリは `--no-git-init` を付ける。

## 判断フロー

```
ユーザーの発話
  ├─ 新機能・新要件？            → [A] 新規開発フロー
  ├─ 要件の優先付け・整理？      → [T] トリアージフロー
  ├─ 既存の変更・修正？          → [B] 変更フロー
  ├─ バグ修正？                  → [C] バグ修正フロー
  ├─ 状況確認？                  → [D] レポートフロー
  ├─ リリース前チェック？        → [E] リリースゲート
  ├─ 既存プロジェクトへの初期導入？ → [F] 初期導入フロー
  └─ 機能削除・要件取り下げ？    → [G] 非活性化（削除）フロー
```

各フローの詳細と判断基準は `references/dev_lifecycle.md` を参照。

## [T] トリアージフロー（優先付け・整理）

ユーザーが「何を先に作るか決めたい」「バックログを整理したい」等と発話したとき。

1. **バックログ確認** — `trace_query.py <dir> backlog` で REQ を優先度順に一覧
2. **優先度設定** — `doorstop_ops.py <dir> update REQ001 --priority high`
3. **未着手の特定** — カバレッジ 0 の REQ（設計・実装が未作成）を特定
4. **ユーザーへの提示** — 未着手 REQ を優先度順に提示し、次に着手するものを確認
5. **ベースライン確認** — `baseline_manager.py <dir> list` で現在の基準点を確認

```bash
# 優先度付きでREQ追加
doorstop_ops.py <dir> add -d REQ -t "要件文" -g GROUP --priority high

# バックログ確認（優先度順）
trace_query.py <dir> backlog
trace_query.py <dir> backlog --group AUTH

# NFR（非機能要件）のバックログも確認
trace_query.py <dir> backlog -d NFR
```

## [D] レポートフロー

| やりたいこと | コマンド |
|---|---|
| プロジェクト全体サマリ | `trace_query.py <dir> status` |
| 特定UIDのチェーン | `trace_query.py <dir> chain <UID>` |
| ファイルからチェーン逆引き | `trace_query.py <dir> chain --file src/mod.py` |
| カバレッジ詳細 | `trace_query.py <dir> coverage [--group GROUP]` |
| suspect一覧 | `trace_query.py <dir> suspects` |
| リンク漏れ検出 | `trace_query.py <dir> gaps [--document IMPL]` |
| **優先度付きバックログ** | `trace_query.py <dir> backlog [--group GROUP]` |
| CRUD操作 | `doorstop_ops.py <dir> add/update/link/unlink/clear/review` |
| 変更の一括承認 | `doorstop_ops.py <dir> chain-review / chain-clear` |
| 非活性化（単体） | `doorstop_ops.py <dir> deactivate <UID> [<UID2> ...]` |
| 非活性化（チェーン） | `doorstop_ops.py <dir> deactivate-chain <UID> [--force]` |
| 活性化（チェーン） | `doorstop_ops.py <dir> activate-chain <UID>` |
| 静的HTMLレポート | `validate_and_report.py <dir> --output-dir ./reports --strict` |
| ダッシュボード | `validate_and_report.py <dir> --serve [--port 8080]` |
| 影響分析 | `impact_analysis.py <dir> --detect-suspects [--json PATH]` |
| **ベースライン作成** | `baseline_manager.py <dir> create <name> [--tag]` |
| **ベースライン一覧** | `baseline_manager.py <dir> list` |
| **バージョン間差分** | `baseline_manager.py <dir> diff <v1> <v2>` |
| **現在との差分** | `baseline_manager.py <dir> diff <v1> HEAD` |

## [B] 変更フロー

1. **現状確認** — `trace_query.py <dir> chain <UID>` で影響範囲を特定
2. **影響分析** — `impact_analysis.py <dir> --detect-suspects` でアクションを確認
3. **上流の更新・レビュー** — REQ/SPEC/ARCH を修正し、`doorstop_ops.py chain-review <UID>` で上流を確定
4. **実装・テストの更新** — コードを修正し、テストをパスさせる
5. **下流の承認** — `doorstop_ops.py chain-clear <UID>` で下流の suspect を一括解消
6. **バリデーション** — `validate_and_report.py --strict` で整合性を最終確認

ユーザーへの報告は技術用語を避け、件数・カバレッジ・suspect数を平易に伝える。

## [E] リリースゲート

| チェック | 必須 | コマンド |
|---|---|---|
| バリデーションエラー 0件 | はい | `validate_and_report.py --strict` |
| 全カバレッジ 100% | はい | `trace_query.py coverage` |
| suspect 0件 | はい | `impact_analysis.py --detect-suspects` |
| テスト全件パス | はい | プロジェクトのテストランナー |
| 未レビュー 0件 | 警告のみ | `trace_query.py status` |
| ベースライン作成 | 推奨 | `baseline_manager.py create <version> --tag` |

## ドキュメント属性

| 属性 | 対象 | 説明 |
|---|---|---|
| `text` | 全アイテム | 内容（必須） |
| `groups` | 全アイテム | 機能グループ: AUTH, PAY, USR 等（必須） |
| `priority` | REQ/NFR | 優先度: `critical` / `high` / `medium`（デフォルト） / `low` |
| `links` | REQ以外 | 親へのリンク（`derived: true` の場合は空でもよい） |
| `derived` | 設計層のみ | 派生要求フラグ。`text` に根拠セクション必須 |
| `references` | IMPL/TST | 外部ファイル紐付け（辞書型リスト、最大2–3ファイル） |
| `test_level` | TST（standard/full） | `unit` / `integration` / `acceptance` |

`references` は `[{"path": "src/mod.py", "type": "file"}]` 形式。
`conftest.py`, `__init__.py`, 共通ユーティリティは含めない。

詳細は `references/doorstop_reference.md`、書き方は `references/item_writing_guide.md` を参照。

## NFR（非機能要件）の扱い

**liteプロファイル**: `groups: [NFR, PERF]` 等で REQ に混在させる。専用文書は不要。

**standard/full**: `--with-nfr` で専用 NFR ドキュメントを作成する（推奨）。
- NFR は REQ と並列のルート文書（parent: null）
- 設計文書（ARCH/HLD）は NFR アイテムへリンクして非機能制約の実現方針を明示する
- TST は NFR アイテムへリンクして非機能テスト（性能・セキュリティ・信頼性）を対応付ける

典型グループ: `PERF`, `SEC`, `REL`, `MNT`, `PRT`, `SAF`（規制産業）

## エージェントの禁止事項

- ユーザーにDoorstop操作を要求する
- 設計文書なしでコードを書き始める（初期導入[F]を除く）
- doorstop YAMLファイルをgrep/手動検索する（`trace_query.py` を使う）
- IMPL/TSTで `derived: true` を使う
- `ref` 属性を使う（`references` に統一）
- suspect未解消のまま次のタスクに移る
- ツリーに存在しない文書タイプを作成しようとする
