#!/usr/bin/env python3
"""AIコーディングエージェント向けトレーサビリティ照会CLI。

doorstop_ops.py がCRUD操作を担当するのに対し、本スクリプトは
トレーサビリティの「分析・照会」に特化する。
すべてのコマンドはJSON形式でstdoutに出力し、エージェントがパースしやすい。

Usage:
    python trace_query.py <project-dir> <command> [options]

Commands:
    status              プロジェクト全体のサマリ（件数・カバレッジ・suspect数）
    chain <UID>         指定UIDの上流→下流チェーン全体を表示
    chain --file PATH   ファイルパスをreferencesから逆引きし、該当アイテムのチェーンを表示
    context <UID>       行動に必要な全文脈情報を一括取得（target/upstream/downstream/files/health）
    related-files <UID> 関連ファイルパスをドキュメント層別に取得
    search <PATTERN>    属性フィルタ付き高機能検索（正規表現対応）
    coverage            カバレッジ詳細（どのSPECがIMPL/TST未カバーか）
    suspects            全suspect一覧と要対応アクション
    gaps                リンク漏れ・ref未設定のアイテム一覧

Examples:
    python trace_query.py . status
    python trace_query.py . chain SPEC003
    python trace_query.py . chain --file src/beautyspot/core.py
    python trace_query.py . context SPEC003
    python trace_query.py . related-files SPEC003
    python trace_query.py . search "タイムアウト" --group auth --suspect
    python trace_query.py . coverage --group CACHE
    python trace_query.py . suspects
    python trace_query.py . gaps --document IMPL

実装は _trace_query/ パッケージに分割されています:
    _trace_query/chain.py    — chain, context, related-files
    _trace_query/status.py   — status, coverage, gaps
    _trace_query/search.py   — search
    _trace_query/quality.py  — suspects, backlog
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _trace_query import main

if __name__ == "__main__":
    main()
