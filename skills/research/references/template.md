---
task: <n>-<slug>
phase: research
status: draft
based_on: [01-research-questions.md]
git_commit: <git rev-parse --short HEAD>
updated: YYYY-MM-DD
---

<!--
Guidance for the research skill. Remove every guidance comment before you set `status: in-review`.
- based_on: full mode [01-research-questions.md]; quick mode [00-ticket.md].
- This artifact describes the code as it exists at `git_commit`. No recommendations, critique, proposals, or "should".
- Every claim about code has a `path:line` or `path:start-end` reference.
- Do not use `diff` blocks or `+`/`-` change markers: nothing changes in research.
-->

# Research

## Summary

<!-- 2-4 short paragraphs: the key components, data flows, and relationships found. Synthesize; do not list every detail. -->

## Findings

<!--
One `###` section per research question, in question order.
The heading states the takeaway (what is true), not the topic and not the question.
  Bad:  ### Session storage
  Bad:  ### How are sessions persisted?
  Good: ### Sessions persist to SQLite before the handler returns
Write concept first, then the reference: "The handler validates the token (`src/auth.py:40-52`) ..."
Use a range for adjacent lines. Add a call tree, file tree, table, or signature where it shows the shape faster than prose.
-->

### 1. <Takeaway for question 1>

Question: <question 1, verbatim>

<Explanation with `path:line` references.>

#### Testing patterns

<Test file locations, test type (unit, integration, e2e), fixtures, and mocking patterns. If no tests exist, write that.>

### 2. <Takeaway for question 2>

Question: <question 2, verbatim>

<Explanation with `path:line` references.>

#### Testing patterns

<Test file locations and patterns, or "No tests exist for this area.">

## Patterns & Conventions

<!-- Conventions the code follows today (naming, module layout, error handling, test style), each with one `path:line` example. Describe; do not judge. -->

## External Sources

<!-- One line per external source: what it states, and its link. Every finding from `loom:web-search-researcher` keeps its link. Write `None.` if no external source was used. -->

- <What the source states> — <URL>

## Not Found / Unclear

<!--
What the research could not find or trace, as descriptive statements ("No caller of `X` was found outside `src/a/`").
Also every claim that failed the claim check, with what the check found instead.
Write `None.` if everything was found.
-->
