---
title: Rename Project to Spot and Task to Mark
status: Accepted
date: 2026-01-18
context: Brand Identity and API Clarity
---

# Rename Project to Spot and Task to Mark

## Context and Problem Statement / コンテキスト

現在、`beautyspot` のメインエントリーポイントとして `Project` クラスが、タスク定義のデコレータとして `@project.task` が使用されています。しかし、これらの名称には以下の課題があります。

1.  **`Project` の曖昧さ:**
    ユーザーにとって "Project" は、自身のソースコード全体やリポジトリを指す言葉であることが多いです。ライブラリの管理オブジェクトを `Project` と呼ぶことで、ユーザーのメンタルモデルとの衝突（「プロジェクトの中にプロジェクトがある？」）を招いています。
2.  **`task` の不一致:**
    `task` は「仕事・課題」を表す名詞ですが、デコレータの役割は「関数を永続化対象として登録・設定する」という動的な作用です。名詞としての命名は、宣言的なデコレータの性質と完全に一致していません。
3.  **ブランド・アイデンティティの欠如:**
    現在の API は汎用的すぎて、このライブラリ特有の「黒子」や「美点（Beauty Spot）」というコンセプトがコード上で表現されていません。

## Decision Drivers / 要求

* **Mental Model Alignment**: ユーザーのプロジェクト構成とライブラリの管理単位を混同させないこと。
* **Declarative API**: デコレータの役割が「設定の付与（マーキング）」であることを直感的に伝えること。
* **Brand Consistency**: ライブラリ名 `beautyspot` と API の命名に一貫性を持たせること。

## Considered Options / 検討

* **Option 1**: 現状維持（`Project` および `task`）。
* **Option 2**: `Project` を `Spot` に、`task` を `mark` にリネームする。

## Decision Outcome / 決定

Chosen option: **Option 2**.

ライブラリのコアとなる用語を再定義し、以下のリネームを行います。

### 1. Rename `Project` class to `Spot`
管理クラスの名前を `Spot` に変更します。これにより、「コード上の特定の場所（Spot）を管理する」というニュアンスを持たせ、ライブラリ名 `beautyspot` との一貫性を持たせます。

### 2. Rename `@task` decorator to `@mark`
デコレータ名を `@spot.mark` に変更します。これは "Marking a spot"（地点に印を付ける）というイディオムに基づいており、「この関数を管理対象としてマークする」という宣言的な意図を明確にします。

### 3. Keep `run` method as `spot.run`
命令的な実行メソッドである `run` は、名前を変更せずそのまま維持します。これは、「`mark`（宣言・静的）」と「`run`（実行・動的）」という役割分担を明確にするためです。

## Consequences / 決定

* **Positive**:
    * **直感的なメンタルモデル:** `Spot` と `mark` の組み合わせにより、「コード上の重要な箇所に印を付けて管理する」という思想が伝わりやすくなる。
    * **名前空間の明確化:** 変数名 `spot` を使用することで、それが `beautyspot` のインスタンスであることが一目で分かる。
    * **一貫性:** ライブラリ名とクラス名が一致し、ブランドとしての統一感が生まれる。
* **Negative**:
    * **破壊的変更:** 既存の v1.x 系コードとは互換性がなくなる。
    * **移行コスト:** 既存ユーザーはコードの書き換えが必要となる。
