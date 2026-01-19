"""Tests for token usage tracking utilities."""

import pytest

from ralph_py_cli.utils.token_usage import (
    SubscriptionTier,
    TokenUsage,
    TokenUsageTracker,
    parse_token_usage,
)


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_total_tokens(self):
        """Test total_tokens property calculation."""
        usage = TokenUsage(input_tokens=1000, output_tokens=500)
        assert usage.total_tokens == 1500

    def test_total_tokens_with_cache(self):
        """Test that cache tokens don't affect total calculation."""
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=200,
            cache_creation_tokens=100,
        )
        # Cache tokens are tracked separately, not added to total
        assert usage.total_tokens == 1500

    def test_format_compact(self):
        """Test compact formatting."""
        usage = TokenUsage(input_tokens=1800, output_tokens=650)
        formatted = usage.format_compact()
        assert "2,450" in formatted  # Total
        assert "1,800" in formatted  # Input
        assert "650" in formatted  # Output

    def test_default_values(self):
        """Test default values are zero."""
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0
        assert usage.cache_creation_tokens == 0
        assert usage.total_tokens == 0


class TestTokenUsageTracker:
    """Tests for TokenUsageTracker class."""

    def test_add_single_usage(self):
        """Test adding a single usage record."""
        tracker = TokenUsageTracker()
        usage = TokenUsage(input_tokens=1000, output_tokens=500)
        tracker.add_usage(usage)

        assert tracker.total_input_tokens == 1000
        assert tracker.total_output_tokens == 500
        assert tracker.total_tokens == 1500
        assert tracker.iteration_count == 1
        assert len(tracker.usages) == 1

    def test_add_multiple_usages(self):
        """Test accumulation across multiple usages."""
        tracker = TokenUsageTracker()
        tracker.add_usage(TokenUsage(input_tokens=1000, output_tokens=500))
        tracker.add_usage(TokenUsage(input_tokens=2000, output_tokens=800))
        tracker.add_usage(TokenUsage(input_tokens=1500, output_tokens=700))

        assert tracker.total_input_tokens == 4500
        assert tracker.total_output_tokens == 2000
        assert tracker.total_tokens == 6500
        assert tracker.iteration_count == 3

    def test_get_tier_percentage_pro(self):
        """Test percentage calculation for Pro tier."""
        tracker = TokenUsageTracker()
        tracker.add_usage(TokenUsage(input_tokens=4400, output_tokens=0))

        percentage = tracker.get_tier_percentage(SubscriptionTier.PRO)
        assert percentage == pytest.approx(10.0, rel=0.01)  # 4400/44000 = 10%

    def test_get_tier_percentage_max_5x(self):
        """Test percentage calculation for Max 5x tier."""
        tracker = TokenUsageTracker()
        tracker.add_usage(TokenUsage(input_tokens=8800, output_tokens=0))

        percentage = tracker.get_tier_percentage(SubscriptionTier.MAX_5X)
        assert percentage == pytest.approx(10.0, rel=0.01)  # 8800/88000 = 10%

    def test_get_tier_percentage_max_20x(self):
        """Test percentage calculation for Max 20x tier."""
        tracker = TokenUsageTracker()
        tracker.add_usage(TokenUsage(input_tokens=22000, output_tokens=0))

        percentage = tracker.get_tier_percentage(SubscriptionTier.MAX_20X)
        assert percentage == pytest.approx(10.0, rel=0.01)  # 22000/220000 = 10%

    def test_format_summary(self):
        """Test summary formatting."""
        tracker = TokenUsageTracker()
        tracker.add_usage(TokenUsage(input_tokens=4000, output_tokens=1550))

        summary = tracker.format_summary()
        assert "5,550" in summary  # Total
        assert "4,000" in summary  # Input
        assert "1,550" in summary  # Output

    def test_format_summary_with_cache(self):
        """Test summary includes cache info when present."""
        tracker = TokenUsageTracker()
        tracker.add_usage(
            TokenUsage(
                input_tokens=1000,
                output_tokens=500,
                cache_read_tokens=200,
                cache_creation_tokens=100,
            )
        )

        summary = tracker.format_summary()
        assert "Cache read" in summary
        assert "Cache creation" in summary

    def test_create_tier_table(self):
        """Test tier table creation doesn't raise errors."""
        tracker = TokenUsageTracker()
        tracker.add_usage(TokenUsage(input_tokens=5000, output_tokens=550))

        # Just verify it creates a table without errors
        table = tracker.create_tier_table()
        assert table is not None
        assert table.title == "5-Hour Rate Limit Usage Estimate"


class TestParseTokenUsage:
    """Tests for parse_token_usage function."""

    def test_parse_usage_at_root(self):
        """Test parsing when usage is at root level."""
        json_data = {
            "result": "Some response",
            "usage": {
                "input_tokens": 1500,
                "output_tokens": 800,
            },
        }
        usage = parse_token_usage(json_data)

        assert usage is not None
        assert usage.input_tokens == 1500
        assert usage.output_tokens == 800

    def test_parse_usage_with_cache_tokens(self):
        """Test parsing includes cache tokens."""
        json_data = {
            "usage": {
                "input_tokens": 1500,
                "output_tokens": 800,
                "cache_read_input_tokens": 300,
                "cache_creation_input_tokens": 150,
            },
        }
        usage = parse_token_usage(json_data)

        assert usage is not None
        assert usage.input_tokens == 1500
        assert usage.output_tokens == 800
        assert usage.cache_read_tokens == 300
        assert usage.cache_creation_tokens == 150

    def test_parse_usage_nested_in_result(self):
        """Test parsing when usage is nested in result."""
        json_data = {
            "result": {
                "text": "Some response",
                "usage": {
                    "input_tokens": 2000,
                    "output_tokens": 1000,
                },
            },
        }
        usage = parse_token_usage(json_data)

        assert usage is not None
        assert usage.input_tokens == 2000
        assert usage.output_tokens == 1000

    def test_parse_no_usage_data(self):
        """Test returns None when no usage data present."""
        json_data = {
            "result": "Some response",
        }
        usage = parse_token_usage(json_data)

        assert usage is None

    def test_parse_zero_tokens(self):
        """Test returns None when tokens are zero."""
        json_data = {
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
            },
        }
        usage = parse_token_usage(json_data)

        assert usage is None

    def test_parse_partial_tokens(self):
        """Test parsing with only input tokens."""
        json_data = {
            "usage": {
                "input_tokens": 1000,
            },
        }
        usage = parse_token_usage(json_data)

        # Returns None because output_tokens defaults to 0 and total would be
        # only input which is valid
        assert usage is not None
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 0

    def test_parse_invalid_usage_type(self):
        """Test handles non-dict usage gracefully."""
        json_data = {
            "usage": "invalid",
        }
        usage = parse_token_usage(json_data)

        assert usage is None


class TestSubscriptionTier:
    """Tests for SubscriptionTier enum."""

    def test_tier_display_names(self):
        """Test tier display names are set correctly."""
        assert SubscriptionTier.PRO.display_name == "Pro"
        assert SubscriptionTier.MAX_5X.display_name == "Max 5x"
        assert SubscriptionTier.MAX_20X.display_name == "Max 20x"

    def test_tier_token_limits(self):
        """Test tier token limits are set correctly."""
        assert SubscriptionTier.PRO.token_limit == 44_000
        assert SubscriptionTier.MAX_5X.token_limit == 88_000
        assert SubscriptionTier.MAX_20X.token_limit == 220_000

    def test_all_tiers_iterable(self):
        """Test all tiers can be iterated."""
        tiers = list(SubscriptionTier)
        assert len(tiers) == 3
