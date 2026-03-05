# tools/generate_report.py
import subprocess
import datetime
from pathlib import Path

# 設定
DOCS_DIR = Path("docs")
IMG_DIR = DOCS_DIR / "statics/img/generated"
REPORT_FILE = DOCS_DIR / "quality_report.md"
SRC_DIR = Path("src/beautyspot")


def run_command(command):
    """コマンドを実行し、標準出力を取得する"""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def generate_report():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = [
        "# 📊 Beautyspot Quality Report",
        f"**最終更新:** {timestamp}",
        "",
        "## 1. アーキテクチャ可視化",
        "### 1.1 依存関係図 (Pydeps)",
        "![Dependency Graph](statics/img/generated/dependency_graph.png)",
        "",
        "### 1.2 安定度分析 (Instability Analysis)",
        "青: 安定(Core系) / 赤: 不安定(高依存系)。矢印は依存の方向を示します。",
        "![Stability Graph](statics/img/generated/architecture_metrics.png)",
        "",
        "### 1.3 クラス図 (Class Diagram)",
        "![Class Diagram](statics/img/generated/classes_beautyspot.png)",
        "",
    ]

    # --- 安定度テーブル ---
    structure_out = run_command(["uv", "run", "python", "tools/analyze_structure.py"])
    report.extend(
        [
            "<details>",
            "<summary>🔍 安定度メトリクスの詳細（Ca/Ce/I）を表示</summary>",
            "",
            "```text",
            structure_out,
            "```",
            "</details>",
            "",
        ]
    )

    # --- コードメトリクス: 循環的複雑度 (CC) ---
    print("Measuring CC...")
    cc_warnings = run_command(
        ["uv", "run", "radon", "cc", str(SRC_DIR), "-a", "-n", "C"]
    )
    cc_all = run_command(["uv", "run", "radon", "cc", str(SRC_DIR), "-a"])

    report.extend(
        [
            "## 2. コード品質メトリクス",
            "### 2.1 循環的複雑度 (Cyclomatic Complexity)",
            "#### ⚠️ 警告 (Rank C 以上)",
            "複雑すぎてリファクタリングが推奨される箇所です。",
            "",
            "```text",
            cc_warnings if cc_warnings else "なし（良好です 🎉）",
            "```",
            "",
            "<details>",
            "<summary>📄 すべての CC メトリクス一覧を表示</summary>",
            "",
            "```text",
            cc_all,
            "```",
            "</details>",
            "",
        ]
    )

    # --- コードメトリクス: 保守性指数 (MI) ---
    print("Measuring MI...")
    mi_warnings = run_command(["uv", "run", "radon", "mi", str(SRC_DIR), "-n", "B"])
    mi_all = run_command(["uv", "run", "radon", "mi", str(SRC_DIR)])

    report.extend(
        [
            "### 2.2 保守性指数 (Maintainability Index)",
            "#### ⚠️ 警告 (Rank B 以下)",
            "コードの読みやすさ・保守しやすさに改善の余地があるモジュールです。",
            "",
            "```text",
            mi_warnings if mi_warnings else "なし（すべて Rank A です ✨）",
            "```",
            "",
            "<details>",
            "<summary>📄 すべての MI メトリクス一覧を表示</summary>",
            "",
            "```text",
            mi_all,
            "```",
            "</details>",
            "",
        ]
    )

    # --- デザイン・インテント分析 ---
    print("Analyzing Design Intents...")
    design_mermaid = run_command(["uv", "run", "python", "tools/analyze_design.py"])

    report.extend(
        [
            "## 4. デザイン・インテント分析 (Design Intent Map)",
            "クラス図には現れない、生成関係、静的利用、および Protocol への暗黙的な準拠を可視化します。",
            "",
            "```mermaid",
            design_mermaid,
            "```",
            "",
        ]
    )

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print(f"✅ レポートを生成しました: {REPORT_FILE}")


if __name__ == "__main__":
    generate_report()
