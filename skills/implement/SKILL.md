---
name: implement
description: Builds the approved plan one implementation phase at a time - a fresh loom implementer per phase, checks enforced by a hook and run again here, a loom reviewer, then one commit per phase and a log.md entry. Auto-advances unless a phase needs manual verification. In oneshot mode it builds one phase from 00-ticket.md. Resumes an interrupted phase.
disable-model-invocation: true
argument-hint: "[implementation phase number] [all | step]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Implement

You orchestrate the implementation of the task. For each implementation phase you run a fresh `loom:implementer`, run the checks, run `loom:implementation-reviewer`, commit, tick the plan, and write `log.md`. You do not edit code yourself.

## State

Current task state from `loom-state`, with the pull request state (a plan change after the PR can add implementation phases):

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr`

Arguments: $ARGUMENTS

"Today" below means `today` from the state. If the state is empty, use the session's current date.
`task.dir` is relative to the project's git top level (your working directory), never to the plugin directory.

## Shared rules

Read these files in full before you start:

- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/implementation-loop.md` (implementer, checks, reviewer, fix attempts, results)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/git-flow.md` (checks, commit message, staging, confirmations)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/pr-update.md` (docs refresh and push when the PR is already open)
- `${CLAUDE_SKILL_DIR}/references/log-format.md` (the exact `log.md` entries)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/frontmatter.md` (artifact statuses and gates)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md` (style of `log.md`, commits, and the final message)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/bash-calls.md` (one command per Bash call: no `cd`, no chaining)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

### Configuration

The state holds the resolved check commands (`checks`) and doc paths (`docs`). Take them from there, never from `.claude/loom.json`. Pass `checks` and `docs.conventions` to the agents as the configuration lines of `implementation-loop.md`.

Read `.claude/loom.json` at the git top level for the other keys. If a key is missing, use the default:

| Key | Default |
|---|---|
| `implement.maxFixAttempts` | `2` |
| `implement.autoAdvance` | `true` |
| `hooks.maxCheckAttempts` | `3` |

Below, `<n>` is `task.number` and `<task dir>` is `task.dir`.

### The `Next:` line

Compute `Next:`; never remember it. After your last write, run `loom-state --json` and map `next.command` as `final-answer.md` describes. A stop before any write uses `next.command` from the state above, unless its table names a fix (for example `/loom:setup`).

## 1. Check preconditions

Read the state above. Stop at the first failed check. Report it in the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`.

| Check | Stop message (`Result:` line) | `Next:` |
|---|---|---|
| The state is empty | `not a loom project (no .claude/loom.json)` | `/loom:setup` |
| `onMain` is `true` | `on the main branch; no task` | `/loom:start-task #<n>` |
| `task` is `null` | `branch <branch> matches no task` | `/loom:start-task #<n>` |
| `task.archived` is `true` | `task #<n> is archived` | `/loom:start-task #<n>` (offers a restore) |
| `task.mode` is not `oneshot`, `quick`, or `full` | `00-ticket.md has no valid mode` | from `next.command` |
| `implementation.blocked` is set | `implementation phase <k> is blocked: <reason>` | `/loom:iterate <fix>` |
| Not oneshot, and `04-plan.md` is missing or not `approved` | `implement needs an approved 04-plan.md (status: <status or missing>)` | from `next.command` |
| Not oneshot, and `implementation.total` is `0`, or a warning names `04-plan.md` | `04-plan.md has no parseable Phase Overview` | `/loom:iterate <feedback>` |
| `implementation.total` > 0 and `implementation.done` equals `implementation.total` (clean or dirty working tree) | `all implementation phases are done` | from `next.command` (for example `/clear, then /loom:describe-pr`; `/loom:finish-task` with an open PR; `/loom:iterate <feedback>` when code changes are uncommitted) |

- The plan is the gate: implement starts only when `04-plan.md` is `approved`. In oneshot mode there is no plan; the ticket is the reference.
- A blocked implementation phase is never resumed here, also with a dirty working tree. `/loom:iterate` fixes it.

Warnings (do not stop):

- `02-research.md` has `stale: true`: add `Warning: research is stale (<staleFiles>); the plan may not match the code`.

## 2. Resume flow

Run this step if `workingTree` is `dirty` or `implementation.inProgress` is set. Otherwise go to section 3.

