---
name: start-task
description: Starts a task from a GitHub issue, or from free text that becomes an issue - picks the mode and the branch type from the labels, builds the slug, switches to a fresh branch from the updated main branch, and copies the issue into 00-ticket.md in the task directory. Offers to restore an archived task.
disable-model-invocation: true
argument-hint: "<#issue | free text> [--oneshot | --quick | --full]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Bash(loom-state --slug *) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Start Task

You turn one GitHub issue into a task: a mode, a branch `<type>/<n>-<slug>` from the updated main branch, and a task directory with `00-ticket.md`. You write no other artifact and no code.

## State

Current task state from `loom-state`:

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json`

Arguments: $ARGUMENTS

"Today" below means `today` from the state. If the state is empty, use the session's current date.

## Shared rules

Read these files in full before you start:

- `${CLAUDE_SKILL_DIR}/references/ticket-template.md` (the `00-ticket.md` file)
- `${CLAUDE_PLUGIN_ROOT}/skills/backlog/references/issue-format.md` (an issue from free text)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/frontmatter.md` (ticket frontmatter)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/git-flow.md` (confirmations, stash, single-quoted titles)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md` (style of an issue and the final message)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/bash-calls.md` (one command per Bash call: no `cd`, no chaining)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

Below, `<main>` is `mainBranch` and `<workDir>` is `workDir`, both from the state; `<drafts>` is `<workDir>/_drafts`.

### Arguments

- `#<n>` or `<n>` (digits only): the issue number.
- `--oneshot`, `--quick`, or `--full`: forces the mode. More than one mode flag: ask which one.
- Any other text: free text for a new issue (step 2).
- Nothing: stop with `Result: no issue given`, `Next: /loom:backlog to pick an issue, then /loom:start-task #<n>`.

## 1. Check preconditions

Stop at the first failed check. Report it in the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`.

| Check | Stop message (`Result:` line) | `Next:` |
|---|---|---|
| The state is empty | `loom is not set up in this project (no .claude/loom.json)` | `/loom:setup` |
| `gh issue list --limit 1` fails | `gh cannot read the issues: <the error>` | `gh auth login, then /loom:start-task <arguments>` |

The working tree is checked in step 7, after you know the task.

## 2. Free text: create the issue

Skip this step when the argument names an issue.

1. Draft one issue from the text, as `issue-format.md` describes: title, labels (`type:`, `size:`, and `mode:` only by its rule), and body. Use only labels that exist (`gh label list --json name --limit 200`).
2. Show the draft. Ask for confirmation. The user may change it.
3. After "yes", write the body to `<drafts>/issue-start-task.md` (if the file exists, Read it first: the Write tool refuses to overwrite an unread file) and run `gh issue create --title '<title>' --body-file <drafts>/issue-start-task.md`, plus one `--label '<label>'` per label. Single-quote the title and write every `'` in it as `'\''`.
4. `<n>` is the number at the end of the URL that `gh issue create` prints.

## 3. Read the issue

Run `gh issue view <n> --json title,body,labels,url,state`.

- It fails: stop with `Result: issue #<n> not found: <the error>`, `Next: /loom:backlog`.
- `state` is `CLOSED`: ask whether to start it anyway.
- The title is `Set up loom`: stop with `Result: #<n> is the setup task`, `Next: /loom:setup` (setup owns its branch and ticket).

## 4. Existing task directory

Look for a task directory of the issue, matched by number:

1. `<workDir>/<n>-*` exists (the task was started before):
   - Its branch `*/<n>-*` exists (`git branch --list '*/<n>-*'`): ask whether to switch to it. After "yes", run `git switch <that branch>` (step 7 checks the working tree first). Do not change the ticket. Go to step 9.
   - No branch exists: ask whether to create the branch for the existing task directory (steps 5 to 7, keep the directory and its ticket) or to stop.
