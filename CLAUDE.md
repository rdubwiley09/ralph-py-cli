# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ralph-py-cli is a CLI tool for running Claude Code iteratively. It provides:

1. **Design Document Builder** - Create and edit design documents that specify what Claude Code should build
2. **Ralph Loop Widget** - Configure and run Claude Code iteratively on a project
   - Specify target folder/project
   - Set number of iterations
   - Execute Claude Code N times in sequence (a "Ralph loop")

The core concept is automating repeated Claude Code runs against a codebase with a design document guiding each iteration.

## Development Setup

```bash
# Install UV and Claude Code CLI
./install.sh
```

## Tech Stack

- **Language:** Python
- **Package Manager:** UV (astral.sh/uv)
- **TUI Framework:** Textual (https://textual.textualize.io/)
