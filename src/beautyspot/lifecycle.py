# src/beautyspot/lifecycle.py

import fnmatch
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, List, Union
from beautyspot.exceptions import ValidationError

# Regex for parsing retention strings (e.g., "7d", "12h", "30m")
_TIME_PATTERN = re.compile(r"^(\d+)([dhm])$")


def parse_retention(value: Union[str, timedelta, int, None]) -> Optional[timedelta]:
    """
    Helper function to normalize retention specification to timedelta.
    None means 'indefinite'.
    int is treated as 'seconds'.
    """
    if value is None:
        return None

    if isinstance(value, timedelta):
        return value

    if isinstance(value, int):
        return timedelta(seconds=value)

    if isinstance(value, str):
        match = _TIME_PATTERN.match(value)
        if not match:
            raise ValidationError(
                f"Invalid retention format: '{value}'. Use format like '7d', '12h', '30m'."
            )

        amount, unit = int(match.group(1)), match.group(2)
        if unit == "d":
            return timedelta(days=amount)
        elif unit == "h":
            return timedelta(hours=amount)
        elif unit == "m":
            return timedelta(minutes=amount)

    raise ValidationError(f"Retention must be str, int, or timedelta, got {type(value)}")


class Retention:
    """Constants for retention policies."""

    INDEFINITE = None


@dataclass
class Rule:
    """
    A rule defining retention policy based on function name pattern.
    """

    pattern: str
    retention: Union[str, timedelta, None]


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

    @classmethod
    def default(cls) -> "LifecyclePolicy":
        """Default policy: Everything is kept indefinitely."""
        return cls(rules=[])

