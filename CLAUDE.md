# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ralph-py-cli is a CLI tool for running Claude Code iteratively. It provides two main commands:

1. **`ralph run`** - Run Claude Code iteratively on a project
   - Specify target folder and a plan (inline or from file)
   - Set maximum number of iterations
   - Execute Claude Code N times in sequence (a "Ralph loop")
   - Interactive prompts between iterations to modify plan or continue
   - Token usage tracking with tier-based rate limit percentages

2. **`ralph plan`** - Improve a plan for optimal iterative execution
   - Restructures plans into small, atomic steps
   - Orders steps by dependencies
   - Makes each step independently completable

The core concept is automating repeated Claude Code runs against a codebase with a design document guiding each iteration.

## Development Setup

```bash
# Install UV and Claude Code CLI
./install.sh

# Run tests
uv run pytest tests/ -v

# Run the CLI
uv run ralph --help
```

## Tech Stack

- **Language:** Python
- **Package Manager:** UV (astral.sh/uv)
- **CLI Framework:** Typer
- **Output Formatting:** Rich

## Project Structure

```
ralph-py-cli/
├── src/ralph_py_cli/
│   ├── cli.py              # Main CLI entry point (typer commands)
│   └── utils/
│       ├── claude_runner.py     # Claude Code subprocess execution
│       ├── interactive.py       # Interactive prompts between iterations
│       ├── ralph_plan_helper.py # Plan improvement logic
│       └── token_usage.py       # Token tracking and tier percentages
├── tests/
│   ├── test_runner_integration.py  # Claude runner tests
│   └── test_token_usage.py         # Token usage tests
├── example_plans/          # Sample plan files
├── pyproject.toml          # Project config and dependencies
└── install.sh              # Setup script
```

## Key Concepts

- **Iteration markers**: Claude Code outputs `<Improved>...</Improved>` when making progress or `<Completed>...</Completed>` when fully done
- **Token tracking**: Tracks input/output tokens per iteration and shows usage against Pro, Max 5x, and Max 20x tier limits
- **Interactive mode**: Between iterations, users can modify the plan, change iteration count, or skip future prompts
