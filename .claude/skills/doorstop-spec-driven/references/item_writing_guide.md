# Doorstop アイテム記述ガイド — 詳細テンプレート

## 概要

Doorstop の `text` フィールドは **Markdown** をサポートしている。
1行の要約だけでなく、構造化された詳細な記述を行うことで、
仕様の正確性・レビュー効率・トレーサビリティが大幅に向上する。

本ガイドでは各層（REQ / SPEC / IMPL / TST）の詳細な書き方テンプレートと
実例を示す。

---

## 共通ルール

- `header` は **短い見出し**（20文字以内推奨）
- `text` に **Markdown で詳細を記述**する
- `group` で機能グループを横断分類する
- `level` でドキュメント内の階層を表現する
- YAMLのリテラルブロック `|` を使い、複数行テキストを記述する

---

## REQ（要件）— What を定義する

### テンプレート

```yaml
active: true
derived: false
group: CACHE
header: |
  関数キャッシュ
level: 1.0
links: []
normative: true
ref: ''
reviewed: null
text: |
  ## 概要

  関数の実行結果をキャッシュし、同一入力に対して再実行せずに
  キャッシュから結果を返せること。

  ## 背景・動機

  データパイプラインやML実験では、同一パラメータでの再実行が頻発する。
  計算コストの高い関数の結果をキャッシュすることで、
  開発サイクルを大幅に短縮できる。

  ## 受入基準

  - 同期関数・非同期関数の両方をサポートすること
  - 同一引数での2回目以降の呼び出しでは、関数を実行せずキャッシュを返すこと
  - キャッシュキーは引数の値に基づき、引数の順序に依存しないこと
  - キャッシュの有無はユーザーコードに透過的であること

  ## 制約事項

  - ジェネレータ関数はキャッシュ対象外とする
  - 副作用のある関数のキャッシュは利用者の責任とする

  ## スコープ外

  - 分散キャッシュ（Redis等）は本要件の対象外
  - キャッシュの自動無効化（依存ファイル変更検知等）は別要件で扱う
```

### ポイント

| セクション | 目的 |
|---|---|
| 概要 | 1-2文で要件の本質を述べる |
| 背景・動機 | なぜこの要件が必要か（Why） |
| 受入基準 | 検証可能な条件のリスト |
| 制約事項 | 明示的な制限・前提条件 |
| スコープ外 | 意図的に含めないもの（誤解防止） |

---

## ARCH（基本設計）— Architecture を定義する（standardプロファイル）

ARCHはコンポーネント分割、コンポーネント間インターフェース、データフロー、
技術選定を定義する。「何を作るか」ではなく「どう構成するか」に焦点を当てる。
fullプロファイルではHLD（High-Level Design）が同等の役割を担う。

### テンプレート

```yaml
active: true
derived: false
group: CACHE
header: |
  キャッシュサブシステム構成
level: 1.0
links:
- REQ001: <fingerprint>
normative: true
ref: ''
reviewed: null
text: |
  ## コンポーネント構成

  ```mermaid
  graph TD
    A[bs.Spot Factory] -->|DI| B[core.Spot Engine]
    B --> C[TaskDBBase]
    B --> D[SerializerProtocol]
    B --> E[BlobStorageBase]
    B --> F[StoragePolicyProtocol]
    B --> G[LimiterProtocol]
    B --> H[LifecyclePolicy]
  ```

  ## コンポーネント責務

  | コンポーネント | 責務 | インターフェース |
  |---|---|---|
  | core.Spot | キャッシュエンジン。キー生成→検索→実行→保存の制御 | `mark()`, `cached_run()` |
  | TaskDBBase | メタデータ永続化。キャッシュキーによる検索と保存 | `find_by_key()`, `insert()` |
  | SerializerProtocol | データのシリアライズ/デシリアライズ | `pack()`, `unpack()` |
  | BlobStorageBase | 大規模データの外部ストレージ保存 | `save()`, `load()`, `delete()` |
  | StoragePolicyProtocol | Blob保存の判定ポリシー | `should_save_as_blob()` |

  ## データフロー

  ```mermaid
  sequenceDiagram
    participant User as ユーザーコード
    participant Spot as core.Spot
    participant DB as TaskDB
    participant Ser as Serializer
    participant Blob as BlobStorage

    User->>Spot: fn(args)
    Spot->>DB: find_by_key(cache_key)
    alt キャッシュヒット
      DB-->>Spot: cached_data
      Spot->>Ser: unpack(data)
    else キャッシュミス
      Spot->>Spot: fn(args) 実行
      Spot->>Ser: pack(result)
      Spot->>DB: insert(metadata)
      opt Blob保存
        Spot->>Blob: save(key, data)
      end
    end
    Spot-->>User: result
  ```

  ## 技術選定

  | 技術領域 | 選定 | 理由 |
  |---|---|---|
  | メタデータDB | SQLite | ゼロ設定、組み込み可能、十分な性能 |
  | シリアライズ | MessagePack | JSONより高速・コンパクト、バイナリ対応 |
  | ストレージ | ローカルファイル / S3 | 小規模はローカル、大規模はS3で透過切替 |

  ## 非機能要件方針

  - **性能**: キャッシュヒット時のオーバーヘッドは1ms以内
  - **スレッド安全性**: `default_wait=False` 時はThreadPoolExecutorで非同期IO
  - **拡張性**: 全コンポーネントはProtocol/ABCで抽象化、DI差し替え可能
```

