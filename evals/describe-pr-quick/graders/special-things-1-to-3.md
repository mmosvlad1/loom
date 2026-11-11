---
# Between "## Special things to note" and "## Change outline": the single line None., or 1-3
# "- " items (indented continuation lines allowed).
type: regex
pattern: '^## Special things to note[ \t]*\n+(?:None\.[ \t]*\n+|(?:- [^\n]*\S[^\n]*\n(?:[ \t]+\S[^\n]*\n)*\n*){1,3})## Change outline'
flags: m
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/pr-body.md" }
---
