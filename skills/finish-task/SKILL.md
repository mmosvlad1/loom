---
name: finish-task
description: Merges the task's PR and cleans up - checks that the branch is up to date and the required checks pass, squash-merges after confirmation, syncs the main branch, deletes the task branch, and archives the task directory. Every step is safe to re-run. After the setup task it offers the main branch ruleset.
disable-model-invocation: true
argument-hint: "[#issue, only to resume on the main branch]"
model: haiku
effort: low
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr) Bash(loom-state --json) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
---

# Finish Task

You merge the pull request of the task and clean up. Every step checks first whether it already happened, so a re-run after a partial failure continues where it stopped.

## State

Current task state from `loom-state`, with the pull request state:

!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr`

Arguments: $ARGUMENTS

`task.dir` is relative to the project's git top level (your working directory), never to the plugin directory.

## Shared rules

Read these files in full before you start:

- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/git-flow.md` (confirmations, push, stash)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/pr-update.md` (commit leftover docs changes and push)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md` (style of the final message)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

Below, `<main>` is `mainBranch`, `<branch>` is `branch`, `<n>` is `task.number`, and `<task dir>` is `task.dir`. `<workDir>` is the parent directory of `task.dir` (`workDir` in `.claude/loom.json`). Note these values now: after the merge you are on `<main>`, where `loom-state` reports no task.

## 1. Check preconditions

Read the state above. Take the first matching row.

