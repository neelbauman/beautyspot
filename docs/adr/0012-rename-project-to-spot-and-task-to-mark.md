# 12. Rename Project to Spot and Task to Mark

Date: 2026-01-18
Status: Accepted

## Context

現在、`beautyspot` のメインエントリーポイントとして `Project` クラスが、タスク定義のデコレータとして `@project.task` が使用されている。しかし、これらの名称には以下の課題がある。

1.  **`Project` の曖昧さ:**
    ユーザーにとって "Project" は、自身のソースコード全体やリポジトリを指す言葉であることが多い。ライブラリの管理オブジェクトを `Project` と呼ぶことで、ユーザーのメンタルモデルとの衝突（「プロジェクトの中にプロジェクトがある？」）を招いている。また、`beautyspot` というライブラリ名との関連性が薄い。

2.  **`task` の不一致:**
    `task` は「仕事・課題」を表す名詞だが、デコレータの役割は「関数を永続化対象として登録・設定する」という動的な作用である。名詞としての命名は、宣言的なデコレータの性質と完全に一致していない。

3.  **ブランド・アイデンティティの欠如:**
    現在の API は汎用的すぎて、このライブラリ特有の「黒子（インフラ制御の隠蔽）」や「美点（Beauty Spot）」というコンセプトがコード上で表現されていない。

## Decision

私たちは、ライブラリのコアとなる用語を再定義し、以下のリネームを行うことを決定した。これに伴い、次期バージョンはメジャーアップデート（Breaking Change）となる。

### 1. Rename `Project` class to `Spot`

管理クラスの名前を `Spot` に変更する。
これにより、「コード上の特定の場所（Spot）を管理する」というニュアンスを持たせ、ライブラリ名 `beautyspot` との一貫性を持たせる。

### 2. Rename `@task` decorator to `@mark`

デコレータ名を `@spot.mark` に変更する。
これは "Marking a spot"（地点をマークする／印を付ける）というイディオムに基づいており、「この関数を管理対象としてマークする」という宣言的な意図を明確にする。

### 3. Keep `run` method as `spot.run`

命令的な実行メソッドである `run` は、名前を変更せずそのまま維持する。
これは、「`mark`（宣言・静的）」と「`run`（実行・動的）」という役割分担を明確にするためである。

## Detailed Design

### API Comparison

#### Before (v1.x)

```python
import beautyspot as bs

# "Project" は広義すぎる
project = bs.Project("my_experiment")

# "task" は名詞であり、動的な作用が伝わりにくい
@project.task
def heavy_process(data):
    ...

```

#### After (v2.0)

```python
import beautyspot as bs

# "Spot" = ここが管理地点であることを示す
spot = bs.Spot("my_experiment")

# "mark" = この関数をスポットとして印付けする (Declarative)
@spot.mark
def heavy_process(data):
    ...

# "run" = スポットの設定に基づいて実行する (Imperative)
# mark と対比され、動詞としての run がより自然に響く
result = spot.run(heavy_process, data)

```

## Consequences

### Positive

* **直感的なメンタルモデル:** `Spot` と `mark` の組み合わせにより、「コード上の重要な箇所に印を付けて管理する」というライブラリの設計思想が直感的に伝わるようになる。
* **名前空間の明確化:** 変数名 `spot` を使用することで、それが `beautyspot` のインスタンスであることが一目で分かる（`project` 変数はユーザーのコードで既に使用されている可能性が高い）。
* **一貫性:** ライブラリ名とクラス名が一致し、ブランドとしての統一感が生まれる。

### Negative

* **破壊的変更:** 既存の v1.x 系コードとは互換性がなくなる。
* **移行コスト:** 既存ユーザーはコードの書き換えが必要となる。また、ドキュメント、サンプルコード、Docstring の全面的な更新が必要となる。

## Migration Strategy

既存ユーザー向けに、以下の移行ガイドを提供する。

1. クラス名の置換: `Project` -> `Spot`
2. デコレータの置換: `.task` -> `.mark`
3. データベース互換性: DBスキーマ自体に変更はないため、既存の `.db` ファイルはそのまま利用可能（ただし、メタデータ上の整合性チェックは必要）。

```bash
# Example text replacement
sed -i 's/Project/Spot/g' **/*.py
sed -i 's/@project.task/@spot.mark/g' **/*.py

```
