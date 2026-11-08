---
name: research
description: Documents the code as it exists today and writes 02-research.md with file:line references. Full mode reads only 01-research-questions.md, never the ticket; quick mode reads 00-ticket.md. Fans out 2 to 6 loom research agents, then verifies sample claims. Describes only - no recommendations.
disable-model-invocation: true
argument-hint: "[notes or extra files]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Research

You document the code as it exists today. You answer the research questions by running loom research agents in parallel and synthesizing their findings into `02-research.md`.

## Your only job: describe what exists

- Describe only what exists, where it exists, how it works, and how components interact.
- Do not suggest improvements, changes, refactoring, or other approaches.
- Do not critique the code or identify problems, bugs, or risks.
- Do not perform root cause analysis.
- Do not propose future work. Do not write "should".
- Later phases (design, plan) and the user decide what to build. Research is the map of the current system.

## State

Current task state from `loom-state`:

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json`

Arguments: $ARGUMENTS

"Today" below means `today` from the state. If the state is empty, use the session's current date.
`task.dir` is relative to the project's git top level (your working directory), never to the plugin directory.

## Shared rules

Read these files in full before you start:

- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/frontmatter.md` (artifact frontmatter and status rules)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md` (style of the artifact and the final message)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/visual-conventions.md` (trees, call trees, signatures)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)
- `${CLAUDE_SKILL_DIR}/references/template.md` (the template of `02-research.md`)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

## 1. Check preconditions

Read the state above. Stop at the first failed check. Report it in the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`.

| Check | Stop message (`Result:` line) | `Next:` |
|---|---|---|
| The state is empty | `not a loom project (no .claude/loom.json)` | `/loom:setup` |
| `onMain` is `true` | `on the main branch; no task` | `/loom:start-task #<n>` |
| `task` is `null` | `branch <branch> matches no task` | `/loom:start-task #<n>` |
| `task.archived` is `true` | `task #<n> is archived` | `/loom:start-task #<n>` (offers a restore) |
| `task.mode` is `oneshot` | `oneshot mode has no research phase` | from `next.command` |
| full mode: `01-research-questions.md` is missing or `draft` | `research needs finished research questions` | `/loom:research-questions` |
| `02-research.md` exists with status `in-review` or `approved`, and `stale` is `false` | ask the user first (see below) | — |

- If `02-research.md` exists with status `in-review` or `approved` and is not stale, ask the user: rerun the research, or change it with `/loom:iterate <feedback>`. Continue only after the answer "rerun".
- If `02-research.md` is stale (`stale: true`):
  - If `03-design.md` or `04-plan.md` exists, show the `staleFiles` and offer to rerun the research. Continue only after the answer "rerun". The later artifacts may then need `/loom:iterate <feedback>`.
  - If neither exists, rerun it without asking.
  - Add a `Warning:` line with the `staleFiles` to the final message.
- If `01-research-questions.md` is `in-review` (not approved), continue. Add `Warning: research questions not reviewed` to the final message.

## 2. Input discipline

The inputs depend on `task.mode`. Follow this rule exactly. An eval checks it.

### Full mode: read only `01-research-questions.md`

- Read `<task.dir>/01-research-questions.md` in full, without offset or limit. It is your only task input.
- **Never read `00-ticket.md`.** Do not open it, grep it, cat it, or list its content.
- Never fetch the issue (`gh issue view`) or read `03-design.md`, `04-plan.md`, `log.md`, or any `*.superseded.md` file.
- Do not infer the goal of the task from the branch name, the task slug, or the issue title. Research the questions as they are written.
- Tell your agents nothing from the ticket. Give them only the research questions, the Key Context Pointers, and what you found in the code.

Research is blind to intent in full mode: it must describe the code without the bias of what will be built.

### Quick mode: read `00-ticket.md`

