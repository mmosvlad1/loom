---
# pullRequest.requiredSections is ["## Test plan"]: the section comes after "## Decisions" and before
# <details> (LOOM_SPEC.md 13.6).
type: regex
pattern: '^## Decisions[ \t]*$[\s\S]*^## Test plan[ \t]*$[\s\S]*<details>'
flags: m
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/pr-body.md" }
---
