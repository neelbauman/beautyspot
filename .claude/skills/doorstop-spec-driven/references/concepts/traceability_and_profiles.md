# トレーサビリティとプロファイル

仕様駆動開発の基本概念、プロファイル定義、ドキュメント役割、
トレーサビリティの仕組みを解説する。

## 基本原則

**仕様が起点、コードが従属。** コードは仕様を実現する手段であり、
仕様に紐づかないコードは存在意義を説明できない。
同様に、テストのないコードは検証されていない仕様実装であり、
仕様のない要件は実現方法が未定義である。

## プロファイルとドキュメント階層

プロジェクト規模に応じた3つのプロファイルを用意している。
**トレーサビリティの考え方、変更波及の仕組み、ライフサイクルフェーズは
すべてのプロファイルで共通。** 異なるのはドキュメント階層の深さだけ。

### lite — 小規模開発

```
REQ（要件: What）
└── SPEC（仕様: How — 基本設計＋詳細設計を兼ねる）
    ├── IMPL（実装: Build）
    └── TST（テスト: Verify）

ADR（決定: Why）── 独立文書。任意のアイテムにリンク可能
```

適用場面: 単体ライブラリ、個人開発、プロトタイプ。
SPECがコンポーネント設計とモジュール設計の両方を担う。

### standard — 中規模開発

```
REQ（要件: What）
└── ARCH（基本設計: Architecture — コンポーネント分割、IF定義）
    └── SPEC（詳細設計: Detail — API仕様、アルゴリズム）
        ├── IMPL（実装: Build）
        └── TST（テスト: Verify）

ADR（決定: Why）── 独立文書。REQ/ARCH/SPEC/IMPL いずれにもリンク可能
```

適用場面: 複数サブシステム、チーム開発。
設計レビューを段階的に行いたい場合に有効。

### full — 大規模開発（V字モデル準拠）

```
REQ（要件: What）
└── HLD（基本設計: High-Level Design）
    └── LLD（詳細設計: Low-Level Design）
        ├── IMPL（実装: Build）
        └── TST（テスト: Verify）

ADR（決定: Why）── 独立文書。あらゆるレベルの意思決定を記録
```

適用場面: 規制産業（医療、航空宇宙、金融）、多チーム開発。
V字モデルの各レベルに対応するテストレベルを明確に定義する。

### V字モデルとの対応

```
要件定義 (REQ)  ─────────────────  受入テスト (acceptance)
   基本設計 (ARCH/HLD) ──────── 結合テスト (integration)
      詳細設計 (SPEC/LLD) ── 単体テスト (unit)
         実装 (IMPL)
```

| V字レベル | lite | standard | full |
|---|---|---|---|
| 要件定義 | REQ | REQ | REQ |
| 基本設計 | SPEC（兼任） | ARCH | HLD |
| 詳細設計 | SPEC（兼任） | SPEC | LLD |
| 実装 | IMPL | IMPL | IMPL |
| 単体テスト | TST | TST (test_level=unit) | TST (test_level=unit) |
| 結合テスト | TST | TST (test_level=integration) | TST (test_level=integration) |
| 受入テスト | TST | TST (test_level=acceptance) | TST (test_level=acceptance) |

## 各ドキュメントの役割

### REQ — 要件（What: 何を実現するか）

全プロファイル共通。ビジネス要件・ユーザーストーリー・機能要件を定義する。
技術的な実現方法には言及しない。

属性:
- `text`: 「〜できること」形式の要件文
- `header`: 要件の短い名称
- `groups`: 機能グループのリスト（`[AUTH, PAY]` 等）
- `priority`: 優先度（`critical` / `high` / `medium` / `low` / `none` / `done`）。デフォルト `medium`
- `level`: ドキュメント内の階層

### ARCH — 基本設計（standardプロファイル）

コンポーネント分割、コンポーネント間インターフェース、データフロー、
技術選定、非機能要件の設計方針を定義する。

属性:
- `text`: アーキテクチャの記述（Mermaid図推奨）
- `groups`: 機能グループのリスト（REQと同じグループ名）
- `links`: 対応するREQアイテムへのリンク（必須）

書き方の基準:
- 「どう構成するか」に焦点を当てる
- コンポーネント間の責務境界とインターフェースを明確にする
- 技術選定理由を記述する
- 非機能要件の具体的な目標値を定義する

### HLD — 基本設計（fullプロファイル）

ARCHと同等の役割だが、V字モデルの用語に合わせてHLD（High-Level Design）と呼称する。
結合テスト（integration test）に対応する設計レベル。

### SPEC — 仕様/詳細設計

liteプロファイルでは基本設計と詳細設計を兼ねる。
standardプロファイルではARCHの下位として詳細設計を担う。

