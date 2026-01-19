"""Claude Code runner utilities for iterative execution.

DEPRECATED: This module is deprecated. Use ralph_py_cli.utils.agent_runner instead.
The agent_runner module provides a unified interface for multiple agents (claude, opencode).
"""

import warnings
from pathlib import Path
from typing import Optional

# Import from new agent system
from ralph_py_cli.utils.agents.base import AgentRunResult as ClaudeRunResult
from ralph_py_cli.utils.agents.base import RunStatus
from ralph_py_cli.utils.agent_runner import run_agent_iteration
from ralph_py_cli.utils.token_usage import TokenUsage

# Emit deprecation warning when module is imported
warnings.warn(
    "ralph_py_cli.utils.claude_runner is deprecated, use ralph_py_cli.utils.agent_runner instead",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export for backward compatibility
__all__ = ["RunStatus", "ClaudeRunResult", "run_claude_iteration"]


def build_iteration_prompt(plan_text: str) -> str:
    """Build the prompt for a single Claude Code iteration.

    Args:
        plan_text: The full plan/design document text.

    Returns:
        The formatted prompt to send to Claude Code.
    """
    return f"""You are working on implementing a design document iteratively. Here is the full plan:

<plan>
{plan_text}
</plan>

Your task for this iteration:
1. Review the current state of the codebase
2. Pick ONE specific aspect from the plan to implement or improve
3. Make the necessary changes
4. When done, output a status marker in one of these formats:

If you made progress but the task is NOT yet fully complete:
<Improved>Brief summary of what you did and what remains</Improved>

If the task is FULLY FINISHED according to the plan:
<Completed>Brief summary confirming task completion</Completed>

Important:
- Focus on just ONE task per iteration
- Always end with either <Improved>...</Improved> or <Completed>...</Completed>
- Use <Improved> when there is still more work to do
- Use <Completed> only when the entire plan is fully implemented
- The marker should contain a concise summary of your changes
"""


def parse_claude_output(
    raw_output: str,
) -> tuple[Optional[str], Optional[str], str, Optional[TokenUsage]]:
    """Parse Claude Code JSON output to extract the status marker and token usage.

    Args:
        raw_output: The raw JSON output from Claude Code CLI.

    Returns:
        A tuple of (marker_type, output_message, summary, token_usage) where:
        - marker_type is "improved", "completed", or None if not found
        - output_message is the content from the marker (or None if not found)
        - summary is the output message or a fallback summary
        - token_usage is the TokenUsage if available, None otherwise

        If both markers are present, <Completed> takes precedence.
    """
    # Try to parse as JSON first
    text_content = ""
    token_usage = None
    try:
        data = json.loads(raw_output)
        # Claude CLI JSON output has a "result" field with the response
        if isinstance(data, dict):
            result = data.get("result", "")
            if isinstance(result, str):
                text_content = result
            elif isinstance(result, dict):
                # Handle nested structure if present
                text_content = result.get("text", str(result))

            # Extract token usage from JSON
            token_usage = parse_token_usage(data)
    except json.JSONDecodeError:
        # If not valid JSON, treat the whole output as text
        text_content = raw_output

    # Look for <Completed> first (takes priority)
    completed_pattern = r"<Completed>(.*?)</Completed>"
    completed_match = re.search(completed_pattern, text_content, re.DOTALL)

    if completed_match:
        output_message = completed_match.group(1).strip()
        return "completed", output_message, output_message, token_usage

    # Look for <Improved> marker
    improved_pattern = r"<Improved>(.*?)</Improved>"
    improved_match = re.search(improved_pattern, text_content, re.DOTALL)

    if improved_match:
        output_message = improved_match.group(1).strip()
        return "improved", output_message, output_message, token_usage

    # Fallback: try to extract a summary from the output
    # Look for common patterns that might indicate what was done
    fallback_summary = _extract_fallback_summary(text_content)
    return None, None, fallback_summary, token_usage


def _extract_fallback_summary(text: str) -> str:
    """Extract a fallback summary when no completion marker is found.

    Args:
        text: The text content to extract a summary from.

    Returns:
        A summary string, or a default message if nothing useful found.
    """
    # Try to find the last meaningful paragraph or statement
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    if not lines:
        return "No output captured"

    # Return the last few non-empty lines as a summary
    summary_lines = lines[-3:] if len(lines) > 3 else lines
    return " ".join(summary_lines)[:500]  # Limit length


def run_claude_iteration(
    plan_text: str,
    folder_path: str,
    timeout_seconds: float = 300.0,
    model: Optional[str] = None,
) -> ClaudeRunResult:
    """Run a single Claude Code iteration on a folder.

    DEPRECATED: Use run_agent_iteration with agent_type='claude' instead.

    Args:
        plan_text: The plan/design document text to guide Claude.
        folder_path: The folder path where Claude should work.
        timeout_seconds: Maximum time to wait for completion (default 5 minutes).
        model: Optional model override for Claude Code.

    Returns:
        ClaudeRunResult with status and output information.
    """
    # Delegate to new agent runner with agent_type='claude'
    return run_agent_iteration(
        agent_type="claude",
        plan_text=plan_text,
        folder_path=folder_path,
        timeout_seconds=timeout_seconds,
        model=model,
    )
