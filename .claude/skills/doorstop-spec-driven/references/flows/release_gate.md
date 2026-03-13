# [E] リリースゲート

リリース前チェックの要望があったとき。

## 必須チェック

| チェック | 必須 | コマンド |
|---|---|---|
| バリデーションエラー 0件 | はい | `validate_and_report.py --strict` |
| 全カバレッジ 100% | はい | `trace_query.py coverage` |
| suspect 0件 | はい | `impact_analysis.py --detect-suspects` |
| テスト全件パス | はい | プロジェクトのテストランナー |
| 未レビュー 0件 | 警告のみ | `trace_query.py status` |
| ベースライン作成 | 推奨 | `baseline_manager.py create <version> --tag` |

## 手順

1. 上記チェックを上から順に実行する
2. 全必須チェックがパスしたら、ベースラインを作成する
3. 結果をユーザーに報告する（パス/失敗の件数と詳細）

## 検証の詳細

### 静的検証（Doorstop）

- `doorstop` でツリー全体のバリデーション
- `validate_and_report.py --strict` で全リンクの完全性チェック
- グループ別カバレッジが全て100%であること

### 動的検証（テスト実行）

- TSTアイテムの `references` が指すテストコードを実行する
- テスト結果をTSTアイテムのカスタム属性 `test_status` に記録する（pass/fail/skip）
