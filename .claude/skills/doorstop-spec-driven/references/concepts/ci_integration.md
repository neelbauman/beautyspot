# CI連携

CIパイプラインに以下のチェックを組み込むことを推奨する
（具体的なCI設定はプロジェクトごとに別途定義）。

## PRゲート（推奨チェック）

1. **doorstop validate**: ツリーの構造整合性チェック
2. **traceability check**: 新規/変更された設計/IMPL/TSTに対するリンク漏れ検出
3. **references check**: IMPL/TSTの `references` が指すファイルが実在するか検証
4. **impact analysis**: `impact_analysis.py --from-git --base main` で変更影響を表示
5. **test execution**: TSTの `references` が指すテストを実行

## リリースゲート（推奨チェック）

1. **coverage check**: 全ドキュメントペアのカバレッジ100%
2. **suspect check**: `impact_analysis.py --detect-suspects` でsuspectが0件
3. **review check**: 未レビューアイテムの一覧表示（警告のみ、ブロックしない）
4. **report generation**: トレーサビリティレポートの自動生成・アーカイブ

## チェックの厳密度

| チェック | PRゲート | リリースゲート |
|----------|----------|----------------|
| doorstop validate | ブロック | ブロック |
| リンク漏れ | ブロック | ブロック |
| references存在チェック | 警告 | ブロック |
| derived根拠チェック | 警告 | ブロック |
| カバレッジ100% | 警告 | ブロック |
| テスト全件パス | ブロック | ブロック |
| suspect 0件 | 警告 | ブロック |
| 未レビューアイテム | 表示のみ | 警告 |
