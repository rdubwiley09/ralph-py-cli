# ralph-py-cli

## Note: this is a cli that allows one to run claude code in yolo mode for a given number of iterations. Use caution and other best practices when going degen mode.

A CLI tool for running Claude Code iteratively on a project until completion.

## What is a Ralph Loop?

A Ralph loop automates repeated Claude Code runs against a codebase. Instead of running Claude Code once and manually re-running it to continue work, Ralph handles the iteration automatically.

Each iteration:
1. Sends your plan/design document to Claude Code
2. Claude works on the task and reports progress
3. If the task isn't complete, Ralph starts another iteration
4. Continues until the task is done, an error occurs, or max iterations reached

This is useful for larger tasks that require multiple Claude Code sessions to complete.

## Installation

```bash
# Install via pip
pip install ralph-py-cli

# Or install via uv
uv add ralph-py-cli
```

## Available Agents

Ralph supports multiple AI coding agents:

- **claude** (default) - Uses Claude Code CLI for code generation and iteration
- **opencode** - Uses OpenCode CLI as an alternative agent (requires OpenCode to be installed)

Both agents support the same Ralph loop workflow with iterative execution and interactive controls.

### Agent-Specific Notes

**OpenCode:**
- Default model: `opencode/glm-4.7-free` (if no model is specified)
- Requires OpenCode CLI to be installed and available in your PATH
- Use `--model` to specify a different OpenCode model

## CLI Usage

Ralph provides three commands: `run`, `run-endlessly`, and `plan`.

### Running the Loop

```bash
# Run with inline plan
ralph run ./my-project --plan "Build a REST API with user authentication" --iterations 5

# Run with plan from file
ralph run ./my-project --plan-file design.md --iterations 10

# With options
ralph run ./my-project \
  --plan-file design.md \
  --iterations 10 \
  --timeout 600 \
  --model claude-sonnet-4-20250514 \
  --verbose

# Using OpenCode agent (alternative to Claude Code)
ralph run ./my-project \
  --plan-file design.md \
  --iterations 10 \
  --agent opencode

# Using OpenCode with custom model
ralph run ./my-project \
  --plan "Build a REST API" \
  --iterations 5 \
  --agent opencode \
  --model opencode/glm-4.7-free
```

**Options:**
- `--plan, -p` - Plan text describing what to build
- `--plan-file, -f` - Read plan from a file
- `--iterations, -n` - Maximum iterations to run (required)
- `--timeout, -t` - Timeout per iteration in seconds (default: 300)
- `--agent, -a` - Agent to use: `claude` or `opencode` (default: claude)
- `--model, -m` - Model override for the agent
- `--verbose, -v` - Show detailed output
- `--interactive/--no-interactive` - Enable/disable prompts between iterations (default: enabled)

**Exit codes:**
- `0` - Task completed successfully
- `1` - Error occurred (timeout, process error, etc.)
- `2` - Max iterations reached without completion

### Running Endlessly

The `run-endlessly` command runs Claude Code continuously, ignoring completion markers and only stopping on errors or manual cancellation. This is useful for iterative improvement and exploration without predefined endpoints.

```bash
# Run endlessly with manual stop (Ctrl+C)
ralph run-endlessly ./my-project --plan "Continuously improve code quality"

# Run endlessly from plan file
ralph run-endlessly ./my-project --plan-file design.md

# With maximum iteration limit
ralph run-endlessly ./my-project --plan-file design.md --max-iterations 50

# With options
ralph run-endlessly ./my-project \
  --plan-file design.md \
  --max-iterations 100 \
  --timeout 600 \
  --model claude-sonnet-4-20250514 \
  --verbose

# Using OpenCode agent
ralph run-endlessly ./my-project \
  --plan "Continuously improve code" \
  --agent opencode \
  --model opencode/glm-4.7-free
```

**Options:**
- `--plan, -p` - Plan text describing what to build
- `--plan-file, -f` - Read plan from a file
- `--max-iterations, -n` - Maximum iterations (optional, omit for endless)
- `--timeout, -t` - Timeout per iteration in seconds (default: 300)
- `--agent, -a` - Agent to use: `claude` or `opencode` (default: claude)
- `--model, -m` - Model override for the agent
- `--verbose, -v` - Show detailed output

**Key differences from `run`:**
- No interactive prompts between iterations
- Continues through COMPLETED and MISSING_MARKER statuses
- Stops only on:
  - 3 consecutive errors (TIMEOUT or PROCESS_ERROR)
  - Manual cancellation (Ctrl+C)
  - Maximum iterations reached (if --max-iterations specified)

**Exit codes:**
- `1` - Stopped due to consecutive errors
- `2` - Cancelled by user or max iterations reached

### Improving a Plan

The `plan` command restructures your plan into small, atomic steps optimized for iterative execution:

```bash
# Improve a plan from text
ralph plan --plan "Build a web app with login, dashboard, and settings pages"

# Improve a plan from file
ralph plan --plan-file rough-ideas.md

# Save improved plan to file
ralph plan --plan-file rough-ideas.md --output optimized-plan.md
```

**Options:**
- `--plan, -p` - Plan text to improve
- `--plan-file, -f` - Read plan from a file
- `--output, -o` - Write improved plan to file
- `--timeout, -t` - Timeout in seconds (default: 120)
- `--agent, -a` - Agent to use: `claude` or `opencode` (default: claude)
- `--model, -m` - Model override for the agent
- `--verbose, -v` - Show detailed output

## Example Workflow

1. Write a rough plan for what you want to build
2. Use `ralph plan` to optimize it for iterative execution
3. Use `ralph run` to execute the plan iteratively

```bash
# Start with a rough idea
echo "Build a CLI todo app with add, list, and delete commands" > plan.txt

# Optimize for iterative execution
ralph plan --plan-file plan.txt --output optimized-plan.txt

# Run the loop
ralph run ./todo-project --plan-file optimized-plan.txt --iterations 5
```

## Interactive Loop Menu

When running in an interactive terminal, Ralph pauses between iterations to let you control the loop. This gives you the opportunity to review progress and make adjustments.

### Main Menu

After each iteration, you'll see:

```
What would you like to do next?
  [1] Continue to next iteration
  [2] Edit loop settings
  [3] Skip future prompts (auto-continue)
  [4] Cancel
```

- **Continue** - Proceed to the next iteration with current settings
- **Edit** - Open the edit menu to change plan or iterations
- **Skip** - Disable prompts and auto-continue for remaining iterations
- **Cancel** - Stop the loop immediately

### Edit Menu

When you select "Edit loop settings", you can make multiple changes before continuing:

```
=== Edit Loop Settings ===
Current plan: <first 100 chars of plan>...
Remaining iterations: X

  [1] Change plan (enter text)
  [2] Change plan (load from file)
  [3] Change iteration count
  [4] Confirm and continue
  [5] Cancel (discard changes)
```

- **Change plan (text)** - Enter new plan text directly
- **Change plan (file)** - Load plan from a file path
- **Change iteration count** - Set remaining iterations
- **Confirm** - Apply changes and continue to next iteration
- **Cancel** - Discard all changes and return to main menu
