---
name: next
description: Shows the task state in a few lines and runs the next loom phase for the mode - research-questions, research, design, plan, or implement - by following that phase's skill in this session. For iterate, describe-pr, and finish-task it only names the command. Use it after /clear between phases.
disable-model-invocation: true
argument-hint: "[notes for the next phase]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Next

You show where the task stands, then run the next phase. The decision comes from `loom-state` (`next.command`); never decide it yourself.

## State

Current task state from `loom-state`, with the pull request state:

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr`

Arguments: $ARGUMENTS

Plugin root (already filled in): `${CLAUDE_PLUGIN_ROOT}`

`task.dir` is relative to the project's git top level (your working directory), never to the plugin directory.

## 1. Read before anything else

Read `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` and `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md`.

If step 3 runs a phase, also read that phase's `SKILL.md` and every file it lists under "Shared rules" now, before you ask the user anything. If research is stale (step 2), also read `${CLAUDE_PLUGIN_ROOT}/skills/research/SKILL.md` and its files.

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

## 2. Show the state

If the state above is empty, stop with `Result: not a loom project (no .claude/loom.json)` and `Next: /loom:setup`.

Print a state summary of 3-5 lines, nothing more:

```text
Task #42 (full) · feat/42-auth-flow · working tree clean
Artifacts: research-questions approved · research in-review · design approved · plan in-review (2 open questions)
Implementation: 1 of 3 phases done
PR: #57 OPEN · checks pending
Next: /loom:iterate <answers> (plan has 2 open questions)
```

- Line 1: `task.number`, `task.mode`, `branch`, `workingTree`. On the main branch or without a task: one line with `next.reason`.
- Artifacts: the phase and `status` of each entry in `artifacts`, with open questions and `stale`. Omit the line when there are none.
- Implementation: `implementation.done` of `implementation.total`, plus `in progress` or `blocked: <reason>`. Omit it before implementation started.
- PR: `pr.number`, `pr.state`, `pr.checks`, `pr.reviewDecision`. Omit it when there is no PR.
- Next: `next.command` and `next.reason`.

Then print the warnings, one `Warning:` line each:

- every entry of `warnings`
- `02-research.md` is `in-review`, and the next phase is design, plan, or implement: `Warning: research not reviewed`. Continue.
- `02-research.md` has `stale: true`: `Warning: research is stale (<staleFiles>)`. Offer a rerun: ask the user whether to rerun research now or continue with the next phase. On "rerun", run `/loom:research` as step 3 describes, with the phase `research`.

## 3. Run or name the next command

Take the first word of `next.command`:

| `next.command` | Action |
|---|---|
| `/loom:research-questions`, `/loom:research`, `/loom:design`, `/loom:plan`, `/loom:implement` | **Run** the phase in this session (below). |
| `/loom:iterate …` | **Name** it. It needs the user's answers, feedback, or approval. |
| `/loom:describe-pr`, `/loom:finish-task` | **Name** it. It needs the user's confirmation to push or merge. |
| `/loom:start-task …`, `/loom:backlog`, `/loom:setup` | **Name** it. |

### Name a command

Do not run it. End with the `final-answer.md` format:

```text
Result: <next.reason>
Next: <next.command>
```

The session is already fresh, so write the command without `/clear, then`. For `/loom:iterate <answers>`, add an example (`/loom:iterate 1a, 2b`); for `/loom:iterate <fix>` or `<feedback>`, say what the user should describe.

### Run a phase

The phase is the command without `/loom:` (for example `plan`). Follow `${CLAUDE_PLUGIN_ROOT}/skills/<phase>/SKILL.md` exactly, as if the user had invoked it, with these differences. They exist because you read the file with Read, so Claude Code did not prepare it as a skill:

1. **Do not run its state injection.** The phase file has a line that starts with an exclamation mark and runs `loom-state`. Do not run that command. Use the state at the top of this skill as the phase's state; it already has the pull request state. If you need fresh state later, run `loom-state --json`, as the phase file says.
2. **Fill in its placeholders.** Claude Code fills these in when a skill loads, but not for a file you read. Replace them yourself in every path and command of the phase file:

   | Placeholder in the phase file | Replace with |
   |---|---|
   | `CLAUDE_PLUGIN_ROOT` in dollar-brace form | the plugin root above |
   | `CLAUDE_SKILL_DIR` in dollar-brace form | `<plugin root>/skills/<phase>` |
   | `ARGUMENTS` after a dollar sign | the arguments of this skill (above) |

3. **Ignore its frontmatter.** Its `allowed-tools` do not apply; this skill's permissions cover the same `loom-state` calls and plugin reads. Its `model` and `effort` do not apply either: the phase runs with the session's model and effort. For `effort: high` on design or plan, the user invokes `/loom:design` or `/loom:plan` directly. Mention this in one `Warning:` line when the phase is design or plan.
4. **Use its final message.** End with the phase's own final message, not with this skill's. Add the `Warning:` lines of step 2.

Never run a phase that `next.command` does not name, except research after the user chose "rerun" in step 2.
