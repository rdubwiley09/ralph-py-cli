"""CLI for running Claude Code iteratively until completion or error."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ralph_py_cli.utils.agents.base import RunStatus
from ralph_py_cli.utils.agent_runner import check_agent_available, run_agent_iteration
from ralph_py_cli.utils.interactive import (
    LoopState,
    get_user_decision,
    is_interactive_terminal,
)
from ralph_py_cli.utils.ralph_plan_helper import (
    PlanHelperStatus,
    improve_plan_for_iteration,
)
from ralph_py_cli.utils.token_usage import TokenUsageTracker

app = typer.Typer(name="ralph", help="Run Claude Code iteratively on a project")
console = Console()


def run_loop(
    folder: Path,
    state: LoopState,
    timeout: float,
    model: Optional[str],
    verbose: bool,
    interactive: bool = True,
) -> tuple[int, RunStatus, str]:
    """Run the Claude Code iteration loop.

    Args:
        folder: Target folder path.
        state: The mutable loop state containing plan and iteration info.
        timeout: Timeout per iteration in seconds.
        model: Optional model override.
        verbose: Show detailed output.
        interactive: Enable/disable prompts between iterations.

    Returns:
        Tuple of (iterations_run, final_status, message).
    """
    # Check if interactive prompts are possible
    can_prompt = interactive and is_interactive_terminal()

    while state.current_iteration < state.total_iterations:
        state.current_iteration += 1
        i = state.current_iteration

        console.print(
            f"[bold blue]Iteration {i}/{state.total_iterations}[/bold blue] - In Progress"
        )

        result = run_agent_iteration(
            agent_type=state.agent_type,
            plan_text=state.plan_text,
            folder_path=str(folder),
            timeout_seconds=timeout,
            model=model,
        )

        # Track token usage if available
        if result.token_usage:
            state.token_tracker.add_usage(result.token_usage)
            console.print(f"  {result.token_usage.format_compact()}")

        if verbose:
            console.print(f"  Status: {result.status.value}")
            if result.summary:
                console.print(f"  Summary: {result.summary}")
            if result.duration_seconds:
                console.print(f"  Duration: {result.duration_seconds:.1f}s")

        if result.status == RunStatus.COMPLETED:
            message = f"Task completed in {i} iteration{'s' if i > 1 else ''}"
            console.print(f"[bold green]{message}[/bold green]")
            if result.output_message:
                console.print(f"  {result.output_message}")
            _print_session_summary(state.token_tracker)
            return i, RunStatus.COMPLETED, message

        if result.status in (
            RunStatus.TIMEOUT,
            RunStatus.PROCESS_ERROR,
            RunStatus.MISSING_MARKER,
        ):
            error_detail = result.error_message or result.status.value
            message = f"Stopped at iteration {i} due to: {error_detail}"
            console.print(f"[bold red]{message}[/bold red]")
            _print_session_summary(state.token_tracker)
            return i, result.status, message

        # IMPROVED - continue to next iteration
        console.print(
            f"[cyan]  Improved:[/cyan] {result.output_message or result.summary}"
        )

        # Prompt user between iterations if interactive and not skipping
        is_last_iteration = state.current_iteration >= state.total_iterations
        if can_prompt and not state.skip_prompts and not is_last_iteration:
            get_user_decision(state)

            if state.cancelled:
                message = f"Cancelled by user after {i} iteration{'s' if i > 1 else ''}"
                console.print(f"[bold yellow]{message}[/bold yellow]")
                _print_session_summary(state.token_tracker)
                return i, RunStatus.IMPROVED, message

    # All iterations exhausted with IMPROVED
    message = f"Ran {state.total_iterations} iterations without completing"
    console.print(f"[bold yellow]{message}[/bold yellow]")
    _print_session_summary(state.token_tracker)
    return state.total_iterations, RunStatus.IMPROVED, message


def run_endless_loop(
    folder: Path,
    state: LoopState,
    timeout: float,
    model: Optional[str],
    verbose: bool,
    max_iterations: Optional[int] = None,
    max_consecutive_errors: int = 3,
) -> tuple[int, RunStatus, str]:
    """Run the Claude Code iteration loop endlessly until stopped.

    Args:
        folder: Target folder path.
        state: The mutable loop state containing plan and iteration info.
        timeout: Timeout per iteration in seconds.
        model: Optional model override.
        verbose: Show detailed output.
        max_iterations: Optional maximum number of iterations (None for endless).
        max_consecutive_errors: Stop after this many consecutive errors.

    Returns:
        Tuple of (iterations_run, final_status, message).
    """
    consecutive_errors = 0

    try:
        while True:
            state.current_iteration += 1
            i = state.current_iteration

            # Check if max_iterations is reached
            if max_iterations is not None and i > max_iterations:
                message = f"Ran {max_iterations} iteration{'s' if max_iterations > 1 else ''} (max_iterations reached)"
                console.print(f"[bold yellow]{message}[/bold yellow]")
                _print_session_summary(state.token_tracker)
                return i - 1, RunStatus.IMPROVED, message

            console.print(f"[bold blue]Iteration {i}[/bold blue] - In Progress")

            result = run_agent_iteration(
                agent_type=state.agent_type,
                plan_text=state.plan_text,
                folder_path=str(folder),
                timeout_seconds=timeout,
                model=model,
            )

            # Track token usage if available
            if result.token_usage:
                state.token_tracker.add_usage(result.token_usage)
                console.print(f"  {result.token_usage.format_compact()}")

            if verbose:
                console.print(f"  Status: {result.status.value}")
                if result.summary:
                    console.print(f"  Summary: {result.summary}")
                if result.duration_seconds:
                    console.print(f"  Duration: {result.duration_seconds:.1f}s")

            if result.status == RunStatus.COMPLETED:
                # Display message but continue (don't stop)
                console.print(
                    f"  [green]Completed:[/green] {result.output_message or result.summary}"
                )
                consecutive_errors = 0  # Reset error counter
                continue

            if result.status == RunStatus.IMPROVED:
                # Display message and continue
                console.print(
                    f"  [cyan]Improved:[/cyan] {result.output_message or result.summary}"
                )
                consecutive_errors = 0  # Reset error counter
                continue

            if result.status == RunStatus.MISSING_MARKER:
                # Display warning and continue
                console.print(
                    f"  [yellow]Warning:[/yellow] No marker found - output missing required tags"
                )
                consecutive_errors = (
                    0  # Reset error counter (MISSING_MARKER counts as success)
                )
                continue

            if result.status in (RunStatus.TIMEOUT, RunStatus.PROCESS_ERROR):
                # Increment error counter
                consecutive_errors += 1
                error_detail = result.error_message or result.status.value
                console.print(f"  [red]Error:[/red] {error_detail}")

                if consecutive_errors >= max_consecutive_errors:
                    message = f"Stopped at iteration {i} after {consecutive_errors} consecutive errors"
                    console.print(f"[bold red]{message}[/bold red]")
                    _print_session_summary(state.token_tracker)
                    return i, result.status, message

                console.print(
                    f"  [yellow]Consecutive errors: {consecutive_errors}/{max_consecutive_errors}[/yellow]"
                )
                continue

    except KeyboardInterrupt:
        message = f"Cancelled by user after {state.current_iteration} iteration{'s' if state.current_iteration > 1 else ''}"
        console.print()
        console.print(f"[bold yellow]{message}[/bold yellow]")
        _print_session_summary(state.token_tracker)
        return state.current_iteration, RunStatus.IMPROVED, message


def _print_session_summary(tracker: TokenUsageTracker) -> None:
    """Print session summary with token usage and tier percentages.

    Args:
        tracker: The token usage tracker with accumulated data.
    """
    if tracker.total_tokens == 0:
        return

    console.print()
    console.print(tracker.format_summary())
    console.print()
    console.print(tracker.create_tier_table())


def resolve_plan_text(plan: Optional[str], plan_file: Optional[Path]) -> str:
    """Resolve plan text from either --plan or --plan-file option.

    Args:
        plan: Plan text string.
        plan_file: Path to plan file.

    Returns:
        The plan text.

    Raises:
        typer.BadParameter: If neither or both options are provided.
    """
    if plan and plan_file:
        raise typer.BadParameter("Cannot use both --plan and --plan-file")
    if not plan and not plan_file:
        raise typer.BadParameter("Must provide either --plan or --plan-file")

    if plan_file:
        if not plan_file.exists():
            raise typer.BadParameter(f"Plan file does not exist: {plan_file}")
        return plan_file.read_text()

    return plan


@app.command()
def run(
    folder: Path = typer.Argument(
        ...,
        help="Target folder path to run Claude Code on",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    plan: Optional[str] = typer.Option(
        None,
        "--plan",
        "-p",
        help="Plan text string describing what to build",
    ),
    plan_file: Optional[Path] = typer.Option(
        None,
        "--plan-file",
        "-f",
        help="Read plan from file (alternative to --plan)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    iterations: int = typer.Option(
        ...,
        "--iterations",
        "-n",
        help="Maximum number of iterations to run",
        min=1,
    ),
    timeout: float = typer.Option(
        300.0,
        "--timeout",
        "-t",
        help="Timeout per iteration in seconds",
        min=1.0,
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Optional model override for the agent",
    ),
    agent: str = typer.Option(
        "claude",
        "--agent",
        "-a",
        help="Agent to use: claude or opencode",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output",
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        "-i/-I",
        help="Enable/disable prompts between iterations",
    ),
) -> None:
    """Run iteratively on a project until completion or error.

    The CLI runs Claude Code in a loop, with each iteration making incremental
    progress on the plan. The loop continues until:
    - The task is completed (exit code 0)
    - An error occurs (exit code 1)
    - Maximum iterations reached without completion (exit code 2)
    - User cancels via interactive prompt (exit code 2)
    """
    try:
        plan_text = resolve_plan_text(plan, plan_file)
    except typer.BadParameter as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    # Validate agent type
    if agent not in ["claude", "opencode"]:
        console.print(f"[bold red]Error:[/bold red] Unknown agent type: {agent}")
        console.print("[dim]Available agents: claude, opencode[/dim]")
        raise typer.Exit(code=1)

    # Set default model for opencode if not specified
    if agent == "opencode" and model is None:
        model = "opencode/glm-4.7-free"

    # Check agent availability
    available, error = check_agent_available(agent)
    if not available:
        console.print(f"[bold red]Error:[/bold red] {error}")
        console.print(f"[dim]Make sure '{agent}' is installed and in your PATH[/dim]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Running on:[/bold] {folder}")
    console.print(f"[bold]Agent:[/bold] {agent}")
    console.print(f"[bold]Max iterations:[/bold] {iterations}")
    if model:
        console.print(f"[bold]Model:[/bold] {model}")
    if not interactive:
        console.print("[dim]Interactive prompts disabled[/dim]")
    console.print()

    state = LoopState(
        plan_text=plan_text, total_iterations=iterations, agent_type=agent
    )

    iterations_run, status, message = run_loop(
        folder, state, timeout, model, verbose, interactive
    )

    # Exit codes based on status
    if status == RunStatus.COMPLETED:
        raise typer.Exit(code=0)
    elif status == RunStatus.IMPROVED:
        raise typer.Exit(code=2)
    else:
        # TIMEOUT, PROCESS_ERROR, MISSING_MARKER
        raise typer.Exit(code=1)


@app.command()
def run_endlessly(
    folder: Path = typer.Argument(
        ...,
        help="Target folder path to run Claude Code on",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    plan: Optional[str] = typer.Option(
        None,
        "--plan",
        "-p",
        help="Plan text string describing what to build",
    ),
    plan_file: Optional[Path] = typer.Option(
        None,
        "--plan-file",
        "-f",
        help="Read plan from file (alternative to --plan)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    max_iterations: Optional[int] = typer.Option(
        None,
        "--max-iterations",
        "-n",
        help="Maximum number of iterations (omit for endless)",
        min=1,
    ),
    timeout: float = typer.Option(
        300.0,
        "--timeout",
        "-t",
        help="Timeout per iteration in seconds",
        min=1.0,
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Optional model override for the agent",
    ),
    agent: str = typer.Option(
        "claude",
        "--agent",
        "-a",
        help="Agent to use: claude or opencode",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output",
    ),
) -> None:
    """Run endlessly on a project until consecutive errors or manual cancellation.

    The CLI runs Claude Code in a loop continuously, ignoring completion markers
    and only stopping on:
    - 3 consecutive TIMEOUT or PROCESS_ERROR statuses
    - Manual cancellation (Ctrl+C)
    - Maximum iterations reached (if --max-iterations specified)

    Unlike the 'run' command, this continues through COMPLETED and MISSING_MARKER
    statuses, making it suitable for iterative improvement and exploration.
    """
    try:
        plan_text = resolve_plan_text(plan, plan_file)
    except typer.BadParameter as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    # Validate agent type
    if agent not in ["claude", "opencode"]:
        console.print(f"[bold red]Error:[/bold red] Unknown agent type: {agent}")
        console.print("[dim]Available agents: claude, opencode[/dim]")
        raise typer.Exit(code=1)

    # Set default model for opencode if not specified
    if agent == "opencode" and model is None:
        model = "opencode/glm-4.7-free"

    # Check agent availability
    available, error = check_agent_available(agent)
    if not available:
        console.print(f"[bold red]Error:[/bold red] {error}")
        console.print(f"[dim]Make sure '{agent}' is installed and in your PATH[/dim]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Running on:[/bold] {folder}")
    console.print(f"[bold]Agent:[/bold] {agent}")
    if max_iterations is not None:
        console.print(f"[bold]Max iterations:[/bold] {max_iterations}")
    else:
        console.print(f"[bold]Max iterations:[/bold] endless")
    if model:
        console.print(f"[bold]Model:[/bold] {model}")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    console.print()

    # Use a large number for total_iterations if max_iterations is not specified
    total_iterations = max_iterations if max_iterations is not None else 999999
    state = LoopState(
        plan_text=plan_text, total_iterations=total_iterations, agent_type=agent
    )

    iterations_run, status, message = run_endless_loop(
        folder, state, timeout, model, verbose, max_iterations
    )

    # Exit codes based on status
    if status in (RunStatus.TIMEOUT, RunStatus.PROCESS_ERROR):
        raise typer.Exit(code=1)
    else:
        # User cancelled or exhausted iterations
        raise typer.Exit(code=2)


@app.command()
def plan(
    plan: Optional[str] = typer.Option(
        None,
        "--plan",
        "-p",
        help="Plan text string to improve",
    ),
    plan_file: Optional[Path] = typer.Option(
        None,
        "--plan-file",
        "-f",
        help="Read plan from file (alternative to --plan)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write improved plan to file instead of stdout",
    ),
    timeout: float = typer.Option(
        120.0,
        "--timeout",
        "-t",
        help="Timeout in seconds",
        min=1.0,
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Optional model override for the agent",
    ),
    agent: str = typer.Option(
        "claude",
        "--agent",
        "-a",
        help="Agent to use: claude or opencode",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output including reasoning",
    ),
) -> None:
    """Improve a plan for optimal iterative execution.

    Takes a plan and restructures it into small, atomic steps suitable
    for iterative implementation in the Ralph loop.
    """
    try:
        plan_text = resolve_plan_text(plan, plan_file)
    except typer.BadParameter as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    # Validate agent type
    if agent not in ["claude", "opencode"]:
        console.print(f"[bold red]Error:[/bold red] Unknown agent type: {agent}")
        console.print("[dim]Available agents: claude, opencode[/dim]")
        raise typer.Exit(code=1)

    # Set default model for opencode if not specified
    if agent == "opencode" and model is None:
        model = "opencode/glm-4.7-free"

    console.print("[bold]Improving plan for iterative execution...[/bold]")
    console.print(f"[bold]Agent:[/bold] {agent}")
    if verbose:
        console.print(f"  Timeout: {timeout}s")
        if model:
            console.print(f"  Model: {model}")
    console.print()

    result = improve_plan_for_iteration(
        plan_text=plan_text,
        timeout_seconds=timeout,
        model=model,
        agent_type=agent,
    )

    if result.status == PlanHelperStatus.SUCCESS:
        if verbose and result.duration_seconds:
            console.print(f"[dim]Completed in {result.duration_seconds:.1f}s[/dim]")
            console.print()

        if output:
            output.write_text(result.improved_plan)
            console.print(
                f"[bold green]Improved plan written to:[/bold green] {output}"
            )
        else:
            console.print("[bold green]Improved Plan:[/bold green]")
            console.print()
            console.print(result.improved_plan)

        # Display token usage if available
        if result.token_usage:
            console.print()
            console.print(result.token_usage.format_compact())
            # Create a tracker for tier percentages display
            tracker = TokenUsageTracker()
            tracker.add_usage(result.token_usage)
            console.print()
            console.print(tracker.create_tier_table())

        raise typer.Exit(code=0)
    else:
        console.print(f"[bold red]Error:[/bold red] {result.status.value}")
        if result.error_message:
            console.print(f"  {result.error_message}")
        if verbose and result.raw_output:
            console.print()
            console.print("[dim]Raw output:[/dim]")
            console.print(result.raw_output)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
