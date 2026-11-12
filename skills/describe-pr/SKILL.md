---
name: describe-pr
description: After the last implementation phase - writes the task summary and ADRs into the docs directory, proposes an architecture overview update, commits the docs, rebases on the main branch, drafts the PR body with the plan attached, and after confirmation pushes and opens the PR. Then proposes follow-up issues.
disable-model-invocation: true
argument-hint: "[notes for the PR]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Describe PR

You turn the finished task into durable docs and a pull request. You distill the working artifacts of the task directory into the committed docs directory, then open the PR.

## State

Current task state from `loom-state`, with the pull request state:

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr`

Arguments: $ARGUMENTS

"Today" below means `today` from the state. If the state is empty, use the session's current date.
`task.dir` is relative to the project's git top level (your working directory), never to the plugin directory.

## Shared rules

Read these files in full before you start:

- `${CLAUDE_SKILL_DIR}/references/summary-template.md` (the task summary)
- `${CLAUDE_SKILL_DIR}/references/adr-template.md` (one ADR)
- `${CLAUDE_SKILL_DIR}/references/pr-template.md` (the PR body)
- `${CLAUDE_PLUGIN_ROOT}/skills/backlog/references/issue-format.md` (follow-up issues)
- `${CLAUDE_PLUGIN_ROOT}/skills/implement/references/log-format.md` (how to read `log.md`)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/git-flow.md` (checks, docs commit, rebase, push, confirmations)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/visual-conventions.md` (trees and diff blocks in docs and the PR)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md` (style of docs, ADRs, and the PR)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/bash-calls.md` (one command per Bash call: no `cd`, no chaining)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

### Configuration

Take every configuration value from the state, never from `.claude/loom.json`: `mainBranch`, `checks.check`, the doc paths (`docs`, the docs map), and `pullRequest.requiredSections`. Never build a doc path yourself.

Below, `<main>` is `mainBranch`, `<n>` is `task.number`, `<slug>` is `task.slug`, and `<task dir>` is `task.dir`. The doc paths:

| Placeholder | From the state |
|---|---|
| `<tasks>` | `docs.tasks`: the directory of task summaries |
| `<decisions>` | `docs.decisions.dir`: the directory of ADRs |
| `<pattern>` | `docs.decisions.pattern`: the ADR file name, e.g. `<NNNN>-<slug>.md` |
| `<overview>` | `docs.overview`: the architecture overview |
| `<docs paths>` | `docs.dir` and every path of `docs`; `workingTreeDocsOnly` counts a change at or below one of them as a docs change |

### Mode differences

| | oneshot | quick, full |
|---|---|---|
| Task summary `<tasks>/<n>-<slug>.md` | no | yes |
| ADRs | no | for resolved decisions with `ADR? = yes` |
| `<overview>` update | proposed if the architecture changed | proposed if the architecture changed |
| Docs commit | only if `<overview>` changed | if any docs file changed |
| PR body | short: `Closes`, Why, Verification | full: `Closes`, Why, Special things to note, Change outline, Verification, Decisions, with the plan attached |

## 1. Check preconditions

Read the state above. Stop at the first failed check. Report it in the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`.

| Check | Stop message (`Result:` line) | `Next:` |
|---|---|---|
| The state is empty | `not a loom project (no .claude/loom.json)` | `/loom:setup` |
| `onMain` is `true` | `on the main branch; no task` | `/loom:start-task #<n>` |
| `task` is `null` | `branch <branch> matches no task` | `/loom:start-task #<n>` |
| `task.archived` is `true` | `task #<n> is archived` | `/loom:start-task #<n>` (offers a restore) |
| `rebaseInProgress` is `true` | `a rebase of <branch> is in progress` | `/loom:iterate rebase` |
| `workingTree` is `null` | `git status failed: <the error from its warning>` | `fix the git error, then /loom:next` |
| `pr.state` is `MERGED` | `PR #<number> is merged` | `/loom:finish-task` |
| `pr.state` is `OPEN` | `PR #<number> is already open; change it with /loom:iterate` | from `next.command` |
| `implementation.blocked` or `implementation.inProgress` is set | `implementation is not finished` | from `next.command` |
| `implementation.total` is `0`, or `implementation.done` is less than `implementation.total` | `implementation is not finished (<done> of <total> phases done)` | from `next.command` |
| Not oneshot, and `04-plan.md` is not `approved` | `04-plan.md changed and is not approved again` | from `next.command` |
| `workingTree` is `dirty` and `workingTreeDocsOnly` is `false` (code changes) | `working tree has uncommitted code changes` | `/loom:iterate` with no argument (it keeps the changes as a fix, or stashes or discards them) |
| `task.pr` is set and `pr` is `null` (`gh` failed) | `PR #<task.pr> state unknown (gh: <the gh warning>)` | — (fix `gh`, then run `/loom:describe-pr` again) |
| `warnings` says `gh` is not installed | `gh is not installed; the PR needs it` | — |

