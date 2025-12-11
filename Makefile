.PHONY: help install test lint lint-fix format build docs-serve docs-deploy clean

help:  ## このヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## 依存関係をインストール
	uv sync

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

.PHONY: publish publish-test

publish: test build  ## PyPIに公開
	@if [ ! -f .env ]; then echo "Error: .env not found"; exit 1; fi
	@export $$(cat .env | grep -v '^#' | xargs) && \
	uv publish --token $$PYPI_TOKEN
	@$(MAKE) clean

publish-test: test build  ## TestPyPIに公開（テスト用）
	@if [ ! -f .env ]; then echo "Error: .env not found"; exit 1; fi
	@export $$(cat .env | grep -v '^#' | xargs) && \
	uv publish --token $$TEST_PYPI_TOKEN --publish-url https://test.pypi.org/legacy/
	@$(MAKE) clean

