# 用語辞書（Glossary）スクリプトリファレンス

## 概要

`glossary.py` はプロジェクトの用語辞書を独立YAMLファイル（`specification/glossary.yml`）として管理する。
Doorstopアイテムとは別管理だが、`check` コマンドで REQ/SPEC 本文の表記ゆれを検出し、
仕様書全体の用語一貫性を保つ。

用語辞書の運用方針・設計判断については `references/concepts/glossary.md` を参照。

## glossary.yml の構造

```yaml
terms:
  - term: "キャッシュヒット"
    definition: "以前の実行結果がキャッシュに存在し、再利用される状態"
    aliases:
      - "cache hit"
    context: "CACHE"          # グループ名との対応（任意）
    code: "find_by_key() が結果を返す"  # コード上の表現（任意）

  - term: "Thundering Herd"
    definition: "同一キーの並行リクエストが同時にキャッシュミスとなる問題"
    aliases:
      - "thundering herd"
      - "スタンピード"
    context: "CACHE"
```

## コマンドリファレンス

```bash
# 基本構文
uv run python <skill-path>/scripts/core/glossary.py <project-dir> <command> [options]
```

### 用語の追加（add）

```bash
glossary.py <dir> add "キャッシュヒット" \
  -D "以前の実行結果がキャッシュに存在し再利用できる状態" \
  --aliases "cache hit" \
  --context CACHE \
  --code "find_by_key() が結果を返す"
```

| オプション | 必須 | 説明 |
|---|---|---|
| `term` | ○ | 用語名（位置引数） |
| `-D`, `--definition` | ○ | 用語の定義 |
| `--aliases` | | エイリアス（カンマ区切り） |
| `--context` | | コンテキスト（機能グループ名等） |
| `--code` | | コード上の表現（クラス名、変数名、API等） |

### 用語の更新（update）

```bash
glossary.py <dir> update "キャッシュヒット" -D "新しい定義"
glossary.py <dir> update "キャッシュヒット" --aliases "cache hit,CHit" --code "CacheManager.find()"
```

指定したフィールドのみ上書きされる。

### 用語の削除（remove）

```bash
glossary.py <dir> remove "キャッシュヒット"
```

### 全用語の一覧（list）

```bash
glossary.py <dir> list                  # 全件
glossary.py <dir> list --context CACHE  # コンテキストで絞り込み
```

### 表記ゆれ検出（check）

REQ/SPEC 本文（text, header, gherkin）をスキャンし、
正式名称ではなくエイリアスが使われている箇所を検出する。

```bash
glossary.py <dir> check
```

出力例:
```json
{
  "issues": [
    {
      "uid": "SPEC003",
      "prefix": "SPEC",
      "type": "alias_usage",
      "alias": "cache hit",
      "canonical": "キャッシュヒット",
      "message": "エイリアス 'cache hit' が使われています。正式名称 'キャッシュヒット' への統一を検討してください。"
    }
  ]
}
```

### 未使用用語の検出（unused）

定義済みだが、全ドキュメントの text/header/gherkin で一度も言及されていない用語を検出する。

```bash
glossary.py <dir> unused
```

### REQ ドキュメントへの同期（sync）

`glossary.yml` の内容を REQ ドキュメント先頭の非規範的アイテム（用語定義セクション）に
自動生成する。既存の用語定義アイテムがあれば上書きし、なければ新規作成する。

```bash
glossary.py <dir> sync
```

動作:
1. `glossary.yml` の全用語を読み込む
2. REQ ドキュメント先頭の `normative: false` かつ header が「用語定義」のアイテムを検索
3. 用語テーブル（用語 / 定義 / コード上の表現）を `text` に自動生成して更新

> **注意**: REQ の用語定義アイテムを手動で編集してはいけない。
> 用語の追加・変更は必ず `glossary.py add` / `glossary.py update` で行い、
> `sync` で REQ に反映する。

## 他ツールとの連携

| 連携先 | 方法 |
|---|---|
| `validate_and_report.py` | 将来的に `--check-glossary` オプションで統合予定 |
| [A] 新規開発フロー | 新ドメイン概念の登場時に `glossary.py add` を実行 |
| [B] 変更フロー | 用語の意味変更時に `glossary.py update` を実行 |
| [F] 初期導入フロー | 既存コードのドメイン用語を棚卸しして一括登録 |
