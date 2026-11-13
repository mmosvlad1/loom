# Git Flow

Rules for commits, checks, rebases, and pushes. `implement`, `iterate`, `describe-pr`, `finish-task`, and `screens` follow them, so the git history of every task has one form.

Below, `<main>` is `mainBranch` from the `loom-state` output, `<n>` is `task.number`, and `<task dir>` is `task.dir`. Never hard-code the main branch name or the work directory.

## What needs confirmation

| Action | Confirmation |
|---|---|
| Local commits, `git rebase`, `git branch -D` of a merged task branch | No |
| `git push` (also `--force-with-lease` on the task branch) | Yes |
| `gh pr create`, `gh pr edit`, `gh pr merge` | Yes |
| `gh issue create`, `gh issue edit` | Yes |
| Repo settings, labels, rulesets: `gh api` calls that change something (`--method POST`, `PUT`, `PATCH`, `DELETE`), `gh label create` | Yes |
| Read-only `gh api` GET calls (no `--method`, no `-f`/`-F` fields), e.g. reading rulesets | No question from the skill. The permission system always asks: `setup` writes `Bash(gh api *)` as an ask rule, so every `gh api` call prompts, also in auto mode. This is intended. |
| `git stash`, discarding changes (`git restore`, `git clean`) | Yes |

- Confirmation means: show exactly what the command does (the commits, the body, the files), ask, and wait for "yes".
- Never push to `<main>`. A hook blocks it.
- Never use `--force`. Use `--force-with-lease`, and only on the task branch.

## Checks

- Run `checks.check` from the `loom-state --json` output (`checks.check`, the resolved command) exactly as configured, from the git top level.
- Run it as one Bash call, also when it chains commands.
- Run it unfiltered: add no pipe into `head`, `tail`, `grep`, `sed`, or similar filters. A hook blocks that, because filtered output hides failures. A configured check that has a pipe itself runs exactly as configured: the hook allows a command that equals a configured check.
- Add no pipe, redirection, or shell variable to it (the shared `bash-calls.md`). Such a command needs a permission prompt, which a subagent or a later turn may not get.
- Read the result from the exit status and the full output.

## Commits

### Subject

`<type>(<scope>): <summary> (#<n>)`

- `<type>`: the branch type, the part of the branch name before `/` (`feat`, `fix`, `chore`, `docs`, `refactor`). Use it for phase commits and for fix commits.
- `<scope>`: one lowercase word for the module the change belongs to: the top-level package, directory, or component that holds most of the changed lines (`auth`, `cli`, `api`). If the changes spread over several modules, take the module that the implementation phase's goal is about.
  - A fix commit takes the scope of the phase commit it fixes.
  - A change of only build, CI, or tool configuration uses `build`, `ci`, or the tool name.
- `<summary>`: imperative mood, lowercase first word, no period at the end. Describe the result, not the process ("add token storage", not "implemented phase 2").
- Keep the whole subject at most 72 characters. Shorten the summary, never the `(#<n>)` suffix.

### Body

The first body line names the implementation phase. The resume flow of `implement`, `iterate`, and the reviewer find phase commits by it (`git log --grep='^Phase N:'`). `loom-state` takes a phase's commit from its `log.md` heading, not from the commits. It reads commit subjects in one place: `loom-state --setup-path` matches the setup commit and the kickoff commit by their exact subjects, so never change these two subjects.

| Commit | Made by | Subject | Body |
|---|---|---|---|
| Phase commit | `implement`; `iterate` for a blocked phase that has no commit yet | `<type>(<scope>): <summary of phase N> (#<n>)` | `Phase N: <name>` (oneshot: `Phase 1: oneshot`) |
| Fix commit | `iterate` | `<type>(<scope>): <summary of the fix> (#<n>)` | `Phase N: <name>`, a blank line, then one `Fix: <item>` line per fix item |
| Docs commit | `describe-pr` | `docs(#<n>): record decisions and summary` | none |
| Task summary update | `iterate` after the PR is open | `docs(#<n>): update task summary` | none |
| Product vision update | `backlog` on a task branch | `docs(#<n>): update product vision` | none |
| Setup commit | `setup` (fast path) | `chore(loom): set up loom (#<n>)` | `Phase 1: oneshot` |
| Kickoff commit | `setup` (onboarding path, before research) | `chore(loom): start loom setup (#<n>)` | none: no `Phase` line |
| Landing commit | `screens` (the first landing of a screens task) | `docs(design): <summary> (#<n>)` | `Phase 1: oneshot` |
| Landing fix commit | `screens` (a later landing) | `docs(design): <summary of the change> (#<n>)` | `Phase 1: oneshot`, a blank line, then one `Fix: <item>` line per change |
| Canvas commit | `screens` (when it creates the canvas) | `docs(design): record the canvas (#<n>)` | none: no `Phase` line |

- `<name>` is the name of `## Phase N: <name>` in `04-plan.md`, exactly.
- Never commit with `--no-verify`, and never amend a pushed commit.

