# loom — Specification

> A Claude Code plugin for structured, agent-driven development: **Research → Plan → Implement**, with GitHub Issues as the backlog, artifacts as the hand-off between phases, and a full git flow from issue to squash merge.

Status: **Draft, revision 2** · Last updated: 2026-11-10 · Describes plugin release **v1**

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
│       └── stop_lint.py            # §11.5 (milestone M4)
├── evals/                          # §20.2: one directory per case, _fixture/, results/ (ignored)
├── tests/                          # unit tests for loom-state, hook scripts, skills, evals (stdlib unittest)
├── .github/workflows/              # ci.yml (make check), eval.yml (make eval on macOS, on demand)
├── Makefile                        # test, validate, check, eval
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
| `.loom/` | ignored | Working artifacts: ticket copy, research, design, plan, log | Until the task is finished, then archived locally |
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

| Change | Effect |
|---|---|
| oneshot → quick | Adds research and plan |
| oneshot → full / quick → full | Existing `02-research.md` is renamed `02-research.superseded.md`, because it read the ticket. An existing `04-plan.md` is renamed `04-plan.superseded.md`, because it builds on that research and has no design. Research is redone blind: research-questions first, then a new research. |
| full → quick | Remaining phases skip design; existing artifacts stay valid |
| any → oneshot | Allowed only if no plan exists |

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
/loom:start-task #42   git switch main && git pull
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
                       git switch main && git pull && git fetch --prune
                       move task directory → .loom/tasks/_archive/
```

### 6.2 After the PR is open

`/loom:next` reads the PR state and routes:

| PR state | Route |
|---|---|
| Implementation phases left (a plan change after the PR; plan approved, or oneshot) | `/loom:implement`, before every other route below; after its last phase it refreshes the docs and pushes (confirmation) |
| Checks failing | `/loom:iterate` → reads failed check logs (`gh run view --log-failed`), fixes |
| Changes requested / review comments | `/loom:iterate` → reads comments (`gh pr view --comments`), fixes |
| Branch behind `main` | `/loom:iterate rebase` → `git rebase origin/main`, re-runs checks |
| Checks pending | Wait; `/loom:finish-task` watches checks |
| Checks green, no requested changes | `/loom:finish-task` |

The post-PR fix path in `iterate`: fix → checks → commit → refresh `docs/tasks/<n>-<slug>.md` and the PR body if affected → push (confirmation; `--force-with-lease` after a rebase).

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
  "mainBranch": "main",
  "onMain": false,
  "task": { "number": 42, "slug": "auth-flow", "dir": ".loom/tasks/42-auth-flow", "mode": "full",
            "size": "L", "archived": false, "url": "https://github.com/o/r/issues/42", "pr": null },
  "artifacts": [
    { "file": "02-research.md", "phase": "research", "status": "in-review", "openQuestions": 0, "stale": false },
    { "file": "03-design.md", "phase": "design", "status": "in-review", "openQuestions": 3, "acceptedByDefault": 0 }
  ],
  "implementation": { "total": 3, "done": 1, "inProgress": null, "blocked": null,
                      "phases": [ { "number": 1, "status": "done", "commit": "d4e5f6" } ] },
  "workingTree": "clean",
  "workingTreeDocsOnly": false,
  "pr": null,
  "next": { "command": "/loom:iterate <answers>", "reason": "design has 3 open questions" },
  "warnings": []
}
```

- `workingTreeDocsOnly` is `true` when the tree is `dirty` only below `docsDir` (besides the ignored `workDir` and `.loom/`), else `false`: an interrupted `describe-pr` writes docs before its commit.
- `today` is the local date (`YYYY-MM-DD`). Skills use it for `updated` instead of injecting a `date` command (§9.0).
- `task` is `null` when the branch matches no task directory. `artifacts` lists only existing files of 01–04 (the ticket is reported through `task`; `*.superseded.md` files are ignored).
- `implementation.blocked` is `null` or `{ "phase": N, "reason": "…" }`. Phase status is `pending`, `in-progress`, `done`, or `blocked`.
- `task.size` is `S`, `M`, `L`, or `null`, from the ticket frontmatter.
- `warnings` collects problems that did not stop the computation (unreadable `loom.json`, missing status, invalid size, unclosed code fence, failed stale check, `gh` errors).
- `--line`: one line for the statusline, e.g. `#42 · full · design:in-review · 3 open Q`, `#42 · full · impl 1/3`, or `#42 · archived`. Empty output when there is no task.
- `--pr`: adds PR state from `gh pr view --json number,state,reviewDecision,statusCheckRollup,mergeStateStatus` as `{ number, state, reviewDecision, checks: passing|failing|pending|none, mergeStateStatus, behindMain }`; `behindMain` is computed with git after `git fetch origin <mainBranch>`. This calls `gh` and the network, so it is not used by the `SessionStart` hook. If `gh` is missing or unauthenticated, or the branch has no PR, `pr` is `null` and a warning is added.
- `--docs`: reserved for the docs freshness check (§23). In v1 it prints "not implemented in v1" to stderr and exits 2.
- `--slug '<issue title>'`: prints the branch slug of §9.3 step 5 and exits 0. It is a pure string function, so it also works outside a loom project. A title that starts with `-` is taken as the title, not as an option. Before the ASCII step it transliterates the letters that Unicode NFKD keeps (`ß` → `ss`, `æ` → `ae`, `œ` → `oe`, `ø` → `o`, `đ` → `d`, `ł` → `l`, `þ` → `th`). One quirk is accepted: a first word that fits and a second word that would pass 40 characters leave only the first word (`a <50-character word>` → `a`). `start-task` uses it, so the slug never depends on the model.

