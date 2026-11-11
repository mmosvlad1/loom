---
# The subagent events hook (LOOM_SPEC.md 11.6) wrote a stop line for a research agent in the research phase.
type: regex
pattern: '"event":"stop"[^\n]*"agent":"(codebase-locator|codebase-analyzer|codebase-pattern-finder|web-search-researcher)"[^\n]*"phase":"research"'
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/events.jsonl" }
---
