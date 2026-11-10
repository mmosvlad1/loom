---
# No decision written as a list item or question under Resolved Decisions (rows: resolved-decisions-empty).
type: regex
pattern: '^## Resolved Decisions[^\n]*\n(?:(?!## )[^\n]*\n)*?(?:[-*+] |\*\*Q\d|Q\d+[.:)] )'
flags: m
match: not_contains
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/03-design.md" }
---
