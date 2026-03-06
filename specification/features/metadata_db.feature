@SPEC-003
Feature: メタデータストレージ
  SQLiteベースのタスクメタデータの管理。

  Scenario: タスクの保存と取得
    Given SQLiteTaskDB が初期化されている
    When  タスクを保存する
    Then  同じキーでタスクを取得できる

  Scenario: タスク履歴の取得
    Given 複数のタスクが保存されている
    When  get_history を呼び出す
    Then  pandas DataFrame でタスクの一覧が返る

  Scenario: タスクの削除
    Given タスクが保存されている
    When  タスクを削除する
    Then  同じキーで取得するとNoneが返る

  Scenario: プレフィックスによるキー検索
    Given 複数のタスクが保存されている
    When  get_keys_start_with でプレフィックスを指定する
    Then  マッチするキーのリストが返る

  Scenario: 書き込みキューのドレイン
    Given 複数の書き込みがキューに積まれている
    When  flush を呼び出す
    Then  すべての書き込みが完了する

  Scenario: ライターキューによる書き込みシリアライズ
    Given 複数スレッドから同時に保存リクエストがある
    When  _DbWriterQueue に投入される
    Then  単一の書き込みスレッドですべての書き込みが順番に実行される
    And   "database is locked" エラーが発生しない

  Scenario: DB接続のライフサイクル管理
    Given SQLiteTaskDB が初期化されている
    When  close を呼び出す
    Then  書き込みキューが停止し、完了を待機した後に接続が閉じられる
