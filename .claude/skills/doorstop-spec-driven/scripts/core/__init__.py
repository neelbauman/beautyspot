import os as _os
import sys as _sys

# core/ 配下のスクリプトは from _common import ... 等のベアインポートを使う。
# スタンドアロン実行時は core/ が sys.path[0] になるため問題ないが、
# パッケージとしてインポートされた場合 (例: from core._common import ...)
# にはベアインポートが解決できない。core/ 自身を sys.path に追加して解決する。
_core_dir = _os.path.dirname(_os.path.abspath(__file__))
if _core_dir not in _sys.path:
    _sys.path.insert(0, _core_dir)

from .validator import validate_tree as validate_tree, compute_coverage as compute_coverage  # noqa: E402
