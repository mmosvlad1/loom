---
type: regex
pattern: '^## Why[ \t]*$[\s\S]*^## Special things to note[ \t]*$[\s\S]*^## Change outline[ \t]*$[\s\S]*^## Verification[ \t]*$[\s\S]*^## Decisions[ \t]*$'
flags: m
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/pr-body.md" }
---
