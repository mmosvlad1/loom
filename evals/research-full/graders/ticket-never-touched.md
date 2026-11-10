---
# Any Read, Grep, Glob, or Bash call whose input names the ticket, by the skill or by a
# subagent (subagent tool calls are in the trace too, with parent_tool_use_id set).
type: regex
pattern: '"name":"(Read|Grep|Glob|Bash)","input":\{[^}]*00-ticket'
match: not_contains
target: trace
---
