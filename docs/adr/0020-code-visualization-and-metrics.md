---
title: Code Visualization and Quality Metrics Strategy
status: Accepted
date: 2026-02-14
context: Maintaining Architectural Health
---

# Code Visualization and Quality Metrics Strategy

## Context and Problem Statement / コンテキスト

プロジェクトの規模拡大に伴い、以下の課題が発生しています：

1.  **構造の把握困難**: モジュール間の依存関係が複雑化し、全体像を掴みにくい。
2.  **品質の定量化**: コードの複雑さが主観で語られており、客観的なリファクタリング基準がない。
3.  **アーキテクチャの健全性**: 「安定依存の原則（SDP）」が守られているか（不安定なモジュールが安定したモジュールに依存していないか）を確認する手段がない。

## Decision Drivers / 要求

* **Objectivity**: リファクタリングの優先順位を、数値に基づく客観的な基準で決定すること。
* **Visibility**: モジュール間の依存関係を視覚化し、設計上の「逆流」を容易に発見できること。
* **Automation**: 開発フロー（CI/CD や Makefile）に組み込み、常に最新のメトリクスを維持すること。

## Considered Options / 検討

* **Option 1**: 手動のコードレビューのみで品質を管理する。
* **Option 2**: Radon, Pydeps, および独自スクリプトを導入し、メトリクス計測と可視化を自動化する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

以下のツールを導入し、開発フローに統合します。

1.  **Radon**: 
    * 循環的複雑度 (Cyclomatic Complexity) と保守性指数 (Maintainability Index) を計測する。
2.  **Pydeps**: 
    * モジュール間のインポート依存関係を可視化するグラフ（SVG）を生成する。
3.  **Custom Stability Analyzer**:
    * 不安定度 ($I$) を算出する独自スクリプトを `tools/` に配置する。
    * Graphviz を用いて、安定度に基づいた色分け（青＝安定、赤＝不安定）を行ったアーキテクチャ図を生成する。

## Consequences / 決定

* **Positive**:
    * リファクタリングの優先順位を数値に基づいて決定できる。
    * 生成された図により、新規参画者のオンボーディングが高速化される。
    * 設計原則（SDP）違反を視覚的に検知できる。
* **Negative**:
    * 実行環境に `graphviz` (システムパッケージ) のインストールが必須となる。
