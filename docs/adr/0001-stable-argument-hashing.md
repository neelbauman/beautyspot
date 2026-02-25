---
title: Stable Hashing for Function Arguments
status: Proposed
date: 2025-11-21
context: Issue 1
---

# Stable Hashing for Function Arguments

## Context and Problem Statement / コンテキスト

`beautyspot` のコア機能である「関数のメモ化（キャッシュ）」において、関数の引数 (`args`, `kwargs`) から一意なキャッシュキーを生成する必要があります。

初期実装 (`v0.1.0`) では、`json.dumps` が失敗した場合のフォールバックとして `str((args, kwargs))` のハッシュ値を使用していました。

しかし、Pythonのデフォルトの `__str__` / `__repr__` 実装は、オブジェクトのメモリアドレス（例: `<MyObject at 0x10a...>`）を含むことが多くあります。

これにより以下の問題が発生していました：

1.  **再起動ごとのキャッシュ無効化:** プロセスを再起動するとメモリアドレスが変わり、同じ入力値でもハッシュが変わってしまう。
2.  **分散環境での不整合:** 異なるマシン（あるいは異なるプロセス）で実行した場合、キャッシュキーが一致しない。

外部ライブラリ（`joblib` 等）を使えば解決しますが、`beautyspot` は軽量な「黒子」ライブラリを目指しており、依存関係を増やしたくありません。

## Decision Drivers / 要求

* **Stability across restarts**: プロセス再起動後もキャッシュが有効に機能すること。
* **Environment Independence**: 異なるマシンや環境間でも一貫したハッシュ値が得られること。
* **Zero External Dependencies**: 軽量さを維持するため、外部ライブラリ（joblib, numpy等）に依存しないこと。
* **Broad Type Support**: `pydantic` モデルや `dataclass` 等、一般的なPythonオブジェクトを透過的に扱えること。

## Considered Options / 検討

* **Option 1**: 現状維持（`str()` によるフォールバック）。
* **Option 2**: 外部ライブラリ（`joblib` 等）の導入。
* **Option 3**: 標準ライブラリの `json` を拡張した、独自の安定化シリアライザの実装。

## Decision Outcome / 決定

Chosen option: **Option 3**.

標準ライブラリの `json` モジュールを使用し、独自の `default` シリアライザ (`_stable_serialize_default`) を実装することで、**依存関係なしで** 堅牢なハッシュ生成を実現します。

具体的には以下の戦略を採用します：

1.  **Set/Frozensetのソート:** JSONは順序を持たない集合を扱えないため、`sorted(list(obj))` でリスト化し、順序を保証します。
2.  **カスタムオブジェクトの辞書化:** `__dict__` または `__slots__` を参照し、オブジェクトの「中身の値」をシリアライズ対象とします。これにより、メモリアドレスへの依存を排除します。
3.  **Bytes型:** 16進数文字列 (`hex`) に変換します。
4.  **最終手段:** それでもシリアライズできない型（循環参照など）については、例外的に `str()` を使用します（この場合のみ不安定になるリスクを許容します）。

## Consequences / 決定

* **Positive**:
    * アプリ再起動後もキャッシュが有効に機能する（永続化の信頼性向上）。
    * `pydantic` モデルや `dataclass` も設定なしでキャッシュ可能になる。
    * 外部依存（`numpy`, `joblib` 等）を増やさずに済む。
* **Negative**:
    * 単なる `str()` 変換よりも、シリアライズ処理のオーバーヘッド（CPUコスト）がわずかに増加する。
    * 循環参照を持つオブジェクトを渡された場合の完全な解決策ではない（ただし、タスクの入力引数としては稀であると判断）。

