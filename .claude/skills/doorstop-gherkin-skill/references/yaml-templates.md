# Doorstop YAML テンプレートリファレンス

## ⚠️ 重要: YAMLはCLIで生成する

DoorstopのYAMLファイルは **手動作成禁止**。必ず `doorstop add` で生成し、
生成されたファイルの `text` フィールドのみを編集する。

```bash
doorstop add REQ    # → reqs/REQ-001.yml を自動生成
doorstop edit REQ-001  # → エディタが開く（$EDITOR に依存）
```

---

## Doorstop addで生成されるYAMLの初期構造

```yaml
active: true
derived: false
header: ''
level: 1.0
links: []
normative: true
ref: ''
reviewed: null
text: |
  （空欄 - ここを編集する）
```

---

## REQ（ビジネス要件）の text の書き方

`text` フィールドにMarkdownで記述する（他のフィールドはDoorstopが管理するため原則変更しない）:

```yaml
text: |
  ## 概要
  （このビジネス要件の一文サマリー）

  ## 背景・動機
  （なぜこの要件が必要か。ビジネス上の課題や目標）

  ## 受け入れ基準
  - （測定可能な条件1）
  - （測定可能な条件2）
```

---

## SPEC（システム仕様）の text の書き方

```yaml
text: |
  ## 概要
  （このシステム仕様の一文サマリー）

  ## 詳細仕様

  ### 入力
  - （入力パラメータや前提条件）

  ### 処理
  - （システムが行う処理の詳細）

  ### 出力・結果
  - （期待される出力や状態変化）
```

**Spec-Weaverのテスト除外設定（カスタム属性）:**

Gherkinで **振る舞い** テストができない仕様の場合は `testable: false` を追加する。

```yaml
active: true
testable: false   # ← この行を追加するだけでSpec-Weaverが監査から除外する
text: |
  ログインボタンの背景色は #1A73E8 とすること。
```

---

## フィールド説明

| フィールド | 意味 | 注意 |
|---|---|---|
| `active` | 有効な要件か | `false` にすると削除の代わりに非表示化できる |
| `level` | 階層番号 | `1.0`終わりの非normativeはセクション見出しになる |
| `links` | 親アイテムへの参照 | `doorstop link` コマンドで自動更新。手動編集不要 |
| `normative` | 規範的か | 通常 `true`。見出し用は `false` + level を `.0` 終わりに |
| `reviewed` | レビュー済みfingerprintハッシュ | `doorstop review` で自動更新。手動編集不要 |
| `ref` | 外部参照（ファイルパスなど） | 通常は空でよい |
| `text` | 本文（Markdown） | **唯一、人間が直接編集するフィールド** |

---

## よくある操作例

```bash
# 新しい要件を追加してリンク
doorstop add REQ          # REQ-002.yml 生成
doorstop add SPEC         # SPEC-002.yml 生成
doorstop link SPEC-002 REQ-002   # リンク設定

# アイテムを非アクティブ化（削除の代わり）
# → YAML の active: false に変更（doorstop edit で）

# 現在の状態を確認
doorstop               # バリデーション実行
doorstop publish all ./specification/public  # HTML生成して確認
```

