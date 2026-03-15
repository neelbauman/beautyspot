#!/usr/bin/env python3
"""Doorstop操作ヘルパー — エージェント向けの単一コマンドインターフェース。

エージェントがDoorstopの操作を1コマンドで実行できるようにする。
すべてのコマンドはJSONで結果を返し、エージェントがパースしやすい形式にする。

Usage:
    python doorstop_ops.py <project-dir> <command> [options]

Commands:
    add              アイテムを追加する
    update           アイテムを更新する
    reorder          アイテムのレベルを変更し、他を自動で再配置する
    link             リンクを追加する
    unlink           リンクを削除する
    clear            suspectを解消する
    review           レビュー済みにする
    deactivate       アイテムを非活性化する（active: false）
    activate         アイテムを活性化する（active: true）
    deactivate-chain リンクチェーン全体を非活性化する（下流を検査して一括処理）
    activate-chain   リンクチェーン全体を活性化する
    chain-review     アイテムとその祖先（上流）を一括でレビュー済みにする
    chain-clear      アイテムとその子孫（下流）のsuspectを一括解消する
    list             アイテム一覧を取得する
    groups           グループ一覧を取得する
    tree             ツリー構造を取得する
    find             テキスト検索でアイテムを探す

実装は _doorstop_ops/ パッケージに分割されています:
    _doorstop_ops/crud.py       — add, update, reorder, link, unlink
    _doorstop_ops/lifecycle.py  — activate/deactivate (単体・チェーン)
    _doorstop_ops/review.py     — clear, review, chain-review, chain-clear
    _doorstop_ops/query.py      — list, groups, tree, find
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _doorstop_ops import main

if __name__ == "__main__":
    main()
