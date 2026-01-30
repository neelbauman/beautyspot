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

## 🚫 Strategic Anti-Goals & Rationale

プロジェクトの哲学である「手軽さ」と「堅牢性」を守るため、以下の機能は **意図的に実装しません**。これらは技術的な制約ではなく、戦略的な選択です。

### 1. Distributed Coordination (分散協調)
**What:** Redis, Memcached, Etcd 等を使用した、複数サーバー間での状態共有（分散ロック、分散レート制限）。

**Why we won't do it:**
* **DXの破壊:** 「`pip install` だけで動く」という `beautyspot` 最大の価値が損なわれる。ユーザーに Redis サーバーの構築・運用を強いることは、"Kuroko" の哲学に反する。
* **複雑性の爆発:** 分散システム特有の問題（ネットワーク分断、競合状態、レイテンシ）への対処により、コードベースのメンテナンスコストが跳ね上がる。
* **「卒業」の推奨:** 分散制御が必要なフェーズは、もはや「試行錯誤」ではない。その段階では Celery, Airflow, Kubernetes などの専用ツールへ移行（卒業）すべきである。

**Alternative (代替案):**
* **FastAPI / Gunicorn:** プロセス数でレート制限値を割る「計算による運用」を推奨する（ドキュメントでサポート）。
* **Custom Interface:** どうしても必要なユーザーのために、独自のバックエンドを注入できる DI (Dependency Injection) 機構のみを提供する。

### 2. Canonical Msgpack for Key Generation (ハッシュ生成のMsgpack化)
**What:** キャッシュキー（引数のハッシュ）の生成ロジックを、現在の JSON から Msgpack へ統一する。

**Why we won't do it:**
* **安定性の欠如:** 標準の `msgpack` 実装は辞書キーの順序を保証しないため、同じ引数でもバイナリが変化し、キャッシュミスを誘発するリスクがある。
* **実装コスト:** 再帰的な正規化処理自体は書けなくはないですが、 `beautyspot` が扱いたいデータは複雑で（カスタムクラスの中身、Set型、Numpy配列などの特殊型、etc...）。それらすべてに対してもれなく再帰的な正規化（Canonicalization）ロジックを自前で実装・維持するコストは、得られるメリット（わずかなパフォーマンス向上と統一感）に見合わない。

**Decision:**
* **Hybrid Strategy:** キー生成には「安定性」に優れた `json.dumps(sort_keys=True)` を継続利用し、データ保存には「効率」に優れた `msgpack` を利用するハイブリッド構成を維持する。

### 3. Job Queue / Worker Management (ジョブキュー)
**What:** タスクを非同期にバックグラウンドプロセスや別サーバーへ配送・実行する機能。

**Why we won't do it:**
* **Scope Creep:** これはライブラリではなく「フレームワーク」や「プラットフォーム」の領分である。`beautyspot` はあくまで「関数呼び出しをフックするデコレータ」という境界線を越えない。

