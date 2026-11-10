# loom

A Claude Code plugin for structured, agent-driven development: **Research → Plan → Implement**.

loom turns a GitHub issue into a merged pull request through explicit phases. Each phase runs in a fresh session and writes a markdown artifact; the next phase reads only those artifacts. You stay in control at the checkpoints that matter: design approval, plan approval, manual verification, push, and merge.

**Status:** early development. All skills exist: `setup`, `backlog`, `start-task`, `research-questions`, `research`, `design`, `plan`, `iterate`, `implement`, `describe-pr`, `finish-task`, and `next`, with the state script, the safety hooks, and the hooks that enforce checks. Milestone M6 added the eval suite (`evals/`, `make eval`) and loom's own CI. See [LOOM_SPEC.md](LOOM_SPEC.md) for the full specification.

## Install

```
/plugin install loom --marketplace mmosvlad1/loom
```

Or in two steps:

```
/plugin marketplace add mmosvlad1/loom
/plugin install loom@loom
```

## Getting started

1. **Install** the plugin (above), then open your project in Claude Code.
2. **`/loom:setup`** detects the stack and writes `.claude/loom.json`, the checks entry point (`Makefile` or `package.json` scripts), CI with a `check` job, `.claude/settings.json`, the `docs/` skeleton, and a short `CLAUDE.md`. It shows every change first and works through loom's own flow: an issue "Set up loom" and a `chore/<n>-loom-setup` branch.
3. **`/loom:describe-pr`**, then **`/loom:finish-task`** merge the setup PR. After the merge, `finish-task` offers a ruleset that protects the main branch.
4. **`/loom:backlog`** discusses ideas, helps fill `docs/product/vision.md`, and creates GitHub issues (labels `type:*`, `size:*`, `mode:*`).
5. **`/loom:start-task #<n>`** picks the mode, creates the branch and `.loom/tasks/<n>-<slug>/00-ticket.md`.
6. **`/clear`, then `/loom:next`**, again and again: `next` runs the next phase for the mode (research, design, plan, implement). Answer question rounds and approve with `/loom:iterate`.
7. **`/loom:describe-pr`** writes the task summary and ADRs into `docs/`, pushes, and opens the PR (with confirmation).
8. **`/loom:finish-task`** waits for green checks, squash-merges (with confirmation), and archives the task directory.

## Highlights

- Three modes: `oneshot`, `quick`, `full`
- GitHub Issues as the backlog, one branch and one squash-merged PR per task
- Batched design questions in rounds instead of one question at a time
- Checks enforced by hooks, not trusted from the agent
- `/clear` → `/loom:next` between phases
- Durable knowledge (task summaries, ADRs, architecture) committed to `docs/`; working artifacts stay local

## Development

Run the working copy with `claude --plugin-dir /path/to/loom` in a sandbox repository.

- **`make check`** runs the unit tests (`tests/`, standard library `unittest`, no model calls) and `claude plugin validate --strict`. It needs no credentials. CI runs it on every pull request and push to `main` (`.github/workflows/ci.yml`).
- **`make eval`** runs the eval suite in `evals/` with `claude plugin eval`. Each case builds a small fixture repository and runs one loom scenario; the graders are model-free (files, regexes, tool calls):

  | Case | Checks |
  |---|---|
  | `research-full` | `/loom:research` writes `02-research.md` in review with `file:line` references and never reads `00-ticket.md` |
  | `design-full` | `/loom:design` writes round 1 with every question open and an empty Resolved Decisions table |
  | `implement-manual` | `/loom:implement` commits phase 1 and stops for manual verification before phase 2 |
  | `guard-main` | the hook blocks `git commit` on `main` |

  Evals call the model and cost tokens, so `make check` does not run them. Every case runs once on `haiku`; one run of the whole suite costs well under 1 USD. `EVAL_MAX_COST` (default 10 USD) is a hard ceiling. Pass more flags through `EVAL_ARGS`:

  ```
  make eval EVAL_ARGS='--case design-full'           # one case
  make eval EVAL_ARGS='--runs 3'                     # repeat every case
  make eval EVAL_ARGS='--model sonnet --keep-temp'   # another model; keep workspaces and traces
  ```

  Results (JSON and an HTML report) go to `evals/results/`, which git ignores.

  On macOS the eval sandbox breaks `git` in the Bash tool, so `implement-manual` cannot commit there. `make eval` on macOS therefore runs only the cases tagged `local` (all but `implement-manual`) and prints a note. `make eval EVAL_FILTER=` runs every case. `--case` and `--tag` combine with AND, so on macOS `EVAL_ARGS='--case implement-manual'` needs `EVAL_FILTER=` too; without it the run finds no case and costs nothing. `implement-manual` is expected to pass on Linux, which is unverified until the first run of the **Evals** workflow (Actions → Evals → Run workflow). The workflow needs an `ANTHROPIC_API_KEY` repository secret.

## Credits

loom is derived from the Research-Plan-Implement workflow in [HumanLayer](https://github.com/humanlayer/humanlayer) (Apache-2.0).

## License

[Apache License 2.0](LICENSE)
