# Doorstop リファレンス

## ドキュメント属性クイックリファレンス

| 属性 | 対象 | 説明 |
|---|---|---|
| `text` | 全アイテム | 内容（必須） |
| `header` | 全アイテム | 短い見出し（20文字以内推奨） |
| `groups` | 全アイテム | 機能グループ: AUTH, PAY, USR 等（必須） |
| `priority` | REQ/NFR | 優先度: `critical` / `high` / `medium`（デフォルト） / `low` / `none` / `done` |
| `status` | ADR | 決定の状態: `accepted`（デフォルト） / `proposed` / `deprecated` / `superseded` |
| `level` | 全アイテム | ドキュメント内の階層 |
| `links` | REQ以外 | 親へのリンク（`derived: true` の場合は空でもよい） |
| `derived` | 設計層のみ | 派生要求フラグ。`text` に根拠セクション必須 |
| `normative` | 全アイテム | `false` で非規範的（見出し・背景説明用） |
| `references` | IMPL/TST | 外部ファイル紐付け（辞書型リスト、最大2–3ファイル） |
| `test_level` | TST（standard/full） | `unit` / `integration` / `acceptance` |
| `gherkin` | 振る舞い定義が必要な文書 | Gherkin 形式の振る舞い記述（Given/When/Then） |
| `active` | 全アイテム | `false` で論理削除 |
| `reviewed` | 全アイテム | レビュー済みハッシュ（`null` = 未レビュー） |

`references` は `[{"path": "src/mod.py", "type": "file"}]` 形式。
`conftest.py`, `__init__.py`, 共通ユーティリティは含めない。

## YAMLアイテムの構造

Doorstopの各要件は以下の属性を持つYAMLファイルとして保存される:

```yaml
active: true          # アイテムが有効かどうか
derived: false        # 派生要求フラグ（下記「派生要求」参照）
header: 'タイトル'     # アイテムのヘッダー（見出し）
level: 1.1            # ドキュメント内の階層レベル
links:                # 親ドキュメントアイテムへのリンク
  - SYS001: <hash>    # UID: フィンガープリント
normative: true       # 規範的（要件として扱う）かどうか。falseにすると見出し・背景説明等になる
ref: ''               # 外部ファイルへの参照（非推奨 → references を使う）
references:           # 外部ファイルへの紐付け（v2.0以降推奨）
  - path: src/mod.py  #   ファイルパス（リポジトリルートからの相対）
    type: file         #   ファイル種別（現在は file のみ）
reviewed: <hash>      # レビュー済みハッシュ（null=未レビュー）
text: |               # 要件のテキスト本体
  システムはユーザー認証を提供すること。
```

### 派生要求（derived 属性）

`derived: true` を設定すると、`links` が空でもトレーサビリティ検証をパスする。
技術的制約やアーキテクチャ選択から論理的に導かれた要求を管理するために使う。

- **使用可能な層**: 設計層のみ（ARCH / SPEC / HLD / LLD）
- **IMPL/TST での使用は禁止**
- **値変更はフィンガープリントに影響しない**（再レビュー不要）
- **text に根拠を必ず記述する**（なぜその制約が生じたか）

### 非規範的アイテム（normative 属性）

`normative: false` を設定することで、そのアイテムは「システムが満たすべき機能要件」ではなくなります。

- **用途**: 序文、背景説明、目標、用語の定義、ドキュメントの章や節の見出しとして使用します。
- **カバレッジ・検証の対象外**: 非規範的アイテムは「親リンク」を持つ必要がなく、リンク漏れチェックやカバレッジ計算から除外されます。
- **悪手**: 「優先度を下げるため」「今は実装しないから」という理由で本来の要件を `normative: false` にしてはいけません。

### references 属性（ref の後継）

`ref`（単一ファイル）の制限を解消し、1つのアイテムに複数ファイルを紐付ける。
各要素には `path`（ファイルパス）と `type`（`file`）を指定する。

紐付け基準:
- ドメインロジックの実装ファイル / 直接のテストファイルのみ
- `conftest.py`, `__init__.py`, 共通ユーティリティは含めない
- 1アイテムあたり最大2–3ファイル
- **`ref` は使わず `references` に統一する**

## ドキュメント設定（.doorstop.yml）

各ドキュメントディレクトリ直下の `.doorstop.yml` は、`init_project.py` で自動生成される。
`init_project.py` が `attributes` セクションも自動追加するが、手動でドキュメントを
追加する場合は自分で設定する必要がある。

