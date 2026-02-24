# データのライフサイクル管理 (Lifecycle Management)

機械学習や実験プロセスにおいて生成されるデータには、「重要度」と「寿命」があります。
`beautyspot` では、タスク定義時にデータの保持期間（Retention）を宣言することで、不要になったデータを自動的に識別し、削除候補とすることができます。

## 保持期間の設定 (Retention Policy)

### `@mark` デコレータによる指定

`@mark` デコレータの `retention` 引数を使用して、そのタスクの結果データをどのくらいの期間保持するかを指定します。

```python
import beautyspot
from beautyspot import mark

# 7日間保持（その後は再実行される）
@mark(retention="7d")
def weekly_report(data):
    return process(data)

# 12時間保持（一時的なデータ）
@mark(retention="12h")
def temporary_cache(data):
    return quick_process(data)

# 30分保持
@mark(retention="30m")
def short_lived_task(x):
    return x * 2

# 指定なし（None）は「無期限（Indefinite）」
# 明示的に retention=None と書くことも可能
@mark
def important_model(params):
    return train(params)


```

### 期間フォーマット

`retention` 引数には、以下の単位を含む文字列を指定できます。

| 単位 | 説明 | 例 |
| --- | --- | --- |
| `d` | 日 (Days) | `"7d"`, `"30d"` |
| `h` | 時間 (Hours) | `"12h"`, `"24h"` |
| `m` | 分 (Minutes) | `"30m"`, `"60m"` |

また、`datetime.timedelta` オブジェクトや、秒数（`int`）を直接渡すことも可能です。

## 🗑️ Automated Garbage Collection (Auto-Eviction)

`beautyspot` は、TTL（有効期限）が切れたデータや、上書きされて孤立したBlobファイルを物理的に削除するガベージコレクション機能を持っています。
長期間稼働するバッチ処理やWebサーバーにおいて、ストレージの無限の肥大化を防ぐために **「確率的自動エビクション（Probabilistic Auto-Eviction）」** を設定することができます。

### 設定方法

`Spot` の初期化時に `eviction_rate` (0.0 〜 1.0) を設定します。
デフォルトは `0.0`（無効）です。

```python
import beautyspot as bs

# 例: キャッシュミス（新規保存）が発生するたびに、1%の確率で自動的にゴミ掃除を行う
spot = bs.Spot("my_app", eviction_rate=0.01)

@spot.mark(retention="7d")
def daily_process(data):
    return "result"

```

### アーキテクチャの強み

この自動エビクションは、`beautyspot` の哲学である **「メインの実行ロジックを阻害しない（Non-blocking）」** ように設計されています。

1. **ゼロ・レイテンシ:** 掃除処理はバックグラウンドの別スレッドで非同期に実行されるため、関数の応答速度には一切影響しません。
2. **安全な排他制御:** 複数プロセス・複数スレッドから同時に呼び出された場合でも、内部の Try-Lock 機構により安全にスキップされるため、SQLite のロック競合（`database is locked`）を引き起こしません。

## 🧹 手動での削除 (Manual Garbage Collection)

自動エビクションを使用しない場合、期限切れとなったデータはディスクから即座には削除されません（Lazy Expiration）。
その場合、物理的な削除を行うには、CLIコマンド `gc` （またはコードからの明示的な呼び出し）を行う必要があります。

### CLI コマンド: `beautyspot gc`

`gc` コマンドを実行することで、宣言された寿命を迎えたデータが一括削除されます。

```bash
# 期限切れ（expires_at < 現在時刻）のデータを全て削除
$ beautyspot gc


```

### 運用のベストプラクティス（手動管理時）

開発サーバーや共有環境で自動エビクションを無効にしている場合は、`cron` や CI/CD パイプラインなどで定期的に `gc` コマンドを実行し、ディスク容量を確保することを推奨します。

**例: 毎日深夜3時にクリーンアップを実行する (crontab)**

```cron
0 3 * * * beautyspot gc --force
```

## 注意事項

* **アクセス時の挙動**: 期限切れのデータに対してアクセスしようとすると、データが物理的に残っていたとしても `None` (Cache Miss) として扱われ、自動的に再計算が行われます（Lazy Check）。
* **依存関係**: 親タスクが削除されても、その子タスク（依存して作られたデータ）はそれぞれの `retention` 設定に従って管理されます。子タスクの寿命が親より長い場合、子タスクは残ります。

