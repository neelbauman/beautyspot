@SPEC-010
Feature: メンテナンスサービス
  管理・保守用のサービスレイヤー。

  Scenario: パスからのサービス構築
    Given DBファイルパスが指定されている
    When  MaintenanceService.from_path() で構築する
    Then  サービスインスタンスが生成される

  Scenario: キャッシュ済みタスクの一覧取得
    Given キャッシュ済みタスクが存在する
    When  get_history() を呼び出す
    Then  タスクの一覧が pandas DataFrame で返る

  Scenario: タスク詳細の取得
    Given キャッシュ済みタスクが存在する
    When  get_task_detail(cache_key) を呼び出す
    Then  タスクの詳細情報が辞書で返る

  Scenario: 関数名指定でのキャッシュ削除
    Given "my_func" のキャッシュが存在する
    When  clear(func_name="my_func") を実行する
    Then  "my_func" のキャッシュが削除される

  Scenario: 孤立Blobのスキャンとクリーンアップ
    Given 孤立Blobファイルが存在する
    When  scan_garbage() でスキャンし clean_garbage() で削除する
    Then  孤立Blobが削除される
