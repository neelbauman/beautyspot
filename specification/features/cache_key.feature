@SPEC-002
Feature: キャッシュキー生成
  SHA-256ベースの決定論的なキャッシュキーを生成する。

  Scenario: 同一引数から同一キーが生成される
    Given 関数名 "my_func" と引数 (1, 2, 3) がある
    When  キャッシュキーを生成する
    Then  毎回同じ64文字の16進数文字列が返る

  Scenario: kwargs の順序に依存しない
    Given kwargs {"a": 1, "b": 2} と {"b": 2, "a": 1} がある
    When  それぞれのキャッシュキーを生成する
    Then  同じキーが生成される

  Scenario: KeyGen.ignore で引数を除外する
    Given keygen=KeyGen.ignore("verbose") が設定されている
    When  verbose=True と verbose=False で実行する
    Then  同じキャッシュキーが生成される
    And   キャッシュヒットとなる

  Scenario: 型の異なる引数で異なるキーが生成される
    Given 引数 1（int）と "1"（str）がある
    When  それぞれのキャッシュキーを生成する
    Then  異なるキーが生成される
