# 図表・画像・数式ガイド

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
groups:
  - CACHE
header: |
  キャッシュ判定フロー
level: 1.1
links:
- REQ001: <fingerprint>
normative: true
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
