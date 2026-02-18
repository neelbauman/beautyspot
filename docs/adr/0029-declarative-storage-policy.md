# 29. Declarative Storage Policy

Date: 2026-02-18
Status: Accepted

## Context
これまでの `beautyspot` では、関数の実行結果をBlobストレージ（ファイル）に保存するか、DBのレコードに直接埋め込むかは、ユーザーが `save_blob=True` フラグで明示的に指定する必要があった。
また、データサイズが大きい場合に警告を出す機能 (`blob_warning_threshold`) はあったが、自動的に対処する機能はなかった。
これにより、ユーザーはデータのサイズを予測してフラグを管理する「How」の負担を強いられていた。

## Decision
ストレージ保存方式の決定ロジックを抽象化した `StoragePolicy` プロトコルを導入し、宣言的な設定を可能にする。

1. **StoragePolicy Interface**:
    * `should_save_as_blob(data: bytes) -> bool` を持つプロトコルを定義する。
    * 配置場所は `src/beautyspot/storage.py` とし、ストレージ関連の責務を凝集させる（`KeyGenPolicy` とは混ぜない）。

2. **Standard Implementations**:
    * `ThresholdStoragePolicy`: 指定したバイト数を超えた場合にBlob保存を選択する（推奨デフォルト）。
    * `WarningOnlyPolicy`: 従来動作互換。Blob化はせず、閾値超えでログ警告のみ行う。

3. **Configuration**: `Spot` 初期化時に `storage_policy` 引数で注入可能にする。

4. **Precedence (優先順位)**:
    * Level 1 (最強): 関数ごとの指定 (`@mark(save_blob=...)`) - ユーザーが意図を持って指定した場合は常に最優先。
    * Level 2 (デフォルト): ポリシーによる自動判定 (`storage_policy.should_save_as_blob(...)`)

## Consequences
### Positive
* ユーザーは「1MB以上はBlob」というルール（What）を定義するだけで、個々の関数のデータサイズを気にせず最適化できる。
* DBの肥大化を自動的に防げる。
* `KeyGenPolicy` と配置を分けることで、モジュールの役割分担（Identity vs Persistence）が明確に保たれる。

### Negative
* シリアライズ後のデータサイズを見てから判定するため、一度メモリ上に全データを展開する必要がある。
* `Spot` クラスのコンストラクタ引数が増えるため、移行期間中は `blob_warning_threshold` 等の旧引数との共存・非推奨警告の管理が必要になる。

