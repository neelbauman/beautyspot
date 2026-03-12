# Code Review Report

## 設計上の懸念点 (Design Concerns)

### DC-1: `_execute_sync` と `_execute_async` の大規模な重複
**ファイル:** `core.py:686-928`

両メソッドはほぼ同一のロジック（準備 → `pre_execute` フック → キャッシュチェック → Herd 待機 → 関数実行 → 結果保存 → 通知 → eviction）を持ちますが、約240行ずつ独立して実装されています。

**トレードオフ:**
- **現状の利点:** async/sync の制御フローが明確に分離されており、個別の修正やデバッグが容易。
- **懸念:** 片方への修正がもう片方に適用漏れするリスクが常にある（BUG-4 のログメッセージ不整合が好例）。ロジック変更時に 2箇所を同期する必要がある。

---

### DC-2: `on_background_error` の名前と責務範囲のミスマッチ
名前は「バックグラウンドエラー」を示唆しますが、実際には:
- `save_sync=True` の同期パスでも発火する（BUG-3）。
- 発火すると例外伝播を抑制するため、ユーザー側のエラーハンドリングを暗黙的に迂回する。

**提案:**
- 同期保存エラーは常に例外伝播し、コールバックは**追加の通知手段**として扱う。
- または `on_save_error` に改名し、`suppress=True/False` パラメータで伝播を制御する。

---

### DC-3: `_owns_db` フラグのファクトリ↔コア間の暗黙的結合
**ファイル:** `__init__.py:118-119`, `core.py:256`

```python
# __init__.py (ファクトリ)
if db is None:
    spot._owns_db = True     # ← コンストラクタ後に外部から設定

# core.py (コンストラクタ)
self._owns_db = False        # ← デフォルト値
```

`_owns_db` は `core.Spot.__init__` でデフォルト `False` に設定され、ファクトリ関数が構築後に外部から `True` に書き換えます。これは `_ensure_bg_resources` のファイナライザ作成時にキャプチャされるため、タイミング次第で正しい値がキャプチャされない可能性があります（現在は実用上問題ないが、構造的に脆い）。

**提案:** コンストラクタの引数として渡す方が安全です。

---

### DC-4: Thundering Herd 対策がスレッドレベルに限定
**ファイル:** `cache.py:72-76`

```python
self._inflight: dict[str, tuple[threading.Event, list[asyncio.Future], list]] = {}
self._inflight_lock = threading.Lock()
```

`_inflight` はインメモリの `dict` であり、同一プロセス内のスレッド間でのみ有効です。マルチプロセス環境（Gunicorn、multiprocessing）では、複数プロセスが同一キーの関数を同時実行する可能性があります。

**トレードオフ:**
- **現状の利点:** ロック不要で高速、外部依存なし。
- **懸念:** ML パイプラインでの分散実行では Thundering Herd が問題になりうる。
- **緩和策:** SQLite を利用したプロセス間ロックは可能だが、複雑性とパフォーマンスコストが大きい。ドキュメントでの明記が最善策。

---

### DC-5: `SQLiteTaskDB` のスレッドローカル読み取り接続に上限がない
**ファイル:** `db.py:297-354`

各スレッドが初回アクセスで独自の SQLite 接続を生成し、スレッドローカルにキャッシュします。接続数の上限がないため、多スレッド環境（例: Web サーバーで数百のワーカースレッド）ではファイルディスクリプタが枯渇するリスクがあります。

**トレードオフ:**
- **現状の利点:** ロックなしで高速、実装がシンプル。
- **懸念:** スレッドプール等で大量のスレッドが使われる場合に問題化。
- **提案:** 接続プール（最大接続数付き）の導入を検討。ただし、典型的な ML パイプラインではスレッド数が限定的なため、優先度は低い。

---

### DC-6: `S3Storage` にリトライロジックがない
**ファイル:** `storage.py:375-455`

S3 操作（`upload_fileobj`, `get_object`, `delete_object`）は一時的なネットワーク障害やスロットリングで失敗する可能性がありますが、リトライロジックが実装されていません。

**トレードオフ:**
- **現状の利点:** シンプルな実装、boto3 のデフォルトリトライ（3回）に依存。
- **懸念:** デフォルトリトライでは不十分な場合（429 Too Many Requests の長時間スロットリングなど）にユーザーの対応策がない。
- **緩和策:** `s3_opts` に `config=Config(retries={'max_attempts': 10})` を渡せることをドキュメント化。

---

### DC-7: `Spot.__init__` でのスキーマ初期化（副作用のあるコンストラクタ）
**ファイル:** `core.py:247`

```python
def __init__(self, ...):
    ...
    self.cache.db.init_schema()  # ← コンストラクタ内で I/O
```

