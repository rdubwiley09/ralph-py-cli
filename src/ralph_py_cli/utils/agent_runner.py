"""Unified agent runner for ralph-py-cli."""

import subprocess
import time
from pathlib import Path
from typing import Optional

from ralph_py_cli.utils.agents.base import AgentProtocol, AgentRunResult, RunStatus
from ralph_py_cli.utils.agents.claude import ClaudeAgent
from ralph_py_cli.utils.agents.opencode import OpenCodeAgent


def get_agent(agent_type: str) -> AgentProtocol:
    """Factory function to get agent by type.

    Args:
        agent_type: Type of agent ("claude" or "opencode")

    Returns:
        AgentProtocol instance for the requested agent type

    Raises:
        ValueError: If agent_type is not recognized
    """
    agents = {
        "claude": ClaudeAgent(),
        "opencode": OpenCodeAgent(),
    }

    if agent_type not in agents:
        raise ValueError(f"Unknown agent type: {agent_type}. Available: {list(agents.keys())}")

    return agents[agent_type]


def check_agent_available(agent_type: str) -> tuple[bool, Optional[str]]:
    """Check if agent CLI is available on the system.

    Args:
        agent_type: Type of agent to check

    Returns:
        Tuple of (is_available, error_message)
        - is_available: True if agent CLI is found and working
        - error_message: None if available, error description otherwise
    """
    agent_commands = {
        "claude": "claude",
        "opencode": "opencode",
    }

    cmd = agent_commands.get(agent_type)
    if not cmd:
        return False, f"Unknown agent type: {agent_type}"

    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            timeout=5.0,
        )
        if result.returncode == 0:
            return True, None
        else:
            return False, f"{cmd} CLI returned error code {result.returncode}"
    except FileNotFoundError:
        return False, f"{cmd} CLI not found in PATH. Please install {agent_type}."
    except subprocess.TimeoutExpired:
        return False, f"{cmd} CLI did not respond within 5 seconds"
    except Exception as e:
        return False, f"Error checking {cmd} CLI: {e}"


def run_agent_iteration(
    agent_type: str,
    plan_text: str,
    folder_path: str,
    timeout_seconds: float = 300.0,
    model: Optional[str] = None,
) -> AgentRunResult:
    """Run a single iteration with the specified agent.

    Args:
        agent_type: Type of agent to use ("claude" or "opencode")
        plan_text: The plan/design document text to guide the agent
        folder_path: The folder path where the agent should work
        timeout_seconds: Maximum time to wait for completion (default 5 minutes)
        model: Optional model override

    Returns:
        AgentRunResult with status and output information
    """
    start_time = time.time()

    # Validate folder path
    folder = Path(folder_path)
    if not folder.exists():
        return AgentRunResult(
            status=RunStatus.PROCESS_ERROR,
            output_message="",
            summary="",
            raw_output="",
            error_message=f"Folder does not exist: {folder_path}",
            duration_seconds=time.time() - start_time,
        )

    if not folder.is_dir():
        return AgentRunResult(
            status=RunStatus.PROCESS_ERROR,
            output_message="",
            summary="",
            raw_output="",
            error_message=f"Path is not a directory: {folder_path}",
            duration_seconds=time.time() - start_time,
        )

    try:
        # Get agent instance
        agent = get_agent(agent_type)

        # Build command using agent-specific strategy
        cmd, stdin_input = agent.build_command(plan_text, str(folder), model)

        # Run subprocess with timeout
        result = subprocess.run(
            cmd,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(folder),
        )

        duration = time.time() - start_time
        raw_output = result.stdout
        stderr_output = result.stderr

        # Check return code
        if result.returncode != 0:
            return AgentRunResult(
                status=RunStatus.PROCESS_ERROR,
                output_message="",
                summary="",
                raw_output=raw_output,
                return_code=result.returncode,
                error_message=stderr_output or f"Process exited with code {result.returncode}",
                duration_seconds=duration,
            )

        # Parse the output using agent-specific parser
        marker_type, output_message, summary, token_usage = agent.parse_output(raw_output)

        if marker_type is None:
            # Create a helpful error message showing what the agent actually said
            preview = summary[:200] if summary else "(no output)"
            if len(summary) > 200:
                preview += "..."
            error_msg = f"No <Improved> or <Completed> marker found. Agent output: {preview}"

            return AgentRunResult(
                status=RunStatus.MISSING_MARKER,
                output_message="",
                summary=summary,
                raw_output=raw_output,
                return_code=result.returncode,
                error_message=error_msg,
                duration_seconds=duration,
                token_usage=token_usage,
            )

        # Set status based on which marker was found
        status = RunStatus.COMPLETED if marker_type == "completed" else RunStatus.IMPROVED

        return AgentRunResult(
            status=status,
            output_message=output_message,
            summary=summary,
            raw_output=raw_output,
            return_code=result.returncode,
            duration_seconds=duration,
            token_usage=token_usage,
        )

    except subprocess.TimeoutExpired:
        return AgentRunResult(
            status=RunStatus.TIMEOUT,
            output_message="",
            summary="Process timed out",
            raw_output="",
            error_message=f"Process timed out after {timeout_seconds} seconds",
            duration_seconds=time.time() - start_time,
        )
    except FileNotFoundError:
        agent_name = agent_type.capitalize()
        return AgentRunResult(
            status=RunStatus.PROCESS_ERROR,
            output_message="",
            summary="",
            raw_output="",
            error_message=f"{agent_name} CLI not found. Make sure '{agent_type}' is installed and in PATH.",
            duration_seconds=time.time() - start_time,
        )
    except ValueError as e:
        # Catch unknown agent type errors
        return AgentRunResult(
            status=RunStatus.PROCESS_ERROR,
            output_message="",
            summary="",
            raw_output="",
            error_message=str(e),
            duration_seconds=time.time() - start_time,
        )
    except Exception as e:
        return AgentRunResult(
            status=RunStatus.PROCESS_ERROR,
            output_message="",
            summary="",
            raw_output="",
            error_message=f"Unexpected error: {e}",
            duration_seconds=time.time() - start_time,
        )
