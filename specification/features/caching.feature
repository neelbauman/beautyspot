@SPEC-001
Feature: 透過的キャッシュ
  関数の実行結果を透過的にキャッシュし、同一引数での再実行を高速化する。

  Background:
    Given Spotインスタンスが初期化されている

  Scenario: 同期関数のキャッシュヒット
    Given @mark デコレータが付与された同期関数がある
    When  同じ引数で2回実行する
    Then  関数本体は1回だけ実行される
    And   2回目の結果は1回目と同じ値を返す

  Scenario: 引数が異なる場合のキャッシュミス
    Given @mark デコレータが付与された関数がある
    When  異なる引数で2回実行する
    Then  関数本体は2回実行される

  Scenario: 非同期関数のキャッシュ
    Given @mark デコレータが付与された非同期関数がある
    When  同じ引数で2回awaitする
    Then  関数本体は1回だけ実行される
    And   2回目の結果は1回目と同じ値を返す

  Scenario: cached_run による直接キャッシュ
    Given キャッシュ対象の関数がある
    When  cached_run で同じ引数を2回実行する
    Then  関数本体は1回だけ実行される

  Scenario: バージョン変更によるキャッシュ無効化
    Given version="v1" で結果がキャッシュ済みである
    When  version="v2" に変更して同じ引数で実行する
    Then  関数本体が再実行される

  Scenario: ジェネレータ関数への適用は拒否される
    Given ジェネレータ関数がある
    When  @mark デコレータを付与する
    Then  ConfigurationError が発生する

  Scenario: デコレート関数のシグネチャ保持
    Given @mark デコレータが付与された関数がある
    When  デコレート後のシグネチャを確認する
    Then  元の関数と同じシグネチャが保持されている
