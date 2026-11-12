# loom

A Claude Code plugin for structured, agent-driven development: **Research → Plan → Implement**.

loom turns a GitHub issue into a merged pull request through explicit phases. Each phase runs in a fresh session and writes a markdown artifact; the next phase reads only those artifacts. You stay in control at the checkpoints that matter: design approval, plan approval, manual verification, push, and merge.

**Status:** version 1.1.0, early development: loom has not been used on a real project yet. All skills exist: `setup`, `backlog`, `start-task`, `research-questions`, `research`, `design`, `plan`, `iterate`, `implement`, `describe-pr`, `finish-task`, and `next`, with the state script, the safety hooks, and the hooks that enforce checks. Milestone M6 added the eval suite (`evals/`, `make eval`) and loom's own CI. Version 1.1.0 adds the new PR layout, one command per Bash call in every skill, inline PR review comments in `iterate`, and process metrics; see [CHANGELOG.md](CHANGELOG.md). See [LOOM_SPEC.md](LOOM_SPEC.md) for the full specification.

## Install

```
/plugin install loom --marketplace mmosvlad1/loom
```

Or in two steps:

```
/plugin marketplace add mmosvlad1/loom
/plugin install loom@loom
```

In a project that `/loom:setup` prepared, `.claude/settings.json` registers the marketplace and enables loom, but each collaborator still installs it once per clone: `claude plugin install loom@loom --scope project`.

## Getting started

1. **Install** the plugin (above), then open your project in Claude Code.
2. **`/loom:setup`** detects the stack and writes `.claude/loom.json`, the checks entry point (`Makefile` or `package.json` scripts), CI with a `check` job (or keeps an existing workflow and records the check name of its job in `ci.requiredCheck`), `.claude/settings.json`, the `docs/` skeleton, and a short `CLAUDE.md`. It shows every change first and works through loom's own flow: an issue "Set up loom" and a `chore/<n>-loom-setup` branch.
3. **`/loom:describe-pr`**, then **`/loom:finish-task`** merge the setup PR. After the merge, `finish-task` offers a ruleset that protects the main branch.
4. **`/loom:backlog`** discusses ideas, helps fill `docs/product/vision.md`, and creates GitHub issues (labels `type:*`, `size:*`, `mode:*`).
5. **`/loom:start-task #<n>`** picks the mode, creates the branch and `.loom/tasks/<n>-<slug>/00-ticket.md`.
6. **`/clear`, then `/loom:next`**, again and again: `next` runs the next phase for the mode (research, design, plan, implement). Answer question rounds and approve with `/loom:iterate`.
7. **`/loom:describe-pr`** writes the task summary and ADRs into `docs/`, pushes, and opens the PR (with confirmation). The PR body has a one-sentence Why, 1–3 Special things to note, and a Change outline (a file tree or an interface `diff`). The task summary ends its Implementation section with a Process metrics line, e.g. `9 subagent runs (research 4, implement 5), 2 review rounds (1 changes-needed), 1 checks retry, subagent time 14 min`.
8. **`/loom:finish-task`** waits for green checks (also for the check named in `ci.requiredCheck` when GitHub requires none), squash-merges (with confirmation), and archives the task directory.

## Highlights

- Three modes: `oneshot`, `quick`, `full`
- GitHub Issues as the backlog, one branch and one squash-merged PR per task
- Batched design questions in rounds instead of one question at a time
- Checks enforced by hooks, not trusted from the agent
- Every loom subagent run is recorded in `.loom/tasks/<n>-<slug>/events.jsonl` (agent, phase, result, duration); `loom-state --json` sums it up as `task.metrics`
- `/clear` → `/loom:next` between phases
- Durable knowledge (task summaries, ADRs, architecture) committed to `docs/`; working artifacts stay local

## Development

Run the working copy with `claude --plugin-dir /path/to/loom` in a sandbox repository.

- **`make check`** runs the unit tests (`tests/`, standard library `unittest`, no model calls) and `claude plugin validate --strict`. It needs no credentials. CI runs it on every pull request and push to `main` (`.github/workflows/ci.yml`), then runs `make test` again on Python 3.9, the oldest supported version.
- **`make eval`** runs the eval suite in `evals/` with `claude plugin eval`. Each case builds a small fixture repository and runs one loom scenario; the graders are model-free (files, regexes, tool calls):

  | Case | Checks |
  |---|---|
  | `research-full` | `/loom:research` writes `02-research.md` in review with `file:line` references and never reads `00-ticket.md`; the subagent events hook writes `events.jsonl` |
  | `design-full` | `/loom:design` writes round 1 with every question open and an empty Resolved Decisions table |
  | `implement-manual` | `/loom:implement` commits phase 1 and stops for manual verification before phase 2; `events.jsonl` has the reviewer's verdict and the implementer's checks result |
  | `guard-main` | the hook blocks `git commit` on `main` |
  | `describe-pr-quick` | `/loom:describe-pr` writes `pr-body.md` with Why, Special things to note, Change outline, Verification, and Decisions, and does not push or open the PR |

  Evals call the model and cost tokens, so `make check` does not run them. Every case runs once on `haiku`; one run of the whole suite costs well under 1 USD. `EVAL_MAX_COST` (default 10 USD) is a hard ceiling. Pass more flags through `EVAL_ARGS`:

  ```
  make eval EVAL_ARGS='--case design-full'           # one case
  make eval EVAL_ARGS='--runs 3'                     # repeat every case
  make eval EVAL_ARGS='--model sonnet --keep-temp'   # another model; keep workspaces and traces
  ```

  Results (JSON and an HTML report) go to `evals/results/`, which git ignores.

  `make eval` runs every case. On macOS, install git with Homebrew first: `brew install git`. Inside the eval sandbox the Bash tool always runs `/usr/bin/git`, an xcrun shim. Without another git the shim fails there, so `implement-manual` cannot commit; full Xcode alone did not help. With Homebrew git installed, the shim runs Homebrew git and `implement-manual` passed (2 of 2 local runs). `describe-pr-quick` also commits with git, so it needs the same; with Homebrew git it passed 4 of 4 local runs (about 0.02 USD each). It also needs `gh` installed (no login needed). Without Homebrew git, `make eval` prints a warning and still runs every case.

  The **Evals** workflow (Actions → Evals → Run workflow) runs every case on a pinned `macos-26` runner. The first four cases passed there (about 0.25 USD for those four); `describe-pr-quick` has not run on the runner yet. It needs an `ANTHROPIC_API_KEY` repository secret. Its `claude_version` input installs another Claude Code version. Linux cannot run the skill cases: the eval sandbox there keeps `TMPDIR` read-only, so every Bash call fails (likely an upstream Claude Code bug, LOOM_SPEC.md §24.2).

## Credits

loom is derived from the Research-Plan-Implement workflow in [HumanLayer](https://github.com/humanlayer/humanlayer) (Apache-2.0).

## License

[Apache License 2.0](LICENSE)
