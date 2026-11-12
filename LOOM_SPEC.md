# loom — Specification

> A Claude Code plugin for structured, agent-driven development: **Research → Plan → Implement**, with GitHub Issues as the backlog, artifacts as the hand-off between phases, and a full git flow from issue to squash merge.

Status: **Draft, revision 2** · Last updated: 2026-11-12 · Describes plugin release **1.1.0**, the unreleased milestone M9a, and the unreleased hardening after M9a (`CHANGELOG.md`)

Changes in revision 2: fixes from the spec review (finish-task commands, agent `tools`, namespacing, versioning, config use, hook exit codes, oneshot conditions), decisions on the post-PR flow, setup bootstrap, approval gates, mode changes and resume, and new features: `loom-state`, `/loom:next`, enforced checks, harness evals, shared snippets, writing style.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Core Principles](#2-core-principles)
3. [Glossary](#3-glossary)
4. [Architecture](#4-architecture)
5. [Workflow Modes](#5-workflow-modes)
6. [End-to-End Lifecycle](#6-end-to-end-lifecycle)
7. [Sessions and Context Model](#7-sessions-and-context-model)
8. [The State Script: `loom-state`](#8-the-state-script-loom-state)
9. [Skills Reference](#9-skills-reference)
10. [Subagents](#10-subagents)
11. [Hooks](#11-hooks)
12. [Question Rounds Protocol](#12-question-rounds-protocol)
13. [Artifacts](#13-artifacts)
14. [Writing Style](#14-writing-style)
15. [Project Documentation Structure](#15-project-documentation-structure)
16. [Git Conventions](#16-git-conventions)
17. [Checks and CI](#17-checks-and-ci)
18. [Stack Detection](#18-stack-detection)
19. [Configuration](#19-configuration)
20. [Testing the Harness](#20-testing-the-harness)
21. [Distribution and Development](#21-distribution-and-development)
22. [Differences from HumanLayer](#22-differences-from-humanlayer)
23. [Roadmap and Out of Scope](#23-roadmap-and-out-of-scope)
24. [Open Topics and Items to Verify](#24-open-topics-and-items-to-verify)

---

## 1. Overview

### 1.1 What loom is

loom is a Claude Code plugin that turns a GitHub issue into a merged pull request through a sequence of explicit phases. Each phase runs in its own session and produces a markdown artifact. The next phase reads only those artifacts. The human stays in control at defined checkpoints: design approval, plan approval, manual verification, push, and merge.

### 1.2 Origin

loom is derived from HumanLayer's Research-Plan-Implement plugin (`humanlayer/humanlayer`, `apps/riptide-rpi-claude-plugin`, Apache-2.0). That plugin depends on HumanLayer's daemon and cloud for subagent registration, `{SKILLBASE}` substitution, artifact sync, and ticket integrations. loom keeps the methodology and the best prompt rules and makes everything self-contained in one plugin. It needs no external services beyond `git` and `gh`.

License: loom is Apache-2.0. It keeps HumanLayer's `LICENSE` and adds a `NOTICE` entry for derived prompts.

### 1.3 Goals

- **Portable:** install once from a marketplace; per project only a small config file.
- **Stack-agnostic:** only `setup` knows about stacks; everything else reads `.claude/loom.json`.
- **Few interruptions:** batched question rounds, approval only where it matters, auto-advance through implementation phases.
- **Reliable:** checks are enforced by hooks, not by trust in the agent.
- **Visible process:** decisions, ADRs, and task summaries are committed; the plan is attached to the PR.
- **Self-contained:** no daemon, no cloud, no Linear/Jira.
- **Tested:** the harness has its own eval suite.

### 1.4 Language

- All prompts (skills, agents, templates, shared snippets) are in **English**.
- All artifacts (research, design, plan, docs, ADRs, PRs, commits) are in **English**.
- Conversation with the user may be in any language.

---

## 2. Core Principles

1. **Research describes, never prescribes.** Research documents only what exists today: where, how, and how components interact. No recommendations, critique, or proposals.
2. **Research is blind to intent (full mode).** Research questions must not leak what will be built ("how does X work", never "how should we build Y"). In full mode the research phase reads the questions, not the ticket.
3. **The human resolves design questions.** The agent may recommend an option. It never closes a design question itself, except under the round cap rule (§12.5) and when the user repeats `approve` (`/loom:iterate approve approve`, §9.8), which takes the recommendations of the open questions.
4. **Vertical slices.** A plan is split into phases that each cut across layers and end in something that can be run, queried, or tested.
5. **Artifacts are the only hand-off.** Each phase starts in a fresh session and reads the previous artifacts.
6. **Later phases win.** When artifacts disagree, the artifact of the later phase controls (order: ticket → research-questions → research → design → plan). For current behavior, the code is the source of truth.
7. **Read inputs fully.** Skills read referenced artifacts in full, in the main context, before they spawn subagents.
8. **Prefer automated verification.** A manual check is listed only when it cannot reasonably be automated.
9. **State is computed, not remembered.** The task state comes from `loom-state` (§8), never from the model's memory of the conversation.

---

## 3. Glossary

Prompts and artifacts use these terms with exactly one meaning each (see §14).

| Term | Meaning |
|---|---|
| **task** | One GitHub issue being worked on, with one branch and one task directory |
| **task directory** | `.loom/tasks/<n>-<slug>/` |
| **mode** | `oneshot`, `quick`, or `full` (§5) |
| **phase** | One workflow step that produces one artifact: research-questions, research, design, plan, implement |
| **implementation phase** | One vertical slice inside the plan |
| **artifact** | A markdown file a phase writes into the task directory |
| **round** | One batch of open questions in design or plan (§12) |
| **approve** | Set an artifact's status to `approved` |
| **gate** | A phase that cannot start until a previous artifact is `approved` |
| **checks** | The commands in `loom.json` → `checks` |
| **docs role** | One kind of durable document that loom reads or writes: `vision`, `overview`, `decisions`, `conventions`, `tasks` (§15) |
| **docs map** | `loom.json` → `docs`: the path of each docs role (§19.1) |

---

## 4. Architecture

### 4.1 Plugin repository layout

```
loom/
├── .claude-plugin/
│   ├── plugin.json                 # the only place with "version"
│   └── marketplace.json
├── skills/
│   ├── _shared/                    # snippets read by several skills
│   │   ├── frontmatter.md          # artifact frontmatter and status rules
│   │   ├── question-rounds.md      # §12
│   │   ├── visual-conventions.md   # trees, diff blocks
│   │   ├── writing-style.md        # §14
│   │   ├── git-flow.md             # §16: commit format, checks, rebase, push, confirmations
│   │   ├── implementation-loop.md  # implementer → checks → reviewer → fix attempts (implement, iterate)
│   │   ├── pr-update.md            # docs refresh, PR body, push after commits on an open PR (iterate, implement)
│   │   ├── bash-calls.md           # one command per Bash call: no cd, no chaining (every skill)
│   │   └── final-answer.md         # format of every skill's last message
│   ├── setup/
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── stacks/python-uv.md
│   │       ├── stacks/node.md
│   │       └── templates/          # loom.json, Makefile, ci.*.yml, settings.json, loom-statusline.py,
│   │                               # CLAUDE.md, docs/*, setup-issue.md
│   ├── backlog/      (SKILL.md, references/issue-format.md — also read by describe-pr)
│   ├── start-task/   (SKILL.md, references/ticket-template.md)
│   ├── research-questions/  (SKILL.md, references/template.md)
│   ├── research/     (SKILL.md, references/template.md)
│   ├── design/       (SKILL.md, references/template.md)
│   ├── plan/         (SKILL.md, references/template.md)
│   ├── iterate/      (SKILL.md)
│   ├── implement/    (SKILL.md, references/log-format.md — also read by iterate and describe-pr)
│   ├── describe-pr/  (SKILL.md, references/summary-template.md, adr-template.md, pr-template.md)
│   ├── finish-task/  (SKILL.md)
│   └── next/         (SKILL.md)
├── agents/
│   ├── codebase-locator.md
│   ├── codebase-analyzer.md
│   ├── codebase-pattern-finder.md
│   ├── web-search-researcher.md
│   ├── implementer.md
│   └── implementation-reviewer.md
├── bin/
│   └── loom-state                  # §8; on the Bash tool's PATH while the plugin is enabled
├── hooks/
│   └── hooks.json
├── scripts/
│   └── hooks/
│       ├── loomhook.py             # shared helpers: hook input, shell parsing, loads bin/loom-state
│       ├── session_start.py        # §11.1
│       ├── guard_main.py           # §11.2
│       ├── block_output_filtering.py  # §11.3
│       ├── subagent_checks.py      # §11.4 (milestone M4)
│       ├── stop_lint.py            # §11.5 (milestone M4)
│       └── subagent_events.py      # §11.6 (v1.1)
├── evals/                          # §20.2: one directory per case, _fixture/, results/ (ignored)
├── tests/                          # unit tests for loom-state, hook scripts, skills, evals (stdlib unittest)
├── .github/workflows/              # ci.yml (make check), eval.yml (make eval on macOS, on demand)
├── Makefile                        # test, validate, check, eval
├── CHANGELOG.md                    # release notes per version (§21)
├── LICENSE
├── NOTICE
└── README.md
```

- Only skills that produce an artifact have a `template.md`.
- Skills address their own files relative to the skill directory, and shared files through `${CLAUDE_PLUGIN_ROOT}/skills/_shared/…` (no `{SKILLBASE}` placeholder).
- `skills/`, `agents/`, `hooks/hooks.json`, and `bin/` at the plugin root are discovered automatically; `plugin.json` needs no paths for them.
- `bin/` executables are on the Bash tool's `PATH` while the plugin is enabled. This is not documented for hooks, so hooks and skill injections reference it by its full path, `"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state` (the Python hooks import that file).
- Hook scripts and `loom-state` are Python 3.9+ with the standard library only (the stock macOS `python3`).

### 4.2 Project-side footprint

```
<project>/
├── CLAUDE.md                     # committed, short
├── Makefile                      # committed (or stack-native equivalent)
├── .github/workflows/ci.yml      # committed
├── .claude/
│   ├── loom.json                 # committed — loom config
│   └── settings.json             # committed — marketplace, enabled plugin, permissions, statusline
├── docs/                         # committed — durable knowledge (§15)
└── .loom/                        # gitignored — working area
    └── tasks/
        ├── 42-auth-flow/
        └── _archive/
```

### 4.3 Two zones

| Zone | Git | Purpose | Lifetime |
|---|---|---|---|
| `.loom/` | ignored | Working artifacts: ticket copy, research, design, plan, log; subagent events (§11.6) | Until the task is finished, then archived locally |
| `docs/` | committed | Durable knowledge: vision, architecture, ADRs, task summaries | Permanent |

`describe-pr` distills durable knowledge from `.loom/` into `docs/` before the PR is opened. Limitation: `.loom/` belongs to one checkout. It does not travel between machines or worktrees.

---

## 5. Workflow Modes

### 5.1 Modes

| Mode | For | Phases |
|---|---|---|
| **oneshot** | Trivial, obvious changes: typo, dependency bump, config tweak, tiny fix | start-task → implement → describe-pr → finish-task |
| **quick** | Small/medium changes with a clear design | start-task → research → plan → implement → describe-pr → finish-task |
| **full** | Larger features, unclear behavior or code shape | start-task → research-questions → research → design → plan → implement → describe-pr → finish-task |

### 5.2 Choosing a mode

1. `start-task --oneshot | --quick | --full` forces a mode.
2. Otherwise the issue label `mode:*` sets it.
3. Otherwise `start-task` proposes one from `size:*` (`S` → oneshot, `M` → quick, `L` → full) and the user confirms.

The mode is stored in `00-ticket.md` frontmatter.

### 5.3 Changing the mode

A mode change is allowed **only before `implement` starts**. After that, a different scope becomes a new issue.

Exception: an invalid mode (`00-ticket.md` has a `mode` that is not `oneshot`, `quick`, or `full`) can be repaired at any time, also after implementation started. `loom-state` routes it to `/loom:iterate mode <oneshot|quick|full>` (§9.12 row 2b). The user names the mode; `iterate` sets the `mode:` line and renames no artifact. `oneshot` is refused while `04-plan.md` exists.

| Change | Effect |
|---|---|
| oneshot → quick | Adds research and plan |
| oneshot → full / quick → full | Existing `02-research.md` is renamed `02-research.superseded.md`, because it read the ticket. An existing `04-plan.md` is renamed `04-plan.superseded.md`, because it builds on that research and has no design. Research is redone blind: research-questions first, then a new research. |
| full → quick | Remaining phases skip design; existing artifacts stay valid |
| any → oneshot | Allowed only if no plan exists |

**Planned (M9, §9.13.1):** `setup` fixes the mode of the setup task (`oneshot` on an empty repository, `full` on a repository with code). `iterate` refuses a mode change on it.

### 5.4 Mode differences

| | oneshot | quick | full |
|---|---|---|---|
| Research questions | — | — | ✓ |
| Research reads the ticket | — | ✓ (accepted bias) | ✗ (reads questions only) |
| Design | — | — | ✓ (gate) |
| Plan | — | ✓ (gate) | ✓ (gate) |
| Implementation phases | 1, built from the ticket | from plan | from plan |
| `log.md` | ✓ | ✓ | ✓ |
| Task summary in `docs/tasks/` | — | ✓ | ✓ |
| ADRs | — | if a decision qualifies | if a decision qualifies |
| Docs commit in describe-pr | only if `overview.md` changed | ✓ | ✓ |
| PR description | short | full | full |

---

## 6. End-to-End Lifecycle

### 6.1 Main path

```
/loom:backlog          discuss ideas → create GitHub issues (labels: type, size, mode)
        │
/loom:start-task #42   git switch main && git pull --ff-only
        │              git switch -c feat/42-auth-flow
        │              .loom/tasks/42-auth-flow/00-ticket.md
        │
   ── /clear → /loom:next ──   runs the next phase for the mode:
        │
        ├─ research-questions  (full)   → 01-research-questions.md
        ├─ research                     → 02-research.md
        ├─ design              (full)   → 03-design.md   rounds via /loom:iterate, then approve
        ├─ plan                         → 04-plan.md     round via /loom:iterate, then approve
        └─ implement           per implementation phase:
                               implementer → checks (enforced) → reviewer → commit → log.md
                               auto-advance unless manual verification is needed
        │
/loom:describe-pr      docs/tasks/42-auth-flow.md, ADRs, overview.md update
        │              commit: docs(#42): record decisions and summary
        │              git rebase origin/main
        │              git push + gh pr create     (confirmation)
        │
   CI (GitHub Actions) make check
        │
/loom:finish-task      branch up to date? CI green? → gh pr merge --squash --delete-branch --subject '<PR title>'   (confirmation)
                       git switch main && git pull --ff-only && git fetch --prune
                       move task directory → .loom/tasks/_archive/
```

### 6.2 After the PR is open

`/loom:next` reads the PR state and routes:

| PR state | Route |
|---|---|
| Implementation phases left (a plan change after the PR; plan approved, or oneshot) | `/loom:implement`, before every other route below; after its last phase it refreshes the docs and pushes (confirmation) |
| Checks failing (the required check `ci.requiredCheck` when the PR reports it, else any check) | `/loom:iterate` → reads failed check logs (`gh run view --log-failed`), fixes |
| Changes requested (`reviewDecision` is `CHANGES_REQUESTED`) | `/loom:iterate` → reads comments (`gh pr view --comments`) and inline review comments on code lines (`gh api --paginate repos/{owner}/{repo}/pulls/<number>/comments`, a read-only GET that the permission system asks for), fixes |
| Branch behind `main` | `/loom:iterate rebase` → `git rebase origin/main`, re-runs checks |
| Checks pending (the required check when the PR reports it, else any check) | Wait; `/loom:finish-task` watches checks |
| Checks green (the required check when the PR reports it, else all checks), no requested changes | `/loom:finish-task` |

When the PR reports a check named `ci.requiredCheck` (`pr.requiredCheck` is not `missing`, §8.2), that check decides failing, pending, and green; other failing checks only add a warning (`PR #<n> has failing checks besides the required check '<name>': <names>`). Without it, the overall checks decide. Requested changes and a branch behind `main` route as above in both cases.

`loom-state` sees only the review decision `CHANGES_REQUESTED`. Plain review comments (a comment review, or a PR comment) do not change the route: with green checks it is `/loom:finish-task`. To fix them, the user runs `/loom:iterate` and names the comments; `iterate` then reads them as above.

The post-PR fix path in `iterate`: fix → checks → commit → refresh `docs/tasks/<n>-<slug>.md` and the PR body if affected → push (confirmation; `--force-with-lease` after a rebase). A branch behind `main` is rebased first, without the rebase's own push: after the rebase and its checks, `iterate` collects the fix items and pushes once, at the end.

---

## 7. Sessions and Context Model

### 7.1 One phase, one session

Each phase starts in a fresh session (`/clear` between phases). A long session fills with search results, test output, and old drafts, and quality drops. Artifacts carry everything the next phase needs.

The normal loop between phases is two commands: `/clear`, then `/loom:next`.

### 7.2 How a fresh session knows the task

The `SessionStart` hook (§11.1) runs `loom-state` and injects the task directory, mode, artifact statuses, and the next step. It fires on `startup`, `resume`, `clear`, and `compact`.

### 7.3 Exceptions

- **Question rounds** (design, plan) stay in one session. Answering and regenerating rounds needs continuity.
- **implement** may run as one session. Each implementation phase runs in a fresh `implementer` subagent; the main session only orchestrates.

### 7.4 Phase endings

Every skill ends with the format from `_shared/final-answer.md`: artifact path, status, open questions count, and the next step, e.g.:

```
Next: /clear, then /loom:next
```

Claude Code cannot clear its own context, so the user runs `/clear`.

### 7.5 Skills and forked context

`research`, `design`, `plan`, and `implement` must **not** use `context: fork`: a forked skill runs as a subagent, and subagents cannot spawn the research and implementer agents these skills depend on.

---

## 8. The State Script: `loom-state`

### 8.1 Purpose

One deterministic script computes the task state. Every component that needs "where is the task and what comes next" uses it: the `SessionStart` hook, `/loom:next`, every phase skill's header, and the statusline. No other component re-implements this logic.

### 8.2 Interface

`${CLAUDE_PLUGIN_ROOT}/bin/loom-state [--json | --line] [--pr] [--docs]`
`${CLAUDE_PLUGIN_ROOT}/bin/loom-state --slug '<issue title>'`

The script is a silent no-op (exit 0, no output) outside a git repository and in a repository without `.claude/loom.json`.

`--json` (default) output:

```json
{
  "today": "2026-11-08",
  "branch": "feat/42-auth-flow",
  "rebaseInProgress": false,
  "mainBranch": "main",
  "onMain": false,
  "workDir": ".loom/tasks",
  "docs": { "dir": "docs", "vision": "docs/product/vision.md", "overview": "docs/architecture/overview.md",
            "decisions": { "dir": "docs/architecture/decisions", "pattern": "<NNNN>-<slug>.md" },
            "conventions": "docs/conventions.md", "tasks": "docs/tasks" },
  "checks": { "lint": "make lint", "typecheck": "make typecheck", "test": "make test", "check": "make check" },
  "ci": { "requiredCheck": "check" },
  "pullRequest": { "requiredSections": [] },
  "rounds": { "cap": { "S": 2, "M": 3, "L": 5 } },
  "implement": { "maxFixAttempts": 2, "autoAdvance": true },
  "hooks": { "stopLint": false, "maxCheckAttempts": 3 },
  "task": { "number": 42, "slug": "auth-flow", "dir": ".loom/tasks/42-auth-flow", "mode": "full",
            "size": "L", "archived": false, "url": "https://github.com/o/r/issues/42", "pr": null,
            "metrics": null },
  "artifacts": [
    { "file": "02-research.md", "phase": "research", "status": "in-review", "openQuestions": 0, "stale": false },
    { "file": "03-design.md", "phase": "design", "status": "in-review", "openQuestions": 3, "acceptedByDefault": 0 }
  ],
  "implementation": { "total": 3, "done": 1, "inProgress": null, "blocked": null,
                      "phases": [ { "number": 1, "status": "done", "commit": "d4e5f6" } ],
                      "planParseError": false },
  "workingTree": "clean",
  "workingTreeDocsOnly": false,
  "pr": null,
  "next": { "command": "/loom:iterate <answers>", "reason": "design has 3 open questions" },
  "warnings": []
}
```

- `workingTreeDocsOnly` is `true` when the tree is `dirty` only in the **docs paths** (besides the ignored `workDir` and `.loom/`), else `false`: an interrupted `describe-pr` writes docs before its commit. The docs paths are `docsDir` and every path of `docs`; a change counts when it is at or below one of them. The `Stop` hook (§11.5) ignores the same paths.
- `docs`: the resolved docs map (§15, §19.1). Paths are relative to the git top level. `dir` is `docsDir`. Skills read doc paths from here and never build them. The freshness check of `--docs` (§23.1) will use the same paths.
- `checks`: the resolved check commands `lint`, `typecheck`, `test`, and `check` (§19.1). A `null` check does not exist in the project. Skills take the check commands from here, and pass them to the implementer (§9.9).
- `ci` and `pullRequest`: the resolved values of these `loom.json` keys (§19.1). Skills read them from here, not from `loom.json`. `pullRequest` (configuration) is not `pr` (the PR state of `--pr`).
- `workDir`, `rounds`, `implement`, and `hooks`: the resolved values of these `loom.json` keys (§19.1). `workDir` is normalized (`./work/tasks/` → `work/tasks`); every `rounds`, `implement`, and `hooks` field is present, with its default when missing or invalid. Skills read them from here, not from `loom.json`. The hooks use the same validated values.
- `workDir`, `docs`, `checks`, `ci`, `pullRequest`, `rounds`, `implement`, `hooks`, and `rebaseInProgress` are in every non-empty output, also without a task (`backlog` reads `docs` on the main branch, `finish-task` reads `ci` after the merge).
- `rebaseInProgress` is `true` while a `git rebase` is stopped (HEAD is detached, and `rebase-merge/head-name` or `rebase-apply/head-name` in the worktree's git directory names a branch). `branch` is then the branch being rebased, the task lookup uses it, a warning is added, and `next` is `/loom:iterate rebase`. A detached HEAD without a rebase gives `branch: null` and `rebaseInProgress: false`.
- `today` is the local date (`YYYY-MM-DD`). Skills use it for `updated` instead of injecting a `date` command (§9.0).
- `task` is `null` when the branch matches no task directory. `task.mode` is `oneshot`, `quick`, or `full`, read ignoring case and surrounding whitespace (`Quick` → `quick`); another value is reported as written, with a warning. `task.pr` is the ticket's `pr` (`57` or `#57`); another value, also `0` or a negative number, adds a warning and gives `null`. `artifacts` lists only existing files of 01–04 (the ticket is reported through `task`; `*.superseded.md` files are ignored). An artifact's `phase` is its file name's phase; a different frontmatter `phase` adds a warning. `status` is `draft`, `in-review`, `approved`, or `null` (missing), read ignoring case and surrounding whitespace; any other value adds a warning and is reported and routed as `in-review`, so no route reruns the phase over the artifact.
- `implementation.blocked` is `null` or `{ "phase": N, "reason": "…" }`. Phase status is `pending`, `in-progress`, `done`, or `blocked`. Phase number 0 is a phase like any other. `implementation.planParseError` is `true` only when `04-plan.md` exists and its Phase Overview cannot be read reliably: no Phase Overview checkboxes, or an unclosed code fence in the plan. Otherwise it is `false`, also without a plan and in oneshot. Skills test this key instead of matching warnings that name `04-plan.md`.
- `task.size` is `S`, `M`, `L`, or `null`, from the ticket frontmatter.
- `task.metrics` is `null`, or the process metrics of `<task dir>/events.jsonl` (§11.6) when the file has at least one valid line:
  ```json
  { "runs": 9, "byPhase": { "research": 4, "implement": 5 }, "reviewRounds": 2, "changesNeeded": 1,
    "checkRetries": 1, "unfinished": 0, "subagentSeconds": 842.5,
    "line": "9 subagent runs (research 4, implement 5), 2 review rounds (1 changes-needed), 1 checks retry, subagent time 14 min" }
  ```
  - A run is one `session_id` and `agent_id` pair; a `null` `session_id` is an ordinary value. A run has one or more segments: each `start` line opens a segment (also when Claude Code resumes the subagent), and the `stop` lines after it close it. Its agent and phase come from its first `start` line (else its first `stop` line).
  - `byPhase` counts runs per phase, in lifecycle order; a run without a phase counts as `unknown`.
  - `reviewRounds` counts the `stop` lines of `implementation-reviewer` with `stop_hook_active` not `true`: each is one verdict, so a resumed reviewer that gives a second verdict counts twice. `changesNeeded` counts those with the result `changes-needed`.
  - `checkRetries` counts the `stop` lines with `stop_hook_active` `true`: a stop hook (normally the checks of §11.4) kept the subagent running.
  - `unfinished` counts runs whose last line is a `start` line (interrupted, or still running).
  - `subagentSeconds` sums, over all segments, the `duration_s` of the segment's last `stop` line. Parallel runs add up, and idle time between segments does not count; it is not wall-clock time.
  - `line` is the text for the task summary (§13.4). Parts with a count of 0 are left out (review rounds, changes-needed, checks retries, unfinished). The time is in rounded seconds below 60 seconds, else in rounded minutes.
  - Malformed lines are skipped. The `--line` output does not change.
- `warnings` collects problems that did not stop the computation: unreadable `loom.json`; an unknown top-level key; invalid `mainBranch`, `workDir`, `docsDir`, `docs`, `checks`, `ci`, `pullRequest`, `rounds`, `implement`, or `hooks` values (§19.1); overlapping docs map roles and docs paths at or below `workDir`; a `checks.*` command that pipes into an output filter; missing or unknown status; a frontmatter `phase` that differs from the file name; invalid mode, size, or `pr`; unclosed code fence; failed stale check; failed `git status`; a stopped rebase; uncommitted changes or a phase in progress before the plan gate holds (§9.12 row 5); `gh` errors; failing PR checks besides `ci.requiredCheck`.
- `--line`: one line for the statusline, e.g. `#42 · full · design:in-review · 3 open Q`, `#42 · full · impl 1/3`, or `#42 · archived`. Empty output when there is no task. Before implementation starts it shows the latest artifact of the mode's phases (after a change from full to quick, a leftover `03-design.md` does not show). It skips the stale research check and the docs-only `git status`, which the line does not use. The output is UTF-8 under any locale.
- `--pr`: adds PR state from `gh pr view --json number,state,reviewDecision,statusCheckRollup,mergeStateStatus` as `{ number, state, reviewDecision, checks: passing|failing|pending|none, requiredCheck: passing|failing|pending|missing, mergeStateStatus, behindMain }`; `behindMain` is computed with git after `git fetch origin <mainBranch>`. `requiredCheck` is the state of the `statusCheckRollup` entry named `ci.requiredCheck` (the `name` of a check run, the `context` of a status). For a repeated name, the latest `startedAt` wins, then the later entry. `missing` means no entry has that name. This calls `gh` and the network, so it is not used by the `SessionStart` hook. If `gh` is missing or unauthenticated, the branch has no PR, or `gh` returns no JSON object, `pr` is `null` and a warning is added.
- `--docs`: reserved for the docs freshness check (§23.1, planned for v1.2). Until then it prints "not implemented yet (planned for v1.2)" to stderr and exits 2.
- **Planned (M9, §9.13):** `task.setup`: `true` when the task is the setup task (branch `chore/<n>-loom-setup`), else `false`.
- `--slug '<issue title>'`: prints the branch slug of §9.3 step 5 and exits 0. It is a pure string function, so it also works outside a loom project. A title that starts with `-` is taken as the title, not as an option. Before the ASCII step it transliterates the letters that Unicode NFKD keeps (`ß` → `ss`, `æ` → `ae`, `œ` → `oe`, `ø` → `o`, `đ` → `d`, `ł` → `l`, `þ` → `th`). One quirk is accepted: a first word that fits and a second word that would pass 40 characters leave only the first word (`a <50-character word>` → `a`). `start-task` uses it, so the slug never depends on the model.

### 8.3 Rules

- **Task lookup:** branch `^(feat|fix|chore|docs|refactor)/(\d+)-(.+)$` → issue number → task directory `<workDir>/<n>-*` (matched by number, so an edited issue title does not break it). If not found, it also looks in `<workDir>/_archive/` and reports `archived: true`. During a stopped rebase (detached HEAD), the branch named by `rebase-merge/head-name` or `rebase-apply/head-name` is used; the paths come from `git rev-parse --git-path`, so linked worktrees work. The mode comes from `00-ticket.md` frontmatter, ignoring case and surrounding whitespace.
- **Config:** reads `.claude/loom.json` at the git top-level (a UTF-8 byte order mark is accepted); missing keys take the defaults of §19.1. An invalid value of a key in the §19.1 validation table takes its default and adds a warning. An unknown top-level key adds a warning and is ignored. The hooks use the same resolved values.
- **Statuses:** read from artifact frontmatter (a minimal parser for the §13.1 fields: scalars and inline lists; a value that starts with `#` and a digit, such as `pr: #57`, is a value, not a comment). Case and surrounding whitespace do not matter; an unknown status counts as `in-review` with a warning. An artifact's phase is its file name.
- **Open questions:** numbered `**Q<n>.` items under the latest `## Open Questions` heading; items marked "accepted by default" are counted separately (`acceptedByDefault`).
- **Code fences:** lines inside fenced code blocks are ignored. Fences follow CommonMark (3+ backticks or tildes; closed only by the same character, at least as long, with nothing after it), except that any indentation is accepted. An unclosed fence adds a warning.
- **Implementation progress:** read from plan Phase Overview checkboxes and `log.md` headings (§13.2); a `log.md` entry wins over the checkbox of the same phase. oneshot has one implicit phase, tracked only through `log.md`.
- **Working tree:** `clean`, `dirty`, or `null` when `git status` fails or times out (with a warning); files under `workDir` are ignored. With `null`, `next` is never `/loom:describe-pr` or `/loom:finish-task` (§9.12).
- **Stale research:** `true` when files referenced in `02-research.md` (as `path:line` or `path`) changed on `main` between the research `git_commit` and `merge-base(HEAD, origin/main)`. The task's own commits do not count. Without `origin/<mainBranch>` the local main branch is used. If the check cannot run, `stale` is `false` and a warning is added.
- **Next step:** computed by the decision table in §9.12.

### 8.4 Implementation

A single Python script, `bin/loom-state`, with no dependencies outside the standard library (Python 3.9+, the stock macOS `python3`), with unit tests in `tests/`. The decision table is a pure function (`decide_next(state)`) that is tested with plain state dicts. The task phase of §11.6 (`task_phase()`) and the process metrics (`events_metrics()`) are pure functions too. Hook scripts import the same file instead of re-implementing its logic.

---

## 9. Skills Reference

### 9.0 Common rules

- All skills set `disable-model-invocation: true`. They run only when invoked as `/loom:<skill>`.
- Phase skills start by injecting state: `` !`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json` `` (verified: `` !`cmd` `` injects command output, and `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_SKILL_DIR}` are substituted when the skill loads).
- Every injected command needs a matching `allowed-tools` rule, or the skill aborts outside auto mode (§24.2). Phase skills set `allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)` (`iterate`, `implement`, `describe-pr`, `finish-task`, and `next`: the injected command is `… --json --pr`; `finish-task` also allows the bare `Bash(loom-state --json --pr)`, which step 3 runs). Only the injection line uses the full path; every Bash call in a skill body uses the bare `loom-state --json` (`bin/` is on the Bash `PATH`), which matches the §19.3 allowlist. `setup`, `backlog`, and `start-task` inject `--json`; `start-task` also allows `Bash(loom-state --slug *)`. The `Read` rule lets the skill read its shared snippets and templates, which lie outside the project's working directory. The grant lasts one turn, so skills read these files before they ask the user anything. Skills inject nothing else; the date comes from `loom-state` → `today`.
- Skills spawn agents by their namespaced name: `loom:codebase-locator`, etc.
- Every Bash call runs one command. A permission rule such as `Bash(git *)` (§19.3) matches one command, so a chained call prompts the user, and an eval run in `dontAsk` mode denies it (§24.2). Every skill reads these rules in `_shared/bash-calls.md`:
  - no `cd`: the working directory is the git top level;
  - no chaining with `&&`, `||`, `;`, or newlines;
  - no pipe, redirection, subshell, or shell variable;
  - tools by the names the skill uses (`loom-state --json`, not `python3 bin/loom-state`);
  - Read, Grep, and Glob instead of `cat`, `ls`, `grep`, or `find` through Bash.

  Exception: a command that a skill gives, and a check command (`checks.*`) as configured, run exactly as written, also when they chain commands or have a pipe. The output filtering hook allows a command that equals a configured check, also with a filter (§11.3). The agents with Bash do not read `_shared`. They carry the rules on `cd`, chaining, pipes, and subshells inline (§10.1). Their own command allowlists replace the last two (the locator may use `ls` and `find`).
- Model and effort per skill (values to tune), set as the skill frontmatter fields `model` and `effort` (verified, §24.2). `default` means the `effort` field is omitted, so the session's effort level applies:

| Skill | Model | Effort |
|---|---|---|
| design, plan | inherit | high |
| research-questions, research, implement, iterate, describe-pr, backlog | inherit | default |
| setup, start-task | inherit | default |
| next, finish-task | inherit | default |

`finish-task` runs the least reversible action (the merge) and reads rulesets, branch protection, and check states, so it keeps the session's model too. `next` runs a phase skill in its own turn (§9.12), so it keeps the session's model and effort: a phase run through `next` uses the session's effort, not the phase's `effort` field. For `effort: high` on design or plan, invoke `/loom:design` or `/loom:plan` directly.

### 9.1 `setup`

**Purpose:** prepare a project for loom. Safe to re-run.

**Planned (M9, §9.13.1):** setup takes one of two paths. An empty or new repository keeps the fast `oneshot` setup of this section. A repository with code gets a `full`-mode setup task instead: setup does only the kickoff (issue, branch, ticket, minimal `loom.json`, kickoff commit, fixed research questions), and loom's own phases do the rest. Path selection:
- On the main branch: the re-run rules below when `origin/<main>` has `.claude/loom.json`; otherwise the path by the repository's files. The plan names the path, and the user can switch it; `/loom:setup --oneshot` forces the fast path.
- On an existing setup branch: onboarding when `00-ticket.md` has `mode: full`, or, without a ticket (a fresh clone), when `origin/<main>..HEAD` has the kickoff commit `chore(loom): start loom setup (#<n>)`. Otherwise the resume of this section.

**Does:**
1. Detects the stack (§18) and existing commands.
2. Bootstraps through loom's own flow, because the guard blocks commits on `main`:
   1. After confirmation, creates the issue "Set up loom" and the branch `chore/<n>-loom-setup`.
   2. Shows a diff, then writes:
      - `.claude/loom.json`
      - `Makefile` (or stack-native scripts) with `lint`, `typecheck`, `test`, `check`
      - `.github/workflows/ci.yml`
      - `.claude/settings.json`: `extraKnownMarketplaces`, `enabledPlugins`, permission allowlist (§19.3), `statusLine` calling `loom-state --line` through `.claude/loom-statusline.py` (optional, §19.3); merged into an existing file, never replaced
      - docs skeleton, one file or directory per docs role at its path in the docs map (§15); by default below `docs/`: `product/vision.md`, `architecture/overview.md`, `architecture/decisions/`, `conventions.md`, `tasks/`. Before `.claude/loom.json` exists the map has its defaults; afterwards setup takes the paths from `docs` in the state.
      - short `CLAUDE.md` pointing to the docs paths
      - `.loom/` entry in `.gitignore`
   3. Optionally creates the labels `type:*`, `size:*`, `mode:*` (`gh label create`, confirmation). The issue gets `type:chore`, `size:S`, `mode:oneshot` if they exist.
   4. Runs `checks.check`, then commits, then hands over to `/loom:describe-pr` (oneshot-style PR). The handover is a normal oneshot task, so `loom-state` routes it: the task directory `<workDir>/<n>-loom-setup/` with `00-ticket.md` (`mode: oneshot`, `size: S`), the commit `chore(loom): set up loom (#<n>)` with the body `Phase 1: oneshot`, and the `log.md` entry `## Phase 1 — done — <hash>`. `next` is then `/loom:describe-pr`.
3. **Ruleset:** offered by `finish-task` after the setup PR is merged, so the required CI check already exists on `main` (§17.3).

**Rules:** existing files are never overwritten silently: setup shows one plan (new files in full, changed files as a diff, and every command that changes something outside the working tree) and acts after one confirmation. Existing commands and CI are reused, not replaced. A reused workflow needs no job named `check`: setup writes the check name of the job that runs the checks (as GitHub reports it: the job `name`, with a matrix suffix if any) into `ci.requiredCheck`, and never renames a job. A stack without a recipe gets `check` and only those of `lint`, `typecheck`, and `test` that the project has; a missing one is `null` (§19.1), and `CLAUDE.md` leaves out its line. A re-run continues where the last run stopped: from the main branch it first switches to an existing `chore/<n>-loom-setup` branch. On the setup branch the setup commit is every path that differs from the main branch, so a re-run after failing checks still commits; a `done` entry in `log.md` means nothing is left but `/loom:describe-pr`. Only on the main branch does a run with nothing to change report that and stop. A setup branch whose PR is already merged stops setup with `Next: git switch <main>, then git pull --ff-only, then /loom:finish-task #<n>`: only the pull brings `.claude/loom.json` to the local main branch.

**Main branch and origin:** `mainBranch` comes from GitHub's default branch (`gh repo view --json defaultBranchRef`), then `origin/HEAD`, then the user. The setup branch is cut from an up-to-date main branch (`git pull --ff-only`). A repository with commits whose main branch is not on `origin` stops setup: the user pushes it (the guard allows only the one-commit bootstrap push). An empty repository whose unborn branch has another name is renamed with `git branch -m <mainBranch>` before the first commit. On an empty repository with no `main` yet, the first commit (only `.gitignore` and `README.md`) is allowed on `main` once; the guard allows it when `main` has no commits.

**Empty repository order:** on an empty repository, setup works in this order:
1. Make the first commit on the main branch (only `.gitignore` and `README.md`).
2. Run `git push -u origin <mainBranch>` (allowed by the guard exception in §11.2).
3. Create the chore branch (step 2.1 above).
4. Write `loom.json` and the other files (step 2.2 above). `loom.json` comes first: `loom-state` and the hooks see nothing without it.

Other untracked files of the empty repository (e.g. the files of `uv init`) go into the setup commit after confirmation.

### 9.2 `backlog`

**Argument:** `[idea or question]`

**Purpose:** product-level planning, between tasks.

**Does:**
- **Discuss ideas:** reads the vision (`docs.vision` in the state, §8.2), the overview and the task summaries, open issues (`gh issue list`), and the code state; discusses options.
- **Create issues** in the format of `references/issue-format.md`: title, context, acceptance criteria, labels. Shows the list and waits for confirmation before `gh issue create`.
- **Prioritize:** answers "what next?" from issue dependencies and what is done.
- Helps fill the vision when it is still a skeleton. The main branch takes no commits, so with an active task and a clean working tree it commits the vision on the task branch (`docs(#<n>): update product vision`); otherwise it offers a `type:docs` oneshot issue that carries the agreed text.
- Issue bodies are written to `<workDir>/_drafts/` (ignored by git), never elsewhere in the repository tree.
- Without `.claude/loom.json` it points to `/loom:setup`. With an active task it says so; new issues do not change the task.

### 9.3 `start-task`

**Argument:** `<#issue | free text>` and optional `--oneshot | --quick | --full`

**Does:**
1. Free text: drafts an issue in the `backlog` issue format, confirms, creates it.
2. Reads the issue: `gh issue view <n> --json title,body,labels,url`.
3. Determines the mode (§5.2).
4. Determines the branch type from the `type:*` label; if missing, proposes one and confirms.
5. Builds the slug with `loom-state --slug '<title>'` (§8.2): issue title → lowercase ASCII, non-alphanumerics → `-`, at most 5 words / 40 characters (words are dropped from the end until it fits; a longer single word is cut; an empty result is `task`).
6. Refuses if the working tree is dirty (offers stash). Then `git switch <mainBranch> && git pull --ff-only` (a main branch that cannot fast-forward stops it), then `git switch -c <type>/<n>-<slug>`.
7. Creates `.loom/tasks/<n>-<slug>/00-ticket.md` from `references/ticket-template.md`: the §13.1 ticket frontmatter and a verbatim copy of the issue (title as the `# ` heading, labels, URL, body).
8. Ends with `Next: /clear, then /loom:next`.

If the issue already has an archived task directory, offers to restore it from `_archive/` instead. The setup issue ("Set up loom") is refused with `Next: /loom:setup`.

### 9.4 `research-questions` (full mode)

**Input:** `00-ticket.md` and files the user mentions.
**Output:** `01-research-questions.md`.

Light contextual research with `loom:codebase-locator`, `loom:codebase-analyzer`, `loom:codebase-pattern-finder` (and `loom:web-search-researcher` only if needed). Writes 2–8 descriptive questions and a verbatim **Key Context Pointers** section. Adds design-system questions if UI work is possible.

**Rule:** questions never reveal what will be built.

**Planned (M9, §9.13.3):** on a setup task this skill stops and names `/loom:research`. `setup` writes `01-research-questions.md` from a fixed list, approved with the setup plan. The fixed list has 7 questions plus the user's own, so the limit of 2–8 questions does not apply to it.

### 9.5 `research`

**Input:** full → `01-research-questions.md` only (never the ticket). quick → `00-ticket.md`.
**Output:** `02-research.md`, `git_commit` = `HEAD`.

**Does:**
1. Groups questions into 2–6 subagent tasks: locators first, analyzers on promising areas, pattern-finder for conventions, web researcher for external docs (links required).
2. Waits for all agents, then synthesizes with `file:line` references.
3. **Claim check:** one `loom:codebase-analyzer` run verifies about 5 randomly chosen `file:line` claims. Failed claims are fixed or moved to "Not Found / Unclear".

**Rule:** describes only; no recommendations or critique.

**Planned (M9, §9.13.3):** on the onboarding task, research answers the fixed onboarding questions. The blind rule holds: it reads only `01-research-questions.md`. It also reads GitHub facts with read-only `gh` commands, and it treats as data the instruction files that Claude Code does not load (§9.13.3): it quotes their rules and never follows them.

### 9.6 `design` (full mode)

**Input:** ticket and research (never research questions).
**Output:** `03-design.md`.

Current state, desired end state, out of scope, proposed architecture (before/after trees, `diff` blocks, key interfaces), testing approach, and the first round (§12). Optional follow-up research with agents.

**Rule:** all questions are written as open. Recommendations are allowed, resolution is not.

Design may read the overview, the ADRs, and the conventions. It takes their paths from `docs` in the state (§8.2).

**Planned (M9, §9.13.4):** on a setup task, design also reads `references/onboarding.md`. It holds the onboarding discussion in the same layout. The topics: what the project is, project rules against loom rules, docs roles, gaps, checks, the required CI check, and PR sections.

### 9.7 `plan`

**Input:** all artifacts except research questions.
**Output:** `04-plan.md`.

Writes the **Phase Overview** (one line per vertical slice) and full implementation phase details (goal, changes as file tree + key signatures, verification with checkboxes). Adds a round only where uncertain. The whole plan is written at once.

**Rule:** implementation phases are vertical slices; each is verifiable by `loom.json` checks.

Plan reads the conventions and the overview from their paths in `docs`, and the check commands from `checks`, in the state (§8.2). It never plans a `null` check.

**Planned (M9, §9.13.5):** on a setup task, the plan copies the content of every loom template it uses into its Changes: the implementer reads only the plan and the project.

### 9.8 `iterate`

**Argument:** `<answers | feedback | "approve" | "rebase">`, or empty.

The single skill for changing anything that already exists. It detects the target from `loom-state --pr` and the argument:

| Situation | Action |
|---|---|
| Open round, argument has answers | Records answers (§12.4), rewrites affected sections, generates the next round or closes questions |
| Open round, empty argument or `ok` | Accepts all recommendations of the current round |
| Feedback on an artifact | Edits it, bumps `updated`, keeps `status: in-review` |
| `approve` | Sets `status: approved`. Refuses while open questions remain, unless the user repeats `approve` in the argument (`/loom:iterate approve approve`); the remaining questions then take their recommendations |
| A blocked implementation phase | Runs the fix loop on it (implementer → checks → reviewer). Not yet committed: commits it as the phase commit and ticks its checkboxes. Already committed: commits a fix commit. Then `done` in `log.md` |
| Feedback on an implemented phase (before PR) | Runs `loom:implementer` on the fix → checks → reviewer → commit → deviation in `log.md` |
| Feedback after the plan is approved that adds, removes, or changes an implementation phase — also with a PR open (this row comes before the post-PR fix path) | Edits the plan (as `draft` while the edit runs, if implementation started; an interrupted edit is finished by the next `iterate`), sets it back to `in-review`, marks affected not-done implementation phases as unchecked; done phases stay done and the change is logged as a deviation |
| All implementation phases done and uncommitted code changes (before the post-PR fix path) | Shows the changes and asks: keep them as a fix (checks → reviewer in fix mode → fix loop on blocking items → fix commit → `log.md` → `pr-update.md` if the PR is open), or drop them (stash or discard, with confirmation; discard loses the work) |
| PR open: failing checks or review comments | Post-PR fix path (§6.2) |
| A stopped rebase (`rebaseInProgress`), with any argument (after the task-directory rows and the unknown-tree stop) | Shows the conflicts, resolves them by the rules of `_shared/git-flow.md` or asks; then `git rebase --continue`, or `git rebase --abort` on the user's choice; then checks and push as below. Never starts a new rebase |
| `rebase` | `git rebase origin/<mainBranch>`, checks, push with `--force-with-lease` (confirmation) |
| Mode change, or an invalid mode (`/loom:iterate mode <oneshot\|quick\|full>`) | §5.3 rules; an invalid mode is repaired at any time, with the mode the user names |
| An unknown working tree (`workingTree: null`), with any argument (this row comes before every row that reads or changes the working tree or commits) | Stops: `git status failed`, `Next: fix the git error, then /loom:next`. Answers, approval, a mode change, and feedback on an artifact before implementation started still run: they change only the task directory |

### 9.9 `implement`

**Argument:** `[implementation phase number]`. Default: the first unchecked phase.
**Input:** `04-plan.md` with `status: approved`; in oneshot, `00-ticket.md`.

**Start:**
- Runs `loom-state`. If the working tree is dirty or `log.md` has a phase `in-progress`, offers: resume, stash, or discard.
- The resume flow does not handle a `blocked` implementation phase. A blocked phase is always handled by `/loom:iterate` (§9.12 rows 3 and 4); `implement` points there.

**Per implementation phase:**
1. Writes `in-progress` for the phase in `log.md`.
2. Launches `loom:implementer` with a short prompt: plan path + phase number (oneshot: ticket path), plus the resolved `checks` and `docs.conventions` from the state (`_shared/implementation-loop.md`). The implementer never reads `.claude/loom.json`, skips a `null` check, and never commits.
3. Checks are enforced by the `SubagentStop` hook (§11.4): the implementer cannot finish while `checks.check` fails. The hook lets the implementer stop after `hooks.maxCheckAttempts` failures, so `implement` runs `checks.check` once more itself. Failing checks there mean the phase is `blocked`; `implement` never commits on failing checks.
4. Launches `loom:implementation-reviewer` with `docs.conventions` and `mainBranch` in its prompt (oneshot: compares the diff with the ticket). The verdict has the categories of §10.2. Only `blocking` items go back to the implementer. At most `implement.maxFixAttempts` fix attempts (from the state, default 2); then `blocked: <reason>` in `log.md` and stop.
5. Commits: `<type>(<scope>): <summary> (#<n>)`, body `Phase N: <name>`; in oneshot mode the body is `Phase 1: oneshot`. `<type>` is the branch type; `<scope>` is the module that holds most of the change (`_shared/git-flow.md`).
6. Ticks the phase checkboxes in `04-plan.md` (Phase Overview and `Automated:` lines; `Manual:` lines stay for the user) and writes `done` with commit hash, checks result, reviewer verdict, deviations, and additions to `log.md` (`implement/references/log-format.md`).
7. **Auto-advance** if checks pass, no `blocking` items remain, and the phase lists no manual verification. Otherwise stops with a phase summary and the manual steps.

The user can override: "do all phases and stop at the end" or "stop after every phase".

- When all implementation phases are done, `implement` stops with `Next:` from `loom-state`, with a clean or a dirty working tree.
- Resume: before it rebuilds an `in-progress` phase, `implement` looks for its commit (`git log --grep='^Phase N:'`); a committed phase only gets its plan ticks and `done` entry. A stash never includes the task directory.
- If the PR is already open (a plan change after the PR added phases), `implement` runs `_shared/pr-update.md` after the last phase: docs refresh, PR body, and push, each with confirmation.

Steps 2–4 are `_shared/implementation-loop.md`; `iterate` runs the same loop for fixes, so both skills decide `done` and `blocked` by the same rules.

### 9.10 `describe-pr`

**Does:**
1. Reads all artifacts and `log.md`. A working tree that is dirty only in the docs paths (`workingTreeDocsOnly`, §8.2) is its own earlier partial run: it continues. Code changes stop it.
   A missing `gh` stops it. So does a failed `gh` when the ticket already has `pr:` (`PR #<n> state unknown`): the PR may exist. Otherwise other `gh` problems (not authenticated, no remote) do not stop it: it still writes the docs and `pr-body.md`, and step 7 reports the failing push or `gh pr create`.
2. quick/full: writes the task summary `<docs.tasks>/<n>-<slug>.md` (§13.4). Its Implementation section ends with `Process metrics: <task.metrics.line>` when `task.metrics` (§8.2) is not `null`; without it the line is left out, never estimated.
3. Creates ADRs for resolved decisions marked `ADR? = yes` (§13.5), in `docs.decisions.dir`, named and numbered by `docs.decisions.pattern`.
4. Checks whether the task changed the architecture; if so, proposes an update to the overview (`docs.overview`).
5. Commits `docs(#<n>): record decisions and summary` — only if something in the docs paths changed.
6. `git rebase origin/<mainBranch>` after the same guarded `git fetch` as `iterate rebase` (no fetch without a remote `origin`); re-runs checks if the rebase brought changes. Failing checks stop it before the push; `/loom:iterate` fixes them.
7. Drafts the PR title (Conventional Commits, ending with `(#<n>)`) and body (§13.6, with the sections of `pullRequest.requiredSections`) in `<task dir>/pr-body.md`, shows them, and after confirmation runs `git push -u origin <branch>` and `gh pr create`.
8. Stores the PR number in `00-ticket.md` frontmatter (`pr: 57`).
9. Proposes follow-ups from the summary as new issues, in the format of `${CLAUDE_PLUGIN_ROOT}/skills/backlog/references/issue-format.md` (confirmation required).

describe-pr takes every doc path from `docs` in the state (§8.2, §15) and `pullRequest.requiredSections` from the state, never from `loom.json`.

**Planned (M9, §9.13.5):** on the onboarding task, the follow-ups include every `Follow-up:` line of the design's Out of Scope.

### 9.11 `finish-task`

**Does:**
1. Runs from the task branch. Refuses on `main`, except `/loom:finish-task #<n>` after a merge that stopped before the cleanup (steps 5–7). Refuses while implementation phases are left, and while local commits are not on the PR (it offers the push, with confirmation): the squash merge takes only what the PR has.
2. Checks the branch is not behind `origin/<mainBranch>`; if it is, routes to `/loom:iterate rebase`.
3. `gh pr checks --required --watch` (pending ≠ failed). Refuses to merge on failure. GitHub marks a check as required only when a ruleset or branch protection requires it; many repositories have none (every repository before its ruleset, private repositories on GitHub Free). Then `finish-task` still enforces `ci.requiredCheck` by name:
   - It runs `gh pr checks --watch` (all checks, the same long timeout; a non-zero exit because a check failed is not an error), then `loom-state --json --pr`, and reads `pr.requiredCheck`.
   - `passing`: it continues; the merge summary says that GitHub requires no check and that loom checked `<ci.requiredCheck>` by name.
   - `failing`: no merge; `Next: /loom:iterate`.
   - `pending`: the watch ended early; it watches again, at most 3 times in all, then stops with `Next: /loom:finish-task`.
   - `missing`: no check with that name ran. It reports "no required checks, and no check named …" and needs the explicit confirmation "yes, merge without required checks".
   - Other failing checks are `Warning:` lines in every case.
4. After confirmation: `gh pr merge --squash --delete-branch --subject '<PR title>' --match-head-commit <sha>` (no number: it selects the PR of the current branch; it deletes the local and remote branch). `--subject` keeps the Conventional Commits title, which already ends with `(#<n>)`, as the squash commit subject; without it GitHub may append ` (#<PR number>)`. `--match-head-commit` is the head whose checks step 3 watched. The title comes from `gh pr view --json title` and is single-quoted (`_shared/git-flow.md`).
5. `git switch <mainBranch> && git pull --ff-only && git fetch --prune`. Deletes the local branch with `git branch -D` only if it still exists.
6. Moves the task directory to `.loom/tasks/_archive/`. `events.jsonl` (§11.6) moves with it; the hook writes nothing for an archived task.
7. If the merged task was the setup task, offers the ruleset (§17.3). The ruleset requires `ci.requiredCheck` from the state (default `check`). `finish-task` first reads the rulesets and the classic branch protection of the main branch, and skips the offer when one of them already requires that check.

All steps are idempotent: re-running after a partial failure continues where it stopped. Every stop after the merge ends with `Next: /loom:finish-task #<n>`, which resumes on the main branch. If the state is empty there (the setup task: the local main branch gets `.claude/loom.json` only from the merge), `/loom:finish-task #<n>` first runs `git pull --ff-only` and `loom-state --json`, and takes its preconditions again with that state.

Dirty working tree: changes only in the docs paths (`workingTreeDocsOnly`) are an interrupted docs refresh, so `finish-task` runs `_shared/pr-update.md` (docs commit, confirmed push) and continues. Code changes stop it with `Next: /loom:iterate`, which keeps them as a fix or stashes or discards them. With the PR already merged, it offers a stash before the cleanup.

### 9.12 `next`

**Purpose:** show the task state and **run** the next phase. It replaces the earlier `next-phase` idea.

**Does:** runs `loom-state --pr`, prints a 3–5 line state summary, then reads and follows the next phase's `SKILL.md` from `${CLAUDE_PLUGIN_ROOT}/skills/<phase>/` (same rules as invoking that skill directly). For `iterate`, `describe-pr`, and `finish-task` it only names the command, because those need the user's input or confirmation.

A file read with Read is not loaded as a skill, so `next` compensates (§24.2):
- **Injection and variables:** Read does not run the phase file's `` !`…` `` line and does not substitute `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_SKILL_DIR}`, or `$ARGUMENTS` in it. The model uses the state that `next` injected (or bare `loom-state --json`) instead of the injection, replaces `${CLAUDE_PLUGIN_ROOT}` with the value shown in `next`'s own (substituted) body, replaces `${CLAUDE_SKILL_DIR}` with `<plugin root>/skills/<phase>`, and treats `$ARGUMENTS` as `next`'s arguments. `next`'s prompt names these placeholders without writing them, because its own body is substituted too.
- **Permissions:** the phase file's `allowed-tools` do not apply. `next` carries the union: its own `… --json --pr` injection rule, bare `loom-state --json`, and the plugin `Read` rule. It reads the phase file and that file's shared files before it asks the user anything.
- **Model:** the phase file's `model` and `effort` do not apply, so `next` uses `model: inherit` with no `effort` (§9.0).

**Decision table** (first matching row wins):

| # | Condition | Next |
|---|---|---|
| 1 | On `main` | suggest `/loom:backlog` or `/loom:start-task #n` |
| 2 | Branch matches no task, or task archived | suggest `/loom:start-task #n` (restore if archived) |
| 2a | A rebase of the task branch is stopped (`rebaseInProgress`) | `/loom:iterate rebase` (continue or abort the rebase) |
| 2b | `00-ticket.md` has no valid mode | `/loom:iterate mode <oneshot\|quick\|full>` |
| 3 | An implementation phase is `blocked` and the plan is not reopened (`04-plan.md` approved or missing, or oneshot) — also with a dirty tree | show the reason; suggest `/loom:iterate <fix>` |
| 4 | Implementation started (`log.md` has a phase entry, or a plan phase is ticked), not oneshot, and `04-plan.md` exists and is not `approved` (a plan change) — with or without a blocked phase, also with a dirty tree | `/loom:iterate <feedback>` if the plan is `draft` (plan edit not finished); else `/loom:iterate <answers>` if it has open questions; else `/loom:iterate approve` |
| 5 | The plan gate holds (oneshot, or `04-plan.md` approved) and: `log.md` phase `in-progress`, or a dirty tree while implementation phases are left. Or all phases done and a dirty tree with code changes (not only in the docs paths) | run `implement` (resume flow); with all phases done: `/loom:finish-task` if the PR is merged, else `/loom:iterate <feedback>` (keep the changes as a fix, or stash or discard them) |
| 6 | Gate artifact (design/plan) `in-review` with open questions | `/loom:iterate <answers>` |
| 7 | Gate artifact `in-review`, no open questions | `/loom:iterate approve` |
| 8 | PR open, or a PR known only from the ticket (`task.pr`, state not read without `--pr`) | PR routing table §6.2; phases left and the plan gate holds: run `implement`, before every other open-PR route. A PR known only from the ticket: run `implement` while phases are left and the plan gate holds; `/loom:finish-task` when all phases are done |
| 9 | All implementation phases done | `/loom:describe-pr` |
| 10 | The plan gate holds, phases left | run `implement` |
| 11 | Otherwise | run the next missing phase for the mode |

**The plan gate** holds for oneshot, and for quick or full when `04-plan.md` is `approved`. An invalid mode never holds it. `next` is never `implement` while the gate does not hold. With an invalid mode, `next` is always `/loom:iterate mode <oneshot|quick|full>` (row 2b), except on rows 1, 2, and 2a: every later row depends on the mode. Artifacts have no `blocked` status (§13.1); `loom-state` reports such a value as an unknown status (`in-review`, with a warning).

Gate work (rows 6 and 7) comes before PR routing and "all implementation phases done": a design or plan that went back to review, for example after a plan change on an open PR, is never skipped. Before implementation starts, a `draft` gate artifact is unfinished work and falls to row 11, which reruns its phase (`/loom:plan` overwrites a draft plan). After implementation started, a draft or in-review plan is a plan change and row 4 handles it, before the dirty tree, PR routing, and describe-pr. Non-gate artifacts (research-questions, research) never block row 11. If research is `in-review`, `next` prints "research not reviewed" and continues. If research is stale, it warns and offers to rerun research.

Row 5 and a dirty tree: `implement` resumes only while implementation phases are left and the plan gate holds. Before the gate holds, a dirty tree (research, design, and plan change no code) or a `log.md` entry in progress falls through to the later rows (open questions, approve, the missing phase), and `loom-state` adds the warning `working tree has uncommitted changes; they are not part of research, design, or plan (commit, stash, or discard them before /loom:implement)` or `log.md has implementation phase <N> in progress, but 04-plan.md is not approved; implementation waits for the plan gate`. With all phases done, a tree that is dirty only in the docs paths (`workingTreeDocsOnly`) is an interrupted `describe-pr` and falls through to the later rows (row 9, `/loom:describe-pr`, which continues its partial run; with an open PR, the PR routing of row 8, whose skills commit the docs through `_shared/pr-update.md`); code changes go to `/loom:iterate` (or `/loom:finish-task` when the PR is merged). A skill that refuses a dirty tree names the skill that handles the changes, never a `Next:` that leads back to the same refusal.

An unknown working tree (`workingTree: null`, `git status` failed or timed out) never routes to `/loom:describe-pr` or `/loom:finish-task`. Instead, `next` is `/loom:iterate <feedback>` with the reason `git status failed, so uncommitted changes are unknown; fix the git error in the warnings, then run /loom:next again (<command> needs a known working tree)`. Other routes are unchanged. `implement`, `describe-pr`, and `finish-task` stop on it with `Next: fix the git error, then /loom:next`. `iterate` stops on it too, whatever the argument is, before every section that reads or changes the working tree or commits; only answers, approval, a mode change, and feedback on an artifact before implementation started still run (they change only the task directory).

Rows 2a and 2b in the skills: `iterate` handles a stopped rebase in its Rebase section (after an explicit mode, `approve`, answers, and the unknown-tree stop, §9.8), and repairs an invalid mode in its Mode change section, also after implementation started. `implement`, `describe-pr`, and `finish-task` stop while `rebaseInProgress` is `true`, with `Next: /loom:iterate rebase`.

### 9.13 Onboarding an existing repository (planned, M9)

**Status:** planned for v1.2, milestone M9, in two milestones (§9.13.8). Milestone M9a (config keys and their use in existing skills) is implemented and not released yet (`CHANGELOG.md`, `[Unreleased]`). Milestone M9b (the onboarding flow) is planned: other sections mark each M9b change with **Planned (M9, §…):**. Text without that marker describes the current behavior: release 1.1.0 plus M9a.

Today `setup` on a repository with code runs one `oneshot` task: it detects the stack, reuses an existing `Makefile` and CI, adds config, and writes empty doc skeletons. It does not discuss the project. Since M9a, skills take the doc paths from the docs map, so a project can keep its own documentation structure (§15). M9 adds an onboarding flow that works for any project. It uses loom's own `full` mode, so the discussion, the gates, the artifacts, and the reviews come from the normal phases.

Terms (M9a added the docs terms and M9b adds the task terms to §3 and to the glossary of `_shared/writing-style.md`):

| Term | Meaning |
|---|---|
| **setup task** | The task of the issue "Set up loom", on the branch `chore/<n>-loom-setup` |
| **onboarding task** | A setup task in `full` mode: the setup of a repository with code |
| **docs role** | One kind of durable document that loom reads or writes: `vision`, `overview`, `decisions`, `conventions`, `tasks` (§15) |
| **docs map** | `loom.json` → `docs`: the path of each docs role (§19.1) |

#### 9.13.1 Two setup paths

| Repository (files tracked on the main branch) | Path | Mode of the setup task |
|---|---|---|
| Empty or new: no commits, or only files that are not code (list below) | Fast setup of §9.1, unchanged | `oneshot` |
| With code: any other tracked file | Onboarding (this section) | `full` |

Files that are not code: `README*`, `LICENSE*`, `.gitignore`, `.gitattributes`, `.editorconfig`, `CODEOWNERS`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, and files below `.github/` except `.github/workflows/`. A workflow file counts as code.

**Path selection.** `setup` takes the first matching row:

| Where `setup` runs | Condition | Path |
|---|---|---|
| The main branch | A branch `chore/<n>-loom-setup` exists, local or on `origin` | Switch to it (§9.1), then use the setup-branch rows |
| The main branch | `origin/<main>` has `.claude/loom.json` | The re-run rules of §9.1 (loom is set up) |
| The main branch | Otherwise | By the table above |
| An existing setup branch `chore/<n>-loom-setup` | `<task dir>/00-ticket.md` has `mode: full` | Onboarding re-run (§9.13.2) |
| An existing setup branch | The ticket is missing (a fresh clone), and `git log origin/<main>..HEAD` has the subject `chore(loom): start loom setup (#<n>)` | Onboarding re-run (§9.13.2) |
| An existing setup branch | `origin/<main>..HEAD` is empty (setup stopped after `git switch -c`, before the ticket) | By the repository's files, as on the main branch |
| An existing setup branch | Otherwise | The fast-path resume of §9.1 |

- The setup plan names the chosen path and why. The user can switch to the other path in the answer. `/loom:setup --oneshot` also forces the fast path. An empty repository has nothing to research, so it never takes the onboarding path.
- The bootstrap rules of §9.1 apply only to the fast path on an empty repository: the first commit on the main branch, its first push, and the guard exceptions of §11.2. An onboarding repository has commits, so the existing precondition applies: its main branch must be on `origin`. Onboarding never uses a guard exception.
- `loom-state` recognizes the setup task by its branch `chore/<n>-loom-setup` and reports `task.setup: true` (§8.2). An onboarding task is a setup task with `task.mode` `full`. The ticket gets no new field.
- The mode of a setup task is fixed by `setup`. `iterate` refuses a mode change on it (§5.3). `start-task` keeps refusing the setup issue (§9.3).

#### 9.13.2 Kickoff (`setup`)

On the onboarding path, `setup` does only the kickoff. It shows one plan and acts after one confirmation, by the rules of §9.1. The plan lists the fixed research questions; the user adds project-specific questions there explicitly.

1. Preconditions and the update of the main branch, as in §9.1.
2. **`.gitignore`:** the `.loom/` line (or `<workDir>/`) if missing. It comes first: the issue draft goes below `workDir`. The uncommitted change goes with the branch, as in §9.1.
3. **Labels:** the missing loom labels (§19.2), optional (`gh label create`, confirmation). Existing labels and label schemes stay. Issues are not migrated: `start-task` proposes the mode for an issue without loom labels (§5.2).
4. **Issue:** "Set up loom" from `templates/setup-issue-onboarding.md`, with the labels `type:chore`, `size:M`, `mode:full` that exist. The notes of `/loom:setup <notes>` go into the issue body. An open issue with this exact title is reused.
5. **Branch:** `chore/<n>-loom-setup` from the up-to-date main branch.
6. **Ticket:** `<workDir>/<n>-loom-setup/00-ticket.md` with `mode: full`, `size: M`, and the issue copied verbatim (§9.3 step 7). It comes right after the branch, so a re-run finds the onboarding path.
7. **`.claude/loom.json`, minimal:** `version` and `mainBranch` (and `workDir` if it is not the default). Every other key takes its §19.1 default until implementation phase 1 writes the full file.
8. **Kickoff commit:** `chore(loom): start loom setup (#<n>)`, with only `.claude/loom.json` and, if step 2 changed it, `.gitignore`, and no `Phase` line in the body. It keeps the working tree clean. A dirty tree would route the task to the resume flow of `implement` (§9.12 row 5).
9. **Research questions:** `<task dir>/01-research-questions.md` with the fixed list of §9.13.3 and the questions the user added. `status: approved`: the user approved the list with the plan confirmation (an exception to §13.1). Key Context Pointers lists, verbatim, the paths that setup found while it chose the path (instruction files, workflow files, PR templates, docs directories).
10. **Final message:** `Next: /clear, then /loom:next`. `next` then runs `research` (§9.12 row 11).

Size `M` caps the design rounds at 3 (§12.5). Most onboarding questions are independent, so round 1 carries most of them.

**Onboarding re-run.** `setup` completes only the missing kickoff items (ticket, kickoff commit, research questions file). Then it stops with `Next:` from `next.command`. It never writes the files of the implementation phases. On a fresh clone the ignored task directory is missing: setup writes the ticket and the research questions again. Research, design, and plan are lost, as for every task (§4.3).

#### 9.13.3 Research: the fixed question list

The list is `skills/setup/references/onboarding-questions.md`, in the §13.2 layout of `01-research-questions.md`. `research-questions` does not run on a setup task: it stops and names `/loom:research`. The questions are descriptive, as §9.4 requires. The fixed list has 7 questions, and the user's questions come on top: the limit of 2–8 questions of §9.4 does not apply to it.

1. **Stacks and check commands.** Which languages, package managers, and lock files does the repository use, and where? Which commands run lint, format check, typecheck, unit tests, build, and e2e tests today (`Makefile`, `justfile`, `Taskfile.yml`, `package.json` scripts, `tox.ini`, `noxfile.py`, `scripts/`)? Is there one root command that runs several of them? Which services, secrets, or network access does each command need?
2. **CI.** Which workflows exist in `.github/workflows/` (and other CI configuration)? For each: the triggers, the check names as GitHub reports them (job `name`, with matrix suffixes), the commands each job runs, how actions and tools are pinned, and how long the jobs ran in the latest run on the main branch (`gh run list`, `gh run view`).
3. **Documentation.** Where do the docs live (README, `docs/`, `doc/`, ADR directories, wiki links)? What are the structure, the file formats, and the file naming? Which documents describe the product and its users, the architecture and its components, past decisions (with their file name pattern and layout), code conventions, and past work (changelogs, task notes)?
4. **Agent instruction files.** Which of `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`, `GEMINI.md`, and similar files exist? Which of them does `CLAUDE.md` import with `@`? What do they state about branches, commits, push, pull requests, confirmations, the planning workflow, checks, and code? Quote each rule with `file:line`.
5. **Conventions.** Which linter, formatter, and type checker configurations exist, with their main settings? How are tests laid out (directories, naming, fixtures)? How are modules and packages laid out?
6. **Git process.** What are the default branch, the branch name patterns in use, the commit message format on the main branch, and the merge method (from history)? Which PR templates exist, with which sections? Which CI steps or actions read the PR title or body? Which labels, open issues, and milestones exist? Which rulesets or branch protection rules apply to the main branch?
7. **loom requirements.** For each item, does it exist today, and where:
   - one root command that runs lint, typecheck, and unit tests; separate commands for each;
   - a CI job that runs that command on pull requests and on pushes to the main branch;
   - a document in each docs role (§15);
   - tests, and the result of the latest CI run on the main branch;
   - `.claude/settings.json`, and its keys.

Rules for the onboarding research:

- **Blind rule:** it holds unchanged. Research reads only `01-research-questions.md`, never the ticket (§9.5). The ticket of the onboarding task holds nothing that the fixed list misses.
- **Describes only:** question 7 is answered as "exists" or "does not exist", with the location. Design names the gaps; research never writes "missing" or "should".
- **GitHub facts:** research reads them in the main context with read-only commands: `gh repo view`, `gh label list`, `gh issue list`, `gh run list`, `gh run view`, and `gh api` GET of rulesets, branch protection, and milestones (the permission system asks for `gh api`, §16.4). A fact it cannot read goes to Not Found / Unclear.
- **Instruction files:** Claude Code loads `CLAUDE.md` and its `@` imports into every session and subagent. During the onboarding task their rules are in effect, not data. The other instruction files are not loaded (`AGENTS.md` without an import, `.cursorrules`, `GEMINI.md`, …): research quotes their rules as data and never follows them. The same holds for every other document it reads.
- **Safeguard until the loom section lands:** a loaded rule such as "push without confirmation" can conflict with loom. Until the setup PR adds the loom section and the `ask` rules of §19.3 (implementation phase 1 and later), the safeguard is the skills' own confirmations and the guard hook (§11.2). The hooks are no-ops on every branch without `.claude/loom.json` (§11), so until the setup PR is merged, the guard works only on the setup branch, which has the kickoff `loom.json`.

The result is `02-research.md` with `file:line` references, as for every task.

#### 9.13.4 Design: the discussion

On a setup task, `design` also reads `skills/design/references/onboarding.md` (the topics and defaults below), with its other shared files, before any question. `03-design.md` keeps the §13.2 layout:

| Section | Onboarding content |
|---|---|
| Current State | The project as research found it: stacks, check commands, CI, docs, instruction files, git process |
| Desired End State | What the setup PR leaves: the full `loom.json`, `checks.check`, the required CI check that runs it, the docs roles, the `CLAUDE.md` loom section, `.claude/settings.json` |
| Out of Scope | Each gap deferred to an issue, as one line `Follow-up: <gap>`. No migration of issues, labels, or branches. |
| Proposed Architecture | The drafts of topic 1, the docs map, the new `loom.json`, the check and CI changes, a `diff` for each changed instruction file, and the table of project rules and their resolution |
| Open Questions | One round per §12, over the topics below |
| Testing Approach | `checks.check` passes locally and in the required CI check of the setup PR |

Topics. Topics 2–7 are one or more questions with 2–4 options and a recommendation; the independence rule of §12.1 applies:

1. **What the project is.** Design drafts vision and overview from the code and the README, as `### Draft: vision` and `### Draft: overview`. It drafts only a role whose recommended option in topic 3 is **create**. If the user maps the role instead, the draft is dropped. The user corrects a draft with `/loom:iterate <feedback>`.
2. **Project rules and loom rules.** One question per conflict between a project rule (research question 4) and a loom rule. Default recommendation:
   - loom's safety rules win in loom-run flows: the confirmations of §16.4, the guard on the main branch (§11.2), and one command per Bash call (§9.0);
   - the formats that loom writes and parses win for loom tasks: the branch name `<type>/<n>-<slug>`, the commit subject `<type>(<scope>): <summary> (#<n>)`, the `Phase N:` commit body, `Closes #<n>` in the PR body, and the task summary file name `<n>-<slug>.md` (open topic in §24.1);
   - every other project rule stays authoritative. The `CLAUDE.md` loom section references it.
   Examples of conflicts: "push and open PRs without confirmation", another branch or commit format, another planning workflow. The resolutions go into the `conventions` document, as a table "project rule → resolution in loom tasks". The `CLAUDE.md` loom section states the precedence in one line and links that table.
3. **Documentation.** For each docs role, one of:
   - **map:** an existing document plays the role; the docs map records its path (recommended when one exists);
   - **migrate:** move the files into loom's layout and update the links in the same implementation phase (only when the user asks: other documents and people link to the old paths);
   - **create:** a new document from the setup skeleton or the approved draft (recommended when none exists).
   For `decisions`, the design records the directory and the file name pattern of the existing ADRs. Known limit: loom reads and writes Markdown only. A project whose docs are reStructuredText or AsciiDoc can only **create** loom's documents.
4. **Gaps.** For each gap of research question 7 and the other findings: close it in the setup PR, or defer it to a follow-up issue. Default: §9.13.6.
5. **Checks.** Which command is `checks.check`: the fast set that the implementer and the `SubagentStop` hook run.
   - It must pass on the main branch today and finish within the hook timeout (540 seconds, §11.4).
   - A check that fails on the existing code (for example a new type checker) stays out of `checks.check` and becomes a follow-up issue.
   - Slow checks and checks that need services (e2e tests) stay CI-only (§17.1).
   - `checks.lint`, `checks.typecheck`, and `checks.test` may be `null` when the project has no such check (§19.1).
   - Several stacks (§18): one root command must run the checks of every stack. If each stack has its own commands and no root command exists, the setup PR adds a root entry point that only calls them (a gap of §9.13.6).
6. **The required CI check.** Which CI check runs `checks.check` (§17.2):
   - a) change an existing job to run `checks.check` exactly, plus its CI-only steps, and record its check name in `ci.requiredCheck` (recommended when a job already runs the same checks);
   - b) add a job named `check` that runs `checks.check` (recommended when no job fits).
   Never rename an existing job: branch protection may require the old name. The ruleset that `finish-task` offers requires `ci.requiredCheck` (§17.3).
7. **PR body.** Which sections the PR template or a CI check requires. They go into `pullRequest.requiredSections` (§13.6, §19.1).
8. **Agent instruction files.** Fixed plan items, not questions:
   - `AGENTS.md` exists and `CLAUDE.md` does not: a new short `CLAUDE.md` with the line `@AGENTS.md` and the loom section;
   - `CLAUDE.md` exists: the loom section is added to it, shown as a `diff`;
   - other instruction files: no change. A topic 2 answer can still change one; that change is a plan item with a `diff`.
   loom never rewrites an instruction file silently.

#### 9.13.5 Plan, implementation, and PR

The plan has the normal layout. Typical implementation phases:

1. **Config and checks:** the full `.claude/loom.json` (checks, docs map, `ci.requiredCheck`, `pullRequest.requiredSections`), the missing parts of the check entry point, `.claude/settings.json` merged by the rules of §19.3, and the optional status line.
2. **CI:** the required check runs `checks.check`.
3. **Docs:** map, migrate, or create each docs role; vision and overview from the approved drafts; the `conventions` document with the CI-only checks (§17.1) and the table of project rules.
4. **Agent instructions:** `CLAUDE.md` and the agreed changes to other instruction files.

- The implementer reads only the plan and the project, never plugin files. So the plan copies small loom templates into its Changes (`loom.json`, the `settings.json` rules, the CI job, the `CLAUDE.md` loom section).
- A larger template (e.g. `loom-statusline.py`) is named in the plan by its path below `skills/setup/references/templates/`. `implement` (its main session may read plugin files) copies it into `<task dir>/templates/` before it launches the implementer, and names that copy in the implementer prompt.
- Each implementation phase runs as for any task: implementer, checks (enforced), reviewer, commit. From phase 1 on, the `SubagentStop` hook runs the new `checks.check`.
- `describe-pr` and `finish-task` run as for any task. The task summary goes to the `tasks` path of the docs map. `describe-pr` proposes every `Follow-up:` line of the design's Out of Scope as an issue (§9.10 step 9, confirmation).
- After the merge, `finish-task` offers the ruleset (§17.3) with `ci.requiredCheck` as the required check.

#### 9.13.6 Gap scope

The setup PR closes only the gaps that loom needs to work:

- the full `.claude/loom.json`;
- one check entry point for `checks.check` (and `lint`, `typecheck`, `test` where the project has them);
- CI runs `checks.check` in the required check;
- `.claude/settings.json` and the `.gitignore` line;
- the `CLAUDE.md` loom section (or a new `CLAUDE.md`);
- the docs roles that the design chose to map, migrate, or create.

Every other gap becomes a follow-up issue after the PR, for example: no tests, no type checker, a check that fails on existing code, old lint errors, missing docs beyond the roles. The setup PR on a mature repository stays reviewable.

#### 9.13.7 Agent instruction files

- **`AGENTS.md` without `CLAUDE.md`:** the onboarding plan writes a short `CLAUDE.md` that imports `@AGENTS.md` and adds the loom section (topic 8). The fast path does not change.
- **Existing instruction files:** never rewritten silently. A change is a plan item with a `diff`.

#### 9.13.8 Implementation milestones

A prompt change is done only when its eval case passes (§20.3). New cases cost tokens, so each milestone names the minimum.

| Milestone | Changes | Tests and evals |
|---|---|---|
| **M9a** (done) — config keys and their use in existing skills | `bin/loom-state`: parse and validate `docs`, `ci`, `pullRequest`, and `null` check commands (§19.1); output the resolved `docs`, `checks`, `ci`, and `pullRequest`, and the wider `workingTreeDocsOnly` (§8.2). Hooks: `stop_lint.py` ignores every docs path and does nothing without `checks.lint`; `block_output_filtering.py` skips `null` commands. **Docs map:** `setup` (skeleton by role), `backlog`, `design`, `plan`, `implement` and `iterate` (they pass `docs.conventions` to the implementer and the reviewer), `describe-pr` and its templates, `_shared/pr-update.md`; agents `implementer` and `implementation-reviewer` take the conventions path from their prompt. **`ci.requiredCheck`:** `finish-task` builds the ruleset with it and skips the offer when a ruleset or classic branch protection already requires it (§17.3). **Checks for the implementer:** `implement` and `iterate` pass the resolved `checks` in the implementer prompt, like `docs.conventions`. `agents/implementer.md` no longer reads `.claude/loom.json`, skips a `null` key, and never invents a command for it. **`pullRequest.requiredSections`:** `describe-pr`, `pr-template.md`, and `_shared/pr-update.md`, whose check for the layout before v1.1 ignores the required headings. Glossary terms **docs role** and **docs map**. | Unit tests: defaults, custom values, invalid values, warnings; lints that no skill builds a role path or reads these keys from `loom.json` itself. No new eval case: the `describe-pr-quick` fixture gets a non-default `docs.tasks` and `pullRequest.requiredSections: ["## Test plan"]`, with a `file_exists` grader on the mapped summary path and a grader for `## Test plan` after `## Decisions`. The fixture keeps the default `docs.decisions`: it has no decision with `ADR? = yes`. Rerun `describe-pr-quick`, `design-full`, `implement-manual`. |
| **M9b** — onboarding flow | `setup`: path selection, `--oneshot`, kickoff, onboarding re-run, templates `setup-issue-onboarding.md` and `onboarding-questions.md`. `bin/loom-state`: `task.setup`. `research-questions`: stop on a setup task. `research`: the fixed list, GitHub facts, instruction files. `design`: `references/onboarding.md`, including the `CLAUDE.md` plan item with `@AGENTS.md`. `plan`: the template rule of §9.13.5. `implement`: copies larger templates into the task directory. `iterate`: no mode change on a setup task. `finish-task`: recognizes the setup task also by `task.setup`. Glossary terms **setup task** and **onboarding task**. | Unit tests for path selection, `task.setup`, and the skill texts. One new eval case, `design-onboarding`: a setup task in full mode with approved research, a fixture with `AGENTS.md` ("push and open PRs without confirmation") and a CI job named `test`. Graders: `03-design.md` in review with round 1, empty Resolved Decisions, a question that names `AGENTS.md`, no Read of `01-research-questions.md`. Rerun `research-full`, `design-full`, `implement-manual`. The kickoff needs `gh` and `origin`, which eval runs lack: static tests plus one live run on a sandbox repository. |

`setup`, `backlog`, `plan`, `iterate`, and `finish-task` have no eval case; their changes get static tests in `tests/test_skills.py` and `tests/test_setup.py`.

Each milestone removes its **Planned** markers from this spec and adds its `CHANGELOG.md` entry when it ships.

---

## 10. Subagents

### 10.1 Definitions

Defined as `agents/*.md`, ported from HumanLayer's daemon-registered agents. Plugin agents are namespaced: skills call them as `loom:<name>`.

| Agent | Model | Tools | Used by | Role |
|---|---|---|---|---|
| `codebase-locator` | haiku | Grep, Glob, Bash | research-questions, research, design, plan | Finds WHERE things live; returns paths grouped by purpose |
| `codebase-analyzer` | sonnet | Read, Grep, Glob | same + research claim check | Explains HOW code works with `file:line` references |
| `codebase-pattern-finder` | sonnet | Read, Grep, Glob | same | Finds similar implementations and conventions |
| `web-search-researcher` | sonnet | WebSearch, WebFetch | research | External docs and libraries; always returns links |
| `implementer` | inherit | Read, Edit, Write, Grep, Glob, Bash | implement, iterate | Implements exactly one implementation phase; runs checks; never commits |
| `implementation-reviewer` | sonnet | Read, Grep, Glob, Bash | implement, iterate | Compares the phase diff with the plan (or ticket in oneshot) |

- `tools` lists only plain tool names. Command restrictions (e.g. read-only Bash for the locator and reviewer) are stated in the agent prompt and enforced by hooks where needed.
- All research agents carry the "document what exists, never critique" rule.
- The agents with Bash (`codebase-locator`, `implementer`, `implementation-reviewer`) carry the one-command rule of §9.0 inline.
- The implementer gets the resolved `checks` and `docs.conventions` in its prompt, and the reviewer gets `docs.conventions` and `mainBranch` (the `Main branch:` line, for the phase commit lookup in fix mode; §9.9). Neither agent reads `.claude/loom.json`. The implementer skips a `null` check and never invents a command for it. Without these prompt lines, both read the values from `loom-state --json`.

### 10.2 Reviewer verdict format

```markdown
## Verdict: pass | changes-needed
### As planned
### Deviations          ← each: what, why it matters, blocking | nit
### Additions           ← not in the plan
### Planned but missing ← blocking by default
```

`implement` sends only `blocking` items back. Deviations and additions go to `log.md` and later into the task summary.

---

## 11. Hooks

All hooks are declared in `hooks/hooks.json` and call Python scripts in `${CLAUDE_PLUGIN_ROOT}/scripts/hooks/` (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/<name>.py"`).

Rules for every hook:
- Silent no-op (exit 0, no output) outside a git repository and in a repository without `.claude/loom.json`: the plugin may be enabled in unrelated projects.
- Never break a session: on an unexpected error the hook exits 0 and writes a short message to stderr.
- `PreToolUse` hooks deny with exit 0 and JSON: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "…"}}`.

### 11.1 `SessionStart` — task context

- Matchers: `startup`, `resume`, `clear`, `compact`, `fork`.
- Runs the `loom-state` logic (no `--pr`: no network at session start) and prints a short plain-text summary to stdout, which Claude Code adds to the context: task directory, mode, artifact statuses, next step.
- On `main` or an unrecognized branch: injects one hint line, then one `Warning: <text>` line per `loom-state` warning (an invalid `loom.json`, for example). With a task, the warnings are part of the summary.

### 11.2 `PreToolUse` (Bash) — guard the main branch

- Reads `mainBranch` from `loom.json`, validated as in `loom-state` (§8.3).
- Blocks `git commit` when the current branch is the main branch, and `git push` when the current branch is the main branch unless the push cannot update the main branch on the remote (see below). Two bootstrap exceptions apply to an empty repository (§9.1):
  - the very first commit, when the main branch has no commits;
  - a plain first push of the main branch: `refs/remotes/origin/<mainBranch>` does not exist and the main branch has exactly one commit. The guard checks both conditions locally, with no network call. "Plain" means all of these:
    - the real current HEAD (read from git, not from a `switch`/`checkout` earlier in the same command) is the main branch;
    - the remote is `origin` (given, or resolved from `branch.<main>.pushRemote`, `remote.pushDefault`, `branch.<main>.remote`);
    - the only flags are `-u`/`--set-upstream`, `-q`/`--quiet`, `-v`/`--verbose`;
    - the refspecs are none, or only `<main>`, `HEAD`, `HEAD:<main>`, `<main>:<main>`, `refs/heads/<main>`. A `+` prefix, any force flag, `--mirror`, `--all`, `--branches`, `--delete`/`-d`, or an empty source (`:<main>`) never qualifies.
- On the main branch, a push that cannot update the main branch is allowed. That is a push with explicit refspecs, none of which targets the main branch: tags (`git push origin v1.0.0`, `git push origin tag v1.0.0`), `--tags` with no refspec, other branches (`git push -u origin feat/9-x`), deletions of other branches (`--delete feat/9-x`, `:feat/9-x`). A dry run (`--dry-run`, `-n`) is allowed from any branch, because it updates nothing.
- Still blocked on the main branch:
  - a push without a refspec (also with `-u` or `--follow-tags`);
  - `HEAD`, `<mainBranch>`, the matching refspec `:`;
  - `--all`, `--mirror`, `--branches`;
  - a refspec the guard cannot resolve (a variable or a command substitution).
  - Reason: "git push of the main branch '<main>' is blocked: <without a refspec it pushes the current branch | the refspec `<spec>` cannot be resolved before it runs>. On the main branch only a push that cannot update it is allowed (tags, other branches, --dry-run). Create a task branch with /loom:start-task".
- Blocks any push whose refspec targets the main branch, from any branch, including force pushes. Covered forms: `origin main`, `HEAD:main`, `+main`, `:main`, `--force`/`-f`/`--force-with-lease … main`, `--all`, `--mirror`, `--branches`, and the matching refspec `:`. With `--repo=<repository>`, every positional is a refspec. This is intentional: it closes bypasses such as `git push origin HEAD:main` from a task branch. Reason: "git push to the main branch '<main>' (<refspec>) is blocked. Create a task branch with /loom:start-task".
- The guard blocks only `git commit` and `git push`. `merge`, `cherry-pick`, `revert`, `reset`, `pull`, `branch -f`, and `update-ref` on the main branch are out of its scope.
- Reads the command with its own small bash parser (`scripts/hooks/loomhook.py`):
  - Compound commands (`&&`, `||`, `;`, `&`, newlines, `|`) and groups. A `cd` inside a subshell `( … )`, a command substitution, `bash -c`, or one stage of a multi-stage pipeline does not leak out. A brace group `{ …; }` runs in the current shell.
  - Directories and repositories: `cd <dir>`, `cd -`, `pushd`/`popd`, `git -C <path>`, `--git-dir`/`--work-tree`, and the `GIT_DIR`/`GIT_WORK_TREE` variables (as a prefix, after `env`, or exported earlier in the command). `env -C <dir>` and global git options before the subcommand (including `--attr-source`) are covered too.
  - Git aliases: configured aliases, aliases of aliases, `!` shell aliases, and aliases set on the command line with `-c alias.<name>=<value>`. An alias the guard cannot read counts as both `commit` and `push`: `--config-env=alias.<name>=…`, a value with a variable, or `GIT_CONFIG_COUNT`/`GIT_CONFIG_PARAMETERS` in the environment.
  - Wrappers and prefixes: `env`, `sudo`, `command`, `exec`, `nohup`, `time`, `timeout [options] <duration>`, `nice [-n N]`, `ionice`, `stdbuf`, `xargs`, `noglob`, zsh `=git`, `function f { …; }`, `f() { …; }`. `command -v|-V <name>` runs nothing.
  - Code the shell runs although it sits in a word or on stdin: `$( … )` and backticks (also inside double quotes and in the body of an unquoted here-doc), process substitutions `<( … )`/`>( … )`, and `eval`. Also `bash -c` (also with options before `-c`, such as `-o pipefail` or `-euo pipefail`), and a shell that reads its script from a here-doc, a here-string, or `echo`/`printf`/`cat <<EOF` through a pipe.
  - Quoted, backslashed, and hyphenated here-doc delimiters (`<<'END-MSG'`, `<<\EOF`), and `$'…'` strings.
  - Text inside single or double quotes (`echo "git commit"`) is not a command, but a substitution inside double quotes is.
- Conservative where it cannot resolve the command:
  - A `cd`, `pushd`, `git -C`, `env -C`, `GIT_DIR`, or `GIT_WORK_TREE` target that contains a variable, a backtick, or a substitution, or that is not an existing directory, means the original cwd.
  - `popd` and `cd -` without a known stack or `OLDPWD` also mean the original cwd.
  - A branch the guard cannot resolve (a variable) means the real current branch.
- Follows branch switches earlier in the same command. Branches are repository state, so a switch inside a subshell counts for the rest of the command.
  - `git switch`/`git checkout <name>`: a switch when `<name>` is a local branch, a branch created earlier in the command, or a remote branch that git creates locally. `git checkout <commit>` and `--detach` mean a detached HEAD. Otherwise the branch does not change: `git switch <name>` of a branch that does not exist fails.
  - `-c`/`-b`/`--orphan <name>` (also `--create=<name>`, `-b<name>`, `-qb <name>`): a switch only when `<name>` does not exist, because git refuses an existing branch. `-C`/`-B` always switch. `--track <remote>/<branch>`: only when the local branch does not exist.
  - `-` and `@{-N}`: resolved through `git rev-parse --symbolic-full-name @{-N}`, or through the previous branch within the command.
  - `git checkout <branch> --` with nothing after `--` is a switch. `git symbolic-ref HEAD refs/heads/<x>` and `git branch -m [<old>] <new>` are tracked too.
  - The right side of `||` runs only when the left side failed. So it is checked with the branch state from before each command of the `&&`/`||` list that may have failed: `git switch feat/x || git commit` on the main branch is denied.
- If the command cannot be parsed (an unterminated quote, for example), a conservative text fallback applies. It is linear in the text, and it calls git only when the text matches.
  - Any `git … commit|push` is denied while the current branch is the main branch (as tracked in the command, or as git reports it).
  - From any branch, a `git … push` is denied when it is followed in its command by a refspec-like word that names the main branch: `main`, `HEAD:main`, `:main`, `+main`, `refs/heads/main`.
  - `commit` or `push` counts when it is at most 32 words after `git` on the same line, in the same command (between `;`, `&`, `|`).
  - Code nested more than 4 levels deep (substitutions, `bash -c`, aliases) and groups nested more than 50 levels deep also get the fallback.
- Every git answer (current branch, refs, aliases, config) is cached for the hook run. The hook never changes the repository, so a long script stays well inside the 10-second hook timeout.
- Denies a commit with the reason "git commit on the main branch '<main>' is blocked. Create a task branch with /loom:start-task". Every deny reason ends with "Create a task branch with /loom:start-task".

Known limits:
- Variables or command substitutions inside a refspec, from a branch other than the main branch: `git push origin "HEAD:$B"`, `git push origin $(echo main)`.
- Non-default git config that changes what a push updates: `push.default=upstream` or `matching`, `remote.<r>.push`, `remote.<r>.mirror`, `git remote add --mirror=push`. For example, a push without a refspec from a task branch whose upstream and push config map it to the main branch. This includes the bootstrap exception (`-c remote.origin.mirror=true`). Each case needs deliberately set non-default config.
- Shell aliases and functions from the user's profile, a command name from a variable (`G=git; $G commit`), and quoting or case tricks in the command name (`g"i"t`, `g''it`, `gi\t`, `GIT` on a case-insensitive file system).
- Shell-function aliases that use positional arguments (`!f() { git push origin "$1"; }; f`) are not resolved.
- A script piped into a shell from anything other than `echo`, `printf`, or `cat <<EOF` (`cat x.sh | bash`, `curl … | sh`), and a script file (`bash x.sh`). Aliases from config files included through `include.path`.
- A branch switch that fails for a reason the guard cannot see (a dirty working tree, a conflict) counts as done: `git switch feat/x; git commit` is allowed although the commit may land on the main branch.
- A directory created earlier in the same command does not exist yet, so the original cwd applies. From a task branch, `git worktree add ../wt main && cd ../wt && git commit` is allowed (the commit lands on main). From the main branch, `git worktree add ../wt -b feat/x && cd ../wt && git commit` is denied.
- A stopped rebase of the main branch leaves HEAD detached, so the guard allows `git commit` (`loom-state` reports `rebaseInProgress`).
- DWIM is approximated: a branch that exists on any remote counts, also when several remotes have it (git then refuses).
- The text fallback for unparsable commands can match text after a `#` comment or inside quotes.

### 11.3 `PreToolUse` (Bash) — block output filtering

Ported from HumanLayer's `block-test-output-filtering.sh`, adapted to `make`, `pytest`, `ruff`, `pyright`, `npm test`. Blocks check commands piped into `head`, `tail`, `grep`, etc., because filtered output hides failures. Denies with the reason: "Run checks unfiltered".

- Check commands:
  - the commands in `loom.json` → `checks` (a `null` check is skipped). Only the first stage of each pipeline in a configured check is a check command, so a filter stage of a configured check is not one. Setup steps chained before a check are not check commands either: `cd`, `export`, `npm ci`, `npm install`, `pnpm install`, `yarn install`, `bun install`, `uv sync`, `pip install`, `poetry install`, `bundle install`, `go mod …`, `cargo fetch`, `composer install`;
  - `make lint|typecheck|test|check`, `pytest`, `ruff`, `pyright`, `mypy`;
  - `npm|pnpm|yarn|bun test`, `npm|pnpm|yarn|bun run test|lint|typecheck`, `pnpm|yarn lint|typecheck`;
  - any of these behind `uv run`, `python -m`, or a wrapper (`timeout`, `nice`, `env`, `time`, …).
- A group counts as a check when it contains one: `(make check) | tail`, `{ make check; } 2>&1 | tail`. So does a shell that runs one: `bash -c 'make check' | head`. Checks inside `$( … )`, also inside double quotes, are found too.
- Filters: `head`, `tail`, `grep`, `rg`, `wc`, `sed`, `awk`, `cut`, `less`, `more`. `| tee <file>` is allowed.
- Exemptions:
  - A command that equals a configured `checks.*` command, after whitespace normalization, runs as configured, also when it has a filter (§9.0). Example: `checks.test = "go test ./... | grep -v 'no test files'"`.
  - Commands that run no check: `--version`, `--help`, `-h`; `make -n`/`--dry-run`/`--just-print`/`--recon`; `pytest --collect-only`/`--co`; `command -v|-V`, `which`, `type`.

Known limits:
- A check inside a loop is not caught when the loop's output is piped (`for i in 1; do pytest; done | tail`).
- Output sent to a filter through a process substitution (`pytest > >(tail)`).

### 11.4 `SubagentStop` — enforce checks for the implementer

- Matcher: `^loom:implementer$`. Plugin agents report the plugin-scoped `agent_type` (`loom:implementer`); the colon puts the matcher on the regex path, so it is anchored. The script checks `agent_type` again.
- Runs `checks.check` at the git top level, with a 540-second timeout (the hook `timeout` in `hooks.json` is 600 seconds, enough for a real `make check`). On failure or timeout, exits with code 2: the subagent cannot finish and receives the tail of the output on stderr.
- Counts failed attempts in a small file per subagent run, in `<tempdir>/loom-subagent-checks/` (`$TMPDIR`), keyed by a hash of `session_id` and `agent_id`. A pass deletes the file.
- After `hooks.maxCheckAttempts` failures in a row (default 3) it exits 0, so the subagent can stop, with a `systemMessage` for the user; `implement` runs the checks again and records `blocked`.
- The counter is always read, also when `stop_hook_active` is `false`; a counter file older than one hour is stale (an interrupted run) and counts as 0. The counter ends the loop: Claude Code's own cap of 8 consecutive stop-hook continuations resets on every tool call. `stop_hook_active` (`true` while the subagent continues because a stop hook blocked it) is recorded in the counter file for debugging only.
- A damaged counter file (not JSON, not UTF-8) counts as 0. If the counter file cannot be read or written (permissions, a full disk), the hook still blocks a failing check while `stop_hook_active` is `false`; stderr says "attempt counter not available: …; you get one retry". While `stop_hook_active` is `true`, it exits 0 with a `systemMessage`, so the loop ends after one retry: "loom: `<check>` failed (exit N) for the implementer again, and the attempt counter is not available (…). The implementer may stop now; /loom:implement records the implementation phase as blocked."
- A `.claude/loom.json` that exists but cannot be read as a JSON object (invalid JSON, an empty file, not an object) does not block. The hook exits 0 with a `systemMessage`: "loom: the implementer checks did not run: <the loom-state warning>. Fix .claude/loom.json; /loom:implement still runs the checks itself before it commits."
- With a readable config, the failure text the implementer receives ends with the `loom-state` config warnings, if any ("Warnings about .claude/loom.json (loom-state):", one `- <warning>` line each), before the output tail.
- No `.claude/loom.json`, or another agent: silent no-op.
- A second `SubagentStop` entry (§11.6, matcher `^loom:`) also matches the implementer. Matching hooks run in parallel; the events hook only appends a line and does not change this hook's exit code.

### 11.5 `Stop` — quick lint (optional)

- Enabled by `hooks.stopLint` (default `false`).
- Runs only if the working tree has code changes (not only `.loom/`, `workDir`, or the docs paths of §8.2: `docsDir` and every path of the docs map).
- Runs `checks.lint` (270-second timeout; hook `timeout` 300 seconds). Without a lint command (`checks.lint` is `null`) it does nothing. On failure exits 2 so Claude sees the output; respects `stop_hook_active` to avoid loops: while it is `true`, the hook does nothing, so each stop gets at most one lint block.
- Does nothing in plan mode (`permission_mode` is `"plan"`). Also does nothing while the Stop input lists background work in flight: `background_tasks` has an entry whose `status` is not a finished status (`completed`, `done`, `failed`, `killed`, `stopped`, `cancelled`, `canceled`, `error`). An example is a background implementer that is still writing code. The Claude Code hooks docs (Stop input) describe `background_tasks` as the in-flight tasks, empty when nothing is in flight. They do not list the status values.
- Known limit: the hook cannot tell who changed the working tree, so uncommitted changes the user made by hand are linted too.

---

### 11.6 `SubagentStart` / `SubagentStop` — subagent events (v1.1)

A *subagent run* is one execution of a loom agent, identified by its `session_id` and `agent_id` (as in §11.4). `subagent_events.py` records every run of the current task in `<task dir>/events.jsonl`; `loom-state` aggregates the file into `task.metrics` (§8.2), and `describe-pr` copies its line into the task summary (§13.4).

- Matcher: `^loom:` on both events, so only loom's own agents count (plugin-scoped `agent_type`, e.g. `loom:codebase-locator`). The script checks the `loom:` prefix again. Hook `timeout`: 10 seconds.
- `SubagentStart` appends a `start` line. Each `SubagentStop` appends a `stop` line. `SubagentStop` fires again each time a stop hook keeps the implementer running (§11.4), so one run can have several `stop` lines; `stop_hook_active` tells them apart. `SubagentStart` also fires when Claude Code resumes a subagent, so one run can have several segments, each opened by a `start` line.
- The task directory is found as in `loom-state` (§8.3), also during a stopped rebase of the task branch. On the main branch, on a branch without a task directory, for an archived task, outside a git repository, and without `.claude/loom.json`, the hook does nothing. It reads only files and the branch: no `git status`, no stale check.
- Each line is one `O_APPEND` write, so parallel hooks never mix lines. A cut last line gets a newline first, so it stays one malformed line.
- The hook never blocks or fails a subagent: exit 0 always, no stdout. On an unexpected error it writes a short message to stderr (the rule of §11).
- The file is in the ignored task directory, so it is never committed. `finish-task` archives it with the task directory (§9.11).

Line format (one compact JSON object per line, keys in this order):

```json
{"event":"start","ts":"2026-11-11T12:34:56.789Z","session_id":"5f0c…","agent_id":"a1b2c3","agent":"implementer","phase":"implement","implementation_phase":2}
{"event":"stop","ts":"2026-11-11T12:41:02.120Z","session_id":"5f0c…","agent_id":"a1b2c3","agent":"implementer","phase":"implement","implementation_phase":2,"result":"pass","stop_hook_active":false,"duration_s":365.3}
```

- `ts`: UTC, ISO 8601 with milliseconds.
- `session_id`: from the hook input; `null` when the input has none.
- `agent`: `agent_type` without `loom:`.
- `phase`: the task phase by the rule below, at the time of the event. `implementation_phase` is present only for `implement`.
- `result` (`stop` only), parsed from `last_assistant_message`:
  - `implementation-reviewer`: the verdict line of §10.2. Near-miss wording counts too: `pass.`, `pass (with nits)`, `Changes needed`, bold forms, and the verdict alone on the line after a `## Verdict` or `**Verdict:**` heading. Result: `pass`, `changes-needed`, or `unknown`. Two different verdicts, `passed`, or extra words after the verdict give `unknown`.
  - `implementer`: the line of its Checks section (`### Checks`, `### Checks:`, `**Checks**`, `**Checks:**`) whose backticked command is `checks.check` from `.claude/loom.json` (default `make check`). Accepted forms include `` `make check`: pass (42 passed) ``, `passed`/`failed`, and a dash instead of the colon (`` `make check` - pass ``). Result: `pass`, `fail`, or `unknown`.
  - every other agent: `done`.
  - The parser takes the report text, so another source of the report can be added later (for example the `SubagentHandback` tool input, §24.1).
- `duration_s` (`stop` only): seconds since the latest `start` line of the same run (same `session_id` and `agent_id`) in the file, so it covers the current segment; one decimal; `null` without a `start` line.

Task phase (`task_phase()` in `loom-state`). The first matching rule wins:

1. An implementation phase is in progress: `implement`, that implementation phase.
2. Implementation started (an implementation phase is not `pending`, also a blocked one), the mode is not oneshot, and a gate artifact of the mode is `draft` or `in-review`: the first such gate (`design` in full mode, then `plan`). This is a design or plan change, which `/loom:iterate` handles (§9.12 rows 4, 6, and 7).
3. An implementation phase is blocked: `implement`, that implementation phase.
4. Implementation started: `implement`, the first implementation phase that is not done. All done: `iterate`.
5. oneshot: `implement`, implementation phase 1.
6. An artifact of the mode's phases is `draft`: the latest such phase. For example, research writes `draft` before its claim check (§9.5).
7. A gate artifact is `in-review`: the first such gate (agents during a question round).
8. The phase after the latest existing artifact of the mode. After the plan: `implement`, the first implementation phase that is not done.

An invalid mode gives `null`. The mode and the artifact statuses are normalized as in §8.2, and an artifact's phase is its file name. `iterate` covers all work after the last implementation phase: fixes before the PR and the post-PR fix path. `implement` writes `in-progress` into `log.md` before it launches the implementer, so implement-time agents get rule 1. Known limit: `/loom:iterate <feedback>` on research questions or research, and a research rerun over a finished research, count as the next phase.

## 12. Question Rounds Protocol

Used by `design` and `plan`. `iterate` processes the answers. Full text lives in `_shared/question-rounds.md`.

### 12.1 Independence rule

A round contains only questions whose answers do not depend on another open question. Dependent questions are deferred to the next round.

### 12.2 Format

```markdown
## Open Questions — Round 1 of ~3

**Q1. Where should agent state be persisted between runs?**
- a) SQLite — recommended: already a dependency, no infrastructure
- b) Redis
- c) JSON files

**Q2. …**
```

- Every question has 2–4 options and one recommended option with a one-line reason.
- Questions are numbered across rounds (round 2 starts after the last number of round 1).

### 12.3 Answering

- Compact answers: `1a, 2b, 3: custom answer …`
- Bulk: `accept all except 2`.
- Empty `/loom:iterate` or `ok`: accept all recommendations of the current round.
- Interactive buttons: the skill may ask through the interactive question tool in batches of up to 4 questions. The artifact remains the source of truth.

### 12.4 After each round

1. Answers move to **Resolved Decisions**: question, decision, rationale, round, `ADR?`.
2. Sections affected by the answers are rewritten.
3. The next round contains only questions unlocked by the answers.

### 12.5 How many rounds

Rounds end when no open question affects the plan, not at a fixed count.

| Size | Expected rounds | Cap |
|---|---|---|
| S | 1–2 | 2 |
| M | 2–3 | 3 |
| L | 3–5 | 5 |

The size comes from the ticket frontmatter `size` (copied from the `size:*` label); without it, the size matching the mode applies (quick → M, full → L). Caps come from `loom.json` → `rounds.cap`; skills read the resolved `rounds.cap` from the state (§8.2).

After the cap, the remaining minor questions are resolved with the recommendation and marked **"accepted by default — revisit if needed"**. `loom-state` reports their count.

---

## 13. Artifacts

### 13.1 Frontmatter and gates

```yaml
---
task: 42-auth-flow
phase: design            # ticket | research-questions | research | design | plan
status: in-review        # draft | in-review | approved   (not used on the ticket)
based_on: [02-research.md]
git_commit: a1b2c3d      # research only: code state the artifact describes
updated: 2026-11-08
---
```

The ticket frontmatter has instead: `mode`, `size` (`S`|`M`|`L`, optional, copied from the `size:*` label by start-task), `issue`, `url`, `pr` (after describe-pr). The ticket has no `status`, `based_on`, `git_commit`, or `updated`.

| Artifact | Statuses | Set by | Gate for |
|---|---|---|---|
| `00-ticket.md` | — | start-task | — |
| `01-research-questions.md` | draft → in-review → approved | skill / iterate | none |
| `02-research.md` | draft → in-review → approved | skill / iterate | none (warning only) |
| `03-design.md` | draft → in-review → approved | skill / iterate | plan |
| `04-plan.md` | draft → in-review → approved | skill / iterate | implement |
| `log.md` | per phase: in-progress / done / blocked | implement | — |

A skill writes `draft` while it works and `in-review` when it finishes. `iterate` also writes `draft` on `04-plan.md` while it changes the plan after implementation started. Only `iterate approve` sets `approved`. `loom-state` reads `status` and the ticket's `mode` ignoring case and surrounding whitespace. Another `status` value adds a warning and counts as `in-review`; there is no `blocked` artifact status. The file name, not `phase`, decides an artifact's phase; a different `phase` adds a warning. The ticket's `pr` may be written `57` or `#57`; it is a number of at least 1.

**Planned (M9, §9.13.2):** one exception. `setup` writes the fixed `01-research-questions.md` of the onboarding task as `approved`: the user approves the list with the confirmation of the setup plan.

### 13.2 Working artifacts (`.loom/tasks/<n>-<slug>/`)

**`00-ticket.md`** — copy of the issue: title, body, labels, URL; the `size:*` label is also stored as frontmatter `size`. Not edited by agents except frontmatter (`mode`, `pr`).

**`01-research-questions.md`** (full)
```markdown
## Key Context Pointers      ← links, paths, packages from the ticket, verbatim
## Questions                 ← 2–8, descriptive only
```

**`02-research.md`**
```markdown
## Summary
## Findings                  ← one section per question, every claim with file:line
## Patterns & Conventions
## External Sources
## Not Found / Unclear       ← includes claims that failed the claim check
```

**`03-design.md`** (full)
```markdown
## Current State
## Desired End State
## Out of Scope
## Proposed Architecture
## Open Questions — Round N of ~M
## Resolved Decisions
   | # | Question | Decision | Rationale | Round | ADR? |
## Testing Approach
```

**`04-plan.md`**
```markdown
## Phase Overview
   - [ ] 1. Fixed-response endpoint, verifiable via curl
   - [ ] 2. Wire to real storage
## Open Questions — Round N
## Resolved Decisions
   | # | Question | Decision | Rationale | Round | ADR? |
## Phase 1: <name>
   ### Goal
   ### Changes
   ### Verification
       - [ ] Automated: make test
       - [ ] Manual: (only if it cannot be automated)
## Phase 2: …
```

**`events.jsonl`** — not an artifact: one JSON line per subagent event, written by the hook of §11.6 and read by `loom-state` for `task.metrics`. Skills never write it.

**`log.md`** — machine-readable headings, parsed by `loom-state`:
```markdown
## Phase 1 — done — d4e5f6
Checks: lint ✓ typecheck ✓ test ✓ (42 passed)
Reviewer: pass
Deviations: switched from X to Y because …

## Phase 2 — blocked
Reason: …
```

### 13.3 Visual conventions

In `_shared/visual-conventions.md`: proper tree glyphs (`├──`, `└──`, `│`), unchanged paths omitted; `diff` blocks for changes to existing shapes (`+` added, `-` removed, `~` changed); plain language blocks for new shapes; short prose between visuals; only visuals that help a decision.

### 13.4 Task summary — `docs/tasks/<n>-<slug>.md` (quick, full)

The directory is `docs.tasks` of the docs map (§15); the default is shown.

```markdown
# #42 Auth flow
## Problem
## Outcome
## Key Decisions        ← links to ADRs
## Implementation       ← phases → commit subjects (hashes change on rebase and squash merge);
                           then "Process metrics: <task.metrics.line>" (§8.2), only when task.metrics is not null
## Deviations from Plan
## Verification
## Follow-ups
```

### 13.5 ADR — `docs/architecture/decisions/NNNN-<slug>.md`

Created from resolved decisions marked `ADR? = yes` (architecture level: storage, protocols, agent structure, major libraries). The directory is `docs.decisions.dir` and the file name follows `docs.decisions.pattern` of the docs map (§15); the default is shown. `NNNN` in the title is the number of the file name, with its digits.

```markdown
# NNNN. Use SQLite for agent state
Status: Accepted · Task: #42 · Date: 2026-11-08
## Context
## Decision
## Alternatives Considered
## Consequences
```

### 13.6 PR body

```markdown
Closes #42

## Why                       ← exactly one sentence: the problem or need this PR answers
## Special things to note    ← 1–3 items, or the single line None.
## Change outline            ← phases → commit subjects, then a file tree or an interface `diff` block
## Verification
## Decisions                 ← links to ADRs and the task summary

<details><summary>Implementation plan</summary>

…04-plan.md…

</details>
```

- **Why** is one sentence of at most 25 words (§14.1 rule 3), on one line, not a list of what changed.
- **Special things to note** lists only what a reviewer must know and cannot see quickly in the diff: a deviation or addition from `log.md`, a risk, a non-obvious decision, a migration or manual step, a known limit. Most important first. If nothing qualifies, the section is the single line None. (no filler, §14.1 rule 6).
- **Change outline** has one line per implementation phase (`1. <phase name> — <commit subject>`), then a file tree of the changed files or an interface `diff` block (signatures and public API only), whichever shows the shape of the change better (§13.3). Unchanged parts are omitted.
- If the body would exceed 60,000 characters (GitHub limit: 65,536), the plan is replaced by its Phase Overview plus a note.
- oneshot PRs contain only `Closes`, Why, and Verification.
- **Required sections:** `pullRequest.requiredSections` (§19.1) lists the headings that the project's PR template or a CI check requires, e.g. `## Test plan`. A required heading that the layout above already has (the same heading line) is that section. Every other required heading comes after Decisions (oneshot: after Verification), before `<details>`, in the order of the list. `describe-pr` fills it from the task's artifacts, or writes `None.` when nothing applies. `_shared/pr-update.md` keeps these sections when it rewrites the body, and its check for the layout before v1.1 ignores them.

---

## 14. Writing Style

loom uses an **STE-lite** style, inspired by ASD-STE100, defined in `_shared/writing-style.md`.

### 14.1 Rules

1. One term, one meaning. Use the glossary (§3). Do not rotate synonyms.
2. Active voice.
3. Sentences of at most 20 words for instructions and 25 for descriptions.
4. One instruction per sentence.
5. Lists for 3 or more steps or conditions.
6. No introductions, recaps of the request, or filler.
7. Keep every condition, number, and scope qualifier, even if the sentence gets longer.
8. Define a project-specific term once.

### 14.2 Where it applies

| Text | Applies |
|---|---|
| research, plan, log, PR, ADR, `docs/` | Yes |
| Final messages of skills | Yes, strictly |
| Skill and agent prompts | Rule 1 always; others where they do not remove nuance |
| Design rationale | Rules 1, 2, 6, 7 |
| The vision document, `backlog` discussion | No |

---

## 15. Project Documentation Structure

```
CLAUDE.md                        # short: what the project is, commands, links into docs/
docs/
├── product/
│   └── vision.md                # what, for whom, non-goals
├── architecture/
│   ├── overview.md              # components, data flow, diagram
│   └── decisions/
│       └── NNNN-*.md            # ADRs
├── conventions.md               # code style, testing rules, module layout
└── tasks/
    └── <n>-<slug>.md            # task summaries
```

- `CLAUDE.md` stays short because it loads into every session.
- `conventions.md` holds project-specific rules (e.g. how LLM calls are tested). `plan`, the implementer, and the reviewer read it.
- `overview.md` is updated in the same PR as the change that affects it.
- ADRs come from design decisions.

**Docs roles and the docs map.** The tree above is the default layout. An existing project can keep its own structure: `loom.json` → `docs` (§19.1) maps each docs role to a path, and `loom-state --json` reports the resolved paths (§8.2).

| Role | Default path | Read by | Written by |
|---|---|---|---|
| `vision` | `<docsDir>/product/vision.md` | backlog | setup (skeleton), backlog |
| `overview` | `<docsDir>/architecture/overview.md` | backlog, design, plan, describe-pr | setup (skeleton), describe-pr (update) |
| `decisions` | directory `<docsDir>/architecture/decisions`, file name pattern `<NNNN>-<slug>.md` | design, describe-pr | setup (skeleton), describe-pr |
| `conventions` | `<docsDir>/conventions.md` | design, plan, implementer, implementation-reviewer | setup (skeleton) |
| `tasks` | `<docsDir>/tasks` (files `<n>-<slug>.md`) | backlog, `_shared/pr-update.md` | setup (skeleton), describe-pr, `_shared/pr-update.md` |

- `CLAUDE.md` is not a docs role. It stays at the git top level.
- Every skill that names a doc path takes it from `docs` in the state: `setup` (it writes the skeleton by docs role), `backlog`, `design`, `plan`, `implement` and `iterate` (they pass `docs.conventions` to the implementer and the reviewer), `describe-pr` with its templates, and `_shared/pr-update.md`. No skill builds a role path from `docsDir`, and no skill reads `docs` from `loom.json`; `tests/test_skills.py` checks both. Before `.claude/loom.json` exists, `setup` uses the default paths of its skeleton templates.
- `docsDir` stays for compatibility. It is the root of the default paths, and changes below it still count as docs changes (§8.2). A path in the map may lie outside `docsDir`, e.g. `ARCHITECTURE.md` or `adr/`.
- loom writes its own ADR layout (§13.5) also in a mapped directory. Only the file name follows the project's pattern. The `NNNN` in the ADR title is the number of the file name, with the digit count of the pattern.
- The task summary file name stays `<n>-<slug>.md`.

---

## 16. Git Conventions

### 16.1 Branches

- Format: `<type>/<issue>-<slug>`, e.g. `feat/42-auth-flow`.
- `type`: `feat`, `fix`, `chore`, `docs`, `refactor` (from the `type:*` label).
- Created from an up-to-date main branch, with a clean working tree.
- Docs and code live in the **same branch**.

### 16.2 Commits

- Conventional Commits with the issue number: `feat(auth): add token storage (#42)`.
- One commit per implementation phase, created by `implement` (never by the implementer agent).
- Docs commit before the PR, only if docs changed: `docs(#42): record decisions and summary`.
- No commits during research/design/plan (those artifacts are in `.loom/`).
- **Planned (M9, §9.13.2):** the onboarding kickoff commit `chore(loom): start loom setup (#<n>)` comes before research. It holds only `.claude/loom.json` and the `.gitignore` line, and its body has no `Phase` line.

### 16.3 Rebase and merge

- Before push and before merge, the branch is rebased on `origin/<mainBranch>`. After a rebase of an already pushed branch, push uses `--force-with-lease`.
- **Squash merge:** the main branch stays linear, one commit per task; implementation-phase commits stay visible in the PR.
- `gh pr merge --squash --delete-branch --subject '<PR title>'` deletes the local and remote branch and keeps the PR title (Conventional Commits, ending with `(#<n>)`) as the squash commit subject. The repo setting "Automatically delete head branches" is also recommended. A deleted branch can be restored from the PR page.

### 16.4 What needs user confirmation

| Action | Confirmation |
|---|---|
| Local commits, rebase, `git branch -D` of a merged task branch | No |
| `git push` (including `--force-with-lease` on a task branch) | Yes |
| `gh pr create`, `gh pr edit`, `gh pr merge` | Yes |
| `gh issue create` | Yes |
| Repo settings, labels, ruleset (`gh api`, `gh label create`) | Yes |
| Read-only `gh api` GET (e.g. listing rulesets, reading inline PR review comments) | No question from the skill; the permission system always asks (the `Bash(gh api *)` ask rule of §19.3), also in auto mode, by intent |
| `git stash`, discarding changes | Yes. A stash runs `git check-ignore -q <task dir>` first: an ignored task directory takes the plain `git stash push --include-untracked` (a pathspec with an ignored path makes `git stash` exit 1 and leave the changes staged); otherwise the `':(exclude)<task dir>'` pathspec. |

Commit messages are written to `<task dir>/commit-msg.txt` and committed with `git commit -F`; one-line titles (`gh pr create --title`, `gh pr merge --subject`) are single-quoted with every `'` written as `'\''`. Double quotes would expand backticks and `$` from plan headings (`_shared/git-flow.md`).

### 16.5 Protection

- `PreToolUse` guard (§11.2): it blocks `git commit` on the main branch and every `git push` that can update the main branch. Other git commands on the main branch (`merge`, `reset`, …) are out of its scope.
- GitHub ruleset on the main branch (§17.3).
- `finish-task` enforces `ci.requiredCheck` by name when GitHub requires no check (§9.11).

---

## 17. Checks and CI

### 17.1 Single entry point

Checks run in four places — the implementer, the `SubagentStop` hook, the optional `Stop` hook, and CI — and must never diverge. The rule: CI runs `checks.check` exactly as configured, and it may run CI-only steps in addition (for example e2e tests or checks that need services). `setup` writes the CI workflow, or reuses an existing one after the user confirms it. **Planned (M9, §9.13.4):** `setup` checks that the workflow runs `checks.check`; on onboarding, the design verifies the existing workflow. The implementer and the hooks never run CI-only steps; the implementer may run narrower commands for fast feedback. The project exposes them through one entry point (Python: `Makefile`):

```makefile
lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run pyright

test:
	uv run pytest || [ $$? -eq 5 ]

check: lint typecheck test
```

`loom.json` references these targets; CI runs `make check`. Recipe lines start with a tab. `pytest` exits with 5 when it collects no tests; a new project has none, so the `test` target accepts exit status 5 and no other failure. Node projects use the `lint`, `typecheck`, `test`, and `check` scripts of `package.json` instead (`setup/references/stacks/node.md`).

`checks.lint`, `checks.typecheck`, and `checks.test` may be `null` when the project has no such check (§19.1). `checks.check` is always a command. The hooks, the plan, and the implementer skip a `null` check. A configured check may chain setup steps or end in a pipe: everyone runs it exactly as configured, the output filtering hook allows it (§11.3), and `loom-state` warns when the pipe goes into an output filter (§19.1).

**Planned (M9, §9.13.4):**
- `checks.check` is the fast set. It must pass on the main branch and finish within the `SubagentStop` timeout (540 seconds, §11.4). The onboarding design chooses it and the CI-only steps.
- The `conventions` document lists each CI-only step: what it runs, why it is CI-only, and how to run it locally. `loom.json` does not record CI-only steps: loom never runs them.

### 17.2 CI workflow (v1)

`.github/workflows/ci.yml`, on `pull_request` and `push` to the main branch. One job named `check` (the ruleset requires this name: the default of `ci.requiredCheck`). A workflow that `setup` reuses keeps its job names: `setup` writes the check name of the job that runs the checks into `ci.requiredCheck` (§9.1). The template's job:

| Step | Python example | Catches |
|---|---|---|
| Install | `uv sync --locked` (cached) | lock file out of sync |
| Lint | `ruff check` | bugs, unused imports |
| Format | `ruff format --check` | unformatted code |
| Types | `pyright` | type errors |
| Tests | `pytest` | broken logic |

CI runs the steps through the single entry point (`make check`, or the `check` script for Node), so CI and the hooks never diverge. Single Python version. Action versions are pinned to exact release tags when `setup` generates the file: `actions/checkout@v7.0.1`, `astral-sh/setup-uv@v10.3.3` (it publishes no major tag), `actions/setup-node@v7.1.0`, `pnpm/action-setup@v6.1.1`, `oven-sh/setup-bun@v2.2.0` (latest releases, checked on 2026-11-09). The workflow sets `permissions: contents: read`.

**Planned (M9, §9.13.4):** on an onboarding task the required check can be an existing CI job. The design changes that job to run `checks.check` exactly (its CI-only steps stay) and records its check name in `ci.requiredCheck`. The name is the one GitHub reports: the job `name`, with a matrix suffix if any. The design adds a job named `check` only when no job fits. It never renames a job: branch protection may require the old name.

### 17.3 Ruleset

Offered by `finish-task` after the setup PR is merged, created with `gh api` after confirmation:
- Merge to the main branch only through a PR.
- Required status check: the check named in `ci.requiredCheck` (§19.1, default `check`), from the state.
- Required approvals: **0** (a solo developer cannot approve their own PR).
- Block force pushes and deletion.

Before the offer, `finish-task` reads the rules of the main branch (`gh api repos/{owner}/{repo}/rules/branches/<main>`) and its classic branch protection: `gh api repos/{owner}/{repo}/branches/<main>/protection`. Both are read-only GETs (the `Bash(gh api *)` ask rule prompts; for the protection, a 404 means none). A 403 (a private repository on GitHub Free, or no admin access) means unknown: `finish-task` still offers the ruleset, and the POST reports whether rulesets are available. It skips the offer when a ruleset or the classic protection already requires `ci.requiredCheck`. Otherwise it offers the ruleset as above.

Availability (verified, §24.2): rulesets work on public repositories on GitHub Free; private repositories need GitHub Pro, Team, or Enterprise Cloud. If unavailable, loom relies on the guard hook, and on `finish-task`: without a ruleset or branch protection GitHub requires no check, so `finish-task` waits for the check named `ci.requiredCheck` and refuses the merge while it fails (§9.11 step 3).

Project-specific testing strategy (e.g. recorded LLM responses, evals of the product) is **not** part of loom. It belongs in the project's `conventions.md`.

---

## 18. Stack Detection

Only `setup` knows about stacks.

```
                    ┌─ references/stacks/python-uv.md
setup ── detects ───┼─ references/stacks/node.md
   stack            └─ (unknown → investigate and ask the user)
   │
   ▼
.claude/loom.json  → checks: { lint, typecheck, test, check }   (same shape for every stack)
   │
   ▼
everything else — stack-agnostic
```

1. **Marker files:** `pyproject.toml` + `uv.lock` → uv; `package.json` + lock file → npm/pnpm/bun; `go.mod` → Go; `Cargo.toml` → Rust.
2. **Prefer what exists:** an existing `Makefile`, `package.json` scripts, or CI workflow is reused.
3. **Idiomatic entry point:** Python → `Makefile`; Node → `package.json` scripts.
4. **Idempotent:** re-running shows a diff.

v1 ships recipes for **python-uv** and **node**. Adding a stack means adding one recipe file. Monorepos with several stacks are out of scope for v1.

**Planned (M9, §9.13.4 topic 5): several stacks.**
- Only the onboarding path handles several stacks. The fast path on an empty repository has at most one stack, so its recipes do not change.
- A repository with several stacks is supported when one root command runs all checks, e.g. a root `Makefile` whose `check` target runs a Python backend and a Node frontend. `checks.*` name the root commands.
- If each stack has its own check commands and no root command exists, the setup PR adds a root entry point that only calls them (a gap of §9.13.6).
- Out of scope: a monorepo without a common root check command, and checks that run per package (only the changed packages) (§23.3).

---

## 19. Configuration

### 19.1 `.claude/loom.json` (committed)

```json
{
  "version": 1,
  "tracker": "github",
  "mainBranch": "main",
  "workDir": ".loom/tasks",
  "docsDir": "docs",
  "checks": {
    "lint": "make lint",
    "typecheck": "make typecheck",
    "test": "make test",
    "check": "make check"
  },
  "hooks": {
    "stopLint": false,
    "maxCheckAttempts": 3
  },
  "rounds": {
    "cap": { "S": 2, "M": 3, "L": 5 }
  },
  "implement": {
    "maxFixAttempts": 2,
    "autoAdvance": true
  }
}
```

Every component takes `mainBranch`, `workDir`, and `docsDir` from this file, directly or through `loom-state` (skills take `mainBranch`, `workDir`, the doc paths from `docs`, and `rounds`, `implement`, and `hooks` from the state, §8.2). None of them hard-codes `main` or `.loom/tasks`. No skill, shared snippet, or agent reads these values from `.claude/loom.json`; `tests/test_skills.py` checks it. The only exception is `setup` while `.claude/loom.json` does not exist yet: the state is empty then, so it takes the template defaults and GitHub's default branch (§9.1).

**Optional keys.** The template above does not list them: a missing key takes its default, so a project that omits them keeps the behavior of release 1.1.0. **Planned (M9, §9.13.5):** the onboarding task writes the keys it needs. Example of these keys with non-default values:

```json
{
  "docs": {
    "vision": "README.md",
    "overview": "ARCHITECTURE.md",
    "decisions": { "dir": "docs/adr", "pattern": "ADR-<NNN>-<slug>.md" },
    "conventions": "CONTRIBUTING.md",
    "tasks": "docs/loom-tasks"
  },
  "ci": { "requiredCheck": "test (3.12)" },
  "pullRequest": { "requiredSections": ["## Test plan"] },
  "checks": { "lint": "make lint", "typecheck": null, "test": "make test", "check": "make check" }
}
```

| Key | Default | Rule | Invalid value |
|---|---|---|---|
| `mainBranch` | `"main"` | A branch name; surrounding whitespace is stripped; no control characters | Warning, the default |
| `workDir` | `".loom/tasks"` | A relative directory path: not empty, not absolute, not `.`, no `..` segment, no control characters, not at or below `.git/` or `.claude/` (compared ignoring case); surrounding whitespace is stripped and the path is normalized | Warning, the default |
| `docsDir` | `"docs"` | A relative directory path by the rules of `docs.tasks` (also not at or below `.loom/` or `workDir`) | Warning, the default |
| `docs` | every role at its §15 default below `docsDir` | An object. Each key is optional. An unknown key gets a warning and is ignored. | Not an object (also `null`): warning, all defaults |
| `docs.vision`, `docs.overview`, `docs.conventions` | §15 | A relative path to a `.md` file (`.md` in any case): not empty, not absolute, not `.` or the git top level, no `..` segment, no control characters (newline, tab, NUL, …), not at or below `workDir`, `.git/`, `.claude/`, or `.loom/` (compared ignoring case); surrounding whitespace is stripped | Warning, the default of that role |
| `docs.tasks` | `<docsDir>/tasks` | A relative directory path, by the same rules | Warning, the default |
| `docs.decisions` | `{ "dir": "<docsDir>/architecture/decisions", "pattern": "<NNNN>-<slug>.md" }` | An object. `dir`: a relative directory path, by the same rules. `pattern`: a file name (no `/`, no control characters) that ends in `.md` (any case), has `<slug>` once, and has one number placeholder `<N…N>` of 1–6 `N`. The placeholder's length is the digit count of the zero-padded number (`<NNN>` → `007`). A missing field takes its default. An unknown field gets a warning and is ignored. | Warning, the default of that field (not an object: both defaults) |
| `ci`, `pullRequest` | as below | An object. An unknown key gets a warning and is ignored. | Not an object (also `null`): warning, the defaults |
| `ci.requiredCheck` | `"check"` | The name of the CI check that runs `checks.check` (§17.2), as GitHub reports it; no control characters; surrounding whitespace is stripped | Warning, the default |
| `pullRequest.requiredSections` | `[]` | A list of heading lines, each `## <text>` or `### <text>` (§13.6), without control characters | Not a list: warning, the default. An invalid or repeated item: warning, the item is dropped |
| `checks.lint`, `checks.typecheck`, `checks.test` | as above | A command (a non-empty string), or `null` when the project has no such check. A `null` check is skipped: the `Stop` hook does nothing without `checks.lint`. A command that pipes its output into an output filter (`head`, `tail`, `grep`, `egrep`, `fgrep`, `sed`, `awk`, `gawk`, `nawk`, `cut`, `less`, `more`, `rg`, `wc`) gets a warning and stays as configured (§11.3) | An empty or blank string: warning ("use null"), `null`, as in release 1.1.0. Another value: warning, the default |
| `checks.check` | `"make check"` | A command (a non-empty string); never `null`. A command piped into an output filter gets a warning, as above | Warning, the default |
| `rounds`, `rounds.cap`, `implement`, `hooks` | as above | An object. A missing field takes its default. An unknown key gets a warning and is ignored. | Not an object (also `null`): warning, the defaults |
| `rounds.cap.S`, `rounds.cap.M`, `rounds.cap.L` | `2`, `3`, `5` | An integer of at least 1 (`true` and `false` are not numbers) | Warning, the default of that size |
| `implement.maxFixAttempts` | `2` | An integer of at least 0 | Warning, the default |
| `implement.autoAdvance` | `true` | `true` or `false` | Warning, the default |
| `hooks.stopLint` | `false` | `true` or `false` | Warning, the default |
| `hooks.maxCheckAttempts` | `3` | An integer of at least 1 | Warning, the default |
| any other top-level key | — | Not a `loom.json` key (the keys are `version`, `tracker`, `mainBranch`, `workDir`, `docsDir`, `docs`, `checks`, `ci`, `pullRequest`, `hooks`, `rounds`, `implement`) | Warning, ignored |

The resolved docs map is also checked as a whole; these warnings keep the values. `docs.tasks` and `docs.decisions.dir` must not be at or below each other (equal included), and no role file may lie at or below either directory. `vision`, `overview`, and `conventions` may share one file (one `README.md` can play several roles). A docs map path at or below `workDir` gets a warning (a configured path there is already invalid, so this is a default built from `docsDir`, e.g. `docsDir: "work"` with `workDir: "work/tasks"` makes `docs.tasks` `work/tasks`; it is the only default, so it stays). The file may start with a UTF-8 byte order mark.

`loom-state` validates these keys, reports problems in `warnings`, and outputs the resolved values as `workDir`, `docs`, `checks`, `ci`, `pullRequest`, `rounds`, `implement`, and `hooks` (§8.2). The hooks use the same resolved values. Skills read them from the state, never from the raw file. Agents get the values they need in their prompt (§9.9).

### 19.2 Issue labels

| Label | Values |
|---|---|
| `type:` | `feat`, `fix`, `chore`, `docs`, `refactor` |
| `size:` | `S`, `M`, `L` |
| `mode:` | `oneshot`, `quick`, `full` |

### 19.3 `.claude/settings.json` (committed, written by `setup`)

Template: `skills/setup/references/templates/settings.json`. `setup` merges it into an existing file: it adds missing keys and rules and never removes or replaces one.

- `extraKnownMarketplaces` + `enabledPlugins`: anyone who clones and trusts the project is offered loom: `"extraKnownMarketplaces": {"loom": {"source": {"source": "github", "repo": "mmosvlad1/loom"}}}` and `"enabledPlugins": {"loom@loom": true}`. Claude Code honors `extraKnownMarketplaces` from a project file only after the workspace trust dialog. A plugin that is enabled only in the project settings is not installed for a collaborator: it loads after each collaborator runs `claude plugin install loom@loom --scope project` once per clone. `/reload-plugins` loads it for one session only (§24.2).
- `statusLine` (optional; `setup` asks): `{"type": "command", "command": "python3 \"$(git rev-parse --show-toplevel 2>/dev/null)/.claude/loom-statusline.py\" 2>/dev/null"}`. A settings file cannot name the plugin directory, so the committed script `.claude/loom-statusline.py` finds the installed plugin (`installed_plugins.json`, then the `loom` marketplace, then the plugin cache below the plugins root) and runs its `bin/loom-state --line` in the session's directory (`workspace.current_dir` from the status line input). It prints nothing on any failure. `LOOM_PLUGIN_ROOT` overrides the lookup (for `--plugin-dir` development). A project `statusLine` replaces each collaborator's personal status line in this project.
- Rule syntax: `Bash(<command> *)`. A trailing ` *` also matches the bare command; the older `:*` suffix is equivalent.
- Permission allowlist (`permissions.allow`; routine, reversible):
  - `git status`, `git diff`, `git log`, `git add`, `git commit`, `git switch`, `git pull`, `git fetch`, `git rebase`, `git stash push`, `git stash list`, `git stash show`, `git stash pop`, `git branch` (stash `drop` and `clear` stay out: they lose work)
  - `make *` (or the stack's check commands)
  - `gh issue view`, `gh issue list`, `gh pr view`, `gh pr list`, `gh pr checks`, `gh run view`, `gh run list`, `gh label list`, `gh repo view` (read-only commands that skills run; Claude Code's built-in read-only set covers read-only `git`, not `gh`)
  - `loom-state --json`, `loom-state --json --pr` (the skills' `allowed-tools` grant lasts only one turn, §24.2; this keeps the `Next:` call from asking after the user answered a question), `loom-state --slug *`
  - `mv` inside `.loom/`: `mkdir -p <workDir>/_archive`, `mv <workDir>/* <workDir>/_archive/` (finish-task), `mv <workDir>/_archive/* <workDir>/` (start-task restore)
- **Not** allowlisted (always asked): `git push`, `gh pr create`, `gh pr edit`, `gh pr merge`, `gh issue create`, `gh label create`, `gh api`. `setup` writes them as `permissions.ask` rules, so a broader allow rule elsewhere (e.g. `Bash(git *)` in user settings) cannot skip the prompt.

---

## 20. Testing the Harness

### 20.1 Unit tests

`tests/` covers `loom-state` (task lookup, statuses, decision table, stale research, log parsing, task phase, process metrics) and the hook scripts (guard, output filtering, SubagentStop checks, Stop lint, subagent events) with fixture directories, plus spec-driven lints of skills, agents, shared snippets, and templates (§13.2, §13.4–§13.6), and of the release files (`plugin.json` version, `CHANGELOG.md`, §21). Runs in loom's CI.

### 20.2 Evals

`evals/` holds a suite for `claude plugin eval` (format: §24.2, milestone M6). One directory per case, with `case.yaml` and `graders/*.md`:

```
evals/
├── _fixture/build.py        # builds the fixture of one scenario in the run workspace
├── research-full/           # case.yaml (prompt: /loom:research), scaffold.sh, graders/
├── design-full/
├── implement-manual/
├── guard-main/
├── describe-pr-quick/
└── results/                 # written by the runs; ignored by git
```

- Each case's `scaffold.sh` runs `_fixture/build.py <scenario>`. It builds a tiny Python repository (`shop/`, stdlib `unittest` checks behind `make check`, the §19.1 `loom.json`, with the optional keys of `describe-pr-quick` below), one commit on `main` with fixed dates (stable hashes), and the task directory of task #7 with the artifacts the scenario needs. `tests/test_evals.py` runs every scaffold and checks that `loom-state` routes it to the case's skill.
- Graders never call a model (`regex`, `tool_used`, `file_exists` only):
  - `research-full` (full mode, research questions approved):
    - `02-research.md` exists with `status: in-review` and `file:line` references.
    - No Read of `00-ticket.md` (`tool_used`, max 0).
    - No Read, Grep, Glob, or Bash input in the trace names the ticket, by the skill or by a subagent.
    - The trace never holds `Wholesale customers`, a phrase that occurs only in the ticket body. This catches the ticket's content reaching the session by any tool.
    - The skill read its shared snippets.
    - `<task dir>/events.jsonl` exists and has a `start` line and a `stop` line of a research agent (`codebase-locator`, `codebase-analyzer`, `codebase-pattern-finder`, or `web-search-researcher`) with `"phase":"research"` (§11.6). Hooks run outside the eval sandbox, and `make eval` loads the plugin's `hooks/hooks.json`.
  - `design-full` (research approved):
    - `03-design.md` exists with `status: in-review`, a `## Open Questions — Round 1 of ~M` heading, and `**Q1.`.
    - Resolved Decisions has no table data rows and no list items.
    - No Read of `01-research-questions.md`.
  - `implement-manual` (quick mode, plan approved, implementation phase 1 has a `Manual:` line):
    - Exactly one `git commit` (also as `git -C <dir> commit`).
    - `log.md` has `## Phase 1 — done — <hash>` and no phase 2 entry.
    - The Phase Overview ticks phase 1 only.
    - The last message has `Manual verification:` and `run the manual steps, then /clear, then /loom:next` (the grader also accepts `step` for a single manual step).
    - `<task dir>/events.jsonl` has a `stop` line of `implementation-reviewer` with `"result":"pass"` or `"changes-needed"`, and a `stop` line of `implementer` with `"result":"pass"` or `"fail"` (§11.6). Each fails when `last_assistant_message` does not hold the agent's report (the result is then `unknown`).
  - `guard-main` (on `main`, staged change, no skill):
    - A Bash `git commit` ran.
    - The trace holds the guard's deny reason.
    - `main` still points to the fixture commit.
  - `describe-pr-quick` (quick mode, both implementation phases done and committed, no remote, no PR; its `loom.json` adds the non-default `docs.tasks` `notes/loom-tasks` and `pullRequest.requiredSections` `["## Test plan"]`, and keeps the default `docs.decisions`: the fixture has no decision with `ADR? = yes`):
    - `pr-body.md` exists, and its first line is `Closes #7`.
    - The task summary exists at the mapped path `notes/loom-tasks/7-bulk-discount-tiers.md` (`file_exists`).
    - The headings `## Why`, `## Special things to note`, `## Change outline`, `## Verification`, and `## Decisions` come in this order; no `## Summary` or `## Changes`.
    - Why is one sentence. Special things to note has 1–3 items or `None.`. Change outline has the phase lines `1.` and `2.`, then a file tree or a `diff` block.
    - The plan is attached in `<details>`.
    - The required section `## Test plan` comes after `## Decisions` and before `<details>`.
    - No Bash `git push` and no `gh pr create` (`tool_used`, max 0). The fixture has no remote, and `make eval` does not grant `gh`. The skill writes `pr-body.md` before it asks to push, and the run ends at that question.
    - The case needs `gh` installed (not authenticated): without it, `loom-state --pr` warns `gh is not installed`, and the skill stops before it writes the body.
    - Passed 4 of 4 local runs before M9a (haiku, macOS, Homebrew git, about 0.02 USD each); not run on the CI runner yet. In one run Bash denied a chained `cd …; ls …`, so the docs commit and the rebase did not happen; the body was still written. With the M9a fixture (mapped `docs.tasks`, required `## Test plan`) it passed 2 of 2 local runs (about 0.03 USD each), and 1 of 1 with the hardening after M9a (2026-11-12, §24.2).
- Every case has `runs: 1` and `model: haiku` (cost); `--runs 3` and `--model sonnet` override them.
- The full suite on the code of the hardening after M9a passed 5 of 5 cases (1 run each, haiku, macOS, Homebrew git, 0.32 USD in total, 2026-11-12, §24.2).
- `make eval` runs the suite with `--scaffold --ablation none --no-publish --trust-plugin`, a `--max-cost-usd` ceiling, and the narrowest `--allow-tools` set: `Write Edit 'Bash(git *)' 'Bash(make *)' 'Bash(loom-state *)' 'Bash(*/bin/loom-state *)'`. It is not part of `make check`. It puts the plugin's `bin/` on `PATH` (the eval runtime does not) and, on macOS only, the developer directory (`xcode-select -p`) first.
- In loom's CI: `make check` (unit tests and `claude plugin validate --strict`), then `make test` on Python 3.9, on every PR and push to `main` (`.github/workflows/ci.yml`, §21). The evals run only on demand (`.github/workflows/eval.yml`, `workflow_dispatch`, repository secret `ANTHROPIC_API_KEY`), never on a schedule: they cost tokens.
- `make eval` runs every case, locally and in the Evals workflow. The Evals workflow runs all 5 cases on a pinned `macos-26` runner. Linux cannot run the skill cases: the eval sandbox breaks every Bash call there (§24.2).
- macOS needs Homebrew git (`brew install git`) for `implement-manual` and `describe-pr-quick` (docs commit and rebase). Inside the eval sandbox Bash `git` is always the `/usr/bin/git` shim; without another git it fails, with the Command Line Tools and with full Xcode (§24.2). When the first `git` on the caller's `PATH` (`command -v git`) is `/usr/bin/git`, `make eval` prints a warning that names `brew install git` and still runs every case.

### 20.3 When to run

After every change to a skill, agent, shared snippet, or hook script. A prompt change is not done until its eval scenario passes: `make eval EVAL_ARGS='--case <name>'`. The Evals workflow runs every case.

---

## 21. Distribution and Development

- **Repository:** a public GitHub repository `loom` with `.claude-plugin/marketplace.json` and the plugin.
- **Install:**
  ```
  /plugin marketplace add mmosvlad1/loom
  /plugin install loom@loom
  ```
- **Versioning:** semver, **only in `plugin.json`**; bump on every release. Users update with `/plugin marketplace update`. `CHANGELOG.md` (Keep a Changelog) lists the changes of every version. `1.0.0` (milestones M1–M6) was never tagged; `1.1.0` is the first version in `plugin.json` after `0.1.0`.
- **Local development:** `claude --plugin-dir ./loom` runs the working copy; exercise it on a sandbox repository and with evals.
- **loom's own CI:** `.github/workflows/ci.yml` runs `make check` on every PR and push to `main`: unit tests (including the check that every `template.md` has its required headings) and `claude plugin validate --strict`, which needs no credentials. One job `check` without a matrix (a ruleset may require that name), `permissions: contents: read`, `actions/checkout@v7.0.1`, `actions/setup-node@v7.1.0`, and Claude Code pinned with `npm install -g @anthropic-ai/claude-code@2.1.318`. After `make check`, `actions/setup-python@v7.1.0` (latest release, published 2026-10-22, checked 2026-11-12) installs Python 3.9, and the next step runs `make test` with it: the Python 3.9+ promise of §4.1 is tested in CI, not only on the stock macOS `python3`. `.github/workflows/eval.yml` runs `make eval` on demand only (§20.2), on a pinned `macos-26` runner. It installs Claude Code 2.1.318 unless the `claude_version` input names another version. It keeps each run's `out/` directory (`--keep-temp`) and uploads `evals/results/` with `actions/upload-artifact@v7.0.2` (latest release, checked on 2026-11-10).
- **Commands** appear as `/loom:<skill>`; agents as `loom:<agent>`.

---

## 22. Differences from HumanLayer

| HumanLayer | loom | Why |
|---|---|---|
| Subagents registered by the daemon via SDK | `agents/*.md` in the plugin, namespaced `loom:` | Self-contained |
| `{SKILLBASE}` substituted by the daemon | Relative paths and `${CLAUDE_PLUGIN_ROOT}` | No daemon |
| Task directory injected by the daemon | `SessionStart` hook + `loom-state` | No daemon; one source of truth |
| `.humanlayer/tasks` synced to cloud | `.loom/tasks` local + distilled `docs/` committed | No cloud; visible process |
| Linear / Jira | GitHub Issues via `gh` | Free, next to the code |
| RPI, PRD-Oriented, Oneshot, Freeform | oneshot, quick, full | PRD/TDD split is overkill for solo work |
| Separate structure outline and plan | One plan with Phase Overview + details | One phase less |
| 9 `iterate-*` skills | One `iterate`, also for post-PR fixes | Less duplication, covers the PR loop |
| One-question-at-a-time checkpoints | Batched rounds with an independence rule and caps | Fewer interruptions |
| Every artifact reviewed before moving on | Gates only on design and plan | Fewer interruptions |
| Stop after every implementation phase | Auto-advance unless manual verification is needed | Fewer interruptions |
| Checks trusted from the agent's report | Enforced by a `SubagentStop` hook | Reliability |
| User remembers the next skill | `/loom:next` computes and runs it | Less friction |
| Artifacts gitignored | Working artifacts ignored, knowledge committed | Clean repo + visible process |
| "Only use when invoked by name" in description | `disable-model-invocation: true` | Enforced, saves context |
| — | `backlog`, `finish-task`, `setup` with CI and ruleset, evals | Full lifecycle, tested harness |

---

## 23. Roadmap and Out of Scope

### 23.1 v1.2 (planned)

- **Docs freshness gate:** `loom-state --docs` flags paths in `overview.md` and ADRs that no longer exist and modules added since the last summary; `describe-pr` asks to address them. It reads the documents through the docs map (§8.2).
- **Onboarding existing repositories (M9):** `setup` on a repository with code starts a `full`-mode setup task.
  - Research answers a fixed onboarding question list.
  - Design discusses the project with the user: drafts of vision and overview, project rules against loom rules, docs roles, gaps, checks, and the required CI check.
  - The normal plan, implement, describe-pr, and finish-task phases follow. Gaps outside loom's needs become follow-up issues.
  - Empty repositories keep the fast `oneshot` setup.
  - New `loom.json` keys let skills use an existing structure: a docs map, the required CI check, and required PR sections. Done in milestone M9a (not released yet, `CHANGELOG.md`).
  - Specified in §9.13, with the milestones M9a and M9b in §9.13.8.

Done in v1.1 (release 1.1.0, `CHANGELOG.md`):

- **PR layout:** "Why" in one sentence, 1–3 "Special things to note", and a "Change outline" (file tree or interface `diff`). Specified in §13.6, written by `describe-pr`, kept by `_shared/pr-update.md`, and covered by the `describe-pr-quick` eval case (§20.2).
- **Observability:** `SubagentStart`/`SubagentStop` hooks append a `start` line and a `stop` line per subagent run (agent, phase, duration, result) to `<task dir>/events.jsonl` (§11.6). `loom-state` aggregates them into `task.metrics` (§8.2), and `describe-pr` adds a "Process metrics" line to the task summary (§13.4). Covered by unit tests and the `research-full` eval case (§20.2).
- **One command per Bash call:** every skill reads `_shared/bash-calls.md`; the agents with Bash carry the rule inline (§9.0).
- **Inline PR review comments:** the post-PR fix path of `iterate` also reads review comments on code lines with a read-only `gh api` GET (§6.2).

### 23.2 Deferred, needs a separate discussion

None. Onboarding existing repositories moved to §23.1 (M9, §9.13). It migrates no existing branches or issues.

### 23.3 Out of scope

- Git worktrees and parallel tasks.
- Monorepos without one root check command, and checks per package (only the changed packages). Several stacks behind one root check command are planned for M9 onboarding (§18).
- Agents other than Claude Code.
- Linear / Jira.
- pre-commit hooks, Dependabot, coverage reports.
- Sync of `.loom/` between machines.

---

## 24. Open Topics and Items to Verify

### 24.1 Open topics

- Prompt quality review after the first real use of loom on a project (dogfooding).
- **Project formats that loom writes (M9):** for loom tasks, the formats that loom writes and parses win over the project's formats (§9.13.4 topic 2): the branch name `<type>/<n>-<slug>`, the commit subject `<type>(<scope>): <summary> (#<n>)`, the `Phase N:` commit body, `Closes #<n>` in the PR body, and the task summary file name `<n>-<slug>.md`. A project that enforces another format (a CI check on commit subjects, branch names that a ticket system needs) has no config key for it. Decide after onboarding a mature repository whether `loom.json` needs format keys.
- **Fast set over the hook timeout (M9):** `checks.check` must finish within 540 seconds (§17.1). A project whose fastest useful set takes longer has no answer yet: a longer hook timeout, or checks scoped to the changed files.
- **Subagent report source for process metrics:** `subagent_events.py` reads `last_assistant_message`. In the eval runtime on Claude Code 2.1.318 it holds the report (`implement-manual` passed 7 of 7 graders locally on 2026-11-12). The hooks docs say that a subagent with the `SubagentHandback` tool delivers its report through that tool, and `last_assistant_message` then holds only its closing text; the Claude desktop app does this. There `result` can be `unknown`. Decide after dogfooding whether a hook on `SubagentHandback` should supply the report.
- **Deferred improvements from the 2026-11-12 review:**
  - The checks run three times per implementation phase: the implementer, the `SubagentStop` hook, and the orchestrator.
  - The ADR number is computed by the model (`describe-pr` step 4), not by `loom-state`.
  - A docs role mapped to a general file such as `README.md` makes a user's edit of that file count as a docs-only change (`workingTreeDocsOnly`).
  - The allowlist covers `make *`, but not a single test file that the implementer runs for fast feedback.

### 24.2 To verify against current Claude Code docs during implementation

Still open: nothing.

Resolved (hardening after M9a, 2026-11-12):

- **`git rebase --continue` in the Bash tool:** Claude Code's Bash tool exports `GIT_EDITOR=true`, so `git rebase --continue` after a resolved conflict exits 0 there. Without that variable and without a terminal, it waits for the default editor (git 2.56.0, merge backend). `git -c core.editor=true rebase --continue` works everywhere, but needs its own allow rule: `Bash(git rebase *)` does not match it. The skills keep the plain form.
- **Eval results of this change:**
  - `implement-manual` on the M9a code, before the hardening: 7 of 7 graders pass, and the `events.jsonl` results are not `unknown` (Claude Code 2.1.318, 0.08 USD).
  - The full suite on the hardened code: 5 of 5 cases pass (1 run each, haiku, macOS, Homebrew git, 0.32 USD in total).

Resolved (milestone M8, v1.1 observability):

- **`SubagentStart`** (https://code.claude.com/docs/en/hooks): `agent_id` and `agent_type` are common input fields of the subagent events; the matcher filters on `agent_type` (plugin agents: `^my-plugin:reviewer$`). `SubagentStart` cannot block: exit 2 only shows stderr as a notice in the subagent's own transcript. Plain stdout of a `SubagentStart` hook is not added to the context. All hooks that match an event run in parallel. So `subagent_events.py` prints nothing and cannot change the outcome of `subagent_checks.py` (§11.6). The `SubagentStop` input is the one verified in milestone M4.

Resolved (milestone M6):

- **`claude plugin eval` format** (https://code.claude.com/docs/en/plugin-evals): a case is a directory below `evals/` with `prompt.md` or `case.yaml` and `graders/*.md`. `case.yaml` needs `schema_version: "1.1"` and `name`; run settings go under `execution:` (`model`, `max_turns`, `timeout_seconds`, `allowed_tools`, `prompt`, …); `context.scaffold_script` runs only with `--scaffold`. Model-free graders: `regex` (targets `last_message`, `trace`, `files`, or `{source: file, path}`; `match: not_contains`), `tool_used` (`tool`, `input_match`, `min`, `max`), `tool_order`, `file_exists`; `llm` and `baseline` call a model and loom does not use them. Results go to `evals/results/<timestamp>/`. Exit codes: 0 all cases at the threshold (default 1.0), 1 below it, 2 partial (cost ceiling). `--trust-plugin` is required outside a terminal; `--ablation none` skips the no-plugin arm.
- **Verified live** (Claude Code 2.1.318, macOS, `make eval` and probe cases, model haiku):
  - A slash command as the whole prompt (`prompt: /loom:research`) runs the skill like a typed command. No `Skill` tool call appears, so a `tool_used: Skill` grader does not detect it, and the skill text is not in the trace. Graders target the skill's output instead.
  - Runs use permission mode `dontAsk`: only the operator's `--allow-tools` grants count, and a skill's `allowed-tools` does not widen them. Without a grant the skill's `` !`…` `` injection aborts the invocation (`Shell command permission check failed … don't ask mode`). `--allow-tools 'Bash(*/bin/loom-state *)'` matches the injection `"<plugin root>"/bin/loom-state --json [--pr]`; then the injection runs.
  - Every hook event fires in an eval run, and hooks run outside the sandbox: a logging probe saw `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse` (also for subagent tools), `SubagentStart`, `SubagentStop` (`agent_type: loom:codebase-locator`), and `Stop`. The trace records only the `SessionStart` output (`hook_response`); a `PreToolUse` deny appears as the tool result `PreToolUse:Bash hook error: <reason>`.
  - Skills read `${CLAUDE_PLUGIN_ROOT}/skills/_shared/*` and their templates with Read in the eval runtime; no denial.
  - The agent's working directory is the scaffold workspace (`<run dir>/home/cwd`; `HOME` is `<run dir>/home`). The scaffold runs in place: `$0` is the script in the case directory, so `$(dirname "$0")/../_fixture/build.py` resolves. Its environment has `PATH`, `HOME`, `TMPDIR`, `TMP`, `TEMP`, `TERM=dumb`, and `GIT_CONFIG_NOSYSTEM=1`.
  - The Agent tool is named `Agent` in the trace. Subagent messages are in the trace with `parent_tool_use_id`, and `tool_used` counts subagent calls too (one Read by the skill plus one by a subagent counted 2). Subagents ran in the background; the trace then has one `result` line per wake-up, and the last one is the final message.
  - `--case` and `--tag` filters combine with AND. A selection with no case prints `No eval cases found matching …`, exits 1, and starts no run.
  - The plugin's `bin/` is not on the Bash `PATH` in eval runs (`command not found: loom-state`); the Bash `PATH` is the `PATH` of the `claude plugin eval` process. `make eval` adds `bin/`.
  - macOS sandbox (2026-11-11, Claude Code 2.1.318):
    - With only the Command Line Tools selected, `/usr/bin/python3`, `make`, and `git` are xcrun shims that fail inside the sandbox (`couldn't create cache file '/var/folders/…/T/xcrun_db-…' (errno=Operation not permitted)`, then `xcode-select: Failed to locate 'git'`). `python3` and `make` follow `PATH`, so `make eval` puts `$(xcode-select -p)/usr/bin` first; zsh `whence -a python3 make` then lists the developer directory's copies first.
    - Bash `git` does not follow `PATH`: `whence -a git` lists only `/usr/bin/git`, also with the Xcode and Homebrew directories first on `PATH` and after `hash -r`. The eval runtime strips `DEVELOPER_DIR` from the Bash environment. The sandbox denies the shim's cache write in `/var/folders/…/T` and its read of `/var/folders/…/T/xcrun_db`.
    - Full Xcode does not fix it. With `xcode-select -p` at `/Applications/Xcode.app/Contents/Developer` (license accepted) and no other git installed, `make eval` passed `research-full`, `design-full`, and `guard-main`; `implement-manual` failed with the same xcrun error, and no `git` command succeeded. In the sandbox, `ls -l` of Xcode's `usr/bin/git` gives `Operation not permitted`, but running it by full path works (`git version 2.54.0 (Apple Git-157)`).
    - Homebrew git fixes it. After `brew install git` (2.56.0, `/opt/homebrew/bin/git`), `git` still resolves to `/usr/bin/git` and the shim still prints the cache errors on stderr, but the command then runs with Homebrew git (`git version 2.56.0`; `git status`, `git diff`, and `git commit` work). How the shim finds Homebrew git is not proven. `implement-manual` then passed 2/2 locally (haiku, 0.12 USD). An earlier run failed for another reason: the model chained commands (`ls … && git status`) and ran `python3 -m …`, which `--allow-tools` does not grant.
    - `git init` in the sandbox cannot copy the hook templates into `.git/hooks` (`Operation not permitted`). loom does not need it: the scaffold builds the fixture repository outside the sandbox.

    Without Homebrew git a skill therefore cannot run `git` there: research falls back to reading `.git/HEAD`, and implement cannot commit. `loom-state` and hook scripts are unaffected (their `git` subprocesses follow `PATH`). The GitHub `macos-26` image ships Homebrew git, which likely explains why `implement-manual` passes there (below); this is not proven. `make eval` warns when the first `git` on the caller's `PATH` is `/usr/bin/git` and still runs every case (§20.2).
- **Evals in GitHub Actions** (`eval.yml`):
  - `ubuntu-24.04`, Claude Code 2.1.318 and 2.1.322: every skill case aborts at turn 0 with `Shell command failed for pattern "!`"…/bin/loom-state --json`"`. The trace shows the cause: `/bin/bash: line 1: /tmp/claude-eval-…/tmp/claude-1001/cwd-…: Read-only file system`. The bubblewrap sandbox keeps the run's `TMPDIR` read-only, so the Bash tool cannot write its cwd file. Every sandboxed Bash call fails, skill injections included. `guard-main` passes, because the hook denies the command before Bash runs. Managed settings `/etc/claude-code/managed-settings.json` with `{"sandbox":{"filesystem":{"allowWrite":["/tmp"]}}}` did not change it. The traces do not show whether Claude Code's sandbox profile or the runner's `/tmp` mount causes it; it looks like an upstream bug. Runs: https://github.com/mmosvlad1/loom/actions/runs/42907795225, 42908329427 (2.1.322), 42908552525 (managed settings).
  - `macos-latest` (image `macos-26-arm64`), Claude Code 2.1.318, haiku: all 4 cases pass 1/1, `implement-manual` included. Total cost 0.25 USD: research 0.15, implement 0.08, design 0.02, guard 0.002. Run: https://github.com/mmosvlad1/loom/actions/runs/42908741230. `eval.yml` therefore pins `macos-26`.
- **`implement` stops at manual verification** (outside the eval sandbox, because of the local macOS limit above; the macOS runner later passed the case in the eval sandbox): `claude -p "/loom:implement" --plugin-dir . --model haiku --permission-mode default --setting-sources project,local --allowedTools "Read" "Edit" "Write" "Agent" "Bash(git *)" "Bash(make *)" "Bash(loom-state *)"` in the `implement-manual` fixture committed phase 1 once, ticked it, logged `## Phase 1 — done — <hash>`, did not start phase 2, and ended with `Manual verification:` and `Next: run the manual steps, then /clear, then /loom:next`. All five graders that the case had then pass on that output.
- **`Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)` in default permission mode** (the eval runtime cannot cover it): `claude -p "/loom:research" --plugin-dir <loom> --model haiku --permission-mode default --setting-sources project,local --allowedTools "Skill"` in the `research-full` fixture read `skills/_shared/frontmatter.md`, `writing-style.md`, `visual-conventions.md`, `final-answer.md`, and `skills/research/references/template.md` without a denial (only a later Write outside the grants was denied). Control: the same run with that rule removed from the skill's `allowed-tools` denied all four `_shared` reads ("Claude requested permissions to read from …").
- **statusLine live check:** on 2026-11-11, Claude Code 2.1.318, macOS, an interactive session `LOOM_PLUGIN_ROOT=<loom checkout> claude --plugin-dir <loom checkout>` in a copy of the `design-full` fixture, with the committed `.claude/loom-statusline.py` and only the `statusLine` entry in `.claude/settings.json`, showed the line `#7 · full · research:approved`. The working directory of the `statusLine` command is not documented; the command finds the script through `git rev-parse --show-toplevel`, and the script runs `loom-state` in `workspace.current_dir`, so any working directory inside the repository works. Scope: this check used the `LOOM_PLUGIN_ROOT` override. The lookup through `installed_plugins.json`, the `loom` marketplace, and the plugin cache is covered only by the unit test against a fake plugins root.
- **`claude plugin validate --strict` needs no credentials:** it passed with an empty `HOME` and no API key or token in the environment, so loom's CI runs it without a secret.

Resolved (milestone M5):

- **Settings schema** (https://code.claude.com/docs/en/settings-reference, entries `extraKnownMarketplaces`, `enabledPlugins`, `statusLine`; https://code.claude.com/docs/en/settings): all three keys and `permissions.allow`/`ask` are honored in the project `.claude/settings.json` ("Any file"). `extraKnownMarketplaces` maps a marketplace name to `{"source": {"source": "github", "repo": "owner/repo"}}` plus an optional `autoUpdate`; Claude Code honors it from a project file only after the workspace trust dialog. `enabledPlugins` maps `plugin@marketplace` to a Boolean. `statusLine` is `{"type": "command", "command": "…"}` with optional `padding`, `refreshInterval`, `hideVimModeIndicator`. Permission lists merge across settings files. `$schema`: `https://json.schemastore.org/claude-code-settings.json`. **Superseded:** this note said that a project-enabled plugin loads without a per-user install when its marketplace entry has a relative-path source (loom's has `./`). That is wrong (checked 2026-11-12, https://code.claude.com/docs/en/plugins/loading, "Enabled in project settings but not installed"): a plugin enabled only in project settings loads after each collaborator runs `claude plugin install loom@loom --scope project` once per clone; `/reload-plugins` loads it for one session. The relative-path source (`./`) does not change this (§19.3).
- **Permission rule syntax** (https://code.claude.com/docs/en/permissions, "Wildcard patterns"): the current form is `Bash(git status *)`; a trailing ` *` also matches the bare command (`Bash(git log *)` matches `git log`); `:*` at the end is an equivalent older form. `ask` rules beat `allow` rules from any file. Project `allow` rules apply only after the workspace trust dialog.
- **statusLine** (https://code.claude.com/docs/en/statusline, https://code.claude.com/docs/en/plugins-reference, https://code.claude.com/docs/en/plugins/loading): a plugin cannot ship a `statusLine`: a plugin `settings.json` applies only `agent` and `subagentStatusLine`. `${CLAUDE_PLUGIN_ROOT}` resolves in hook, monitor, MCP, LSP, and skill content, not in settings; the status line command gets the session JSON on stdin (`workspace.current_dir`, `workspace.project_dir`) and runs only after workspace trust; empty output or a non-zero exit blanks the line. Plugins live in `<plugins root>/cache/<marketplace>/<plugin>/<version>/` (plugins root: `CLAUDE_CODE_PLUGIN_CACHE_DIR`, default `~/.claude/plugins`), `installed_plugins.json` records each install's `installPath`, and an old version gets an `.orphaned_at` marker. Decision: the committed script `.claude/loom-statusline.py` (§19.3), optional in `setup`.
- **Rulesets on the free plan** (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets, "Who can use this feature?"): "Rulesets are available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, and GitHub Enterprise Cloud."
- **CI action versions** (GitHub releases, checked on 2026-11-09): `actions/checkout` v7.0.1, `astral-sh/setup-uv` v10.3.3 (no floating major tag), `actions/setup-node` v7.1.0, `pnpm/action-setup` v6.1.1, `oven-sh/setup-bun` v2.2.0. The CI templates pin these exact tags.
- **Empty python-uv project** (checked locally with uv 0.10.5): `ruff check`, `ruff format --check`, and `pyright` exit 0 without source files; `pytest` exits 5 ("no tests ran"), hence the `test` target of §17.1.

Resolved (milestone M4):

- **`SubagentStop` for a plugin agent** (https://code.claude.com/docs/en/hooks, SubagentStart and SubagentStop): the input has `stop_hook_active`, `agent_id`, `agent_type`, `agent_transcript_path`, and `last_assistant_message`, plus the common fields. `agent_type` is the matcher value. For a plugin agent it is the plugin-scoped name (`loom:implementer`), not the frontmatter name; the docs recommend the anchored matcher `^my-plugin:reviewer$`. Exit 2 keeps the subagent running and delivers stderr as its next instruction. `stop_hook_active` is `true` while Claude Code continues because of a stop hook; Claude Code also caps consecutive stop-hook continuations at 8, but that count resets on every tool call. The default command hook timeout is 600 seconds.
  - Verified live (Claude Code 2.1.318, `claude -p --plugin-dir . --model haiku --permission-mode default --setting-sources project,local --allowedTools "Read Edit Write Agent Task"`, fixture repository whose `make check` always fails, plus a project `SubagentStop` hook with matcher `*` that logged its input): the input had `agent_type: "loom:implementer"`; the matcher `^loom:implementer$` fired; `subagent_checks.py` exited 2 twice and the implementer continued each time (the hook output reached it as "Stop hook feedback"); `stop_hook_active` was `false` on the first stop and `true` on the second and third, also after a successful Read call in between; on the third failure the hook exited 0 with its `systemMessage`, and the implementer stopped.
  - Also seen live: in default permission mode, `make check 2>&1 | tee "${TMPDIR:-/tmp}/loom-check.log"` was refused ("A variable in braces in this command can't be checked before it runs"). Skills and the implementer therefore run checks exactly as configured, with no pipe, redirection, or shell variable (`_shared/git-flow.md`).
- **`/loom:next` follows a phase file read with Read:** the file is not loaded as a skill. Its `` !`…` `` injection does not run, its `${…}` variables and `$ARGUMENTS` are not substituted, its `allowed-tools` do not apply, and its `model` and `effort` do not apply. Fix (§9.0, §9.12): `next` injects the state itself, tells the model how to fill in the placeholders, carries the union of the permission rules, and runs with `model: inherit` and the session's effort instead of `haiku`/`low`.

Resolved (milestone M3):

- **Skill frontmatter `model` and `effort`** (https://code.claude.com/docs/en/skills, frontmatter reference): both are supported. `model` accepts the values of `/model` (aliases such as `sonnet`, `opus`, `haiku`, or a full model ID) or `inherit`; it applies for the rest of the current turn. `effort` accepts `low`, `medium`, `high`, `xhigh`, `max` (available levels depend on the model); omitted, the normal effort resolution applies. There is no `default` value, so §9.0 `default` means the field is omitted. An unknown frontmatter field is ignored without an error, so `tests/test_skills.py` checks the field names and values against §9.0.
- **Skill command injection** (same page, "Inject dynamic context"): a failing `` !`cmd` `` (non-zero exit) aborts the whole skill invocation with `Shell command failed for pattern "..."`. Injected commands never prompt: each is checked against the permission rules first. Outside auto mode, any result other than allow (a deny or ask rule, or no matching rule) aborts the invocation with `Shell command permission check failed for pattern "..."`. `allowed-tools` pre-approves a command for the invoking turn; deny and ask rules still override it. In auto mode an unmatched command does not abort; Claude runs it itself. `allowed-tools` accepts a space- or comma-separated string or a YAML list; `${CLAUDE_PLUGIN_ROOT}` is substituted in its Bash rules for plugin skills.
  - Verified live (Claude Code 2.1.318, `claude -p --plugin-dir . --permission-mode default --setting-sources project,local`, fixture repository): without `allowed-tools`, `/loom:research` aborted with `Shell command permission check failed for pattern "!`"/…/loom"/bin/loom-state --json`": This command requires approval`. With `allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json)`, the injection ran and the skill received the state JSON. The quoted form matches the rule as written. `/loom:iterate` with the `… --json --pr` rule rendered too. A Bash call of the bare `loom-state --json` (as `final-answer.md` writes it) ran without a prompt under `Bash(loom-state --json)`.
  - Also verified live: in default mode, `Read` of the plugin's `skills/` files is denied ("Path is outside allowed working directories") unless allowed; `Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)` (an absolute-path rule, `//…` after substitution) allows it.
  - `loom-state` exits 0 outside a loom project, so the injection does not fail there; skills treat empty state as "not a loom project".
  - **Turn scope:** the `allowed-tools` grant lasts only until the user's next message. After a skill asks the user something (overwrite or rerun, fix items, push, rebase conflicts), plugin-file reads and `loom-state` calls fall back to the normal permission rules. Skills therefore read all plugin files (shared snippets, template) before the first question, and `setup` allowlists `loom-state` (§19.3).
  - **Not documented:** the docs describe `${CLAUDE_PLUGIN_ROOT}` substitution in the Bash rules of `allowed-tools` only. Its substitution in the `Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)` rule was seen live (see "Also verified live" above) but is not documented. An eval cannot cover it (the eval runtime manages permissions itself); M6 checked it live again in default permission mode (Resolved, milestone M6).

Resolved (milestone M1):

- **Skill content:** `` !`cmd` `` injects command output; `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_SKILL_DIR}` are substituted when the skill loads.
- **`SubagentStop` exit code 2** for subagents is documented: the subagent cannot stop and receives stderr.
- **`bin/` on `PATH`:** executables in the plugin's `bin/` are on the Bash tool's `PATH` while the plugin is enabled. Not documented for hooks, so hooks call `"${CLAUDE_PLUGIN_ROOT}"/bin/…` (quoted). `loom-state` lives in `bin/`.
- **Manifests:** `.claude-plugin/plugin.json` requires only `name` (also `version`, `description`, `author{name,email,url}`, `homepage`, `repository`, `license`, `keywords`); the version lives only there. `.claude-plugin/marketplace.json` requires `name`, `owner{name}`, and `plugins[{name, source}]`; a plugin at the repository root uses `"source": "./"`. Install: `/plugin install loom@loom`.
- **Auto-discovery:** `skills/`, `agents/`, `hooks/hooks.json`, and `bin/` at the plugin root.
- **`hooks/hooks.json`:** `{"hooks": {"<Event>": [{"matcher": "…", "hooks": [{"type": "command", "command": "…", "timeout": 10}]}]}}`; `timeout` is in seconds. A matcher of letters, digits, `_`, `-`, `|`, `,`, and spaces is an exact name or a list; other characters make it an unanchored regex.
- **`SessionStart`:** matchers `startup`, `resume`, `clear`, `compact` (also `fork`); stdin JSON has `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `source`; on exit 0, plain stdout is added to the context.
- **`PreToolUse` (Bash):** the command is `tool_input.command`, plus `cwd`; deny with exit 0 and `hookSpecificOutput.permissionDecision: "deny"`.
- **Validation:** `claude plugin validate --strict .` validates the marketplace manifest (and runs plugin directory checks); `claude plugin validate --strict .claude-plugin/plugin.json` validates the plugin manifest. `make validate` runs both.