### 8.3 Rules

- **Task lookup:** branch `^(feat|fix|chore|docs|refactor)/(\d+)-(.+)$` → issue number → task directory `<workDir>/<n>-*` (matched by number, so an edited issue title does not break it). If not found, it also looks in `<workDir>/_archive/` and reports `archived: true`. The mode comes from `00-ticket.md` frontmatter.
- **Config:** reads `.claude/loom.json` at the git top-level; missing keys take the defaults of §19.1.
- **Statuses:** read from artifact frontmatter (a minimal parser for the §13.1 fields: scalars and inline lists).
- **Open questions:** numbered `**Q<n>.` items under the latest `## Open Questions` heading; items marked "accepted by default" are counted separately (`acceptedByDefault`).
- **Code fences:** lines inside fenced code blocks are ignored. Fences follow CommonMark (3+ backticks or tildes; closed only by the same character, at least as long, with nothing after it), except that any indentation is accepted. An unclosed fence adds a warning.
- **Implementation progress:** read from plan Phase Overview checkboxes and `log.md` headings (§13.2); a `log.md` entry wins over the checkbox of the same phase. oneshot has one implicit phase, tracked only through `log.md`.
- **Working tree:** `clean` or `dirty`; files under `workDir` are ignored.
- **Stale research:** `true` when files referenced in `02-research.md` (as `path:line` or `path`) changed on `main` between the research `git_commit` and `merge-base(HEAD, origin/main)`. The task's own commits do not count. Without `origin/<mainBranch>` the local main branch is used. If the check cannot run, `stale` is `false` and a warning is added.
- **Next step:** computed by the decision table in §9.12.

### 8.4 Implementation

A single Python script, `bin/loom-state`, with no dependencies outside the standard library (Python 3.9+, the stock macOS `python3`), with unit tests in `tests/`. The decision table is a pure function (`decide_next(state)`) that is tested with plain state dicts. Hook scripts import the same file instead of re-implementing its logic.

---

## 9. Skills Reference

### 9.0 Common rules

- All skills set `disable-model-invocation: true`. They run only when invoked as `/loom:<skill>`.
- Phase skills start by injecting state: `` !`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json` `` (verified: `` !`cmd` `` injects command output, and `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_SKILL_DIR}` are substituted when the skill loads).
- Every injected command needs a matching `allowed-tools` rule, or the skill aborts outside auto mode (§24.2). Phase skills set `allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)` (`iterate`, `implement`, `describe-pr`, `finish-task`, and `next`: the injected command is `… --json --pr`). Only the injection line uses the full path; every Bash call in a skill body uses the bare `loom-state --json` (`bin/` is on the Bash `PATH`), which matches the §19.3 allowlist. `setup`, `backlog`, and `start-task` inject `--json`; `start-task` also allows `Bash(loom-state --slug *)`. The `Read` rule lets the skill read its shared snippets and templates, which lie outside the project's working directory. The grant lasts one turn, so skills read these files before they ask the user anything. Skills inject nothing else; the date comes from `loom-state` → `today`.
- Skills spawn agents by their namespaced name: `loom:codebase-locator`, etc.
- Model and effort per skill (values to tune), set as the skill frontmatter fields `model` and `effort` (verified, §24.2). `default` means the `effort` field is omitted, so the session's effort level applies:

| Skill | Model | Effort |
|---|---|---|
| design, plan | inherit | high |
| research-questions, research, implement, iterate, describe-pr, backlog | inherit | default |
| setup, start-task | inherit | default |
| next | inherit | default |
| finish-task | haiku | low |

`next` runs a phase skill in its own turn (§9.12), so it keeps the session's model and effort: a phase run through `next` uses the session's effort, not the phase's `effort` field. For `effort: high` on design or plan, invoke `/loom:design` or `/loom:plan` directly.

### 9.1 `setup`

**Purpose:** prepare a project for loom. Safe to re-run.

**Does:**
1. Detects the stack (§18) and existing commands.
2. Bootstraps through loom's own flow, because the guard blocks commits on `main`:
   1. After confirmation, creates the issue "Set up loom" and the branch `chore/<n>-loom-setup`.
   2. Shows a diff, then writes:
      - `.claude/loom.json`
      - `Makefile` (or stack-native scripts) with `lint`, `typecheck`, `test`, `check`
      - `.github/workflows/ci.yml`
      - `.claude/settings.json`: `extraKnownMarketplaces`, `enabledPlugins`, permission allowlist (§19.3), `statusLine` calling `loom-state --line` through `.claude/loom-statusline.py` (optional, §19.3); merged into an existing file, never replaced
      - `docs/` skeleton: `product/vision.md`, `architecture/overview.md`, `architecture/decisions/`, `conventions.md`, `tasks/`
      - short `CLAUDE.md` pointing to `docs/`
      - `.loom/` entry in `.gitignore`
   3. Optionally creates the labels `type:*`, `size:*`, `mode:*` (`gh label create`, confirmation). The issue gets `type:chore`, `size:S`, `mode:oneshot` if they exist.
   4. Runs `checks.check`, then commits, then hands over to `/loom:describe-pr` (oneshot-style PR). The handover is a normal oneshot task, so `loom-state` routes it: the task directory `<workDir>/<n>-loom-setup/` with `00-ticket.md` (`mode: oneshot`, `size: S`), the commit `chore(loom): set up loom (#<n>)` with the body `Phase 1: oneshot`, and the `log.md` entry `## Phase 1 — done — <hash>`. `next` is then `/loom:describe-pr`.
