# log.md Format

`<task dir>/log.md` records every implementation phase. `loom-state` parses its headings to compute `implementation` (phase statuses, `inProgress`, `blocked`) and the next step. The body lines are for people and for `describe-pr`.

`implement` writes it; `iterate` appends fix and plan-change entries. `setup` and `screens` write the entries of their own tasks. The implementer agent never writes it.

## Rules

- `log.md` has no frontmatter.
- **Append only.** Never edit or delete an earlier entry. A new state is a new entry.
- One entry is one `## ` heading plus the lines up to the next `## ` heading.
- Leave one blank line between entries.
- Do not put entries inside code fences. `loom-state` ignores fenced lines; an unclosed fence hides the rest of the file and adds a warning.

## Entries

### Phase started

```markdown
## Phase N — in-progress
Started: <today>
```

Write it before you launch the implementer for implementation phase N.

### Phase done

```markdown
## Phase N — done — <commit short hash>
Checks: <checks.check command>: pass; <one line, e.g. lint ✓ typecheck ✓ test ✓ (42 passed)>
Reviewer: <pass | pass after K fix attempts>; nits: <list, or None>
Deviations: <each deviation with its reason, or None>
Additions: <each change the plan does not mention, or None>
Manual verification: <the steps the user still runs, or None>
```

- `<commit short hash>` is `git rev-parse --short HEAD` right after the phase commit.
- `Deviations` collects the reviewer's deviations and the implementer's reported deviations. `describe-pr` copies them into the task summary.

### Fix of a done phase (`iterate`)

```markdown
## Phase N — done — <fix commit short hash>
Fix: <one line per fix item>
Checks: <checks.check command>: pass; <one line>
Reviewer: <pass | pass after K fix attempts>; nits: <list, or None>
Deviations: <how the code now differs from the plan, and why; or None>
```

The phase stays `done`: the last entry of a phase wins.

### Phase blocked

```markdown
## Phase N — blocked
Reason: <one line: the failing check, the remaining blocking items, or the open problem>
```

- Keep the reason on one line. `loom-state` reports it as `implementation.blocked.reason`, and `/loom:next` shows it.
- Only `/loom:iterate` resolves a blocked phase. It appends a `done` entry when the fix is committed.

### Plan change (`iterate`)

```markdown
## Plan change — <today>
Deviations: <what changed in the plan, and why>
Affected implementation phases: <numbers>; done phases unchanged: <numbers>
```

This heading has no `Phase N —` form, so it is not an implementation phase entry.

## Grammar (what `loom-state` parses)

A phase entry heading matches this pattern, case-insensitive, on an unindented line outside code fences:

```text
## Phase <N> <sep> <status> [<sep> <extra>]
```

| Part | Rule |
|---|---|
| `## ` | Exactly two `#` at the start of the line, then whitespace. `#` or `###` headings are not phase entries. |
| `<N>` | The implementation phase number, digits only. In oneshot mode it is always `1`. |
| `<sep>` | One or more of `—` (em dash), `–` (en dash), or `-`, with optional spaces around. loom writes ` — `. |
| `<status>` | `in-progress`, `done`, or `blocked`. |
| `<extra>` | `done`: the first word is the commit hash. `blocked`: the whole text is the reason. `in-progress`: ignored. |

- **Last entry wins.** For each phase number, only the last heading counts.
- **Blocked reason.** For `blocked` without `<extra>`, the reason is the first `Reason: <text>` line of the entry. A `###` heading inside the entry does not end it; another `#` or `##` heading does.
- **Other lines.** `Started:`, `Checks:`, `Reviewer:`, `Deviations:`, `Additions:`, `Manual verification:`, and `Fix:` lines are not parsed.
- **Other headings.** A `##` heading that does not match (for example `## Plan change — <date>`) is not an implementation phase entry and ends the previous entry.
- **Log and plan.** A `log.md` entry wins over the Phase Overview checkbox of the same implementation phase in `04-plan.md`. A phase with no entry is `done` if its checkbox is ticked, else `pending`.
- **Derived state.** `implementation.inProgress` is the lowest phase number whose last entry is `in-progress`. `implementation.blocked` is the lowest phase number whose last entry is `blocked`, with its reason.
