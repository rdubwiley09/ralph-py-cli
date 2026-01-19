"""Interactive prompts for loop control between iterations."""

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from ralph_py_cli.utils.token_usage import TokenUsageTracker


class LoopAction(Enum):
    """Actions available during interactive loop control."""

    CONTINUE = "continue"
    EDIT = "edit"
    SKIP_PROMPTS = "skip"
    CANCEL = "cancel"


@dataclass
class LoopState:
    """Mutable state for the iteration loop."""

    plan_text: str
    total_iterations: int
    agent_type: str = "claude"  # Agent to use: "claude" or "opencode"
    current_iteration: int = 0
    skip_prompts: bool = False
    cancelled: bool = False
    token_tracker: TokenUsageTracker = field(default_factory=TokenUsageTracker)


def is_interactive_terminal() -> bool:
    """Check if stdin is connected to an interactive terminal."""
    return sys.stdin.isatty()


def prompt_main_menu() -> LoopAction:
    """Display main menu and prompt user for next action.

    Returns:
        The selected LoopAction.
    """
    print()
    print("What would you like to do next?")
    print("  [1] Continue to next iteration")
    print("  [2] Edit loop settings")
    print("  [3] Skip future prompts (auto-continue)")
    print("  [4] Cancel")
    print()

    while True:
        choice = input("Choice [1-4] (default: 1): ").strip()

        if choice == "" or choice == "1":
            return LoopAction.CONTINUE
        elif choice == "2":
            return LoopAction.EDIT
        elif choice == "3":
            return LoopAction.SKIP_PROMPTS
        elif choice == "4":
            return LoopAction.CANCEL
        else:
            print("Invalid choice. Please enter 1-4.")


def prompt_new_plan_text() -> Optional[str]:
    """Prompt for new plan text via multi-line input.

    Returns:
        The new plan text, or None if empty/cancelled.
    """
    print()
    print("Enter new plan text (press Enter twice to finish, Ctrl+C to cancel):")
    print("-" * 40)

    lines = []
    empty_line_count = 0

    try:
        while True:
            line = input()
            if line == "":
                empty_line_count += 1
                if empty_line_count >= 2:
                    break
                lines.append(line)
            else:
                empty_line_count = 0
                lines.append(line)
    except EOFError:
        pass

    # Remove trailing empty lines
    while lines and lines[-1] == "":
        lines.pop()

    plan_text = "\n".join(lines).strip()

    if not plan_text:
        print("Empty plan text - keeping original plan.")
        return None

    return plan_text


def prompt_plan_file_path() -> Optional[str]:
    """Prompt for a file path to load plan from.

    Returns:
        The plan text from the file, or None if cancelled/invalid.
    """
    print()

    while True:
        path_str = input("Enter plan file path (or empty to cancel): ").strip()

        if not path_str:
            print("Cancelled - keeping original plan.")
            return None

        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            print(f"File does not exist: {path}")
            continue

        if not path.is_file():
            print(f"Not a file: {path}")
            continue

        try:
            plan_text = path.read_text()
            if not plan_text.strip():
                print("File is empty - keeping original plan.")
                return None
            print(f"Loaded plan from: {path}")
            return plan_text
        except Exception as e:
            print(f"Error reading file: {e}")
            continue


def prompt_additional_iterations() -> Optional[int]:
    """Prompt for additional iterations to add.

    Returns:
        The number of additional iterations, or None if cancelled.
    """
    print()

    while True:
        count_str = input("Enter number of additional iterations (or empty to cancel): ").strip()

        if not count_str:
            print("Cancelled - keeping current iteration count.")
            return None

        try:
            count = int(count_str)
            if count <= 0:
                print("Please enter a positive number.")
                continue
            return count
        except ValueError:
            print("Invalid number. Please enter a positive integer.")


def prompt_new_iteration_count(current_remaining: int) -> Optional[int]:
    """Prompt for a new total iteration count.

    Args:
        current_remaining: The current number of remaining iterations.

    Returns:
        The new total iteration count, or None if cancelled.
    """
    print()

    while True:
        count_str = input(
            f"Enter new remaining iteration count (currently {current_remaining}, or empty to cancel): "
        ).strip()

        if not count_str:
            print("Cancelled - keeping current iteration count.")
            return None

        try:
            count = int(count_str)
            if count < 0:
                print("Please enter a non-negative number.")
                continue
            return count
        except ValueError:
            print("Invalid number. Please enter a non-negative integer.")


