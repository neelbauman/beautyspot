# 40. Thread-safe LRU Cache for Serializer

## 状況・背景 (Context)
`MsgpackSerializer` は動的型生成時のメモリリークを防ぐために、内部で `OrderedDict` を用いた LRU (Least Recently Used) キャッシュを運用している。
しかし、`beautyspot` のアーキテクチャでは `Spot` インスタンスを通じたバックグラウンド保存（`wait=False`）や、Webフレームワークでのシングルトン利用など、マルチスレッド環境からの並行アクセスが日常的に発生する。
ロックを持たない `OrderedDict` への並行操作は `RuntimeError: OrderedDict mutated during iteration` やデータの破損を引き起こす致命的なバグの温床となっていた。

## 決定事項 (Decision)
`MsgpackSerializer` の内部状態（`_subclass_cache` およびレジストリ）に対するすべての読み書き操作を `threading.Lock()` で保護する。

## 理由 (Rationale)
1. **安定性の優先**: 稀に発生するクラッシュはデバッグが極めて困難であり、ライブラリの信頼性を著しく損なうため、確実な排他制御が不可欠である。
2. **パフォーマンスへの影響の最小化**: ロックの範囲は「型の解決とキャッシュの更新」というメモリアクセス領域に限定し、シリアライズ処理そのもの（I/Oやエンコード計算）はロック外で実行する。これにより、並行処理スループットの低下を最小限に抑えつつスレッドセーフ性を担保できる。

## 結果 (Consequences)
- **Positive**: `MsgpackSerializer` をシングルトンとして安全にマルチスレッド環境で使い回せるようになった。
- **Negative**: 型の初回解決時やキャッシュヒット時のロック取得により、ごくわずかなオーバーヘッドが追加されるが、実用上問題ないレベルであると判断した。
