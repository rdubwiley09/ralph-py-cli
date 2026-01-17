"""Claude Code runner utilities for iterative execution."""

import asyncio
import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class RunStatus(Enum):
    """Status of a Claude Code run."""

    IMPROVED = "improved"  # Made progress but task not complete
    COMPLETED = "completed"  # Task fully finished per spec
    TIMEOUT = "timeout"
    PROCESS_ERROR = "process_error"
    MISSING_MARKER = "missing_marker"


@dataclass
class ClaudeRunResult:
    """Result from a single Claude Code iteration."""

    status: RunStatus
    output_message: str  # From <Improved> or <Completed> marker
    summary: str  # Summary of what was done
    raw_output: str  # Full output for debugging
    return_code: Optional[int] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None


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


def parse_claude_output(raw_output: str) -> tuple[Optional[str], Optional[str], str]:
    """Parse Claude Code JSON output to extract the status marker.

    Args:
        raw_output: The raw JSON output from Claude Code CLI.

    Returns:
        A tuple of (marker_type, output_message, summary) where:
        - marker_type is "improved", "completed", or None if not found
        - output_message is the content from the marker (or None if not found)
        - summary is the output message or a fallback summary

        If both markers are present, <Completed> takes precedence.
    """
    # Try to parse as JSON first
    text_content = ""
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
    except json.JSONDecodeError:
        # If not valid JSON, treat the whole output as text
        text_content = raw_output

    # Look for <Completed> first (takes priority)
    completed_pattern = r"<Completed>(.*?)</Completed>"
    completed_match = re.search(completed_pattern, text_content, re.DOTALL)

    if completed_match:
        output_message = completed_match.group(1).strip()
        return "completed", output_message, output_message

    # Look for <Improved> marker
    improved_pattern = r"<Improved>(.*?)</Improved>"
    improved_match = re.search(improved_pattern, text_content, re.DOTALL)

    if improved_match:
        output_message = improved_match.group(1).strip()
        return "improved", output_message, output_message

    # Fallback: try to extract a summary from the output
    # Look for common patterns that might indicate what was done
    fallback_summary = _extract_fallback_summary(text_content)
    return None, None, fallback_summary


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


async def run_claude_iteration(
    plan_text: str,
    folder_path: str,
    timeout_seconds: float = 300.0,
    model: Optional[str] = None,
) -> ClaudeRunResult:
    """Run a single Claude Code iteration on a folder.

    Args:
        plan_text: The plan/design document text to guide Claude.
        folder_path: The folder path where Claude should work.
        timeout_seconds: Maximum time to wait for completion (default 5 minutes).
        model: Optional model override for Claude Code.

    Returns:
        ClaudeRunResult with status and output information.
    """
    start_time = time.time()

    # Validate folder path
    folder = Path(folder_path)
    if not folder.exists():
        return ClaudeRunResult(
            status=RunStatus.PROCESS_ERROR,
            output_message="",
            summary="",
            raw_output="",
            error_message=f"Folder does not exist: {folder_path}",
            duration_seconds=time.time() - start_time,
        )

    if not folder.is_dir():
        return ClaudeRunResult(
            status=RunStatus.PROCESS_ERROR,
            output_message="",
            summary="",
            raw_output="",
            error_message=f"Path is not a directory: {folder_path}",
            duration_seconds=time.time() - start_time,
        )

    # Build the prompt
    prompt = build_iteration_prompt(plan_text)

    # Build the command
    cmd = ["claude", "-p", "--dangerously-skip-permissions", "--output-format", "json"]
    if model:
        cmd.extend(["--model", model])

    try:
        # Create subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(folder),
        )

        try:
            # Wait for completion with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt.encode("utf-8")),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            # Kill the process on timeout
            process.kill()
            await process.wait()
            return ClaudeRunResult(
                status=RunStatus.TIMEOUT,
                output_message="",
                summary="Process timed out",
                raw_output="",
                error_message=f"Process timed out after {timeout_seconds} seconds",
                duration_seconds=time.time() - start_time,
            )

        duration = time.time() - start_time
        raw_output = stdout.decode("utf-8", errors="replace")
        stderr_output = stderr.decode("utf-8", errors="replace")

        # Check return code
        if process.returncode != 0:
            return ClaudeRunResult(
                status=RunStatus.PROCESS_ERROR,
                output_message="",
                summary="",
                raw_output=raw_output,
                return_code=process.returncode,
                error_message=stderr_output or f"Process exited with code {process.returncode}",
                duration_seconds=duration,
            )

        # Parse the output
        marker_type, output_message, summary = parse_claude_output(raw_output)

        if marker_type is None:
            return ClaudeRunResult(
                status=RunStatus.MISSING_MARKER,
                output_message="",
                summary=summary,
                raw_output=raw_output,
                return_code=process.returncode,
                duration_seconds=duration,
            )

        # Set status based on which marker was found
        status = RunStatus.COMPLETED if marker_type == "completed" else RunStatus.IMPROVED

        return ClaudeRunResult(
            status=status,
            output_message=output_message,
            summary=summary,
            raw_output=raw_output,
            return_code=process.returncode,
            duration_seconds=duration,
        )

    except FileNotFoundError:
        return ClaudeRunResult(
            status=RunStatus.PROCESS_ERROR,
            output_message="",
            summary="",
            raw_output="",
            error_message="Claude CLI not found. Make sure 'claude' is installed and in PATH.",
            duration_seconds=time.time() - start_time,
        )
    except Exception as e:
        return ClaudeRunResult(
            status=RunStatus.PROCESS_ERROR,
            output_message="",
            summary="",
            raw_output="",
            error_message=f"Unexpected error: {e}",
            duration_seconds=time.time() - start_time,
        )
