# Changelog

This file lists the notable changes of every loom version. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and loom uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is set only in `.claude-plugin/plugin.json`.

## [Unreleased]

### Added

- Milestone M9a: new optional `.claude/loom.json` keys (LOOM_SPEC.md §19.1). A project that omits them keeps the behavior of 1.1.0.
  - `docs`, the docs map: the path of each docs role (`vision`, `overview`, `decisions` with a file name pattern, `conventions`, `tasks`). A project can keep its own documentation structure.
  - `ci.requiredCheck`: the CI check that runs `checks.check` (default `check`).
  - `pullRequest.requiredSections`: headings that the project's PR template or a CI check requires, e.g. `## Test plan`.
  - `checks.lint`, `checks.typecheck`, and `checks.test` may be `null` when the project has no such check.
- `loom-state --json` validates these keys, reports invalid values in `warnings`, and outputs the resolved `docs`, `checks`, `ci`, and `pullRequest` in every output, also without a task.
- `finish-task` also reads the classic branch protection of the main branch (read-only `gh api` GET). It skips the ruleset offer when a ruleset or the protection already requires the check.
- Glossary terms **docs role** and **docs map**.

### Changed

- Skills take every doc path from `docs` in the state and never build one from `docsDir`: `setup` writes the docs skeleton by docs role; `backlog`, `design`, `plan`, `describe-pr` (and its templates), and `_shared/pr-update.md` read and write the mapped paths. `describe-pr` numbers ADRs by `docs.decisions.pattern`.
- `implement` and `iterate` pass the resolved check commands and `docs.conventions` in the implementer prompt, and `docs.conventions` in the reviewer prompt. The implementer no longer reads `.claude/loom.json`; it skips a `null` check and never invents a command for it.
- The ruleset that `finish-task` offers requires `ci.requiredCheck` instead of a fixed `check`.
- `describe-pr` keeps the required PR sections after Decisions (oneshot: after Verification). `_shared/pr-update.md` keeps them, and its check for the PR layout before v1.1 ignores them.
- `workingTreeDocsOnly` and the `Stop` hook count a change as a docs change when it is below `docsDir` or at or below any path of the docs map. The `Stop` hook does nothing when `checks.lint` is `null`; the output filtering hook skips `null` checks.
- An empty `checks.lint`, `checks.typecheck`, or `checks.test` still turns the check off, now with a warning to use `null`. An empty or other invalid `checks.check`, and any other invalid check value, takes its default with a warning.
- Eval case `describe-pr-quick`: the fixture maps `docs.tasks` to `notes/loom-tasks` and requires `## Test plan`; two new graders check the mapped task summary and the required section.

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
