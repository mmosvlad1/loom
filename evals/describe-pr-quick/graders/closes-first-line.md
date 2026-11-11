---
# No m flag: ^ is the start of the file.
type: regex
pattern: '^Closes #7[ \t]*\r?\n'
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/pr-body.md" }
---
