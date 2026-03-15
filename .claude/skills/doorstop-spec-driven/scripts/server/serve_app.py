#!/usr/bin/env python3
"""REST API + SPA サーバー for Doorstop トレーサビリティレポート。

バックエンドで Doorstop tree を一元管理し、全ビュー（ダッシュボード・マトリクス・
グループビュー・アイテム詳細）が API からリアルタイムにデータを取得する。
Edit/Review/Clear 操作も API 経由でバックエンドに反映され、次回のデータ取得時に
全ビューへ自動的に伝播する。

Usage:
    python serve_app.py <project-dir> [--port 8080] [--strict]

API Endpoints:
    GET  /api/overview              ダッシュボード概要
    GET  /api/matrix[?group=NAME]   トレーサビリティマトリクス
    GET  /api/groups                グループ一覧
    GET  /api/group/<name>          グループ詳細
    GET  /api/items[?group=&prefix=] アイテム一覧
    GET  /api/items/<uid>           アイテム詳細
    GET  /api/validation            検証結果
    GET  /api/coverage              カバレッジ
    POST /api/items/<uid>/review    レビュー済みにする
    POST /api/items/<uid>/clear     suspect解消
    POST /api/items/<uid>/edit      テキスト編集
    POST /api/reload                YMLファイルを再読み込み
"""

import argparse
import os
import sys
from http.server import HTTPServer

try:
    import doorstop
except ImportError:
    print("ERROR: doorstop がインストールされていません。", file=sys.stderr)
    sys.exit(1)

from data_store import DoorstopDataStore
from api_handler import ReportAPIHandler


# ===================================================================
# Entry point
# ===================================================================

def serve(tree, project_dir, port=8080, strict=False):
    """REST API + SPA サーバーを起動する。"""
    store = DoorstopDataStore(tree, project_dir, strict=strict)
    ReportAPIHandler.store = store

    server = HTTPServer(("127.0.0.1", port), ReportAPIHandler)
    print(f"\nDoorstop Dashboard: http://127.0.0.1:{port}/")
    print("  REST API + SPA mode")
    print("  All data is managed centrally in the backend.")
    print("  Edit/Review/Clear changes are reflected across all views.")
    print("  External YML edits are auto-detected on page reload.")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


def main():
    parser = argparse.ArgumentParser(
        description="Doorstop Traceability REST API + SPA Server"
    )
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    parser.add_argument("--strict", action="store_true", help="Strict validation mode")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    os.chdir(project_dir)

    print("Building document tree...")
    tree = doorstop.build()

    serve(tree, project_dir, port=args.port, strict=args.strict)


if __name__ == "__main__":
    main()
