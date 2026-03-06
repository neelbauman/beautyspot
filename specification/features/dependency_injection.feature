@SPEC-015
Feature: 依存性の注入（DI）
  Spotファクトリによる各コンポーネントの柔軟な構成とDI。

  Scenario: デフォルト設定でのSpot初期化
    When  bs.Spot() を呼び出す
    Then  デフォルトの TaskDB, Serializer, BlobStorage が構成される

  Scenario: カスタムコンポーネントの注入
    Given カスタム TaskDB 実装がある
    When  bs.Spot(db=custom_db) を呼び出す
    Then  注入された custom_db が内部で使用される

  Scenario: コンテキストマネージャによるリソース管理
    Given Spotインスタンスが構成されている
    When  with spot: ブロックに入る
    Then  DB接続がオープンされる
    And   ブロックを抜ける際に flush と close が安全に実行される
