# CI/CD 連携ガイド

## GitHub Actions: 仕様整合性チェック

```yaml
# .github/workflows/spec-check.yml
name: Spec Coverage Check

on: [push, pull_request]

jobs:
  doorstop-validate:
    name: Doorstop 整合性チェック
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install doorstop
      - name: Doorstop バリデーション
        run: doorstop  # リンク切れ・未レビューアイテムを検出

  spec-weaver-audit:
    name: Spec-Weaver 監査
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Spec-Weaver インストール
        run: |
          cd spec-weaver  # または pip install spec-weaver
          uv tool install .
      - name: 仕様カバレッジ監査
        run: spec-weaver audit ./features
        # 孤児タグまたは未実装仕様があれば終了コード1 → CIが失敗する
```

---

## ローカルでの pre-commit フック

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: doorstop-check
        name: Doorstop validation
        language: system
        entry: doorstop
        pass_filenames: false
        files: \.(yml|feature)$

      - id: spec-weaver-audit
        name: Spec-Weaver audit
        language: system
        entry: spec-weaver audit ./features
        pass_filenames: false
        files: \.(yml|feature)$
```

インストール:
```bash
pip install pre-commit
pre-commit install
```

---

## モノレポでのSpec-Weaver設定例

バックエンドとフロントエンドで別々の `features/` がある場合:

```bash
# バックエンドのfeatures
spec-weaver audit ./backend/tests/features --repo-root ./docs/specs

# フロントエンドのfeatures
spec-weaver audit ./frontend/e2e/features --repo-root ./docs/specs
```

GitHub Actionsでは matrix で並列実行できる:

```yaml
strategy:
  matrix:
    target:
      - { dir: backend/tests/features, name: backend }
      - { dir: frontend/e2e/features, name: frontend }
steps:
  - run: spec-weaver audit ./${{ matrix.target.dir }} --repo-root ./docs/specs
```
