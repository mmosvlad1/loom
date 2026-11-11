<!--
Template of the task summary `<docsDir>/tasks/<n>-<slug>.md` (quick and full mode only).
Guidance for describe-pr. Remove every guidance comment before you commit.
- The file is committed and permanent. Write for a reader who never saw the task directory.
- Apply the shared `writing-style.md` strictly. Link files with paths relative to the repository root.
- The H1 is `# #<n> <issue title>`, e.g. `# #42 Auth flow`.
-->

# #<n> <Issue title>

## Problem

<!-- Two to four sentences from 00-ticket.md: what did not work or did not exist, and for whom. -->

## Outcome

<!-- What works now that did not work before. One short paragraph or a list of 3-5 items. -->

## Key Decisions

<!--
One line per resolved decision of 03-design.md and 04-plan.md that matters after the merge.
Link the ADR when one exists: `- Agent state lives in SQLite ([ADR 0003](../architecture/decisions/0003-use-sqlite-for-agent-state.md)).`
Mark decisions taken by the round cap: `(accepted by default)`. Write `None.` when there are none.
-->

## Implementation

<!--
One line per implementation phase, in order: `1. <phase name> — <commit subject>`.
Use the commit subject, not the hash: the rebase and the squash merge change hashes.
Add one sentence per phase only if the name does not say what it built.
Then, only if `task.metrics` in the loom-state output is not null, one line:
`Process metrics: <task.metrics.line>`, copied exactly, e.g.
`Process metrics: 9 subagent runs (research 4, implement 5), 2 review rounds (1 changes-needed), 1 checks retry, subagent time 14 min`.
Without `task.metrics`, write no Process metrics line. Never estimate the numbers.
-->

## Deviations from Plan

<!--
From log.md: the `Deviations:` and `Additions:` lines of every phase, `Fix:` entries, and `## Plan change` entries.
One item per deviation: what differs and why. Write `None.` when the code follows the plan.
-->

## Verification

<!--
The checks that ran (`checks.check` and its result), the specific automated commands of the plan,
and the manual steps with their result. Do not claim a manual step passed unless the user confirmed it.
-->

## Follow-ups

<!--
Work that this task found but did not do: out-of-scope items, nits worth a change, open risks.
One item per follow-up. describe-pr proposes each one as a new issue. Write `None.` when there are none.
-->
