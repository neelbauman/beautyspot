# ワークフローフェーズ 詳細リファレンス

各フェーズの詳細な手順、チェックリスト、コマンド、テンプレートを記載する。

---

## Phase 1: 分析

### 目的

変更の影響範囲を把握し、既存の仕様体系との関係を明確にする。
**このフェーズを飛ばすと、後続フェーズで手戻りが発生するリスクが高まる。**

### 手順

#### 1.1 要求の理解

ユーザーの要求を正確に把握する。不明点があれば確認する。

- 何を実現したいのか（ゴール）
- なぜ必要なのか（動機・背景）
- 制約条件はあるか（技術的制約、時間制約）

#### 1.2 既存仕様のスキャン

```bash
# 関連しそうなキーワードで仕様を検索
# （Grep ツールで specification/ 配下を検索）

# 関連するアイテムのトレーサビリティを確認
spec-weaver trace <関連ID> -f ./specification/features

# 全体のステータスを確認
spec-weaver status
```

#### 1.3 コードベースの調査

```bash
# 影響を受けるモジュールを特定
# （Grep / Glob / Read ツールを使用）

# テストの状態を確認
uv run pytest tests/ -q --collect-only
```

#### 1.4 分析結果の報告

以下のテンプレートで分析結果をユーザーに報告する:

```markdown
## 分析結果

### 関連する既存仕様
- REQ-xxx: （概要）
- SPEC-xxx: （概要）

### 影響を受けるモジュール
- `src/xxx/yyy.py`: （影響内容）

### 必要な仕様変更
- [ ] 新規 REQ の追加: （内容）
- [ ] 新規 SPEC の追加: （内容）
- [ ] 既存 SPEC-xxx の更新: （変更内容）
- [ ] 新規 `.feature` の追加: （内容）

### リスク・懸念事項
- （あれば記載）
```

### チェックリスト

- [ ] ユーザーの要求を正確に理解した
- [ ] 関連する REQ / SPEC を全てリストアップした
- [ ] 影響を受けるコードモジュールを特定した
- [ ] 新規 REQ / SPEC の追加が必要かどうか判断した
- [ ] 分析結果をユーザーに報告した
- [ ] ユーザーから方向性の合意を得た

---

## Phase 2: 設計

### 目的

実装方針を決定し、必要に応じて設計ドキュメント（DESIGN / ADR / RESEARCH）を作成する。

### 手順

#### 2.1 仕様の作成・更新

doorstop-gherkin-skill の手順に従い、REQ / SPEC を作成・更新する。

```bash
# 新規REQの追加
doorstop add REQ
doorstop edit REQ-xxx

# 新規SPECの追加とリンク
doorstop add SPEC
doorstop link SPEC-xxx REQ-xxx
doorstop edit SPEC-xxx
```

カスタム属性（`status`, `created_at`, `updated_at`）の設定を忘れないこと。

#### 2.2 設計ドキュメントの作成

規模判定に基づいて、必要なドキュメントを作成する。

**大規模変更の場合:**

```bash
# DESIGNドキュメント（アーキテクチャ設計）
doorstop add DESIGN
doorstop link DESIGN-xxx SPEC-xxx

# ADR（技術選定がある場合）
doorstop add ADR
doorstop link ADR-xxx SPEC-xxx

# RESEARCH（調査が必要な場合）
doorstop add RESEARCH
doorstop link RESEARCH-xxx SPEC-xxx
```

各ドキュメント型のテンプレートは `document-types.md` を参照。

#### 2.3 `.feature` ファイルの方針決定

- 新しい振る舞いには新しいシナリオが必要か
- 既存のシナリオを更新する必要があるか
- テスト不可能な仕様には `testable: false` を設定する

#### 2.4 設計方針の提示

設計内容をユーザーに提示し、承認を得る。

### 設計ドキュメントの粒度ガイド

| ドキュメント型 | いつ作るか | 最低限含めるべき内容 |
|---|---|---|
| DESIGN | 2つ以上のモジュールに影響する場合 | コンポーネント図、インターフェース定義 |
| ADR | 複数の技術的選択肢がある場合 | 選択肢の比較、決定理由 |
| RESEARCH | 未知の技術を使う場合 | 調査結果、PoC結果 |

### チェックリスト

- [ ] REQ / SPEC の新規追加・更新が完了した
- [ ] カスタム属性（status, created_at, updated_at）を設定した
- [ ] 必要な設計ドキュメントを作成した
- [ ] `.feature` ファイルの更新方針を決定した
- [ ] 設計方針についてユーザーの承認を得た

---

## Phase 3: 計画

### 目的

実装タスクを分解し、実行順序を明確にする。

### 手順

#### 3.1 タスクの分解

実装作業を具体的なステップに分解する。各ステップは以下を満たすこと:

