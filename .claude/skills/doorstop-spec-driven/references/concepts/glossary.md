# 用語辞書（Glossary）の運用

## 概要

用語辞書は DDD（ドメイン駆動設計）における**ユビキタス言語（Ubiquitous Language）** の
実践手段である。プロジェクト固有の用語を一箇所に定義し、
仕様書・コード・テスト・ドキュメント全体で同じ言葉を同じ意味で使うことを保証する。

## なぜ必要か

- **仕様の曖昧さ防止**: 「キャッシュ」「保存」「永続化」が別々の意味で使われると、仕様の解釈がブレる
- **オンボーディング加速**: 新しい開発者がドメイン用語を一箇所で学べる
- **エージェントの精度向上**: AIエージェントが用語の正確な定義を参照できる

## 管理方法

用語辞書は **`specification/glossary.yml`** を唯一の真実の源（Single Source of Truth）として管理する。

```yaml
# specification/glossary.yml
terms:
  - term: "キャッシュヒット"
    definition: "以前の実行結果がキャッシュに存在し、再利用される状態"
    aliases: ["cache hit"]
    context: "CACHE"
    code: "find_by_key() が結果を返す"

  - term: "Spot"
    definition: "キャッシュエンジンのインスタンス。関数のキャッシュ管理を担う"
    aliases: []
    context: "CACHE"
    code: "bs.Spot(...), core.Spot"
```

### REQ ドキュメントへの自動生成

`glossary.yml` から REQ ドキュメント先頭の非規範的アイテム（用語定義セクション）を
自動生成する。手動で REQ 内の用語定義を編集してはならない。

```bash
# glossary.yml → REQ 先頭の非規範的アイテムに同期
glossary.py <dir> sync
```

`sync` コマンドは以下を行う:
1. `glossary.yml` の全用語を読み込む
2. REQ ドキュメント先頭の用語定義アイテム（`normative: false`）を検索（なければ作成）
3. 用語テーブルをアイテムの `text` に自動生成して上書き

これにより、用語の追加・変更は常に `glossary.yml` で行い、
REQ ドキュメントの用語定義は自動的に最新状態に保たれる。

## 運用ルール

### 新規用語の追加タイミング

- **[A] 新規開発時**: 新しいドメイン概念が登場したとき
- **[F] 初期導入時**: 既存コードのドメイン用語を棚卸しするとき
- **[B] 変更時**: 既存の用語の意味が変わるとき（旧定義も注記として残す）

### 用語辞書の更新手順

1. `glossary.py add` / `glossary.py update` で `glossary.yml` を更新する
2. `glossary.py sync` で REQ ドキュメントの用語定義アイテムに反映する
3. `glossary.py check` で仕様書本文の表記ゆれを検出する

### コード上の命名との一致

`glossary.yml` の `code` フィールドにコード上のクラス名・メソッド名・変数名を記録し、
用語とコードの対応を明示する。

### 規模別の運用

| 規模 | 方法 |
|---|---|
| 小規模（lite） | `glossary.yml` に全用語を列挙。`sync` で REQ に反映 |
| 中規模（standard） | `glossary.yml` の `context` フィールドでグループ別に分類 |
| 大規模（full） | `glossary.yml` + 必要に応じて外部ドキュメントから参照 |
