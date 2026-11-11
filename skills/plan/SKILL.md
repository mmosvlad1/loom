---
name: plan
description: Quick and full mode. Reads all task artifacts except the research questions and writes the whole 04-plan.md at once - a Phase Overview of vertical-slice implementation phases, each with goal, changes, and verification - plus a question round only where the plan is uncertain. Full mode needs an approved 03-design.md.
disable-model-invocation: true
argument-hint: "[notes or extra files]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
effort: high
---

# Plan

You write the implementation plan: a sequence of implementation phases that `implement` runs one by one. Each implementation phase is a vertical slice that the checks can verify on its own.

## State

Current task state from `loom-state`:

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json`

Arguments: $ARGUMENTS

"Today" below means `today` from the state. If the state is empty, use the session's current date.
`task.dir` is relative to the project's git top level (your working directory), never to the plugin directory.

## Shared rules

Read these files in full before you start:

- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/frontmatter.md` (artifact frontmatter, status rules, `log.md` format)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/question-rounds.md` (format and rules of question rounds)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/visual-conventions.md` (trees, diff blocks, signatures)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md` (style of the artifact and the final message)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/bash-calls.md` (one command per Bash call: no `cd`, no chaining)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)
- `${CLAUDE_SKILL_DIR}/references/template.md` (the template of `04-plan.md`)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

## 1. Check preconditions

Read the state above. Stop at the first failed check. Report it in the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`.

| Check | Stop message (`Result:` line) | `Next:` |
|---|---|---|
| The state is empty | `not a loom project (no .claude/loom.json)` | `/loom:setup` |
| `onMain` is `true` | `on the main branch; no task` | `/loom:start-task #<n>` |
| `task` is `null` | `branch <branch> matches no task` | `/loom:start-task #<n>` |
| `task.archived` is `true` | `task #<n> is archived` | `/loom:start-task #<n>` (offers a restore) |
| `task.mode` is `oneshot` | `oneshot mode has no plan; implement works from 00-ticket.md` | `/loom:implement` |
| `02-research.md` is missing or `draft` | `plan needs finished research (02-research.md)` | `/loom:research` |
| full mode: `03-design.md` is missing or `draft` | `plan needs a finished design (03-design.md)` | `/loom:design` |
| full mode: `03-design.md` is `in-review` with open questions | `03-design.md has <n> open questions` | `/loom:iterate <answers>` |
| full mode: `03-design.md` is `in-review` without open questions | `03-design.md is not approved` | `/loom:iterate approve` |
| any implementation phase has status other than `pending` | `implementation started; change the plan with /loom:iterate` | `/loom:iterate <feedback>` |
| `04-plan.md` exists with status `in-review` or `approved` | ask the user first (see below) | — |

- The design is a gate in full mode: the plan starts only when `03-design.md` is `approved`.
- If `04-plan.md` exists with status `in-review` or `approved`, ask the user: rewrite it from scratch, or change it with `/loom:iterate`. Continue only after the answer "rewrite". A `draft` file is unfinished work: overwrite it.

Warnings (do not stop):

- `02-research.md` is `in-review`: add `Warning: research not reviewed`.
- `02-research.md` has `stale: true`: add `Warning: research is stale (<staleFiles>); consider /loom:research`.

## 2. Input discipline

Follow this rule exactly. An eval checks it.

- Read all task artifacts except the research questions, in full, without offset or limit:
  - `<task.dir>/00-ticket.md`
  - `<task.dir>/02-research.md`
  - `<task.dir>/03-design.md`, if it exists (always in full mode)
- **Never read `01-research-questions.md`.** It is an input of the research phase only.
- Do not read `*.superseded.md` files.
- Read `<docsDir>/conventions.md` and `<docsDir>/architecture/overview.md` if they exist (`docsDir` from `.claude/loom.json`, default `docs`).
- Read `.claude/loom.json` → `checks`. If a key is missing, use the default: `lint` = `make lint`, `typecheck` = `make typecheck`, `test` = `make test`, `check` = `make check`.
- Read every file the arguments mention, in full.
- Read the source files that the plan changes, as the research and the design reference them. You need them to write exact signatures and change points.

When artifacts disagree, the later phase wins: ticket, then research, then design. For current behavior, the code wins. Follow the design's Resolved Decisions over the ticket.

## 3. Follow-up research (optional)

Spawn agents only if the inputs do not show something the plan needs (an exact call site, a test pattern, a config file). Use only these agents, by their namespaced name:

- `loom:codebase-locator`: finds more files for a specific component.
- `loom:codebase-analyzer`: explains how a specific part works.
- `loom:codebase-pattern-finder`: finds test patterns and similar implementations to follow.

Do not use `general-purpose`, `Explore`, or `Plan`. Wait for all agents before you write.

## 4. Cut the implementation phases

Every implementation phase is a **vertical slice**:

- It cuts across the layers the change needs (for example storage, logic, interface, and tests) and ends in something that can be run, queried, or tested.
- It passes `checks.check` on its own, with its own tests. Phase N never needs phase N+1 to verify.
- The first implementation phase is the thinnest end-to-end version. Later phases add behavior to it.

Do not cut horizontal phases:

| Horizontal (do not) | Vertical (do) |
|---|---|
| 1. Add all types 2. Add the API 3. Add the UI 4. Add tests | 1. Fixed-response endpoint, verifiable via curl and a test 2. Wire it to real storage 3. Add the first validation error end to end |

- Not all work fits this shape exactly. Cross module boundaries where you can, so problems show up early.
- Use as few implementation phases as the change needs. A small change can have one.

## 5. Write the plan

Use the template you read at the start (`${CLAUDE_SKILL_DIR}/references/template.md`). Write the **whole** `<task.dir>/04-plan.md` in one pass: all sections and all implementation phases. Do not ask for confirmation between implementation phases.

1. Write `status: draft`, `updated` = today, and `based_on`:
   - full mode: `[00-ticket.md, 02-research.md, 03-design.md]`
   - quick mode: `[00-ticket.md, 02-research.md]` (add `03-design.md` if it exists)
2. **Phase Overview**: one top-level checkbox per implementation phase, `- [ ] <N>. <name>, verifiable via <how>`. `loom-state` parses these lines:
   - Keep each line unindented, numbered from 1, and unchecked. Only `implement` ticks them.
   - The numbers and names match the `## Phase <N>: <name>` sections.
   - Do not add other checkboxes to this section.
3. **Open Questions**: see step 6.
4. **Resolved Decisions**: the table header only. No rows. The design's decisions stay in `03-design.md`; the implementer reads both.
5. One `## Phase <N>: <name>` section per implementation phase, with:
   - `### Goal`: what works at the end of the implementation phase that did not work before.
   - `### Changes`: a file tree of the created, changed, and deleted files, then key signatures and `diff` blocks for changed shapes. Name the tests to add or change, following the testing patterns from the research. Be exact enough that `loom:implementer` needs no design decision.
   - `### Verification`: checkbox lines (see below).
6. Remove every guidance comment from the template.

### Verification lines

- Start with `- [ ] Automated: <command>` lines: the checks from `.claude/loom.json` (e.g. `checks.test`), plus specific commands where they help (a single test file, a curl call, a CLI run).
- Add a `- [ ] Manual: <step>` line only if the check cannot reasonably be automated. Prefer a test or a script.
- `implement` stops after every implementation phase that has a `Manual:` line. An implementation phase without manual steps has no `Manual:` line at all.
- Do not add commit steps. `implement` commits each implementation phase.

## 6. Questions only where uncertain

- Add a question round only where the plan is uncertain: a choice the inputs do not settle and that changes the implementation phases. Design questions are already decided in `03-design.md`; do not ask them again.
- If nothing is uncertain, write `## Open Questions` with the single line `None.`.
- Otherwise write `## Open Questions — Round 1` and follow `question-rounds.md` exactly: `**Q<n>.` at the start of the line, 2-4 options, exactly one `— recommended: <one-line reason>`, and the independence rule.
- Write every question as open. Do not resolve it yourself. Write the plan for the recommended option and point to the question ("Assumes Q1 a").
- Size: `task.size`, or `M` in quick mode and `L` in full mode if it is `null`. Cap: `.claude/loom.json` → `rounds.cap.<size>` (defaults `S` = 2, `M` = 3, `L` = 5). `/loom:iterate` applies the cap.
- Do not write the round-cap marker from `question-rounds.md`. Only `/loom:iterate` writes it, at the cap.

## 7. Finish

- Check that `loom-state` parses the plan: run `loom-state --json`. `implementation.total` must equal the number of `## Phase <N>:` sections, and `warnings` must not mention `04-plan.md`. Fix the plan if not.
- Set `status: in-review` and `updated` to today.
- Run `loom-state --json` again and compute the `Next:` line as `final-answer.md` describes.
- End with the `final-answer.md` format and nothing else. Write `Open questions` with the round if a round is open, e.g. `2 (round 1)`. Add the `Warning:` lines from step 1.