| Check | Action |
|---|---|
| The state is empty | Stop: `Result: not a loom project (no .claude/loom.json)`, `Next: /loom:setup` |
| `onMain` is `true`, and the argument names an issue `#<k>` | Go to [Resume on the main branch](#resume-on-the-main-branch) |
| `onMain` is `true` | Stop: `Result: on the main branch; finish-task runs from the task branch`, `Warning: a merge that stopped before the cleanup resumes with /loom:finish-task #<n>`, `Next:` from `next.command` |
| `task` is `null`, or `task.archived` is `true` | Stop: `Result: no active task for <branch>`, `Next:` from `next.command` |
| `pr` is `null`, `task.pr` is set, and `warnings` has a `gh` warning | Stop: `Result: cannot read the state of PR #<task.pr>`, `Warning: <the gh warning>; check gh auth status`, `Next: /loom:finish-task` |
| `pr` is `null` | Stop: `Result: the branch has no PR`, `Next:` from `next.command` (normally `/loom:describe-pr`) |
| `pr.state` is `MERGED` | The merge already happened. If `workingTree` is `dirty`, the changes are not in the merge: offer the stash of `git-flow.md` (confirmation) first. Docs-only changes are usually leftovers of this task: say so, and offer discard after the user looks at them as the other choice; without "yes", stop with `Result: PR #<number> is merged, but the working tree has uncommitted changes` and `Next: commit or stash the changes, then /loom:finish-task`. Go to step 5. |
| `pr.state` is `CLOSED` | Stop: `Result: PR #<number> is closed without a merge`. Ask the user to reopen it or start over. |
| `implementation.blocked` or `implementation.inProgress` is set, or `implementation.done` is less than `implementation.total` | Stop: `Result: implementation phases are left (<done> of <total> done)`, `Next:` from `next.command` |
| `pr.reviewDecision` is `CHANGES_REQUESTED` | Stop: `Result: PR #<number> has requested changes`, `Next: /loom:iterate` |
| `workingTree` is `dirty` and `workingTreeDocsOnly` is `true` | The docs changes are an interrupted docs refresh. Run the shared `pr-update.md` (docs commit, then the push with confirmation). Then continue with step 2. |
| `workingTree` is `dirty` (code changes) | Stop: `Result: working tree has uncommitted code changes`, `Next: /loom:iterate` with no argument (it keeps the changes as a fix, or stashes or discards them) |

## 2. Branch up to date

1. Local commits that the PR does not have would be lost by the merge. Run `git rev-list --count @{u}..HEAD`.
   - If it fails (no upstream) or the count is above 0: show `git log --oneline @{u}..HEAD`. Offer to push them, as `git-flow.md` describes (confirmation). Without "yes", stop: `Result: local commits are not on PR #<number>`.
2. If `pr.behindMain` is above 0, or `pr.mergeStateStatus` is `BEHIND`: stop with `Result: <branch> is behind <main>` and `Next: /loom:iterate rebase`.

## 3. Required checks

First note the PR head and title: `gh pr view --json headRefOid,title`. `<head sha>` is `headRefOid`; it must equal `git rev-parse HEAD` (step 2 pushed every local commit). `<title>` is the PR title. The merge in step 4 uses both, so it merges exactly the head whose checks you watch.

Run `gh pr checks --required --watch`. It waits until every required check finishes, which can take many minutes:

- Run it with the longest Bash timeout (600000 ms), or in the background and wait for it to finish.
- If the Bash call times out while checks are still running, run the command again. Pending is not failed.

Read the result:

| Result | Action |
|---|---|
| Every required check passes | Continue with step 4. |
| A required check fails | Do not merge. Stop: `Result: required checks fail on PR #<number>: <names>`, `Next: /loom:iterate`. |
| The output says there are no required checks | Run `gh pr checks` (all checks) and show the result. Report `no required checks` on its own line. Merging then needs an explicit "yes, merge without required checks" in step 4. A failing optional check is a `Warning:` line. |
| Any other error | Stop: `Result: <the error>`. |

## 4. Merge

1. Show what happens: `PR #<number> "<title>" is squash-merged into <main> as one commit with the subject "<title>"; the local and remote branch <branch> are deleted.` Add the checks result.
2. Ask for confirmation. Without required checks, ask for the explicit confirmation of step 3.
3. After "yes", run:
   `gh pr merge --squash --delete-branch --subject '<title>' --match-head-commit <head sha>`
   - Give no PR number: it selects the PR of the current branch.
   - Quote the title with the single-quote rule of `git-flow.md` (every `'` becomes `'\''`). `--subject` keeps the Conventional Commits title, which ends with `(#<n>)`, as the squash commit subject.
   - `--match-head-commit` refuses the merge if someone pushed after the checks you watched.
4. If it fails (for example a missing approval, a ruleset, or a new head commit), stop with `Result: <the error>`. Nothing else changed.

**From here on, every stop ends with `Next: /loom:finish-task #<n>`.** After the merge you are on `<main>`, where only the argument `#<n>` finds the task again ([Resume on the main branch](#resume-on-the-main-branch)).

## 5. Sync the main branch

Run each command; each one is safe when its work is already done:

1. `git switch <main>` (`gh pr merge` may already have switched).
2. `git pull`.
3. `git fetch --prune`.
4. If `git rev-parse --verify --quiet refs/heads/<branch>` succeeds, the local branch still exists: run `git branch -D <branch>`. Otherwise skip it.

## 6. Archive the task directory

1. The target is `<workDir>/_archive/<task dir name>`.
2. If `<task dir>` does not exist and the target exists, the archive is done. Skip this step.
3. If both exist, stop: `Result: <task dir> and its archive copy both exist; keep one`, `Next: /loom:finish-task #<n>`.
4. Otherwise run `mkdir -p <workDir>/_archive`, then `mv <task dir> <workDir>/_archive/`.

## 7. Ruleset after the setup task

Only for the setup task: `<branch>` is `chore/<n>-loom-setup`, or the first `# ` heading of `00-ticket.md` is `Set up loom`. Otherwise skip this step.

1. Read the rules that apply to `<main>`: `gh api repos/{owner}/{repo}/rules/branches/<main>`. This GET is read-only and needs no confirmation. (The list endpoint `…/rulesets` has no `conditions`, so it cannot tell which branch a ruleset targets.) If the result has any rule with a `ruleset_id`, a ruleset already protects `<main>`: skip this step.
2. Read the default branch: `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name` (read-only). If it is `<main>`, the ref is `~DEFAULT_BRANCH`; otherwise it is `refs/heads/<main>`.
3. Offer the ruleset and ask for confirmation. It protects `<main>`:
   - changes reach `<main>` only through a PR, with 0 required approvals
   - the required status check is `check` (the CI job)
   - force pushes and deletion are blocked
   - there are no bypass actors: nobody, also no admin, can bypass it
4. After "yes", write this JSON to `<workDir>/_archive/<task dir name>/ruleset.json`, with `<main>` and `<ref>` replaced:
   ```json
   {
     "name": "loom: protect <main>",
     "target": "branch",
     "enforcement": "active",
     "bypass_actors": [],
     "conditions": { "ref_name": { "include": ["<ref>"], "exclude": [] } },
     "rules": [
       { "type": "deletion" },
       { "type": "non_fast_forward" },
       { "type": "pull_request", "parameters": {
           "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": false,
           "require_code_owner_review": false, "require_last_push_approval": false,
           "required_review_thread_resolution": false } },
       { "type": "required_status_checks", "parameters": {
           "strict_required_status_checks_policy": false,
           "required_status_checks": [ { "context": "check" } ] } }
     ]
   }
   ```
5. Run `gh api --method POST repos/{owner}/{repo}/rulesets --input <workDir>/_archive/<task dir name>/ruleset.json`.
6. If GitHub refuses (403 or 404: rulesets on private repositories need a paid plan), add `Warning: ruleset not available; only the loom guard hook protects <main>`. If the call fails for another reason (network, auth), stop with `Result: <the error>` and `Next: /loom:finish-task #<n>`.

## 8. Final message

Run `loom-state --json`. Use the `final-answer.md` format:

```text
Result: PR #<number> merged into <main> (<squash commit short hash>); task directory archived to <workDir>/_archive/<task dir name>
Warning: <one line per warning, if any>
Next: /clear, then /loom:next
```

- Take the squash commit from `git log -1 --format=%h <main>`.
- `Next:` comes from `loom-state` and is mapped as `final-answer.md` describes.
- A stop in steps 5-7 (a failed `git pull`, archive, or ruleset call) does not use this message: it ends with `Result: <the error>` and `Next: /loom:finish-task #<n>`.

---

## Resume on the main branch

An earlier run merged the PR and switched to `<main>`, but did not finish. The argument names the issue `#<k>`.

1. Read `workDir` from `.claude/loom.json` (if it is missing: the `tasks` directory inside `.loom`). Find the task directory: `<workDir>/<k>-*`, or else `<workDir>/_archive/<k>-*` (archived already; only step 7 may be left). If neither exists, stop: `Result: no task directory for #<k>`.
2. Check the merge: `git log --format='%h %s' <main>` must have a commit whose subject contains `(#<k>)`. Run `git pull` first. If no such commit exists, stop: `Result: no merge of #<k> found on <main>; run /loom:finish-task from the task branch`.
3. Run steps 5 to 8 with `<n>` = `<k>` and `<task dir>` = the directory of step 1. Each step skips what is already done. The branch is `<type>/<k>-<slug>`: `<slug>` is the task directory name after `<k>-`, and `<type>` is the type of the merge commit subject. If it is unclear, skip the branch deletion and add a `Warning:` line.
