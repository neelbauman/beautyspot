# [D] レポートフロー

ユーザーが状況確認を要望したとき。

## コマンド一覧

| やりたいこと | コマンド |
|---|---|
| プロジェクト全体サマリ | `trace_query.py <dir> status` |
| 特定UIDのチェーン | `trace_query.py <dir> chain <UID>` |
| ファイルからチェーン逆引き | `trace_query.py <dir> chain --file src/mod.py` |
| カバレッジ詳細 | `trace_query.py <dir> coverage [--group GROUP]` |
| suspect一覧 | `trace_query.py <dir> suspects` |
| リンク漏れ検出 | `trace_query.py <dir> gaps [--document IMPL]` |
| 優先度付きバックログ | `trace_query.py <dir> backlog [--group GROUP]` |
| CRUD操作 | `doorstop_ops.py <dir> add/update/link/unlink/clear/review` |
| 変更の一括承認 | `doorstop_ops.py <dir> chain-review / chain-clear` |
| 非活性化（単体） | `doorstop_ops.py <dir> deactivate <UID> [<UID2> ...]` |
| 非活性化（チェーン） | `doorstop_ops.py <dir> deactivate-chain <UID> [--force]` |
| 活性化（チェーン） | `doorstop_ops.py <dir> activate-chain <UID>` |
| 静的HTMLレポート | `validate_and_report.py <dir> --output-dir ./reports --strict` |
| ダッシュボード | `validate_and_report.py <dir> --serve [--port 8080]` |
| 影響分析 | `impact_analysis.py <dir> --detect-suspects [--json PATH]` |
| ベースライン作成 | `baseline_manager.py <dir> create <name> [--tag]` |
| ベースライン一覧 | `baseline_manager.py <dir> list` |
| バージョン間差分 | `baseline_manager.py <dir> diff <v1> <v2>` |
| 現在との差分 | `baseline_manager.py <dir> diff <v1> HEAD` |

ユーザーへの報告は技術用語を避け、件数・カバレッジ・suspect数を平易に伝える。
