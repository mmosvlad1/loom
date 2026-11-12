<!--
Template of an ADR in `docs.decisions.dir` (from the loom-state output). The file name is `docs.decisions.pattern`
(default `<NNNN>-<slug>.md`) with the number and the slug filled in.
Guidance for describe-pr. Remove every guidance comment before you commit.
- One ADR per resolved decision with `ADR? = yes` (architecture level: storage, protocols, agent structure, major libraries).
- `NNNN` is the next free number in the decisions directory, zero-padded to the length of the pattern's number
  placeholder (`<NNNN>`: 0001 if it is empty). The title uses the same digits as the file name. Never reuse a number.
- `<slug>`: the title in lowercase ASCII, non-alphanumerics replaced by `-`, at most 6 words.
- The title states the decision: "Use SQLite for agent state", not "Storage".
- The status line has exactly this form, with today's date from loom-state.
-->

# NNNN. <Decision title>
Status: Accepted · Task: #<n> · Date: YYYY-MM-DD

## Context

<!-- The forces behind the decision: the problem, the constraints, and what the code looked like (from research and design). -->

## Decision

<!-- The decision in one or two sentences, active voice: "We store agent state in SQLite." Then the key details that follow from it. -->

## Alternatives Considered

<!-- The other options of the question round, each with the reason it was not chosen. -->

## Consequences

<!-- What becomes easier, what becomes harder, and what a later change must keep in mind. -->