### ポイント

| セクション | 目的 |
|---|---|
| コンポーネント構成 | システムの構成要素と関係を図示（Mermaid推奨） |
| コンポーネント責務 | 各コンポーネントの責務とインターフェース |
| データフロー | コンポーネント間のデータの流れ（シーケンス図推奨） |
| 技術選定 | 採用技術とその理由 |
| 非機能要件方針 | 性能、セキュリティ、スケーラビリティの目標値 |

> **ARCHとSPECの書き分け基準**:
> ARCH はコンポーネント **間** の設計（外から見た構造）、
> SPEC はコンポーネント **内** の設計（中の実装方針）。
> 「このインターフェースを通じて何をやりとりするか」はARCH、
> 「このインターフェースの中でどう処理するか」はSPEC。

---

## SPEC（仕様）— How を定義する

> **プロファイルによる役割の違い:**
> - **lite**: 基本設計＋詳細設計を兼ねる（REQの直下）
> - **standard**: 詳細設計に特化する（ARCHの直下）
> - fullプロファイルではLLD（Low-Level Design）が同等の役割を担う

### テンプレート

```yaml
active: true
derived: false
group: CACHE
header: |
  mark デコレータ
level: 1.0
links:
- REQ001: <fingerprint>
normative: true
ref: ''
reviewed: null
text: |
  ## インターフェース

  ```python
  @spot.mark(
      save_blob: bool | None = None,
      keygen: KeyGen | None = None,
      version: str = "",
      content_type: ContentType = ContentType.PYTHON_OBJECT,
      serializer: SerializerProtocol | None = None,
      save_sync: bool | None = None,
      retention: str | None = None,
      hooks: list[HookBase] | None = None,
  )
  def my_func(x, y): ...
  ```

  ## 振る舞い

  ### 基本フロー

  1. デコレータが対象関数をラップする
  2. 呼び出し時にキャッシュキーを生成する
  3. DBからキャッシュを検索する
  4. **ヒット時**: デシリアライズして結果を返す（関数は実行しない）
  5. **ミス時**: 関数を実行し、結果をシリアライズしてDB/Blobに保存する

  ### sync/async 自動判定

  - `inspect.iscoroutinefunction(fn)` で判定する
  - sync関数 → `_execute_sync()` に委譲
  - async関数 → `_execute_async()` に委譲

  ## パラメータ詳細

  | パラメータ | デフォルト | 説明 |
  |---|---|---|
  | `save_blob` | `None` | `None`: StoragePolicy に委譲、`True`: 強制Blob保存、`False`: DB内保存 |
  | `keygen` | `None` | キャッシュキー生成のカスタマイズ。特定引数の除外等 |
  | `version` | `""` | バージョン文字列。変更するとキャッシュが無効化される |
  | `content_type` | `PYTHON_OBJECT` | セマンティックなコンテンツ種別 |
  | `serializer` | `None` | `None`: Spotのデフォルトを使用。関数単位でオーバーライド可能 |
  | `save_sync` | `None` | `None`: Spotのデフォルト（`default_wait`）に従う |
  | `retention` | `None` | ライフサイクルポリシーの保持期間（例: `"30d"`, `"1y"`） |
  | `hooks` | `None` | 関数単位のフックリスト |

  ## エラーハンドリング

  - ジェネレータ関数を渡した場合 → `ConfigurationError` を送出
  - シリアライズ失敗時 → `SerializationError` を送出
  - Blob保存失敗（`save_sync=False`） → ERROR ログに記録、例外は送出しない

  ## エッジケース

  - ラップされた関数の `__name__`, `__doc__`, `inspect.signature` は保持される
  - デコレータの多重適用は未定義動作とする
  - `version` が空文字の場合と未指定の場合は同一とみなす
```

