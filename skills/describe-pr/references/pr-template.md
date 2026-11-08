<!--
Template of the PR body (quick and full mode). Guidance for describe-pr. Remove every guidance comment.
- The first line closes the issue. Keep `Closes #<n>` exactly, so GitHub links and closes the issue on merge.
- Apply the shared `writing-style.md`. Use the shared `visual-conventions.md` for trees and diff blocks.
- Size limit: if the whole body is longer than 60,000 characters (GitHub's limit is 65,536),
  replace the plan inside <details> with its `## Phase Overview` section and this line:
  `The full plan is longer than the PR body allows; only its Phase Overview is attached.`
- The PR title is not part of the body: `<type>(<scope>): <summary of the task> (#<n>)` (Conventional Commits).
-->

Closes #<n>

## Summary

<!-- Two to four sentences: the problem and what this PR changes. No list of files. -->

## Changes

<!--
The shape of the change: one line per implementation phase (`1. <phase name> — <commit subject>`),
then a small file tree or a `diff` block where it helps a reviewer. Omit unchanged parts.
-->

## Verification

<!-- The checks and their result (`checks.check`: pass), specific automated commands, and manual steps the user confirmed. -->

## Decisions

<!--
Links to the ADRs this PR adds and to the task summary, e.g.
`- [ADR 0003: Use SQLite for agent state](docs/architecture/decisions/0003-use-sqlite-for-agent-state.md)`
`- Task summary: [docs/tasks/42-auth-flow.md](docs/tasks/42-auth-flow.md)`
Add one line per other resolved decision a reviewer needs. Use the real docsDir path.
-->

<details><summary>Implementation plan</summary>

<!-- The body of 04-plan.md without its frontmatter. Keep its headings. -->

</details>

<!--
oneshot mode: a short body with only three parts, in this order: the `Closes #<n>` line, the Summary section, and the Verification section.
No Changes, no Decisions, and no plan.
-->
