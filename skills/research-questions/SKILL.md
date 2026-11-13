---
name: research-questions
description: Full mode only, never on the setup task. Reads the task's 00-ticket.md, does light research with loom agents, and writes 01-research-questions.md - 2 to 8 descriptive questions about the code as it exists, plus verbatim context pointers - without revealing what will be built.
disable-model-invocation: true
argument-hint: "[files or notes to consider]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Research Questions

You write the query plan for the research phase. The research phase reads only your file, never the ticket. Your questions must lead it to the right code without telling it what will be built.

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
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/bash-calls.md` (one command per Bash call: no `cd`, no chaining)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)
- `${CLAUDE_SKILL_DIR}/references/template.md` (the template of `01-research-questions.md`)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

## 1. Check preconditions

Read the state above. Stop at the first failed check. Report it in the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`. A `Next:` from `next.command` is mapped as `final-answer.md` describes.

| Check | Stop message (`Result:` line) | `Next:` |
|---|---|---|
| The state is empty | `not a loom project (no .claude/loom.json)` | `/loom:setup` |
| `onMain` is `true` | `on the main branch; no task` | `/loom:start-task #<n>` |
| `task` is `null` | `branch <branch> matches no task` | `/loom:start-task #<n>` |
| `task.archived` is `true` | `task #<n> is archived` | `/loom:start-task #<n>` (offers a restore) |
| `task.setup` is `true` (the setup task) | `research-questions does not run on the setup task (#<n>); /loom:setup owns its first steps` | from `next.command` (on an onboarding task: `/loom:research` after a finished kickoff, `/loom:setup` after a stopped one) |
| `task.mode` is not `full` | `research-questions runs only in full mode (mode: <mode>)` | from `next.command` |
| `01-research-questions.md` exists with status `in-review` or `approved` | ask the user first (see below) | — |

If `01-research-questions.md` already exists with status `in-review` or `approved`, ask the user: overwrite it, or change it with `/loom:iterate <feedback>`. Continue only after the answer "overwrite". A `draft` file is unfinished work: overwrite it.

## 2. Read the inputs

- Read `<task.dir>/00-ticket.md` in full, without offset or limit.
- Read every file the arguments mention, in full.
- Do not read other artifacts in the task directory.
- While you read, collect every concrete pointer: links (URLs, issues, docs), repositories, packages and dependencies, file paths, directories. Copy them verbatim.
- **Screens.** Never open a screen: a file at or below `docs.screens`. A screen shows what will be built. So leave the paths of the ticket's `## Screens` section out of the pointers. When `design.screens` is not empty, your own calls follow the rule of the `Excluded path:` line too: never Read a file at or below `docs.screens`; a Grep that starts at its parent or higher carries `glob: "!<docs.screens>/**"`; a Glob gets a `path` or a pattern that does not reach it.

## 3. Do light research

Find out where the relevant code lives, so the questions can point to it. Keep it light: the research phase does the deep work.

Spawn agents in parallel by their namespaced name. Use only these agents. Do not use `general-purpose`, `Explore`, or `Plan`.

- `loom:codebase-locator`: finds the files and directories for a topic.
- `loom:codebase-analyzer`: explains how a specific part works, with `file:line` references.
- `loom:codebase-pattern-finder`: finds similar implementations and conventions.
- `loom:web-search-researcher`: only if the ticket depends on an external library, API, or service.

Tell each agent what to find, not how to search. Every prompt to `loom:codebase-locator`, `loom:codebase-analyzer`, or `loom:codebase-pattern-finder` carries the line `Work directory: <workDir>` (`workDir` from the state). The agent skips that directory: it holds the loom artifacts, the ticket too. When `design.screens` in the state is not empty, every such prompt also carries the line `Excluded path: <docs.screens>`. Never name a screen in a prompt. Wait for all agents before you write.

## 4. Write the questions

Use the template you read at the start (`${CLAUDE_SKILL_DIR}/references/template.md`). Write `<task.dir>/01-research-questions.md` from it:

- Write `status: draft` first. Set `based_on: [00-ticket.md]` and `updated` to today.
- Fill **Key Context Pointers** with the pointers from step 2, verbatim. Copy only the pointer, never the sentence around it that explains the goal. Write `None.` if there are none.
- Write 2-8 questions under **Questions** as a numbered list. Size the number to the task. Use more than 8 only if the user asks.
- Remove every guidance comment from the template.

### The questions never reveal what will be built

This is the most important rule of this skill.

- Ask what exists, where it exists, how it works, and how components interact.
- Ask about current behavior, data flow, contracts between components, conventions, edge cases, tests, and how libraries are used.
- Point each question at where the answer may be: "In `src/sessions/`, how does …?"
- Never ask what should be built, what needs to change, or how to implement something.
- Never name the new feature, the desired behavior, or the ticket's goal. A reader of the questions alone must not be able to guess the task.

| Bad (leaks intent) | Good (descriptive) |
|---|---|
| How should we add OAuth login to the auth module? | How does `src/auth/` authenticate a request today, from the HTTP handler to the session store? |
| Where should the new export command go? | How are CLI commands registered and dispatched in `src/cli/`? |
| What must change in the retry logic to support backoff? | How does the HTTP client in `src/http/client.py` handle failed requests today? |

### UI work

If the task may involve frontend or visual components, even when the ticket does not say so, add questions about the design system. These questions may be generic:

- Which component library or design system does the UI use?
- What patterns exist for colors (with hex codes), typography, spacing, borders, and shadows?
- Which theming system exists, if any?

When the ticket has a `## Screens` section, add one descriptive question: which UI components, styles, and tokens exist in the code, and where.

## 5. Finish

- Check the questions again against the rule above. Rewrite any question that names the goal of the task.
- Set `status: in-review` and `updated` to today.
- Run `loom-state --json` and compute the `Next:` line as `final-answer.md` describes.
- End with the `final-answer.md` format and nothing else. `Open questions` is `0` for this artifact.
