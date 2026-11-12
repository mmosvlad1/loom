---
name: setup
description: Prepares a project for loom - detects the stack and existing commands, then through loom's own flow (a Set up loom issue and a chore branch) writes loom.json, the checks entry point, CI, Claude Code settings, the docs skeleton, and CLAUDE.md, shows every change first, commits, and hands over to describe-pr. Safe to re-run.
disable-model-invocation: true
argument-hint: "[notes, e.g. the stack or the check commands]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Setup

You prepare a project for loom. You never commit on the main branch (a hook blocks it), so setup runs through loom's own flow: an issue "Set up loom", the branch `chore/<n>-loom-setup`, one commit, and a handover to `/loom:describe-pr`. Existing files and commands are reused, never overwritten silently.

## State

Current task state from `loom-state`:

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json`

Arguments: $ARGUMENTS

The state is empty when the project has no `.claude/loom.json` yet (the normal first run) or the directory is not a git repository.

"Today" below means `today` from the state. If the state is empty, use the session's current date.

## Shared rules

Read these files in full before you start:

- `${CLAUDE_SKILL_DIR}/references/stacks/python-uv.md` (python-uv recipe)
- `${CLAUDE_SKILL_DIR}/references/stacks/node.md` (node recipe)
- `${CLAUDE_SKILL_DIR}/references/templates/loom.json`, `${CLAUDE_SKILL_DIR}/references/templates/settings.json`, `${CLAUDE_SKILL_DIR}/references/templates/loom-statusline.py`, `${CLAUDE_SKILL_DIR}/references/templates/CLAUDE.md`, `${CLAUDE_SKILL_DIR}/references/templates/setup-issue.md`
- the CI template and the Makefile of the detected stack: `${CLAUDE_SKILL_DIR}/references/templates/ci.python-uv.yml` and `${CLAUDE_SKILL_DIR}/references/templates/Makefile`, or `${CLAUDE_SKILL_DIR}/references/templates/ci.node.yml`
- the docs skeleton: `${CLAUDE_SKILL_DIR}/references/templates/docs/product/vision.md`, `${CLAUDE_SKILL_DIR}/references/templates/docs/architecture/overview.md`, `${CLAUDE_SKILL_DIR}/references/templates/docs/conventions.md`
- `${CLAUDE_PLUGIN_ROOT}/skills/start-task/references/ticket-template.md` (the setup task's `00-ticket.md`)
- `${CLAUDE_PLUGIN_ROOT}/skills/implement/references/log-format.md` (the setup task's `log.md`)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/git-flow.md` (confirmations, commit message file, quoting, staging, stash, push)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/frontmatter.md` (ticket frontmatter)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md` (style of the issue, commit, docs, and final message)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/bash-calls.md` (one command per Bash call: no `cd`, no chaining)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission. Read the templates with the Read tool and copy them; never write them from memory.

### Values

- `<current>`: the current branch, `git symbolic-ref --short HEAD` (it works on an empty repository too). Do not take `branch` from the state: the state is empty before `.claude/loom.json` exists.
- `<main>`: `mainBranch` from `.claude/loom.json` if the file exists. Otherwise the default branch on GitHub: `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`. If that is empty (an empty GitHub repository), `git symbolic-ref --short refs/remotes/origin/HEAD` without the `origin/` prefix. If that fails too, ask the user, and propose `main`.
- `<workDir>`: `workDir` from `.claude/loom.json`, else the template default.
- **Docs paths**: one path per docs role, from `docs` in the state (the docs map) when `.claude/loom.json` exists. Before the file exists, the state is empty. The template `loom.json` has no `docs` key, so every role then takes its default: the path of its skeleton file relative to `templates/`. Never build a doc path in another way. After step 7 writes `.claude/loom.json`, `loom-state --json` reports the same paths in `docs`.
- `<n>`: the number of the issue "Set up loom". `<branch>` is `chore/<n>-loom-setup`. `<task dir>` is `<workDir>/<n>-loom-setup`.
- `<drafts>`: `<workDir>/_drafts`. Write issue bodies and the first commit message there. The work directory is ignored by git, and `loom-state` never takes `_drafts` for a task directory.
- **Dirty**: `git status --porcelain --untracked-files=all` lists a path outside `<workDir>`. Always pass `--untracked-files=all` in this skill: plain `git status` collapses an untracked directory into its parent (`?? .loom/`), which hides whether the files are below `<workDir>`. Paths below `<workDir>` do not count: until the setup PR is merged, `<main>` has no `.gitignore` line for it, so the work directory of an earlier run shows as untracked there.
- **Draft and message files**: the Write tool refuses to overwrite a file you have not read. If a file in `<drafts>` or `<task dir>/commit-msg.txt` already exists, Read it first, then Write it (`git-flow.md`, "Commit with a message file").

## 1. Check preconditions

Take the first matching row. Stop rows end in the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`. Write nothing before this table is through.