属性:
- `text`: 技術仕様（APIシグネチャ、アルゴリズム、制約）
- `groups`: 機能グループのリスト
- `links`: 対応するREQ（lite）またはARCH（standard）へのリンク（必須）

### LLD — 詳細設計（fullプロファイル）

SPECと同等の役割だが、V字モデルの用語に合わせてLLD（Low-Level Design）と呼称する。
単体テスト（unit test）に対応する設計レベル。

属性:
- `text`: モジュール内部設計（APIシグネチャ、アルゴリズム、クラス設計）
- `groups`: 機能グループのリスト
- `links`: 対応するHLDアイテムへのリンク（必須）

### 派生要求（derived 属性）

派生要求の定義、仕様、および運用ルールについては、
`doorstop_reference.md` の「派生要求」セクションを参照。

### IMPL — 実装（Build: 何を作ったか）

全プロファイル共通。最下位設計文書に対応する実装成果物（ソースコード）を追跡する。

属性:
- `text`: 実装の概要説明
- `groups`: 機能グループのリスト
- `links`: 最下位設計文書へのリンク（必須）
- `references`: 外部ファイルへの紐付け（辞書型リスト）

紐付け基準:
- ドメインロジックの実装ファイルのみに厳選する
- `conftest.py`, `__init__.py`, 共通ユーティリティは含めない
- 1アイテムあたり最大2–3ファイル
- 影響範囲の広い共通ファイルを紐付けると「レビュー疲れ」を引き起こすため避ける

### TST — テスト（Verify: どう検証するか）

全プロファイル共通。最下位設計文書に対する検証手順・期待結果を定義する。

属性:
- `text`: テスト手順と期待結果の説明
- `groups`: 機能グループのリスト
- `links`: 最下位設計文書へのリンク（必須）
- `references`: テストコードへの紐付け（辞書型リスト）
- `test_level`: テスト粒度（standard/fullのみ。`unit` / `integration` / `acceptance`）

## トレーサビリティの流れ

全アイテムのリンクは **子 → 親** 方向で張る。

### liteプロファイル

```
REQ001 [AUTH] ← SPEC001 [AUTH] ← IMPL001 [AUTH]
                                ← TST001  [AUTH]

ADR001 ── REQ001 / SPEC001 等にリンク（独立）
```

### standardプロファイル

```
REQ001 [AUTH] ← ARCH001 [AUTH] ← SPEC001 [AUTH] ← IMPL001 [AUTH]
                                                 ← TST001  [AUTH]

ADR001 ── REQ001 / ARCH001 / SPEC001 等にリンク（独立）
```

### fullプロファイル

```
REQ001 [AUTH] ← HLD001 [AUTH] ← LLD001 [AUTH] ← IMPL001 [AUTH]
                                               ← TST001  [AUTH]

ADR001 ── REQ001 / HLD001 / LLD001 等にリンク（独立）
```

ADR は主チェーン（REQ→設計→IMPL/TST）の外側に位置し、
あらゆるレベルの意思決定を独立して記録する。
ADR の `links` は決定の文脈を示すために使い、
他のアイテムから ADR へのリンクは判断の根拠参照として使う。

これにより以下の問いに答えられる:

| 問い | 追跡方向 |
|------|----------|
| この要件はどう実装されている？ | REQ → 設計 → IMPL |
| このコードはなぜ存在する？ | IMPL → 設計 → REQ |
| この仕様はテストされている？ | 設計 → TST |
| このテストは何を検証している？ | TST → 設計 → REQ |
| この要件は検証済みか？ | REQ → 設計 → TST（結果確認） |
| なぜこの判断をしたか？ | 任意のアイテム → ADR |
| この判断は何に影響しているか？ | ADR → links 先アイテム |

## ライフサイクルフェーズ概要

以下のフェーズは **全プロファイルで共通**。
設計フェーズの粒度だけがプロファイルによって異なる。

| Phase | 名称 | 入力 | 成果 |
|---|---|---|---|
| 1 | 要件定義 | ユーザーストーリー、ビジネス要件 | REQ/NFRドキュメント + 用語辞書更新 |
| 1.5 | トリアージ | REQ/NFR全量 | 優先度付きバックログ、スコープ合意 |
| 2 | 設計策定 | REQドキュメント | 設計ドキュメント（gherkin 付き）+ ADR（該当時） |
| 3 | テスト設計 | 設計ドキュメント（gherkin） | TSTドキュメント（gherkin シナリオ → テストケース） |
| 4 | 実装 | 設計ドキュメント | IMPL + ソースコード |
| 5 | 検証 | 全ドキュメント + コード | レポート + テスト結果 |
| 6 | レビュー | 検証済みドキュメント | reviewed状態クリア + ベースライン |
| 7 | 変更影響分析 | 変更アイテム | 影響範囲 + アクションリスト |

