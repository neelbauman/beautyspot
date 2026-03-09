# Doorstop リファレンス

## YAMLアイテムの構造

Doorstopの各要件は以下の属性を持つYAMLファイルとして保存される:

```yaml
active: true          # アイテムが有効かどうか
derived: false        # 派生要求フラグ（下記「派生要求」参照）
header: 'タイトル'     # アイテムのヘッダー（見出し）
level: 1.1            # ドキュメント内の階層レベル
links:                # 親ドキュメントアイテムへのリンク
  - SYS001: <hash>    # UID: フィンガープリント
normative: true       # 規範的（要件として扱う）かどうか
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

### references 属性（ref の後継）

`ref`（単一ファイル）の制限を解消し、1つのアイテムに複数ファイルを紐付ける。
各要素には `path`（ファイルパス）と `type`（`file`）を指定する。

紐付け基準:
- ドメインロジックの実装ファイル / 直接のテストファイルのみ
- `conftest.py`, `__init__.py`, 共通ユーティリティは含めない
- 1アイテムあたり最大2–3ファイル
- **`ref` は使わず `references` に統一する**

## ドキュメント設定（.doorstop.yml）

各ドキュメントディレクトリ直下の `.doorstop.yml` は、`doorstop create` で自動生成される。
`init_project.py` が `attributes` セクションを自動追加するが、手動でドキュメントを
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
  defaults:             # doorstop add / doc.add_item() 時に自動付与される初期値
    group: ''
  reviewed:             # フィンガープリント計算に含めるカスタム属性
    - group             #   → group を変更すると「未レビュー」状態になる
  publish:              # doorstop publish 時に出力に含めるカスタム属性
    - group
```

### 各キーの効果

| キー | 効果 |
|---|---|
| `defaults` | `doorstop add` や `doc.add_item()` で新規アイテム作成時に自動付与される |
| `reviewed` | ここに列挙した属性の値が変更されると、アイテムが「未レビュー」状態に戻る |
| `publish` | `doorstop publish` でドキュメント出力時に表示されるカスタム属性 |

### 運用原則

**設定すべき属性:**
- `group` — 機能グループ。仕様の対象スコープを示すメタデータ

**設定してはいけない属性:**
- `author`, `creation_date`, `status` — Git（バージョン管理）やチケット管理の責務。
  Doorstop に持たせると情報が乖離し、管理が破綻する

### 注意事項

- `attributes` セクションは `doorstop create` では生成されない。
  `init_project.py` が自動追加するか、手動で追記する必要がある
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

## 要件テキストの書き方

### 良い例

```
システムはログインに3回連続失敗したアカウントを30分間ロックすること。
ソフトウェアは全てのAPI応答を200ms以内に返却すること。
テストはログイン成功時にHTTPステータス200が返ることを検証すること。
```

### 避けるべき表現

```
✗ システムは適切にエラーハンドリングすること。        → 「適切に」が曖昧
✗ レスポンスは十分高速であること。                    → 数値基準がない
✗ ソフトウェアは使いやすいUIを提供すること。          → 主観的で検証不能
✗ システムはセキュアであること。                      → 具体性に欠ける
```

### REQ / SPEC / TST の使い分け

| レベル | 焦点 | 例 |
|--------|------|-----|
| REQ | 何を実現するか（What） | 「管理者はユーザーアカウントを無効化できること」 |
| SPEC | どう実現するか（How） | 「APIは /api/users/{id}/deactivate エンドポイントを提供すること」 |
| TST | どう検証するか（Verify） | 「DELETEリクエスト送信後、該当ユーザーのstatus=inactiveを確認する」 |

### 機能グループ（group カスタム属性）

各アイテムに `group` 属性を設定して、機能単位で横断的に分類できる。

```yaml
# YAMLファイル内での表現
active: true
group: AUTH          # ← カスタム属性
header: 'ログイン'
level: 1.1
links:
  - REQ001
text: |
  ソフトウェアはJWT認証を実装すること。
```

Python APIでの設定:
```python
item.set('group', 'AUTH')
item.save()

# 取得
group = item.get('group')
```

推奨グループ名の例:
- `AUTH` — 認証・認可
- `PAY` — 決済・課金
- `USR` — ユーザー管理
- `NTF` — 通知
- `RPT` — レポート・分析
- `ADM` — 管理機能
- `DAT` — データ管理
- `SEC` — セキュリティ

## CLI コマンドリファレンス

### プロジェクト操作
```bash
doorstop                        # ツリー表示＋バリデーション
doorstop create PREFIX PATH     # 新規ドキュメント作成
doorstop delete PREFIX          # ドキュメント削除
```

### アイテム操作
```bash
doorstop add PREFIX             # アイテム追加
doorstop add PREFIX -l 1.2      # レベル指定で追加
doorstop add PREFIX -c 5        # 5件一括追加
doorstop remove UID             # アイテム削除
doorstop edit UID               # エディタで編集
```

### リンク操作
```bash
doorstop link CHILD PARENT      # リンク追加
doorstop unlink CHILD PARENT    # リンク解除
doorstop clear UID              # suspectステータス解消
doorstop review UID             # レビュー済みに設定
```

### 出力
```bash
doorstop publish PREFIX         # テキスト出力（stdout）
doorstop publish PREFIX -m      # Markdown出力
doorstop publish PREFIX -H      # HTML出力
doorstop publish all DIR --html # 全ドキュメントHTML出力
doorstop export PREFIX          # YAML形式でエクスポート
```

### バリデーションオプション
```bash
doorstop -Z    # --strict-child-check: 全親アイテムに子リンク必須
doorstop -C    # --no-child-check: 子リンクチェック無効
doorstop -S    # --no-suspect-check: suspect警告を無視
doorstop -W    # --no-review-check: レビュー状態チェック無効
```

## Python API 主要クラス

```python
import doorstop

# ツリー構築
tree = doorstop.build()           # カレントディレクトリから構築
tree = doorstop.build(root='.')   # ルート指定

# ドキュメント操作
doc = tree.find_document('SYS')
items = list(doc)                 # 全アイテム
item = doc.find_item('SYS001')   # UID指定で取得

# アイテム操作
new_item = doc.add_item(level='1.0')
new_item.text = '要件テキスト'
new_item.header = 'タイトル'
new_item.link('PARENT_UID')
new_item.save()

# バリデーション
valid = tree.validate()           # True/False
```
