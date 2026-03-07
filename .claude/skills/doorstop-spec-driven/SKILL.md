---
name: doorstop-spec-driven
description: >
  仕様駆動開発（Specification-Driven Development）を自律的に実行するスキル。
  コーディングエージェント（Claude Code等）が、ユーザーの自然言語による要望を受け取り、
  Doorstopによる要件→仕様→実装→テストの全ライフサイクルを自動的に管理する。
  ユーザーは「〜を作って」「〜を直して」と言うだけでよい。
  エージェントがREQ/SPEC/IMPL/TSTアイテムの作成および修正・リンク・バリデーション・
  影響分析をすべて自動で行い、コードの実装・テストも並行して実施する。
  「機能を追加して」「バグを直して」「仕様を変更して」「リファクタリングして」
  のような開発リクエスト全般でトリガーすること。
  コードを書く前に必ずこのスキルを参照し、仕様→実装の順序を守ること。
---

# 仕様駆動開発スキル（エージェント版）

コーディングエージェントが仕様駆動開発のライフサイクルを自律的に実行するための指示書。
ユーザーは気軽に要望を伝えるだけでよい。エージェントが以下を全自動で行う:

- 要望をREQ/SPECに分解・登録
- コード実装とIMPLアイテム登録
- テスト作成とTSTアイテム登録
- トレーサビリティリンクの構築
- バリデーションと影響分析

## 鉄則

1. **コードを書く前にSPECを書く。** 実装はSPECの具現化であり、SPECのないコードは書かない
    1. ただし、実装はSPECにない力学でも構築されるので、逆に実装から仕様に反映されることもある
2. **テストを書いたらTSTを書く。** テストコードとTSTアイテムは常にペア
3. **変更したらimpact_analysisを回す。** 変更の影響を把握してから修正に入る
4. **バリデーションを最後に必ず実行する。** リンク漏れやカバレッジ低下を放置しない
5. 仕様や要件が変更になったら、インタラクティブダッシュボード（REST API + SPA） `uv run python <skill-path>/scripts/validate_and_report.py <project-dir> --serve [--port 8080]` を起動し、レビューをすることをユーザーに促す。

## セットアップ

初回のみ実行。プロジェクトにDoorstopツリーがなければ自動初期化する。

```bash
uv add doorstop
uv run python <skill-path>/scripts/init_project.py <project-dir>
```

既存gitリポジトリ: `--no-git-init` を付ける。

初期化されるツリー:
```
REQ（要件: What）→ SPEC（仕様: How）→ IMPL（実装: Build）
                                    → TST（テスト: Verify）
```

## エージェントの判断フロー

ユーザーの発話を受けたら、以下の判断木に従う。

```
ユーザーの発話
  │
  ├─ 新機能・新要件？ ──────→ [A] 新規開発フロー
  │  「〜を作って」「〜機能が欲しい」
  │
  ├─ 既存の変更・修正？ ────→ [B] 変更フロー
  │  「〜を直して」「〜を変えて」
  │
  ├─ バグ修正？ ────────────→ [C] バグ修正フロー
  │  「〜が動かない」「〜でエラーが出る」
  │
  ├─ 状況確認？ ────────────→ [D] レポートフロー
  │  「トレーサビリティを見せて」「カバレッジは？」
  │
  └─ リリース前チェック？ ──→ [E] リリースゲート
     「リリースして」「出荷OK？」
```

---

## [A] 新規開発フロー

ユーザーが新しい機能を要望したとき。

### ステップ

```
1. 理解     ユーザーの要望を要件文に変換する
2. 分類     機能グループを決定する（既存 or 新規）
3. REQ登録  要件アイテムを作成する
4. SPEC策定 技術仕様を設計し、アイテムを作成する
5. 実装     コードを書く
6. IMPL登録 実装アイテムを作成し、refでコードを紐づける
7. テスト   テストコードを書く
8. TST登録  テストアイテムを作成し、refでテストを紐づける
9. 検証     バリデーション実行
10. 報告    ユーザーに結果を簡潔に報告する
```

### 実行手順

**ステップ1-2: 理解と分類**

ユーザーの発話から以下を抽出する:
- 何を実現したいか（→ REQのtext）
- 既存のどの機能グループに属するか、新規グループが必要か

ユーザーに確認は不要。エージェントが自律判断する。
ただし、要件の解釈に曖昧さがある場合のみユーザーに確認する。

**ステップ3: REQ登録**

```python
import doorstop
tree = doorstop.build()
req = tree.find_document('REQ')

item = req.add_item()
item.text = '要件文（〜できること形式）'
item.header = '短い名称'
item.set('group', 'AUTH')
item.save()
```

要件文のルール:
- 「〜できること」「〜すること」形式
- 1アイテム1要件（複合しない）
- 検証可能な表現を使う

**ステップ4: SPEC策定**

REQから技術仕様を導出する。エージェント自身の技術判断で仕様を決定する。

