"""Base agent protocol and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ralph_py_cli.utils.token_usage import TokenUsage


class RunStatus(Enum):
    """Status of an agent run."""

    IMPROVED = "improved"  # Made progress but task not complete
    COMPLETED = "completed"  # Task fully finished per spec
    TIMEOUT = "timeout"
    PROCESS_ERROR = "process_error"
    MISSING_MARKER = "missing_marker"


@dataclass
class AgentRunResult:
    """Result from a single agent iteration."""

    status: RunStatus
    output_message: str  # From <Improved> or <Completed> marker
    summary: str  # Summary of what was done
    raw_output: str  # Full output for debugging
    return_code: Optional[int] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None
    token_usage: Optional[TokenUsage] = None


class AgentProtocol(ABC):
    """Base protocol for AI coding agents."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name (e.g., 'claude', 'opencode')."""
        pass

    @abstractmethod
    def build_command(
        self, plan_text: str, folder_path: str, model: Optional[str] = None
    ) -> tuple[list[str], Optional[str]]:
        """Build command and optional stdin input.

        Args:
            plan_text: The full plan/design document text
            folder_path: Path to the project folder
            model: Optional model override

        Returns:
            Tuple of (command_list, stdin_text)
            - For Claude: (["claude", "-p", ...], prompt_text)
            - For OpenCode: (["opencode", "run", prompt_text], None)
        """
        pass

    @abstractmethod
    def parse_output(
        self, raw_output: str
    ) -> tuple[Optional[str], Optional[str], str, Optional[TokenUsage]]:
        """Parse agent output for status markers and token usage.

        Args:
            raw_output: Raw output from the agent subprocess

        Returns:
            Tuple of (marker_type, output_message, summary, token_usage)
            - marker_type: "completed", "improved", or None
            - output_message: Content from the marker
            - summary: Brief summary for display
            - token_usage: Token usage data if available
        """
        pass
