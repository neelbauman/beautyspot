@SPEC-011
Feature: CLIインターフェース
  コマンドラインからのキャッシュ管理。

  Scenario: キャッシュ一覧の表示
    Given キャッシュ済みタスクが存在する
    When  beautyspot list コマンドを実行する
    Then  タスクの一覧がテーブル形式で表示される

  Scenario: タスク詳細の表示
    Given 特定のキャッシュ済みタスクが存在する
    When  beautyspot show コマンドで指定する
    Then  タスクの詳細情報が表示される

  Scenario: キャッシュ統計の表示
    Given キャッシュ済みタスクが存在する
    When  beautyspot stats コマンドを実行する
    Then  キャッシュの統計情報が表示される

  Scenario: 名前指定でのキャッシュ削除
    Given "my_func" のキャッシュが存在する
    When  beautyspot clear --name "my_func" を実行する
    Then  "my_func" のキャッシュが削除される

  Scenario: ガベージコレクション
    Given 孤立Blobと期限切れタスクが存在する
    When  beautyspot gc コマンドを実行する
    Then  孤立Blobと期限切れタスクが削除される
