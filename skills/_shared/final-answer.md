# Final Answer Format

End every skill with this message format and nothing else. The user reads it to decide the next command. Apply the writing style strictly (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/writing-style.md`).

## Format

```text
Artifact: <path of the artifact you wrote or changed>
Status: <status>
Open questions: <count>
Next: <next step>
```

Optional lines, in this order, between `Open questions` and `Next`:

- `Manual verification:` followed by a list of steps, when `implement` stops for manual verification.
- `Accepted by default:` followed by the question numbers, when the round cap resolved questions (see `question-rounds.md`).
- `Clarify:` one line per question you need the user to answer outside the normal round: an unclear answer, or a question that is not minor after the round cap. Name the question number and what is unclear, e.g. `Clarify: Q4 - option d does not exist; choose a, b, or c.`
- `Warning:` one line per warning that needs the user's attention (e.g. stale research, research not reviewed).

## Fields

- **Artifact**: the path relative to the repository root, e.g. `.loom/tasks/42-auth-flow/03-design.md`. A skill that writes no artifact replaces the `Artifact` and `Status` lines with one `Result:` line (e.g. the PR URL, or the merged commit).
- **Status**: the frontmatter `status` (`draft`, `in-review`, `approved`). For `implement`, the progress: `implementation phase 2 of 3 done (d4e5f6)` or `implementation phase 2 blocked: <reason>`.
- **Open questions**: the number of `**Q<n>.` items under `## Open Questions`, as `loom-state` reports it. Add the round for design and plan: `3 (round 1 of ~3)`. Write `0` when none are open. Omit the line when the skill writes no artifact.
- **Next**: compute it, do not remember it. Run `"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json` after your last write and read `next.command`:
  - `/loom:iterate …` (open round, approval, fix): write the command; it continues in this session.
  - `/loom:describe-pr` or `/loom:finish-task`: write `/clear, then /loom:describe-pr` (or `/loom:finish-task`).
  - Any other command: write `/clear, then /loom:next`.

## Rules

- No recap of the work. No summary of the artifact. No introduction or closing sentence.
- Do not repeat the open questions of the round; the artifact holds them. Only `Clarify:` lines name a question.
- Do not list files you read or agents you ran.
- Write the `Next` line last.

## Examples

Design with an open round:

```text
Artifact: .loom/tasks/42-auth-flow/03-design.md
Status: in-review
Open questions: 3 (round 1 of ~3)
Next: /loom:iterate <answers>, e.g. /loom:iterate 1a, 2b, 3: <text>. An empty /loom:iterate accepts all recommendations.
```

Research finished:

```text
Artifact: .loom/tasks/42-auth-flow/02-research.md
Status: in-review
Open questions: 0
Next: /clear, then /loom:next
```

Implementation phase that needs manual verification:

```text
Artifact: .loom/tasks/42-auth-flow/log.md
Status: implementation phase 2 of 3 done (d4e5f6)
Open questions: 0
Manual verification:
- Run `make dev`, open http://localhost:8000/login, and sign in with the seed user.
- Check that the session cookie has the `HttpOnly` flag.
Next: run the manual steps, then /clear, then /loom:next
```
