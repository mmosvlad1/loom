---
# The Screens table of the brief has one row per state (brief-template.md) and marks both rows drafted
# (LOOM_SPEC.md 9.14.6, stage 4): the default state and order-summary--empty, in either order.
type: regex
pattern: '^(?=[\s\S]*^\|[ \t]*`?order-summary`?[ \t]*\|[ \t]*drafted[ \t]*\|)(?=[\s\S]*^\|[ \t]*`?order-summary--empty`?[ \t]*\|[ \t]*drafted[ \t]*\|)'
flags: m
target: { source: file, path: ".loom/tasks/12-loom-screens/screens-brief.md" }
---