3. **Ruleset:** offered by `finish-task` after the setup PR is merged, so the required CI check already exists on `main` (§17.3).

**Rules:** existing files are never overwritten silently: setup shows one plan (new files in full, changed files as a diff, and every command that changes something outside the working tree) and acts after one confirmation. Existing commands and CI are reused, not replaced. A re-run continues where the last run stopped: from the main branch it first switches to an existing `chore/<n>-loom-setup` branch. On the setup branch the setup commit is every path that differs from the main branch, so a re-run after failing checks still commits; a `done` entry in `log.md` means nothing is left but `/loom:describe-pr`. Only on the main branch does a run with nothing to change report that and stop.

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
- **Discuss ideas:** reads `docs/product/vision.md`, open issues (`gh issue list`), and the code state; discusses options.
- **Create issues** in the format of `references/issue-format.md`: title, context, acceptance criteria, labels. Shows the list and waits for confirmation before `gh issue create`.
- **Prioritize:** answers "what next?" from issue dependencies and what is done.
- Helps fill `vision.md` when it is still a skeleton. The main branch takes no commits, so with an active task and a clean working tree it commits the vision on the task branch (`docs(#<n>): update product vision`); otherwise it offers a `type:docs` oneshot issue that carries the agreed text.
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
6. Refuses if the working tree is dirty (offers stash). Then `git switch <mainBranch> && git pull`, then `git switch -c <type>/<n>-<slug>`.
7. Creates `.loom/tasks/<n>-<slug>/00-ticket.md` from `references/ticket-template.md`: the §13.1 ticket frontmatter and a verbatim copy of the issue (title as the `# ` heading, labels, URL, body).
8. Ends with `Next: /clear, then /loom:next`.

If the issue already has an archived task directory, offers to restore it from `_archive/` instead. The setup issue ("Set up loom") is refused with `Next: /loom:setup`.

### 9.4 `research-questions` (full mode)

**Input:** `00-ticket.md` and files the user mentions.
**Output:** `01-research-questions.md`.

Light contextual research with `loom:codebase-locator`, `loom:codebase-analyzer`, `loom:codebase-pattern-finder` (and `loom:web-search-researcher` only if needed). Writes 2–8 descriptive questions and a verbatim **Key Context Pointers** section. Adds design-system questions if UI work is possible.

**Rule:** questions never reveal what will be built.

### 9.5 `research`

**Input:** full → `01-research-questions.md` only (never the ticket). quick → `00-ticket.md`.
**Output:** `02-research.md`, `git_commit` = `HEAD`.

**Does:**
1. Groups questions into 2–6 subagent tasks: locators first, analyzers on promising areas, pattern-finder for conventions, web researcher for external docs (links required).
2. Waits for all agents, then synthesizes with `file:line` references.
3. **Claim check:** one `loom:codebase-analyzer` run verifies about 5 randomly chosen `file:line` claims. Failed claims are fixed or moved to "Not Found / Unclear".

**Rule:** describes only; no recommendations or critique.

### 9.6 `design` (full mode)

**Input:** ticket and research (never research questions).
**Output:** `03-design.md`.

Current state, desired end state, out of scope, proposed architecture (before/after trees, `diff` blocks, key interfaces), testing approach, and the first round (§12). Optional follow-up research with agents.

**Rule:** all questions are written as open. Recommendations are allowed, resolution is not.

### 9.7 `plan`

**Input:** all artifacts except research questions.
**Output:** `04-plan.md`.

Writes the **Phase Overview** (one line per vertical slice) and full implementation phase details (goal, changes as file tree + key signatures, verification with checkboxes). Adds a round only where uncertain. The whole plan is written at once.

**Rule:** implementation phases are vertical slices; each is verifiable by `loom.json` checks.

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
| `rebase` | `git rebase origin/<mainBranch>`, checks, push with `--force-with-lease` (confirmation) |
| Mode change | §5.3 rules |

### 9.9 `implement`

**Argument:** `[implementation phase number]`. Default: the first unchecked phase.
**Input:** `04-plan.md` with `status: approved`; in oneshot, `00-ticket.md`.

**Start:**
- Runs `loom-state`. If the working tree is dirty or `log.md` has a phase `in-progress`, offers: resume, stash, or discard.
- The resume flow does not handle a `blocked` implementation phase. A blocked phase is always handled by `/loom:iterate` (§9.12 rows 3 and 4); `implement` points there.

**Per implementation phase:**
1. Writes `in-progress` for the phase in `log.md`.
2. Launches `loom:implementer` with a short prompt: plan path + phase number (oneshot: ticket path). The implementer never commits.
3. Checks are enforced by the `SubagentStop` hook (§11.4): the implementer cannot finish while `checks.check` fails. The hook lets the implementer stop after `hooks.maxCheckAttempts` failures, so `implement` runs `checks.check` once more itself. Failing checks there mean the phase is `blocked`; `implement` never commits on failing checks.
4. Launches `loom:implementation-reviewer` (oneshot: compares the diff with the ticket). The verdict has the categories of §10.2. Only `blocking` items go back to the implementer. At most `implement.maxFixAttempts` fix attempts (default 2); then `blocked: <reason>` in `log.md` and stop.
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
1. Reads all artifacts and `log.md`. A working tree that is dirty only below `docsDir` is its own earlier partial run: it continues. Code changes stop it.
2. quick/full: writes `docs/tasks/<n>-<slug>.md` (§13.4).
3. Creates ADRs for resolved decisions marked `ADR? = yes` (§13.5).
4. Checks whether the task changed the architecture; if so, proposes an update to `docs/architecture/overview.md`.
5. Commits `docs(#<n>): record decisions and summary` — only if something changed.
6. `git rebase origin/<mainBranch>` after the same guarded `git fetch` as `iterate rebase` (no fetch without a remote `origin`); re-runs checks if the rebase brought changes. Failing checks stop it before the push; `/loom:iterate` fixes them.
7. Drafts the PR title (Conventional Commits, ending with `(#<n>)`) and body (§13.6) in `<task dir>/pr-body.md`, shows them, and after confirmation runs `git push -u origin <branch>` and `gh pr create`.
8. Stores the PR number in `00-ticket.md` frontmatter (`pr: 57`).
9. Proposes follow-ups from the summary as new issues, in the format of `${CLAUDE_PLUGIN_ROOT}/skills/backlog/references/issue-format.md` (confirmation required).

