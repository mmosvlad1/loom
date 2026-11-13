---
# Any Read, Grep, Glob, or Bash call whose input names the screens directory (docs.screens, LOOM_SPEC.md 9.14.5),
# by the skill or by a subagent, except inside an exclusion: Grep `glob: "!<path>/**"` (also rg `--glob '!<path>/**'`
# and the git pathspec `':!<path>'`), the git pathspec `':(exclude)<path>'`, and find `-not -path '*<path>/*'`.
type: regex
pattern: '"name":"(Read|Grep|Glob|Bash)","input":\{[^}]*?(?<!!)(?<!\(exclude\))(?<!-path ''\*)docs/design/screens'
match: not_contains
target: trace
---
