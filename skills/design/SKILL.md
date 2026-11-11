---
name: design
description: Full mode only. Reads 00-ticket.md and 02-research.md (never the research questions) and writes 03-design.md - current state, desired end state, out of scope, proposed architecture, testing approach - with the first round of open design questions for the user to answer via /loom:iterate.
disable-model-invocation: true
argument-hint: "[notes or extra files]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
effort: high
---

# Design

You write the design for the task: what changes, the proposed architecture, and the design questions the user must decide. You recommend; the user resolves.

## State

Current task state from `loom-state`:

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json`

Arguments: $ARGUMENTS

"Today" below means `today` from the state. If the state is empty, use the session's current date.
`task.dir` is relative to the project's git top level (your working directory), never to the plugin directory.

## Shared rules

Read these files in full before you start:

- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/frontmatter.md` (artifact frontmatter and status rules)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/question-rounds.md` (format and rules of question rounds)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/visual-conventions.md` (trees, diff blocks, signatures)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md` (style of the artifact and the final message)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/bash-calls.md` (one command per Bash call: no `cd`, no chaining)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)
- `${CLAUDE_SKILL_DIR}/references/template.md` (the template of `03-design.md`)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

## 1. Check preconditions

Read the state above. Stop at the first failed check. Report it in the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`.

| Check | Stop message (`Result:` line) | `Next:` |
|---|---|---|
| The state is empty | `not a loom project (no .claude/loom.json)` | `/loom:setup` |
| `onMain` is `true` | `on the main branch; no task` | `/loom:start-task #<n>` |
| `task` is `null` | `branch <branch> matches no task` | `/loom:start-task #<n>` |
| `task.archived` is `true` | `task #<n> is archived` | `/loom:start-task #<n>` (offers a restore) |
| `task.mode` is not `full` | `design runs only in full mode (mode: <mode>)` | from `next.command` |
| `02-research.md` is missing or `draft` | `design needs finished research (02-research.md)` | `/loom:research` |
| `03-design.md` exists with status `in-review` or `approved` | ask the user first (see below) | — |

- If `03-design.md` exists with status `in-review` or `approved`, ask the user: rewrite it from scratch, or change it with `/loom:iterate`. Continue only after the answer "rewrite". A `draft` file is unfinished work: overwrite it.

Warnings (do not stop):

- `02-research.md` is `in-review`: add `Warning: research not reviewed`.
- `02-research.md` has `stale: true`: add `Warning: research is stale (<staleFiles>); consider /loom:research`.

## 2. Input discipline

Follow this rule exactly. An eval checks it.

- Read `<task.dir>/00-ticket.md` and `<task.dir>/02-research.md` in full, without offset or limit.
- **Never read `01-research-questions.md`.** It is an input of the research phase only. Use the research instead.
- Do not read `*.superseded.md` files.
- Read every file the arguments mention, in full.
- You may read the project docs in `<docsDir>` (from `.claude/loom.json`, default `docs`) if they exist: `architecture/overview.md`, `architecture/decisions/`, `conventions.md`.
- Read the inputs yourself, in the main context, before you spawn any agent.

When the ticket and the research disagree about current behavior, the research and the code win. When they disagree about the goal, the ticket wins.

## 3. Follow-up research (optional)

Spawn agents only if the research does not answer something the design needs. Use only these agents, by their namespaced name:

- `loom:codebase-locator`: finds more files for a specific component.
- `loom:codebase-analyzer`: explains how a specific part works.
- `loom:codebase-pattern-finder`: finds existing patterns to follow, with code excerpts.

Do not use `general-purpose`, `Explore`, or `Plan`. Wait for all agents before you write. Skip this step when the research already gives the context.

## 4. Size the rounds

- Read the size from `task.size` in the state. If it is `null`, use `L` (full mode).
- Read the round cap from `.claude/loom.json` (at the git top level) → `rounds.cap.<size>`. If a key is missing, use the default: `S` = 2, `M` = 3, `L` = 5.
- Write the expected number of rounds `~M` in the heading as `question-rounds.md` describes (S → 2, M → 3, L → 5).
- This is round 1.

## 5. Write the design

Use the template you read at the start (`${CLAUDE_SKILL_DIR}/references/template.md`). Write `<task.dir>/03-design.md` from it:

1. Write `status: draft`, `based_on: [00-ticket.md, 02-research.md]`, and `updated` = today.
2. Fill the sections:
   - **Current State**: what exists today and what the user experiences, from the research.
   - **Desired End State**: what is true when the task is done.
   - **Out of Scope**: what this task does not do.
   - **Proposed Architecture**: before/after file trees, `diff` blocks for changed shapes, key interfaces as signatures, and the existing patterns to follow (each with `path:line` and a short excerpt). Use the smallest set of views that makes the change clear.
   - **Open Questions — Round 1 of ~M**: the first round (see below).
   - **Resolved Decisions**: the table header only. No rows.
   - **Testing Approach**: which existing test patterns to follow (with `path:line`), which new tests, and which checks cover them.
3. Remove every guidance comment from the template.

### All questions are open

This rule is checked by an eval.

- Write **every** design question under `## Open Questions — Round 1 of ~M`. Write none as resolved.
- Leave **Resolved Decisions** empty: the header row and the separator row only. Only the user's answers (through `/loom:iterate`) add rows.
- Do not resolve a question yourself, also when the research makes the answer look obvious. Recommend it instead.
- Do not write the round-cap marker from `question-rounds.md`. Only `/loom:iterate` writes it, at the cap.

### The first round

- Follow `question-rounds.md` exactly: `**Q<n>.` at the start of the line, 2-4 options, exactly one `— recommended: <one-line reason>`.
- Base the recommendation on the research and the codebase conventions.
- Apply the independence rule: a question goes into round 1 only if its answer does not depend on another open question. Keep dependent questions for later rounds; do not write them yet.
- Ask only questions that change the architecture, the scope, or the plan. Decide minor implementation details in the plan phase instead.
- Where the Proposed Architecture depends on an open question, describe the recommended option and point to the question ("Assumes Q2 a").
- If no question is open, write `## Open Questions` with the single line `None.`.

## 6. Finish

- Set `status: in-review` and `updated` to today.
- Run `loom-state --json` and compute the `Next:` line as `final-answer.md` describes.
- End with the `final-answer.md` format and nothing else. Write `Open questions` with the round, e.g. `3 (round 1 of ~5)`. Add the `Warning:` lines from step 1.
