---
task: <n>-<slug>
phase: plan
status: draft
based_on: [00-ticket.md, 02-research.md, 03-design.md]
updated: YYYY-MM-DD
---

<!--
Guidance for the plan skill. Remove every guidance comment before you set `status: in-review`.
- based_on: quick mode [00-ticket.md, 02-research.md]; full mode adds 03-design.md.
- Every implementation phase is a vertical slice: it cuts across layers and ends in something that can be run, queried, or tested.
- Every implementation phase passes the checks from `.claude/loom.json` on its own. Phase N never needs phase N+1 to verify.
- Follow the shared `visual-conventions.md` for trees, diffs, and signatures.
-->

# Plan

## Phase Overview

<!--
One top-level checkbox per implementation phase, in order: `- [ ] <N>. <name>, verifiable via <how>`.
`loom-state` parses these lines. Keep them unindented, numbered, and unchecked. Only `implement` ticks them.
The numbers and names match the `## Phase <N>: <name>` sections below.
-->

- [ ] 1. <Thinnest end-to-end slice>, verifiable via <command or test>
- [ ] 2. <Next slice>, verifiable via <command or test>

## Open Questions — Round 1

<!--
Add a round only where the plan is uncertain. Follow the shared `question-rounds.md` exactly.
If nothing is uncertain, use the heading `## Open Questions` with the single line `None.` under it.
-->

**Q1. <Question about an uncertain plan choice?>**
- a) <option> — recommended: <one-line reason>
- b) <option> — <trade-off>

## Resolved Decisions

<!-- Empty when the plan skill writes the artifact. Only /loom:iterate adds rows. Design decisions stay in 03-design.md. -->

| # | Question | Decision | Rationale | Round | ADR? |
|---|---|---|---|---|---|

## Phase 1: <name>

### Goal

<!-- One or two sentences: what works at the end of this implementation phase that did not work before. -->

### Changes

<!--
A file tree of the files this implementation phase creates, changes, or deletes (with `new:` / `changed:` comments),
then key signatures and `diff` blocks for changed shapes. Include the tests to add or change, following the research's testing patterns.
-->

### Verification

<!--
Automated lines first: the checks from `.claude/loom.json` and any specific command (a test file, a curl call).
A Manual line only if the check cannot reasonably be automated. Delete the Manual line otherwise:
`implement` stops after every implementation phase that has a Manual line.
-->

- [ ] Automated: <checks.test command, e.g. make test>
- [ ] Manual: <only if it cannot be automated>

## Phase 2: <name>

### Goal

### Changes

### Verification

- [ ] Automated: <checks.check command, e.g. make check>