def prompt_agent_type(current_agent: str) -> Optional[str]:
    """Prompt for agent type selection.

    Args:
        current_agent: The current agent type.

    Returns:
        The selected agent type, or None if cancelled.
    """
    print()
    print(f"Current agent: {current_agent}")
    print("Available agents:")
    print("  [1] claude (Claude Code CLI)")
    print("  [2] opencode (OpenCode CLI)")
    print()

    while True:
        choice = input("Choice [1-2] (or empty to cancel): ").strip()

        if not choice:
            print("Cancelled - keeping current agent.")
            return None
        elif choice == "1":
            return "claude"
        elif choice == "2":
            # Check if opencode is available
            from ralph_py_cli.utils.agent_runner import check_agent_available
            available, error = check_agent_available("opencode")
            if not available:
                print(f"Warning: {error}")
                print("Continue anyway? The next iteration will fail if opencode is not available.")
                confirm = input("Continue? [y/N]: ").strip().lower()
                if confirm != "y":
                    continue
            return "opencode"
        else:
            print("Invalid choice. Please enter 1 or 2.")


def prompt_edit_menu(state: LoopState) -> bool:
    """Display edit menu and allow user to modify loop settings.

    Shows current plan preview and iteration info. Allows multiple edits
    before confirming. Modifies state directly for plan/iteration changes.

    Args:
        state: The current loop state to potentially modify.

    Returns:
        True if changes were confirmed, False if cancelled.
    """
    # Store original values in case user cancels
    original_plan = state.plan_text
    original_iterations = state.total_iterations
    original_agent_type = state.agent_type

    while True:
        # Show current state
        remaining = state.total_iterations - state.current_iteration
        plan_preview = state.plan_text[:100]
        if len(state.plan_text) > 100:
            plan_preview += "..."

        print()
        print("=== Edit Loop Settings ===")
        print(f"Current agent: {state.agent_type}")
        print(f"Current plan: {plan_preview}")
        print(f"Remaining iterations: {remaining}")
        print()
        print("  [1] Change plan (enter text)")
        print("  [2] Change plan (load from file)")
        print("  [3] Change iteration count")
        print("  [4] Change agent type")
        print("  [5] Confirm and continue")
        print("  [6] Cancel (discard changes)")
        print()

        choice = input("Choice [1-6]: ").strip()

        if choice == "1":
            new_plan = prompt_new_plan_text()
            if new_plan:
                state.plan_text = new_plan
                print("Plan updated.")

        elif choice == "2":
            new_plan = prompt_plan_file_path()
            if new_plan:
                state.plan_text = new_plan
                print("Plan updated from file.")

        elif choice == "3":
            remaining = state.total_iterations - state.current_iteration
            new_remaining = prompt_new_iteration_count(remaining)
            if new_remaining is not None:
                state.total_iterations = state.current_iteration + new_remaining
                print(f"Iteration count updated. {new_remaining} iterations remaining.")

        elif choice == "4":
            new_agent = prompt_agent_type(state.agent_type)
            if new_agent:
                state.agent_type = new_agent
                print(f"Agent updated to: {new_agent}")

        elif choice == "5":
            # Confirm and continue
            return True

        elif choice == "6":
            # Cancel - restore original values
            state.plan_text = original_plan
            state.total_iterations = original_iterations
            state.agent_type = original_agent_type
            print("Changes discarded.")
            return False

        else:
            print("Invalid choice. Please enter 1-6.")


def get_user_decision(state: LoopState) -> None:
    """Get user decision and update state accordingly.

    This function handles the interactive prompt and modifies the
    LoopState based on user input.

    Args:
        state: The current loop state to potentially modify.
    """
    try:
        while True:
            action = prompt_main_menu()

            if action == LoopAction.CONTINUE:
                return  # Continue to next iteration

            elif action == LoopAction.CANCEL:
                state.cancelled = True
                return

            elif action == LoopAction.SKIP_PROMPTS:
                state.skip_prompts = True
                print("Future prompts disabled - will auto-continue.")
                return

            elif action == LoopAction.EDIT:
                confirmed = prompt_edit_menu(state)
                if confirmed:
                    return  # Changes confirmed, continue to next iteration
                # If cancelled, loop back to main menu

    except KeyboardInterrupt:
        print("\nCancelled.")
        state.cancelled = True