```python
spec = tree.find_document('SPEC')
s = spec.add_item()
s.text = '技術仕様（具体的な数値・フォーマット・プロトコル含む）'
s.set('group', 'AUTH')
s.link(req_item.uid)  # REQへのリンク
s.save()
```

仕様文のルール:
- 技術的に具体的であること（アルゴリズム名、数値、制約）
- 1つのREQに対して1つ以上のSPEC

**ステップ5-6: 実装 + IMPL登録**

SPECに従ってコードを実装する。実装完了後にIMPLアイテムを登録する。

```python
impl = tree.find_document('IMPL')
i = impl.add_item()
i.text = '実装概要'
i.set('group', 'AUTH')
i.ref = 'src/auth/password.py::PasswordHasher'  # リポジトリルートからの相対パス
i.link(spec_item.uid)  # SPECへのリンク
i.save()
```

ref の書き方:
- ファイル単位: `src/auth/password.py`
- クラス/関数まで: `src/auth/password.py::PasswordHasher`

**ステップ7-8: テスト + TST登録**

SPECに対するテストを書き、TSTアイテムを登録する。

```python
tst = tree.find_document('TST')
t = tst.add_item()
t.text = 'テスト手順と期待結果'
t.set('group', 'AUTH')
t.ref = 'tests/test_auth.py::test_password_hash'
t.link(spec_item.uid)  # SPECへのリンク
t.save()
```

**ステップ9: 検証**

```bash
uv run python <skill-path>/scripts/validate_and_report.py <project-dir> --strict --json ./reports/validation.json
```

エラー0件・警告0件を目指す。問題があれば自律的に修正する。

**ステップ10: 報告**

ユーザーには簡潔に報告する。Doorstopの内部的な話は不要。

報告テンプレート:
```
✅ [AUTH] ログイン機能を実装しました。

作成したもの:
- REQ001: ユーザーはパスワードでログインできること
- src/auth/login.py — ログイン処理
- tests/test_auth.py — テスト3件（全件パス）

トレーサビリティ: REQ→SPEC→IMPL/TST 全リンク済み、カバレッジ100%
```

---

## [B] 変更フロー

既存の仕様・実装を変更するとき。

### ステップ

```
1. 影響分析   変更対象の特定と波及範囲の把握
2. SPEC更新   仕様アイテムを修正する
3. 実装修正   コードを修正する
4. IMPL更新   実装アイテムを更新する
5. テスト修正 テストを修正する
6. TST更新    テストアイテムを更新する
7. suspect解消 doorstop clear で解消
8. 検証       バリデーション実行
9. 報告       ユーザーに影響範囲と修正結果を報告
```

### 実行手順

**ステップ1: 影響分析（変更前に必ず実行）**

```bash
# 何が影響を受けるか事前に把握する
uv run python <skill-path>/scripts/impact_analysis.py <project-dir> \
  --changed <変更予定のUID> \
  --json ./reports/impact.json
```

影響分析の結果から、修正が必要なIMPL/TSTアイテムとそのrefファイルを把握する。

**ステップ2-6: 仕様→実装→テストの順に修正**

仕様を先に修正し、その内容に合わせてコードとテストを修正する。
順序を逆にしてはいけない（コードを先に直して仕様を後から合わせるのはNG）。

```python
# SPEC修正
spec_item.text = '新しい仕様文'
spec_item.save()

# コード修正（エディタ操作）

# IMPL更新（refが変わった場合）
impl_item.text = '更新後の実装概要'
impl_item.save()

# テスト修正（エディタ操作）

# TST更新
tst_item.text = '更新後のテスト手順'
tst_item.save()
```

**ステップ7: suspect解消**

親アイテムの変更で発生したsuspectリンクを解消する。
修正が完了したアイテムに対してのみclearする。

```bash
doorstop clear IMPL001
doorstop clear TST001
```

Python APIでは:
```python
for link in item.links:
    item.clear(link)
item.save()
```

**ステップ8-9: 検証と報告**

```bash
uv run python <skill-path>/scripts/validate_and_report.py <project-dir> --strict
uv run python <skill-path>/scripts/impact_analysis.py <project-dir> --detect-suspects
```

suspect 0件を確認してから報告する。

報告テンプレート:
```
✅ [AUTH] パスワードハッシュをArgon2idに変更しました。

変更内容:
- SPEC001: bcrypt → Argon2id（メモリ64MB、反復3回）
- src/auth/password.py — ハッシュアルゴリズム変更
- tests/test_auth.py — 期待値更新、テスト全件パス

影響範囲: IMPL001, TST001 → 修正済み、suspect解消済み
```

---

## [C] バグ修正フロー

バグ報告を受けたとき。

### ステップ

```
1. 原因特定    どのSPEC/IMPLに関連するバグか特定する
2. 判断        仕様バグか実装バグか判断する
   - 仕様バグ → [B]変更フローへ（SPECの修正から始める）
   - 実装バグ → 以下を続行
3. コード修正  バグを修正する
4. IMPL更新    必要に応じてIMPLアイテムを更新する
5. テスト追加  バグの再発防止テストを追加する
6. TST登録     テストアイテムを追加し、SPECにリンクする
7. 検証        バリデーション実行
8. 報告
```

