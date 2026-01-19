"""Plan improvement utilities for optimal iterative execution in the Ralph loop."""

import json
import re
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ralph_py_cli.utils.token_usage import TokenUsage, parse_token_usage


class PlanHelperStatus(Enum):
    """Status of a plan improvement operation."""

    SUCCESS = "success"  # Plan successfully improved
    TIMEOUT = "timeout"  # Claude timed out
    PROCESS_ERROR = "process_error"  # CLI error
    PARSE_ERROR = "parse_error"  # Could not extract improved plan


@dataclass
class PlanHelperResult:
    """Result from plan improvement operation."""

    status: PlanHelperStatus
    improved_plan: str  # The restructured plan
    original_plan: str  # Original for reference/fallback
    raw_output: str  # For debugging
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None
    token_usage: Optional[TokenUsage] = None


def build_plan_improvement_prompt(plan_text: str) -> str:
    """Build the prompt for plan improvement.

    Args:
        plan_text: The original plan text to improve.

    Returns:
        The formatted prompt to send to Claude.
    """
    return f"""You are an expert at restructuring development plans for optimal iterative execution.

Your task is to take the following plan and restructure it to be more suitable for iterative implementation by an AI coding assistant. The restructured plan should follow these principles:

1. **Small, Atomic Steps** - Break down into the smallest independently completable units. Each step should be something that can be fully implemented and tested in a single iteration.

2. **Dependency Ordering** - Prerequisites must come before dependent tasks. If step B requires step A, step A must be listed first.

3. **Verifiable Outcomes** - Each step should have a clear "done" condition. It should be obvious when a step is complete.

4. **Incremental Value** - After completing each step, the codebase should be in a working state. No step should leave the code broken or incomplete.

5. **Clear Scope** - Each step should have unambiguous boundaries. It should be clear exactly what is and isn't included in each step.

Here is the plan to restructure:

<original_plan>
{plan_text}
</original_plan>

Please restructure this plan following the principles above. Output your response in this format:

<reasoning>
Brief explanation of how you restructured the plan and why.
</reasoning>

<improved_plan>
The restructured plan with numbered, atomic steps. Each step should be on its own line and be self-contained.
</improved_plan>

Important:
- Keep the overall goals and requirements from the original plan
- Make each step specific and actionable
- Number each step sequentially (1, 2, 3, etc.)
- Include any setup or prerequisite steps that were implicit in the original
- If the original plan is already well-structured, still format it with numbered steps
"""


def parse_plan_improvement_response(
    raw_output: str,
) -> tuple[Optional[str], Optional[str], Optional[TokenUsage]]:
    """Parse Claude's response to extract the improved plan and token usage.

    Args:
        raw_output: The raw output from Claude (may be JSON).

    Returns:
        A tuple of (improved_plan, reasoning, token_usage) where any may be None if not found.
    """
    # Try to parse as JSON first (Claude CLI JSON output format)
    text_content = ""
    token_usage = None
    try:
        data = json.loads(raw_output)
        if isinstance(data, dict):
            result = data.get("result", "")
            if isinstance(result, str):
                text_content = result
            elif isinstance(result, dict):
                text_content = result.get("text", str(result))

            # Extract token usage from JSON
            token_usage = parse_token_usage(data)
    except json.JSONDecodeError:
        # If not valid JSON, treat the whole output as text
        text_content = raw_output

    # Extract improved_plan
    plan_pattern = r"<improved_plan>(.*?)</improved_plan>"
    plan_match = re.search(plan_pattern, text_content, re.DOTALL)
    improved_plan = plan_match.group(1).strip() if plan_match else None

    # Extract reasoning (optional)
    reasoning_pattern = r"<reasoning>(.*?)</reasoning>"
    reasoning_match = re.search(reasoning_pattern, text_content, re.DOTALL)
    reasoning = reasoning_match.group(1).strip() if reasoning_match else None

    return improved_plan, reasoning, token_usage


def improve_plan_for_iteration(
    plan_text: str,
    timeout_seconds: float = 120.0,
    model: Optional[str] = None,
    agent_type: str = "claude",
) -> PlanHelperResult:
    """Use an agent to improve a plan for optimal iterative execution.

    This function sends the plan to the specified agent for restructuring into small,
    atomic steps that are suitable for iterative implementation in the
    Ralph loop.

    Args:
        plan_text: The plan text to improve.
        timeout_seconds: Maximum time to wait for completion (default 2 minutes).
        model: Optional model override for the agent.
        agent_type: Agent to use: "claude" or "opencode" (default "claude").

    Returns:
        PlanHelperResult with the improved plan or error information.
    """
    start_time = time.time()

    # Build the prompt
    prompt = build_plan_improvement_prompt(plan_text)

    # Build the command based on agent type
    # Note: no --dangerously-skip-permissions since this is read-only
    if agent_type == "claude":
        cmd = ["claude", "-p", "--output-format", "json"]
        if model:
            cmd.extend(["--model", model])
        stdin_input = prompt
    elif agent_type == "opencode":
        cmd = ["opencode", "run", prompt, "--format", "json"]
        if model:
            cmd.extend(["--model", model])
        stdin_input = None
    else:
        return PlanHelperResult(
            status=PlanHelperStatus.PROCESS_ERROR,
            improved_plan="",
            original_plan=plan_text,
            raw_output="",
            error_message=f"Unknown agent type: {agent_type}",
            duration_seconds=0.0,
        )

    try:
        # Run subprocess with timeout
        result = subprocess.run(
            cmd,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        duration = time.time() - start_time
        raw_output = result.stdout
        stderr_output = result.stderr

        # Check return code
        if result.returncode != 0:
            return PlanHelperResult(
                status=PlanHelperStatus.PROCESS_ERROR,
                improved_plan="",
                original_plan=plan_text,
                raw_output=raw_output,
                error_message=stderr_output or f"Process exited with code {result.returncode}",
                duration_seconds=duration,
            )

        # Parse the output
        improved_plan, _reasoning, token_usage = parse_plan_improvement_response(raw_output)

        if improved_plan is None:
            return PlanHelperResult(
                status=PlanHelperStatus.PARSE_ERROR,
                improved_plan="",
                original_plan=plan_text,
                raw_output=raw_output,
                error_message="Could not extract improved plan from response",
                duration_seconds=duration,
                token_usage=token_usage,
            )

        return PlanHelperResult(
            status=PlanHelperStatus.SUCCESS,
            improved_plan=improved_plan,
            original_plan=plan_text,
            raw_output=raw_output,
            duration_seconds=duration,
            token_usage=token_usage,
        )

    except subprocess.TimeoutExpired:
        return PlanHelperResult(
            status=PlanHelperStatus.TIMEOUT,
            improved_plan="",
            original_plan=plan_text,
            raw_output="",
            error_message=f"Process timed out after {timeout_seconds} seconds",
            duration_seconds=time.time() - start_time,
        )
    except FileNotFoundError:
        agent_name = agent_type.capitalize()
        return PlanHelperResult(
            status=PlanHelperStatus.PROCESS_ERROR,
            improved_plan="",
            original_plan=plan_text,
            raw_output="",
            error_message=f"{agent_name} CLI not found. Make sure '{agent_type}' is installed and in PATH.",
            duration_seconds=time.time() - start_time,
        )
    except Exception as e:
        return PlanHelperResult(
            status=PlanHelperStatus.PROCESS_ERROR,
            improved_plan="",
            original_plan=plan_text,
            raw_output="",
            error_message=f"Unexpected error: {e}",
            duration_seconds=time.time() - start_time,
        )
