# Update an Open PR

After new commits on a task branch whose PR is open, bring the PR up to date: refresh the docs that the commits affect, update the PR body, and push. `iterate` runs these steps after a post-PR fix. `implement` runs them after the last implementation phase when the PR is open (a plan change after the PR added phases).

Below, `<n>` is `task.number`, `<slug>` is `task.slug`, `<task dir>` is `task.dir`, `<docs>` is `docsDir` from `.claude/loom.json` (default `docs`), and `<number>` is the PR number (`pr.number`, or `task.pr`).

## Steps

A working tree that is dirty only below `<docs>` (`workingTreeDocsOnly` is `true` in the `loom-state` output) is an interrupted earlier run of these steps. Treat those changes as yours: check them against the new commits in step 1, and commit them there. With code changes in the tree, do not run these steps; the skill that called them says what to do.

1. **Task summary.** If `<docs>/tasks/<n>-<slug>.md` exists and the new commits change what it states (Implementation, Deviations from Plan, Verification), update it.
   - Write the message `docs(#<n>): update task summary` to `<task dir>/commit-msg.txt` (Read the file first if it exists, as `git-flow.md` says).
   - Stage the file (`git add -- <path>`), and every other changed file below `<docs>`. Run `git commit -F <task dir>/commit-msg.txt`, as the shared `git-flow.md` describes.
2. **PR body.** If the new commits change what the PR body states (Why, Special things to note, Change outline, Verification, Decisions, or the attached plan):
   - Update `<task dir>/pr-body.md`. `describe-pr` wrote it; if it is missing, start from `gh pr view --json body`.
   - Keep the layout of `describe-pr`: Why stays one sentence; Special things to note keeps 1-3 list items, or the single line None. (no backticks); Change outline keeps one line per implementation phase, then a file tree or an interface `diff` block.
   - A body in the layout before loom v1.1 (`## Summary` and `## Changes`, for example from `gh pr view`) is rewritten into this layout: Why, Special things to note, Change outline, Verification, Decisions, then the plan.
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
