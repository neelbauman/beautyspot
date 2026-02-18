# 31. Declarative Lifecycle Policy

Date: 2026-02-18
Status: Proposed

## Context
機械学習や生成AIの実験プロセスにおいて、生成されるデータの重要度は均一ではない。
数ヶ月保持すべき「最終モデル」もあれば、数時間で不要になる「一時的なデバッグ出力」もある。

現在、これらの古いデータを削除するには、ユーザーが `MaintenanceService.prune(older_than=...)` を呼び出すスクリプトを自作し、cron等で定期実行する必要がある（Imperative/命令的アプローチ）。
これはユーザーにとって「Toil（苦役）」であり、設定を忘れるとディスク容量を圧迫する原因となる。

また、`beautyspot` は分散システムではないため、バックグラウンドで常にクリーンアップを行う常駐ワーカープロセスを持たない。そのため、データ削除のトリガーをどのように設計するかが課題となる。

## Decision

ユーザーが「データの寿命（What）」を宣言するだけで済むよう、以下の仕組みを導入する。

### 1. `retention` Parameter for `@mark`
デコレータおよび `run` メソッドに `retention` 引数を追加する。

```python
# 文字列による指定（パースしてtimedeltaに変換）
@spot.mark(retention="7d")  # 7日間保持
def weekly_report(): ...

@spot.mark(retention="1h")  # 1時間のみ保持（一時データ）
def quick_debug(): ...

# None は「無期限（Indefinite）」を意味する（デフォルト）
@spot.mark(retention=None)
def gold_dataset(): ...

```

### 2. Database Schema Change (`expires_at`)

タスク作成時に寿命を計算し、DBに静的に保存する。これにより、読み込み時やGC時の計算コストをゼロにする。

* **変更点:** `tasks` テーブルに `expires_at` (TIMESTAMP, Nullable) カラムを追加し、Indexを貼る。
* **ロジック:** `expires_at = created_at + retention`

### 3. Lazy Expiration (Access-time Check)

キャッシュ取得時（`spot.db.get`）に、有効期限をチェックする。

* **挙動:**
* `expires_at < current_time` の場合、そのタスクは「存在しない（Cache Miss）」とみなして `None` を返す。
* **Note:** この時点では物理削除は行わない（読み込み処理のレイテンシ悪化を防ぐため、または非同期削除のみ試みる）。



### 4. Explicit Garbage Collection (CLI)

期限切れデータの物理削除は、CLIコマンドによって一括で行う。

```bash
# 期限切れ（expires_at < NOW）のタスクを全て削除
$ beautyspot gc --expired

```

これにより、ユーザーは `beautyspot gc --expired` を適当なタイミング（開発の合間やCIの前後）に叩くだけで良くなり、複雑な条件指定（`older_than` 等）から解放される。

## Consequences

### Positive

* **Cognitive Load Reduction:** ユーザーは関数定義時に「これは一時データ」と決めるだけでよく、後片付けを気にする必要がなくなる。
* **Performance:** 有効期限の判定は `TIMESTAMP` 比較のみで高速。
* **Safety:** デフォルトは `None`（無期限）であるため、意図せずデータが消えることはない。

### Negative

* **Storage Consumption:** Lazy Expiration を採用するため、実際に `beautyspot gc` コマンドが実行されるまでは、期限切れのデータもディスク上に残り続ける（容量は即時には解放されない）。
* **Migration Required:** 既存の `tasks` テーブルへのカラム追加マイグレーションが必要。

## Alternatives Considered

* **Auto-Deletion on Write:** 新しいタスクを保存するたびに、確率的（例: 1%の確率）にクリーンアップを走らせる案。
* -> **却下:** 保存処理（`save`）のレイテンシが予測不能になり、ユーザー体験を損なうため。