仕様バグと実装バグの判断基準:
- SPECの記述通りに実装したがユーザーの期待と違う → 仕様バグ（REQ/SPECの修正が必要）
- SPECの記述と実装が乖離している → 実装バグ（コードの修正のみ）

---

## [D] レポートフロー

```bash
# トレーサビリティレポート（全体）— 静的HTML+JSON生成
uv run python <skill-path>/scripts/validate_and_report.py <project-dir> \
  --output-dir ./reports --strict --json

# インタラクティブダッシュボード（REST API + SPA）
# バックエンドでデータを一元管理し、Edit/Review/Clear が全ビューに即時反映される
uv run python <skill-path>/scripts/validate_and_report.py <project-dir> --serve [--port 8080]
# または直接起動:
uv run python <skill-path>/scripts/serve_app.py <project-dir> [--port 8080] [--strict]

# 影響分析（suspectチェック）
uv run python <skill-path>/scripts/impact_analysis.py <project-dir> \
  --detect-suspects --json ./reports/impact.json

# 局所トレーサビリティビュー（静的HTML生成）
uv run python <skill-path>/scripts/local_trace_view.py <project-dir> --uid REQ001
uv run python <skill-path>/scripts/local_trace_view.py <project-dir> --group CACHE
uv run python <skill-path>/scripts/local_trace_view.py <project-dir> --all [--json]
```

`--serve` モードでは REST API + SPA が起動し、ダッシュボード・マトリクス・
グループビュー・アイテム詳細を動的に表示する。全データはバックエンドの
DoorstopDataStore で一元管理され、Edit/Review/Clear 操作後は
インデックスが自動再構築されるため、全ビューに即時反映される。

静的レポートは `--output-dir`（デフォルト: `./reports`）に出力される。
局所ビューは `./reports/local` に出力され、`--all` 時は `index.html` がインデックス。

ユーザーへの報告は技術用語を避け、プレーンに:
```
📊 プロジェクト状況:
- 要件: 12件（REQ）
- 仕様: 18件（SPEC）→ 要件カバレッジ 100%
- 実装: 16件（IMPL）→ 仕様カバレッジ 89%（SPEC015, SPEC018 が未実装）
- テスト: 15件（TST）→ 仕様カバレッジ 83%（SPEC012, SPEC015, SPEC018 が未テスト）
- 未解消のsuspect: 0件
- 未レビュー: 3件
```

---

## [E] リリースゲート

リリース前に全チェックを実行する。

```bash
# 1. バリデーション
uv run python <skill-path>/scripts/validate_and_report.py <project-dir> --strict --json ./reports/validation.json

# 2. suspect確認
uv run python <skill-path>/scripts/impact_analysis.py <project-dir> --detect-suspects --json ./reports/suspects.json

# 3. テスト実行（プロジェクトのテストランナー）
pytest  # or 適切なテストコマンド
```

リリース可否の判断基準:
- バリデーションエラー: 0件 → 必須
- 全カバレッジ: 100% → 必須
- suspect: 0件 → 必須
- テスト全件パス → 必須
- 未レビュー: 警告表示（ブロックしない）

---

## ドキュメント階層と属性

```
REQ（要件: What）
└── SPEC（仕様: How）
    ├── IMPL（実装: Build）  ref → ソースコード
    └── TST（テスト: Verify） ref → テストコード
```

全アイテム共通属性:
- `text`: 内容（必須）
- `group`: 機能グループ（AUTH, PAY, USR 等。必須）
- `links`: 親へのリンク（REQ以外は必須）

IMPL/TST追加属性:
- `ref`: ソース/テストファイルのパス（リポジトリルートからの相対パス）

## 機能グループ

大文字の短縮形を使い、プロジェクト内で統一する。
新規グループが必要な場合はエージェントが命名する。

既存グループの確認:
```python
groups = sorted({get_group(item) for doc in tree for item in doc})
```

## 操作リファレンス

詳細なDoorstop APIやCLIの使い方は `references/doorstop_reference.md` を参照。
Doorstopアイテムの記述の仕方は、`references/item_writing_guide.md` を参照。
ライフサイクル全体の設計思想は `references/dev_lifecycle.md` を参照。

## エージェントの振る舞い規約

### やること
- ユーザーの発話を自律的にREQ/SPECに分解する
- コードを書く前にSPECアイテムを先に作成する
- 実装後にIMPLアイテムを作成し、refでコードを紐づける
- テスト後にTSTアイテムを作成し、refでテストを紐づける
- 変更時は必ず影響分析を先に実行する
- 最後にバリデーションを実行し、エラー0件を確認する
- ユーザーへの報告はDoorstopの内部構造を隠し、成果物ベースで伝える

### やらないこと
- ユーザーにDoorstop操作を要求する
- SPECなしでコードを書き始める
- IMPLやTSTのアイテム登録をスキップする
- バリデーション警告を無視して作業を終える
- suspect未解消のまま次のタスクに移る