- Read `<task.dir>/00-ticket.md` in full. It is your only task input. (This bias is accepted in quick mode.)
- Derive 2-8 descriptive questions from the ticket yourself: what exists today in the areas the ticket touches. Write them as the `Question:` lines of the Findings.
- Research still describes only. The ticket tells you where to look, not what to recommend.
- Do not read `03-design.md`, `04-plan.md`, or any `*.superseded.md` file.

### Both modes

- Read every file the arguments mention, in full.
- Read the inputs yourself, in the main context, before you spawn any agent.

## 3. Run the research agents

Group the questions into **2-6 agent tasks**. Combine related questions that touch the same area into one task. Do not map one question to one agent.

Spawn agents by their namespaced name. Use only these agents. Do not use `general-purpose`, `Explore`, or `Plan`.

| Agent | Use it to |
|---|---|
| `loom:codebase-locator` | find WHERE files and components live. Run locators first. |
| `loom:codebase-analyzer` | explain HOW specific code works, on the most promising areas the locators found |
| `loom:codebase-pattern-finder` | find conventions and similar implementations, with code excerpts |
| `loom:web-search-researcher` | read external docs for libraries, APIs, and services. Ask it to return a link for every finding. |

- Run agents in parallel when they search different areas.
- Tell each agent what to find. Do not tell it how to search; each agent knows its job.
- Ask every codebase agent for `file:line` references.
- Wait for **all** agents to finish before you synthesize.
- If an answer is still missing, run one more targeted pass with at most 3 agents. After that pass, put what is still missing under **Not Found / Unclear**.

## 4. Write the research

Use the template you read at the start (`${CLAUDE_SKILL_DIR}/references/template.md`). Write `<task.dir>/02-research.md` from it:

1. Run `git rev-parse --short HEAD`. Write the result as `git_commit`.
2. Write `status: draft`, `updated` = today, and `based_on`:
   - full mode: `[01-research-questions.md]`
   - quick mode: `[00-ticket.md]`
3. Fill the sections:
   - **Summary**: 2-4 short paragraphs on the key components, data flows, and relationships.
   - **Findings**: one `###` section per question, in question order. Start with a `Question:` line that quotes the question. The heading states the takeaway ("Sessions persist to SQLite before the handler returns"), not the topic and not the question.
   - Under each finding, a `#### Testing patterns` subsection: test files, test type, fixtures, mocks. If no tests exist, write that; it is a finding.
   - **Patterns & Conventions**: the conventions the code follows today, each with a `path:line` example.
   - **External Sources**: every external finding with its link. `None.` if no web research ran.
   - **Not Found / Unclear**: what you could not find or trace. `None.` if everything was found.
4. Remove every guidance comment from the template.

Writing rules:

- Every claim about code has a `path:line` or `path:start-end` reference. Use a range for adjacent lines.
- Write concept first, then the reference: "The handler validates the token (`src/auth.py:40-52`)", not "`src/auth.py:40` validates".
- Prefer the live code over comments and docs when they disagree.
- Use call trees, file trees, tables, signatures, and pseudocode where they show a shape faster than prose. Place each one next to the prose it supports.
- Do not use `diff` blocks or `+`/`-` change markers. Nothing changes in research.
- Do not add a `## Open Questions` section. Put open points under **Not Found / Unclear**.

## 5. Claim check

After the draft is written, verify it:

1. Pick about 5 `file:line` claims at random from different Findings sections. Pick by position, not by how sure you are.
2. Run **one** `loom:codebase-analyzer` with the list. For each claim, give the exact `file:line` and the statement. Ask it to answer `confirmed` or `not confirmed` with what the code shows.
3. For each claim that is not confirmed:
   - fix the claim if the analyzer shows the correct fact and location, or
   - move it to **Not Found / Unclear** with what the check found.

## 6. Finish

- Set `status: in-review` and `updated` to today.
- Run `loom-state --json` and compute the `Next:` line as `final-answer.md` describes.
- End with the `final-answer.md` format and nothing else. `Open questions` is `0` for this artifact. Add the `Warning:` lines from step 1.