### 9.11 `finish-task`

**Does:**
1. Runs from the task branch. Refuses on `main`, except `/loom:finish-task #<n>` after a merge that stopped before the cleanup (steps 5–7). Refuses while implementation phases are left, and while local commits are not on the PR (it offers the push, with confirmation): the squash merge takes only what the PR has.
2. Checks the branch is not behind `origin/<mainBranch>`; if it is, routes to `/loom:iterate rebase`.
3. `gh pr checks --required --watch` (pending ≠ failed). Refuses to merge on failure; "no required checks" is reported separately and needs explicit confirmation.
4. After confirmation: `gh pr merge --squash --delete-branch --subject '<PR title>' --match-head-commit <sha>` (no number: it selects the PR of the current branch; it deletes the local and remote branch). `--subject` keeps the Conventional Commits title, which already ends with `(#<n>)`, as the squash commit subject; without it GitHub may append ` (#<PR number>)`. `--match-head-commit` is the head whose checks step 3 watched. The title comes from `gh pr view --json title` and is single-quoted (`_shared/git-flow.md`).
5. `git switch <mainBranch> && git pull && git fetch --prune`. Deletes the local branch with `git branch -D` only if it still exists.
6. Moves the task directory to `.loom/tasks/_archive/`.
7. If the merged task was the setup task and no ruleset exists, offers to enable it (§17.3).

All steps are idempotent: re-running after a partial failure continues where it stopped. Every stop after the merge ends with `Next: /loom:finish-task #<n>`, which resumes on the main branch.

Dirty working tree: changes only below `docsDir` are an interrupted docs refresh, so `finish-task` runs `_shared/pr-update.md` (docs commit, confirmed push) and continues. Code changes stop it with `Next: /loom:iterate`, which keeps them as a fix or stashes or discards them. With the PR already merged, it offers a stash before the cleanup.

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
| 3 | Any artifact has `blocked`, or an implementation phase is `blocked` and the plan gate holds (`04-plan.md` approved or missing, or oneshot) — also with a dirty tree | show the reason; suggest `/loom:iterate <fix>` |
| 4 | Implementation started (`log.md` has a phase entry, or a plan phase is ticked), not oneshot, and `04-plan.md` exists and is not `approved` (a plan change) — with or without a blocked phase, also with a dirty tree | `/loom:iterate <feedback>` if the plan is `draft` (plan edit not finished); else `/loom:iterate <answers>` if it has open questions; else `/loom:iterate approve` |
| 5 | `log.md` phase `in-progress`, or a dirty tree while implementation phases are left; with all phases done, a dirty tree with code changes (not only below `docsDir`) | run `implement` (resume flow); with all phases done: `/loom:finish-task` if the PR is merged, else `/loom:iterate <feedback>` (keep the changes as a fix, or stash or discard them) |
| 6 | Gate artifact (design/plan) `in-review` with open questions | `/loom:iterate <answers>` |
| 7 | Gate artifact `in-review`, no open questions | `/loom:iterate approve` |
| 8 | PR open | PR routing table §6.2; phases left and the plan gate holds (approved, or oneshot): run `implement`, before every other open-PR route |
| 9 | All implementation phases done | `/loom:describe-pr` |
| 10 | Plan approved (or oneshot), phases left | run `implement` |
| 11 | Otherwise | run the next missing phase for the mode |

Gate work (rows 6 and 7) comes before PR routing and "all implementation phases done": a design or plan that went back to review, for example after a plan change on an open PR, is never skipped. Before implementation starts, a `draft` gate artifact is unfinished work and falls to row 11, which reruns its phase (`/loom:plan` overwrites a draft plan). After implementation started, a draft or in-review plan is a plan change and row 4 handles it, before the dirty tree, PR routing, and describe-pr. Non-gate artifacts (research-questions, research) never block row 11. If research is `in-review`, `next` prints "research not reviewed" and continues. If research is stale, it warns and offers to rerun research.

Row 5 and a dirty tree: `implement` resumes only while implementation phases are left. With all phases done, a tree that is dirty only below `docsDir` (`workingTreeDocsOnly`) is an interrupted `describe-pr` and falls through to the later rows (row 9, `/loom:describe-pr`, which continues its partial run; with an open PR, the PR routing of row 8, whose skills commit the docs through `_shared/pr-update.md`); code changes go to `/loom:iterate` (or `/loom:finish-task` when the PR is merged). A skill that refuses a dirty tree names the skill that handles the changes, never a `Next:` that leads back to the same refusal.

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

- Matchers: `startup`, `resume`, `clear`, `compact`.
- Runs the `loom-state` logic (no `--pr`: no network at session start) and prints a short plain-text summary to stdout, which Claude Code adds to the context: task directory, mode, artifact statuses, next step.
- On `main` or an unrecognized branch: injects one hint line.

### 11.2 `PreToolUse` (Bash) — guard the main branch