### ポイント

| セクション | 目的 |
|---|---|
| インターフェース | コードレベルのAPI定義（シグネチャ） |
| 振る舞い | 処理フローをステップで記述 |
| パラメータ詳細 | 各パラメータの意味・デフォルト・挙動を表で整理 |
| エラーハンドリング | 異常系の挙動を明示 |
| エッジケース | 境界条件・未定義動作を記述 |

---

## IMPL（実装）— Where / How を記録する

### テンプレート

```yaml
active: true
derived: false
group: CACHE
header: |
  mark デコレータ実装
level: 1.0
links:
- SPEC001: <fingerprint>
normative: true
references:
  - path: src/beautyspot/core.py
    type: file
reviewed: null
text: |
  ## 実装場所

  - **モジュール**: `src/beautyspot/core.py`
  - **クラス**: `Spot`
  - **メソッド**: `mark()`, `_execute_sync()`, `_execute_async()`

  ## 設計判断

  ### デコレータパターン

  `mark()` は二段階のデコレータファクトリとして実装する:

  ```python
  def mark(self, **options):
      def decorator(fn):
          @functools.wraps(fn)
          def wrapper(*args, **kwargs):
              return self._execute_sync(fn, args, kwargs, options)
          return wrapper
      return decorator
  ```

  ### sync/async の分岐

  `mark()` 内で `inspect.iscoroutinefunction(fn)` を判定し、
  async関数の場合は `async def wrapper` を返す。
  判定は **デコレーション時**（呼び出し時ではなく）に行われる。

  ## 依存関係

  - `KeyGen` (`cachekey.py`) — キャッシュキー生成
  - `TaskDBBase` (`db.py`) — メタデータ永続化
  - `SerializerProtocol` (`serializer.py`) — シリアライズ/デシリアライズ
  - `BlobStorageBase` (`storage.py`) — 大規模データ保存
  - `ThreadPoolExecutor` (stdlib) — バックグラウンドIO

  ## 注意事項

  - `functools.wraps(fn)` により元関数のメタデータを保持すること
  - ジェネレータ判定は `inspect.isgeneratorfunction` で行う
```

### ポイント

| セクション | 目的 |
|---|---|
| 実装場所 | ファイル・クラス・メソッドの具体的な場所 |
| 設計判断 | なぜこの実装方法を選んだか（コード例付き） |
| 依存関係 | 利用する他コンポーネント |
| 注意事項 | 実装時の注意点・落とし穴 |

> **`references` フィールド**: 実装ファイルパスを `references` に設定すると、
> 1つのアイテムに対して複数のファイルを紐付けられる。
> ドメインロジックの実装ファイルのみに厳選し（最大2–3ファイル）、
> `conftest.py` や共通ユーティリティは含めない（レビュー疲れ防止）。

---

## TST（テスト）— Verify を定義する

### テンプレート

