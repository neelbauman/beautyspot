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
2. **振る舞いの定義が必要な文書には `gherkin` 属性で書く。** Given/When/Then 形式。テストケースに直結させる
3. **テストを書いたらTSTを書く。** テストコードとTSTアイテムは常にペア
4. **変更したらimpact_analysisを回す。** 変更の影響を把握してから修正に入る
5. **バリデーションを最後に必ず実行する。** リンク漏れやカバレッジ低下を放置しない
6. 仕様変更時は `validate_and_report.py --serve` を使いダッシュボードを起動し、レビューをユーザーに促す
7. **関連アイテムの探索には `trace_query.py` を使う。** doorstop YAMLをgrepしない。ファイルパスからの逆引きは `chain --file` を使う
8. **派生要求は設計層のみで使う。** `derived: true` + 根拠明記。IMPL/TSTでの使用は禁止
9. **外部ファイル紐付けには `references` を使う。** `ref` ではなく `references` 属性。最大2–3ファイル
10. **仕様変更のコミットはドキュメント層ごとに分ける。** 詳細は `references/concepts/commit_convention.md` を参照
11. **新ドメイン概念には用語辞書を更新する。** `glossary.py add` で用語を追加し、`glossary.py check` で表記ゆれを検出する。詳細は `references/concepts/glossary.md` を参照
12. **設計判断は ADR に記録する。** 技術選定やアーキテクチャ変更時。詳細は `references/concepts/adr.md` を参照

## エージェントの振る舞い規約

- **仕様書の構造化**: 序文、背景、用語定義、章の見出しなど「システムが直接実装する要件ではないもの」には `--non-normative` を指定してアイテムを作成すること。
- **報告の簡潔化**: 内部構造は見せず、成果物ベースでユーザーに報告すること。
- **ツリー構造の動的判断**: 初動で `doorstop.build()` を呼び、存在する文書に基づいて振る舞いを動的に決定する。ツリー構造をハードコードしない。
- **最下位設計文書** = IMPL/TSTがリンクする直接の親（lite/standard: SPEC、full: LLD）。

## プロファイル

| プロファイル | 階層 | 適用場面 |
|---|---|---|
| `lite` | REQ → SPEC → IMPL/TST · ADR | 小規模（単体ライブラリ、個人開発） |
| `standard` | REQ/NFR → ARCH → SPEC → IMPL/TST · ADR | 中規模（複数サブシステム、チーム開発） |
| `full` | REQ/NFR → HLD → LLD → IMPL/TST · ADR | 大規模（規制産業、V字モデル準拠） |

詳細は `profiles/*.yml` および `references/concepts/traceability_and_profiles.md` を参照。

## セットアップ

```bash
uv add doorstop --dev
uv add markdown --dev
uv run python <skill-path>/scripts/init_project.py <project-dir> --profile standard

# NFRドキュメントも作成する場合（standard/full推奨）:
uv run python <skill-path>/scripts/init_project.py <project-dir> --profile standard --with-nfr
```

既存gitリポジトリは `--no-git-init` を付ける。

## 判断フロー

ユーザーの発話に応じて、該当するフロー文書を読み、手順に従う。

| 発話パターン | フロー | 概要 | 参照先 |
|---|---|---|---|
| 新機能・新要件 | [A] 新規開発 | REQ→設計→実装→テストの全サイクル | `references/flows/new_development.md` |
| 優先付け・整理 | [T] トリアージ | 優先度付け・バックログ整理・スコープ確定 | `references/flows/triage.md` |
| 既存の変更・修正 | [B] 変更 | 影響分析→設計更新→実装・テスト修正 | `references/flows/change.md` |
| バグ修正 | [C] バグ修正 | 再現→特定→修正→回帰テスト登録 | `references/flows/bugfix.md` |
| 状況確認 | [D] レポート | カバレッジ・suspect・健全性の状況確認 | `references/flows/report.md` |
| リリース前チェック | [E] リリースゲート | リリース前の必須チェックリスト（0 errors・100% coverage） | `references/flows/release_gate.md` |
| 既存プロジェクトへの初期導入 | [F] 初期導入 | 既存コードへの逆引き仕様化（コード→ドキュメント） | `references/flows/initial_adoption.md` |
| 機能削除・要件取り下げ | [G] 非活性化 | active: false によるソフトデリートと連鎖処理 | `references/flows/deactivation.md` |

## リファレンス

| ドキュメント | 内容 |
|---|---|
| `references/doorstop_reference.md` | Doorstop操作・属性・スクリプトリファレンス |
| `references/item_writing_guide.md` | アイテム記述テンプレート（REQ/SPEC/IMPL/TST） |
| `references/diagram_and_image_guide.md` | 図表・画像・数式の挿入ガイド |
| `references/scaling_strategy.md` | プロジェクト規模別の導入・運用ガイド |
| `references/concepts/traceability_and_profiles.md` | トレーサビリティ・プロファイル・ライフサイクル概念 |
| `references/concepts/commit_convention.md` | コミット粒度規約 |
| `references/concepts/nfr.md` | FR/NFR（機能要件・非機能要件）の分類と運用 |
| `references/concepts/adr.md` | ADR（設計判断記録）連携 |
| `references/concepts/glossary.md` | 用語辞書（ユビキタス言語）の運用概念 |
| `references/glossary_reference.md` | glossary.py スクリプトリファレンス |
| `references/concepts/ci_integration.md` | CI連携の概念 |

## エージェントの禁止事項

- ユーザーにDoorstop操作を要求する
- 設計文書なしでコードを書き始める（初期導入[F]を除く）
- doorstop YAMLファイルをgrep/手動検索する（`trace_query.py` を使う）
- IMPL/TSTで `derived: true` を使う
- `ref` 属性を使う（`references` に統一）
- suspect未解消のまま次のタスクに移る
- ツリーに存在しない文書タイプを作成しようとする
