# tests/unit/test_lifecycle_extended.py
"""SPEC-008: Retention.FOREVER と resolve_with_fallback のテスト"""

from datetime import timedelta
from beautyspot.lifecycle import (
    LifecyclePolicy,
    Rule,
    Retention,
    _ForeverSentinel,
)


class TestRetentionForever:
    """Retention.FOREVER の単体テスト"""

    def test_forever_is_singleton(self):
        """FOREVER は常に同じインスタンスであること"""
        assert Retention.FOREVER is _ForeverSentinel()

    def test_forever_is_truthy(self):
        """FOREVER は真値であること"""
        assert bool(Retention.FOREVER) is True

    def test_forever_repr(self):
        """FOREVER の repr は 'Retention.FOREVER' であること"""
        assert repr(Retention.FOREVER) == "Retention.FOREVER"

    def test_forever_is_not_none(self):
        """FOREVER は INDEFINITE (None) と区別されること"""
        assert Retention.FOREVER is not Retention.INDEFINITE
        assert Retention.FOREVER is not None

    def test_forever_is_instance_of_sentinel(self):
        """FOREVER は _ForeverSentinel のインスタンスであること"""
        assert isinstance(Retention.FOREVER, _ForeverSentinel)


class TestResolveWithFallback:
    """LifecyclePolicy.resolve_with_fallback のテスト"""

    def test_matches_full_identifier_first(self):
        """完全修飾名にマッチするルールが優先されること"""
        rules = [
            Rule(pattern="mymodule.tasks.*", retention="30d"),
            Rule(pattern="heavy_*", retention="1h"),
        ]
        policy = LifecyclePolicy(rules)

        result = policy.resolve_with_fallback(
            func_identifier="mymodule.tasks.heavy_compute",
            func_name="heavy_compute",
        )
        assert result == timedelta(days=30)

    def test_falls_back_to_short_name(self):
        """完全修飾名にマッチしない場合、短縮名でフォールバックすること"""
        rules = [
            Rule(pattern="mymodule.other.*", retention="30d"),
            Rule(pattern="heavy_*", retention="1h"),
        ]
        policy = LifecyclePolicy(rules)

        result = policy.resolve_with_fallback(
            func_identifier="mymodule.tasks.heavy_compute",
            func_name="heavy_compute",
        )
        assert result == timedelta(hours=1)

    def test_no_match_returns_indefinite(self):
        """どちらにもマッチしない場合は INDEFINITE を返すこと"""
        rules = [
            Rule(pattern="specific_module.*", retention="1d"),
        ]
        policy = LifecyclePolicy(rules)

        result = policy.resolve_with_fallback(
            func_identifier="other_module.func",
            func_name="func",
        )
        assert result is Retention.INDEFINITE

    def test_identifier_match_wins_over_name_match(self):
        """同じルールセットで identifier と name の両方がマッチする場合、identifier が優先"""
        rules = [
            Rule(pattern="pkg.mod.*", retention="7d"),
            Rule(pattern="compute", retention="1h"),
        ]
        policy = LifecyclePolicy(rules)

        result = policy.resolve_with_fallback(
            func_identifier="pkg.mod.compute",
            func_name="compute",
        )
        # identifier 側の "pkg.mod.*" にマッチ → 7d
        assert result == timedelta(days=7)

    def test_fallback_with_wildcard_patterns(self):
        """ワイルドカードパターンのフォールバック動作"""
        rules = [
            Rule(pattern="production.*", retention="365d"),
            Rule(pattern="tmp_*", retention="1h"),
        ]
        policy = LifecyclePolicy(rules)

        # identifier にマッチしないが、短縮名にマッチ
        result = policy.resolve_with_fallback(
            func_identifier="dev.experiments.tmp_result",
            func_name="tmp_result",
        )
        assert result == timedelta(hours=1)