- If `pr.state` is `OPEN` and `task.pr` is not set, an earlier run created the PR but stopped. Write `pr: <number>` into the `00-ticket.md` frontmatter (step 8), then stop with the `PR #<number> is already open` row.
- While `task.pr` is not set, other `gh` warnings (for example `gh auth login` is missing, or the repository has no remote) do not stop it here. Steps 3-8 still write the docs and `pr-body.md`; step 8 stops when the push or `gh pr create` fails. With `task.pr` set, a failed `gh` stops it (the row above): the PR may exist, so do not redo the docs, the rebase, or the PR.
- Re-running after a partial failure is safe: every step below checks what already exists.
- A working tree that is dirty only in the docs paths (`workingTreeDocsOnly` is `true`) is an earlier partial run of this skill: it wrote docs and stopped before the docs commit. Continue. Steps 3-5 update those files in place; step 6 commits them. Show `git status --porcelain -- <docs paths>` in a `Warning:` line so the user sees what the earlier run left.

## 2. Read the task

Read in full, without offset or limit:

- `<task dir>/00-ticket.md`, `<task dir>/log.md`.
- quick and full: `<task dir>/04-plan.md`, `<task dir>/02-research.md`, and `<task dir>/03-design.md` if it exists. Do not read `*.superseded.md` files.
- `<overview>` if it exists. List `<decisions>`.

Read the code history:

- The base is `origin/<main>` if `git remote get-url origin` succeeds, else `<main>`.
- `git log --format='%h %s%n%b' <base>..HEAD`: the phase commits and fix commits.
- `git diff --stat <base>...HEAD`, and `git diff <base>...HEAD` where you need detail.

Take the issue title from the first `# ` heading of `00-ticket.md`.

## 3. Task summary (quick and full)

Write `<tasks>/<n>-<slug>.md` from `summary-template.md`:

- If the file exists (a re-run), update it in place. Keep text that is still true.
- **Key Decisions**: the resolved decisions of `03-design.md` and `04-plan.md` that matter after the merge, with links to their ADRs (step 4).
- **Implementation**: one line per implementation phase with its commit subject. Do not write hashes; the rebase and the squash merge change them.
- **Process metrics**: if `task.metrics` in the state is not `null`, end the Implementation section with the line `Process metrics: <task.metrics.line>`. Copy `task.metrics.line` exactly. If `task.metrics` is `null`, write no Process metrics line. Never estimate the numbers yourself.
- **Deviations from Plan**: from `log.md` (`Deviations:`, `Additions:`, `Fix:` lines, and `## Plan change` entries).
- **Verification**: the checks and the manual steps. Mark a manual step as passed only if the user confirmed it.
- **Follow-ups**: out-of-scope items, worthwhile nits, and open risks. Step 9 proposes them as issues.
- Remove every guidance comment.

## 4. ADRs (quick and full)

For each row of `## Resolved Decisions` in `03-design.md` and `04-plan.md` with `ADR?` = `yes`:

1. Skip it if an ADR for it exists: an ADR in `<decisions>` with `Task: #<n>` and the same decision.
2. Number: the highest number of the files in `<decisions>` whose names match `<pattern>` (its `<N…N>` placeholder holds the number), plus 1. Pad it with zeros to the length of the placeholder: `<NNNN>` gives four digits, so the default numbering starts at `0001`; `<NNN>` starts at `001`. Create the directory if it is missing.
3. Write `<decisions>/<file name>` from `adr-template.md`. The file name is `<pattern>` with the number and the ADR slug filled in. The `<slug>` inside `<pattern>` is the ADR slug that `adr-template.md` defines, not `task.slug`. A number longer than the placeholder is written in full, never cut (`<NN>` and ADR 100 give `100`). The title is `# <number>. <Decision title>`, with the same digits as the file name. `Status: Accepted · Task: #<n> · Date: <today>`.
4. Context, Alternatives Considered, and Consequences come from the question, its options, the design, and the research. A decision taken by the round cap ("accepted by default") gets that fact in its Context.
5. Link the ADR from the task summary's Key Decisions.

## 5. Architecture overview

1. Compare the change (the diff, the design, and the ADRs) with `<overview>`. The architecture changed if the task:
   - adds, removes, or renames a component, module, or service
   - changes the data flow or a protocol between components
   - adds a major library or an external dependency
2. If it changed, propose an update:
   - Show the change as a `diff` block of `<overview>`.
   - Ask the user to accept, change, or skip it. Apply it only after "yes".
3. If `<overview>` does not exist, do not create it. Add `Warning: <overview> is missing (/loom:setup creates it)`.

## 6. Docs commit

1. Run `git status --porcelain -- <docs paths>`.
   - oneshot: commit only if `<overview>` changed.
   - quick and full: commit if any file in `<docs paths>` changed.
