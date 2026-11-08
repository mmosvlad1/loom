# loom

A Claude Code plugin for structured, agent-driven development: **Research → Plan → Implement**.

loom turns a GitHub issue into a merged pull request through explicit phases. Each phase runs in a fresh session and writes a markdown artifact; the next phase reads only those artifacts. You stay in control at the checkpoints that matter: design approval, plan approval, manual verification, push, and merge.

**Status:** early development. The core (state script and safety hooks) and the subagents exist; the skills are not implemented yet. See [LOOM_SPEC.md](LOOM_SPEC.md) for the full specification.

## Install

```
/plugin install loom --marketplace mmosvlad1/loom
```

Or in two steps:

```
/plugin marketplace add mmosvlad1/loom
/plugin install loom@loom
```

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