| Check | Action |
|---|---|
| `git rev-parse --show-toplevel` fails | Stop: `Result: not a git repository`, `Next: run git init, add the GitHub repository as remote origin, then /loom:setup` |
| `git remote get-url origin` fails | Stop: `Result: no remote origin; loom needs a GitHub repository for issues and PRs`, `Next: add the remote origin, then /loom:setup` |
| `gh repo view --json nameWithOwner,visibility,defaultBranchRef` fails | Stop: `Result: gh cannot read the repository: <the error>`, `Next: gh auth login, then /loom:setup` |
| `<current>` matches `chore/<k>-loom-setup` | Re-run on the setup branch: `<n>` = `<k>`. Go to [Resume on the setup branch](#resume-on-the-setup-branch). |
| `task` is set and not archived | Stop: `Result: task #<task.number> is active on <current>; finish it before setup`, `Next:` from `next.command` |
| `git branch --list 'chore/*-loom-setup'` lists a branch, or `git branch -r --list 'origin/chore/*-loom-setup'` lists one (a fresh clone has only the remote branch) | An earlier run created it. Several branches: ask which one. Take `<n>` from its name; for a remote-only branch, `git switch chore/<n>-loom-setup` creates the local tracking branch. If `gh pr list --head <that branch> --state merged --json number` lists a PR, the setup is merged (for example in the GitHub UI): stop with `Result: the setup PR of #<n> is merged; the cleanup is left`, `Next: /loom:finish-task #<n>`. Run `git switch <that branch>` and go to [Resume on the setup branch](#resume-on-the-setup-branch). Uncommitted changes go with you (often the files of the stopped run); the resume plan lists them, so the user can keep out what does not belong to setup. Every final message of this run then adds `Warning: uncommitted changes moved to <that branch>: <paths>`. If git refuses the switch, stop as in the dirty-tree row below. |
| The repository has commits (`git rev-parse --verify --quiet HEAD` succeeds) and `git ls-remote --exit-code --heads origin <main>` fails | Stop: `Result: <main> is not on origin; describe-pr cannot open a PR against it`, `Next: push <main> yourself (git push -u origin <main>), then /loom:setup`. The guard allows only the first push of a one-commit repository, so setup does not push here. |
| The repository has no commits, and `git ls-remote --exit-code --heads origin <main>` succeeds | Stop: `Result: origin has <main> but this clone has no commits`, `Next: git pull origin <main>, then /loom:setup` |
| The repository has commits and the working tree is dirty (see Values) | Offer the stash of `git-flow.md` (confirmation), with `<workDir>` in place of `<task dir>`; `git-flow.md` gives the commands. Without "yes", stop: `Result: working tree has uncommitted changes`, `Next: commit or stash the changes, then /loom:setup` |
| Otherwise | Continue with step 2. An empty repository (no commits) may have untracked files; step 3 lists them. |

### Start from `<main>`

Repository with commits: the precondition table left a clean working tree. [Resume on the setup branch](#resume-on-the-setup-branch) never runs this section. Before you detect anything:

1. If `<current>` is not `<main>`, run `git switch <main>`.
2. Run `git pull --ff-only origin <main>`. If it fails, stop: `Result: git pull failed on <main>: <the error>`, `Next: /loom:setup` after you fix it.

Detection, the plan, and the setup branch then all start from an up-to-date `<main>`: a `Makefile` or workflow that exists only on another branch is never reused. An empty repository skips this; step 4 handles it.

Note `visibility` from `gh repo view`. A private repository needs a paid GitHub plan for the main branch ruleset that `/loom:finish-task` offers later; say so in a `Warning:` line of the final message.

## 2. Detect

### Stack

Check the marker files at the git top level (the recipes give the details):

| Markers | Stack | Recipe |
|---|---|---|
| `pyproject.toml` and `uv.lock` | python-uv | `stacks/python-uv.md` |
| `package.json` and a lock file | node | `stacks/node.md` |
| `go.mod`, `Cargo.toml`, or anything else | no recipe in v1 | below |
| No source files (a new repository) | ask the user | below |

- **No recipe**: investigate before you ask. Read the README, an existing `Makefile` or `justfile`, the workflows in `.github/workflows/`, and the build files. Propose the four check commands (`lint`, `typecheck`, `test`, `check`) and a CI workflow that runs `check` in one job named `check`, with action versions pinned to exact release tags. Ask the user to confirm or correct them.
- **New repository**: ask which stack the project uses: python-uv, node, or another. For python-uv and node, the recipe says how to create the marker files.
- Monorepos with several stacks are out of scope for v1. If you find several, ask the user which one the checks cover.

### Existing files

Prefer what exists. For each target file, record one state: **missing**, **identical** to what setup would write, or **different**.

| Target | What setup writes |
|---|---|
| `.claude/loom.json` | `templates/loom.json` with `mainBranch` = `<main>` and `checks` from the recipe. Every other key stays as in the template. If the file exists, keep its values; add only missing keys. |
| `Makefile` (python-uv) or `scripts` in `package.json` (node) | The recipe's checks entry point. Reuse existing targets and scripts. |
| `.github/workflows/ci.yml` | The recipe's CI template with its placeholders filled. Reuse an existing workflow if the user agrees. |
| `.claude/settings.json` | `templates/settings.json`, merged (see [Merge settings.json](#merge-settingsjson)). |
| `.claude/loom-statusline.py` | `templates/loom-statusline.py`, unchanged, if the user wants the status line. |
| The docs skeleton: one target per docs role (table below) | Only missing files; an existing file is kept as it is. |
| `CLAUDE.md` | `templates/CLAUDE.md` with its placeholders filled. If the file exists, propose a short loom section (commands, docs links, workflow) instead of replacing it. |
| `.gitignore` | The line `.loom/` (or `<workDir>/` when `workDir` is not below `.loom/`), if `git check-ignore -q <workDir>` fails. Plus the recipe's lines, if missing. |

The docs skeleton, by docs role. The paths come from the docs paths (see Values):

| Docs role | Target | What setup writes |
|---|---|---|
| `vision` | `docs.vision` | `templates/docs/product/vision.md` |
| `overview` | `docs.overview` | `templates/docs/architecture/overview.md` |
| `conventions` | `docs.conventions` | `templates/docs/conventions.md` |
| `decisions` | `<docs.decisions.dir>/.gitkeep` | `templates/docs/architecture/decisions/.gitkeep` (empty), only when the directory is missing or empty |
| `tasks` | `<docs.tasks>/.gitkeep` | `templates/docs/tasks/.gitkeep` (empty), only when the directory is missing or empty |

Run `git check-ignore -v -- <path>` for every target file. A global or repository ignore rule can hide one (a global `core.excludesFile` that ignores `CLAUDE.md` is common). Name each ignored target and its rule in the plan.

Fill `CLAUDE.md` from the README and the user's notes: the project name, one or two sentences about the project, the check commands, `<main>`, and the docs paths in the doc links. Keep it short; it loads into every session.

### Setup issue and labels

- Find an open issue "Set up loom": `gh issue list --state open --search 'in:title "Set up loom"' --json number,title,url`. Only an exact title match counts. If one exists, reuse it: `<n>` is its number.
- Read the labels: `gh label list --json name --limit 200`. loom uses these 11 labels (`issue-format.md` in the backlog skill describes them):

  | Label | Color | Description |
  |---|---|---|
  | `type:feat` | `1d76db` | New feature |
  | `type:fix` | `d73a4a` | Bug fix |
  | `type:chore` | `cfd3d7` | Maintenance, config, or dependencies |
  | `type:docs` | `0075ca` | Documentation |
  | `type:refactor` | `a2eeef` | Code change without a behavior change |
  | `size:S` | `c2e0c6` | Trivial change |
  | `size:M` | `fbca04` | Small or medium change with a clear design |
  | `size:L` | `e99695` | Larger feature or unclear behavior |
  | `mode:oneshot` | `bfdadc` | loom mode: oneshot |
  | `mode:quick` | `bfdadc` | loom mode: quick |
  | `mode:full` | `bfdadc` | loom mode: full |

### Nothing to change

Only on `<main>`, never on the setup branch: if every target file is identical and `.claude/loom.json` exists, stop: `Result: loom is already set up; nothing to change`, plus `Warning:` lines for missing labels. `Next:` from `next.command` (on the main branch: `/loom:start-task #<n>`, or `/loom:backlog` to plan issues).

## 3. Plan and confirm

Show one plan. Then ask for confirmation once. The plan names every command that changes something outside the working tree, exactly as you will run it:

1. **Detected**: the stack, the package manager, `<main>`, and the check commands for `loom.json`.
2. **Empty repository only**: `git branch -m <main>` if `<current>` is not `<main>`, the first commit on `<main>` (only `.gitignore` and `README.md`), then `git push -u origin <main>`. List the other untracked files; they go into the setup commit unless the user excludes them. An excluded file must be moved out of the repository, or the task cannot reach a clean working tree.
3. **Labels**: the missing labels, each as its `gh label create` command. Optional: the user may skip them. Create labels only after "yes".
4. **Issue**: `gh issue create` for "Set up loom" (step 5), or the open issue you reuse.
5. **Stack commands**: the recipe commands that change project files, e.g. `uv init --bare`, `uv lock`, `uv add --dev <missing tools>`, or the Node install command that writes the lock file. They run in step 7.
6. **Files**: one line per target file: `new`, `changed`, or `unchanged`. For a new file, show its full content. For a changed file, show a `diff` block. Never write a file the plan does not show. For an ignored target, ask: commit it anyway (`git add -f -- <path>` in step 9), or keep it out of the commit.
7. **Status line** (optional, default yes): `.claude/loom-statusline.py` and the `statusLine` setting. It shows the one-line task state of `loom-state` (its `--line` output), e.g. `#42 · full · design:in-review · 3 open Q`. Say: a project `statusLine` replaces each collaborator's personal status line in this project. If `.claude/settings.json` already has a `statusLine`, keep it unless the user chooses loom's.

The user may drop or change items. Apply the answer and show the changed items again. Without "yes", stop: `Result: setup not applied; nothing changed`.

## 4. Bootstrap

Run these in order:

1. **Repository with commits**: you are on an up-to-date `<main>` ([Start from `<main>`](#start-from-main)). Nothing to do here.
2. **Empty repository: name the branch.** If `<current>` is not `<main>`, run `git branch -m <main>` (it renames the unborn branch).
3. **Ignore the work directory.** Add the `.gitignore` lines of the plan now, before any file in `<workDir>` exists.
4. **Empty repository only** (the guard allows the first commit on `<main>` and its first push):
   1. Write `README.md` if it is missing: `# <project name>` and one sentence about the project.
   2. Run `git add -- .gitignore README.md`.
   3. Write `chore: initial commit` to `<drafts>/commit-msg.txt`. Run `git commit -F <drafts>/commit-msg.txt`.
   4. Run `git push -u origin <main>`. The plan confirmed it.
5. **Labels**: run the confirmed `gh label create` commands, one per label: `gh label create 'type:chore' --color cfd3d7 --description 'Maintenance, config, or dependencies'`. A label that already exists is not an error; continue.

## 5. Issue

Skip this step when you reuse an open issue.

1. Copy `templates/setup-issue.md` to `<drafts>/setup-issue.md`.
2. Run `gh issue create --title 'Set up loom' --body-file <drafts>/setup-issue.md` with `--label 'type:chore' --label 'size:S' --label 'mode:oneshot'`. Add only labels that exist now.
3. `<n>` is the number at the end of the URL that `gh issue create` prints.

## 6. Branch

Run `git switch -c <branch>`. The uncommitted `.gitignore` change goes with you to the branch. If the branch already exists, stop: step 1 should have found it; re-run `/loom:setup`.

## 7. Write the files

Write the files of the plan, exactly as shown, in this order:

1. `.claude/loom.json` first: `loom-state` and the hooks read it. Then run `loom-state --json`. Take `checks` and the docs paths (`docs`) from it for the rest of this run.
2. The stack: run the confirmed recipe commands (`uv init --bare`, `uv lock`, `uv add --dev …`, or the Node install), then write the checks entry point (`Makefile` or `package.json` scripts).
3. `.github/workflows/ci.yml`.
4. `.claude/settings.json` (merged) and, if confirmed, `.claude/loom-statusline.py`.
5. The docs skeleton (by docs role), then `CLAUDE.md`.

Write each file with the Write or Edit tool. Never use shell redirection to write a file. On a resume, write only the targets that are still missing or different.

### Merge settings.json

If `.claude/settings.json` exists, merge the template into it. Never replace the file and never remove a key.

- `extraKnownMarketplaces.loom`: add it if missing. If it exists with another source, keep it and ask the user.
- `enabledPlugins["loom@loom"]`: set it to `true`. If it is `false`, ask first.
- `permissions.allow` and `permissions.ask`: append the template rules that are missing. Keep the existing rules and their order. If a template `allow` rule is also in the file's `deny` or `ask`, keep the stricter rule and say so in a `Warning:` line.
- `statusLine`: add it only if the file has none and the user wants it.
- Keep every other key as it is. Keep the file valid JSON (no comments, no trailing commas).

Fill in the template's stack and work directory values before you merge:

- Check commands: python-uv keeps `Bash(make *)`. Node replaces it with one exact rule per check command, e.g. `Bash(npm run check)`.
- The `mkdir` and `mv` rules name the template's default work directory (the `workDir` of `templates/loom.json`). Replace it with `<workDir>` when `workDir` differs.

## 8. Checks

Run `checks.check` from `loom-state --json` exactly as configured, from the git top level, as `git-flow.md` describes.

- Pass: continue.
- Fail: stop. Do not commit. Show the key failure lines. `Result: checks fail on <branch>: <the key lines>`, `Next: fix the failures, then /loom:setup` (a re-run continues on this branch).

## 9. Task directory and commit

1. Read the issue: `gh issue view <n> --json title,body,labels,url`.
2. Write `<task dir>/00-ticket.md` from `ticket-template.md`: `task: <n>-loom-setup`, `phase: ticket`, `mode: oneshot`, `size: S`, `issue: <n>`, `url: <url>`. The body is the issue title as the `# ` heading, the labels, the URL, and the issue body verbatim.
3. Stage the setup commit. The staging set is every path outside `<workDir>` that differs from `<main>`: the paths of `git status --porcelain --untracked-files=all` (staged, changed, and untracked), plus `git diff --name-only origin/<main>...HEAD` on a resume. This includes `pyproject.toml` and `uv.lock` after `uv add`, and the untracked files the plan put into the setup commit. Leave out the files the user excluded. Run `git add -- <paths>`. Never use `git add -A` or `git add .`. Add an ignored target that the user chose to commit with `git add -f -- <path>`; never force-add anything else.
4. Run `git status --porcelain --untracked-files=all`. Nothing outside `<workDir>` may be left unstaged or untracked. If something is, ask the user whether it belongs to the setup commit. Ask all questions now: steps 5 to 7 run without a question in between.
5. Write the message to `<task dir>/commit-msg.txt`: the subject `chore(loom): set up loom (#<n>)`, a blank line, then the body `Phase 1: oneshot`.
6. Append the in-progress entry of `log-format.md` to `<task dir>/log.md`: `## Phase 1 — in-progress`, then `Started: <today>`. Skip it if the last entry of `log.md` already is `## Phase 1 — in-progress`.
7. Right after step 6, run `git commit -F <task dir>/commit-msg.txt`. If the commit fails, stop: `Result: setup commit failed: <the error>`, `Next: fix it, then /loom:setup` (not `/loom:next`: with the in-progress entry, `loom-state` routes to `/loom:implement`).
8. Append the done entry of `log-format.md` to `<task dir>/log.md`:

   ```markdown
   ## Phase 1 — done — <commit short hash>
   Checks: <checks.check command>: pass; <one line>
   Reviewer: not run (the setup commit comes from /loom:setup); nits: None
   Deviations: None
   Additions: <files beyond the plan's template set, e.g. the project files of an empty repository, or None>
   Manual verification: None
   ```

   `<commit short hash>` is `git rev-parse --short HEAD` right after the commit.

`loom.json`, the ticket, the commit, and the `done` entry make `loom-state` route the task to `/loom:describe-pr`. It opens a short oneshot PR. After the merge, `/loom:finish-task` offers the main branch ruleset: it knows the setup task by the branch `chore/<n>-loom-setup` and by the ticket title `Set up loom`.

## 10. Final message

Run `loom-state --json`. `next.command` must be `/loom:describe-pr`. If it is not, add `Warning: loom-state routes to <next.command>: <next.reason>`.

Use the `final-answer.md` format:

```text
Result: loom set up on <branch> (<commit short hash>) for issue #<n>
Warning: <one line per warning, if any>
Next: /clear, then /loom:describe-pr
```

- Add `Labels: <created labels, or skipped>` after `Result:` when this run created labels.
- Map `next.command` as `final-answer.md` describes.

---

## Resume on the setup branch

An earlier run stopped on `<branch>` (for example after failing checks). Continue where it stopped. Never write a second `in-progress` entry after a `done` entry.

1. `<task dir>` is `<workDir>/<n>-loom-setup`. Read `.claude/loom.json` if it exists for `<main>` and `<workDir>`; the docs paths come from `docs` in the state. Compare with `origin/<main>`, not the local `<main>`: a fresh clone may have no local `<main>`. Run `git fetch origin <main>` first.
   - If `gh pr list --head <branch> --state merged --json number` lists a PR, stop: `Result: the setup PR of #<n> is merged; the cleanup is left`, `Next: /loom:finish-task #<n>`.
   - If `gh pr list --head <branch> --state open --json number` lists a PR, stop: `Result: the setup PR is open`, `Next:` from `next.command` (`loom-state` routes the open PR).
2. `log.md` has `## Phase 1 — done`: the setup commit exists. Write nothing. Go to step 10 (`next.command` is `/loom:describe-pr`).
3. The setup commit exists (`git log --format=%h --grep='^Phase 1: oneshot' origin/<main>..HEAD` prints a hash), but `log.md` has no `done` entry (also on a fresh clone, where the ignored task directory is missing):
   - If `<task dir>/00-ticket.md` is missing, write it from the issue as steps 9.1 and 9.2 describe.
   - Append the done entry as step 9.8 describes, with that hash. Do not write an `in-progress` entry.
   - Go to step 10.
4. Otherwise the setup commit is still missing. Run step 2 (detect; skip [Nothing to change](#nothing-to-change)), step 3, step 7, step 8, and step 9 on this branch:
   - The plan of step 3 lists the setup commit: every path outside `<workDir>` that differs from `<main>` (`git status --porcelain --untracked-files=all` and `git diff --name-only origin/<main>...HEAD`), plus the targets that are still missing or different. Files an earlier run wrote count as part of the commit, also when they are identical to the templates.
   - Skip steps 4 to 6: the issue and the branch exist. Run labels or stack commands only if the plan still lists them.
