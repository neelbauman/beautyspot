# ==============================================================================
# Variables
# ==============================================================================

# Gitタグからバージョンを取得（タグがない場合は開発版扱い）
VERSION := $(shell git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')
ifeq ($(VERSION),)
VERSION := 0.0.0-dev
endif

# 出力ディレクトリ
GEN_IMG_DIR := docs/statics/img/generated

# ==============================================================================
# Main Targets
# ==============================================================================

.PHONY: help install clean

help:  ## このヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## 依存関係をインストール
	uv sync --all-groups

clean:  ## 生成ファイルを削除
	rm -rf dist/ .pytest_cache/ .ruff_cache/ .mypy_cache/
	find . -name '__pycache__' -exec rm -rf {} +
	rm -rf $(GEN_IMG_DIR)

# ==============================================================================
# Development & Quality Assurance
# ==============================================================================

.PHONY: format lint lint-fix

format:  ## コードをフォーマット (ruff)
	uvx ruff format .

lint:  ## リントチェック (ruff)
	uvx ruff check .

lint-fix:  ## リントチェックと自動修正
	uvx ruff check . --fix

# ==============================================================================
# Testing
# ==============================================================================

.PHONY: test test-unit test-typing

test: test-unit test-typing ## 全てのテストを実行

test-unit: ## ユニットテストを実行 (pytest)
	uv run pytest

test-typing: ## 型チェックを実行 (pyright)
	@echo "=========== START pyright typing test =============="
	uv run pyright tests/typing
	@echo "=========== FINISH pyright typing test =============="

# ==============================================================================
# Analysis & Reports
# ==============================================================================

.PHONY: audit visualize report

audit:  ## コードの複雑度と保守性を解析 (radon)
	@echo "=== Cyclomatic Complexity (Rank C+) ==="
	-uv run radon cc src -a -n C
	@echo "\n=== Maintainability Index (Rank B-) ==="
	-uv run radon mi src -n B

visualize: ## 依存関係グラフと構造解析画像を生成
	@mkdir -p $(GEN_IMG_DIR)
	# 1. pydeps で依存関係を可視化
	-uv run pydeps src/beautyspot \
		--noshow --max-bacon=2 --cluster --show-dot > $(GEN_IMG_DIR)/dependency_graph.dot
	-dot -Tpng $(GEN_IMG_DIR)/dependency_graph.dot -o $(GEN_IMG_DIR)/dependency_graph.png
	@rm -f $(GEN_IMG_DIR)/dependency_graph.dot beautyspot.svg
	
	# 2. 構造解析スクリプトの実行
	-uv run python tools/analyze_structure.py
	
	# 3. pyreverse によるクラス図生成
	-uv run --with pylint pyreverse -o png -p beautyspot src/beautyspot --output-directory $(GEN_IMG_DIR)/
	@ls -lh $(GEN_IMG_DIR)

report: audit visualize ## 全解析を実行し、docs/quality_report.md を生成
	@uv run python tools/generate_report.py

# ==============================================================================
# Documentation & Specification
# ==============================================================================

.PHONY: docs-serve docs-deploy specification update-claude

docs-serve:  ## ドキュメントをローカルでプレビュー
	uv run mkdocs serve

docs-deploy:  ## ドキュメントを GitHub Pages にデプロイ
	uv run mkdocs gh-deploy

specification-serve: ## 仕様書のビルドとプレビュー
	uv run python .claude/skills/doorstop-spec-driven/scripts/server/serve_app.py . --strict --port 8091 2>&1

# ==============================================================================
# Release & Publish
# ==============================================================================

.PHONY: version build pypi-publish test-publish release

version:  ## 現在のバージョン（Gitタグ）を表示
	@echo "Current version: $(VERSION)"

build: clean test ## パッケージをビルド（クリーンアップとテスト後）
	uv build

pypi-publish: build  ## PyPIに公開 (要 .env と PYPI_TOKEN)
	@if [ ! -f .env ]; then echo "Error: .env not found"; exit 1; fi
	@echo "Publishing version $(VERSION) to PyPI..."
	@export $$(cat .env | grep -v '^#' | xargs) && uv publish --token $$PYPI_TOKEN

test-publish: build  ## TestPyPIに公開
	@if [ ! -f .env ]; then echo "Error: .env not found"; exit 1; fi
	@echo "Publishing version $(VERSION) to TestPyPI..."
	@export $$(cat .env | grep -v '^#' | xargs) && \
	uv publish --token $$TEST_PYPI_TOKEN --publish-url https://test.pypi.org/legacy/
	@$(MAKE) clean

release: pypi-publish  ## 完全リリース（PyPI公開とタグのPush）
	@echo "Pushing tag v$(VERSION) to origin..."
	git push origin v$(VERSION)
	@echo "✓ Release $(VERSION) completed!"
