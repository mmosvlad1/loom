---
task: <n>-<slug>
phase: design
status: draft
based_on: [00-ticket.md, 02-research.md]
updated: YYYY-MM-DD
---

<!--
Guidance for the design skill. Remove every guidance comment before you set `status: in-review`.
- Follow the shared `visual-conventions.md` for every tree, diff, and signature.
- Rationale text follows rules 1, 2, 6, and 7 of the writing style.
-->

# Design

## Current State

<!-- What exists today and what the user experiences, from the research. Short bullets. Use `path:line` only where a reader needs to find the code. -->

- <current behavior>

## Desired End State

<!-- What is true when the task is done: new behavior, problems solved, what a user can do. Short bullets. -->

- <end-state behavior>

## Out of Scope

<!-- What this task does not do, so later phases do not add it. Write `None.` only if nothing is near the edge of the scope. -->

- <excluded item>

## Proposed Architecture

<!--
The smallest set of views that makes the change clear:
- before/after file tree or a `diff` block of the file layout
- `diff` blocks for changed calls, types, or config
- key interfaces as signatures; plain language blocks for new flows
- existing patterns to follow, each with a `path:line` reference and a short excerpt
Put one or two sentences of prose next to each view.
-->

## Open Questions — Round 1 of ~<M>

<!--
Follow the shared `question-rounds.md` exactly:
- every question is open; you may recommend, never resolve
- only questions whose answers do not depend on another open question
- `**Q<n>.` at the start of the line, 2-4 options, exactly one `— recommended: <reason>`
- no questions inside code blocks
-->

**Q1. <Question about a design choice?>**
<One or two sentences of context, or "See Proposed Architecture.">
- a) <option> — recommended: <one-line reason>
- b) <option> — <trade-off>

**Q2. <Question about another independent design choice?>**
- a) <option> — <trade-off>
- b) <option> — recommended: <one-line reason>

## Resolved Decisions

<!-- Empty when the design skill writes the artifact. Only /loom:iterate adds rows, from the user's answers. -->

| # | Question | Decision | Rationale | Round | ADR? |
|---|---|---|---|---|---|

## Testing Approach

<!-- How the change is tested: which existing test patterns to follow (with `path:line`), which new tests, and which checks from `.claude/loom.json` cover them. -->