### 構造

```yaml
settings:
  digits: '3'
  itemformat: yaml
  prefix: REQ
  sep: ''
  parent: null          # ルート文書は null、子文書は親の prefix

attributes:
  defaults:             # doorstop_ops.py add 時に自動付与される初期値
    groups: []
    priority: medium    # critical / high / medium / low / none / done
  reviewed:             # フィンガープリント計算に含めるカスタム属性
    - groups            #   → groups を変更すると「未レビュー」状態になる
    # REQ/NFR は priority も追加を推奨（優先度変更で再レビューをトリガー）
  publish:              # doorstop publish 時に出力に含めるカスタム属性
    - groups
    - priority
```

### 各キーの効果

| キー | 効果 | 例 |
|---|---|---|
| `defaults` | `doorstop_ops.py add` で新規アイテム作成時に自動付与される | `groups: []`, `priority: medium` |
| `reviewed` | ここに列挙した属性の値が変更されると、アイテムが「未レビュー」状態に戻る | `groups`, `priority`（REQ/NFR） |
| `publish` | `validate_and_report.py` でドキュメント出力時に表示されるカスタム属性 | `groups`, `priority` |

### 運用原則

**設定すべき属性:**
- `groups` — 機能グループ（リスト型）。仕様の対象スコープを示すメタデータ
- `priority` — 優先度（REQ/NFRのみ）。トリアージ・バックログ管理用
- `status` — ADRの状態（`accepted`, `proposed`, `deprecated`, `superseded`）

**設定してはいけない属性:**
- `author`, `creation_date` — Git（バージョン管理）やチケット管理の責務。
  Doorstop に持たせると情報が乖離し、管理が破綻する

### 注意事項

- `attributes` セクションは `init_project.py` が自動追加する。
  手動でドキュメントを追加した場合は自分で追記する必要がある
- `defaults` に定義した属性は、既存アイテムには遡及適用されない（新規アイテムのみ）
- `reviewed` に追加した属性は、変更のたびに再レビューが必要になるため、
  頻繁に変わる属性を入れると「レビュー疲れ」を引き起こす

## レベル（level）の使い方

レベルはドキュメントのアウトライン構造を決定する:

```
1.0   → セクション見出し（normative: false にすると純粋な見出し）
1.1   → 第1セクション内の要件1
1.2   → 第1セクション内の要件2
2.0   → 第2セクション見出し
2.1   → 第2セクション内の要件1
2.1.1 → サブ要件
```

## カスタム属性の使い方

### groups（機能グループ）

機能グループで横断的に分類する。推奨グループ名:
- 機能系: `AUTH`, `PAY`, `USR`, `NTF`, `RPT`, `ADM`, `DAT`
- 非機能系（NFRドキュメント）: `PERF`, `SEC`, `REL`, `MNT`, `PRT`, `SAF`

```bash
doorstop_ops.py <dir> add -d REQ -t "..." -g AUTH,PAY
doorstop_ops.py <dir> update REQ001 -g AUTH,PAY
```

### priority（優先度）

REQ/NFRアイテムの実装優先度。トリアージ・バックログ管理で使用する。

| 値 | 意味 |
|---|---|
| `critical` | 今すぐ必要、リリースブロッカー |
| `high` | 今回のリリースに含める |
| `medium` | できれば今回、次回でも可（デフォルト） |
| `low` | 将来対応、今回はスコープ外 |
| `none` | 未トリアージ（まだ優先度が決まっていない） |
| `done` | 対応完了（バックログ上の管理用） |

```bash
doorstop_ops.py <dir> add -d REQ -t "..." -g AUTH --priority high
doorstop_ops.py <dir> update REQ001 --priority critical
trace_query.py <dir> backlog              # 優先度順一覧
```

### status（ステータス）

ADR（Architecture Decision Records）の状態を管理する。

| 値 | 意味 |
|---|---|
| `accepted` | 採用され、現在有効な決定（デフォルト） |
| `proposed` | 提案中でレビュー待ちの決定 |
| `deprecated` | 廃止された決定（現在は使われていない） |
| `superseded` | 別の新しいADRによって上書きされた決定 |

```bash
doorstop_ops.py <dir> update ADR001 --status superseded
```

### gherkin（振る舞い記述）

設計文書（SPEC/ARCH/HLD/LLD）にBDD（振る舞い駆動）形式のシナリオを記述する。
`text` フィールドの技術仕様を補完し、テストケースへの変換を容易にする。

