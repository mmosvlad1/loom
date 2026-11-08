---
task: <n>-<slug>
phase: research-questions
status: draft
based_on: [00-ticket.md]
updated: YYYY-MM-DD
---

<!--
Guidance for the research-questions skill. Remove every guidance comment before you set `status: in-review`.
- The research phase reads ONLY this file. It never sees the ticket.
- Nothing in this file may reveal what will be built: no feature names from the ticket, no "should", no "how would we".
-->

# Research Questions

## Key Context Pointers

<!--
High-signal starting points from the ticket and the user, copied VERBATIM: full URLs, exact paths, package names, repositories.
Copy only the pointer itself, never the sentence that says why it matters for the task.
Write `None.` if the ticket gives no pointers.
-->

- Links: <URL, verbatim>
- Paths: <path/to/file/or/dir, verbatim>
- Packages: <package or dependency name, verbatim>

## Questions

<!--
2-8 descriptive questions about what exists today: where, how, and how components interact.
Point each question at where the answer may be ("In src/sessions/, how does ...?").
Good: "How does the request pipeline in src/http/ handle retries today?"
Bad:  "How should we add retries to the HTTP client?"
-->

1. <How does X work today, end to end, and which components take part?>
2. <Where is Y defined, and which modules read or write it?>
