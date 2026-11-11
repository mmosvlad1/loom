---
# The subagent events hook (LOOM_SPEC.md 11.6) parsed the reviewer's verdict from last_assistant_message.
type: regex
pattern: '"event":"stop"[^\n]*"agent":"implementation-reviewer"[^\n]*"result":"(pass|changes-needed)"'
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/events.jsonl" }
---
