# 要件の分類: FR（機能要件）と NFR（非機能要件）

## 概要

要件は大きく **FR（Functional Requirements: 機能要件）** と
**NFR（Non-Functional Requirements: 非機能要件）** に分類される。

- **FR**: システムが「何をするか」を定義する。ユーザーが直接操作・観察できる機能
- **NFR**: システムが「どの品質水準で動くか」を定義する。性能、セキュリティ、保守性など

## FR と NFR の判断基準

| 観点 | FR（機能要件） | NFR（非機能要件） |
|---|---|---|
| **定義** | 入力に対して何を出力するか | どの程度の品質で実現するか |
| **検証方法** | 「正しい結果が返ること」 | 「N秒以内に返ること」「N件まで扱えること」 |
| **表現形式** | 「〜できること」 | 「〜であること」（定量的な基準値付き） |
| **例** | 「関数の実行結果をキャッシュできること」 | 「キャッシュヒット時のオーバーヘッドが1ms以内であること」 |

### 判断フローチャート

```
ユーザーの要望
  │
  ├── 「〜できるようにしたい」 → FR
  ├── 「〜が速い/安全/信頼できること」 → NFR
  ├── 「〜のとき〜を返す」 → FR
  └── 「〜件まで/〜秒以内に」 → NFR
```

## NFR の分類（ISO 25010 ベース）

| カテゴリ | グループ名 | 対象の品質特性 | 典型的な基準 |
|---|---|---|---|
| **性能** | `PERF` | 応答時間、スループット、リソース使用量 | p99レイテンシ、RPS、メモリ上限 |
| **セキュリティ** | `SEC` | 認証、認可、暗号化、監査 | 暗号方式、セッション管理、入力検証 |
| **信頼性** | `REL` | 可用性、耐障害性、復旧性 | SLA、RTO/RPO、エラーハンドリング |
| **保守性** | `MNT` | モジュール性、再利用性、テスト容易性 | 循環的複雑度、コードカバレッジ |
| **可搬性** | `PRT` | OS互換、クラウド互換、DB互換 | サポートOS、Python バージョン |
| **安全性** | `SAF` | フェイルセーフ、ハザード分析 | 規制産業向け（医療、航空宇宙） |

### 定量化のガイドライン

NFR は**定量的な基準値**を持つことで検証可能になる。曖昧な NFR は避ける。

| 悪い例（曖昧） | 良い例（定量的） |
|---|---|
| 「高速であること」 | 「キャッシュヒット時のオーバーヘッドが p99 で 1ms 以内であること」 |
| 「安全であること」 | 「シリアライズデータに pickle を使用しないこと」 |
| 「使いやすいこと」 | 「公開 API のメソッド数が 10 以下であること」 |
| 「スケーラブルであること」 | 「10万件のキャッシュエントリで検索が 100ms 以内であること」 |

## プロファイル別の扱い

### lite プロファイル

専用 NFR ドキュメントは作成しない。以下の 2 つの方法で FR と NFR を管理する。

**方法 A: REQ に混在させる（推奨）**

`groups` でカテゴリを識別する。FR は機能グループ（`CACHE`, `CLI` 等）、
NFR は品質グループ（`PERF`, `SEC` 等）を使う。

```bash
# FR（機能要件）
doorstop_ops.py <dir> add -d REQ -t "関数の実行結果をキャッシュできること" -g CACHE --priority high

# NFR（非機能要件）
doorstop_ops.py <dir> add -d REQ -t "キャッシュヒット時のオーバーヘッドがp99で1ms以内であること" \
  -g PERF --priority medium
```

**方法 B: NFR ドキュメントを追加する**

規模が大きくなり FR と NFR の混在が管理しにくくなった場合：

```bash
init_project.py <dir> --profile lite --with-nfr --no-git-init
```

### standard プロファイル（推奨: NFR ドキュメントあり）

```bash
init_project.py <dir> --profile standard --with-nfr
```

NFR のトレーサビリティ：
- NFR は REQ と並列のルートドキュメント（`parent: null`）
- ARCH/SPEC は NFR アイテムへリンクして非機能制約の実現方針を明示
- TST は NFR アイテムへリンクして非機能テスト（性能・セキュリティ）を対応付け

```
REQ ← ARCH ← SPEC ← IMPL
               ↑       ↑
NFR ──────────┘       TST（非機能テスト）
```

### full プロファイル（強く推奨: NFR ドキュメント必須）

規制産業では NFR の文書化とテストが監査要件になる場合がある。

V字モデルでの NFR 対応：
```
NFR [PERF] ─────────── TST (test_level=system, groups=[PERF])
   HLD [PERF] ──── TST (test_level=integration, groups=[PERF])
```

## NFR のテスト戦略

| NFR カテゴリ | テスト手法 | 例 |
|---|---|---|
| `PERF` | ベンチマーク、負荷テスト | `pytest-benchmark` で p99 レイテンシ計測 |
| `SEC` | セキュリティスキャン、ファジング | `bandit`, `detect-secrets` |
| `REL` | 障害注入テスト | 例外発生時のグレースフルデグラデーション |
| `MNT` | 静的解析 | `radon` 循環的複雑度、`pyright` 型チェック |
| `PRT` | マトリクステスト | CI で複数 Python バージョン × OS |

## コマンド例

```bash
# NFR アイテムの追加
doorstop_ops.py <dir> add -d NFR -t "全APIの応答時間はp99で200ms以内とする" -g PERF --priority high
doorstop_ops.py <dir> add -d NFR -t "シリアライズにpickleを使用しないこと" -g SEC --priority critical

# 設計文書から NFR へリンク（非機能制約の実現方針を明示）
doorstop_ops.py <dir> link ARCH001 NFR001

# NFR のバックログ確認
trace_query.py <dir> backlog -d NFR
trace_query.py <dir> backlog -d NFR --group PERF

# NFR のカバレッジ確認
trace_query.py <dir> coverage --group PERF
```
