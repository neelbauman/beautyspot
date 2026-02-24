# 44. Delegate Workspace Initialization to Storage Backends

## Status
Proposed (提案中)

## Context (背景)
これまで `beautyspot` では、メインの Factory 関数である `beautyspot.Spot()` の初期化時（`__init__.py` 内）において、デフォルトのキャッシュディレクトリ（`.beautyspot/`）の作成と `.gitignore` の配置を一律で行っていた。
しかし、ユーザーがカスタムのデータベースパスやカスタムのストレージパス（例: `/tmp/my_cache` や S3）を指定した場合でも、意図せずカレントディレクトリに `.beautyspot/` が作成されてしまうという課題があった。
また、コンポーネント（DB、ストレージ）が自身の永続化先のインフラストラクチャを自己管理できておらず、関心の分離（Separation of Concerns）の観点で不完全な設計となっていた。

## Decision (決定事項)
`__init__.py` および `core.py` からワークスペース初期化ロジック（`_setup_workspace`）を完全に削除する。
代わりに、ローカルファイルシステムに依存する各バックエンドコンポーネント（`LocalStorage` および `SQLiteTaskDB`）の初期化処理内で、自身が使用するディレクトリの作成と `.gitignore` の配置を行うように責務を委譲する。

## Rationale (理由)
1. **関心の分離 (Separation of Concerns)**: コアロジックや Factory 関数は「どこにデータを保存するか」というインフラの物理的な詳細（ディレクトリ構造など）を知る必要がなくなり、純粋な依存性の注入（DI）に専念できる。
2. **正確な副作用**: ユーザーが指定したパスに対してのみ必要なディレクトリと `.gitignore` が生成されるようになり、不要なゴミファイル（空の `.beautyspot/` ディレクトリ）が生成されるのを防ぐことができる。
3. **拡張性**: 今後ユーザーが独自のストレージバックエンド（例えば `RedisTaskDB` や `GCSStorage`）を実装する際、ライブラリ側が勝手にローカルディレクトリを作るお節介をなくすことができる。

## Consequences (結果)
* **Good**: ユーザーがカスタムパスを指定した際の挙動が直感的になり、クリーンなファイルシステムが保たれる。
* **Good**: `LocalStorage` と `SQLiteTaskDB` が独立して動作可能になり、テストや単体での利用が容易になる。
* **Bad**: カスタムのローカルバックエンドを実装するユーザーは、必要に応じて自身で `.gitignore` などを配置するロジックを書く必要がある。
* **Mitigation**: `BlobStorageBase` や `TaskDBBase` の Docstring およびカスタムバックエンド実装ガイドに、ディレクトリ管理の責務について明記する。
