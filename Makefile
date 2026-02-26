.PHONY: help install test lint lint-fix format build clean 

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
	uv run pytest; echo "=========== START pyright typing test =============="; uv run pyright tests/typing; echo "=========== FINISH pyright typing test ==============";

lint:  ## リントチェック
	uvx ruff check .

lint-fix:  ## リントチェック (--fixオプションで自動修正）
	uvx ruff check . --fix

format:  ## コードをフォーマット
	uvx ruff format .

build: clean test  ## パッケージをビルド（テスト後）
	# hatch-vcs が自動的にGitタグからバージョンを埋め込みます
	uv build

clean:  ## 生成ファイルを削除
	rm -rf dist/ .pytest_cache/ .ruff_cache/
	find . -name '__pycache__' -exec rm -rf {} +


.PHONY: docs-serve docs-deploy

docs-serve:  ## ドキュメントをローカルで確認
	uvx --with mkdocs-material --with "mkdocstrings[python]" mkdocs serve

docs-deploy:  ## GitHub Pagesにデプロイ
	uvx --with mkdocs-material --with "mkdocstrings[python]" mkdocs gh-deploy

.PHONY: version pypi-publish test-publish release

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

# Makefile (追加案)

.PHONY: audit visualize 

audit:  ## [Console] コードの複雑度と保守性をコンソール出力
	@echo "=== Cyclomatic Complexity (Rank C+) ==="
	-uv run radon cc src -a -n C
	@echo "\n=== Maintainability Index (Rank B-) ==="
	-uv run radon mi src -n B

visualize: ## [Image] 依存関係グラフのみ生成
	@mkdir -p docs/statics/img/generated
	# 1. pydeps で DOT 形式を出力
	-uv run pydeps src/beautyspot \
		--noshow \
		--max-bacon=2 \
		--cluster \
		--show-dot > docs/statics/img/generated/dependency_graph.dot
	
	# 2. 明示的に PNG レンダリング
	-dot -Tpng docs/statics/img/generated/dependency_graph.dot -o docs/statics/img/generated/dependency_graph.png
	
	@ls -lh docs/statics/img/generated/dependency_graph.png
	@rm docs/statics/img/generated/dependency_graph.dot
	@rm beautyspot.svg
	
	-uv run python tools/analyze_structure.py
	-uv run --with pylint pyreverse -o png -p beautyspot src/beautyspot --output-directory docs/statics/img/generated/

report: audit visualize## [Report] 全解析を実行し、docs/quality_report.md を生成
	@uv run python tools/generate_report.py


.PHONY: update-claude

update-claude:  ## CLAUDE.md の自動生成セクションを更新
	uv run python tools/generate_claude_ref.py

.PHONY: specification

specification:
	-spec-weaver build specification/
	-uvx --with mkdocs-material zensical serve -f .specification/mkdocs.yml
