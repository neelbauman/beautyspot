# 🗺️ beautyspot Roadmap to Maturity (Updated: 2026-02-17)

## 🎯 Vision & Goals

`beautyspot` は、開発者が手元のマシンで「試行錯誤（Trial & Error）」を高速かつ快適に行うための **「最強の補助輪」** を目指します。

---

## 🛠️ Phase 1: Feature Completion (The "Missing Pieces")

### 1.1. Multimodal Support (Audio/Video) 🎵 🎬

* **Why:** 生成AIの出力はテキストや画像に留まらず、音声 (TTS) や動画 (Video Gen) に広がっているため、これらをダッシュボードで確認可能にする必要があります。
* **Deliverables:**
* `ContentType.AUDIO_*` / `ContentType.VIDEO_*` の定義。
* Dashboard への `st.audio`, `st.video` プレビュー機能の実装。



### 1.2. Cloud Storage Expansion (GCS) ☁️

* **Why:** AWS (S3) 以外のクラウド環境を利用するユーザーに対応し、ポータビリティを高めるためです。
* **Deliverables:** `GCSStorage` クラスの実装。

### 1.3. Schema Evolution Resilience 🧬

* **Why:** 開発中はクラス定義が頻繁に変更されるため、古い構造のキャッシュ読み込みによるクラッシュを防ぎ、データを可能な限り救出する必要があるためです。
* **Deliverables:**
* `SerializationError` 時のフォールバック機構（Raw Dictとして返す）。
* マイグレーションを支援するための `version` フィールドの活用ガイド整備。

---

## 💎 Phase 2: Maturity & Stability (Polishing)

### 2.1. Documentation & Recipes 📖

* **Topics:** FastAPI / Gunicorn での運用ガイド、LangChain / LlamaIndex との統合ベストプラクティス、分散ツール（Celery/Airflow）への移行ガイドライン。

### 2.2. Robustness & Testing 🛡️

* **Focus:** 10万件以上のタスクがある場合の SQLite クエリ最適化、ディスクフルやプロセス強制終了時の耐久性検証、`msgpack` シリアライズのベンチマーク。

### 2.3. Developer Experience (DX) Improvements ✨

* **Focus:** エラーメッセージの改善（ユーザーに次のアクションを提示）、ライブラリ全体への厳格な型ヒント (`py.typed`) の適用。

---

## 🚫 Strategic Anti-Goals & Rationale

プロジェクトの哲学である「手軽さ」を守るため、以下の機能は意図的に実装しません。

### 1. Distributed Coordination (分散協調)

Redis 等を利用した分散ロックやレート制限は、`pip install` だけで動く価値を損なうため、実装しません。必要な場合は DI 機構 を通じたカスタムバックエンドの実装を推奨します。

### 2. Job Queue / Worker Management (ジョブキュー)

ジョブの配送・実行管理はフレームワークの領分であり、`beautyspot` は「関数呼び出しをフックするデコレータ」という境界線を越えません。

---

### 更新のハイライト

* **Dashboard 削除ボタンの削除:** `src/beautyspot/dashboard.py` に実装された「Delete Record」機能を完了済みとしてロードマップから外しました。
* **Anti-Goals の整理:** `cachekey.py` ですでに `msgpack` を用いた正規化が実装されているため、以前の Anti-Goal にあった「ハッシュ生成の Msgpack 化」の項目を削除しました。
* **フェーズの再構成:** 残ったタスクに優先順位をつけ、番号を振り直しました。

