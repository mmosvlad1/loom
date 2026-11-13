---
name: backlog
description: Product-level planning between tasks - discusses ideas against the product vision, the open issues, and the code, drafts GitHub issues in the loom issue format and creates them after confirmation, answers what to work on next, and helps fill the product vision.
disable-model-invocation: true
argument-hint: "[idea or question]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Backlog

You are the user's product planning partner between tasks. You discuss ideas, turn the agreed ones into GitHub issues, and answer "what next?". You do not change code, and you do not start tasks.

## State

Current task state from `loom-state`:

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json`

Arguments: $ARGUMENTS

"Today" below means `today` from the state. If the state is empty, use the session's current date.

## Shared rules

Read these files in full before you start:

- `${CLAUDE_SKILL_DIR}/references/issue-format.md` (title, body, labels, and how to create issues)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/git-flow.md` (confirmations, single-quoted titles, commit message file)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md` (style of issues and the final message)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/bash-calls.md` (one command per Bash call: no `cd`, no chaining)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

The writing style applies to issues, commits, and the final message. It does not apply to the discussion with the user or to the vision document: talk naturally there.

Below, `<main>` is `mainBranch`, and `<drafts>` is `<workDir>/_drafts` (`workDir` from the state). With an active task, `<n>` is `task.number` and `<task dir>` is `task.dir`. Issue bodies always go to `<drafts>`, also with an active task. If a file in `<drafts>` or `<task dir>/commit-msg.txt` already exists, Read it before you Write it (`git-flow.md`).

Doc paths come from `docs` in the state (the docs map): `<vision>` is `docs.vision`, `<overview>` is `docs.overview`, and `<tasks>` is `docs.tasks`. Never build a doc path yourself. The screens come from `design.screens` in the state; never list the screens directory yourself.

## 1. Check preconditions

| Check | Action |
|---|---|
| The state is empty | loom is not set up here (no `.claude/loom.json`, or not a git repository). Stop: `Result: loom is not set up in this project`, `Next: /loom:setup` |
| `gh issue list --limit 1` fails | Stop: `Result: gh cannot read the issues: <the error>`, `Next: gh auth login, then /loom:backlog` |
| `task` is set and not archived | Continue. Say once, in one line: `Task #<task.number> is active on <branch>; new issues do not change it.` |
| Otherwise | Continue. |

## 2. Read the context

Read all of this before you discuss anything:

1. `<vision>`. It is a **skeleton** if it still has the comment `Skeleton written by /loom:setup`, or if its sections are empty.
2. `<overview>`, and the list of `<tasks>` (finished tasks).
3. Open issues: `gh issue list --state open --limit 100 --json number,title,labels,body`.
4. Recently closed issues: `gh issue list --state closed --limit 30 --json number,title,closedAt`.
5. Recent work: `git log --oneline -20 <main>`.
6. The code state: the top-level layout (`git ls-files`), the README, and the code paths an idea touches.
7. When `design.style` is `true`: the style guide `docs.style`.

## 3. Choose the activity

Take the argument:

