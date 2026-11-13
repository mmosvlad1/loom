# Update an Open PR

After new commits on a task branch whose PR is open, bring the PR up to date: refresh the docs that the commits affect, update the PR body, and push. `iterate` runs these steps after a post-PR fix. `implement` runs them after the last implementation phase when the PR is open (a plan change after the PR added phases). `screens` runs them after a landing on a screens task whose PR is open.

Below, `<n>` is `task.number`, `<slug>` is `task.slug`, `<task dir>` is `task.dir`, and `<number>` is the PR number (`pr.number`, or `task.pr`). Doc paths come from `docs` in the `loom-state` output (the docs map); never build one yourself. `<tasks>` is `docs.tasks`. The **docs paths** are `docs.dir` and every path of `docs`: `workingTreeDocsOnly` counts a change at or below one of them as a docs change.

## Steps

A working tree that is dirty only in the docs paths (`workingTreeDocsOnly` is `true` in the `loom-state` output) is an interrupted earlier run of these steps. Treat those changes as yours: check them against the new commits in step 1, and commit them there. With code changes in the tree, do not run these steps; the skill that called them says what to do.

1. **Task summary.** If `<tasks>/<n>-<slug>.md` exists and the new commits change what it states (Implementation, Deviations from Plan, Verification), update it.
   - When you update it, also refresh its `Process metrics:` line from `task.metrics.line` of a new `loom-state --json` call (the format of `describe-pr`). Without `task.metrics`, leave the summary without that line. A change of the metrics alone is no reason to update the summary.
   - Write the message `docs(#<n>): update task summary` to `<task dir>/commit-msg.txt` (Read the file first if it exists, as `git-flow.md` says).
   - Stage the file (`git add -- <path>`), and every other changed file in the docs paths. Run `git commit -F <task dir>/commit-msg.txt`, as the shared `git-flow.md` describes.
2. **PR body.** If the new commits change what the PR body states (the `Closes` lines, Why, Special things to note, Change outline, Verification, Decisions, or the attached plan):
   - Update `<task dir>/pr-body.md`. `describe-pr` wrote it; if it is missing, start from `gh pr view --json body`.
   - Keep the layout of `describe-pr`: Why stays one sentence; Special things to note keeps 1-3 list items, or the single line None. (no backticks); Change outline keeps one line per implementation phase, then a file tree or an interface `diff` block.
   - Keep the required sections: `pullRequest.requiredSections` from the `loom-state` output, at the place `describe-pr` gives them (a heading of the layout is that section; every other one comes after Decisions, oneshot: after Verification, before `<details>`, in the order of the list). Update a required section only when the new commits change what it states.
   - A body in the layout before loom v1.1 (`## Summary` and `## Changes`, for example from `gh pr view`) is rewritten into this layout: Why, Special things to note, Change outline, Verification, Decisions, then the plan. A heading of `pullRequest.requiredSections` never marks the old layout: ignore the required headings in this check, also `## Summary` or `## Changes`.
   - **Covered issues** (a screens task, `task.screens` is `true`): compute the `Closes #<k>` lines after `Closes #<n>` again, with the method of `describe-pr`:
     - For each `Covers #<k>` line of the ticket's Context, run `gh issue view <k> --json title`. Its title `Design screens: update <screen ID>` names the screen.
     - The branch diff: `git diff origin/<main>...HEAD --name-only` (without `origin/<main>`: the local `<main>`; `<main>` is `mainBranch`).
     - The screen is in the diff when the diff lists a file below `docs.screens` with that screen ID. Then add the line `Closes #<k>` after `Closes #<n>`.
     - Keep no line whose screen is not in the diff: a covered issue whose screen did not land stays open.
   - Write the CI item of `describe-pr` (`` - [ ] CI check `<ci.requiredCheck>` passes on this PR ``) unticked again, also when it was ticked: the checks run again on the new head.
   - A phase line names the phase's own commit subject (`1. <phase name> — <commit subject>`). Fix commits get no phase line. Mention a fix in Special things to note only if a reviewer needs to know it.
   - Keep the body under 60,000 characters (the rule of `describe-pr`).
   - Show the changed parts. Ask for confirmation.
   - After "yes", run `gh pr edit <number> --body-file <task dir>/pr-body.md`.
3. **Push**, as the Push rules of `git-flow.md` describe:
   - Show `git log --oneline @{u}..HEAD`.
   - Ask for confirmation.
   - Run `git push`. If the branch history was rewritten (a rebase in this run), run `git push --force-with-lease` instead.
   - Without "yes", do not push. Add `Warning: commits not pushed; PR #<number> does not have them yet` to the final message.

The PR checks run again on the pushed commits. `/loom:finish-task` watches them.
