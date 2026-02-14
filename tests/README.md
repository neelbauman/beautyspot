# Beautyspot Test Suite

`beautyspot` のテストスイート。
本プロジェクトでは、テストの保守性と実行速度を最適化するために、テストケースを以下の4つのレイヤーに分類しています。

## 📂 Directory Structure

### 1. `unit/` (Unit Tests)
**外部依存（DB, FileSystem, Network）を持たない、beautyspotの純粋なロジックのテスト**です。
これらは非常に高速に実行される必要があります。

* **主な対象:**
    * `KeyGen` / `KeyGenPolicy` のハッシュ生成ロジック
    * `TokenBucket` (Rate Limiter) の計算アルゴリズム
    * `MsgpackSerializer` のエンコード/デコード処理
* **ルール:** `Spot` インスタンスの生成や、ディスクへの書き込みは行わないでください。

### 2. `integration/` (Integration Tests)
**`Spot` クラスを中心とした、コンポーネント間の連携動作を検証するテスト**です。
SQLite (DB) や ファイルシステム (Storage) と実際にやり取りを行います。

* **サブディレクトリ:**
    * `core/`: `mark`, `cached_run`, コンテキストマネージャ等の基本機能。
    * `storage/`: DBのCRUD、Blobの保存・削除、S3バックエンド等。
    * `cli/`: CLIコマンド (`beautyspot ui` 等) の動作確認。

### 3. `scenarios/` (Scenario & E2E Tests)
**ユーザーの利用シーンを想定した、より複雑または包括的なテスト**です。
複数の機能を組み合わせたケースや、非機能要件（セキュリティ、エッジケース）を扱います。

* **主な対象:**
    * `test_security.py`: パストラバーサル対策などのセキュリティ検証。
    * `test_guardrails.py`: 大規模データ警告などのガードレール機能。
    * `test_edge_cases.py`: 異常系や境界値の複合テスト。

### 4. `migration/` (Migration Tests)
**後方互換性を担保するための、一時的なテスト**です。
非推奨（Deprecated）となった機能が、警告を出しつつも動作し続けることを保証します。

* **運用:** メジャーバージョンアップ（例: v3.0）で該当機能が削除される際、このディレクトリ内のテストも削除されます。
* **例:** `input_key_fn` パラメータから `keygen` パラメータへの移行テスト。

---

## 🚀 Running Tests

プロジェクトには `uv` を使用しています。ルートディレクトリから以下のように実行してください。

### 全テストの実行
```bash
uv run pytest

```

### 特定のレイヤーのみ実行

ロジック修正時の高速フィードバックループに便利です。

```bash
uv run pytest tests/unit

```

### 互換性チェックのみ実行

```bash
uv run pytest tests/migration

```

---

## 🛠 Guidelines for Contributors

1. **New Tests**:
* 新しいロジック（関数・クラス）を追加した → **`unit/`**
* `Spot` の新しいオプションやDB操作を追加した → **`integration/`**
* バグ修正（再現テスト）や、特定のワークフローの検証 → **`scenarios/`**

2. **Performance**:
`integration` や `scenarios` のテストはディスクI/Oを伴うため、不必要にループ回数を増やさないよう注意してください。

