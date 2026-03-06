@SPEC-008
Feature: ライフサイクルポリシー
  関数名パターンに基づくデータ保持期間の管理。

  Scenario: パターンマッチによる保持期間の決定
    Given Rule("temp_*", retention="1d") が設定されている
    When  "temp_calc" という関数のキャッシュが作成される
    Then  有効期限は1日後に設定される

  Scenario: FOREVER指定による無期限保持
    Given Rule("important_*", retention=Retention.FOREVER) が設定されている
    When  "important_result" という関数のキャッシュが作成される
    Then  キャッシュは期限切れにならない

  Scenario: 期限切れタスクのガベージコレクション
    Given 有効期限を過ぎたタスクが存在する
    When  gc コマンドを実行する
    Then  期限切れタスクが削除される

  Scenario: 確率的自動エビクションによるガベージコレクション
    Given 確率 0.1% で gc が自動実行される設定がある
    When  キャッシュ保存が実行される
    Then  設定された確率に基づいて gc がトリガーされる
    And   期限切れタスクが自動的に削除される
