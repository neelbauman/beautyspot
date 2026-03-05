@SPEC-014
Feature: カスタム型登録
  ユーザー定義クラスのシリアライズ・デシリアライズ対応。

  Scenario: デコレータによるカスタム型登録
    Given カスタムクラス MyClass がある
    When  @spot.register(code=1, encoder=..., decoder=...) で登録する
    Then  MyClass インスタンスをキャッシュできる
    And   キャッシュからの復元で元のインスタンスが再構築される

  Scenario: 命令的なカスタム型登録
    Given カスタムクラス MyClass がある
    When  spot.register_type(MyClass, code=1, encoder=..., decoder=...) で登録する
    Then  MyClass インスタンスをキャッシュできる
