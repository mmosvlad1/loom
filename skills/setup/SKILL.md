---
name: setup
description: Prepares a project for loom through loom's own flow (a Set up loom issue and a chore branch). An empty or new repository gets the fast setup - stack detection, loom.json, the checks entry point, CI, Claude Code settings, the docs skeleton, and CLAUDE.md in one commit, then a handover to describe-pr. A repository with code gets an onboarding task in full mode - setup does only the kickoff, and loom's own phases do the rest. Shows every change first. Safe to re-run.
disable-model-invocation: true
argument-hint: "[--oneshot] [notes, e.g. the stack or the check commands]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json) Bash(loom-state --json) Bash(loom-state --setup-path *) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Setup

You prepare a project for loom. You never commit on the main branch (a hook blocks it), so setup runs through loom's own flow: an issue "Set up loom" and the branch `chore/<n>-loom-setup`. Existing files and commands are reused, never overwritten silently.

The *setup task* is the task of the issue "Set up loom", on the branch `chore/<n>-loom-setup`. `loom-state --setup-path <main>` chooses one of two setup paths (step 1):

- **Fast path** (`fast`): an empty or new repository. Setup writes every file, makes one commit, and hands over to `/loom:describe-pr`. The setup task has mode `oneshot`.
- **Onboarding path** (`onboarding`): a repository with code. The setup task is an *onboarding task*: a setup task in `full` mode. Setup does only the kickoff (`references/onboarding.md`). loom's own phases (research, design, plan, implement) do the rest; then `/loom:describe-pr` and `/loom:finish-task` open and merge the setup PR.

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

**Onboarding path only.** When step 1 chooses the path `onboarding` or `onboarding-rerun`, also read these files in full, right after step 1 runs `loom-state --setup-path <main>`, before any other question. The fast path never reads them:

- `${CLAUDE_SKILL_DIR}/references/onboarding.md` (the kickoff and the onboarding re-run)
- `${CLAUDE_SKILL_DIR}/references/onboarding-questions.md` (the fixed research questions: the template of `01-research-questions.md`)
- `${CLAUDE_SKILL_DIR}/references/templates/setup-issue-onboarding.md` (the issue body of the onboarding task)

If the user switches from the fast path to the onboarding path in the plan answer (step 3), read them then.

### Values

- `<current>`: the current branch, `git symbolic-ref --short HEAD` (it works on an empty repository too). Do not take `branch` from the state: the state is empty before `.claude/loom.json` exists.
- `<main>`: `mainBranch` from the state when the state is not empty (`.claude/loom.json` exists). Otherwise the default branch on GitHub: `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`. If that is empty (an empty GitHub repository), `git symbolic-ref --short refs/remotes/origin/HEAD` without the `origin/` prefix. If that fails too, ask the user, and propose `main`.
- `<workDir>`: `workDir` from the state when it is not empty, else the `workDir` of `templates/loom.json`.
- **State after a switch**: the state above was read before any `git switch`. After a switch to the setup branch, run `loom-state --json` again and take the values from that output.
- **Docs paths**: one path per docs role, from `docs` in the state (the docs map) when `.claude/loom.json` exists. Before the file exists, the state is empty. The template `loom.json` has no `docs` key, so every role then takes its default: the path of its skeleton file relative to `templates/`. Never build a doc path in another way. After step 7 writes `.claude/loom.json`, `loom-state --json` reports the same paths in `docs`.
- `<n>`: the number of the issue "Set up loom". `<branch>` is `chore/<n>-loom-setup`. `<task dir>` is `<workDir>/<n>-loom-setup`.
- `<path>`, `<reason>`, and `<found>`: `path`, `reason`, and `found` of the latest `loom-state --setup-path <main>` output (step 1).
- `--oneshot`: the argument `--oneshot` forces the fast path. The other arguments are notes.
- `<drafts>`: `<workDir>/_drafts`. Write issue bodies and the first commit message there. The work directory is ignored by git, and `loom-state` never takes `_drafts` for a task directory.
- **Dirty**: `git status --porcelain --untracked-files=all` lists a path outside `<workDir>`. Always pass `--untracked-files=all` in this skill: plain `git status` collapses an untracked directory into its parent (`?? .loom/`), which hides whether the files are below `<workDir>`. Paths below `<workDir>` do not count: until the setup PR is merged, `<main>` has no `.gitignore` line for it, so the work directory of an earlier run shows as untracked there. A changed `.gitignore` does not count either when its only change is the line `.loom/` (or `<workDir>/`) that setup adds (check with `git diff -- .gitignore`): a run that stopped before the branch leaves that change on `<main>`. The same holds for an untracked `.gitignore` (`?? .gitignore`, which `git diff` does not show) whose only line is that line: Read it. It goes into the setup commit or the kickoff commit.
- **Permission prompts**: the `allowed-tools` grant ends with the user's next message. After an answer (the stash offer, a choice of branch, the plan confirmation), `loom-state --setup-path <main>` and `loom-state --json` may ask for permission until `.claude/settings.json` has the allow rules. That prompt is expected and harmless: the user approves it.
- **Draft and message files**: the Write tool refuses to overwrite a file you have not read. If a file in `<drafts>` or `<task dir>/commit-msg.txt` already exists, Read it first, then Write it (`git-flow.md`, "Commit with a message file").

