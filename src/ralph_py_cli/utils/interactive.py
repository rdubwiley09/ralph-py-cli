"""Interactive prompts for loop control between iterations."""

import asyncio
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class LoopAction(Enum):
    """Actions available during interactive loop control."""

    CONTINUE = "continue"
    REFRESH_PLAN_TEXT = "refresh_text"
    REFRESH_PLAN_FILE = "refresh_file"
    EXTEND_ITERATIONS = "extend"
    SKIP_PROMPTS = "skip"
    CANCEL = "cancel"


@dataclass
class LoopState:
    """Mutable state for the iteration loop."""

    plan_text: str
    total_iterations: int
    current_iteration: int = 0
    skip_prompts: bool = False
    cancelled: bool = False


def is_interactive_terminal() -> bool:
    """Check if stdin is connected to an interactive terminal."""
    return sys.stdin.isatty()


def prompt_user_action() -> LoopAction:
    """Display menu and prompt user for next action.

    Returns:
        The selected LoopAction.
    """
    print()
    print("What would you like to do next?")
    print("  [1] Continue to next iteration")
    print("  [2] Refresh plan (enter text)")
    print("  [3] Refresh plan (load from file)")
    print("  [4] Extend iterations")
    print("  [5] Skip future prompts (auto-continue)")
    print("  [6] Cancel")
    print()

    while True:
        choice = input("Choice [1-6] (default: 1): ").strip()

        if choice == "" or choice == "1":
            return LoopAction.CONTINUE
        elif choice == "2":
            return LoopAction.REFRESH_PLAN_TEXT
        elif choice == "3":
            return LoopAction.REFRESH_PLAN_FILE
        elif choice == "4":
            return LoopAction.EXTEND_ITERATIONS
        elif choice == "5":
            return LoopAction.SKIP_PROMPTS
        elif choice == "6":
            return LoopAction.CANCEL
        else:
            print("Invalid choice. Please enter 1-6.")


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


def get_user_decision(state: LoopState) -> None:
    """Get user decision and update state accordingly.

    This is a synchronous function that handles the interactive prompt
    and modifies the LoopState based on user input.

    Args:
        state: The current loop state to potentially modify.
    """
    try:
        action = prompt_user_action()

        if action == LoopAction.CONTINUE:
            pass  # Do nothing, continue to next iteration

        elif action == LoopAction.CANCEL:
            state.cancelled = True

        elif action == LoopAction.SKIP_PROMPTS:
            state.skip_prompts = True
            print("Future prompts disabled - will auto-continue.")

        elif action == LoopAction.REFRESH_PLAN_TEXT:
            new_plan = prompt_new_plan_text()
            if new_plan:
                state.plan_text = new_plan
                print("Plan updated.")

        elif action == LoopAction.REFRESH_PLAN_FILE:
            new_plan = prompt_plan_file_path()
            if new_plan:
                state.plan_text = new_plan
                print("Plan updated from file.")

        elif action == LoopAction.EXTEND_ITERATIONS:
            additional = prompt_additional_iterations()
            if additional:
                state.total_iterations += additional
                print(f"Extended to {state.total_iterations} total iterations.")

    except KeyboardInterrupt:
        print("\nCancelled.")
        state.cancelled = True


async def async_get_user_decision(state: LoopState) -> None:
    """Async wrapper for get_user_decision using run_in_executor.

    Args:
        state: The current loop state to potentially modify.
    """
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, get_user_decision, state)
