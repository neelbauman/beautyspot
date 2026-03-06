# tests/unit/test_lifecycle.py

import pytest
from datetime import timedelta
from beautyspot.lifecycle import parse_retention, LifecyclePolicy, Rule, Retention


class TestParseRetention:
    """parse_retention 関数のテスト"""

    def test_parse_none(self):
        """None は None (INDEFINITE) を返すべき"""
        assert parse_retention(None) is None

    def test_parse_timedelta(self):
        """timedelta オブジェクトはそのまま返すべき"""
        td = timedelta(hours=1)
        assert parse_retention(td) == td

    def test_parse_int(self):
        """int は秒数として解釈されるべき"""
        assert parse_retention(60) == timedelta(seconds=60)

    def test_parse_float(self):
        """float は秒数として解釈されるべき"""
        assert parse_retention(3600.5) == timedelta(seconds=3600.5)

    @pytest.mark.parametrize(
        "input_str, expected",
        [
            ("7d", timedelta(days=7)),
            ("12h", timedelta(hours=12)),
            ("30m", timedelta(minutes=30)),
        ],
    )
    def test_parse_str_valid(self, input_str, expected):
        """有効なフォーマット文字列のパース"""
        assert parse_retention(input_str) == expected

    @pytest.mark.parametrize(
        "non_positive_value",
        [
            "0d",
            0,
            -10,
            timedelta(seconds=0),
            timedelta(seconds=-1),
        ],
    )
    def test_parse_non_positive(self, non_positive_value):
        """0以下の値は ValueError を送出すること"""
        with pytest.raises(ValueError, match="positive"):
            parse_retention(non_positive_value)

    @pytest.mark.parametrize(
        "invalid_str",
        [
            "7",  # 単位なし
            "d",  # 数字なし
            "1y",  # 未サポートの単位
            "100s",  # 未サポートの単位 (現状 d, h, m のみ)
            "invalid",  # フォーマット違い
        ],
    )
    def test_parse_str_invalid(self, invalid_str):
        """無効なフォーマット文字列は ValueError を送出すること"""
        with pytest.raises(ValueError, match="Invalid retention format"):
            parse_retention(invalid_str)

    def test_parse_invalid_type(self):
        """未サポートの型は ValueError (ValidationError) を送出すること"""
        with pytest.raises(ValueError, match="Retention must be"):
            parse_retention([1, 2])  # type: ignore # list is not supported


class TestLifecyclePolicy:
    """LifecyclePolicy クラスのテスト"""

    def test_resolve_exact_match(self):
        """完全一致パターンの解決"""
        rules = [
            Rule(pattern="my_func", retention="1h"),
            Rule(pattern="other", retention="7d"),
        ]
        policy = LifecyclePolicy(rules)

        assert policy.resolve("my_func") == timedelta(hours=1)
        assert policy.resolve("other") == timedelta(days=7)

    def test_resolve_wildcard_match(self):
        """ワイルドカード (*) を含むパターンの解決"""
        rules = [
            Rule(pattern="report_*", retention="30d"),
            Rule(pattern="tmp_*", retention="1h"),
        ]
        policy = LifecyclePolicy(rules)

        assert policy.resolve("report_monthly") == timedelta(days=30)
        assert policy.resolve("tmp_debug") == timedelta(hours=1)

    def test_resolve_first_match_wins(self):
        """最初にマッチしたルールのポリシーが適用されること (順序依存)"""
        rules = [
            Rule(pattern="test_*", retention="1m"),  # 具体的なルール
            Rule(pattern="*", retention="365d"),  # 包括的なルール
        ]
        policy = LifecyclePolicy(rules)

        # "test_" で始まるものは 1m になるべき
        assert policy.resolve("test_01") == timedelta(minutes=1)
        # それ以外は 1y
        assert (
            policy.resolve("production_data") == timedelta(days=365)
        )  # 1y not supported explicitly in parser test above, assuming 365d logic or just checking fallback logic logic if we used "365d"

    def test_resolve_no_match_default(self):
        """どのルールにもマッチしない場合は None (Indefinite) を返すこと"""
        rules = [Rule(pattern="specific", retention="1h")]
        policy = LifecyclePolicy(rules)

        assert policy.resolve("unknown_func") is Retention.INDEFINITE

    def test_default_policy(self):
        """default() ファクトリは空のルールを持つこと"""
        policy = LifecyclePolicy.default()
        assert policy.rules == []
        assert policy.resolve("anything") is Retention.INDEFINITE
