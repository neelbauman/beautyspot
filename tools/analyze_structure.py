# tools/analyze_structure.py
import ast
import sys
from collections import defaultdict
from pathlib import Path

try:
    from graphviz import Digraph
except ImportError:
    print("Error: graphviz library is required. Run 'uv sync --all-groups'")
    sys.exit(1)


def analyze_structure(
    target_dir: str = "src/beautyspot", output_dir: str = "docs/statics/img/generated"
):
    root = Path(target_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    package_name = root.name
    modules = [p.stem for p in root.glob("*.py") if p.stem != "__init__"]

    fan_in = defaultdict(int)  # Ca
    fan_out = defaultdict(int)  # Ce
    graph = defaultdict(set)

    # 1. 解析フェーズ
    for mod in modules:
        path = root / f"{mod}.py"
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        deps = set()
        for node in ast.walk(tree):
            # Import a
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(package_name):
                        parts = alias.name.split(".")
                        if len(parts) > 1:
                            deps.add(parts[1])
            # From . import a / From package import a
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # absolute import like 'beautyspot.core'
                    if node.module.startswith(package_name):
                        parts = node.module.split(".")
                        if len(parts) > 1:
                            deps.add(parts[1])
                    # relative import (level=0 is absolute)
                    elif node.level == 0 and node.module in modules:
                        deps.add(node.module)
                else:
                    # from . import core (module is None)
                    pass

        # 自分自身は除外
        deps.discard(mod)

        # 集計
        fan_out[mod] = len(deps)
        graph[mod] = deps
        for dep in deps:
            if dep in modules:
                fan_in[dep] += 1

    # 2. 描画フェーズ (Instability = Ce / (Ca + Ce))
    dot = Digraph(comment=f"{package_name} Stability Analysis")
    dot.attr(rankdir="TB")

    print(f"\n{'Module':<15} | {'Ca':<3} | {'Ce':<3} | {'I (Instability)':<6}")
    print("-" * 45)

    for mod in modules:
        ca = fan_in[mod]
        ce = fan_out[mod]
        total = ca + ce
        instability = ce / total if total > 0 else 0.0

        print(f"{mod:<15} | {ca:<3} | {ce:<3} | {instability:.2f}")

        # Color coding: Blue (Stable) -> Red (Volatile)
        # I=0.0 -> Stable (Blue), I=1.0 -> Volatile (Orange/Red)
        if instability <= 0.3:
            color = "#e6f3ff"  # Light Blue
        elif instability >= 0.7:
            color = "#ffe6e6"  # Light Red
        else:
            color = "#ffffff"  # White

        label = f"<{mod}<BR/><FONT POINT-SIZE='10'>I={instability:.2f}</FONT>>"
        dot.node(mod, label=label, style="filled", fillcolor=color, shape="box")

    for mod, deps in graph.items():
        for dep in deps:
            if dep in modules:
                dot.edge(mod, dep)

    outfile = output_path / "architecture_metrics"
    dot.render(outfile, format="png", cleanup=True)
    print(f"\nGraph generated at: {outfile}.png")


if __name__ == "__main__":
    analyze_structure()
