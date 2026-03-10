# Dev-Lifecycle: 仕様駆動開発ライフサイクル

仕様を起点とし、要件→設計→実装→テストの全工程を
Doorstopのトレーサビリティで一貫管理するライフサイクル定義。

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
- `group`: 機能グループ（AUTH, PAY 等）
- `level`: ドキュメント内の階層

例:
```
REQ001 [AUTH] ユーザーはパスワードでシステムにログインできること。
REQ002 [AUTH] ログインに5回失敗したアカウントは30分間ロックされること。
```

### ARCH — 基本設計（standardプロファイル）

コンポーネント分割、コンポーネント間インターフェース、データフロー、
技術選定、非機能要件の設計方針を定義する。

属性:
- `text`: アーキテクチャの記述（Mermaid図推奨）
- `group`: 機能グループ（REQと同じグループ名）
- `links`: 対応するREQアイテムへのリンク（必須）

書き方の基準:
- 「どう構成するか」に焦点を当てる
- コンポーネント間の責務境界とインターフェースを明確にする
- 技術選定理由を記述する
- 非機能要件の具体的な目標値を定義する

例:
```
ARCH001 [AUTH] → REQ001
  認証サブシステムはJWTベースのトークン認証を採用する。
  トークン発行APIとトークン検証ミドルウェアの2コンポーネントで構成する。
```

### HLD — 基本設計（fullプロファイル）

ARCHと同等の役割だが、V字モデルの用語に合わせてHLD（High-Level Design）と呼称する。
結合テスト（integration test）に対応する設計レベル。

### SPEC — 仕様/詳細設計

liteプロファイルでは基本設計と詳細設計を兼ねる。
standardプロファイルではARCHの下位として詳細設計を担う。

属性:
- `text`: 技術仕様（APIシグネチャ、アルゴリズム、制約）
- `group`: 機能グループ
- `links`: 対応するREQ（lite）またはARCH（standard）へのリンク（必須）

例:
```
SPEC001 [AUTH] → ARCH001 (standard) / → REQ001 (lite)
  パスワードはArgon2idでハッシュ化して保存する。
  メモリ: 64MB、反復: 3回、並列度: 1。
```

### LLD — 詳細設計（fullプロファイル）

SPECと同等の役割だが、V字モデルの用語に合わせてLLD（Low-Level Design）と呼称する。
単体テスト（unit test）に対応する設計レベル。

属性:
- `text`: モジュール内部設計（APIシグネチャ、アルゴリズム、クラス設計）
- `group`: 機能グループ
- `links`: 対応するHLDアイテムへのリンク（必須）

### 派生要求（derived 属性）

設計策定中に、REQからの直接ブレイクダウンではなく、アーキテクチャの選択や
技術的制約から論理的に導き出された要求が生じることがある。これを「派生要求」として管理する。

仕様:
- `derived: true` を設定すると、`links` が空でもトレーサビリティ検証をパスする
- `derived` の値変更はフィンガープリントに影響しない（再レビュー不要）

運用ルール:
- **使用可能な層**: ARCH / SPEC / HLD / LLD（設計層のみ）
- **IMPL/TST での使用は禁止** — IMPL/TST は常に最下位設計文書にリンクすべき
- **必須記述**: `text` 内に「派生要求の根拠」セクションを設け、なぜその制約が生じたか明記
- **避けるべき運用**: 親リンク整理が面倒という理由での逃げ道として使ってはならない

例:
```
SPEC024 [SERIAL] (derived)
  派生要求の根拠: MsgpackSerializerのext type制約（0–127）により、
  カスタム型の登録上限は128種に制限される。
  → 派生元: SPEC003（シリアライザ仕様の技術選定）
```

### IMPL — 実装（Build: 何を作ったか）

全プロファイル共通。最下位設計文書に対応する実装成果物（ソースコード）を追跡する。

