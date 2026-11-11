---
# One non-empty line between "## Why" and the next heading: no list item, no period followed by
# a space (a second sentence) except in e.g. and i.e., ending with a period.
type: regex
pattern: '^## Why[ \t]*\n+(?![-*] )(?:\b(?:e\.g|i\.e)\. |[^\n.]|\.(?=\S))+\.[ \t]*\n+## '
flags: m
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/pr-body.md" }
---
