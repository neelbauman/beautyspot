@SPEC-007
Feature: レートリミッター
  GCRAベースのトークンバケットによる関数実行レート制限。

  Scenario: レート内での実行は遅延しない
    Given TokenBucket(tokens_per_minute=60) が設定されている
    When  1秒間隔で実行する
    Then  遅延なく即座に実行される

  Scenario: レート超過時は待機する
    Given TokenBucket(tokens_per_minute=60) が設定されている
    When  連続して高速に実行する
    Then  レートを超えないよう適切に待機する
