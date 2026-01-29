---
title: Decorator-based Type Registration with Late Binding
status: Accepted
date: 2026-01-29
context: Enhancing Developer Experience (DX) for Serialization
---

# Decorator-based Type Registration with Late Binding

## Context and Problem Statement

これまでの `spot.register_type()` は命令的であり、クラス定義と登録ロジックが分離してしまうため、凝集度が低いという課題があった。
また、Pydantic モデルのようなクラスメソッド（例: `cls.model_validate_json`）をデコーダとして登録したい場合、デコレータ評価時にはまだクラスが未定義（NameError）であるため、綺麗に記述できないという技術的な制約があった。

## Decision Drivers

* **Developer Experience (DX):** クラス定義の直上にシリアライズ設定を記述したい（Co-location）。
* **Support for Modern Libraries:** Pydantic など、クラスメソッドをファクトリとして使用するパターンを容易にサポートしたい。
* **Safety:** 循環参照や未定義エラーを回避しつつ、型安全に登録を行いたい。

## Decision Outcome

`Spot` クラスに `register` デコレータメソッドを追加し、**`decoder_factory` による遅延バインディング** を導入する。

### Technical Details

```python
@spot.register(
    code=10,
    encoder=lambda obj: ...,
    decoder_factory=lambda cls: cls.deserialize  # Class is passed here after definition
)
class MyModel:
    ...

```

1. `register` デコレータは、対象クラスの定義完了後（デコレート時）に実行される。
2. `decoder_factory` が指定されている場合、生成された `cls` オブジェクトを引数としてファクトリを実行し、実際の `decoder` 関数を取得する。
3. 取得した `decoder` を用いて、既存の `register_type` バックエンドに登録する。

## Consequences

* **Positive:**
* ユーザーはクラス定義と登録を1箇所にまとめられる。
* 自己参照を含むクラス（自分自身を返すクラスメソッドなど）の登録が容易になる。


* **Negative:**
* `decoder` と `decoder_factory` という2つの引数が増え、APIが少し複雑になる（ドキュメントでの補完が必要）。