```bash
# SPEC追加時に gherkin を同時設定
doorstop_ops.py <dir> add -d SPEC -t "仕様テキスト" -g CACHE --links REQ001 \
  --gherkin "Scenario: 基本キャッシュ動作
  Given 空のDBとLocalStorageが初期化されている
  When @spot.mark() でデコレートされた関数を同一引数で2回呼び出す
  Then 1回目は関数が実行されキャッシュされる
  And 2回目はキャッシュから結果が返り関数は実行されない"

# 既存アイテムに gherkin を追加・更新
doorstop_ops.py <dir> update SPEC001 --gherkin "更新後の Gherkin シナリオ"
```

**記述ガイドライン:**
- `Scenario:` でシナリオ名を宣言する
- `Given` で前提条件、`When` で操作、`Then` で期待結果を記述する
- `And` / `But` で条件を追加できる
- 複数シナリオがある場合は `Scenario:` を繰り返す
- `text` フィールドには技術仕様（API、アルゴリズム等）を書き、`gherkin` には振る舞いを書く
- `gherkin` の各シナリオが TST のテストケースに 1:1 で対応することを目指す

### test_level（テスト粒度）

TST アイテムのテスト粒度を示す。standard/full プロファイルで使用する。
lite プロファイルでは不要（TST は全て SPEC に直接リンクする）。

| 値 | V字モデル対応 | リンク先 |
|---|---|---|
| `unit` | 単体テスト | SPEC / LLD |
| `integration` | 結合テスト | ARCH / HLD |
| `acceptance` | 受入テスト | REQ |

```bash
doorstop_ops.py <dir> add -d TST -t "..." -g AUTH --test-level unit --links SPEC001
doorstop_ops.py <dir> update TST001 --test-level integration
```

アイテムの書き方は `references/item_writing_guide.md` を参照。

## 操作スクリプトリファレンス

エージェントはDoorstopの生CLIやPython APIを直接使わず、専用スクリプトを使う。
すべてのスクリプトは `<skill-path>/scripts/` にある。

### doorstop_ops.py — CRUD操作

アイテムの追加・更新・リンク・レビューなど、すべてのCRUD操作を1コマンドで実行する。
結果はJSON形式で返される。

```bash
# 基本構文
uv run python <skill-path>/scripts/doorstop_ops.py <project-dir> <command> [options]
```

#### アイテム追加（add）
```bash
# REQ追加（テキスト + グループ指定）
doorstop_ops.py <dir> add -d REQ -t "システムはユーザー認証を提供すること" -g AUTH,PAY

# SPEC追加（ヘッダー + 親リンク付き）
doorstop_ops.py <dir> add -d SPEC -t "JWTベースの認証を実装する" --header "JWT認証" -g AUTH,PAY --links REQ001

# SPEC追加（gherkin 付き）
doorstop_ops.py <dir> add -d SPEC -t "仕様テキスト" --header "キャッシュ動作" -g CACHE --links REQ001 \
  --gherkin "Scenario: 基本キャッシュ動作
  Given 空のDBが初期化されている
  When 同一引数で2回呼び出す
  Then 2回目はキャッシュから返る"

# 非規範的アイテム（見出しや背景）の追加
doorstop_ops.py <dir> add -d REQ -t "本章では認証について定義する。" --header "認証システム" --non-normative -l 1.0

# IMPL追加（references付き）
doorstop_ops.py <dir> add -d IMPL -t "認証モジュールの実装" -g AUTH,PAY \
  --references '[{"path":"src/auth.py","type":"file"}]' --links SPEC001

# TST追加（references付き）
doorstop_ops.py <dir> add -d TST -t "認証成功時にHTTP200を返すことを検証する" -g AUTH,PAY \
  --references '[{"path":"tests/test_auth.py","type":"file"}]' --links SPEC001

# TST追加（test_level付き — standard/fullプロファイル用）
doorstop_ops.py <dir> add -d TST -t "結合テスト" -g AUTH --test-level integration --links SPEC001

# レベル指定で追加（指定したレベルとして末尾などに追加）
doorstop_ops.py <dir> add -d REQ -t "サブ要件" -g AUTH,PAY -l 1.2

# 特定のレベルに挿入し、以降のアイテムを自動で後ろにずらす
doorstop_ops.py <dir> add -d REQ -t "挿入要件" --insert 1.5

#### アイテム更新（update）
```bash
# テキスト更新
doorstop_ops.py <dir> update REQ001 -t "新しい要件テキスト"

