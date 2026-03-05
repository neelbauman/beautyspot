@SPEC-005
Feature: Blobストレージ
  大容量データ用のBlobストレージバックエンド。

  Scenario: LocalStorage への保存と読み込み
    Given LocalStorage が初期化されている
    When  1MBのデータを保存する
    Then  同じキーでデータを読み込める
    And   元のデータと一致する

  Scenario: Blobの削除
    Given データが保存されている
    When  delete でBlobを削除する
    Then  同じキーで読み込むとエラーになる

  Scenario: 保存キーの一覧取得
    Given 複数のBlobが保存されている
    When  list_keys を呼び出す
    Then  保存済みの全キーが返る
