.PHONY: help install test lint lint-fix format build docs-serve docs-deploy clean github-release pypi-publish test-publish bump-major bump-minor bump-patch check-version version release

# pyproject.tomlからバージョンを取得（Python非依存）
VERSION := $(shell grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')

help:  ## このヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## 依存関係をインストール
	uv sync --all-groups

test:  ## テストを実行
	uv run pytest

lint:  ## リントチェック
	uvx ruff check .

lint-fix:  ## リントチェック (--fixオプションで自動修正）
	uvx ruff check . --fix

format:  ## コードをフォーマット
	uvx ruff format .

build: clean test  ## パッケージをビルド（テスト後）
	uv build

docs-serve:  ## ドキュメントをローカルで確認
	uvx --with mkdocs-material --with "mkdocstrings[python]" mkdocs serve

docs-deploy:  ## GitHub Pagesにデプロイ
	uvx --with mkdocs-material --with "mkdocstrings[python]" mkdocs gh-deploy

clean:  ## 生成ファイルを削除
	rm -rf dist/ .pytest_cache/ .ruff_cache/
	find . -name '__pycache__' -exec rm -rf {} +

version:  ## 現在のバージョンを表示
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: Could not read version from pyproject.toml"; \
		exit 1; \
	fi
	@echo "Current version: $(VERSION)"

check-version:  ## バージョンの整合性をチェック
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: Could not read version from pyproject.toml"; \
		exit 1; \
	fi
	@echo "Checking version consistency..."
	@echo "pyproject.toml version: $(VERSION)"
	@if git rev-parse v$(VERSION) >/dev/null 2>&1; then \
		echo "✓ Git tag v$(VERSION) exists"; \
	else \
		echo "✗ Git tag v$(VERSION) does not exist"; \
	fi

_github-release-core: check-version test build  ## GitHubリリースのコア処理（内部用）
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: Could not read version from pyproject.toml"; \
		exit 1; \
	fi
	@echo "Preparing GitHub release for version $(VERSION)..."
	@if git rev-parse v$(VERSION) >/dev/null 2>&1; then \
		echo "Error: Tag v$(VERSION) already exists"; \
		exit 1; \
	fi
	@echo "All checks passed! Creating tag v$(VERSION)..."
	git tag v$(VERSION)
	git push origin v$(VERSION)
	@echo "✓ Tag v$(VERSION) pushed. GitHub release will be created."

github-release: _github-release-core clean  ## GitHubリリース作成（タグをpush）

pypi-publish:  ## PyPIにローカルから公開（dist/ディレクトリが必要）
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: Could not read version from pyproject.toml"; \
		exit 1; \
	fi
	@if [ ! -d "dist" ]; then \
		echo "Error: dist/ directory not found. Run 'make build' first."; \
		exit 1; \
	fi
	@echo "Publishing version $(VERSION) to PyPI..."
	@if [ ! -f .env ]; then \
		echo "Error: .env not found"; \
		exit 1; \
	fi
	@export $$(cat .env | grep -v '^#' | xargs) && \
	uv publish --token $$PYPI_TOKEN
	@echo "✓ Published version $(VERSION) to PyPI"

test-publish: test build  ## TestPyPIに公開
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: Could not read version from pyproject.toml"; \
		exit 1; \
	fi
	@echo "Publishing version $(VERSION) to TestPyPI..."
	@if [ ! -f .env ]; then \
		echo "Error: .env not found"; \
		exit 1; \
	fi
	@export $$(cat .env | grep -v '^#' | xargs) && \
	uv publish --token $$TEST_PYPI_TOKEN --publish-url https://test.pypi.org/legacy/
	@echo "✓ Published version $(VERSION) to TestPyPI"
	@$(MAKE) clean

release: _github-release-core pypi-publish clean  ## 完全リリース（GitHubタグ作成→PyPI公開）
	@echo "✓ Release $(VERSION) completed!"

bump-patch:  ## パッチバージョンをインクリメント（例: 1.0.0 -> 1.0.1）
	@uv run python scripts/bump_version.py patch

bump-minor:  ## マイナーバージョンをインクリメント（例: 1.0.0 -> 1.1.0）
	@uv run python scripts/bump_version.py minor

bump-major:  ## メジャーバージョンをインクリメント（例: 1.0.0 -> 2.0.0）
	@uv run python scripts/bump_version.py major
