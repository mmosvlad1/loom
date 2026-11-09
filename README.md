# loom

A Claude Code plugin for structured, agent-driven development: **Research → Plan → Implement**.

loom turns a GitHub issue into a merged pull request through explicit phases. Each phase runs in a fresh session and writes a markdown artifact; the next phase reads only those artifacts. You stay in control at the checkpoints that matter: design approval, plan approval, manual verification, push, and merge.

**Status:** early development. All skills exist: `setup`, `backlog`, `start-task`, `research-questions`, `research`, `design`, `plan`, `iterate`, `implement`, `describe-pr`, `finish-task`, and `next`, with the state script, the safety hooks, and the hooks that enforce checks. The eval suite and loom's own CI come in the next milestone (M6). See [LOOM_SPEC.md](LOOM_SPEC.md) for the full specification.

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

## Credits

loom is derived from the Research-Plan-Implement workflow in [HumanLayer](https://github.com/humanlayer/humanlayer) (Apache-2.0).

## License

[Apache License 2.0](LICENSE)
