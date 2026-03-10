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
- `groups`: 機能グループのリスト（`[AUTH, PAY]` 等）
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
- `groups`: 機能グループのリスト（REQと同じグループ名）
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
- `groups`: 機能グループのリスト
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
- `groups`: 機能グループのリスト
- `links`: 対応するHLDアイテムへのリンク（必須）

### 派生要求（derived 属性）

派生要求の定義、仕様、および運用ルールについては、[Doorstop リファレンス](./doorstop_reference.md#派生要求derived-属性) を参照してください。

### IMPL — 実装（Build: 何を作ったか）

全プロファイル共通。最下位設計文書に対応する実装成果物（ソースコード）を追跡する。

属性:
- `text`: 実装の概要説明
- `groups`: 機能グループのリスト
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
成果: REQドキュメント（+ NFRドキュメント：standard/full推奨）
```

1. 機能グループを定義する（AUTH, PAY, ...）
2. 各グループごとにREQアイテムを作成し、`priority` を設定する
3. 要件テキストを検証可能な形式で記述する
4. REQドキュメント内でレベル構造を整理する
5. 非機能要件（NFR）がある場合: standard/fullでは NFR ドキュメントに追加する

#### NFRドキュメントの利用（standard/fullプロファイル）

NFR（Non-Functional Requirements）は機能要件（REQ）と並列のルートドキュメントとして管理する。
REQ が「何をするか」を定義するのに対し、NFR は「どの品質水準で実現するか」を定義する。

```bash
# NFR ドキュメント付きで初期化
init_project.py <dir> --profile standard --with-nfr

# NFR アイテムの追加
doorstop_ops.py <dir> add -d NFR -t "全APIの応答時間はp99で200ms以内とする" -g PERF --priority high
doorstop_ops.py <dir> add -d NFR -t "パスワードはArgon2idで保存すること" -g SEC --priority critical
```

NFRのトレーサビリティ:
- 設計文書（ARCH/SPEC/HLD）は NFR アイテムへリンクして非機能制約の実現方針を明示する
- TST は NFR アイテムへリンクして非機能テスト（性能・セキュリティ）を対応付ける
- liteプロファイルでは `groups: [NFR, PERF]` 等で REQ に混在させる

NFR の典型グループ: `PERF`（性能）、`SEC`（セキュリティ）、`REL`（信頼性）、
`MNT`（保守性）、`PRT`（可搬性）、`SAF`（安全性、規制産業）

完了基準: 全REQ/NFRアイテムにテキスト・グループ・priorityが設定されていること。

---

### Phase 1.5: トリアージ（優先付け・スコープ確定）

```
入力: REQ/NFRドキュメント（全量登録済み）
成果: 優先度付きバックログ、今回の開発スコープの合意
```

Phase 1 で洗い出した要件全量に対し、設計着手前に優先度を確定し、
開発チーム・ユーザーと合意する。一度に全要件を実装する必要はない。
priorityの高いものから順に設計・実装フェーズへ流すことで、
価値の高い機能から早期に提供できる。

#### 手順

1. **バックログ確認** — `trace_query.py <dir> backlog` で REQ を優先度順に一覧表示
2. **未着手 REQ の特定** — カバレッジ0（設計・実装が未作成）の REQ を抽出
3. **優先度の調整** — ユーザーとの合意に基づき `--priority` を更新
4. **スコープ確定** — 今回の開発サイクルで対応する REQ を明確にする
5. **ベースライン作成** — 合意済みスコープのベースラインを記録する

```bash
# 優先度付きバックログ表示
trace_query.py <dir> backlog
trace_query.py <dir> backlog --group AUTH
trace_query.py <dir> backlog -d NFR      # 非機能要件のバックログ

# 優先度を更新
doorstop_ops.py <dir> update REQ001 --priority critical
doorstop_ops.py <dir> update REQ005 --priority low

# 今回対応しない要件は active のまま priority: low で管理（非活性化はしない）
# スコープ合意後にベースライン作成
baseline_manager.py <dir> create scope-v1 --tag
```

#### 優先度の値

| 値 | 意味 | 典型的な使用場面 |
|---|---|---|
| `critical` | 今すぐ必要。これがないとリリースできない | セキュリティ、コアとなる機能 |
| `high` | 今回のリリースに含めたい | 主要機能、ユーザーが期待する機能 |
| `medium` | できれば今回、次回でも可（デフォルト） | 拡張機能、利便性向上 |
| `low` | 将来対応。今回はスコープ外 | Nice-to-have、実験的機能 |

完了基準: 全アクティブREQ/NFRに priority が設定され、今回の対象スコープが合意されていること。

---

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

Doorstopの `reviewed` 属性:
- アイテムの内容が変更されると `reviewed` がリセットされ、下流のリンクがsuspect（要再確認）状態になる
- 関連アイテムとの整合性や編集内容を確認した上で、`doorstop_ops.py chain-review <UID>` を実行し、アイテムチェーン全体を一括でsuspect解消＆レビュー済みにする（単に義務的にクリアするのではなく、実質的な確認を伴うこと）

レビュー対象:
- 新規・変更されたREQアイテム → 要件レビュー
- 新規・変更された設計アイテム（ARCH/SPEC/HLD/LLD）→ 設計レビュー
- 新規・変更されたIMPLアイテム → コードレビュー（通常のPRレビューと統合）
- 新規・変更されたTSTアイテム → テストレビュー

#### ベースライン管理

全アイテムが `reviewed` 状態となり suspect が解消された段階で、
仕様のベースラインを記録する。ベースラインは「この時点の合意済み仕様」を示す基準点であり、
後から何が変わったかを追跡するための参照点になる。

```bash
# ベースライン作成（Git タグも付ける）
baseline_manager.py <dir> create v1.0 --tag
baseline_manager.py <dir> create v1.0 --tag --tag-name v1.0.0-spec

# ベースライン一覧
baseline_manager.py <dir> list

# バージョン間の差分（v1.0 から v2.0 で何が変わったか）
baseline_manager.py <dir> diff v1.0 v2.0

# 現在の状態と最後のベースラインの差分（未記録の変更を確認）
baseline_manager.py <dir> diff v1.0 HEAD
```

**diff の出力内容:**
- `added`: 新しく追加されたアイテム
- `removed`: 非活性化されたアイテム
- `changed`: フィンガープリント（stamp）が変化したアイテム（テキスト変更等）
- `unchanged`: 変更なし

**ロールバックについて:**
仕様変更の取り消しは `git revert` に委ねる。`baseline_manager.py diff` で
変更範囲を特定してから revert の対象コミットを特定すること。

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
  ├─ 優先付け・整理 → バックログ確認 → 優先度更新 → ベースライン作成
  │
  ├─ 新機能 → REQ作成（priority設定）→ 設計策定（上位から順に）→ 実装 → IMPL登録
  │           → テスト → TST登録 → 検証 → ベースライン更新（リリース時）→ 報告
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


## [T] トリアージフロー（優先付け・スコープ確定）

ユーザーが「何を先に作るか決めたい」「バックログを整理したい」等と発話したとき。
詳細は Phase 1.5 を参照。

1. **バックログ確認** — `trace_query.py <dir> backlog` で REQ を優先度順に一覧
2. **優先度設定** — `doorstop_ops.py <dir> update REQ001 --priority high`
3. **未着手の特定** — 設計・実装が未作成の REQ を特定し、ユーザーへ提示
4. **ベースライン確認** — `baseline_manager.py <dir> list` で現在の基準点を確認
5. **スコープ合意後のベースライン作成** — `baseline_manager.py <dir> create <name>`

## [A] 新規開発フロー

1. **理解** — ユーザーの要望を要件文に変換する。曖昧な場合のみ確認
2. **分類** — 機能グループと優先度を決定（既存グループ or 新規、`--priority` を設定）
3. **REQ登録** — `doorstop_ops.py add -d REQ -t "要件文" -g GROUP --priority high`
4. **設計策定** — 設計文書を上位から順に作成し、親へリンク。派生要求は `derived: true`。NFR制約がある場合は設計文書から NFR アイテムへもリンクする
5. **実装・テスト** — 最下位設計文書に従ってコードとテストを書く（編集の順序は問わない）
6. **IMPL/TST登録** — `doorstop_ops.py add` でそれぞれ登録し、最下位設計にリンク
7. **レビュー** — `doorstop_ops.py chain-review <UID>` で関連アイテム全体を一括レビュー済みにする
8. **検証** — `validate_and_report.py --strict`。エラー0件を目指す
9. **コミット** — 仕様(設計)、テスト、実装の順番でコミットし、テストファーストの考え方を履歴に残す
10. **ベースライン更新** — リリースポイントで `baseline_manager.py create <version> --tag`
11. **報告** — 成果物ベースで簡潔に報告（Doorstopの内部構造は見せない）

操作コマンドは `doorstop_ops.py` を使う。アイテムの書き方は `references/item_writing_guide.md` を参照。

## [B] 変更フロー

1. **現状把握** — `trace_query.py chain <UID>` で関係性を把握
2. **影響分析** — `impact_analysis.py --changed <UID>` で波及範囲を特定
3. **設計更新** — 上位から順に修正（standard: ARCH → SPEC、full: HLD → LLD）
4. **実装・テスト修正** — コードとテストを修正。最終的に整合性が取れていれば、仕様・テスト・実装の**編集順序は問わない**。
5. **IMPL/TST更新** — アイテムを更新。関連アイテムとの整合性や編集内容を確認した上で、`doorstop_ops.py chain-review <UID>` でアイテムチェーン全体のsuspectを一括解消＆レビュー済みにする
6. **検証** — `validate_and_report.py --strict` + `impact_analysis.py --detect-suspects`
7. **コミット** — 仕様(設計)、テスト、実装の順番でコミットし、テストファーストの考え方を履歴に残す。
8. **報告** — 影響範囲と修正結果を報告。suspect 0件を確認

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
| ファイルからチェーン逆引き | `trace_query.py <dir> chain --file src/mod.py` |
| カバレッジ詳細 | `trace_query.py <dir> coverage [--group GROUP]` |
| suspect一覧 | `trace_query.py <dir> suspects` |
| リンク漏れ検出 | `trace_query.py <dir> gaps [--document IMPL]` |
| CRUD操作 | `doorstop_ops.py <dir> add/update/reorder/link/clear/review` |
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
| `groups` | 全アイテム | 機能グループ: AUTH, PAY, USR 等（必須） |
| `priority` | REQ/NFR | 優先度: `critical` / `high` / `medium`（デフォルト） / `low` |
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

### エージェントのコミット実行手順

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