- 1つの論理的な変更単位である
- 完了条件が明確である
- 依存関係が明示されている

#### 3.2 PLAN ドキュメントの作成（中〜大規模の場合）

```bash
doorstop add PLAN
doorstop link PLAN-xxx SPEC-xxx
doorstop edit PLAN-xxx
```

PLAN の `text` フィールドに実装タスクを記述する（テンプレートは `document-types.md` 参照）。

#### 3.3 タスクの順序整理

以下の原則でタスクを並べる:

1. **依存関係順**: 他のタスクが依存するものを先に
2. **リスク順**: 不確実性の高いものを先に（早期にリスクを検出）
3. **テスト容易性**: テストしやすい単位で区切る

#### 3.4 計画の提示

計画をユーザーに提示し、承認を得る。

### チェックリスト

- [ ] 実装タスクが具体的なステップに分解された
- [ ] 各ステップの完了条件が明確である
- [ ] タスクの依存関係と実行順序が整理された
- [ ] 中〜大規模の場合は PLAN ドキュメントを作成した
- [ ] ユーザーの承認を得た

---

## Phase 4: 実装

### 目的

計画に沿ってコードを変更し、仕様との同期を保つ。

### 手順

#### 4.1 コードの変更

計画の各ステップに沿って実装を進める。

#### 4.2 仕様の同期

コード変更に伴い仕様が変わる場合は、doorstop-gherkin-skill の手順に従って同時に更新する:

- SPEC の `text` を更新する
- 新しい振る舞いがあれば `.feature` にシナリオを追加する
- `updated_at` を当日の日付に更新する

#### 4.3 ステータスの更新

```bash
# 実装中の SPEC の status を in-progress に変更
# YAML を直接編集するか doorstop edit を使用
```

#### 4.4 テストの実行

```bash
uv run pytest tests/ -q
```

### チェックリスト

- [ ] 計画の全タスクが完了した
- [ ] コードが正しく動作する（テスト通過）
- [ ] 仕様（REQ / SPEC / `.feature`）がコードと同期している
- [ ] 関連アイテムの `status` を更新した
- [ ] `updated_at` を更新した

---

## Phase 5: 検証・コミット

### 目的

全ての整合性チェックを通過させ、変更をコミットする。

### 手順

#### 5.1 検証コマンドの実行

以下の順序で実行する（前の検証が失敗した場合は修正してから次に進む）:

```bash
# Step 1: テスト実行
uv run pytest tests/ -q

# Step 2: Spec-Weaver 監査
uv run spec-weaver audit ./specification/features

# Step 3: Doorstop バリデーション
doorstop

# Step 4: ドキュメント再生成（推奨）
uv run spec-weaver build ./specification/features --out-dir .specification
```

#### 5.2 ステータスの最終更新

```bash
# 完了した SPEC の status を implemented に変更
# created_at / updated_at を確認・更新

# 確認
spec-weaver status
```

#### 5.3 コミット

コミット規約（`commit-conventions.md`）に従ってコミットする。

```bash
git add <変更ファイル>
git commit -m "feat(SPEC-xxx): 変更の概要"
```

### 検証失敗時の対応

| 検証 | よくある失敗原因 | 対処法 |
|---|---|---|
| pytest | テストロジックの不備 | テストコードを修正して再実行 |
| spec-weaver audit | タグの不一致、未テスト仕様 | `.feature` のタグを修正、または `testable: false` を設定 |
| doorstop | リンク切れ、未レビュー | `doorstop link` でリンク修正、`doorstop review all` |

### チェックリスト

- [ ] `pytest` が全て通過した
- [ ] `spec-weaver audit` が exit code 0 を返した
- [ ] `doorstop` バリデーションが通過した
- [ ] 関連アイテムの `status` を `implemented` に更新した
- [ ] `updated_at` を当日の日付に更新した
- [ ] コミット規約に従ったメッセージでコミットした

---

## 承認フローの詳細

### いつ承認を求めるか

| タイミング | 必須/任意 | 内容 |
|---|---|---|
| Phase 1 終了時 | **必須** | 分析結果と方向性の確認 |
| Phase 2 終了時 | **必須** | 設計方針の承認 |
| Phase 3 終了時 | 中〜大規模で**必須** | 実装計画の承認 |
| Phase 4 中 | 任意 | 想定外の問題が発生した場合 |
| Phase 5 コミット前 | 任意 | コミット内容の最終確認 |

### 承認の方法

ユーザーに対して明確に「承認を求めている」ことを伝え、
以下のいずれかの応答を待つ:

- **承認**: 次のフェーズに進む
- **修正依頼**: 指摘に基づいて修正し、再度承認を求める
- **差し戻し**: 前のフェーズに戻る
