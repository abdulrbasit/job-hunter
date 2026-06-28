---
name: commit
description: Commit workflow for Job Hunter development, including preflight tests, schema validation, linting, safe staging, and intentional commit messages.
when_to_use: "Developer context only - use when preparing, reviewing, or creating a git commit for Job Hunter repo changes."
user-invocable: true
allowed-tools: Bash Read Grep
author: "Abdul Basit (@abdulrbasit)"
category: dev
---

# Dev Commit

Use this skill when preparing a developer commit in this repo.

## Goal

Create a clean, intentional commit after verifying that code, tests, configs, and staged files are safe.

## Workflow

1. Inspect the worktree.
   - Run `git status --short`.
   - Review unstaged and staged diffs for the files you changed.
   - Do not revert user changes.

2. Run preflight checks.
   - Tests: `uv run pytest tests/ -q --tb=short`
   - Format check: `uv run ruff format --check job_hunter tests`
   - Lint: `uv run ruff check job_hunter tests`
   - Type check: `uv run ty check job_hunter tests`
   - If formatting fails, run `uv run ruff format job_hunter tests` then rerun format check. Do not hand-format.
   - If `pyproject.toml` changed, run `uv sync --extra dev` first.
   - Treat failed tests, lint, or type errors as blockers unless the user explicitly accepts the risk.

3. Stage only specific files.
   - Never use `git add .` or `git add -A`.
   - Stage files by explicit path.
   - Include only files related to the requested change.

4. Check staged files.
   - Run `git diff --cached --stat`.
   - Run `git diff --cached --name-only`.
   - Confirm no private outputs, generated PDFs, resumes, cover letters, secrets, or unrelated state files are staged.
   - Context or skill files may be staged only when the user explicitly requested workflow or agent-behavior changes.

5. Prepare the commit.
   - Propose a concise commit message, 72 characters or fewer.
   - **Never include `Co-authored-by` or any AI attribution trailer.** This repo does not use co-author tags regardless of tool defaults.
   - For version bump commits, the message must be exactly `release: v{VERSION}` (e.g. `release: v0.14`). The release workflow checks for this exact format.
   - Ask for confirmation before committing.

6. Commit after confirmation.
   - Run `git commit -m "<message>"`.
   - Show the commit hash and final `git status --short`.

## Output Contract

Keep output compact:

- Preflight status.
- Staged file list or stat.
- Commit message.
- Any blockers or warnings.