2. `<workDir>/_archive/<n>-*` exists and no active directory exists: offer **restore** or **start fresh**.
   - **Restore**: run `mv <workDir>/_archive/<dir> <workDir>/`. The ticket keeps its mode. Take `<slug>` from the directory name (the part after `<n>-`). Continue with step 6 for the type and step 7 for the branch; if a branch `*/<n>-*` exists, switch to it instead of creating one. Then go to step 9.
   - **Start fresh**: continue with step 5. The archive stays as it is.
3. Neither exists: continue with step 5.

## 5. Mode

Take the first rule that applies:

1. A mode flag in the argument: use it.
2. A `mode:*` label (`mode:oneshot`, `mode:quick`, `mode:full`): use it.
3. A `size:*` label: propose the mapped mode, `S` → oneshot, `M` → quick, `L` → full. Confirm it with the user.
4. No label: propose a mode from the issue's scope (oneshot: a trivial, obvious change; quick: a small or medium change with a clear design; full: a larger feature or unclear behavior). Confirm it with the user.

`size` for the ticket comes from the `size:*` label only. Without the label, the ticket has no `size` line.

## 6. Branch type and slug

1. **Type**: the `type:*` label (`feat`, `fix`, `chore`, `docs`, `refactor`). No label, or another value: propose one and confirm it with the user.
2. **Slug**: run `loom-state --slug '<issue title>'`. Single-quote the title and write every `'` in it as `'\''`. Use the printed slug exactly; never build it yourself. (The rule: lowercase ASCII, every run of other characters becomes `-`, at most 5 words and 40 characters.)
3. `<branch>` is `<type>/<n>-<slug>`. `<task dir>` is `<workDir>/<n>-<slug>`.

Ask the confirmations of steps 5 and 6 together, in one message.

## 7. Branch

1. **Working tree.** If `workingTree` is `dirty`, refuse. Show `git status --short`. Offer the stash of `git-flow.md` (confirmation), with `<workDir>` in place of `<task dir>` when no task is active. Without "yes", stop: `Result: working tree has uncommitted changes`, `Next: stash or commit them (on a task branch, /loom:next continues that task), then /loom:start-task #<n>`.
2. **Existing branch.** If `git rev-parse --verify --quiet refs/heads/<branch>` succeeds, or `git branch --list '*/<n>-*'` lists another branch for the issue, ask: switch to it (it keeps its commits), or stop. Never delete or reset a branch.
3. **Update the main branch.** Run `git switch <main>`. If `git remote get-url origin` succeeds, run `git pull --ff-only`. If the pull fails (also when `<main>` cannot fast-forward), stop with `Result: git pull failed on <main>: <the error>` and `Next: /loom:start-task #<n>` after the user fixes it.
4. **Create the branch.** Run `git switch -c <branch>`.

## 8. Write the ticket

Write `<task dir>/00-ticket.md` from `ticket-template.md`:

| Field | Value |
|---|---|
| `task` | `<n>-<slug>` |
| `phase` | `ticket` |
| `mode` | the mode of step 5 |
| `size` | the `size:*` value (`S`, `M`, or `L`); omit the line without the label |
| `issue` | `<n>` |
| `url` | the issue `url` |

- The body is a verbatim copy of the issue: the title as the `# ` heading, the labels (comma-separated, or `None`), the URL, then the issue body exactly as `gh issue view` returned it. Do not reword, shorten, or fix it.
- Do not add other frontmatter fields. The ticket has no `status` and no `updated`.

## 9. Final message

Run `loom-state --json`. Check that `task.number` is `<n>` and `task.mode` is the chosen mode; add a `Warning:` line for each problem and for each entry of `warnings`.

Use the `final-answer.md` format:

```text
Artifact: <task dir>/00-ticket.md
Status: <mode> mode, branch <branch>
Next: /clear, then /loom:next
```

- `Next:` comes from `next.command`, mapped as `final-answer.md` describes (normally `/clear, then /loom:next`).
- Omit the `Open questions` line: the ticket has none.
