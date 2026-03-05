@SPEC-004
Feature: シリアライザ
  MessagePackベースのオブジェクトシリアライズ・デシリアライズ。

  Scenario: 基本型のシリアライズ往復
    Given MsgpackSerializer が初期化されている
    When  int, str, list, dict をシリアライズしてデシリアライズする
    Then  元のオブジェクトと同じ値が復元される

  Scenario: カスタム型の登録とシリアライズ
    Given カスタムクラス MyClass が定義されている
    And   code=1 でエンコーダ/デコーダが登録されている
    When  MyClass インスタンスをシリアライズしてデシリアライズする
    Then  元のインスタンスと同じ属性値が復元される
