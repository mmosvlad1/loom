---
# "Wholesale customers" occurs only in the body of 00-ticket.md (tests/test_evals.py checks this),
# so the trace holds it only if the ticket's content reached the skill or a subagent, by any tool.
type: regex
pattern: 'Wholesale customers'
match: not_contains
target: trace
---
