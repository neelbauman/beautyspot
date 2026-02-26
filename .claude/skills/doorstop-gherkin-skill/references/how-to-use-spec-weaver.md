# Spec-Weaverの使い方

### 1. 仕様とテストの紐付けルール

Doorstopの仕様書（YAML）で発番されたIDを、Gherkin（`.feature`）の **タグ** として記述することで両者を紐付けます。

**Doorstop側 (`specs/SPEC-001.yml`)**

```yaml
active: true
testable: true
text: |
  パスワードはハッシュ化して保存すること。

```

**Gherkin側 (`features/login.feature`)**

```gherkin
@SPEC-001
Feature: ユーザー認証
  Scenario: 正しいパスワードでのログイン
    Given ...

```

### 2. 監査（Audit）コマンドの実行

`audit` コマンドを使用して、仕様とテストの乖離をチェックします。

```bash
# 基本的な実行（カレントディレクトリをプロジェクトルートとする場合）
spec-weaver audit ./features

# モノレポ環境などで、Doorstopのルートディレクトリが別にある場合
spec-weaver audit ./backend/tests/features --repo-root ./docs/doorstop

# プレフィックスを変更する場合（デフォルトは "SPEC"）
spec-weaver audit ./features --prefix REQ

```

### 3. 出力例

仕様と実装に乖離がある場合、エラー（終了コード1）と共に詳細な表が出力されます。

```text
❌ テストが実装されていない仕様 (Untested Specs):
Missing Spec ID
---------------
SPEC-002

⚠️ 仕様書に存在しない孤児タグ (Orphaned Tags):
Orphaned Tag
---------------
@SPEC-003

```

乖離がない場合は、成功メッセージ（終了コード0）が出力されます。

## ⚙️ 高度な設定（テスト対象外の仕様）

「UIのカラーコード」や「ライセンス表記」など、Gherkinでの振る舞いテストが不可能な仕様は、DoorstopのYAMLファイルに `testable: false` 属性を追記することで、Spec-Weaverの監査対象から除外できます。

```yaml
# SPEC-005.yml
active: true
testable: false
text: |
  ログインボタンの背景色は青色とすること。

```