```yaml
active: true
derived: false
group: CACHE
header: |
  mark デコレータテスト
level: 1.0
links:
- SPEC001: <fingerprint>
normative: true
references:
  - path: tests/integration/core/test_mark.py
    type: file
reviewed: null
text: |
  ## テスト対象

  `@spot.mark()` デコレータの基本キャッシュ動作を検証する。

  ## テストシナリオ

  ### TC-1: 基本キャッシュ動作

  **前提条件**: 空のDBとLocalStorageが初期化されている

  1. `@spot.mark()` で関数をデコレートする
  2. 同一引数で2回呼び出す
  3. **期待結果**:
     - 1回目: 関数が実行され、結果がキャッシュされる
     - 2回目: 関数は実行されず、キャッシュから結果が返る
     - 両方の戻り値が一致する

  ### TC-2: Blobモード保存

  **前提条件**: `save_blob=True` で設定

  1. `@spot.mark(save_blob=True)` で関数をデコレートする
  2. 関数を実行する
  3. **期待結果**:
     - 結果がBlobストレージに保存される
     - DB上の `storage_type` が `DIRECT_BLOB` である

  ### TC-3: シグネチャ保持

  1. docstring と型アノテーション付きの関数をデコレートする
  2. **検証項目**:
     - `fn.__name__` が元の関数名と一致する
     - `fn.__doc__` が元のdocstringと一致する
     - `inspect.signature(fn)` が元のシグネチャと一致する

  ### TC-4: ジェネレータ関数の拒否

  1. ジェネレータ関数に `@spot.mark()` を適用する
  2. **期待結果**: `ConfigurationError` が送出される

  ### TC-5: version によるキャッシュ無効化

  1. `version="v1"` でキャッシュを作成する
  2. `version="v2"` に変更して同一引数で呼び出す
  3. **期待結果**: キャッシュミスとなり、関数が再実行される

  ## テストデータ

  - 基本テスト: `fn(x) = x * 2`, 引数 `x=3`
  - 複雑な引数: `dict`, `list`, ネストした構造体

  ## テストファイル

  - `tests/integration/core/test_mark.py`
  - `tests/unit/test_core_mark.py`（ユニットテスト）
```

### ポイント

| セクション | 目的 |
|---|---|
| テスト対象 | 何をテストするかの1行サマリ |
| テストシナリオ | 個別のテストケースを番号付きで記述 |
| 前提条件 | テストの初期状態 |
| 期待結果 | 検証すべき具体的な条件 |
| テストデータ | テストで使用するデータの概要 |
| テストファイル | 実際のテストコードの場所 |

---

## 詳細度の判断基準

全てのアイテムを最大詳細度で書く必要はない。以下の基準で判断する:

| 複雑度 | 詳細度 | 例 |
|---|---|---|
| **低** — 自明な要件 | 2-3行の簡潔な記述 | 「バージョン情報を表示するCLIコマンド」 |
| **中** — 標準的な機能 | 概要 + 受入基準/振る舞い | 「ストレージポリシーの閾値判定」 |
| **高** — 複雑なロジック | フルテンプレート | 「mark デコレータ」「キャッシュキー生成」 |

### 簡潔版の例（低複雑度）

```yaml
text: |
  `beautyspot version` コマンドで、パッケージのバージョン情報を表示する。

  - `__version__` から取得した値を `rich.Panel` で表示する
  - 引数なし、オプションなし
```

---

## Markdown 記法チートシート（text フィールド内）

```markdown
## 見出し（H2推奨、H1はheaderフィールドと重複するため避ける）

### サブ見出し

**太字** で重要な用語を強調

- 箇条書き
  - ネスト可能

1. 番号付きリスト
2. 手順の記述に適する

| 列1 | 列2 | 列3 |
|---|---|---|
| セル | セル | セル |

`インラインコード` でクラス名・関数名・パラメータ名を囲む

\```python
# コードブロック（言語指定付き）
def example():
    pass
\```

> 引用・補足情報
```

## YAML記述時の注意

- `text: |` のリテラルブロックを使う（`>` は改行が消えるため非推奨）
- インデント（2スペース）を揃えること
- コードブロック内のインデントもYAMLのインデントに加算される
- `---` (YAMLセパレータ) と Markdown の水平線が衝突するため、
  text 内では `---` の代わりに見出し (`##`) で区切る

---

## 図・画像・数式の挿入

Doorstop の `text` フィールド内で利用できるリッチコンテンツを解説する。

### レンダリング環境と対応状況

| コンテンツ | `doorstop publish -H` (HTML) | `doorstop publish -m` (Markdown) | MkDocs / GitHub |
|---|---|---|---|
| Mermaid 図 | カスタムテンプレート必要 | コードブロックのまま出力 | ネイティブ対応 |
| PlantUML 図 | ネイティブ対応（サーバー経由SVG） | コードブロックのまま出力 | プラグインで対応 |
| 画像 (`![](...)`) | 対応 | 対応 | 対応 |
| 数式 (MathJax) | ネイティブ対応 | テキストのまま出力 | プラグインで対応 |