## 1. Check preconditions

Take the first matching row. Stop rows end in the `final-answer.md` format, with a `Result:` line instead of `Artifact` and `Status`. Write nothing before this table is through.

| Check | Action |
|---|---|
| `git rev-parse --show-toplevel` fails | Stop: `Result: not a git repository`, `Next: run git init, add the GitHub repository as remote origin, then /loom:setup` |
| `git remote get-url origin` fails | Stop: `Result: no remote origin; loom needs a GitHub repository for issues and PRs`, `Next: add the remote origin, then /loom:setup` |
| `gh repo view --json nameWithOwner,visibility,defaultBranchRef` fails | Stop: `Result: gh cannot read the repository: <the error>`, `Next: gh auth login, then /loom:setup` |
| A rebase is stopped: `rebaseInProgress` is `true` in the state; or the state is empty, `git symbolic-ref --short HEAD` fails (a detached HEAD), and `git status` prints `rebase in progress` | Stop on every path: during a rebase HEAD is detached, so the path would be wrong. `Result: a rebase is in progress; setup waits until it is continued or aborted`, `Next:` names how to continue or abort it. When `next.command` of the state is `/loom:iterate rebase` (a stopped rebase of a task branch): `Next: /loom:iterate rebase, then /loom:setup`. Otherwise (no state, or a branch without a task): `Next: git rebase --continue or git rebase --abort, then /loom:setup` |
| Otherwise | [Choose the path](#choose-the-path), before any question to the user. |

### Choose the path

`loom-state --setup-path <main>` computes the path from git facts, so the choice never depends on you. It makes no network call and works without `.claude/loom.json`.

1. Find `<main>` (Values).
2. Run `loom-state --setup-path <main>`. It prints one JSON object with `path`, `reason`, `setupBranches`, `codeFiles`, and `found`. If it exits with another status than 0, stop: `Result: loom-state --setup-path failed: <its message>`, `Next: fix it, then /loom:setup`. It fails, for example, when the repository has commits but `<main>` exists neither locally nor on `origin`.
3. With `--oneshot`, the path `onboarding` counts as `fast`. The path `onboarding-rerun` stops: once the ticket of an onboarding task exists, the path is fixed. Stop with `Result: setup task #<n> is an onboarding task` and `Next: /loom:setup to continue the onboarding task; to start over on the fast path, delete the branch <branch> (local and on origin) and <task dir>, then /loom:setup --oneshot`.
4. Take the row of `<path>`. Only the `switch` row takes this table again, once, with the `<path>` of its second run (now on the setup branch). For `rerun`, `fast`, and `onboarding`, the second run after [Start from `<main>`](#start-from-main) is final: continue as its row says, and do not run the preconditions again.

| `<path>` | Action |
|---|---|
| `switch` | An earlier run created the setup branch that `<reason>` names. First the active-task check: if `task` is set and not archived, stop as the first row of [Other preconditions](#other-preconditions) says. Setup never leaves the branch of another task. Several setup branches: ask which one. Take `<n>` from its name; for a remote-only branch, `git switch chore/<n>-loom-setup` creates the local tracking branch. If `gh pr list --head <that branch> --state merged --json number` lists a PR, the setup is merged (for example in the GitHub UI): stop with `Result: the setup PR of #<n> is merged; the cleanup is left`, `Next: git switch <main>, then git pull --ff-only, then /loom:finish-task #<n>`. Run `git switch <that branch>`. Uncommitted changes go with you (often the files of the stopped run); the resume plan lists them, so the user can keep out what does not belong to setup. Every final message of this run then adds `Warning: uncommitted changes moved to <that branch>: <paths>`. If git refuses the switch, handle it as the dirty-tree row of [Other preconditions](#other-preconditions) says (the stash offer; without "yes", stop), then run the switch again. After the switch, run `loom-state --json` (State after a switch) and `loom-state --setup-path <main>` again. |
| `onboarding-rerun` | `<current>` matches `chore/<k>-loom-setup`: `<n>` = `<k>`. Run "Onboarding re-run" of `onboarding.md`. |
| `fast-resume` | `<current>` matches `chore/<k>-loom-setup`: `<n>` = `<k>`. Go to [Resume on the setup branch](#resume-on-the-setup-branch). |
| `fast` or `onboarding`, and `<current>` matches `chore/<k>-loom-setup` | An earlier run stopped after `git switch -c`, before it wrote a file. `<n>` = `<k>`. Keep the branch and reuse the open issue #<n>. Skip [Other preconditions](#other-preconditions) and [Start from `<main>`](#start-from-main): on a setup branch, setup never stops on an active task and never offers a stash. The uncommitted files are the stopped run. `fast`: continue with step 2; skip step 6, and in step 5 run only the `gh issue edit` of the reused issue, if any. `onboarding`: run "Kickoff" of `onboarding.md`; skip its branch step (kickoff step 5), and in its issue step (kickoff step 4) run only the confirmed `gh issue edit` of the reused issue, if any. A switch between `fast` and `onboarding` in the plan answer keeps this place. |
| `rerun`, `fast`, or `onboarding` | Run [Other preconditions](#other-preconditions) and [Start from `<main>`](#start-from-main). Then run `loom-state --setup-path <main>` once more, on the updated `<main>` (it may ask for permission after an answer: see Values). Its result is final. `rerun` (loom is set up) and `fast`: continue with step 2. `onboarding`: run "Kickoff" of `onboarding.md`. |

### Other preconditions

They run only for `rerun`, and for `fast` and `onboarding` outside a setup branch. Take the first matching row.

| Check | Action |
|---|---|
| `task` is set and not archived | Stop: `Result: task #<task.number> is active on <current>; finish it before setup`, `Next:` from `next.command` |
| The repository has commits (`git rev-parse --verify --quiet HEAD` succeeds) and `git ls-remote --exit-code --heads origin <main>` fails | Stop: `Result: <main> is not on origin; describe-pr cannot open a PR against it`, `Next: push <main> yourself (git push -u origin <main>), then /loom:setup`. The guard allows only the first push of a one-commit repository, so setup does not push here. |
| The repository has no commits, and `git ls-remote --exit-code --heads origin <main>` succeeds | Stop: `Result: origin has <main> but this clone has no commits`, `Next: git pull origin <main>, then /loom:setup` |
| The repository has commits and the working tree is dirty (see Values) | Offer the stash of `git-flow.md` (confirmation), with `<workDir>` in place of `<task dir>`; `git-flow.md` gives the commands. Without "yes", stop: `Result: working tree has uncommitted changes`, `Next: commit or stash the changes, then /loom:setup` |
| Otherwise | Continue with [Start from `<main>`](#start-from-main). An empty repository (no commits) may have untracked files; step 3 lists them. |

### Start from `<main>`

Repository with commits: the precondition table left a clean working tree. A run on a setup branch never runs this section. Before you detect anything:

1. If `<current>` is not `<main>`, run `git switch <main>`.
2. Run `git pull --ff-only origin <main>`. If it fails, stop: `Result: git pull failed on <main>: <the error>`, `Next: /loom:setup` after you fix it. If git refuses because the pull would overwrite the local `.gitignore` (the work directory line of a stopped run), say so: `Next: undo the local .gitignore change (git checkout -- .gitignore, or delete an untracked .gitignore), then /loom:setup`. Setup adds the line again.
3. Run `git rev-list --count origin/<main>..<main>`. If it prints a number above 0, the local `<main>` is ahead of `origin/<main>`. Stop: `Result: <main> has <count> commits that are not on origin/<main>`, `Next: push <main> or reset it to origin/<main> yourself, then /loom:setup`. Otherwise the path would come from `origin/<main>`, and the setup PR would carry the unpushed commits. The one exception is the bootstrap commit of an empty repository: step 4 makes it and pushes it in the same run.

Detection, the plan, and the setup branch then all start from an up-to-date `<main>`: a `Makefile` or workflow that exists only on another branch is never reused. An empty repository skips this section; step 4 handles it.

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

- **No recipe**: investigate before you ask. Read the README, an existing `Makefile` or `justfile`, the workflows in `.github/workflows/`, and the build files. Propose `check`, and those of `lint`, `typecheck`, and `test` that the project really has. A check the project does not have is `null` in `loom.json`; never invent a command for it. Propose a CI workflow that runs `check` in one job named `check`, with action versions pinned to exact release tags, or reuse an existing workflow as the recipes describe. Ask the user to confirm or correct them.
- **New repository**: ask which stack the project uses: python-uv, node, or another. For python-uv and node, the recipe says how to create the marker files.
- Monorepos with several stacks are out of scope for v1. If you find several, ask the user which one the checks cover.

### Existing files

Prefer what exists. For each target file, record one state: **missing**, **identical** to what setup would write, or **different**.

| Target | What setup writes |
|---|---|
| `.claude/loom.json` | `templates/loom.json` with `mainBranch` = `<main>` and `checks` from the recipe. With a kept CI workflow, also `"ci": { "requiredCheck": "<check name>" }` (the recipe's "Reuse an existing workflow"). Every other key stays as in the template. If the file exists, keep its values; add only missing keys. |
| `Makefile` (python-uv) or `scripts` in `package.json` (node) | The recipe's checks entry point. Reuse existing targets and scripts. |
| `.github/workflows/ci.yml` | The recipe's CI template with its placeholders filled. Reuse an existing workflow if the user agrees; never rename its jobs. A reused workflow must run `checks.check`: see [Reused workflow](#reused-workflow). |
| `.claude/settings.json` | `templates/settings.json`, merged (see [Merge settings.json](#merge-settingsjson)). |
| `.claude/loom-statusline.py` | `templates/loom-statusline.py`, unchanged, if the user wants the status line. |
| The docs skeleton: one target per docs role (table below) | Only missing files; an existing file is kept as it is. |
| `CLAUDE.md` | `templates/CLAUDE.md` with its placeholders filled, plus the line `@AGENTS.md` (or `@.claude/AGENTS.md`) when the repository has one and no other `CLAUDE.md` (see below). If the file exists, propose a short loom section (commands, docs links, workflow) instead of replacing it. |
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

Fill `CLAUDE.md` from the README and the user's notes: the project name, one or two sentences about the project, the check commands, `<main>`, and the docs paths in the doc links. Leave out the line of a `null` check. Keep it short; it loads into every session.

**`AGENTS.md`.** Claude Code loads an `AGENTS.md` or `.claude/AGENTS.md` at the git top level by itself only while the project has none of `CLAUDE.md`, `.claude/CLAUDE.md`, and `CLAUDE.local.md` there. The `CLAUDE.md` that setup writes would stop that. So when setup writes a new `CLAUDE.md` from the template, the git top level has `AGENTS.md` or `.claude/AGENTS.md`, and it has none of `CLAUDE.md`, `.claude/CLAUDE.md`, and `CLAUDE.local.md`: add the import line on its own line, right after the one or two sentences about the project. The line is `@AGENTS.md` for `AGENTS.md`, and `@.claude/AGENTS.md` for `.claude/AGENTS.md` (both files: both lines). The import keeps the project's instructions in effect. Never change an `AGENTS.md` file itself.

### Reused workflow

CI must run `checks.check` exactly as configured. It may run CI-only steps in addition (for example e2e tests, or checks that need services). When the plan keeps an existing workflow:

1. Read the job whose check name goes into `ci.requiredCheck`.
2. It runs `checks.check` (for example `make check`, or `npm run check`) as one of its steps: keep it as it is.
3. It does not: say so in the plan. Propose a `diff` of that job that adds `checks.check` as a step and keeps its other steps, or `ci.yml` from the template. The user chooses. Never rename the job, and never remove one of its steps without confirmation.

### Setup issue and labels

- Find an open issue "Set up loom": `gh issue list --state open --search 'in:title "Set up loom"' --json number,title,url,labels`. Only an exact title match counts. If one exists, reuse it: `<n>` is its number. On a setup branch, the issue is #<n> of the branch.
- **Labels of a reused issue**: the fast path uses `size:S` and `mode:oneshot`, the onboarding path `size:M` and `mode:full`. A reused issue that carries the size or mode label of the other path gets the labels of this path, for example on the fast path `gh issue edit <n> --remove-label 'size:M' --remove-label 'mode:full' --add-label 'size:S' --add-label 'mode:oneshot'`. Add only labels that exist. The plan shows the command. The issue body stays.
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

1. **Path**: `<path>` and `<reason>` (with `--oneshot`: `fast, forced by --oneshot`). On `fast`, when the repository has commits, say: the user can answer `onboarding` to set up loom as an onboarding task in full mode instead. An empty repository (no commits) has nothing to research, so it never takes the onboarding path.
2. **Detected**: the stack, the package manager, `<main>`, the check commands for `loom.json` (a missing check as `null`), and the required CI check (`ci.requiredCheck`).
3. **Empty repository only**: `git branch -m <main>` if `<current>` is not `<main>`, the first commit on `<main>` (only `.gitignore` and `README.md`), then `git push -u origin <main>`. List the other untracked files; they go into the setup commit unless the user excludes them. An excluded file must be moved out of the repository, or the task cannot reach a clean working tree.
4. **Labels**: the missing labels, each as its `gh label create` command. Optional: the user may skip them. Create labels only after "yes".
5. **Issue**: `gh issue create` for "Set up loom" (step 5), or the open issue you reuse, with its `gh issue edit` command when it carries the labels of the onboarding path.
6. **Stack commands**: the recipe commands that change project files, e.g. `uv init --bare`, `uv lock`, `uv add --dev <missing tools>`, or the Node install command that writes the lock file. They run in step 7.
7. **Files**: one line per target file: `new`, `changed`, or `unchanged`. For a new file, show its full content. For a changed file, show a `diff` block. Never write a file the plan does not show. For an ignored target, ask: commit it anyway (`git add -f -- <path>` in step 9), or keep it out of the commit.
8. **Status line** (optional, default yes): `.claude/loom-statusline.py` and the `statusLine` setting. It shows the one-line task state of `loom-state` (its `--line` output), e.g. `#42 · full · design:in-review · 3 open Q`. Say: a project `statusLine` replaces each collaborator's personal status line in this project. If `.claude/settings.json` already has a `statusLine`, keep it unless the user chooses loom's.

The user may drop or change items. Apply the answer and show the changed items again. Without "yes", stop: `Result: setup not applied; nothing changed`.

The answer `onboarding` switches the path: read the onboarding files (Shared rules), then run "Kickoff" of `onboarding.md` from its plan. Nothing of this plan runs. A switch keeps the place: on a setup branch, keep the branch and reuse the open issue #<n>, so the kickoff skips its branch step (kickoff step 5), and in its issue step (kickoff step 4) runs only the confirmed `gh issue edit` of the reused issue, if any.

## 4. Bootstrap

Run these in order:

1. **Repository with commits**: you are on an up-to-date `<main>` ([Start from `<main>`](#start-from-main)), or on the setup branch of a stopped run. Nothing to do here.
2. **Empty repository: name the branch.** If `<current>` is not `<main>`, run `git branch -m <main>` (it renames the unborn branch).
3. **Ignore the work directory.** Add the `.gitignore` lines of the plan now, before any file in `<workDir>` exists.
4. **Empty repository only** (the guard allows the first commit on `<main>` and its first push):
   1. Write `README.md` if it is missing: `# <project name>` and one sentence about the project.
   2. Run `git add -- .gitignore README.md`.
   3. Write `chore: initial commit` to `<drafts>/commit-msg.txt`. Run `git commit -F <drafts>/commit-msg.txt`.
   4. Run `git push -u origin <main>`. The plan confirmed it.
5. **Labels**: run the confirmed `gh label create` commands, one per label: `gh label create 'type:chore' --color cfd3d7 --description 'Maintenance, config, or dependencies'`. A label that already exists is not an error; continue.

## 5. Issue

When you reuse an open issue, run only its confirmed `gh issue edit` command, if any, and skip the rest of this step.

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

1. Read the issue: `gh issue view <n> --json title,body,labels,url`. Read it after step 5, so the labels line of the ticket shows the labels after a `gh issue edit`.
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

`loom.json`, the ticket, the commit, and the `done` entry make `loom-state` route the task to `/loom:describe-pr`. It opens a short oneshot PR. After the merge, `/loom:finish-task` offers the main branch ruleset: it knows the setup task by `task.setup` in the state on the task branch, and by the ticket title `Set up loom` on the main branch.

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

The path `fast-resume`: an earlier run of the fast path stopped on `<branch>` (for example after failing checks), or the setup PR of the fast path is open. Continue where it stopped. Never write a second `in-progress` entry after a `done` entry. On a setup branch, setup never stops on an active task and never offers a stash.

1. `<task dir>` is `<workDir>/<n>-loom-setup`. `<main>`, `<workDir>`, and the docs paths come from the state when `.claude/loom.json` exists (Values). Compare with `origin/<main>`, not the local `<main>`: a fresh clone may have no local `<main>`. Run `git fetch origin <main>` first.
   - If `gh pr list --head <branch> --state merged --json number` lists a PR, stop: `Result: the setup PR of #<n> is merged; the cleanup is left`, `Next: git switch <main>, then git pull --ff-only, then /loom:finish-task #<n>`.
2. `<task dir>/00-ticket.md` exists and its `mode` is not `oneshot` (another mode, or none): change only the `mode:` line of its frontmatter to `mode: oneshot`. Setup owns the mode of the setup task: the fast path writes `oneshot`. Name the change in the final message.
3. `log.md` has `## Phase 1 — done`: the setup commit exists. Write nothing. Go to item 5.
4. The setup commit exists (`git log --format=%h --grep='^Phase 1: oneshot' origin/<main>..HEAD` prints a hash), but `log.md` has no `done` entry (also on a fresh clone, where the ignored task directory is missing):
   - If `<task dir>/00-ticket.md` is missing, write it from the issue as steps 9.1 and 9.2 describe.
   - Append the done entry as step 9.8 describes, with that hash. Do not write an `in-progress` entry.
   - Go to item 5.
5. If `gh pr list --head <branch> --state open --json number` lists a PR, stop: `Result: the setup PR is open`, plus the restored files of items 2 to 4, if any. `Next: /loom:next` (it reads the PR state). The restore comes first: without the ticket and the `done` entry, `loom-state` finds no task, and its `Next:` leads back to `/loom:setup`.
6. The setup commit exists (items 3 and 4): go to step 10 (`next.command` is `/loom:describe-pr`).
7. Otherwise the setup commit is still missing. Run step 2 (detect; skip [Nothing to change](#nothing-to-change)), step 3, step 7, step 8, and step 9 on this branch:
   - The plan of step 3 lists the setup commit: every path outside `<workDir>` that differs from `<main>` (`git status --porcelain --untracked-files=all` and `git diff --name-only origin/<main>...HEAD`), plus the targets that are still missing or different. Files an earlier run wrote count as part of the commit, also when they are identical to the templates.
   - Skip steps 4 to 6: the issue and the branch exist. Run labels or stack commands only if the plan still lists them.
