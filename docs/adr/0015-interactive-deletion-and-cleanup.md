---
title: Interactive Deletion and Cleanup Policy
status: Accepted
date: 2026-02-02
context: v2.2.6 Enhancement
---

# Interactive Deletion and Cleanup Policy

## Context and Problem Statement / コンテキスト

`beautyspot` は「試行錯誤の高速化」を掲げていますが、ユーザーが失敗した実験結果（キャッシュ）を即座に破棄する手段が Dashboard 上に存在しませんでした。
また、キャッシュ削除のロジックが `cli.py` に直接実装されており、Core API (`Spot` クラス) として提供されていないため、プログラムからの制御やテストが困難な状態でした。

加えて、削除機能を実現するには `BlobStorageBase` (Storage backend) に物理ファイルを削除するインターフェースが必要ですが、これまでの定義には `save` と `load` しか存在しませんでした。

## Decision Drivers / 要求

* **User Experience:** Dashboard 上で「結果を見て、即座に消して、やり直す」というループを実現したい。
* **Consistency:** CLI, Dashboard, Python Script すべてで同一の削除ロジックを利用したい。
* **Cleanliness:** DBレコードを消した際に、対応する Blob ファイルも確実に消去したい。

## Considered Options / 検討

* **Option 1**: 手動での削除（OS コマンドや DB の直接編集）をユーザーに委ねる。
* **Option 2**: Core API に `delete` メソッドを追加し、Storage インターフェースを拡張して、Dashboard からも操作可能にする。

## Decision Outcome / 決定

Chosen option: **Option 2**.

1. **Core API への `delete` メソッドの追加**
   `Spot.delete(cache_key)` を正式な API として追加します。このメソッドは、「DBレコードの削除」と「Blobファイルの削除」をアトミック（ベストエフォート）に行う責任を持ちます。

2. **Storage Interface への拡張**
   `BlobStorageBase` 抽象基底クラスに `delete(location)` メソッドを追加します。
   * **Breaking Change:** ユーザーが独自の Storage Backend を実装している場合、`delete` メソッドの実装が必要となります。
   * **Idempotency:** ファイルが既に存在しない場合でもエラーを送出せず、静かに終了する（冪等な挙動）ことを推奨実装とします。

3. **Dashboard への削除機能の露出**
   Dashboard に削除ボタンを配置します。誤操作を防ぐため、確認ダイアログを経由する UI とし、`Spot.delete` を呼び出します。

## Consequences / 決定

* **Positive**:
    * ユーザーは Dashboard から離れることなく、不要なキャッシュを整理できる。
    * キャッシュ削除ロジックが一元化され、メンテナンス性が向上する。
    * 将来的な「自動ローテーション」機能の基盤となる。
* **Negative**:
    * `BlobStorageBase` を継承したカスタムクラスを持つ既存ユーザーコードは、`delete` メソッドの実装が必要になる。
    * リリースノートでの周知が必須となる規模の変更である。
