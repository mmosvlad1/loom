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
- Milestone M9b: onboarding of a repository with code (LOOM_SPEC.md §9.13). `/loom:setup` now takes one of two paths.
  - **Fast setup** (an empty or new repository, or `/loom:setup --oneshot`): the `oneshot` setup task, as before.
  - **Onboarding** (a repository with code): a setup task in `full` mode, the *onboarding task*. `setup` does only the kickoff: the issue, the branch `chore/<n>-loom-setup`, the ticket, a minimal `.claude/loom.json`, the kickoff settings of `.claude/settings.json`, the kickoff commit `chore(loom): start loom setup (#<n>)`, and a fixed list of 7 research questions.
  - `research` answers the fixed questions. It reads GitHub facts and local git facts, runs each candidate check command once (exit status, run time), and records which instruction files Claude Code loads.
  - `design` discusses the project with the user: drafts of vision and overview, project rules against loom rules, docs roles (map, migrate, or create), gaps, the check command, the required CI check, the PR sections, the agent instruction files, and the status line.
  - `plan` copies the small loom templates into its Changes. `implement` writes the full `.claude/loom.json` first in implementation phase 1. `describe-pr` proposes every `Follow-up:` line of the design as an issue.
  - The setup PR closes only the gaps that loom needs; every other gap becomes a follow-up issue.
- `loom-state --setup-path <main>` chooses the setup path (`switch`, `rerun`, `fast`, `onboarding`, `onboarding-rerun`, `fast-resume`) and prints it as JSON with its reason.
- `task.setup` in the state. The slug `loom-setup` is reserved for the setup task. For a setup task, `next` routes to `/loom:setup` while the setup run is not finished, and never to `/loom:research-questions`; `research-questions` stops on a setup task. `iterate` refuses a mode change on a setup task, and `finish-task` takes the setup task from `task.setup`.
- With `AGENTS.md` (or `.claude/AGENTS.md`) and no `CLAUDE.md`, the new `CLAUDE.md` imports it with the line `@AGENTS.md` (or `@.claude/AGENTS.md`): once a `CLAUDE.md` exists, Claude Code no longer loads `AGENTS.md` by itself.
- `implement` and `iterate` read the state again after an implementation phase changed `.claude/loom.json`, so the checks, the reviewer prompt, and the later phases use the new values.
- Settings files stay out of the implementer's hands: in auto permission mode Claude Code denies a subagent's edit of `.claude/settings.json`. `implement` applies a settings change of the plan itself before the phase, after it showed the `diff` and got one confirmation; `iterate` does the same before it fixes a blocked phase without a commit. A fix of a settings file never goes to the implementer.
- The CI item of the PR body: `describe-pr` writes a checklist item about the CI result as `` - [ ] CI check `<ci.requiredCheck>` passes on this PR ``, and `finish-task` ticks it before the merge when the check passed. `_shared/pr-update.md` writes it unticked again when it rewrites the body. `loom-state --pr` reports `pr.bodyInSync`, so the tick never overwrites a body that was edited on GitHub.
- Glossary terms **setup task** and **onboarding task**.
- Eval case `design-onboarding`: `/loom:design` on the onboarding task (6 cases in all).
- On the fast path, `setup` checks that a reused CI workflow runs `checks.check`.
- `loom-state` outputs `workDir`, `rounds`, `implement`, and `hooks` with validation, so skills no longer read `.claude/loom.json`. Unknown top-level keys in `loom.json` get a warning.
- `loom-state --pr` reports `pr.requiredCheck`, the state of the check named `ci.requiredCheck`, and routes on it; other failing checks are a warning.
- `loom-state` reports `rebaseInProgress`, keeps the task during a stopped rebase of the task branch, and routes to `/loom:iterate rebase`.
- `implementation.planParseError` in the state: `true` when the Phase Overview of `04-plan.md` cannot be read reliably.
- Warnings for overlapping docs map roles, docs paths at or below `workDir`, and `checks.*` commands that pipe into an output filter.
- `iterate` continues or aborts a stopped rebase (`rebaseInProgress`) before anything else, and repairs an invalid ticket mode at any time, also after implementation started. `implement`, `describe-pr`, and `finish-task` stop during a stopped rebase with `Next: /loom:iterate rebase`.
- `finish-task` without required checks on GitHub (no ruleset or branch protection): it waits for all checks, then enforces `ci.requiredCheck` by name through `pr.requiredCheck`, and refuses the merge while that check fails. Only when no check of that name ran does it still ask for "yes, merge without required checks".
- `next` shows the state of the required check in its PR line.
- The setup allowlist adds the read-only `gh run list`, `gh pr list`, `gh label list`, and `gh repo view`.
- loom's CI runs `make test` on Python 3.9 too (`actions/setup-python@v7.1.0`), in the one job `check`, on a pinned `ubuntu-24.04` runner (no Python 3.9 build exists for Ubuntu 26.04).
- The SessionStart hook also runs for forked sessions (`fork` matcher). On the main branch and on a branch without a task, it also prints the `loom-state` warnings.
- Milestone M10a: an optional style guide and screens (mockup files) in the repository, read by the existing skills (LOOM_SPEC.md §9.14). A project without them sees no change.
  - Two optional docs roles: `style` (default `docs/design/DESIGN.md`) and `screens` (default `docs/design/screens`, one file per screen ID). `setup` writes no skeleton for them.
  - The `loom.json` key `design.canvas`: `null`, or the URL of a Claude Design canvas.
  - `loom-state --json` outputs `design`: `canvas`, `style` (the style guide exists), and `screens` (the sorted screen paths). Two files with one screen ID get a warning.
  - A custom `docs.tasks` or `docs.decisions.dir` at or above `docs/design` now gets an overlap warning with the default `docs.screens` or `docs.style`.
  - The issue format has an optional `## Screens` section. `backlog` writes it, and attaches every screen that no issue names to an issue (`gh issue edit`, with confirmation). `start-task` warns about a screen path that is not in `design.screens`.
  - `design` reads the screens of the ticket, maps them to components, and asks about missing states and conflicts with the style guide. `plan` names the screens in its Changes and adds one `Manual:` line per screen. `iterate` keeps these rules in later rounds.
  - The implementer builds UI from the screens with the project's components and tokens; the reviewer checks tokens, UI states, and unplanned changes to the design files. Both get the `Style guide:` and `Screens:` lines in their prompt.
  - `describe-pr` lists the screens under Verification and proposes a `Design screens: update <screen ID>` follow-up for each screen that the code differs from.
  - Glossary terms **style guide**, **screen**, and **screen ID**.
