"""CLI for running Claude Code iteratively until completion or error."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ralph_py_cli.utils.claude_runner import (
    RunStatus,
    run_claude_iteration,
)
from ralph_py_cli.utils.ralph_plan_helper import (
    PlanHelperStatus,
    improve_plan_for_iteration,
)

app = typer.Typer(name="ralph", help="Run Claude Code iteratively on a project")
console = Console()


async def run_loop(
    folder: Path,
    plan_text: str,
    iterations: int,
    timeout: float,
    model: Optional[str],
    verbose: bool,
) -> tuple[int, RunStatus, str]:
    """Run the Claude Code iteration loop.

    Args:
        folder: Target folder path.
        plan_text: The plan/design document text.
        iterations: Maximum number of iterations.
        timeout: Timeout per iteration in seconds.
        model: Optional model override.
        verbose: Show detailed output.

    Returns:
        Tuple of (iterations_run, final_status, message).
    """
    for i in range(1, iterations + 1):
        console.print(f"[bold blue]Iteration {i}/{iterations}[/bold blue] - In Progress")

        result = await run_claude_iteration(
            plan_text=plan_text,
            folder_path=str(folder),
            timeout_seconds=timeout,
            model=model,
        )

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
            return i, RunStatus.COMPLETED, message

        if result.status in (RunStatus.TIMEOUT, RunStatus.PROCESS_ERROR, RunStatus.MISSING_MARKER):
            error_detail = result.error_message or result.status.value
            message = f"Stopped at iteration {i} due to: {error_detail}"
            console.print(f"[bold red]{message}[/bold red]")
            return i, result.status, message

        # IMPROVED - continue to next iteration
        console.print(f"[cyan]  Improved:[/cyan] {result.output_message or result.summary}")

    # All iterations exhausted with IMPROVED
    message = f"Ran {iterations} iterations without completing"
    console.print(f"[bold yellow]{message}[/bold yellow]")
    return iterations, RunStatus.IMPROVED, message


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
        help="Optional model override for Claude Code",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output",
    ),
) -> None:
    """Run Claude Code iteratively on a project until completion or error.

    The CLI runs Claude Code in a loop, with each iteration making incremental
    progress on the plan. The loop continues until:
    - The task is completed (exit code 0)
    - An error occurs (exit code 1)
    - Maximum iterations reached without completion (exit code 2)
    """
    try:
        plan_text = resolve_plan_text(plan, plan_file)
    except typer.BadParameter as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    console.print(f"[bold]Running Claude Code on:[/bold] {folder}")
    console.print(f"[bold]Max iterations:[/bold] {iterations}")
    if model:
        console.print(f"[bold]Model:[/bold] {model}")
    console.print()

    iterations_run, status, message = asyncio.run(
        run_loop(folder, plan_text, iterations, timeout, model, verbose)
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
        help="Optional model override for Claude Code",
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

    console.print("[bold]Improving plan for iterative execution...[/bold]")
    if verbose:
        console.print(f"  Timeout: {timeout}s")
        if model:
            console.print(f"  Model: {model}")
    console.print()

    result = asyncio.run(
        improve_plan_for_iteration(
            plan_text=plan_text,
            timeout_seconds=timeout,
            model=model,
        )
    )

    if result.status == PlanHelperStatus.SUCCESS:
        if verbose and result.duration_seconds:
            console.print(f"[dim]Completed in {result.duration_seconds:.1f}s[/dim]")
            console.print()

        if output:
            output.write_text(result.improved_plan)
            console.print(f"[bold green]Improved plan written to:[/bold green] {output}")
        else:
            console.print("[bold green]Improved Plan:[/bold green]")
            console.print()
            console.print(result.improved_plan)

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
