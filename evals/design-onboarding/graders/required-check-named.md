---
# One question of the round names ci.requiredCheck, the word job (or jobs), and test as a whole token
# (also jobs.test), in its heading line or its text before the next question or section.
type: regex
pattern: '^\*\*Q\d+\.(?=(?:(?!\n\*\*Q\d|\n## )[\s\S])*?ci\.requiredCheck)(?=(?:(?!\n\*\*Q\d|\n## )[\s\S])*?\bjobs?\b)(?=(?:(?!\n\*\*Q\d|\n## )[\s\S])*?(?:^|[^\w.]|\bjobs\.)test(?![\w-]))'
flags: m
target: { source: file, path: ".loom/tasks/1-loom-setup/03-design.md" }
---
