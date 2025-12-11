---
title: Customizable Serialization Strategy with Msgpack Default
status: Accepted
date: 2025-12-03
context: v1.0.0 Release Preparation
---

# Customizable Serialization Strategy with Msgpack Default

## Context and Problem Statement / コンテキスト

現在、`beautyspot` はキャッシュデータのシリアライズ（保存）に Python 標準の `pickle` を使用している。
これには以下の重大な課題がある：

1.  **セキュリティリスク (RCE):** `pickle` は信頼できないデータを読み込む際に任意のコード実行（RCE）を引き起こす可能性があり、「共有キャッシュ」としての利用にリスクがある。
2.  **互換性:** Python のバージョンやライブラリのバージョンが変わると、クラス定義の不整合によりデシリアライズに失敗しやすい。
3.  **代替案の欠点:** 標準ライブラリの `json` は安全だが、画像などのバイナリデータを効率的に扱えず（Base64化でサイズ増）、タプルなどのPython固有型が失われる。

v1.0.0 リリースにあたり、**「デフォルトで安全（Secure by Default）」** かつ **「拡張性（Extensibility）」** のあるシリアライズ戦略が必要である。

## Decision Drivers / 要求

* **Security:** デフォルト状態で RCE のリスクを排除したい。
* **Performance:** 画像やNumpy配列などのバイナリデータを、オーバーヘッドなく高速に扱いたい。
* **Extensibility:** ユーザーが独自のクラスや特殊な型（例: `pandas.DataFrame`）を、ライブラリ側の変更なしに保存・復元できるようにしたい。
* **Developer Experience (DX):** シリアライズ失敗時に、「どのオブジェクトが原因か」と「どうすれば解決できるか」を明確に示したい。

## Considered Options / 検討

* **Option 1:** 現状維持（`pickle` のまま）。警告文で責任をユーザーに委ねる。
* **Option 2:** 標準ライブラリ `json` に一本化する。バイナリは Base64 エンコードを強制する。
* **Option 3:** `msgpack` を採用し、標準型のみサポートする。
* **Option 4:** `msgpack` を採用し、`ExtType` 機能を用いた「カスタム型登録システム」を実装する。

## Decision Outcome / 決定

Chosen option: **Option 4**.

シリアライザのバックエンドとして `msgpack` (MessagePack) を採用し、さらにユーザーが任意の型変換ロジックを注入できる `TypeRegistry` パターンを導入する。

1.  **依存関係:** `msgpack>=1.0.0` を `pyproject.toml` に追加する。
2.  **デフォルトの挙動:**
    * `pickle` はデフォルトから廃止（またはオプトイン化）する。
    * `msgpack` を使用し、安全な型のみをシリアライズする。
3.  **カスタム型の登録:**
    * `Project` クラスに `register_type(type, code, encoder, decoder)` メソッドを追加する。
    * ユーザーは、シリアライズできない型（例: カスタムクラス）に対して、一意なID (`code`) と変換関数を登録することで対応できる。
4.  **エラーハンドリング:**
    * 未登録の型に遭遇した場合、標準の `TypeError` ではなく、具体的なオブジェクト情報と `register_type` の利用を促す親切なエラーメッセージ (`SerializationError`) を送出する。

### Technical Details / 技術詳細

`msgpack` の `default` (pack時) と `ext_hook` (unpack時) を活用し、拡張型を `msgpack.ExtType` としてラップする。

```python
# Implementation Sketch

class Project:
    def __init__(self, ...):
        # ...
        self.serializer = MsgpackSerializer()

    def register_type(self, type_: type, code: int, encoder: Callable, decoder: Callable):
        """
        Register a custom serializer for a specific type.
        
        Args:
            type_: The class to handle (e.g. MyClass)
            code: Unique integer ID (0-127) for this type
            encoder: Function that converts obj -> bytes
            decoder: Function that converts bytes -> obj
        """
        self.serializer.register(type_, code, encoder, decoder)

# --- Internal ---

class MsgpackSerializer:
    def dump(self, obj):
        return msgpack.packb(obj, default=self._default_packer, use_bin_type=True)

    def load(self, data):
        return msgpack.unpackb(data, ext_hook=self._ext_hook, raw=False)

    def _default_packer(self, obj):
        # 登録済みの型なら ExtType に変換
        if type(obj) in self._encoders:
            code, encoder = self._encoders[type(obj)]
            return msgpack.ExtType(code, encoder(obj))
        
        # 未登録なら詳細なエラーを出す
        raise SerializationError(f"Object of type '{type(obj).__name__}' is not serializable...")
```

## Consequences / 結果

  * **Positive:**
      * **安全性:** `pickle` を排除することで、デフォルトでの脆弱性を解消できる。
      * **パフォーマンス:** `json` + Base64 よりも高速かつ省サイズでバイナリデータを扱える。
      * **柔軟性:** ユーザーはライブラリをフォークすることなく、必要な型（Numpy, Pandas, Custom Class）の対応を追加できる。
  * **Negative:**
      * **依存関係:** 新たに `msgpack` パッケージへの依存が発生する（ただし軽量であるため許容範囲とする）。
      * **移行コスト:** 既存の `pickle` で保存されたキャッシュデータ (`.pkl`) との互換性がなくなるため、v1.0.0 アップデート時にキャッシュクリア（DBリセット）が必要になる。

## Updates (2025-12-11)
See [ADR-0009](0009-msgpack-everywhere-and-guardrails.md) for further refinements regarding `save_blob=False` behavior (Msgpack + Base64) and size guardrails.