---

### Mermaid ダイアグラム

Doorstop の Markdown 処理でフェンスドコードブロックは
`<pre><code class="language-mermaid">` として HTML 出力される。
Mermaid JS をページに読み込めば自動でレンダリングされる。

#### 書き方（text フィールド内）

````yaml
text: |
  ## アーキテクチャ

  ```mermaid
  graph TD
    A[bs.Spot] -->|DI| B[core.Spot]
    B --> C[TaskDBBase]
    B --> D[SerializerProtocol]
    B --> E[BlobStorageBase]
    B --> F[StoragePolicyProtocol]
    B --> G[LimiterProtocol]
    B --> H[LifecyclePolicy]
  ```
````

#### Mermaid で使える主な図の種類

##### フローチャート — 処理フロー・判断分岐の記述に

````yaml
text: |
  ## キャッシュ判定フロー

  ```mermaid
  flowchart TD
    Start([関数呼び出し]) --> GenKey[キャッシュキー生成]
    GenKey --> Lookup{DB検索}
    Lookup -->|ヒット| Deser[デシリアライズ]
    Deser --> Return([結果を返す])
    Lookup -->|ミス| Exec[関数実行]
    Exec --> Ser[シリアライズ]
    Ser --> Save{save_blob?}
    Save -->|true| Blob[Blobストレージに保存]
    Save -->|false| DB[DBに保存]
    Blob --> Return
    DB --> Return
  ```
````

##### シーケンス図 — コンポーネント間のやり取りに

````yaml
text: |
  ## mark デコレータ実行シーケンス

  ```mermaid
  sequenceDiagram
    participant User as ユーザーコード
    participant Mark as @spot.mark
    participant KG as KeyGen
    participant DB as TaskDB
    participant Ser as Serializer
    participant Blob as BlobStorage

    User->>Mark: fn(args)
    Mark->>KG: generate(fn, args)
    KG-->>Mark: cache_key
    Mark->>DB: lookup(cache_key)
    alt キャッシュヒット
      DB-->>Mark: cached_data
      Mark->>Ser: deserialize(data)
      Ser-->>Mark: result
    else キャッシュミス
      Mark->>Mark: fn(args) 実行
      Mark->>Ser: serialize(result)
      Ser-->>Mark: binary
      Mark->>DB: save(cache_key, metadata)
      opt save_blob=true
        Mark->>Blob: save(key, binary)
      end
    end
    Mark-->>User: result
  ```
````

##### 状態遷移図 — ステートの変化に

````yaml
text: |
  ## キャッシュエントリのライフサイクル

  ```mermaid
  stateDiagram-v2
    [*] --> Active: 関数実行＆保存
    Active --> Active: キャッシュヒット
    Active --> Expired: TTL超過
    Active --> Invalidated: version変更
    Expired --> [*]: GCで削除
    Invalidated --> Active: 再実行＆保存
    Invalidated --> [*]: GCで削除
  ```
````

##### ER図 — データモデルの記述に

````yaml
text: |
  ## メタデータDBスキーマ

  ```mermaid
  erDiagram
    TASKS {
      text task_id PK
      text func_name
      text input_key
      text version
      text content_type
      text storage_type
      blob result_data
      text blob_key
      real created_at
      real expires_at
    }
    TASKS ||--o| BLOB_STORAGE : "blob_key"
    BLOB_STORAGE {
      text key PK
      blob data
      text path
    }
  ```
````

##### クラス図 — インターフェース・継承関係に

````yaml
text: |
  ## ストレージ階層

  ```mermaid
  classDiagram
    class BlobStorageBase {
      <<abstract>>
      +save(key, data) void
      +load(key) bytes
      +delete(key) void
      +list_keys() list
    }
    class LocalStorage {
      -base_path: Path
      +save(key, data) void
      +load(key) bytes
    }
    class S3Storage {
      -bucket: str
      -prefix: str
      +save(key, data) void
      +load(key) bytes
    }
    BlobStorageBase <|-- LocalStorage
    BlobStorageBase <|-- S3Storage
  ```