# ヘッダーとグループを更新
doorstop_ops.py <dir> update SPEC001 --header "新ヘッダー" -g PAY

# references更新
doorstop_ops.py <dir> update IMPL001 --references '[{"path":"src/new_mod.py","type":"file"}]'

# test_level更新（standard/fullプロファイル）
doorstop_ops.py <dir> update TST001 --test-level unit

# gherkin更新
doorstop_ops.py <dir> update SPEC001 --gherkin "Scenario: 更新後のシナリオ
  Given ...
  When ...
  Then ..."

# 規範的/非規範的の切り替え
doorstop_ops.py <dir> update REQ001 --set-non-normative
```

#### アイテムの並べ替え（reorder）
レベル（階層）を変更し、以降のアイテムのレベルを自動で調整します。

```bash
# REQ004 をレベル 1.5 の位置に移動し、以降のアイテムを自動調整する
doorstop_ops.py <dir> reorder REQ004 1.5
```

#### リンク追加（link）
```bash
doorstop_ops.py <dir> link SPEC001 REQ001    # SPEC001 → REQ001 へリンク
```

#### リンク削除（unlink）
```bash
doorstop_ops.py <dir> unlink SPEC001 REQ001  # SPEC001 → REQ001 のリンクを削除
```

リンクの張り替え（別の親に繋ぎ直す）:
```bash
doorstop_ops.py <dir> unlink SPEC001 REQ001  # 旧リンクを削除
doorstop_ops.py <dir> link SPEC001 REQ002    # 新リンクを追加
```

#### 非活性化（deactivate）
```bash
# 単体の非活性化
doorstop_ops.py <dir> deactivate REQ001          # REQ001 を active: false に
doorstop_ops.py <dir> deactivate REQ001 SPEC001  # 複数UID指定可

# チェーン非活性化（下流を自動検査し連鎖的に非活性化）
doorstop_ops.py <dir> deactivate-chain REQ001
# → REQ001 と、他に活性な親を持たない下流アイテムを一括非活性化

# 強制チェーン非活性化（他に活性な親があっても強制）
doorstop_ops.py <dir> deactivate-chain REQ001 --force
```

#### 活性化（activate）
```bash
# 単体の活性化
doorstop_ops.py <dir> activate REQ001 SPEC001

# チェーン活性化（下流を連鎖的に活性化）
doorstop_ops.py <dir> activate-chain REQ001
```

#### suspect解消（clear）
```bash
doorstop_ops.py <dir> clear SPEC001 SPEC002  # 複数UID指定可
```

#### レビュー済み設定（review）
```bash
doorstop_ops.py <dir> review SPEC001 IMPL001 TST001  # 複数UID指定可
```

#### チェーンレビュー（chain-review）

アイテムを起点に、そのアイテムと全ての**祖先（上流）アイテム**を一括で review 済みにする。
SDD 原則に基づき、下位の変更を確定させる前に、まず上位の仕様が正しいことを承認するために使用する。
※下流の suspect 解消（clear）は行わない。

```bash
# SPEC001 と、その親である ARCH/REQ を一括でレビュー済みに
doorstop_ops.py <dir> chain-review SPEC001

# 複数の起点UIDを指定可
doorstop_ops.py <dir> chain-review SPEC001 SPEC002
```

#### チェーンクリア（chain-clear）

アイテムを起点に、そのアイテムと全ての**子孫（下流）アイテム**を探索し、`suspect` リンクがあれば一括で解消（clear）する。
実装やテストの修正が完了した後、上位仕様の変更を下流が正しく取り込んだことを一括承認するために使用する。

```bash
# SPEC001 の変更を、下流の IMPL001/TST001 に波及させた後に一括承認する
doorstop_ops.py <dir> chain-clear SPEC001
```

#### 一覧・検索

```bash
# 全アイテム一覧
doorstop_ops.py <dir> list

# ドキュメント絞り込み
doorstop_ops.py <dir> list -d SPEC

# グループ絞り込み
doorstop_ops.py <dir> list -g AUTH,PAY

# ドキュメント + グループ絞り込み
doorstop_ops.py <dir> list -d IMPL -g AUTH,PAY

# グループ一覧
doorstop_ops.py <dir> groups

# ツリー構造
doorstop_ops.py <dir> tree

# テキスト検索
doorstop_ops.py <dir> find "認証"
```

### trace_query.py — トレーサビリティ照会

```bash
# プロジェクト全体のステータスサマリ
trace_query.py <dir> status

