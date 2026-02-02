# 15. Interactive Deletion and Cleanup Policy

* Status: Accepted
* Date: 2026-02-02
* Context: v2.2.6

## Context and Problem Statement

`beautyspot` は「試行錯誤の高速化」を掲げているが、ユーザーが失敗した実験結果（キャッシュ）を即座に破棄する手段が Dashboard 上に存在しなかった。
また、キャッシュ削除のロジックが `cli.py` に直接実装されており、Core API (`Spot` クラス) として提供されていないため、プログラムからの制御やテストが困難な状態だった。

加えて、削除機能を実現するには `BlobStorageBase` (Storage backend) に物理ファイルを削除するインターフェースが必要だが、これまでの定義には `save` と `load` しか存在しなかった。

## Decision Drivers

* **User Experience:** Dashboard 上で「結果を見て、即座に消して、やり直す」というループを実現したい。
* **Consistency:** CLI, Dashboard, Python Script すべてで同一の削除ロジックを利用したい。
* **Cleanliness:** DBレコードを消した際に、対応する Blob ファイルも確実に消去したい。

## Decision

1. **Core API への `delete` メソッドの追加**
   `Spot.delete(cache_key)` を正式な API として追加する。このメソッドは、「DBレコードの削除」と「Blobファイルの削除」をアトミック（ベストエフォート）に行う責任を持つ。

2. **Storage Interface への破壊的変更**
   `BlobStorageBase` 抽象基底クラスに `delete(location)` メソッドを追加する。
   * **Breaking Change:** ユーザーが独自の Storage Backend を実装している場合、`delete` メソッドの実装が必須となる。
   * **Idempotency:** ファイルが既に存在しない場合でもエラーを送出せず、静かに終了する（Idempotentな挙動）ことを推奨実装とする。

3. **Dashboard への削除機能の露出**
   Dashboard に削除ボタンを配置する。誤操作を防ぐため、確認ダイアログ（Popover）を経由する UI とし、`Spot.delete` (相当のロジック) を呼び出す。

## Consequences

### Positive
* ユーザーは Dashboard から離れることなく、不要なキャッシュを整理できる。
* キャッシュ削除ロジックが一元化され、メンテナンス性が向上する。
* 将来的に「古いキャッシュの自動ローテーション」などの機能を実装する際の基盤となる。

### Negative
* `BlobStorageBase` を継承したカスタムクラスを持つ既存ユーザーコードは、`delete` メソッド未実装により `TypeError` となる可能性がある（v2.x のパッチバージョンでの変更としては大きいため、リリースノートでの周知が必須）。
