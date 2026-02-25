---
title: Drop Absolute Path Support in LocalStorage
status: Accepted
date: 2026-02-24
context: Security and Path Normalization
---

# Drop Absolute Path Support in LocalStorage

## Context and Problem Statement / コンテキスト

v1.x 系の `LocalStorage` では、ファイルパス（`location`）として絶対パスを許容・解決する挙動が含まれていました。v2.0 の開発において、パストラバーサル脆弱性を防ぐために `base_dir` に対する厳密なセキュリティチェックを導入しましたが、これが旧来の絶対パスの挙動と競合し、意図せぬクラッシュを引き起こす可能性がありました。

## Decision Drivers / 要求

* **Security**: ディレクトリトラバーサル攻撃のリスクを完全に排除し、ストレージ層の堅牢性を確保すること。
* **Simplicity**: 例外的なパス解決ロジックを排除し、ストレージバックエンドの実装を単純で予測可能なものに保つこと。
* **Predictability**: すべてのファイルアクセスが、指定された `base_dir` の管理下に限定されることを保証すること。

## Considered Options / 検討

* **Option 1**: 絶対パスの場合はセキュリティチェックをバイパスし、後方互換性を維持する。セキュリティ上のリスクが残る。
* **Option 2**: 絶対パスのサポートを公式に放棄し、全てのパスを `base_dir` からの相対パスとして厳密に解釈する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

`LocalStorage.load()` および関連するファイルアクセスにおいて、絶対パスによる後方互換性の維持を公式に **放棄** します。

すべての `location` パラメータは `base_dir` に対する相対パスとしてのみ解釈されます。絶対パスの形式であっても、それが `base_dir` のサブディレクトリ内に解決されない限り、セキュリティチェックにより `ValueError` として処理されます。

## Consequences / 決定

* **Positive**:
    * ストレージ層の堅牢性が向上し、予期せぬディレクトリへのアクセスリスクが排除された。
    * コードの責務が単純化された。
* **Negative**:
    * v1.x からの移行ユーザーで、DB に絶対パスが記録されている場合、キャッシュの読み込みに失敗する。
* **Mitigation**:
    * この変更を v2 系の破壊的変更としてリリースノートに明記する。移行時にはキャッシュのクリアまたは DB のマイグレーションを推奨する。
