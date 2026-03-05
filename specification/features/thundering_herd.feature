@SPEC-012
Feature: Thundering Herd Protection
  同一関数・同一引数への同時リクエストを束ねる。

  Scenario: 同時リクエストの束ね
    Given 実行に1秒かかる関数がある
    When  10スレッドから同時に同じ引数で実行する
    Then  関数本体は1回だけ実行される
    And   全スレッドが同じ結果を受け取る

  Scenario: 失敗時の例外伝播
    Given 実行時に例外を投げる関数がある
    When  複数スレッドから同時に実行する
    Then  全スレッドに同じ例外が伝播する
