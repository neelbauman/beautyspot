# Gherkin .feature 作成ガイド

## 基本構造

```gherkin
@SPEC-001         ← DoorstopのSPEC IDをタグとして付与（必須）
Feature: ユーザー認証
  ユーザーが自分のアカウントに安全にアクセスできること。

  Background:       ← 各シナリオの前提（オプション）
    Given システムが起動している

  Scenario: 正しい認証情報でのログイン成功
    Given 登録済みユーザー "alice@example.com" が存在する
    When  正しいパスワードで "/api/login" にPOSTする
    Then  ステータスコード 200 が返る
    And   レスポンスにアクセストークンが含まれる

  Scenario: 誤ったパスワードでのログイン失敗
    Given 登録済みユーザー "alice@example.com" が存在する
    When  誤ったパスワードで "/api/login" にPOSTする
    Then  ステータスコード 401 が返る
```

---

## タグの付け方

```gherkin
@SPEC-001                    # 単一SPECに対応
Feature: ...

@SPEC-002 @SPEC-003           # 複数SPECにまたがる場合
Feature: ...

@SPEC-001
  @smoke                    # 追加タグ（テスト分類）と併用可
  Scenario: ...
```

**ルール:**
- `Feature` には必ず対応する `@SPEC-xxx` タグを付ける
- 1つのfeatureファイルは原則1つの機能領域（Feature）
- Scenarioにも個別のSPECタグを付けてよい（より細かく紐づける場合）

---

## Given-When-Then の書き方原則

| キーワード | 意味 | 書き方 |
|---|---|---|
| `Given` | 前提条件・初期状態 | 「〜が存在する」「〜の状態で」 |
| `When` | 操作・イベント | 「〜する」「〜をPOSTする」 |
| `Then` | 期待結果 | 「〜が返る」「〜になる」「〜を含む」 |
| `And` / `But` | 前のキーワードの継続 | Given/When/Thenの補足 |

---

## Scenario Outline（パラメータ化）

複数の入力パターンを1つのシナリオで表現:

```gherkin
@SPEC-001
Scenario Outline: さまざまな入力での検証
  Given ユーザーが "<role>" の権限を持つ
  When  "<endpoint>" にアクセスする
  Then  ステータスコード <status> が返る

  Examples:
    | role  | endpoint      | status |
    | admin | /api/admin    | 200    |
    | user  | /api/admin    | 403    |
    | guest | /api/profile  | 401    |
```

---

## ファイル命名規則

```
features/
├── auth.feature          # 認証系
├── payment.feature       # 決済系
├── user_profile.feature  # ユーザープロフィール系
└── notification.feature  # 通知系
```

- スネークケース
- 機能ドメイン名でファイルを分割
- 1ファイルに複数のScenarioは許容（同一Featureなら）

---

## 既存コードからのGherkin逆引き例

既存テストコード（例: pytest, Jest）から変換する場合:

```python
# 既存テスト（pytest）
def test_login_success():
    response = client.post("/api/login", json={"email": "...", "password": "..."})
    assert response.status_code == 200
```

↓ Gherkin に変換

```gherkin
Scenario: ログイン成功
  Given 登録済みユーザーが存在する
  When  正しい認証情報で "/api/login" にPOSTする
  Then  ステータスコード 200 が返る
```

**変換のコツ:**
- `describe`/`context` → `Feature` または `Scenario` のグループ
- `test`/`it` → `Scenario`
- `beforeEach`/`setup` → `Background` または `Given`
- `assert`/`expect` → `Then`
