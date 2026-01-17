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
# Install dependencies (requires UV)
./install.sh
```

## CLI Usage

Ralph provides two commands: `run` and `plan`.

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
```

**Options:**
- `--plan, -p` - Plan text describing what to build
- `--plan-file, -f` - Read plan from a file
- `--iterations, -n` - Maximum iterations to run (required)
- `--timeout, -t` - Timeout per iteration in seconds (default: 300)
- `--model, -m` - Model override for Claude Code
- `--verbose, -v` - Show detailed output

**Exit codes:**
- `0` - Task completed successfully
- `1` - Error occurred (timeout, process error, etc.)
- `2` - Max iterations reached without completion

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
- `--model, -m` - Model override for Claude Code
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
