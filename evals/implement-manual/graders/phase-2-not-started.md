---
type: regex
pattern: '^## Phase 2\b'
flags: m
match: not_contains
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/log.md" }
---
