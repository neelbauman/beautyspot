---
title: Protocol-based Serializer Registration
status: Accepted
date: 2026-02-17
context: Decoupling Core from Concrete Serializer Implementation
---

# Protocol-based Serializer Registration

## Context and Problem Statement / コンテキスト

`beautyspot` では、`@spot.register` デコレータを使用してカスタム型を登録できます。
当初の実装では、`Spot` クラス内でシリアライザが `MsgpackSerializer` のインスタンスであるかどうかを明示的にチェックしていました。

```python
if isinstance(self.serializer, MsgpackSerializer):
    self.serializer.register(...)
```

これは、高レベルの `Spot` クラスを特定の具象クラス (`MsgpackSerializer`) に結合させており、依存関係逆転の原則 (Dependency Inversion Principle) に違反していました。その結果、カスタム型登録をサポートする他のシリアライザ（将来的な `JsonSerializer` やカスタムラッパーなど）を使用することが不可能でした。

## Decision Drivers / 要求

* **Decoupling**: `Spot` クラスを特定のライブラリ（`msgpack`）や実装から切り離すこと。
* **Extensibility**: ユーザーが独自のシリアライザを実装し、かつカスタム型登録機能も維持できるようにすること。
* **Interface Segregation**: 基本的なシリアライズ機能と、型登録機能という異なる責務を明確に分離すること。

## Considered Options / 検討

* **Option 1**: 具象クラスに対する `isinstance` チェックを維持する。
* **Option 2**: 構造的部分型（Protocol）を導入し、インターフェースに基づくチェックに切り替える。

## Decision Outcome / 決定

Chosen option: **Option 2**.

`beautyspot.serializer` に **`TypeRegistryProtocol`** を導入します。

1. **Define Protocol**: 型登録に必要な `register` メソッドのシグネチャを規定するプロトコルを定義します。
2. **Decoupling**: `Spot` クラスは、具象クラスではなくこのプロトコルに対して適合性チェックを行うように変更します。
3. **Interface Segregation**: 基本的な `SerializerProtocol` (dump/load) と `TypeRegistryProtocol` を分離し、型登録をサポートしないシリアライザも許容できるようにします。

## Consequences / 決定

* **Positive**:
    * コアロジックが `msgpack` から解放され、`TypeRegistryProtocol` に従う任意のシリアライザを使用可能になった。
    * モックを使用したテストが容易になった。
* **Negative**:
    * シリアライザの実装者は、プロトコルで定義された `register` メソッドのシグネチャを正確に遵守する必要がある。
