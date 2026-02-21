# 32. cached_run スコープ制限の廃止

Date: 2026-02-21
Status: Accepted
Supersedes: [ADR-0014](0014-strict-scoping-for-cached-run.md)

## Context

ADR-0014 では、`cached_run` が返すラッパー関数を `with` ブロック外から呼び出した場合に
`RuntimeError` を raise する Runtime Guard パターンを導入した。

しかし、ADR-0023 で `Spot` インスタンス自体の再利用性（`with spot:` はフラッシュのみで
制限ではない）が確立されたことにより、`cached_run` のラッパーについても同様に
スコープ外での利用を妨げない方針が自然な帰結となった。

また、Runtime Guard の実装に `ContextVar` を使用していたが、
`cached_run` 呼び出しごとに新規の `ContextVar` を作成するため、
コンテキスト分離の恩恵が得られない構造になっていた。
さらに asyncio のデタッチドタスクパターンでは `reset()` が伝播せず、
`with` 外から呼べてしまうという逆効果のバグも内包していた。

## Decision

`cached_run` の Runtime Guard を廃止し、返されたラッパー関数は
`with` ブロック外でも呼び出し可能とする。

- `ContextVar`、`is_active`、`make_scoped_guard`、`_sync_guard`、`_async_guard` を削除
- `make_cached` に簡略化（`self.mark()` を適用して返すだけ）
- `try/finally` による `reset()` も不要のため削除

## Consequences

### Positive
* **シンプルな実装**: ガード層がなくなり、`cached_run` は単純な `@mark` の一括適用に帰結する。
* **バグの除去**: `ContextVar` の誤用に起因する asyncio デタッチドタスクでのガード素通りが解消される。
* **ADR-0023 との一貫性**: `Spot` インスタンスと同様に、ラッパーもスコープに縛られない利用が可能になる。

### Negative
* **誤用の検出不可**: `with` ブロック外でのラッパー使用がランタイムで検出されなくなる。
  ただし、ラッパー自体は通常の `@spot.mark()` 相当の関数であり、
  呼び出しても意図しない副作用は生じない。