````

#### Mermaid を HTML 出力でレンダリングするためのカスタムテンプレート

Doorstop のデフォルト HTML テンプレートには Mermaid JS が含まれていない。
プロジェクトにカスタムテンプレートを配置して対応する。

**手順:**

1. ドキュメントディレクトリ（例: `specification/reqs/`）に `template/` フォルダを作成する
2. Doorstop 組込テンプレート一式をコピーし、`base.tpl` に Mermaid JS を追加する

```
specification/reqs/
  template/           ← カスタムテンプレート
    base.tpl          ← Mermaid JS 追加版
    doorstop.tpl      ← 組込からコピー
    bootstrap.min.css
    ...その他アセット
  .doorstop.yml
  REQ001.yml
  ...
```

**`base.tpl` に追加するスクリプト:**

```html
<!-- base.tpl の </body> の直前に追加 -->
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({ startOnLoad: false, theme: 'default' });

  // Doorstop が出力する <pre><code class="language-mermaid"> を変換
  document.querySelectorAll('code.language-mermaid').forEach((el) => {
    const pre = el.parentElement;
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = el.textContent;
    pre.replaceWith(div);
  });

  await mermaid.run({ querySelector: '.mermaid' });
</script>
```

**HTML 出力コマンド:**

```bash
doorstop publish all output/ --html --template
```

---

### PlantUML ダイアグラム

Doorstop 3.x は `plantuml-markdown` 拡張を内蔵しており、
HTML 出力時に PlantUML サーバー経由で **自動的に SVG レンダリング** される。

#### 書き方（text フィールド内）

````yaml
text: |
  ## コンポーネント構成

  ```plantuml
  @startuml
  skinparam componentStyle rectangle

  package "beautyspot" {
    [bs.Spot] as factory
    [core.Spot] as core
    [SQLiteTaskDB] as db
    [MsgpackSerializer] as ser
    [LocalStorage] as store
  }

  factory --> core : DI
  core --> db
  core --> ser
  core --> store
  @enduml
  ```
````

#### PlantUML vs Mermaid の使い分け

| 観点 | Mermaid | PlantUML |
|---|---|---|
| HTML出力 | カスタムテンプレート必要 | Doorstop ネイティブ対応 |
| 記法の簡潔さ | シンプル | やや冗長 |
| 図の種類 | フロー/シーケンス/ER/状態/クラス/ガント | 上記に加えユースケース/アクティビティ/配置図等 |
| レンダリング | クライアントサイドJS | サーバーサイド（要ネット接続） |
| GitHub/MkDocs | ネイティブ対応 | プラグイン必要 |

**推奨**: GitHub/MkDocs での閲覧が主なら **Mermaid**、
Doorstop HTML 出力のみで完結させたいなら **PlantUML**。

---

### 画像の挿入

#### 方法1: assets ディレクトリ（推奨）

各 Doorstop ドキュメントは `assets/` サブディレクトリを持てる。
画像をここに配置し、相対パスで参照する。

```
specification/specs/
  assets/
    architecture.png
    sequence_flow.svg
  .doorstop.yml
  SPEC001.yml
```

````yaml
# SPEC001.yml
text: |
  ## システム構成図

  ![アーキテクチャ概要](assets/architecture.png)

  上図はコンポーネント間の依存関係を示す。

  ## データフロー

  ![シーケンスフロー](assets/sequence_flow.svg)
````

> **注意**: `doorstop publish` でHTML出力する場合、`assets/` ディレクトリは
> 出力先に自動コピーされる。Markdown 出力の場合は手動コピーが必要。

#### 方法2: 外部URL参照

プロジェクト外の画像やCI生成のダイアグラムを参照する場合:

````yaml
text: |
  ## CI パイプライン状態

  ![Build Status](https://img.shields.io/github/actions/workflow/status/user/repo/ci.yml)
````

#### 方法3: Base64 インライン埋め込み（小さい画像のみ）

アイコンやバッジ等、非常に小さい画像のみ推奨（ファイルサイズ肥大化に注意）:

````yaml
text: |
  状態: ![OK](data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0...)
````

#### 画像サイズの制御（HTML出力時）

Markdown の `![alt](url)` ではサイズ指定ができないため、
必要に応じて HTML タグを直接記述する:

````yaml
text: |
  ## 詳細図

  <img src="assets/detail.png" alt="詳細図" width="600">

  `markdown.extensions.extra` が有効なため、HTML タグが利用可能。
````

---

### 数式（MathJax）

Doorstop の HTML テンプレートは MathJax を内蔵しており、
LaTeX 記法の数式が自動レンダリングされる。

#### 書き方

````yaml
text: |
  ## トークンバケットアルゴリズム

  レート制限は GCRA（Generic Cell Rate Algorithm）に基づく。

  ### インライン数式

  バケットの残トークン数 $T$ は、時刻 $t$ において
  $T(t) = \min(C, T(t_0) + r \cdot (t - t_0))$ で計算される。

  ### ブロック数式

  $$
  T(t) = \min\left(C,\ T(t_0) + r \cdot (t - t_0)\right)
  $$

  ここで:

  - $C$: バケット容量（最大トークン数）
  - $r$: トークン補充レート（tokens/sec）
  - $t_0$: 前回の計算時刻
````

#### 対応状況

- **HTML出力**: MathJax でレンダリング（`$...$` インライン、`$$...$$` ブロック）
- **Markdown出力**: LaTeX テキストのまま出力（GitHub は `$$` のみ対応）

---

### 図と文章を組み合わせた実例

以下は SPEC アイテムの中で、テキスト・図・表・コードを組み合わせた実践例:

````yaml
active: true
derived: false
group: CACHE
header: |
  キャッシュ判定フロー
level: 1.1
links:
- REQ001: <fingerprint>
normative: true
ref: ''
reviewed: null
text: |
  ## 概要

  `@spot.mark()` でデコレートされた関数が呼び出された際の
  キャッシュ判定フローを定義する。

  ## 判定フロー図

  ```mermaid
  flowchart TD
    Start([fn 呼び出し]) --> HookPre[pre_execute hook]
    HookPre --> GenKey[KeyGen.generate]
    GenKey --> DB{DB lookup}
    DB -->|HIT & 未期限切れ| HookHit[cache_hit hook]
    HookHit --> Deser[deserialize]
    Deser --> Return([return result])
    DB -->|MISS or 期限切れ| Exec[fn 実行]
    Exec --> Ser[serialize]
    Ser --> Policy{StoragePolicy}
    Policy -->|BLOB| SaveBlob[BlobStorage.save]
    Policy -->|INLINE| SaveDB[DB.save]
    SaveBlob --> HookMiss[cache_miss hook]
    SaveDB --> HookMiss
    HookMiss --> Return
  ```

  ## 判定条件の詳細

  | 条件 | 結果 | 説明 |
  |---|---|---|
  | DB にレコードあり & 期限内 | キャッシュヒット | デシリアライズして返す |
  | DB にレコードあり & 期限切れ | キャッシュミス | 再実行して上書き保存 |
  | DB にレコードなし | キャッシュミス | 新規実行して保存 |
  | `version` 不一致 | キャッシュミス | 新しい version で保存 |

  ## シーケンス（キャッシュミス時）

  ```mermaid
  sequenceDiagram
    participant U as User Code
    participant S as Spot
    participant K as KeyGen
    participant D as TaskDB
    participant Sr as Serializer
    participant B as BlobStorage

    U->>S: fn(x=3)
    S->>K: generate(fn, (3,), {})
    K-->>S: "sha256:abc..."
    S->>D: find_by_key("sha256:abc...")
    D-->>S: None (miss)
    S->>S: result = fn(3)
    S->>Sr: pack(result)
    Sr-->>S: bytes
    S->>D: insert(key, metadata)
    S->>B: save("sha256:abc...", bytes)
    S-->>U: result
  ```

  ## save_blob 判定の優先順位

  1. `@spot.mark(save_blob=True)` — 明示指定（最優先）
  2. `@spot.mark(save_blob=False)` — 明示指定
  3. `save_blob=None`（デフォルト） → `StoragePolicy.should_save_as_blob(data)` に委譲

  ```python
  # 判定の擬似コード
  if explicit_save_blob is not None:
      use_blob = explicit_save_blob
  else:
      use_blob = storage_policy.should_save_as_blob(serialized_data)
  ```
````
