# Changelog

This file lists the notable changes of every loom version. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and loom uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is set only in `.claude-plugin/plugin.json`.

## [1.1.0] - 2026-11-11

### Added

- Subagent events: a `SubagentStart` and `SubagentStop` hook (`scripts/hooks/subagent_events.py`) records every run of a loom agent in `<task dir>/events.jsonl`, with the agent, the task phase, the result, and the duration (LOOM_SPEC.md §11.6).
- `loom-state --json` reports `task.metrics`: subagent runs per phase, review rounds, checks retries, subagent time, and a one-line text.
- `describe-pr` adds a `Process metrics:` line to the task summary when `task.metrics` exists. `_shared/pr-update.md` refreshes it when it updates the summary.
- `skills/_shared/bash-calls.md`: one command per Bash call, with no `cd`, no chaining, and no pipe, redirection, or shell variable. Every skill reads it. The agents with Bash carry the rule inline.
- `iterate` reads inline PR review comments on code lines with a read-only `gh api` GET. The permission system asks for it once.
- Eval case `describe-pr-quick` checks the PR body layout. The `research-full` and `implement-manual` cases also check `events.jsonl`.
- `CHANGELOG.md`.

### Changed

- New PR body layout: `Closes`, Why (one sentence), Special things to note (1–3 items, or None.), Change outline (one line per implementation phase, then a file tree or an interface `diff`), Verification, Decisions, and the attached plan. oneshot PRs keep `Closes`, Why, and Verification. `_shared/pr-update.md` keeps this layout and rewrites an older body into it.
- `describe-pr` stops when the task has a PR but `gh` cannot read its state. Other `gh` warnings no longer stop it before the PR exists.
- The Evals workflow runs every case on a pinned `macos-26` runner. On Linux the eval sandbox breaks every Bash call (LOOM_SPEC.md §24.2).
- `plugin.json` version: `0.1.0` → `1.1.0`.

## [1.0.0] - 2026-11-10

First complete version, built in milestones M1–M6. It was never tagged, and `plugin.json` kept the version `0.1.0`.

### Added

- M1: `bin/loom-state` computes the task state and the next step. Hooks inject the task context at session start, block commits and pushes on the main branch, and block filtered check output.
- M2: six agents (`codebase-locator`, `codebase-analyzer`, `codebase-pattern-finder`, `web-search-researcher`, `implementer`, `implementation-reviewer`) and the shared skill snippets.
- M3: `research-questions`, `research`, `design`, `plan`, and `iterate`, with question rounds and approval gates.
- M4: `implement`, `describe-pr`, `finish-task`, and `next`. A `SubagentStop` hook enforces the checks for the implementer. An optional `Stop` hook runs lint.
- M5: `setup` (python-uv and node recipes, CI, settings, docs skeleton, optional statusline), `backlog`, and `start-task`.
- M6: the eval suite (`evals/`, `make eval`) with model-free graders, and loom's own CI (`make check`).