属性:
- `text`: 実装の概要説明
- `group`: 機能グループ
- `links`: 最下位設計文書へのリンク（必須）
- `references`: 外部ファイルへの紐付け（辞書型リスト）

`references` の記述:
```yaml
references:
  - path: src/auth/password.py
    type: file
```

紐付け基準:
- ドメインロジックの実装ファイルのみに厳選する
- `conftest.py`, `__init__.py`, 共通ユーティリティは含めない
- 1アイテムあたり最大2–3ファイル
- 影響範囲の広い共通ファイルを紐付けると「レビュー疲れ」を引き起こすため避ける

### TST — テスト（Verify: どう検証するか）

全プロファイル共通。最下位設計文書に対する検証手順・期待結果を定義する。

属性:
- `text`: テスト手順と期待結果の説明
- `group`: 機能グループ
- `links`: 最下位設計文書へのリンク（必須）
- `references`: テストコードへの紐付け（辞書型リスト）
- `test_level`: テスト粒度（standard/fullのみ。`unit` / `integration` / `acceptance`）

## トレーサビリティの流れ

全アイテムのリンクは **子 → 親** 方向で張る。

### liteプロファイル

```
REQ001 [AUTH] ← SPEC001 [AUTH] ← IMPL001 [AUTH]
                                ← TST001  [AUTH]
```

### standardプロファイル

```
REQ001 [AUTH] ← ARCH001 [AUTH] ← SPEC001 [AUTH] ← IMPL001 [AUTH]
                                                 ← TST001  [AUTH]
```

### fullプロファイル

```
REQ001 [AUTH] ← HLD001 [AUTH] ← LLD001 [AUTH] ← IMPL001 [AUTH]
                                               ← TST001  [AUTH]
```

これにより以下の問いに答えられる:

| 問い | 追跡方向 |
|------|----------|
| この要件はどう実装されている？ | REQ → 設計 → IMPL |
| このコードはなぜ存在する？ | IMPL → 設計 → REQ |
| この仕様はテストされている？ | 設計 → TST |
| このテストは何を検証している？ | TST → 設計 → REQ |
| この要件は検証済みか？ | REQ → 設計 → TST（結果確認） |

## ライフサイクルフェーズ

以下のフェーズは **全プロファイルで共通**。
設計フェーズの粒度だけがプロファイルによって異なる。

### Phase 1: 要件定義

```
入力: ユーザーストーリー、ビジネス要件、ステークホルダー要望
成果: REQドキュメント
```

1. 機能グループを定義する（AUTH, PAY, ...）
2. 各グループごとにREQアイテムを作成する
3. 要件テキストを検証可能な形式で記述する
4. REQドキュメント内でレベル構造を整理する

完了基準: 全REQアイテムにテキストとグループが設定されていること。

### Phase 2: 設計策定

```
入力: REQドキュメント
成果: 設計ドキュメント（プロファイルに応じた層数）
```

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

完了基準: 全REQが設計文書にカバーされ、全リンクが張られていること。

### Phase 3: テスト設計

```
入力: 設計ドキュメント
成果: TSTドキュメント（全TST → 最下位設計文書リンク済み）
```

1. 各最下位設計アイテムに対して1つ以上のTSTを作成する
2. テスト手順と期待結果を記述する
3. TST → 最下位設計文書のリンクを張る
4. テストコードのファイルパスを `references` に設定する（スタブでも可）
5. standard/fullでは `test_level` を設定する

完了基準: 全最下位設計アイテムが少なくとも1つのTSTにカバーされていること。

### Phase 4: 実装

```
入力: 設計ドキュメント
成果: IMPLドキュメント + ソースコード（全IMPL → 最下位設計文書リンク済み）
```

1. 最下位設計文書に従ってコードを実装する
2. 各実装単位に対してIMPLアイテムを作成する
3. IMPL → 最下位設計文書のリンクを張る
4. `references` にソースコードのパスを設定する