### Commit with a message file

Never pass a commit message on the command line. A plan heading can contain backticks or `$`, which the shell expands inside double quotes, and such a command needs a permission prompt.

1. Write the whole message with the Write tool to `<task dir>/commit-msg.txt`: the subject, a blank line, then the body. The task directory is ignored by git.
2. Run `git commit -F <task dir>/commit-msg.txt`.

The file stays after the commit, and every later commit reuses it. The Write tool refuses to overwrite a file it has not read, so: **if `commit-msg.txt` exists, Read it first, then Write the new message.** The same rule holds for every other reused file in the work directory: issue bodies, `pr-body.md`, and the files in `<workDir>/_drafts/`. Do not delete these files; they are ignored by git.

Example file of a phase commit:

```text
feat(auth): add token storage (#42)

Phase 2: Wire `TokenStore` to real storage
```

### One-line titles

For a one-line title on the command line (`gh pr create --title`, `gh pr merge --subject`), use single quotes. Inside single quotes the shell expands nothing. Write every `'` of the text as `'\''`.

- `feat(auth): add the user's token store (#42)` becomes `--title 'feat(auth): add the user'\''s token store (#42)'`.
- Never put a title or message in double quotes.

### Staging

- Stage only the files of the change: `git add -- <paths>`. Never use `git add -A` or `git add .`.
- For implementation work, the paths are the implementer's `Files changed` of every run, checked against `git status --porcelain`.
- The implementer never edits `.claude/settings.json`. When the plan has a settings change for the implementation phase and `.claude/settings.json` is changed in the working tree, stage the file with the files of the phase, also when an earlier run or the user applied the change. The same holds for the user's change of the file after a `settings:` block (`implementation-loop.md`).
- After staging, run `git status --porcelain`. Nothing outside `<task dir>` may be left unstaged or untracked. If something is, ask the user whether it belongs to the change.
- Never stage files of the task directory. It is ignored by git.

## Stash and discard

Both change the working tree. Confirm them first: show the exact commands and the files they touch, and wait for "yes". They never touch the task directory.

### Stash

1. Run `git check-ignore -q <task dir>`.
2. Exit status 0 (the task directory is ignored by git, the default): run `git stash push --include-untracked -m '<message>'`. A plain stash already leaves ignored files alone. Do not add a pathspec: with an ignored path in it, `git stash` exits 1 and leaves the changes staged in the tree.
3. Exit status 1 (not ignored): run `git stash push --include-untracked -m '<message>' -- . ':(exclude)<task dir>'`.
4. Check the exit status of `git stash`. If it is not 0, stop. Show its output, and show `git status --short`. Do not continue on a tree that is still dirty.
5. Tell the user how to restore the changes: `git stash pop`.

`<message>` is short and single-quoted, for example `'loom #<n> phase N <today>'`.

### Discard

1. Say plainly: **the discarded changes are lost and cannot be recovered.**
2. Name every path. Tracked changes: `git restore --source=HEAD --staged --worktree -- <paths>`. Untracked files: `git clean -f -- <paths>`.
3. Never name a path inside `<task dir>`.

## Rebase

Rebase the task branch on the main branch before the PR is opened (`describe-pr`), when the branch is behind (`iterate rebase`), and never during `implement`.

A stopped rebase (`rebaseInProgress` is `true` in the `loom-state` output: HEAD is detached, and `branch` is the branch being rebased) is handled only by `/loom:iterate rebase`. It continues or aborts that rebase and never starts a new one. `implement`, `describe-pr`, `finish-task`, and `screens` stop with `Next: /loom:iterate rebase`.

1. The working tree must be clean (`workingTree` is `clean`).
2. Choose the base. Run `git remote get-url origin`.
   - It succeeds: run `git fetch origin <main>`. The base is `origin/<main>`.
   - It fails (no remote `origin`): do not fetch. The base is `<main>`.
3. Note `git rev-parse HEAD`. Run `git rebase <base>` (normally `git rebase origin/<main>`).
4. On conflicts:
   - List the files: `git diff --name-only --diff-filter=U`.
   - Resolve a conflict only when the intent of both sides is clear from the code, the plan, and the main branch commit. Then run `git add -- <file>` and `git rebase --continue`.
   - Otherwise stop. Show the conflicts. Ask the user: resolve them together, or abort with `git rebase --abort`. Never pick a side blindly.
5. If `HEAD` changed, the rebase brought changes: run `checks.check` again.

## Push

1. Check for an upstream: `git rev-parse --abbrev-ref --symbolic-full-name @{u}`.
2. Show what you push: `git log --oneline @{u}..HEAD`, or `git log --oneline <base>..HEAD` without an upstream.
3. Ask for confirmation. If a rebase rewrote commits that are already on the remote, say that the push rewrites the remote branch.
4. Push:
   - No upstream: `git push -u origin <branch>`.
   - Upstream, history not rewritten: `git push`.
   - Upstream, history rewritten by a rebase: `git push --force-with-lease`.