- `research-questions` and `research` never open a screen: the codebase agents take an `Excluded path:` line, never read a file below it, and exclude it in every search or listing from a parent directory (Grep `glob: "!<path>/**"`, `git ls-files ':(exclude)<path>'`, `find -not -path '*<path>/*'`). The two skills follow the same rule in their own calls, and `iterate` passes the line too.
- Eval cases `research-full` and `design-full`: the fixture has a style guide, one HTML screen, and a `## Screens` section in the ticket. New graders check that research never touches the screen and that design reads it and names its path.

### Changed

- `loom-state --pr` adds no warning when the branch has no PR and the ticket has no valid `pr:`: that is the normal state before `describe-pr`.
- Skills take every doc path from `docs` in the state and never build one from `docsDir`: `setup` writes the docs skeleton by docs role; `backlog`, `design`, `plan`, `describe-pr` (and its templates), and `_shared/pr-update.md` read and write the mapped paths. `describe-pr` numbers ADRs by `docs.decisions.pattern`.
- `implement` and `iterate` pass the resolved check commands and `docs.conventions` in the implementer prompt, and `docs.conventions` in the reviewer prompt. The implementer no longer reads `.claude/loom.json`; it skips a `null` check and never invents a command for it.
- The ruleset that `finish-task` offers requires `ci.requiredCheck` instead of a fixed `check`.
- `describe-pr` keeps the required PR sections after Decisions (oneshot: after Verification). `_shared/pr-update.md` keeps them, and its check for the PR layout before v1.1 ignores them.
- `workingTreeDocsOnly` and the `Stop` hook count a change as a docs change when it is below `docsDir` or at or below any path of the docs map. The `Stop` hook does nothing when `checks.lint` is `null`; the output filtering hook skips `null` checks.
- An empty `checks.lint`, `checks.typecheck`, or `checks.test` still turns the check off, now with a warning to use `null`. An empty or other invalid `checks.check`, and any other invalid check value, takes its default with a warning.
- Eval case `describe-pr-quick`: the fixture maps `docs.tasks` to `notes/loom-tasks` and requires `## Test plan`; two new graders check the mapped task summary and the required section.
- `/loom:implement` is never the next step before the plan gate holds (oneshot, or `04-plan.md` approved): a dirty working tree or a phase in progress before that falls through to the question, approval, and missing-phase routes, with a warning that names the uncommitted changes.
- An invalid ticket mode routes to `/loom:iterate mode <oneshot|quick|full>` before every route except the main branch, a missing or archived task, and a stopped rebase. The mode ignores case and surrounding whitespace.
- A ticket `pr:` without `--pr` routes to `/loom:implement` while implementation phases are left.
- Artifact `status` ignores case and whitespace; an unknown status (also `blocked`) is a warning and counts as `in-review`. The file name decides an artifact's phase.
- `--line` shows only the mode's phases and skips the stale research check and the docs-only `git status`.
- Skills, shared snippets, and agents take `mainBranch`, `workDir`, `rounds.cap`, `implement.*`, and `hooks.*` from the state, never from `.claude/loom.json` (`setup` only while the file does not exist). The reviewer gets the main branch as a `Main branch:` line in its prompt, with a `loom-state` fallback. A lint in `tests/test_skills.py` checks every skill, reference, shared snippet, and agent.
- `finish-task` runs on the session's model (`model: inherit`, no `effort`) instead of `haiku` with `effort: low`.
- `implement`, `iterate`, and `plan` test `implementation.planParseError` instead of searching the warnings for `04-plan.md`.
- `implement`, `describe-pr`, and `finish-task` stop when `git status` failed (`workingTree` is `null`). `iterate` stops too, whatever the argument is, before every section that reads or changes the working tree or commits; answers, approval, a mode change, and feedback on an artifact before implementation started still run.
- `/loom:finish-task #<n>` on a main branch without `.claude/loom.json` (a setup PR merged before the pull) runs `git pull --ff-only` and reads the state again. `setup` names that pull when it finds the setup PR merged.
- `research-questions`, `research`, `design`, `plan`, and `iterate` give every codebase agent the line `Work directory: <workDir>`; the agents skip that directory (`.loom/` without the line).
- `finish-task` watches a pending required check at most 3 times, then stops.
- `start-task` and `finish-task` update the main branch with `git pull --ff-only`.
- The `Next:` line of the final message names the next command itself, not `/loom:next`:
  - A phase command (`/loom:research-questions`, `/loom:research`, `/loom:design`, `/loom:plan`, `/loom:implement`), `/loom:describe-pr`, and `/loom:finish-task` are written as `/clear, then <command>`, e.g. `Next: /clear, then /loom:design`. A phase that you invoke by its own command runs with the `model` and `effort` of its skill.
  - `/loom:start-task …`, `/loom:backlog`, and `/loom:setup` are written as they are.
  - With manual verification steps: `run the manual steps, then /clear, then /loom:implement`. After the last implementation phase the command is `/loom:describe-pr`, or `/loom:finish-task` with an open PR.
  - `/loom:next` stays only where a step of yours comes first and changes the state: a git error to fix, changes to commit or stash, a settings file to change and commit, and an open setup PR. It also stays for a session without the `Next:` line of the last message.