1. Find the interrupted work:
   - `implementation.inProgress` names phase N, or else N is the first implementation phase that is not `done`.
   - Run `git status --porcelain`. List the changed files outside `<task dir>`.
2. Check whether phase N is already committed (the run stopped after the commit, before `log.md`):
   - The base is `origin/<main>` if `git remote get-url origin` succeeds, else `<main>` (`<main>` is `mainBranch`).
   - Run `git log --format='%h %s' --grep='^Phase N:' <base>..HEAD`. Match the number only (oneshot: `Phase 1:`).
   - If a commit exists, do not implement phase N again. Do only items 5 and 6 of section 4 (tick the plan; append the `done` entry with that commit's short hash and `Checks: not recorded (resumed after the commit)`). Then, if the working tree is still dirty, continue with item 3 below for the remaining changes; otherwise continue with section 5.
3. Ask the user one question. Show phase N and the changed files, then offer three choices:
   - **resume**: keep the changes and continue phase N. The implementer continues from the working tree.
   - **stash**: move the changes to `git stash`, then start phase N on a clean working tree. The user can restore them later with `git stash pop`.
   - **discard**: delete the changes, then start phase N on a clean working tree. Say clearly: **discarded changes cannot be recovered.**
4. Stash and discard change the working tree. Confirm them before you run anything, and follow "Stash and discard" in `git-flow.md` exactly:
   - Show the exact commands and the files they touch. Ask for "yes".
   - **stash**: first `git check-ignore -q <task dir>`, then the plain or the pathspec form of `git stash push --include-untracked`, with the message `'loom #<n> phase N <today>'`. Check the exit status; on failure stop with its output.
   - **discard**: `git restore --source=HEAD --staged --worktree -- <tracked changed paths>`, then `git clean -f -- <untracked paths>`. Name every path. Never touch `<task dir>`.
   - Without "yes", stop with `Result: nothing changed` and `Next: choose resume, stash, or discard with /loom:implement, or commit the changes yourself`.
5. Continue with section 3. Phase N is the first implementation phase to run. If you chose **resume**, tell the implementer that the working tree already contains part of the work.

If the changed files clearly do not belong to phase N (an unrelated edit of the user), say so in the question. The commit of phase N will include only the files of phase N; you ask about the rest when you stage.

## 3. Choose the implementation phases

1. **Inputs.** Read in full, without offset or limit:
   - oneshot: `<task dir>/00-ticket.md`.
   - quick and full: `<task dir>/04-plan.md`. Read `<task dir>/log.md` if it exists.
   - Do not read `01-research-questions.md` or `*.superseded.md` files. The agents read what they need themselves.
2. **First phase.**
   - oneshot: phase 1, the only implementation phase.
   - The argument starts with a number `k`: phase k. Refuse if phase k does not exist (`Result: 04-plan.md has no implementation phase k`), if it is `done` (`Result: implementation phase k is done; change it with /loom:iterate`), or if an earlier phase is not `done` (`Result: implementation phase <j> is not done; implementation phases run in order`).
   - Otherwise: the resume phase from section 2, or the first phase in `implementation.phases` that is not `done`.
3. **Run mode.** Take the first match:

   | Argument or request | Run mode |
   |---|---|
   | `all`, or "do all phases and stop at the end" | **all**: run every remaining phase. Do not stop for manual verification; collect the manual steps for the end. |
   | `step`, or "stop after every phase" | **step**: stop after every implementation phase. |
   | `implement.autoAdvance` is `false` | **step** |
   | Otherwise | **auto**: continue to the next phase unless the stop rules in section 5 apply. |

   A blocked phase always stops the run, in every run mode.

## 4. Run one implementation phase

For implementation phase N:

1. **Start.** Append `## Phase N — in-progress` to `<task dir>/log.md` (create the file if it is missing), in the form of `log-format.md`. Skip this when the last entry of phase N is already `in-progress` (a resumed phase).
2. **Loop.** Run the shared `implementation-loop.md` in phase mode:
   - Reference: the plan path `<task dir>/04-plan.md` and phase N. oneshot: the ticket path `<task dir>/00-ticket.md`; the reviewer compares the diff with the ticket.
   - Configuration: the `Checks:` line (`checks` from the state) and the `Conventions:` line (`docs.conventions`) in the implementer prompt; the `Conventions:` line in the reviewer prompt.
   - Checks: the `SubagentStop` hook enforces `checks.check` on the implementer, and you run `checks.check` once more after it returns. Failing checks mean the hook gave up after `hooks.maxCheckAttempts` attempts: the phase is blocked.
   - Fix attempts: only `blocking` reviewer items go back, at most `implement.maxFixAttempts` times.
3. **Blocked.** If the result is blocked:
   - Do not commit. Leave the change in the working tree.
   - Append `## Phase N — blocked` and `Reason: <one line>` to `log.md`.
   - Run `loom-state --json` and stop with the final message of section 6. `Next:` is normally `/loom:iterate <fix>`.
4. **Commit.** If the result is done, commit the phase as the shared `git-flow.md` describes:
   - Stage the implementer's `Files changed` of every run with `git add -- <paths>`, then check `git status --porcelain`.
   - Subject: `<type>(<scope>): <summary of phase N> (#<n>)`. `<type>` is the branch type; `<scope>` and `<summary>` follow `git-flow.md`.
   - Body: `Phase N: <name>`, with `<name>` exactly as in `## Phase N: <name>`. oneshot: `Phase 1: oneshot`.
   - Write the message (subject, blank line, body) to `<task dir>/commit-msg.txt` with the Write tool; if the file exists, Read it first (`git-flow.md`). Run `git commit -F <task dir>/commit-msg.txt`.
5. **Tick the plan** (quick and full):
   - In `## Phase Overview`, change `- [ ] N.` to `- [x] N.`.
   - In `## Phase N:` → `### Verification`, tick every `Automated:` checkbox.
   - Leave `Manual:` checkboxes unchecked; the user ticks them. Change nothing else in `04-plan.md`, also not its frontmatter.
6. **Log.** Append the `done` entry of `log-format.md`: the commit short hash (`git rev-parse --short HEAD`), the checks result, the reviewer verdict with its nits, the deviations, the additions, and the manual verification steps.

## 5. Advance or stop

After a done phase, take the first matching row:

| Condition | Action |
|---|---|
| It was the last implementation phase | Stop: the implementation is finished. If `pr.state` is `OPEN`, first run the shared `pr-update.md` (docs refresh, PR body, push with confirmation). |
| Run mode **step** | Stop after this phase. |
| Run mode **auto**, and the phase lists manual verification | Stop with the manual steps. |
| Otherwise | Run `loom-state --json`. Check that phase N is now `done`. Continue with section 4 for the next implementation phase. |

- A phase **lists manual verification** if its `### Verification` has a `Manual:` line, or the implementer reported `Manual verification needed` items other than `None`.
- In run mode **all**, collect the manual steps of every phase and show them at the end.
- Run every implementation phase in a fresh `loom:implementer`. Never reuse an agent from an earlier phase.

## 6. Final message

Run `loom-state --json` after your last write. Use the `final-answer.md` format:

- `Artifact: <task dir>/log.md`.
- `Status`:
  - one phase done: `implementation phase N of <total> done (<hash>)`.
  - several phases done in this run: `implementation phases 1-3 of 3 done (<hash>, <hash>, <hash>)`.
  - blocked: `implementation phase N blocked: <reason>`. If earlier phases of this run are done, add them before: `implementation phase 1 of 3 done (<hash>); implementation phase 2 blocked: <reason>`.
- `Open questions: 0`.
- `Manual verification:` with the steps of the phases that need them, grouped by phase. Omit it when there are none.
- `Warning:` lines from section 1, and one `Warning:` line per blocking deviation you could not record elsewhere.
- `Next:` from `loom-state`:
  - After the last phase, map `next.command` as `final-answer.md` describes, for example `/clear, then /loom:describe-pr`, or `/clear, then /loom:finish-task` with an open PR.
  - With manual steps, write `run the manual steps, then /clear, then /loom:next` (after the last phase: `then /clear, then /loom:describe-pr`). If a manual step fails, the user runs `/loom:iterate <feedback>`.
  - Blocked: `/loom:iterate <fix>`; the user may add hints, e.g. `/loom:iterate the test needs the fixture from phase 1`.

No recap of the code changes. `log.md` and the commits hold them.
