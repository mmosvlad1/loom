---
type: regex
pattern: '^## (Summary|Changes)\b'
flags: m
match: not_contains
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/pr-body.md" }
---