- The final message has one `Warning:` line for each warning of the `loom-state` output that gives the next command. A phase that you invoke by its own command shows the same `loom-state` warnings as `/loom:next`, except the warnings about the PR state.
- The research warnings name the command that clears them: `Warning: research not reviewed; approve it with /loom:iterate approve research`, and in `research`, `Warning: research questions not reviewed; approve them with /loom:iterate approve research-questions`. The note in `loom-state`'s `next.reason` is `research not reviewed (/loom:iterate approve research)`.
- `iterate`: a post-PR fix on a branch behind the main branch rebases first, then collects the fix items, and pushes once at the end.
- `setup` keeps an existing CI workflow without a job named `check`: it writes the check name of the job that runs the checks into `ci.requiredCheck` and never renames a job. For a stack without a recipe it proposes only the checks the project has; a missing one is `null`, and `CLAUDE.md` leaves out its line.
- The main-branch guard reads commands with its own bash parser. It also catches commits and pushes inside `$( … )` (also in double quotes), backticks, process substitutions, here-docs, here-strings, or `echo … |` fed to a shell. It also catches them behind wrappers such as `timeout`, `nice`, `xargs`, and `env`, through `GIT_DIR`/`GIT_WORK_TREE`, and through aliases set with `git -c alias.<name>=…`.
- The guard is conservative when it cannot resolve a command. An unresolvable `cd`, `git -C`, or `GIT_DIR` target means the original cwd. An unresolvable branch means the real current branch. An unreadable alias counts as commit and push. A `cd` inside a subshell no longer leaks. The right side of `||` is checked as if the left side failed.
- The guard follows `git switch -`, `@{-1}`, `git checkout <branch> --`, `git symbolic-ref HEAD`, `git branch -m`, and `switch -c`/`checkout -b` of an existing branch, which git refuses.
- Here-doc delimiters such as `<<'END-MSG'` and `$'…'` strings are parsed. The fallback for unparsable commands is linear in the text. It now also denies, from any branch, a push that names the main branch.
- On the main branch, `git push` is allowed when it cannot update the main branch: tags, other branches, deletions of other branches, `--dry-run`. A push without a refspec, `HEAD`, `--all`, and `--mirror` stay blocked, with a new reason text. A dry run is allowed from any branch.
- The output filtering hook allows a command that is exactly a configured check, also when it has a filter. Filter stages and setup steps (`npm ci`) inside a configured check are no longer check commands.
- The output filtering hook also blocks `rg` and `wc`, checks inside `( … )`, `{ …; }`, and `bash -c`, `pnpm`/`yarn`/`bun` test runs, and checks behind `timeout`.
- The output filtering hook allows `--version`, `--help`, `make -n`, `pytest --collect-only`, and `command -v`.
- The `Stop` lint hook does nothing in plan mode and while background tasks are in flight.
- The `SubagentStop` checks hook still enforces the checks when its attempt counter cannot be read or written: it blocks once, then lets the implementer stop with a message. A `.claude/loom.json` that cannot be read no longer blocks the implementer; the user gets a message instead. Config warnings are added to the failure text.
- Subagent events classify near-miss report wording: `Verdict: pass.`, `Changes needed`, `` `make check`: passed ``, `### Checks:`.
- `gh issue edit` asks for confirmation: the setup allowlist adds the ask rule `Bash(gh issue edit *)`.

