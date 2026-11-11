---
# The subagent events hook (LOOM_SPEC.md 11.6) parsed the checks.check line of the implementer's report.
type: regex
pattern: '"event":"stop"[^\n]*"agent":"implementer"[^\n]*"result":"(pass|fail)"'
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/events.jsonl" }
---
