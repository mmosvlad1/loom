<!--
Template of the PR body (quick and full mode). Guidance for describe-pr. Remove every guidance comment.
- The first line closes the issue. Keep `Closes #<n>` exactly, so GitHub links and closes the issue on merge.
- Apply the shared `writing-style.md`. Use the shared `visual-conventions.md` for trees and diff blocks.
- Size limit: if the whole body is longer than 60,000 characters (GitHub's limit is 65,536),
  replace the plan inside <details> with its `## Phase Overview` section and this line:
  `The full plan is longer than the PR body allows; only its Phase Overview is attached.`
- The PR title is not part of the body: `<type>(<scope>): <summary of the task> (#<n>)` (Conventional Commits).
- Required sections: `pullRequest.requiredSections` in the loom-state output (empty by default). A required heading
  that this layout already has (the same heading line) is that section. See the comment before <details>.
-->

Closes #<n>

## Why

<!--
Exactly one sentence of at most 25 words, on one line: the problem or need this PR answers, from 00-ticket.md.
Not a list of what changed: Change outline shows that.
-->

## Special things to note

<!--
1-3 list items (`- `), most important first. Only what a reviewer must know and cannot see quickly in the diff:
- a deviation from the plan or an addition, recorded in log.md
- a risk
- a non-obvious decision
- a migration or a manual step (also a manual verification step that the user has not confirmed)
- a known limit
If nothing qualifies, write the single line None. (no backticks) and nothing else. Do not add filler.
-->

## Change outline

<!--
First one line per implementation phase, in order: `1. <phase name> — <commit subject>`.
Use the commit subject, not the hash: the rebase and the squash merge change hashes.
Then one visual that shows the shape of the change. Pick the one that shows it better:
- a file tree of the changed files only, with `new:` or `changed:` comments (`visual-conventions.md`)
- an interface `diff` block: only signatures and public API (functions, classes, fields, config keys, commands)
Omit unchanged parts.
-->

## Verification

<!--
The checks and their result (`checks.check`: pass), specific automated commands, and manual steps the user confirmed.
When the ticket has a `## Screens` section: one line per screen, its path and the result of its manual comparison.
-->

## Decisions

<!--
Links to the ADRs this PR adds and to the task summary, by their repository paths, e.g.
`- [ADR 0003: Use SQLite for agent state](<docs.decisions.dir>/0003-use-sqlite-for-agent-state.md)`
`- Task summary: [<docs.tasks>/42-auth-flow.md](<docs.tasks>/42-auth-flow.md)`
Add one line per other resolved decision a reviewer needs. Take the real paths from `docs` in the loom-state output.
-->

<!--
Required sections: every heading of `pullRequest.requiredSections` that this layout does not have, exactly as listed,
in the order of the list. Fill each from the task's artifacts, or write the single line None. when nothing applies.
Without required sections, nothing goes here.
-->

<details><summary>Implementation plan</summary>

<!-- The body of 04-plan.md without its frontmatter. Keep its headings. -->

</details>

<!--
oneshot mode: a short body with only three parts, in this order: the `Closes #<n>` line, the Why section, and the Verification section.
No Special things to note, no Change outline, no Decisions, and no plan.
A screens task adds one `Closes #<k>` line per covered update issue whose screen is in the branch diff, right after `Closes #<n>`.
The required sections that this layout does not have are the exception: they come after the Verification section.
-->