- Reads `mainBranch` from `loom.json`.
- Blocks `git commit` and `git push` when the current branch is the main branch, with two bootstrap exceptions for an empty repository (§9.1):
  - the very first commit, when the main branch has no commits;
  - a plain first push of the main branch: `refs/remotes/origin/<mainBranch>` does not exist and the main branch has exactly one commit. The guard checks both conditions locally, with no network call. "Plain" means all of these:
    - the real current HEAD (read from git, not from a `switch`/`checkout` earlier in the same command) is the main branch;
    - the remote is `origin` (given, or resolved from `branch.<main>.pushRemote`, `remote.pushDefault`, `branch.<main>.remote`);
    - the only flags are `-u`/`--set-upstream`, `-q`/`--quiet`, `-v`/`--verbose`;
    - the refspecs are none, or only `<main>`, `HEAD`, `HEAD:<main>`, `<main>:<main>`, `refs/heads/<main>`. A `+` prefix, any force flag, `--mirror`, `--all`, `--branches`, `--delete`/`-d`, or an empty source (`:<main>`) never qualifies.
- Blocks any push whose refspec targets the main branch, from any branch, including force pushes (`origin main`, `HEAD:main`, `+main`, `:main`, `--force`/`-f`/`--force-with-lease … main`, `--all`, `--mirror`). This is intentional: it closes bypasses such as `git push origin HEAD:main` from a task branch.
- Parses the command with `shlex`: compound commands (`&&`, `||`, `;`, `|`, subshells), `cd <dir> && git …`, `git -C <path>`, global git options before the subcommand, git aliases (including `!` shell aliases), and `bash -c`. Text inside quotes (`echo "git commit"`) is not a command.
- Follows branch switches earlier in the same command: `git switch`, `git checkout -b`, `--track <remote>/<branch>`, and `git checkout <name>` when `<name>` is a local branch or a remote branch that git creates locally.
- If the command cannot be parsed, a conservative fallback applies: any `git … commit|push` in the text is denied while the current branch is the main branch.

- Denies with the reason: "Create a task branch with /loom:start-task".

Known limits:
- Shell-function aliases that use positional arguments (`!f() { git push origin "$1"; }; f`) are not resolved.
- The regex fallback for unparsable commands can match text after a `#` comment (on the main branch only).
- The bootstrap exception does not inspect git config that turns a plain push into a forced or mirror push (`-c remote.origin.mirror=true`, a saved `remote.origin.push=+…`, `git remote add --mirror=push`). Each case needs deliberately set non-default config.

### 11.3 `PreToolUse` (Bash) — block output filtering

Ported from HumanLayer's `block-test-output-filtering.sh`, adapted to `make`, `pytest`, `ruff`, `pyright`, `npm test`. Blocks check commands piped into `head`, `tail`, `grep`, etc., because filtered output hides failures. Denies with the reason: "Run checks unfiltered".

- Check commands: the commands in `loom.json` → `checks`, plus `make lint|typecheck|test|check`, `pytest`, `ruff`, `pyright`, `mypy`, `npm test`, `npm run test|lint|typecheck`, and any of these behind `uv run` or `python -m`.
- Filters: `head`, `tail`, `grep`, `sed`, `awk`, `cut`, `less`, `more`. `| tee <file>` is allowed.

Known limits:
- A check inside a `{ …; }` group or a loop is not caught when the group's output is piped (`{ pytest; } | tail`).

### 11.4 `SubagentStop` — enforce checks for the implementer

- Matcher: `^loom:implementer$`. Plugin agents report the plugin-scoped `agent_type` (`loom:implementer`); the colon puts the matcher on the regex path, so it is anchored. The script checks `agent_type` again.
- Runs `checks.check` at the git top level, with a 540-second timeout (the hook `timeout` in `hooks.json` is 600 seconds, enough for a real `make check`). On failure or timeout, exits with code 2: the subagent cannot finish and receives the tail of the output on stderr.
- Counts failed attempts in a small file per subagent run, in `<tempdir>/loom-subagent-checks/` (`$TMPDIR`), keyed by a hash of `session_id` and `agent_id`. A pass deletes the file.
- After `hooks.maxCheckAttempts` failures in a row (default 3) it exits 0, so the subagent can stop, with a `systemMessage` for the user; `implement` runs the checks again and records `blocked`.
- The counter is always read, also when `stop_hook_active` is `false`; a counter file older than one hour is stale (an interrupted run) and counts as 0. The counter ends the loop: Claude Code's own cap of 8 consecutive stop-hook continuations resets on every tool call. `stop_hook_active` (`true` while the subagent continues because a stop hook blocked it) is recorded in the counter file for debugging only.
- No `.claude/loom.json`, or another agent: silent no-op.

### 11.5 `Stop` — quick lint (optional)

- Enabled by `hooks.stopLint` (default `false`).
- Runs only if the working tree has code changes (not only `.loom/`, `workDir`, or `docsDir`).
- Runs `checks.lint` (270-second timeout; hook `timeout` 300 seconds). On failure exits 2 so Claude sees the output; respects `stop_hook_active` to avoid loops: while it is `true`, the hook does nothing, so each stop gets at most one lint block.

---

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

The size comes from the ticket frontmatter `size` (copied from the `size:*` label); without it, the size matching the mode applies (quick → M, full → L). Caps come from `loom.json` → `rounds.cap`.

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

A skill writes `draft` while it works and `in-review` when it finishes. `iterate` also writes `draft` on `04-plan.md` while it changes the plan after implementation started. Only `iterate approve` sets `approved`.

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

