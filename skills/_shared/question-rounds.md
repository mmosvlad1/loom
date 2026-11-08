# Question Rounds Protocol

`design` and `plan` ask open questions in rounds. `iterate` records the answers and writes the next round. Follow this protocol exactly: `loom-state` counts the open questions from the artifact, and `/loom:next` routes on that count.

A round is one batch of open questions in an artifact. All rounds of an artifact stay in one session.

## Who decides

- The user resolves design questions. You never close a question yourself, except under the round cap (see "How many rounds").
- Write every question as open, also when the answer seems obvious from the research.
- You may recommend one option. A recommendation is not a decision.
- When `design` or `plan` writes the first round, Resolved Decisions has no rows. Only answers from the user (or the round cap) add rows.

## Independence rule

A round contains only questions whose answers do not depend on another open question.

- Before you write a round, check each question: would a possible answer to another open question change this question or its options? If yes, defer it to a later round.
- A deferred question is not written in the artifact yet. Keep it for the round that its answer unlocks.

## Format

The artifact has exactly one open-questions section. Its heading is:

- `03-design.md`: `## Open Questions — Round N of ~M` (M is the expected number of rounds)
- `04-plan.md`: `## Open Questions — Round N`

```markdown
## Open Questions — Round 1 of ~3

**Q1. Where should agent state be persisted between runs?**
- a) SQLite — recommended: already a dependency, no infrastructure
- b) Redis
- c) JSON files

**Q2. Which component owns the retry policy?**
- a) The HTTP client — recommended: all calls already pass through it
- b) Each caller
```

Rules:

- Start each question with `**Q<n>.` at the beginning of the line. `loom-state` counts these lines.
- Give every question 2-4 options, labeled `a)` to `d)`.
- Mark exactly one option `— recommended: <one-line reason>`.
- You may add a short trade-off after another option (`- b) Redis — needs a server`).
- Keep the context a question needs in one or two sentences under the question line, or point to the section that explains it.
- Do not put questions inside code blocks. `loom-state` ignores code blocks.
- When no question is open, keep the heading `## Open Questions` with the single line `None.` under it.

## Numbering

- Number questions across rounds. Round 2 starts after the highest number of round 1.
- Never renumber. A question that stays open keeps its number in the next round.
- Never reuse the number of a resolved question.

## Answering

The user answers with `/loom:iterate <answers>`. Accept these forms:

| Answer | Meaning |
|---|---|
| `1a, 2b` | Q1 takes option a, Q2 takes option b |
| `3: <text>` | Q3 takes the custom answer `<text>` |
| `accept all except 2` | Every question of the current round takes its recommendation, except Q2 |
| empty `/loom:iterate`, or `ok` | Every question of the current round takes its recommendation |
| free text | Read it as answers where it clearly answers a question; otherwise treat it as feedback |

- A question with no answer stays open in the next round, with the same number.
- If an answer is unclear (an option that does not exist, or text that fits two options), do not guess. Keep the question open and ask about it in a `Clarify:` line of the final message (`final-answer.md`).
- A custom answer that raises a new dependent question unlocks that question for the next round.

## Interactive questions

A skill may also ask the questions of the current round with the interactive question tool (`AskUserQuestion`):

- Ask at most 4 questions per call. Split a larger round into several calls.
- Give each question 2-4 options. Put the recommended option first and add "(Recommended)" to its label.
- The tool lets the user type a custom answer. Record it as a custom answer.
- Write the round into the artifact before you ask. The artifact remains the source of truth.
- Record the answers in the artifact exactly as for answers typed with `/loom:iterate`.

## After each round

1. Move each answered question to the artifact's `## Resolved Decisions` section (in `03-design.md` and `04-plan.md`):

   ```markdown
   ## Resolved Decisions
   | # | Question | Decision | Rationale | Round | ADR? |
   |---|---|---|---|---|---|
   | Q1 | Where is agent state persisted? | SQLite | Already a dependency; no new infrastructure | 1 | yes |
   ```

   - Rationale: the user's reason, or the recommendation's reason if the user accepted it.
   - `ADR?` is `yes` for architecture-level decisions: storage, protocols, agent structure, major libraries. Otherwise `no`.
2. Rewrite every section the answers affect (e.g. Proposed Architecture, Testing Approach, implementation phase details). Remove text that assumed another option.
3. Write the next round. It contains only:
   - questions the answers unlocked
   - questions of the current round that are still open
4. If no open question affects the plan, end the rounds: write `None.` under `## Open Questions`.
5. Change `updated` in the frontmatter. Keep `status: in-review`.
6. End with the final answer (the shared `final-answer.md`, next to this file), including the open questions count.

## How many rounds

Rounds end when no open question affects the plan, not at a fixed count.

| Size | Expected rounds | Cap |
|---|---|---|
| S | 1-2 | 2 |
| M | 2-3 | 3 |
| L | 3-5 | 5 |

- Read the size from `task.size` in the `loom-state --json` output (validated there; start-task copies it from the `size:*` label). If it is `null`, use the size that matches the mode: quick → M, full → L.
- The caps come from `.claude/loom.json` → `rounds.cap` (defaults above).
- For `~M` in the design heading, use the upper bound of the expected range (S → 2, M → 3, L → 5).

### Accepted by default

When the answers to the round at the cap still leave questions open:

1. Resolve each remaining minor question with its recommendation.
2. Add it to Resolved Decisions with the Decision cell `<option> — accepted by default — revisit if needed`. Write the marker on exactly one line per question; `loom-state` counts these lines.
3. List their numbers in the `Accepted by default:` line of the final message, so the user can revisit them with `/loom:iterate`.

A question that still changes the architecture or the plan is not minor. Do not accept it by default. Keep it open and ask the user to answer it in a `Clarify:` line of the final message.
