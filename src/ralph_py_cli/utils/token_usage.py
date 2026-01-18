"""Token usage tracking utilities for Claude Code runs."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich.table import Table


class SubscriptionTier(Enum):
    """Claude subscription tiers with estimated 5-hour token budgets."""

    PRO = ("Pro", 44_000)
    MAX_5X = ("Max 5x", 88_000)
    MAX_20X = ("Max 20x", 220_000)

    def __init__(self, display_name: str, token_limit: int):
        self.display_name = display_name
        self.token_limit = token_limit


@dataclass
class TokenUsage:
    """Token counts from a single Claude Code run."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens used in this run."""
        return self.input_tokens + self.output_tokens

    def format_compact(self) -> str:
        """Format as a compact one-line string."""
        return f"Tokens: {self.total_tokens:,} (in: {self.input_tokens:,}, out: {self.output_tokens:,})"


@dataclass
class TokenUsageTracker:
    """Accumulates token usage across multiple iterations."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_creation_tokens: int = 0
    iteration_count: int = 0
    usages: list[TokenUsage] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        """Total tokens used across all iterations."""
        return self.total_input_tokens + self.total_output_tokens

    def add_usage(self, usage: TokenUsage) -> None:
        """Add a single run's usage to the tracker."""
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens
        self.total_cache_read_tokens += usage.cache_read_tokens
        self.total_cache_creation_tokens += usage.cache_creation_tokens
        self.iteration_count += 1
        self.usages.append(usage)

    def get_tier_percentage(self, tier: SubscriptionTier) -> float:
        """Calculate percentage of a tier's 5-hour limit used."""
        if tier.token_limit == 0:
            return 0.0
        return (self.total_tokens / tier.token_limit) * 100

    def format_summary(self) -> str:
        """Format a summary of total usage."""
        lines = [
            f"Total tokens used: {self.total_tokens:,}",
            f"  Input: {self.total_input_tokens:,}",
            f"  Output: {self.total_output_tokens:,}",
        ]
        if self.total_cache_read_tokens > 0:
            lines.append(f"  Cache read: {self.total_cache_read_tokens:,}")
        if self.total_cache_creation_tokens > 0:
            lines.append(f"  Cache creation: {self.total_cache_creation_tokens:,}")
        return "\n".join(lines)

    def create_tier_table(self) -> Table:
        """Create a Rich table showing usage across subscription tiers."""
        table = Table(title="5-Hour Rate Limit Usage Estimate")
        table.add_column("Tier", style="cyan")
        table.add_column("Tokens Used", justify="right")
        table.add_column("Limit", justify="right")
        table.add_column("Usage %", justify="right")

        for tier in SubscriptionTier:
            percentage = self.get_tier_percentage(tier)

            # Color-code based on usage percentage
            if percentage >= 80:
                style = "bold red"
            elif percentage >= 50:
                style = "yellow"
            else:
                style = "green"

            table.add_row(
                tier.display_name,
                f"{self.total_tokens:,}",
                f"{tier.token_limit:,}",
                f"[{style}]{percentage:.1f}%[/{style}]",
            )

        return table


def parse_token_usage(json_data: dict) -> Optional[TokenUsage]:
    """Extract token usage from Claude CLI JSON output.

    Args:
        json_data: Parsed JSON output from Claude CLI.

    Returns:
        TokenUsage instance if token data found, None otherwise.
    """
    # Try different locations where token data might be
    usage_data = None

    # Location 1: data["usage"]
    if "usage" in json_data and isinstance(json_data["usage"], dict):
        usage_data = json_data["usage"]

    # Location 2: nested in result
    elif "result" in json_data and isinstance(json_data["result"], dict):
        result = json_data["result"]
        if "usage" in result and isinstance(result["usage"], dict):
            usage_data = result["usage"]

    if usage_data is None:
        return None

    # Extract token counts with safe defaults
    input_tokens = usage_data.get("input_tokens", 0)
    output_tokens = usage_data.get("output_tokens", 0)
    cache_read = usage_data.get("cache_read_input_tokens", 0)
    cache_creation = usage_data.get("cache_creation_input_tokens", 0)

    # Only return if we have at least some token data
    if input_tokens == 0 and output_tokens == 0:
        return None

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
    )
