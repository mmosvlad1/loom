---
# "Quillfeather Stationers" occurs only in the screen docs/design/screens/order-summary.html (tests/test_evals.py
# checks this), so the trace holds it only if the screen's content reached the skill or a subagent, by any tool.
type: regex
pattern: 'Quillfeather Stationers'
match: not_contains
target: trace
---
