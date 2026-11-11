---
type: regex
pattern: '<details>\s*<summary>\s*Implementation plan\s*</summary>[\s\S]*^## Phase Overview[\s\S]*^## Phase 2: [\s\S]*</details>'
flags: m
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/pr-body.md" }
---
