#!/usr/bin/env python3
"""Bump version in pyproject.toml"""
import sys
import re
from pathlib import Path


def bump_version(bump_type: str) -> None:
    """Bump version in pyproject.toml
    
    Args:
        bump_type: 'major', 'minor', or 'patch'
    """
    pyproject = Path("pyproject.toml")
    content = pyproject.read_text()
    
    # 現在のバージョンを取得
    match = re.search(r'version = "(\d+)\.(\d+)\.(\d+)"', content)
    if not match:
        print("Error: Could not find version in pyproject.toml")
        sys.exit(1)
    
    major, minor, patch = map(int, match.groups())
    
    # バージョンをインクリメント
    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        print(f"Error: Invalid bump type '{bump_type}'. Use 'major', 'minor', or 'patch'")
        sys.exit(1)
    
    new_version = f"{major}.{minor}.{patch}"
    old_version = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    
    # ファイルを更新
    new_content = content.replace(
        f'version = "{old_version}"',
        f'version = "{new_version}"'
    )
    pyproject.write_text(new_content)
    
    print(f"✓ Version bumped: {old_version} -> {new_version}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python bump_version.py [major|minor|patch]")
        sys.exit(1)
    
    bump_version(sys.argv[1])

