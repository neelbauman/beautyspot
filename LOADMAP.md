# 🗺️ beautyspot Roadmap to Maturity

## 🎯 Vision & Goals

**"The Ultimate Local Development Companion"**

`beautyspot` は、大規模分散システムの構築を目指すのではなく、開発者が手元のマシンで「試行錯誤（Trial & Error）」を高速かつ快適に行うための **「最強の補助輪」** であることを目指します。

今後の開発は、以下の2つのフェーズで進行します。

1.  **Phase 1: Feature Completion (v1.0.0 - v1.2.0)**
    * ローカル開発ツールとして「欠けている必須機能」を埋める。
2.  **Phase 2: Maturity & Stability (v1.3.0 ~)**
    * 機能追加を凍結し、堅牢性・ドキュメント・エコシステムを成熟させる。

---

## 🛠️ Phase 1: Feature Completion (The "Missing Pieces")

「生成AI / スクレイピングの試行錯誤」というユースケースにおいて、現状で不足している機能を実装しきります。

### 1.1. Multimodal Support (Audio/Video) 🎵 🎬
* **Why:** 生成AIの出力はテキストや画像に留まらず、音声 (TTS) や動画 (Video Gen) に広がっている。これらをダッシュボードで確認できないのはボトルネックである。
* **Deliverables:**
    * `ContentType.AUDIO_*` / `ContentType.VIDEO_*` の定義。
    * Dashboard (`dashboard.py`) への `st.audio`, `st.video` プレビュー機能の実装。
    * 巨大ファイルに対するストリーミング再生（または直接パス参照）の最適化。

### 1.2. CLI Maintenance Tools 🧹
* **Why:** 長期間の試行錯誤により、ローカルディスクに「使われていないBlobファイル（ゴミ）」や「古いキャッシュ」が蓄積し、容量を圧迫する。手動削除は危険である。
* **Deliverables:**
    * `beautyspot clean`: 孤立した（DBにレコードがない）Blobファイルのガベージコレクション。
    * `beautyspot prune --days <N>`: 指定期間以上経過した古いタスクデータの安全な削除。
    * CLI実装の `argparse` への移行と安全性（Dry-Run/確認プロンプト）の担保。

### 1.3. Cloud Storage Expansion (GCS) ☁️
* **Why:** AWS (S3) 以外のクラウド環境（特にデータ分析で人気のある Google Cloud Platform）を利用するユーザーに対応し、ポータビリティを高める。
* **Deliverables:**
    * `GCSStorage` クラスの実装 (`google-cloud-storage` 利用)。
    * `create_storage` ファクトリでの `gs://` プロトコルサポート。
    * 認証情報の「環境依存（ADC）」設計の徹底。

---

## 💎 Phase 2: Maturity & Stability (Polishing)

Phase 1 の完了後は、原則として**大きな新機能の追加を行いません**（Feature Freeze）。
代わりに、以下の活動を通じて「インフラとしての信頼性」を高めます。

### 2.1. Documentation & Recipes 📖
* **Integration Guides:**
    * **FastAPI / Gunicorn:** マルチプロセス環境での安全な運用方法（レート制限の考え方、マイグレーション回避策）の解説。
    * **LangChain / LlamaIndex:** これらと一緒に使う場合のベストプラクティス。
* **"Graduation" Guide:**
    * `beautyspot` でプロトタイプを作成した後、本番運用のために Celery や Airflow へ移行するためのガイドライン。

### 2.2. Robustness & Testing 🛡️
* **Usecase Test:**
    * いろんな想定ユースケースでのテスト
    * 非想定ユースケースの具体化
* **Edge Case Coverage:**
    * ディスクフル、ネットワーク遮断、プロセス強制終了時の挙動検証。
    * `weakref` によるリソース解放の確実性のテスト。
* **Performance Tuning:**
    * 大量のタスク（10万件以上）がある場合の SQLite クエリ最適化。
    * `msgpack` シリアライズ/デシリアライズのベンチマークと高速化。

### 2.3. Developer Experience (DX) Improvements ✨
* **Better Error Messages:**
    * シリアライズエラーや設定ミスが発生した際、ユーザーが「次に何をすべきか」が即座にわかるエラーメッセージへの改善。
* **Type Hinting:**
    * ライブラリ全体への厳格な型ヒント (`py.typed`) の適用と、ユーザーコードでの補完精度の向上。

---

## 🚫 Anti-Goals (What we will NOT do)

以下の機能は、プロジェクトの複雑性を増大させ、「手軽さ」を損なうため、**実装しません**。

* ❌ **Distributed Coordination:** Redis や Memcached を用いた分散ロック、分散レート制限。
* ❌ **Job Queue / Workers:** タスクを別プロセスや別サーバーに配送する機能。
* ❌ **Complex Workflow (DAGs):** タスク間の依存関係解決やスケジューリング機能。