コンストラクタ内でデータベースのスキーマ初期化（ファイル作成、DDL 実行）を行っています。これによりインスタンス化自体が失敗する可能性があり、テスト時のモック化も複雑になります。

**トレードオフ:**
- **現状の利点:** ユーザーが別途 `init_schema()` を呼ぶ必要がなく、使い勝手が良い。
- **懸念:** 遅延初期化（初回アクセス時）にすれば、インスタンス化と I/O を分離できる。
- **判断:** キャッシュライブラリとして「作ったらすぐ使える」は重要なので、現状は合理的。

---

### DC-8: タイムスタンプの文字列比較の脆弱性
**ファイル:** `db.py:592-614, 658-671`

`expires_at` と `updated_at` は `_ensure_utc_isoformat` により ISO 8601 文字列として保存され、SQL の文字列比較で時間順序を判定しています。

```python
# _ensure_utc_isoformat の出力例: "2024-01-15 12:30:00+00:00"
conn.execute("DELETE FROM tasks WHERE updated_at < ?", (cutoff_str,))
```

ISO 8601 + UTC 統一であれば文字列の辞書順と時系列が一致するため、現状の実装は正しく動作します。ただし、以下のリスクがあります:
- レガシーデータで `DEFAULT CURRENT_TIMESTAMP`（タイムゾーンなし）の行がある場合、比較精度がずれる。
- SQLite は `TIMESTAMP` 型にネイティブ型がなく、文字列として格納される。

**緩和策:** `save()` で `updated_at` を明示的に設定している点は正しい判断。レガシーデータのマイグレーションスクリプトがあるとなお良い。

---

### DC-9: `dashboard.py` のモジュールレベル初期化
**ファイル:** `dashboard.py:32-35`

```python
service = MaintenanceService.from_path(DB_PATH)
atexit.register(service.close)
```

モジュール読み込み時に `MaintenanceService.from_path()` が実行され、SQLite writer thread が起動します。Streamlit はホットリロードでモジュールを再読み込みするため、前回の service の writer thread がリークする可能性があります（`atexit.register` は蓄積される）。

**提案:** `st.cache_resource` を使ってシングルトン管理する、または `__del__` / セッション管理でライフサイクルを制御する。

---

### DC-10: `CacheManager` が複数の責務を併せ持つ
**ファイル:** `cache.py:42-76`

`CacheManager` はキャッシュの CRUD、キー生成、有効期限計算、Thundering Herd 保護をすべて担っています。また `Spot` は `self.cache.db`, `self.cache.storage`, `self.cache.serializer` を介して内部コンポーネントに直接アクセスしています。

**トレードオフ:**
- **現状の利点:** 単一のコンポジションポイントで依存関係が明確。
- **懸念:** `CacheManager` の責務が増えると肥大化しやすい。特に Thundering Herd ロジックはキャッシュの CRUD とは別関心事。
- **判断:** 現状の規模では問題ないが、機能追加時に分割を検討する価値あり。

---

## 3. 良い設計判断
一方で、以下の点はよく設計されていると感じました:

- **`LocalStorage.save()` のアトミック書き込み:** `mkstemp` → `write` → `fsync` → `replace` のパターンは堅牢。
- **`_ReadConnWrapper`:** スレッドローカル接続のライフサイクルを管理し、shutdown 時の競合を防止。
- **Copy-on-Write レジストリ (`MsgpackSerializer`):** ロックフリーのリード、登録時のみロック。世代カウンタによるキャッシュ無効化も正確。
- **`WeakRef.finalize` + `atexit`:** GC とプロセス終了の両方に対応したリソース解放。
- **`_WriteTask` の状態マシン (PENDING/RUNNING/DONE/CANCELLED):** ロックベースの状態遷移で RUNNING 中のタスクキャンセルを安全に防止。
- **Canonicalization の型タグ (`cachekey.py`):** `list`/`tuple`/`set`/`frozenset` を区別し、型の違いによるキャッシュ衝突を防止。
- **`ThreadSafeHookBase` の `__init_subclass__` パターン:** サブクラスのメソッドを自動的にロック保護するメタプログラミング。

---

## 優先度まとめ

| 優先度 | ID | 分類 | 概要 |
| :--- | :--- | :--- | :--- |
| **中** | DC-1 | 設計 | sync/async の重複によるメンテナンスリスク |
| **中** | DC-2 | 設計 | `on_background_error` の命名と責務 |
| **低** | DC-3 | 設計 | `_owns_db` の結合度 |
| **低** | DC-4 | 設計 | Thundering Herd のスコープ（ドキュメント化推奨） |
| **低** | DC-9 | 設計 | Dashboard のモジュールレベル初期化 |
