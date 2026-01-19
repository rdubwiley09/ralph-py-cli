"""Claude Code agent implementation."""

import json
import re
from typing import Optional

from ralph_py_cli.utils.agents.base import AgentProtocol
from ralph_py_cli.utils.token_usage import TokenUsage, parse_token_usage


class ClaudeAgent(AgentProtocol):
    """Agent implementation for Claude Code CLI."""

    @property
    def name(self) -> str:
        """Agent name."""
        return "claude"

    def build_command(
        self, plan_text: str, folder_path: str, model: Optional[str] = None
    ) -> tuple[list[str], Optional[str]]:
        """Build Claude Code command with stdin prompt.

        Args:
            plan_text: The full plan/design document text
            folder_path: Path to the project folder (not used in command, used for cwd)
            model: Optional model override

        Returns:
            Tuple of (command_list, stdin_text)
        """
        cmd = ["claude", "-p", "--dangerously-skip-permissions", "--output-format", "json"]
        if model:
            cmd.extend(["--model", model])

        prompt = self._build_iteration_prompt(plan_text)
        return (cmd, prompt)

    def parse_output(
        self, raw_output: str
    ) -> tuple[Optional[str], Optional[str], str, Optional[TokenUsage]]:
        """Parse Claude Code JSON output for markers and token usage.

        Args:
            raw_output: Raw output from Claude Code CLI

        Returns:
            Tuple of (marker_type, output_message, summary, token_usage)
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
        fallback_summary = self._extract_fallback_summary(text_content)
        return None, None, fallback_summary, token_usage

    def _build_iteration_prompt(self, plan_text: str) -> str:
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

    def _extract_fallback_summary(self, text: str) -> str:
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
