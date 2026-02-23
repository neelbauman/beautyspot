#!/usr/bin/env python3
"""
tools/generate_claude_ref.py

Auto-generates the Reference section of CLAUDE.md from source code.
Reads class/function docstrings and CLI command declarations via AST — no imports needed.

Usage:
    uv run python tools/generate_claude_ref.py
    make update-claude
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src" / "beautyspot"
CLAUDE_MD = ROOT / "CLAUDE.md"

MARKER = "<!-- AUTO-GENERATED BELOW — run `make update-claude` to refresh -->"

# Modules to skip in the summary (no public classes to list)
SKIP_MODULES = {"_version", "dashboard", "__init__"}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _first_docline(node: ast.AST) -> str:
    doc = ast.get_docstring(node)  # type: ignore[arg-type]
    if doc:
        return doc.strip().splitlines()[0].rstrip(".")
    return ""


def _classes_with_docs(filepath: Path) -> list[tuple[str, str]]:
    """Return [(ClassName, first_doc_line)] for all classes with docstrings."""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    return [
        (node.name, _first_docline(node))
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and _first_docline(node)
    ]


def _cli_commands(filepath: Path) -> list[tuple[str, str]]:
    """Return [(command_name, description)] from @app.command(...) decorators."""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "command"
                and dec.args
            ):
                continue
            try:
                cmd_name = ast.literal_eval(dec.args[0])
            except Exception:
                continue
            raw = _first_docline(node)
            clean = re.sub(r"\[/?[^\]]*\]", "", raw).strip()  # strip rich markup
            results.append((cmd_name, clean))
    return results


def _public_exports(filepath: Path) -> list[str]:
    """Return names listed in __all__."""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, ast.List):
                    return [
                        ast.literal_eval(elt)
                        for elt in node.value.elts
                        if isinstance(elt, ast.Constant)
                    ]
    return []


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _section_modules() -> list[str]:
    lines = ["### Modules", "", "| Module | Key classes |", "|---|---|"]
    for fp in sorted(SRC.glob("*.py")):
        if fp.stem in SKIP_MODULES or fp.stem.startswith("__"):
            continue
        classes = _classes_with_docs(fp)
        cell = ", ".join(f"`{name}`" for name, _ in classes[:5]) if classes else "—"
        lines.append(f"| `{fp.stem}.py` | {cell} |")
    lines.append("")
    return lines


def _section_class_summaries() -> list[str]:
    lines = ["### Class Summaries", ""]
    for fp in sorted(SRC.glob("*.py")):
        if fp.stem in SKIP_MODULES or fp.stem.startswith("__") or fp.stem == "cli":
            continue
        classes = _classes_with_docs(fp)
        if not classes:
            continue
        lines.append(f"**`{fp.stem}.py`**")
        lines.append("")
        for name, doc in classes:
            lines.append(f"- `{name}`: {doc}")
        lines.append("")
    return lines


def _section_cli() -> list[str]:
    cli_path = SRC / "cli.py"
    if not cli_path.exists():
        return []
    commands = _cli_commands(cli_path)
    if not commands:
        return []
    lines = ["### CLI Commands", "", "| Command | Description |", "|---|---|"]
    for cmd, doc in commands:
        lines.append(f"| `beautyspot {cmd}` | {doc} |")
    lines.append("")
    return lines


def _section_public_api() -> list[str]:
    init_path = SRC / "__init__.py"
    if not init_path.exists():
        return []
    exports = _public_exports(init_path)
    if not exports:
        return []
    names = ", ".join(f"`{n}`" for n in exports)
    return [
        "### Public API (`import beautyspot as bs`)",
        "",
        names,
        "",
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate_section() -> str:
    parts: list[str] = [
        MARKER,
        "",
        "## Reference (Auto-generated — do not edit manually)",
        "",
    ]
    parts += _section_modules()
    parts += _section_class_summaries()
    parts += _section_cli()
    parts += _section_public_api()
    return "\n".join(parts) + "\n"


def update_claude_md() -> None:
    current = CLAUDE_MD.read_text(encoding="utf-8")

    # Keep everything above the marker
    if MARKER in current:
        manual_zone = current[: current.index(MARKER)].rstrip()
    else:
        manual_zone = current.rstrip()

    new_content = manual_zone + "\n\n" + generate_section()
    CLAUDE_MD.write_text(new_content, encoding="utf-8")
    print(f"✓ Updated {CLAUDE_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    update_claude_md()
