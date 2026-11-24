---
# Any Read, Grep, Glob, or Bash call whose input names the screens directory (docs.screens, LOOM_SPEC.md 9.14.5),
# by the skill or by a subagent, except inside an exclusion: Grep `glob: "!<path>/**"` (also rg `--glob '!<path>/**'`
# and the git pathspec `':!<path>'`), the git pathspec `':(exclude)<path>'`, and find `-not -path '*<path>/*'`.
# A Grep glob can exclude several paths in one brace list, `"!{.loom/**,<path>/**}"`: the path is accepted as the
# first element (after `!{`) and after another element (after `**,`). Known limit: a brace list without `!` that
# names the path after another element is not caught; the grader screen-content-absent covers what it would find.
# The pattern walks the input string by string, so a `}` inside a string (a brace list) does not end the search.
type: regex
pattern: '"name":"(Read|Grep|Glob|Bash)","input":\{(?:[^}"]|"(?:[^"\\]|\\.)*")*?"(?:[^"\\]|\\.)*?(?<!!)(?<!!\{)(?<!\*\*,)(?<!\(exclude\))(?<!-path ''\*)docs/design/screens'
match: not_contains
target: trace
---