2. If nothing changed, make no commit.
3. Otherwise stage the changed docs files (`git add -- <paths>`). Write `docs(#<n>): record decisions and summary` to `<task dir>/commit-msg.txt` and run `git commit -F <task dir>/commit-msg.txt`. If `commit-msg.txt` exists, Read it before you Write it (`git-flow.md`).

## 7. Rebase

Follow the Rebase rules of `git-flow.md`: the guarded `git fetch origin <main>`, then `git rebase origin/<main>` (or `<main>` without a remote `origin`), and the conflict rules.

- If the rebase brought changes (`HEAD` changed), run `checks.check` again.
- If the checks fail: do not push. Stop with `Result: checks fail after the rebase on <base>` and `Next: /loom:iterate <the failing check and its key lines>`. `/loom:iterate` fixes it as code feedback.

## 8. Pull request

### Draft

1. **Title**: Conventional Commits, `<type>(<scope>): <summary of the task> (#<n>)`. `<type>` is the branch type. `<scope>` and `<summary>` follow `git-flow.md`. This title becomes the squash commit on `<main>`.
2. **Body**: write `<task dir>/pr-body.md` from `pr-template.md`. A re-run finds the file of the earlier run: Read it before you Write it (`git-flow.md`).
   - quick and full, in this order: `Closes #<n>`, Why, Special things to note, Change outline, Verification, Decisions, then the body of `04-plan.md` (without frontmatter) inside `<details><summary>Implementation plan</summary>`.
   - oneshot: only `Closes #<n>`, Why, and Verification. Keep it short.
   - **Why** is exactly one sentence of at most 25 words: the problem or need this PR answers (from `00-ticket.md`). It is not a list of what changed.
   - **Special things to note** has 1-3 list items, most important first: only what a reviewer must know and cannot see quickly in the diff. Candidates: a deviation or addition from `log.md`, a risk, a non-obvious decision, a migration or manual step (also a manual verification step the user has not confirmed), a known limit. If nothing qualifies, write the single line None. (plain text, no backticks); never add filler.
   - **Change outline** has one line per implementation phase (`1. <phase name> — <commit subject>`), then one visual: a file tree of the changed files only, or an interface `diff` block with only signatures and public API. Pick the one that shows the shape of the change better (`visual-conventions.md`). Omit unchanged parts.
   - Decisions links the new ADRs and the task summary by their repository paths.
   - **Required sections**: `pullRequest.requiredSections` from the state lists headings that the project's PR template or a CI check requires (empty by default). A required heading that the layout above already has (the same heading line, e.g. `## Verification`) is that section. Write every other required heading after Decisions (oneshot: after Verification), before `<details>`, in the order of the list, exactly as listed. Fill it from the task's artifacts, or write the single line None. (no backticks) when nothing applies.
   - Remove every guidance comment. Add the user's notes from the argument where they fit.
3. **Size**: count the characters of the body. If it is longer than 60,000, replace the plan inside `<details>` with its `## Phase Overview` section and the line `The full plan is longer than the PR body allows; only its Phase Overview is attached.`

### Confirm, push, create

1. Show the title, the body (the `pr-body.md` you wrote above), and the commits to push (`git log --oneline <base>..HEAD`).
2. Ask for one confirmation for both actions: push the branch and open the PR.
3. After "yes":
   - Push as `git-flow.md` describes. Normally the branch has no upstream yet: `git push -u origin <branch>`. If an upstream exists and the rebase rewrote its commits, use `git push --force-with-lease`.
   - `gh pr create --base <main> --title '<title>' --body-file <task dir>/pr-body.md`. Quote the title with the single-quote rule of `git-flow.md` (every `'` becomes `'\''`).
4. If `git remote get-url origin` fails, or `gh pr create` fails (for example `gh auth login` is missing), stop with `Result: <the error>`. The docs commit stays; a re-run continues.

### Record

- Take the PR number from the URL that `gh pr create` prints (`…/pull/57` → `57`).
- Write `pr: <number>` into the `00-ticket.md` frontmatter: replace an existing `pr:` line, or add it before the closing `---`. Change nothing else in the ticket.

## 9. Follow-up issues

1. Collect follow-ups: the task summary's Follow-ups (oneshot: worthwhile nits and open problems from `log.md`).
2. If there are none, skip this step.
3. Draft each follow-up as an issue in the format of `issue-format.md`: Context starts with `Follow-up from #<n>` and links the PR.
4. Show the drafts. Ask the user which ones to create. Create only confirmed issues, with `gh issue create` as `issue-format.md` describes.

## 10. Final message

Run `loom-state --json`. Use the `final-answer.md` format:

```text
Result: PR #<number> opened: <url>
Warning: <one line per warning, if any>
Next: /clear, then /loom:finish-task
```

- Add `Docs: <the files written or changed>` and `Issues: <#k, #m>` (created follow-ups) after `Result:`, one line each, when they exist.
- `Next:` comes from `loom-state` (`next.command` is normally `/loom:finish-task`; it watches the checks).
