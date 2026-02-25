# src/beautyspot/lifecycle.py

import fnmatch
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, List, Union
from beautyspot.exceptions import ValidationError

# Regex for parsing retention strings (e.g., "7d", "12h", "30m")
_TIME_PATTERN = re.compile(r"^(\d+)([dhm])$")


class _ForeverSentinel:
    """ライフサイクルポリシーを明示的にバイパスし、無期限保持を指定するセンチネル。

    ``Retention.FOREVER`` として公開され、``@spot.mark(retention=Retention.FOREVER)``
    のようにデコレータに渡すことで、グローバルなライフサイクルポリシーが設定されていても
    そのキャッシュエントリを無期限に保持できます。
    """

    _instance: "_ForeverSentinel | None" = None

    def __new__(cls) -> "_ForeverSentinel":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "Retention.FOREVER"

    def __bool__(self) -> bool:
        return True


_FOREVER = _ForeverSentinel()


# parse_retention の受け取り可能な型 (FOREVER sentinel を含む)
RetentionSpec = Union[str, timedelta, int, float, _ForeverSentinel, None]


def parse_retention(value: Union[str, timedelta, int, float, None]) -> Optional[timedelta]:
    """
    Helper function to normalize retention specification to timedelta.
    None means 'indefinite' (defers to lifecycle policy).
    int is treated as 'seconds'.

    Note:
        ``_ForeverSentinel`` (``Retention.FOREVER``) は本関数では処理しません。
        呼び出し元 (``Spot._calculate_expires_at``) で事前にチェックしてください。
    """
    if value is None:
        return None

    if isinstance(value, timedelta):
        if value.total_seconds() <= 0:
            raise ValidationError(f"Retention timedelta must be positive, got {value}.")
        return value

    if isinstance(value, (int, float)):
        if value <= 0:
            raise ValidationError(
                f"Retention must be a positive number (seconds), got {value}."
            )
        return timedelta(seconds=value)

    if isinstance(value, str):
        match = _TIME_PATTERN.match(value)
        if not match:
            raise ValidationError(
                f"Invalid retention format: '{value}'. Use format like '7d', '12h', '30m'."
            )

        amount, unit = int(match.group(1)), match.group(2)
        if amount <= 0:
            raise ValidationError(
                f"Retention duration must be positive, got '{value}'."
            )
        if unit == "d":
            return timedelta(days=amount)
        elif unit == "h":
            return timedelta(hours=amount)
        elif unit == "m":
            return timedelta(minutes=amount)

    raise ValidationError(
        f"Retention must be str, int, float, or timedelta, got {type(value)}"
    )


class Retention:
    """Constants for retention policies.

    Attributes:
        INDEFINITE: ライフサイクルポリシーに委ねるデフォルト値 (None)。
            ポリシーが設定されている場合はそのルールに従い、
            未設定の場合は無期限保持となります。
        FOREVER: ライフサイクルポリシーを明示的にバイパスし、
            このキャッシュエントリを常に無期限保持することを宣言します。
            ``@spot.mark(retention=Retention.FOREVER)`` で使用します。
    """

    INDEFINITE = None
    FOREVER: _ForeverSentinel = _FOREVER


@dataclass
class Rule:
    """
    A rule defining retention policy based on function name pattern.
    """

    pattern: str
    retention: Union[str, timedelta, int, None]


class LifecyclePolicy:
    """
    Manages data retention policies based on function names.
    """

    def __init__(self, rules: List[Rule]):
        self.rules = rules

    def resolve(self, func_name: str) -> Optional[timedelta]:
        """
        Find the first matching rule for the given function name.
        Returns the retention timedelta, or None if indefinite (or no match).
        """
        for rule in self.rules:
            if fnmatch.fnmatch(func_name, rule.pattern):
                return parse_retention(rule.retention)
        # Default is indefinite (None)
        return Retention.INDEFINITE

    def resolve_with_fallback(
        self, func_identifier: str, func_name: str
    ) -> Optional[timedelta]:
        """
        Resolve retention using the fully-qualified identifier first, then
        fall back to the short function name for backward compatibility.
        """
        for rule in self.rules:
            if fnmatch.fnmatch(func_identifier, rule.pattern):
                return parse_retention(rule.retention)

        for rule in self.rules:
            if fnmatch.fnmatch(func_name, rule.pattern):
                return parse_retention(rule.retention)

        return Retention.INDEFINITE

    @classmethod
    def default(cls) -> "LifecyclePolicy":
        """Default policy: Everything is kept indefinitely."""
        return cls(rules=[])
