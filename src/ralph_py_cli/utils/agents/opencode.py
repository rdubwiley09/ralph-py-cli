"""OpenCode agent implementation."""

import json
import re
from typing import Optional

from ralph_py_cli.utils.agents.base import AgentProtocol
from ralph_py_cli.utils.token_usage import TokenUsage, parse_token_usage


class OpenCodeAgent(AgentProtocol):
    """Agent implementation for OpenCode CLI."""

    @property
    def name(self) -> str:
        """Agent name."""
        return "opencode"

    def build_command(
        self, plan_text: str, folder_path: str, model: Optional[str] = None
    ) -> tuple[list[str], Optional[str]]:
        """Build OpenCode command with prompt as argument.

        Args:
            plan_text: The full plan/design document text
            folder_path: Path to the project folder (not used in command, used for cwd)
            model: Optional model override

        Returns:
            Tuple of (command_list, stdin_text)
            OpenCode uses command arguments, so stdin_text is None
        """
        prompt = self._build_iteration_prompt(plan_text)
        cmd = ["opencode", "run", prompt, "--format", "json"]

        if model:
            cmd.extend(["--model", model])

        # OpenCode uses command argument, not stdin
        return (cmd, None)

    def parse_output(
        self, raw_output: str
    ) -> tuple[Optional[str], Optional[str], str, Optional[TokenUsage]]:
        """Parse OpenCode JSON output for markers and token usage.

        OpenCode returns newline-delimited JSON (NDJSON) with streaming events.
        We need to extract text from all "text" type events and concatenate them.

        Args:
            raw_output: Raw output from OpenCode CLI

        Returns:
            Tuple of (marker_type, output_message, summary, token_usage)
        """
        text_content = ""
        token_usage = None

        # OpenCode returns NDJSON (newline-delimited JSON)
        # Each line is a separate JSON object representing a streaming event
        lines = raw_output.strip().split('\n')

        for line in lines:
            if not line.strip():
                continue

            try:
                data = json.loads(line)

                # Extract text from "text" type events
                if isinstance(data, dict):
                    event_type = data.get("type")

                    if event_type == "text":
                        # Text content is in part.text
                        part = data.get("part", {})
                        if isinstance(part, dict):
                            text = part.get("text", "")
                            if text:
                                text_content += text

                    # Extract token usage from step_finish events
                    elif event_type == "step_finish" and token_usage is None:
                        part = data.get("part", {})
                        if isinstance(part, dict):
                            tokens = part.get("tokens", {})
                            if tokens:
                                # Try to create TokenUsage from opencode format
                                input_tokens = tokens.get("input", 0)
                                output_tokens = tokens.get("output", 0)
                                cache_info = tokens.get("cache", {})
                                cache_read = cache_info.get("read", 0) if isinstance(cache_info, dict) else 0
                                cache_write = cache_info.get("write", 0) if isinstance(cache_info, dict) else 0

                                if input_tokens or output_tokens:
                                    from ralph_py_cli.utils.token_usage import TokenUsage
                                    token_usage = TokenUsage(
                                        input_tokens=input_tokens,
                                        output_tokens=output_tokens,
                                        cache_read_tokens=cache_read,
                                        cache_creation_tokens=cache_write,
                                    )

            except json.JSONDecodeError:
                # If a line isn't valid JSON, it might be plain text - include it
                text_content += line + "\n"

        # If we didn't extract any text from NDJSON, fall back to treating raw_output as text
        if not text_content:
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
        # If text_content is JSON-like, use raw_output instead for better summary
        summary_text = text_content if not text_content.startswith("{") else raw_output
        fallback_summary = self._extract_fallback_summary(summary_text)
        return None, None, fallback_summary, token_usage

    def _build_iteration_prompt(self, plan_text: str) -> str:
        """Build the prompt for a single OpenCode iteration.

        Args:
            plan_text: The full plan/design document text.

        Returns:
            The formatted prompt to send to OpenCode.
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
