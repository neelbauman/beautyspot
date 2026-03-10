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
groups:
  - CACHE
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

## 見出し・コンテキスト（Non-normative）— 文脈を提供する

`normative: false` を設定することで、システム要件ではなく「人間が読むための章見出しや背景説明」としてアイテムを定義できます。

### テンプレート

```yaml
active: true
derived: false
groups:
  - CACHE
header: |
  キャッシュシステム概要
level: 1.0
links: []
normative: false
ref: ''
reviewed: null
text: |
  本章では、システムのパフォーマンス向上のためのキャッシュレイヤーの要件を定義する。

  ## 目的
  計算コストの高い関数の結果を再利用することで、全体のスループットを向上させる。

  ## 用語定義
  - **キャッシュヒット**: 保存された結果を再利用すること
  - **キャッシュミス**: 結果が未保存のため、関数を再実行すること
```

### ポイント
- ドキュメントをフラットなリストにせず、`level: X.0` と組み合わせて章立てを作るために使用します。
- `normative: false` のアイテムはカバレッジやリンク検証の対象から外れるため、`links` が空でもエラーになりません。

---

## ARCH（基本設計）— Architecture を定義する（standardプロファイル）

ARCHはコンポーネント分割、コンポーネント間インターフェース、データフロー、
技術選定を定義する。「何を作るか」ではなく「どう構成するか」に焦点を当てる。
fullプロファイルではHLD（High-Level Design）が同等の役割を担う。

### テンプレート

```yaml
active: true
derived: false
groups:
  - CACHE
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
groups:
  - CACHE
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

## IMPL（実装）— 実装の生きた記録

IMPLは単なる「何を実装したか」のリストではなく、**実装ジャーナル**として機能する。
設計判断の根拠、実装中の気づき、将来の課題、仕様へのフィードバックを記録し、
コードだけでは伝わらない知識を保持する。

### `references` と `text` の役割分担

| | `references` | `text` |
|---|---|---|
| **粒度** | ファイルレベル（最大2–3ファイル） | クラス・メソッド・関数レベル |
| **対象読者** | ツール・トレーサビリティレポート | 開発者・レビュアー |
| **答える問い** | 「どのファイルを見ればいいか？」 | 「そのファイルの中の何を、なぜそう実装したか？」 |
| **データ性質** | 構造化ポインタ（機械可読） | 自由記述の知識（人間可読） |

`references` はファイルレベルに留め、クラス/メソッド/関数の詳細は `text` に記述する。
ファイルパスは安定的だが、クラス・メソッド名はリファクタリングで変わりやすい。
構造化フィールドに入れると更新負荷が高いため、`text` に柔軟に記述する方が適切である。

### テンプレート

```yaml
active: true
derived: false
groups:
  - CACHE
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
  ## 実装概要

  `Spot.mark()` メソッドが本仕様の中核。二段階デコレータファクトリとして、
  `_execute_sync()` と `_execute_async()` に処理を委譲する。
  sync/async の判定は**デコレーション時**に `inspect.iscoroutinefunction()` で行い、
  呼び出し時の判定オーバーヘッドを回避している。

  ## 設計判断

  ### 二段階デコレータファクトリの採用

  `mark()` がオプションを受け取り、内部の `decorator()` が実際のラッピングを行う。
  `@mark` (括弧なし) と `@mark()` (括弧あり) の両方をサポートするため、
  引数の型で分岐するパターンを採用した。

  ### sync/async 分岐のタイミング

  デコレーション時に判定する方式を採用。呼び出し時に毎回判定する方式と比較し、
  ランタイムオーバーヘッドがゼロになる利点がある。ただし、デコレーション後に
  関数の性質が変わるケース（動的に async に切り替える等）には対応できない。

  ## 実装メモ

  - ジェネレータ判定は `isgeneratorfunction` と `isasyncgenfunction` の
    両方をチェックする必要がある（async generator も拒否対象）
  - `functools.wraps(fn)` により `__name__`, `__doc__`, `__module__`,
    `__qualname__`, `__annotations__` が保持される。ただし
    `inspect.signature` の保持は `__wrapped__` 属性による

  ## TODO / 技術的負債

  - デコレータの多重適用時の挙動が未定義（検出・警告の追加を検討）
  - `@mark` 括弧なし記法のテストカバレッジが不足

  ## 仕様への遡上事項

  - `version=""` と `version` 未指定の扱いが SPEC001 で曖昧
    → 現実装では同一として扱っているが、明示的な仕様化が望ましい