```markdown
# #42 Auth flow
## Problem
## Outcome
## Key Decisions        ← links to ADRs
## Implementation       ← phases → commit subjects (hashes change on rebase and squash merge)
## Deviations from Plan
## Verification
## Follow-ups
```

### 13.5 ADR — `docs/architecture/decisions/NNNN-<slug>.md`

Created from resolved decisions marked `ADR? = yes` (architecture level: storage, protocols, agent structure, major libraries).

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

## Summary
## Changes
## Verification
## Decisions          ← links to ADRs and the task summary

<details><summary>Implementation plan</summary>

…04-plan.md…

</details>
```

- If the body would exceed 60,000 characters (GitHub limit: 65,536), the plan is replaced by its Phase Overview plus a note.
- oneshot PRs contain only `Closes`, Summary, and Verification.

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
| `vision.md`, `backlog` discussion | No |

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
- `conventions.md` holds project-specific rules (e.g. how LLM calls are tested). `plan` and `implement` read it.
- `overview.md` is updated in the same PR as the change that affects it.
- ADRs come from design decisions.

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
| Read-only `gh api` GET (e.g. listing rulesets) | No question from the skill; the permission system always asks (the `Bash(gh api *)` ask rule of §19.3), also in auto mode, by intent |
| `git stash`, discarding changes | Yes. A stash runs `git check-ignore -q <task dir>` first: an ignored task directory takes the plain `git stash push --include-untracked` (a pathspec with an ignored path makes `git stash` exit 1 and leave the changes staged); otherwise the `':(exclude)<task dir>'` pathspec. |

Commit messages are written to `<task dir>/commit-msg.txt` and committed with `git commit -F`; one-line titles (`gh pr create --title`, `gh pr merge --subject`) are single-quoted with every `'` written as `'\''`. Double quotes would expand backticks and `$` from plan headings (`_shared/git-flow.md`).

### 16.5 Protection

- `PreToolUse` guard (§11.2).
- GitHub ruleset on the main branch (§17.3).

---

## 17. Checks and CI

### 17.1 Single entry point

Checks run in four places — the implementer, the `SubagentStop` hook, the optional `Stop` hook, and CI — and must never diverge. The project exposes them through one entry point (Python: `Makefile`):

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

### 17.2 CI workflow (v1)

`.github/workflows/ci.yml`, on `pull_request` and `push` to the main branch. One job named `check` (the ruleset requires this name):

| Step | Python example | Catches |
|---|---|---|
| Install | `uv sync --locked` (cached) | lock file out of sync |
| Lint | `ruff check` | bugs, unused imports |
| Format | `ruff format --check` | unformatted code |
| Types | `pyright` | type errors |
| Tests | `pytest` | broken logic |

CI runs the steps through the single entry point (`make check`, or the `check` script for Node), so CI and the hooks never diverge. Single Python version. Action versions are pinned to exact release tags when `setup` generates the file: `actions/checkout@v7.0.1`, `astral-sh/setup-uv@v10.3.3` (it publishes no major tag), `actions/setup-node@v7.1.0`, `pnpm/action-setup@v6.1.1`, `oven-sh/setup-bun@v2.2.0` (latest releases, checked on 2026-11-09). The workflow sets `permissions: contents: read`.

### 17.3 Ruleset

Offered by `finish-task` after the setup PR is merged, created with `gh api` after confirmation:
- Merge to the main branch only through a PR.
- Required status check: `check`.
- Required approvals: **0** (a solo developer cannot approve their own PR).
- Block force pushes and deletion.

Availability (verified, §24.2): rulesets work on public repositories on GitHub Free; private repositories need GitHub Pro, Team, or Enterprise Cloud. If unavailable, loom relies on the guard hook only.

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

Every component reads `mainBranch`, `workDir`, and `docsDir` from this file. None of them hard-codes `main` or `.loom/tasks`.

### 19.2 Issue labels

| Label | Values |
|---|---|
| `type:` | `feat`, `fix`, `chore`, `docs`, `refactor` |
| `size:` | `S`, `M`, `L` |
| `mode:` | `oneshot`, `quick`, `full` |

### 19.3 `.claude/settings.json` (committed, written by `setup`)

Template: `skills/setup/references/templates/settings.json`. `setup` merges it into an existing file: it adds missing keys and rules and never removes or replaces one.

- `extraKnownMarketplaces` + `enabledPlugins`: anyone who clones and trusts the project is offered loom: `"extraKnownMarketplaces": {"loom": {"source": {"source": "github", "repo": "mmosvlad1/loom"}}}` and `"enabledPlugins": {"loom@loom": true}`. Claude Code honors `extraKnownMarketplaces` from a project file only after the workspace trust dialog. The marketplace entry has a relative-path source (`./`), so a project-enabled loom loads without a per-user install.
- `statusLine` (optional; `setup` asks): `{"type": "command", "command": "python3 \"$(git rev-parse --show-toplevel 2>/dev/null)/.claude/loom-statusline.py\" 2>/dev/null"}`. A settings file cannot name the plugin directory, so the committed script `.claude/loom-statusline.py` finds the installed plugin (`installed_plugins.json`, then the `loom` marketplace, then the plugin cache below the plugins root) and runs its `bin/loom-state --line` in the session's directory (`workspace.current_dir` from the status line input). It prints nothing on any failure. `LOOM_PLUGIN_ROOT` overrides the lookup (for `--plugin-dir` development). A project `statusLine` replaces each collaborator's personal status line in this project.
- Rule syntax: `Bash(<command> *)`. A trailing ` *` also matches the bare command; the older `:*` suffix is equivalent.
- Permission allowlist (`permissions.allow`; routine, reversible):
  - `git status`, `git diff`, `git log`, `git add`, `git commit`, `git switch`, `git pull`, `git fetch`, `git rebase`, `git stash push`, `git stash list`, `git stash show`, `git stash pop`, `git branch` (stash `drop` and `clear` stay out: they lose work)
  - `make *` (or the stack's check commands)
  - `gh issue view`, `gh issue list`, `gh pr view`, `gh pr checks`, `gh run view`
  - `loom-state --json`, `loom-state --json --pr` (the skills' `allowed-tools` grant lasts only one turn, §24.2; this keeps the `Next:` call from asking after the user answered a question), `loom-state --slug *`
  - `mv` inside `.loom/`: `mkdir -p <workDir>/_archive`, `mv <workDir>/* <workDir>/_archive/` (finish-task), `mv <workDir>/_archive/* <workDir>/` (start-task restore)
- **Not** allowlisted (always asked): `git push`, `gh pr create`, `gh pr edit`, `gh pr merge`, `gh issue create`, `gh label create`, `gh api`. `setup` writes them as `permissions.ask` rules, so a broader allow rule elsewhere (e.g. `Bash(git *)` in user settings) cannot skip the prompt.

---

## 20. Testing the Harness

### 20.1 Unit tests

`tests/` covers `loom-state` (task lookup, statuses, decision table, stale research, log parsing) and the hook scripts (guard, output filtering, SubagentStop checks, Stop lint) with fixture directories, plus spec-driven lints of skills, agents, shared snippets, and templates (§13.2, §13.4–§13.6). Runs in loom's CI.

### 20.2 Evals

`evals/` holds a suite for `claude plugin eval` (format: §24.2, milestone M6). One directory per case, with `case.yaml` and `graders/*.md`:

```
evals/
├── _fixture/build.py        # builds the fixture of one scenario in the run workspace
├── research-full/           # case.yaml (prompt: /loom:research), scaffold.sh, graders/
├── design-full/
├── implement-manual/
├── guard-main/
└── results/                 # written by the runs; ignored by git
```

- Each case's `scaffold.sh` runs `_fixture/build.py <scenario>`. It builds a tiny Python repository (`shop/`, stdlib `unittest` checks behind `make check`, the §19.1 `loom.json`), one commit on `main` with fixed dates (stable hashes), and the task directory of task #7 with the artifacts the scenario needs. `tests/test_evals.py` runs every scaffold and checks that `loom-state` routes it to the case's skill.
- Graders never call a model (`regex`, `tool_used`, `file_exists` only):
  - `research-full` (full mode, research questions approved):
    - `02-research.md` exists with `status: in-review` and `file:line` references.
    - No Read of `00-ticket.md` (`tool_used`, max 0).
    - No Read, Grep, Glob, or Bash input in the trace names the ticket, by the skill or by a subagent.
    - The trace never holds `Wholesale customers`, a phrase that occurs only in the ticket body. This catches the ticket's content reaching the session by any tool.
    - The skill read its shared snippets.
  - `design-full` (research approved):
    - `03-design.md` exists with `status: in-review`, a `## Open Questions — Round 1 of ~M` heading, and `**Q1.`.
    - Resolved Decisions has no table data rows and no list items.
    - No Read of `01-research-questions.md`.
  - `implement-manual` (quick mode, plan approved, implementation phase 1 has a `Manual:` line):
    - Exactly one `git commit` (also as `git -C <dir> commit`).
    - `log.md` has `## Phase 1 — done — <hash>` and no phase 2 entry.
    - The Phase Overview ticks phase 1 only.
    - The last message has `Manual verification:` and `run the manual steps, then /clear, then /loom:next`.
  - `guard-main` (on `main`, staged change, no skill):
    - A Bash `git commit` ran.
    - The trace holds the guard's deny reason.
    - `main` still points to the fixture commit.
- Every case has `runs: 1` and `model: haiku` (cost); `--runs 3` and `--model sonnet` override them.
- `make eval` runs the suite with `--scaffold --ablation none --no-publish --trust-plugin`, a `--max-cost-usd` ceiling, and the narrowest `--allow-tools` set: `Write Edit 'Bash(git *)' 'Bash(make *)' 'Bash(loom-state *)' 'Bash(*/bin/loom-state *)'`. It is not part of `make check`. It puts the plugin's `bin/` on `PATH` (the eval runtime does not) and, on macOS only, the developer directory (`xcode-select -p`) first.
- In loom's CI: `make check` (unit tests and `claude plugin validate --strict`) on every PR and push to `main` (`.github/workflows/ci.yml`). The evals run only on demand (`.github/workflows/eval.yml`, `workflow_dispatch`, repository secret `ANTHROPIC_API_KEY`), never on a schedule: they cost tokens.
- `make eval` runs every case, locally and in the Evals workflow. The Evals workflow runs all 4 cases on a pinned `macos-26` runner. Linux cannot run the skill cases: the eval sandbox breaks every Bash call there (§24.2).
- macOS needs Homebrew git (`brew install git`) for `implement-manual`. Inside the eval sandbox Bash `git` is always the `/usr/bin/git` shim; without another git it fails, with the Command Line Tools and with full Xcode (§24.2). When the first `git` on the caller's `PATH` (`command -v git`) is `/usr/bin/git`, `make eval` prints a warning that names `brew install git` and still runs every case.

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
- **Versioning:** semver, **only in `plugin.json`**; bump on every release. Users update with `/plugin marketplace update`.
- **Local development:** `claude --plugin-dir ./loom` runs the working copy; exercise it on a sandbox repository and with evals.
- **loom's own CI:** `.github/workflows/ci.yml` runs `make check` on every PR and push to `main`: unit tests (including the check that every `template.md` has its required headings) and `claude plugin validate --strict`, which needs no credentials. One job `check`, `permissions: contents: read`, `actions/checkout@v7.0.1`, `actions/setup-node@v7.1.0`, and Claude Code pinned with `npm install -g @anthropic-ai/claude-code@2.1.318`. `.github/workflows/eval.yml` runs `make eval` on demand only (§20.2), on a pinned `macos-26` runner. It installs Claude Code 2.1.318 unless the `claude_version` input names another version. It keeps each run's `out/` directory (`--keep-temp`) and uploads `evals/results/` with `actions/upload-artifact@v7.0.2` (latest release, checked on 2026-11-10).
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

