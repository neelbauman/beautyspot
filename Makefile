.PHONY: help install test lint lint-fix format build docs-serve docs-deploy clean pypi-publish test-publish version release

# Gitタグからバージョンを取得（タグがない場合は開発版扱い）
VERSION := $(shell git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')
ifeq ($(VERSION),)
VERSION := 0.0.0-dev
endif

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
	# hatch-vcs が自動的にGitタグからバージョンを埋め込みます
	uv build

docs-serve:  ## ドキュメントをローカルで確認
	uvx --with mkdocs-material --with "mkdocstrings[python]" mkdocs serve

docs-deploy:  ## GitHub Pagesにデプロイ
	uvx --with mkdocs-material --with "mkdocstrings[python]" mkdocs gh-deploy

clean:  ## 生成ファイルを削除
	rm -rf dist/ .pytest_cache/ .ruff_cache/
	find . -name '__pycache__' -exec rm -rf {} +

version:  ## 現在のバージョン（Gitタグ）を表示
	@echo "Current version (from git): $(VERSION)"

pypi-publish: build  ## PyPIにローカルから公開（dist/ディレクトリが必要）
	@echo "Publishing version $(VERSION) to PyPI..."
	@if [ ! -f .env ]; then \
		echo "Error: .env not found"; \
		exit 1; \
	fi
	@export $$(cat .env | grep -v '^#' | xargs) && \
	uv publish --token $$PYPI_TOKEN
	@echo "✓ Published version $(VERSION) to PyPI"

test-publish: build  ## TestPyPIに公開
	@echo "Publishing version $(VERSION) to TestPyPI..."
	@if [ ! -f .env ]; then \
		echo "Error: .env not found"; \
		exit 1; \
	fi
	@export $$(cat .env | grep -v '^#' | xargs) && \
	uv publish --token $$TEST_PYPI_TOKEN --publish-url https://test.pypi.org/legacy/
	@echo "✓ Published version $(VERSION) to TestPyPI"
	@$(MAKE) clean

release: pypi-publish  ## 完全リリース（PyPI公開→GitHubタグPush）
	@echo "Pushing tag v$(VERSION) to trigger GitHub Release..."
	git push origin v$(VERSION)
	@echo "✓ Release $(VERSION) completed!"

