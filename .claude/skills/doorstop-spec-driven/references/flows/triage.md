# [T] トリアージフロー（優先付け・スコープ確定）

ユーザーが「何を先に作るか決めたい」「バックログを整理したい」等と発話したとき。

## 手順

1. **バックログ確認** — `trace_query.py <dir> backlog` で REQ を優先度順に一覧
2. **優先度設定** — `doorstop_ops.py <dir> update REQ001 --priority high`
3. **未着手の特定** — カバレッジ 0 の REQ（設計・実装が未作成）を特定
4. **ユーザーへの提示** — 未着手 REQ を優先度順に提示し、次に着手するものを確認
5. **ベースライン確認** — `baseline_manager.py <dir> list` で現在の基準点を確認
6. **スコープ合意後** — `baseline_manager.py <dir> create <name>` でベースライン作成

## コマンド例

```bash
# 優先度付きでREQ追加
doorstop_ops.py <dir> add -d REQ -t "要件文" -g GROUP --priority high

# バックログ確認（優先度順）
trace_query.py <dir> backlog
trace_query.py <dir> backlog --group AUTH

# NFR（非機能要件）のバックログも確認
trace_query.py <dir> backlog -d NFR
```

## 優先度の値

| 値 | 意味 | 典型的な使用場面 |
|---|---|---|
| `critical` | 今すぐ必要。これがないとリリースできない | セキュリティ、コアとなる機能 |
| `high` | 今回のリリースに含めたい | 主要機能、ユーザーが期待する機能 |
| `medium` | できれば今回、次回でも可（デフォルト） | 拡張機能、利便性向上 |
| `low` | 将来対応。今回はスコープ外 | Nice-to-have、実験的機能 |

## 完了基準

全アクティブREQ/NFRに priority が設定され、今回の対象スコープが合意されていること。
