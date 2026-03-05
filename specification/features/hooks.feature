@SPEC-009
Feature: ライフサイクルフック
  タスク実行ライフサイクルへのユーザー定義フックの介入。

  Scenario: pre_execute フックの実行
    Given pre_execute を実装したフックがある
    When  @mark(hooks=[hook]) 付き関数を実行する
    Then  関数実行前に pre_execute が呼ばれる
    And   PreExecuteContext に関数名と引数が含まれる

  Scenario: on_cache_hit フックの実行
    Given on_cache_hit を実装したフックがある
    And   キャッシュ済みの結果がある
    When  同じ引数で @mark(hooks=[hook]) 付き関数を実行する
    Then  on_cache_hit が呼ばれる
    And   CacheHitContext にキャッシュされた結果が含まれる

  Scenario: on_cache_miss フックの実行
    Given on_cache_miss を実装したフックがある
    When  キャッシュにない引数で @mark(hooks=[hook]) 付き関数を実行する
    Then  on_cache_miss が呼ばれる
    And   CacheMissContext に実行結果が含まれる