```

### ポイント

| セクション | 目的 | 必須度 |
|---|---|---|
| 実装概要 | クラス・メソッドレベルの実装場所と処理の流れ | 必須 |
| 設計判断 | なぜこの実装方法を選んだか。代替案と棄却理由 | 必須 |
| 実装メモ | 実装中の気づき、工夫、ハマった点 | 推奨 |
| TODO / 技術的負債 | 既知の改善点、将来の課題 | 該当時 |
| 仕様への遡上事項 | 実装中に発覚したSPEC/ARCHの不備・曖昧さ | 該当時 |

> **`references` フィールド**: 実装ファイルパスを `references` に設定すると、
> 1つのアイテムに対して複数のファイルを紐付けられる。
> ドメインロジックの実装ファイルのみに厳選し（最大2–3ファイル）、
> `conftest.py` や共通ユーティリティは含めない（レビュー疲れ防止）。
> クラス・メソッド名は `references` に含めず、`text` の実装概要に記述する。

---

## TST（テスト）— Verify を定義する

TSTは3層構造で記述する。全TSTに「目的」と「検証観点」を必須とし、
複雑度が高いTSTには「主要シナリオ（TC-N）」を追加する。

### テンプレート（複雑度「高」の場合）

```yaml
active: true
derived: false
groups:
  - CACHE
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
  ## 目的

  `@spot.mark()` はユーザーが最も頻繁に使う公開APIであり、
  キャッシュの正確性・透過性・拡張性の基盤となる。
  デコレーションによって元の関数の挙動やメタデータが損なわれると、
  ユーザーコードのデバッグや型チェックに支障をきたすため、
  ラッパーの透過性を厳密に検証する。

  ## 検証観点

  - **正常系**: 同一引数での2回目呼び出しでキャッシュヒットし、
    元の関数が再実行されないこと
  - **Blobモード**: `save_blob=True` 指定時にBlobストレージ経由で
    保存されること
  - **ラッパー透過性**: `__name__`, `__doc__`, `inspect.signature` が
    元の関数と一致すること
  - **キャッシュ無効化**: `version=` を変更するとキャッシュキーが変わり、
    既存キャッシュがヒットしなくなること

  ## 主要シナリオ

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
     - DB上の `storage_type` が `FILE` である

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
```

### テンプレート（複雑度「中〜低」の場合）

```yaml
text: |
  ## 目的

  `TokenBucket` のレート制御が不正だと、APIの過負荷や
  スループットの不必要な低下を招く。GCRA アルゴリズムの
  スムーズなレート制御を検証する。

  ## 検証観点

  - **初期化バリデーション**: rate ≤ 0 等の不正パラメータが拒否されること
  - **max_cost 超過拒否**: バケット容量を超えるリクエストが即座に拒否されること
  - **GCRA 待機動作**: トークン補充まで適切な時間だけ待機すること
  - **バースト許容**: 容量分のリクエストがバーストで処理できること
```

### ポイント

| セクション | 目的 | 必須度 |
|---|---|---|
| 目的 | なぜこのテストが必要か（リスク・影響） | 必須 |
| 検証観点 | 何を確認するか（観点の箇条書き） | 必須 |
| 主要シナリオ | 具体的なTC-N（前提条件・手順・期待結果） | 複雑度「高」のみ |

### 複雑度の判断基準

| 複雑度 | 構成 | 例 |
|---|---|---|
| **低** | 目的 + 検証観点（3-4項目） | Retention パース、CLI version コマンド |
| **中** | 目的 + 検証観点（5-7項目） | ストレージポリシー、LifecyclePolicy |
| **高** | 目的 + 検証観点 + 主要シナリオ（TC-N） | mark デコレータ、LocalStorage、Thundering Herd |

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

## 図表・画像・数式の挿入

図表（Mermaid、PlantUML）、数式（MathJax）、および画像の挿入方法やレンダリング環境（カスタムHTMLテンプレートの設定など）については、別紙 [図表・画像・数式ガイド](./diagram_and_image_guide.md) を参照してください。