### 23.1 v1.1 (planned)

- **Observability:** `SubagentStart`/`SubagentStop` hooks append one line per subagent run (agent, phase, duration, result) to `<task dir>/events.jsonl`. `describe-pr` adds a "Process metrics" line to the task summary.
- **Docs freshness gate:** `loom-state --docs` flags paths in `overview.md` and ADRs that no longer exist and modules added since the last summary; `describe-pr` asks to address them.
- **PR layout:** "Why" in one sentence, 1–3 "Special things to note", and a "Change outline" (file tree or interface `diff`).

### 23.2 Deferred, needs a separate discussion

- **Onboarding existing repositories:** how loom adopts a project that already has code, docs, CI, and conventions (drafting `overview.md` and `conventions.md` from the code, reusing existing docs, migrating existing branches and issues). v1 targets new projects; `setup` on an existing repository only adds config, checks, and empty doc skeletons.

### 23.3 Out of scope

- Git worktrees and parallel tasks.
- Monorepos with multiple stacks.
- Agents other than Claude Code.
- Linear / Jira.
- pre-commit hooks, Dependabot, coverage reports.
- Sync of `.loom/` between machines.

---

## 24. Open Topics and Items to Verify

### 24.1 Open topics

- Exact prompt texts for each skill and agent (ported from HumanLayer, adapted to this spec).
- Inline PR review comments: `gh pr view --comments` shows PR comments and review summaries, not inline review comments on code lines. The post-PR fix path in `iterate` does not read them yet; reading them needs `gh api`, which always asks for confirmation (§19.3).
- Content of `_shared/*.md` and `final-answer.md`.

