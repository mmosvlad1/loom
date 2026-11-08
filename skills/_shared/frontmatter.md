# Artifact Frontmatter and Status Rules

Every artifact in the task directory starts with YAML frontmatter. `loom-state` reads it to compute the task state, so follow these rules exactly.

## Artifact frontmatter

Artifacts `01`-`04` use these fields:

```yaml
---
task: 42-auth-flow
phase: design
status: in-review
based_on: [02-research.md]
git_commit: a1b2c3d
updated: 2026-11-08
---
```

| Field | Value | Rules |
|---|---|---|
| `task` | `<n>-<slug>` | The name of the task directory |
| `phase` | `research-questions`, `research`, `design`, or `plan` | The phase that writes the artifact |
| `status` | `draft`, `in-review`, or `approved` | See "Status values" |
| `based_on` | inline list of file names | The artifacts this artifact read, e.g. `[00-ticket.md, 02-research.md]` |
| `git_commit` | short commit hash | `research` only: the code state the artifact describes (`git rev-parse --short HEAD`). Omit it on other artifacts. |
| `updated` | `YYYY-MM-DD` | Today's date. Change it on every edit. |

Parser limits:

- Use only `key: value` scalars and `key: [a, b]` inline lists.
- Do not use nested keys, block lists (`- item`), or multiline values.
- Do not add fields that are not listed here.

## Status values

| Status | Meaning | Who sets it |
|---|---|---|
| `draft` | The phase skill is still writing the artifact, or `iterate` is changing the plan | The phase skill, when it starts writing; `iterate`, when it starts a plan change after implementation started |
| `in-review` | The artifact is complete and waits for review | The phase skill, when it finishes; `iterate`, after every edit |
| `approved` | The user approved the artifact | Only `/loom:iterate approve` |

Rules:

- A phase skill writes `draft` while it works and `in-review` when it finishes.
- `iterate` writes `draft` on `04-plan.md` while it changes the plan after implementation started, and `in-review` when the change is done. The next `iterate` finishes an interrupted plan change.
- Never set `approved` yourself, except in `iterate` when the user runs `/loom:iterate approve`.
- `iterate` refuses `approve` while open questions remain, unless the user repeats `approve`.
- Feedback on an artifact keeps `status: in-review` and changes `updated`.
- Feedback that changes an approved plan sets the plan back to `in-review` (see the `iterate` skill).

## Gates

A gate is a phase that cannot start until a previous artifact is `approved`.

| Artifact | Statuses | Set by | Gate for |
|---|---|---|---|
| `00-ticket.md` | — | start-task | — |
| `01-research-questions.md` | draft → in-review → approved | skill / iterate | none |
| `02-research.md` | draft → in-review → approved | skill / iterate | none (warning only) |
| `03-design.md` | draft → in-review → approved | skill / iterate | plan |
| `04-plan.md` | draft → in-review → approved | skill / iterate | implement |
| `log.md` | per implementation phase: in-progress / done / blocked | implement | — |

- `plan` (full mode) starts only when `03-design.md` is `approved`.
- `implement` starts only when `04-plan.md` is `approved`. In oneshot mode there is no plan; `implement` works from `00-ticket.md`.
- Research questions and research never block the next phase. If research is `in-review`, `/loom:next` prints "research not reviewed" and continues.

## Ticket frontmatter

`00-ticket.md` has no `status`, `based_on`, `git_commit`, or `updated`. It has these fields instead:

```yaml
---
task: 42-auth-flow
phase: ticket
mode: full
size: L
issue: 42
url: https://github.com/o/r/issues/42
pr: 57
---
```

| Field | Value | Set by |
|---|---|---|
| `task` | `<n>-<slug>` | start-task |
| `phase` | `ticket` | start-task |
| `mode` | `oneshot`, `quick`, or `full` | start-task; changed only by a mode change before `implement` starts |
| `size` | `S`, `M`, or `L`; optional | start-task, copied from the `size:*` label. Omit it when the issue has no size label. |
| `issue` | the issue number | start-task |
| `url` | the issue URL | start-task |
| `pr` | the PR number | describe-pr, after `gh pr create` |

Agents do not edit the ticket, except these frontmatter fields: `mode` and `pr`.

## `log.md`

`log.md` has no frontmatter. Its headings are machine-readable. Only `implement` (and `iterate` for fixes) writes it:

```markdown
## Phase 1 — done — d4e5f6
Checks: lint ✓ typecheck ✓ test ✓ (42 passed)
Reviewer: pass
Deviations: switched from X to Y because …

## Phase 2 — blocked
Reason: …
```

- Heading form: `## Phase <N> — in-progress`, `## Phase <N> — done — <commit hash>`, or `## Phase <N> — blocked`, followed by a `Reason:` line.
- The last heading for an implementation phase wins.
- A `log.md` entry wins over the plan checkbox of the same implementation phase.
- In oneshot mode the only implementation phase is `Phase 1`.

## Resolved Decisions

`03-design.md` and `04-plan.md` both have a `## Resolved Decisions` section. It holds the answers to question rounds (see `question-rounds.md`), in this table:

```markdown
## Resolved Decisions
| # | Question | Decision | Rationale | Round | ADR? |
|---|---|---|---|---|---|
```

`implementer` and `implementation-reviewer` read the Resolved Decisions of both artifacts.

## Superseded files

A mode change to full renames an existing `02-research.md` to `02-research.superseded.md` and an existing `04-plan.md` to `04-plan.superseded.md`. `loom-state` ignores `*.superseded.md` files. Do not read them as inputs.
