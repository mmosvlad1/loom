---
type: regex
pattern: '^## Resolved Decisions[^\n]*\n(?:(?!## )[^\n]*\n)*?\|(?!\s*#\s*\|)(?![-:| ]*$)'
flags: m
match: not_contains
target: { source: file, path: ".loom/tasks/1-loom-setup/03-design.md" }
---