Phase 3とPhase 4は並行して進めてよい。Phase 7はどのフェーズでも発生しうる。

```
Phase 1 → Phase 1.5 → Phase 2 → Phase 3/4（並行可）→ Phase 5 → Phase 6
  │                      │                                ↑
  用語辞書               ADR     Phase 7（変更発生時に随時）──┘
```

## 変更影響分析（Impact Analysis）

仕様や要件の変更は、下流のアイテム（実装・テスト）に波及する。
Doorstop の組み込みメカニズム（suspect検出）と専用スクリプトで変更を追跡する。

### suspect メカニズム

各リンクにはリンク時点の親アイテムのフィンガープリント（SHA256）が記録されている。
親アイテムが変更されるとフィンガープリントが不一致となり、リンクが suspect 状態になる。

```
SPEC001 変更前 → stamp: abc123
  IMPL001 link: SPEC001:abc123  ← 一致 → 正常
  TST001  link: SPEC001:abc123  ← 一致 → 正常

SPEC001 変更後 → stamp: xyz789
  IMPL001 link: SPEC001:abc123  ← 不一致 → suspect
  TST001  link: SPEC001:abc123  ← 不一致 → suspect
```

設計層が複数ある場合、上位の変更は全下位層に波及する:

```
standard: ARCH変更 → SPEC suspect → IMPL/TST suspect
full:     HLD変更  → LLD suspect  → IMPL/TST suspect
```

### 3つの検出方式

| 方式 | コマンド | 用途 |
|---|---|---|
| suspect自動検出 | `impact_analysis.py --detect-suspects` | 日常の整合性チェック |
| Git diff検出 | `impact_analysis.py --from-git [--base main]` | PR単位の影響分析 |
| 手動指定 | `impact_analysis.py --changed <UID>` | 変更前のシミュレーション |

### 影響範囲のトレース

変更アイテムを起点に、リンクを双方向にたどる:

```
上流追跡（なぜ変わった？）       下流追跡（何に影響する？）
  REQ001 ← SPEC001 変更 → IMPL001 suspect
                          → TST001  suspect
```

上流追跡は変更の根本原因を把握するため、
下流追跡は修正が必要なコード・テストを特定するために行う。

### suspect解消のワークフロー

1. `impact_analysis.py` で影響範囲を特定
2. 影響を受けるIMPL/TSTの `references` 先（ソースコード/テストコード）を修正
3. `doorstop_ops.py chain-review <UID>` で関連アイテムのsuspect解消＆レビュー済みに一括更新
4. `validate_and_report.py` で全体の整合性を再確認

## ベースライン管理

全アイテムが `reviewed` 状態となり suspect が解消された段階で、
仕様のベースラインを記録する。ベースラインは「この時点の合意済み仕様」を示す基準点であり、
後から何が変わったかを追跡するための参照点になる。

```bash
baseline_manager.py <dir> create v1.0 --tag
baseline_manager.py <dir> list
baseline_manager.py <dir> diff v1.0 v2.0
baseline_manager.py <dir> diff v1.0 HEAD
```

**diff の出力内容:**
- `added`: 新しく追加されたアイテム
- `removed`: 非活性化されたアイテム
- `changed`: フィンガープリント（stamp）が変化したアイテム（テキスト変更等）
- `unchanged`: 変更なし

**ロールバック:**
仕様変更の取り消しは `git revert` に委ねる。`baseline_manager.py diff` で
変更範囲を特定してから revert の対象コミットを特定すること。

## 健全性指標

validate_and_report.py が出力するメトリクス:

| 指標 | 説明 | 目標値 |
|------|------|--------|
| 設計 → REQ カバレッジ | 設計文書がカバーするREQの割合 | 100% |
| IMPL → 設計カバレッジ | IMPLがカバーする最下位設計の割合 | 100% |
| TST → 設計カバレッジ | TSTがカバーする最下位設計の割合 | 100% |
| 孤立REQ | 設計文書からリンクされていないREQ | 0件 |
| 孤立設計 | IMPL/TSTどちらからもリンクされていない最下位設計 | 0件 |
| suspectリンク | 親アイテム変更後に未解消のリンク数 | 0件 |
| 未レビューアイテム | reviewed未クリアのアイテム数 | 0件（目標） |
| クロスグループリンク | 異なるグループ間のリンク数 | 少ないほど良い |

standard/fullプロファイルでは設計層間のカバレッジも追加で計測:

| 指標（standard） | 説明 |
|---|---|
| SPEC → ARCH カバレッジ | SPECがカバーするARCHの割合 |

| 指標（full） | 説明 |
|---|---|
| LLD → HLD カバレッジ | LLDがカバーするHLDの割合 |

これらのメトリクスはグループ別にも集計される。