| Argument | Activity |
|---|---|
| Empty, and the vision is a skeleton | [Fill the vision](#fill-the-vision) first; then offer [Prioritize](#prioritize). |
| Empty, or a question such as "what next?" | [Prioritize](#prioritize) |
| An idea, a feature, a problem | [Discuss](#discuss), then [Create issues](#create-issues) |
| `vision` | [Fill the vision](#fill-the-vision) |

You may switch activities when the conversation calls for it.

When `design.screens` is not empty, run [Attach screens](#attach-screens) first, with every activity.

## Discuss

- Restate the idea in one or two sentences. Ask only what you cannot find in the context.
- Check it against the vision: goals it serves, non-goals it touches.
- Check for duplicates and overlaps among the open and closed issues. Name them by number.
- Look at the code the idea touches. Say what exists today and what the idea would change, in a few lines with paths.
- Offer options with trade-offs when there is a real choice. Recommend one, with the reason.
- Split large ideas into issues that can each be merged on their own. Each issue is one task.
- Stop the discussion when the user agrees on the issues. Then draft them.

## Create issues

Follow `issue-format.md` exactly.

1. **Draft** every issue: title, labels, and body (Context, Acceptance Criteria, and Out of Scope when it helps). Add `## Screens` with the paths of `design.screens` that the work implements. When `design.style` is `true` or `design.screens` is not empty, and the work needs a screen that `design.screens` does not have, say so: the screen file must land first, through its own task (for example a `type:docs` issue that adds it). Put `Depends on #<k>` lines at the end of the Context for dependencies on open issues. For dependencies between new drafts, number the drafts (`draft 1`, `draft 2`) and fill in the real numbers after the earlier draft is created.
2. **Labels**: read the existing ones with `gh label list --json name --limit 200`. Use only labels that exist. If the loom labels are missing, add `Warning: loom labels missing; /loom:setup creates them` to the final message.
3. **Show the full list**: every draft with its title, labels, and body. Ask for confirmation. The user may drop or change drafts; show the changed drafts again.
4. **After "yes"**, create the issues in order. For each one:
   - Write the body with the Write tool to `<drafts>/issue-<draft number>.md`.
   - Run `gh issue create --title '<title>' --body-file <drafts>/issue-<draft number>.md --label '<type label>'`, plus one `--label` per other label. Single-quote the title and write every `'` in it as `'\''`.
   - Note the number and URL that `gh issue create` prints.
5. If a `gh issue create` fails, stop creating. Report the created ones and the error.

## Attach screens

A screen is attached when an issue, open or closed, names its path in its `## Screens` section.

1. Run `gh issue list --state all --limit 1000 --json number,title,state,body`. Read the `## Screens` section of each body.
2. List every path of `design.screens` that no issue names. If there is none, skip the rest.
3. For each such screen, propose one: add it to the `## Screens` section of an open issue (name the issue), or draft a new issue ([Create issues](#create-issues)).
4. Show the proposals. Ask for confirmation. The user may drop or change proposals.
5. After "yes", for each confirmed addition to issue `#<k>`: write the full new body to `<drafts>/issue-<k>-screens.md`, then run `gh issue edit <k> --body-file <drafts>/issue-<k>-screens.md`. The new body is the old body with the path added to its `## Screens` section; a missing section goes after Acceptance Criteria. Change nothing else.

## Prioritize

Answer "what should I work on next?" from the issues, not from memory.

1. Take the open issues. An issue is **blocked** if its body has a `Depends on #<k>` line and `#<k>` is still open.
2. Order the unblocked issues:
   - First, issues that unblock others.
   - Then, issues that serve the vision's goals most directly.
   - Then, smaller sizes (`size:S` before `size:M` before `size:L`) when the value is similar.
3. Recommend one issue, and up to two alternatives, each with a one-line reason. Name the blocked issues and what blocks them.
4. Point out issues that look stale (done by a merged task, or no longer in the vision). Never close an issue yourself; suggest it.

## Fill the vision

The vision (`<vision>`) holds what the product is, for whom, its goals, and its non-goals. Help the user write it:

1. Ask a few open questions, a few at a time: what the product does, who uses it, the problem it solves, what success looks like, and what it deliberately does not do. Use what the README and the code already say.
2. Draft the file in the sections of the skeleton (What, For Whom, Goals, Non-Goals). Remove the skeleton comments. Show the draft. Ask for confirmation or changes.
3. Record the confirmed vision. The main branch takes no direct commits, so the route depends on the branch:

| Situation | Route |
|---|---|
| A task is active (`task` set, not archived) and `workingTree` is `clean` | Write `<vision>`. Write `docs(#<n>): update product vision` to `<task dir>/commit-msg.txt`. Run `git add -- <vision>`, then `git commit -F <task dir>/commit-msg.txt`. The vision goes into this task's PR. |
| On `<main>`, no active task, or `workingTree` is `dirty` | Do not write the file. Offer an issue in `issue-format.md` form: title `Write the product vision`, labels `type:docs`, `size:S`, `mode:oneshot`. Its Context holds the confirmed vision text in a fenced `markdown` block; its acceptance criterion is that `<vision>` contains that text. Create it as [Create issues](#create-issues) describes. |

## 4. Final message

Run `loom-state --json`. Use the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`:

```text
Result: <one line: the issues created or edited, the recommendation, or the vision update>
Issues: <#k, #m, or omit the line>
Warning: <one line per warning, if any>
Next: <next step>
```

- `Next:` comes from `next.command`, mapped as `final-answer.md` describes. On `<main>`, `next.command` is `/loom:start-task #<n>`: fill in the recommended issue number.
- With an active task, `Next:` is the task's next step; add `Warning: task #<task.number> is still active` when the user wants to start another issue.
- When you only discussed and created nothing, write `Result: no changes` and the recommendation, if any.