### 24.2 To verify against current Claude Code docs during implementation

Still open: nothing.

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
- **`implement` stops at manual verification** (outside the eval sandbox, because of the local macOS limit above; the macOS runner later passed the case in the eval sandbox): `claude -p "/loom:implement" --plugin-dir . --model haiku --permission-mode default --setting-sources project,local --allowedTools "Read" "Edit" "Write" "Agent" "Bash(git *)" "Bash(make *)" "Bash(loom-state *)"` in the `implement-manual` fixture committed phase 1 once, ticked it, logged `## Phase 1 — done — <hash>`, did not start phase 2, and ended with `Manual verification:` and `Next: run the manual steps, then /clear, then /loom:next`. All five graders of the case pass on that output.
- **`Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)` in default permission mode** (the eval runtime cannot cover it): `claude -p "/loom:research" --plugin-dir <loom> --model haiku --permission-mode default --setting-sources project,local --allowedTools "Skill"` in the `research-full` fixture read `skills/_shared/frontmatter.md`, `writing-style.md`, `visual-conventions.md`, `final-answer.md`, and `skills/research/references/template.md` without a denial (only a later Write outside the grants was denied). Control: the same run with that rule removed from the skill's `allowed-tools` denied all four `_shared` reads ("Claude requested permissions to read from …").
- **statusLine live check:** on 2026-11-11, Claude Code 2.1.318, macOS, an interactive session `LOOM_PLUGIN_ROOT=<loom checkout> claude --plugin-dir <loom checkout>` in a copy of the `design-full` fixture, with the committed `.claude/loom-statusline.py` and only the `statusLine` entry in `.claude/settings.json`, showed the line `#7 · full · research:approved`. The working directory of the `statusLine` command is not documented; the command finds the script through `git rev-parse --show-toplevel`, and the script runs `loom-state` in `workspace.current_dir`, so any working directory inside the repository works. Scope: this check used the `LOOM_PLUGIN_ROOT` override. The lookup through `installed_plugins.json`, the `loom` marketplace, and the plugin cache is covered only by the unit test against a fake plugins root.
- **`claude plugin validate --strict` needs no credentials:** it passed with an empty `HOME` and no API key or token in the environment, so loom's CI runs it without a secret.

Resolved (milestone M5):

- **Settings schema** (https://code.claude.com/docs/en/settings-reference, entries `extraKnownMarketplaces`, `enabledPlugins`, `statusLine`; https://code.claude.com/docs/en/settings): all three keys and `permissions.allow`/`ask` are honored in the project `.claude/settings.json` ("Any file"). `extraKnownMarketplaces` maps a marketplace name to `{"source": {"source": "github", "repo": "owner/repo"}}` plus an optional `autoUpdate`; Claude Code honors it from a project file only after the workspace trust dialog. `enabledPlugins` maps `plugin@marketplace` to a Boolean. `statusLine` is `{"type": "command", "command": "…"}` with optional `padding`, `refreshInterval`, `hideVimModeIndicator`. Permission lists merge across settings files. `$schema`: `https://json.schemastore.org/claude-code-settings.json`. A project-enabled plugin from an external source is not installed for other users, unless its marketplace entry has a relative-path source; loom's has `./`.
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
