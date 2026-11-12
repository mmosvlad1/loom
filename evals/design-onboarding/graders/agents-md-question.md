---
# One question of the round names AGENTS.md and the push or the confirmation: its heading line or its text
# before the next question or section.
type: regex
pattern: '^\*\*Q\d+\.(?=(?:(?!\n\*\*Q\d|\n## )[\s\S])*?AGENTS\.md)(?=(?:(?!\n\*\*Q\d|\n## )[\s\S])*?(?:[Pp]ush|[Cc]onfirm))'
flags: m
target: { source: file, path: ".loom/tasks/1-loom-setup/03-design.md" }
---