Phase 3とPhase 4は並行して進めてよい。
編集の順序としては仕様、実装、テストのいずれから着手しても最終的に整合していれば問題ない。
ただし、実装をパスさせるためにテストを歪めることがあってはならない。
**Gitへのコミットは仕様(設計) → テスト → 実装 の順に行うこと**を強く推奨する。これにより、履歴上にテストファーストの思想と整合性の取れた状態を残すことができる。

完了基準: 全最下位設計アイテムが少なくとも1つのIMPLにカバーされていること。

### コミット粒度規約

ダッシュボードはアイテムごとにgitの作成日・更新日・作成者・コミットハッシュを
表示する。コミットの粒度がアイテムの変更履歴としての意味を持つため、
仕様駆動ライフサイクル内のコミットは **ドキュメント層の変更単位** で分ける。

#### 基本ルール

```
1コミット = 1つのドキュメント層の変更
```

典型的なフローでの推奨コミット分割:

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

#### まとめてよいケース

- 同一層の複数アイテムを同時に変更（例: SPEC001〜003を一括修正）
- IMPL + TST を同一コミット（実装とテストは密結合のため許容）
- 開発途中のWIPコミット（最終的には整理を推奨）
- ツール・CI設定など仕様アイテムに関係しない変更

#### なぜ分けるのか

1. **アイテム単位の変更追跡**: `updated_at` と `updated_commit` が
   そのアイテム固有の変更を指す
2. **影響分析との整合**: `impact_analysis.py --from-git` がコミット単位で
   変更を検出するため、層ごとに分かれていると因果関係が明確になる
3. **レビュー効率**: 設計変更と実装変更が分離されていると
   レビュアーが段階的に確認できる

#### コミットメッセージ

```
<type>: <summary>

type:
  spec:  REQ/SPEC/ARCH/HLD/LLD のYML変更
  impl:  IMPL + ソースコード
  test:  TST + テストコード
  fix:   バグ修正（実装バグ）
  tool:  スキルスクリプト・CI・ツール変更
```

アイテムUIDをメッセージに含めると、`git log` からアイテムの変更履歴を追跡しやすい。

### Phase 5: 検証

```
入力: 全ドキュメント + ソースコード + テストコード
成果: トレーサビリティレポート + テスト結果
```

静的検証（Doorstop）:
- `doorstop` でツリー全体のバリデーション
- `validate_and_report.py --strict` で全リンクの完全性チェック
- グループ別カバレッジが全て100%であること

動的検証（テスト実行）:
- TSTアイテムの `references` が指すテストコードを実行する
- テスト結果をTSTアイテムのカスタム属性 `test_status` に記録する（pass/fail/skip）

完了基準: 静的検証エラー0件、テスト全件パス。

### Phase 6: レビュー

```
入力: 全ドキュメント（検証済み）
成果: 全アイテムのreviewed状態がクリア
```

Doorstopの `reviewed` 属性とベースライン管理:
- アイテムの内容が変更されると `reviewed` がリセットされ、下流のリンクがsuspect（要再確認）状態になる
- 関連アイテムとの整合性や編集内容を確認した上で、`doorstop_ops.py chain-review <UID>` を実行し、アイテムチェーン全体を一括でsuspect解消＆レビュー済みにする（単に義務的にクリアするのではなく、実質的な確認を伴うこと）
- **ベースラインの確定**: 全てのアイテムが `reviewed` 状態となり、suspectが解消された段階で仕様のベースラインが揃ったと見なし、Gitでタグを打つ（例: `git tag -a v1.0.0-spec` 等）

レビュー対象:
- 新規・変更されたREQアイテム → 要件レビュー
- 新規・変更された設計アイテム（ARCH/SPEC/HLD/LLD）→ 設計レビュー
- 新規・変更されたIMPLアイテム → コードレビュー（通常のPRレビューと統合）
- 新規・変更されたTSTアイテム → テストレビュー

### Phase 7: 変更影響分析（Impact Analysis）

