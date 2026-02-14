# 18. Per-Task Serializer Override

## Context
プロジェクト全体としては安全性と互換性の観点から `msgpack` を標準シリアライザとしている。
しかし、探索的データ分析（EDA）やプロトタイピング、あるいは `msgpack` でのシリアライズが困難なサードパーティ製オブジェクトを扱う特定のタスクにおいては、Python標準の `pickle` のような柔軟なシリアライザを局所的に使用したいというニーズがある。

## Decision
1.  **Override Mechanism:** `Spot.mark()` および `Spot.cached_run()` に、オプショナル引数 `serializer` を追加する。
2.  **Protocol:** ユーザーは `dumps(obj) -> bytes` および `loads(bytes) -> obj` メソッドを持つ任意のオブジェクトを渡すことができる。
3.  **Fallback Behavior:** 指定されたシリアライザでデシリアライズに失敗した場合（例: `pickle.UnpicklingError`, `AttributeError`）、ADR-0003 の方針に従い、キャッシュ破損として扱い、タスクを再実行する。

## Consequences
* **Pros:**
    * ユーザーはプロジェクト全体の設定を変更することなく、必要な箇所だけで `pickle` 等の強力なシリアライズ機能を利用できる。
    * クラス定義の変更などでキャッシュが読み込めなくなった場合も、自動的に再計算されるため、開発体験（DX）が損なわれない。
* **Cons:**
    * `pickle` を使用したタスクは、異なるPython環境間や長期間の保存において互換性が保証されない（ユーザー責任となる）。
    * `Spot.register()` で登録したカスタム型変換は、オーバーライドされたシリアライザ（例: `pickle`）には適用されない。
