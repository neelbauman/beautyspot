@SPEC-013
Feature: バックグラウンドI/O
  キャッシュ保存処理の非同期実行。

  Scenario: save_sync=False での非同期保存
    Given save_sync=False が設定されている
    When  @mark 付き関数を実行する
    Then  結果は即座に返却される
    And   キャッシュ保存はバックグラウンドで実行される

  Scenario: コンテキストマネージャでの完了待機
    Given save_sync=False でキャッシュ保存が実行されている
    When  with spot: ブロックを抜ける
    Then  ペンディング中のすべての保存が完了する

  Scenario: flush による明示的な完了待機
    Given save_sync=False でキャッシュ保存が実行されている
    When  spot.flush() を呼び出す
    Then  ペンディング中のすべての保存が完了する

  Scenario: バックグラウンド保存の失敗はログのみ
    Given バックグラウンド保存が失敗する状況がある
    When  保存処理が失敗する
    Then  ERRORレベルのログが出力される
    And   メインの処理には例外が伝播しない

  Scenario: on_background_error コールバック
    Given on_background_error コールバックが設定されている
    And   バックグラウンド保存が失敗する状況がある
    When  保存処理が失敗する
    Then  コールバックに Exception と SaveErrorContext が渡される