```
入力: 変更されたアイテム（設計修正、REQ追加・変更など）
成果: 影響範囲レポート + 対応アクションリスト + suspect解消
```

仕様や要件の変更は、下流のアイテム（実装・テスト）に波及する。
このフェーズでは変更の影響範囲を特定し、必要な修正を追跡する。

設計層が複数ある場合、上位の変更は全下位層に波及する:
```
standard: ARCH変更 → SPEC suspect → IMPL/TST suspect
full:     HLD変更  → LLD suspect  → IMPL/TST suspect
```

`scripts/impact_analysis.py` が3つの方式で変更を検出する:

**方式1: suspect自動検出 (`--detect-suspects`)**

Doorstopの組み込みメカニズムを利用する。各リンクにはリンク時点の
親アイテムのフィンガープリント（SHA256）が記録されており、親アイテムが
変更されるとフィンガープリントが不一致となり、リンクがsuspect状態になる。

```
SPEC001 変更前 → stamp: abc123
  IMPL001 link: SPEC001:abc123  ← 一致 → 正常
  TST001  link: SPEC001:abc123  ← 一致 → 正常

SPEC001 変更後 → stamp: xyz789
  IMPL001 link: SPEC001:abc123  ← 不一致 → ⚠ suspect
  TST001  link: SPEC001:abc123  ← 不一致 → ⚠ suspect
```

**方式2: Git diff検出 (`--from-git`)**

Gitの差分からDoorstopのYAMLファイルの変更を検出する。
PR単位で影響分析を実行する場合に有効。

```bash
# mainブランチとの差分から検出
uv run python impact_analysis.py . --from-git --base main

# 直前のコミットからの差分
uv run python impact_analysis.py . --from-git
```

**方式3: 手動指定 (`--changed UID`)**

変更予定のアイテムを事前に指定し、影響範囲を予測する。
変更前のシミュレーションとして使える。

```bash
uv run python impact_analysis.py . --changed SPEC001 SPEC003
```

**影響範囲のトレース**

変更アイテムを起点に、リンクを双方向にたどる:

```
上流追跡（なぜ変わった？）       下流追跡（何に影響する？）
  REQ001 ← SPEC001 変更 → IMPL001 ⚠ suspect
                          → TST001  ⚠ suspect
```

上流追跡は変更の根本原因（要件変更の影響か、仕様自体の改善か）を把握するため、
下流追跡は修正が必要なコード・テストを特定するために行う。

**suspect解消のワークフロー**

```
1. impact_analysis.py で影響範囲を特定
2. 影響を受けるIMPL/TSTのreferences先（ソースコード/テストコード）を修正
3. doorstop_ops.py chain-review <UID> で関連アイテムのsuspect解消＆レビュー済みに一括更新
4. validate_and_report.py で全体の整合性を再確認
```

このフェーズはPhase 1〜6のどの段階でも発生しうる。
変更が発生したら即座にPhase 7を実行し、影響を把握してから
修正→検証→レビューのサイクルに戻る。

## CI連携の概念

CIパイプラインに以下のチェックを組み込むことを推奨する
（具体的なCI設定はプロジェクトごとに別途定義）:

### PRゲート（推奨チェック）

1. **doorstop validate**: ツリーの構造整合性チェック
2. **traceability check**: 新規/変更された設計/IMPL/TSTに対するリンク漏れ検出
3. **references check**: IMPL/TSTの `references` が指すファイルが実在するか検証
4. **impact analysis**: `impact_analysis.py --from-git --base main` で変更影響を表示
5. **test execution**: TSTの `ref` が指すテストを実行

### リリースゲート（推奨チェック）

1. **coverage check**: 全ドキュメントペアのカバレッジ100%
2. **suspect check**: `impact_analysis.py --detect-suspects` でsuspectが0件
3. **review check**: 未レビューアイテムの一覧表示（警告のみ、ブロックしない）
4. **report generation**: トレーサビリティレポートの自動生成・アーカイブ