### Fixed

- `.claude/loom.json` with a UTF-8 byte order mark is read.
- `mainBranch`, `workDir`, and `docsDir` are trimmed and validated; reserved directories compare ignoring case; `.md` in any case is accepted; `null` objects and control characters get a warning.
- A failed `git status` never routes to `/loom:describe-pr` or `/loom:finish-task`.
- `pr: #57` in the ticket parses; a non-numeric, zero, or negative `pr` gets a warning instead of a crash or a silent `null`.
- Implementation phase 0 is not ignored.
- `loom-state` prints UTF-8 under any locale and survives non-object `gh` output, lone surrogates in `loom.json`, and non-finite `duration_s` values.
- One open question is no longer "1 open questions", in `loom-state` and in the skills' stop messages.
- LOOM_SPEC.md: a project-enabled loom still needs `claude plugin install loom@loom --scope project` once per clone (§19.3); plain review comments do not change the PR route (§6.2); artifacts have no `blocked` status (§9.12).
- `_shared/git-flow.md` names the right readers of the `Phase N:` commit body: `loom-state` takes the phase commit from `log.md`.
- Main-branch guard bypasses through common command forms, such as `cd "$(git rev-parse --show-toplevel)" && git commit`, `git switch -`, `echo "$(git commit …)"`, `timeout 30 git commit`, and `git -c alias.x=commit x`.
- A false positive of the guard on `git switch main && git pull && git switch - && git push`.
- `git push --repo=origin main` and the matching refspec `git push origin :` were not recognized as pushes to the main branch.
- A configured check with a pipe (`go test ./... | grep -v …`) could not run as configured.
- The status line script stopped at a malformed `installed_plugins.json` instead of trying the marketplace and the cache.

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
