---
title: Declarative Lifecycle Policy
status: Proposed
date: 2026-02-18
context: Managing Data Longevity
---

# Declarative Lifecycle Policy

## Context and Problem Statement / コンテキスト

機械学習や生成AIの実験プロセスにおいて、生成されるデータの重要度は均一ではありません。数ヶ月保持すべき「最終モデル」もあれば、数時間で不要になる「一時的なデバッグ出力」もあります。

現在、これらの古いデータを削除するには、ユーザーが `MaintenanceService.prune(older_than=...)` を呼び出すスクリプトを自作し、定期実行する必要があります。これはユーザーにとって負担であり、設定を忘れるとディスク容量を圧迫する原因となります。また、`beautyspot` は常駐プロセスを持たないため、クリーンアップのトリガー設計が課題となります。

## Decision Drivers / 要求

* **Cognitive Load Reduction**: ユーザーが「Toil（苦役）」から解放され、データの寿命を宣言するだけで管理が完結すること。
* **Predictable Performance**: 有効期限の判定や削除処理が、メインの実行パスのレイテンシに悪影響を与えないこと。
* **Safety**: デフォルトではデータを無期限に保持し、意図しないデータ消失を防ぐこと。

## Considered Options / 検討

* **Option 1**: 命令的なアプローチ。ユーザーが必要に応じて削除スクリプトを記述・実行する。
* **Option 2**: 宣言的な `retention` パラメータとデータベースでの有効期限管理を導入し、アクセス時のチェック（Lazy Expiration）と CLI による一括削除を組み合わせる。

## Decision Outcome / 決定

Chosen option: **Option 2**.

ユーザーが「データの寿命（What）」を宣言するだけで済むよう、以下の仕組みを導入します。

### 1. `retention` Parameter for `@mark`
デコレータおよび `run` メソッドに `retention` 引数を追加します（例: `"7d"`, `"1h"`, `None`）。

### 2. Database Schema Change (`expires_at`)
タスク作成時に寿命を計算し、`tasks` テーブルの `expires_at` カラムに保存します。

### 3. Lazy Expiration (Access-time Check)
キャッシュ取得時（`spot.db.get`）に、`expires_at < current_time` であれば「キャッシュミス」とみなして `None` を返します。この時点では物理削除は行わず、レイテンシへの影響を最小限にします。

### 4. Explicit Garbage Collection (CLI)
期限切れデータの物理削除は、CLI コマンド `$ beautyspot gc --expired` によって一括で行います。

## Consequences / 決定

* **Positive**:
    * **認知負荷の低減**: 関数定義時に寿命を決めるだけで、後片付けを気にする必要がなくなる。
    * **パフォーマンス**: 有効期限の判定は TIMESTAMP 比較のみで高速。
    * **安全性**: デフォルトは無期限であるため、安全。
* **Negative**:
    * **容量解放の遅延**: CLI コマンドが実行されるまで、期限切れデータもディスクに残り続ける。
    * **マイグレーション**: 既存テーブルへのカラム追加が必要。
