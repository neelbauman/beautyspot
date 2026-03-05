@SPEC-006
Feature: ストレージポリシー
  データサイズに基づくDB/Blob振り分けの判定。

  Scenario: 閾値以下のデータはDBに保存される
    Given ThresholdStoragePolicy(threshold=1MB) が設定されている
    When  500KBのデータを保存する
    Then  データはDBに直接保存される

  Scenario: 閾値超過のデータはBlobに保存される
    Given ThresholdStoragePolicy(threshold=1MB) が設定されている
    When  2MBのデータを保存する
    Then  データはBlobストレージに保存される

  Scenario: 明示的な save_blob 指定が優先される
    Given ThresholdStoragePolicy が設定されている
    When  save_blob=True を指定して500KBのデータを保存する
    Then  閾値以下でもBlobストレージに保存される

  Scenario: WarningOnlyPolicy は常にDB保存
    Given WarningOnlyPolicy が設定されている
    When  大きなデータを保存する
    Then  データはDBに保存される
    And   警告ログが出力される
