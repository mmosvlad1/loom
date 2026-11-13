---
name: finish-task
description: Merges the task's PR and cleans up - checks that the branch is up to date and the required checks pass, squash-merges after confirmation, syncs the main branch, deletes the task branch, and archives the task directory. Every step is safe to re-run. After the setup task it offers the main branch ruleset.
disable-model-invocation: true
argument-hint: "[#issue, only to resume on the main branch]"
model: inherit
allowed-tools: Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr) Bash(loom-state --json) Bash(loom-state --json --pr) Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)
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
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/bash-calls.md` (one command per Bash call: no `cd`, no chaining)
- `${CLAUDE_PLUGIN_ROOT}/skills/_shared/final-answer.md` (format of your last message)

Read these files before you ask the user anything. The skill's tool permissions (`allowed-tools`) last only until the user's next message; after that, reads of plugin files may ask for permission.

Below, `<main>` is `mainBranch`, `<branch>` is `branch`, `<n>` is `task.number`, and `<task dir>` is `task.dir`. `<workDir>` is `workDir` from the state (the parent directory of `task.dir`). `<required check>` is `ci.requiredCheck` from the state: the CI check that runs `checks.check` (default `check`). `<setup task>` is `task.setup`: `true` for the setup task (step 7). Note these values now: after the merge you are on `<main>`, where `loom-state` reports no task.

## 1. Check preconditions

Read the state above. Take the first matching row.

| Check | Action |
|---|---|
| The state is empty, and the argument names an issue `#<k>` | A merge may have stopped before the pull: the main branch of a setup task gets `.claude/loom.json` only from the merge. Run `git pull --ff-only` (if it fails, stop: `Result: git pull failed: <the error>`, `Next: /loom:finish-task #<k>` after the user fixes it). Then run `loom-state --json` and take the rows of this table again with that state. If it is still empty, stop as in the next row. |
| The state is empty | Stop: `Result: not a loom project (no .claude/loom.json)`, `Next: /loom:setup` |
| `onMain` is `true`, and the argument names an issue `#<k>` | Go to [Resume on the main branch](#resume-on-the-main-branch) |
| `onMain` is `true` | Stop: `Result: on the main branch; finish-task runs from the task branch`, `Warning: a merge that stopped before the cleanup resumes with /loom:finish-task #<n>`, `Next:` from `next.command` |
| `task` is `null`, or `task.archived` is `true` | Stop: `Result: no active task for <branch>`, `Next:` from `next.command` |
| `rebaseInProgress` is `true` | Stop: `Result: a rebase of <branch> is in progress`, `Next: /loom:iterate rebase` |
| `workingTree` is `null` | Stop: `Result: git status failed: <the error from its warning>`, `Next: fix the git error, then /loom:next` |
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

Without required checks on GitHub (no ruleset or branch protection), you still wait for `<required check>` and enforce it by name.

First note the PR head and title: `gh pr view --json headRefOid,title`. `<head sha>` is `headRefOid`; it must equal `git rev-parse HEAD` (step 2 pushed every local commit). `<title>` is the PR title. The merge in step 4 uses both, so it merges exactly the head whose checks you watch.

Run `gh pr checks --required --watch`. It waits until every required check finishes, which can take many minutes:

- Run it with the longest Bash timeout (600000 ms), or in the background and wait for it to finish.
- If the Bash call times out while checks are still running, run the command again. Pending is not failed.

Read the result:

| Result | Action |
|---|---|
| Every required check passes | Continue with [CI item](#ci-item), then step 4. |
| A required check fails | Do not merge. Stop: `Result: required checks fail on PR #<number>: <names>`, `Next: /loom:iterate`. |
| The output says there are no required checks | Continue with [Without required checks](#without-required-checks). |
| Any other error | Stop: `Result: <the error>`. |

Every other failing check is a `Warning:` line, in every case.

### Without required checks

1. Run `gh pr checks --watch`. It waits for all checks. The timeout rules above apply. A non-zero exit because a check failed is not an error here: continue with item 2.
2. Run `loom-state --json --pr`. Read `pr.requiredCheck`: the state of the check named `<required check>`.

| `pr.requiredCheck` | Action |
|---|---|
| `passing` | Continue with [CI item](#ci-item), then step 4. Add to the merge summary: `GitHub requires no check; loom checked <required check> by name.` |
| `failing` | Do not merge. Stop: `Result: check <required check> fails on PR #<number>`, `Next: /loom:iterate`. |
| `pending` | The watch ended early. Run item 1 again, at most 3 times in all. Then stop: `Result: check <required check> is still pending on PR #<number>`, `Next: /loom:finish-task`. |
| `missing` | No check with that name ran. Report `no required checks, and no check named <required check>` on its own line. Merging then needs an explicit "yes, merge without required checks" in step 4. |

### CI item

`describe-pr` can write the *CI item* into the PR body: the unticked line `` - [ ] CI check `<required check>` passes on this PR ``. The CI item gets its tick in step 4 only when all are true:

- `pr.requiredCheck` is `passing`. After "Every required check passes", this run has not read it yet: run `loom-state --json --pr` now.
- `<task dir>/pr-body.md` exists and has the unticked line.
- `pr.bodyInSync` is `true`: the PR body on GitHub equals `<task dir>/pr-body.md`. The tick uploads the file as the new body, so it must not differ.

With `pr.bodyInSync` `false` and the unticked line in the file, do not tick. Add `Warning: the PR body on GitHub differs from <task dir>/pr-body.md; the CI item is not ticked` to the final message.

Otherwise change nothing: no file, no unticked line, another state of the check, or a merge without checks (`missing`). Do not change the file before the "yes" of step 4. A re-run after a declined merge must still find the unticked line.

## 4. Merge

1. Show what happens: `PR #<number> "<title>" is squash-merged into <main> as one commit with the subject "<title>"; the local and remote branch <branch> are deleted.` Add the checks result. When the CI item gets its tick (step 3), add: `The CI item of the PR body gets its tick.` One confirmation covers the tick and the merge.
2. Ask for confirmation. When step 3 found no check at all (`missing`), ask for its explicit confirmation.
3. After "yes", when the CI item gets its tick, do this first:
   - Change `[ ]` to `[x]` in that line of `<task dir>/pr-body.md` with the Edit tool.
   - Run `gh pr edit --body-file <task dir>/pr-body.md`. The permission system asks for it (an ask rule); that is intended.
   - If `gh pr edit` fails, add `Warning: gh pr edit failed: <the error>; the CI item on GitHub is not ticked`. Continue with the merge.
4. Then run:
   `gh pr merge --squash --delete-branch --subject '<title>' --match-head-commit <head sha>`
   - Give no PR number: it selects the PR of the current branch.
   - Quote the title with the single-quote rule of `git-flow.md` (every `'` becomes `'\''`). `--subject` keeps the Conventional Commits title, which ends with `(#<n>)`, as the squash commit subject.
   - `--match-head-commit` refuses the merge if someone pushed after the checks you watched.
5. If it fails (for example a missing approval, a ruleset, or a new head commit), stop with `Result: <the error>`. Nothing else changed, except the tick of the CI item.

**From here on, every stop ends with `Next: /loom:finish-task #<n>`.** After the merge you are on `<main>`, where only the argument `#<n>` finds the task again ([Resume on the main branch](#resume-on-the-main-branch)).

## 5. Sync the main branch

Run each command; each one is safe when its work is already done:

1. `git switch <main>` (`gh pr merge` may already have switched).
2. `git pull --ff-only`.
3. `git fetch --prune`.
4. If `git rev-parse --verify --quiet refs/heads/<branch>` succeeds, the local branch still exists: run `git branch -D <branch>`. Otherwise skip it.

## 6. Archive the task directory

1. The target is `<workDir>/_archive/<task dir name>`.
2. If `<task dir>` does not exist and the target exists, the archive is done. Skip this step.
3. If both exist, stop: `Result: <task dir> and its archive copy both exist; keep one`, `Next: /loom:finish-task #<n>`.
4. Otherwise run `mkdir -p <workDir>/_archive`, then `mv <task dir> <workDir>/_archive/`.

## 7. Ruleset after the setup task

Only for the setup task. Otherwise skip this step:

- On the task branch (this run started there): `task.setup` was `true` in the state at the start (`<setup task>`).
- On the main branch ([Resume on the main branch](#resume-on-the-main-branch)): the state has no task, so take it from the ticket. The first `# ` heading of `<task dir>/00-ticket.md` is `Set up loom`.

1. Read the rules that apply to `<main>`: `gh api repos/{owner}/{repo}/rules/branches/<main>`. This GET is read-only and needs no confirmation. The permission system still asks for it (the `Bash(gh api *)` ask rule); that is intended. (The list endpoint `…/rulesets` has no `conditions`, so it cannot tell which branch a ruleset targets.) If a rule of type `required_status_checks` lists `<required check>` as a `context` in `parameters.required_status_checks`, a ruleset already requires the check: skip this step. If the GET fails with HTTP 403 or 404, the rules are unknown: continue with item 2. Any other error (network, auth): stop with `Result: <the error>` and `Next: /loom:finish-task #<n>`.
2. Read the classic branch protection of `<main>`: `gh api repos/{owner}/{repo}/branches/<main>/protection`. This GET is read-only too; the permission system asks for it in the same way. Take the first matching row:

   | Result | Action |
   |---|---|
   | HTTP 404 (`Branch not protected`) | No classic protection. Continue. |
   | HTTP 403 | Unknown: a private repository on GitHub Free, or no admin access. Continue: still offer the ruleset. The POST of step 6 reports whether rulesets are available. |
   | `required_status_checks.contexts`, or a `context` in `required_status_checks.checks`, is `<required check>` | The classic protection already requires the check: skip this step. |
   | Success otherwise | The protection does not require the check. Continue. |
   | Any other error (network, auth) | Stop with `Result: <the error>` and `Next: /loom:finish-task #<n>`. |
3. Read the default branch: `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name` (read-only). If it is `<main>`, the ref is `~DEFAULT_BRANCH`; otherwise it is `refs/heads/<main>`.
4. Offer the ruleset and ask for confirmation. It protects `<main>`:
   - changes reach `<main>` only through a PR, with 0 required approvals
   - the required status check is `<required check>` (the CI check that runs `checks.check`)
   - force pushes and deletion are blocked
   - there are no bypass actors: nobody, also no admin, can bypass it
5. After "yes", write this JSON to `<workDir>/_archive/<task dir name>/ruleset.json`, with `<main>`, `<ref>`, and `<required check>` replaced (a JSON string: escape `"` and `\`). If the file exists (a re-run), Read it before you Write it:
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
           "required_status_checks": [ { "context": "<required check>" } ] } }
     ]
   }
   ```
6. Run `gh api --method POST repos/{owner}/{repo}/rulesets --input <workDir>/_archive/<task dir name>/ruleset.json`.
7. If GitHub refuses (403 or 404: rulesets on private repositories need a paid plan), add `Warning: ruleset not available; only the loom guard hook protects <main>`. If the call fails for another reason (network, auth), stop with `Result: <the error>` and `Next: /loom:finish-task #<n>`.

## 8. Final message

Run `loom-state --json`. Use the `final-answer.md` format:

```text
Result: PR #<number> merged into <main> (<squash commit short hash>); task directory archived to <workDir>/_archive/<task dir name>
Warning: <one line per warning, if any>
Next: /clear, then /loom:start-task #<n> (pick the issue with /loom:backlog)
```

- Take the squash commit from `git log -1 --format=%h <main>`.
- `Next:` comes from `loom-state` and is mapped as `final-answer.md` describes. On the main branch `next.command` is `/loom:start-task #<n>`: write it as `loom-state` prints it, with the literal `#<n>`. Do not choose an issue.
- A stop in steps 5-7 (a failed `git pull --ff-only`, archive, or ruleset call) does not use this message: it ends with `Result: <the error>` and `Next: /loom:finish-task #<n>`.

---

## Resume on the main branch

An earlier run merged the PR and switched to `<main>`, but did not finish. The argument names the issue `#<k>`.

1. `<workDir>` is `workDir` from the state (the fresh state of section 1 when the injected state was empty). Find the task directory: `<workDir>/<k>-*`, or else `<workDir>/_archive/<k>-*` (archived already; only step 7 may be left). If neither exists, stop: `Result: no task directory for #<k>`.
2. Check the merge: `git log --format='%h %s' <main>` must have a commit whose subject contains `(#<k>)`. Run `git pull --ff-only` first; if it fails, stop with `Result: git pull failed on <main>: <the error>` and `Next: /loom:finish-task #<k>` after the user fixes it. If no such commit exists, stop: `Result: no merge of #<k> found on <main>; run /loom:finish-task from the task branch`.
3. Run steps 5 to 8 with `<n>` = `<k>` and `<task dir>` = the directory of step 1. Each step skips what is already done. The branch is `<type>/<k>-<slug>`: `<slug>` is the task directory name after `<k>-`, and `<type>` is the type of the merge commit subject. If it is unclear, skip the branch deletion and add a `Warning:` line.
