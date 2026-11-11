---
# In "## Change outline", before "## Verification": the phase lines 1. and 2., then the first fenced
# block of the section (any info string) with a tree glyph or a +/-/~ diff line inside it. Lines before
# that block may not open a fence, so a closing fence never counts as an opening one.
type: regex
pattern: '^## Change outline[ \t]*\n(?:(?!## |```|~~~)[^\n]*\n)*?1\. [^\n]+\n(?:(?!## |```|~~~)[^\n]*\n)*?2\. [^\n]+\n(?:(?!## |```|~~~)[^\n]*\n)*?(`{3,}|~{3,})[\w-]*[ \t]*\n(?:(?!\1)[^\n]*\n)*?(?:[^\n]*(?:├──|└──)|[+~-] ?\S)(?:(?!^## )[\s\S])*?^## Verification'
flags: m
target: { source: file, path: ".loom/tasks/7-bulk-discount-tiers/pr-body.md" }
---