# 特定UIDの上下リンクチェーンを表示
trace_query.py <dir> chain SPEC003

# ファイルパスをreferencesから逆引きしてチェーンを表示（--file フラグ）
# → 実装/テストファイルを起点にどのSPEC/REQに紐づくか追跡できる
# フルパス、相対パス、basename のいずれでもマッチする
trace_query.py <dir> chain --file src/beautyspot/core.py
trace_query.py <dir> chain --file tests/integration/core/test_mark.py
trace_query.py <dir> chain --file core.py   # basename のみでも可

# 全文脈情報を一括取得（target/upstream/downstream/関連ファイル/health状態）
# → 1回のコマンドで「何を読み、何を変え、何をテストすべきか」が分かる
trace_query.py <dir> context SPEC003

# 関連ファイルパスをドキュメント層別に取得（context より軽量）
trace_query.py <dir> related-files SPEC003
trace_query.py <dir> related-files --file src/beautyspot/core.py  # ファイル逆引きも可

# 属性フィルタ付き高機能検索（正規表現対応）
trace_query.py <dir> search "タイムアウト"                           # テキスト検索
trace_query.py <dir> search "認証" -d SPEC -g AUTH                   # ドキュメント+グループ絞り込み
trace_query.py <dir> search --suspect --unreviewed                   # suspect かつ未レビュー
trace_query.py <dir> search --has-gherkin -d SPEC                    # gherkin付きSPECを検索
trace_query.py <dir> search -g AUTH --priority critical,high         # 優先度フィルタ
trace_query.py <dir> search --derived -d SPEC                        # 派生要求のみ
trace_query.py <dir> search -d IMPL -g CACHE                        # パターンなし=全件（フィルタのみ）

# カバレッジ（全体 / グループ別）
trace_query.py <dir> coverage
trace_query.py <dir> coverage --group AUTH

# suspect一覧
trace_query.py <dir> suspects

# リンク漏れ検出
trace_query.py <dir> gaps
trace_query.py <dir> gaps --document IMPL

# 優先度順バックログ一覧（トリアージ用）
# デフォルトは REQ のみ。--document でドキュメント指定、--all で全ドキュメント
trace_query.py <dir> backlog
trace_query.py <dir> backlog --group AUTH         # グループ絞り込み
trace_query.py <dir> backlog -d NFR               # NFRのバックログ
trace_query.py <dir> backlog --all                 # 全ドキュメントのバックログ
```

### impact_analysis.py — 影響分析

```bash
# suspect自動検出
impact_analysis.py <dir> --detect-suspects

# 特定UIDの変更による影響範囲を分析
impact_analysis.py <dir> --changed REQ001

# JSON出力（action_plan_summary 付き）
impact_analysis.py <dir> --detect-suspects --json report.json

# 推奨アクション（review/clear）を自動実行
impact_analysis.py <dir> --detect-suspects --auto-execute
```

### baseline_manager.py — ベースライン管理

```bash
# ベースラインを作成（任意のタイミングで記録）
baseline_manager.py <dir> create v1.0
baseline_manager.py <dir> create v1.0 --tag                    # Git タグも付ける
baseline_manager.py <dir> create sprint-3 --tag --tag-name v1.3.0-spec

# ベースライン一覧
baseline_manager.py <dir> list

# バージョン間の差分（stamp変化=テキスト変更、added/removed=アイテム増減）
baseline_manager.py <dir> diff v1.0 v2.0
baseline_manager.py <dir> diff v1.0 HEAD  # HEAD = 現在のツリー状態
```

### validate_and_report.py — バリデーション・レポート

```bash
# 厳密バリデーション（リリースゲート用）
validate_and_report.py <dir> --strict

# 静的HTMLレポート出力
validate_and_report.py <dir> --output-dir ./reports --strict

# ダッシュボード起動
validate_and_report.py <dir> --serve --port 8080
```

### init_project.py — プロジェクト初期化

```bash
# 新規プロジェクト初期化
init_project.py <project-dir> --profile lite

# 既存gitリポジトリに導入（git init をスキップ）
init_project.py <project-dir> --profile lite --no-git-init
```

### 注意事項

- **生の `doorstop` CLI は使わない。** `doorstop_ops.py` がすべてのCRUD操作をカバーする
- **Python API (`import doorstop`) の直接使用は避ける。** スクリプト経由で操作する
- すべてのスクリプトは `uv run python <skill-path>/scripts/<script>.py` で実行する
- 結果はJSON形式で返されるため、エージェントが容易にパースできる