### チェックの厳密度

| チェック | PRゲート | リリースゲート |
|----------|----------|----------------|
| doorstop validate | ブロック | ブロック |
| リンク漏れ | ブロック | ブロック |
| references存在チェック | 警告 | ブロック |
| derived根拠チェック | 警告 | ブロック |
| カバレッジ100% | 警告 | ブロック |
| テスト全件パス | ブロック | ブロック |
| suspect 0件 | 警告 | ブロック |
| 未レビューアイテム | 表示のみ | 警告 |

## フェーズ間の成果物と依存関係

```
Phase 1        Phase 2              Phase 3        Phase 4        Phase 5       Phase 6
要件定義  ───→  設計策定        ──┬→  テスト設計  ──→  検証     ───→  レビュー
  │              │                │                    ↑               │
  REQ            設計文書          └→  実装       ──────┘              reviewed
                 (SPEC|ARCH+SPEC       │                              クリア
                  |HLD+LLD)            IMPL
                  │                    references → src/...
                  └── TST
                      references → tests/...

                        Phase 7: 変更影響分析
                        ────────────────────
                        どのフェーズでも変更が発生したら即座に実行
                        suspect検出 → 影響トレース → 修正 → clear → review
                        → Phase 5（検証）に戻る
```

## ドキュメント間の健全性指標

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

## エージェント駆動モード

自律型コーディングエージェント（Claude Code等）がこのライフサイクルを
自動実行する場合の運用モデル。

### 役割分担

```
ユーザー（人間）           エージェント
─────────────────         ─────────────────────────────────
「ログイン機能を作って」   → REQ/設計策定 → 実装 → テスト
                          → IMPL/TST登録 → リンク → 検証
                          → 結果を簡潔に報告

「ハッシュをbcryptに変えて」→ 影響分析 → 設計修正 → 実装修正
                          → テスト修正 → suspect解消 → 検証
                          → 影響範囲と結果を報告

「出荷できる？」          → リリースゲート全チェック
                          → 結果を報告
```

### エージェント用ツール

`scripts/doorstop_ops.py` はエージェントが1コマンドでDoorstopを操作するためのツール。
すべてのコマンドはJSON形式で結果を返す。

```bash
# アイテム追加（リンク付き）
uv run python doorstop_ops.py . add -d SPEC -t "仕様文" -g AUTH,PAY --links REQ001

# アイテム更新
uv run python doorstop_ops.py . update SPEC001 -t "新しい仕様文"

# suspect解消
uv run python doorstop_ops.py . clear IMPL001 TST001

# 状況確認
uv run python doorstop_ops.py . list -d SPEC -g AUTH,PAY
uv run python doorstop_ops.py . groups
uv run python doorstop_ops.py . tree
```

### エージェントの判断フロー

```
ユーザーの発話
  │
  ├─ 新機能 → REQ作成 → 設計策定（上位から順に） → 実装 → IMPL登録
  │           → テスト → TST登録 → 検証 → 報告
  │
  ├─ 変更   → 影響分析 → 設計修正（上位から順に） → 実装修正 → IMPL更新
  │           → テスト修正 → TST更新 → clear → 検証 → 報告
  │
  ├─ バグ   → 原因特定（仕様バグ or 実装バグ）
  │           → 仕様バグ: 変更フローへ
  │           → 実装バグ: コード修正 → テスト追加 → 検証 → 報告
  │
  └─ 確認   → レポート生成 → 平易な言葉で報告
```

### ユーザーへの報告規約

エージェントはDoorstopの内部構造をユーザーに見せない。
報告は「何を作った/直した」「どのファイルが変わった」「テストは通ったか」に絞る。

```
✅ [AUTH] ログイン機能を実装しました。
  - src/auth/login.py — ログイン処理
  - tests/test_auth.py — テスト3件（全件パス）
  - トレーサビリティ: 全リンク済み、カバレッジ100%
```
