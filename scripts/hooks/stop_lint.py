#!/usr/bin/env python3
"""Stop hook: quick lint before Claude ends its turn (LOOM_SPEC.md 11.5).

Off unless .claude/loom.json sets `hooks.stopLint` to true. When on, and the
working tree has changes outside `.loom/`, the work directory, and
`<docsDir>/`, it runs `checks.lint` at the git top level. On failure it exits
2 with the tail of the output on stderr, so Claude sees it and continues.

Loop guard: when `stop_hook_active` is true (Claude already continues because
a stop hook blocked it), the hook does nothing. Each stop sequence gets at
most one lint block.

A silent no-op outside a git repository and without .claude/loom.json.
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

# hooks.json gives this hook 300 seconds; lint gets less, so the hook can still
# report a timeout.
LINT_TIMEOUT = 270
LOOM_DIR = ".loom"


def main() -> None:
    data = loomhook.read_input()
    if data.get("stop_hook_active"):
        return
    ls = loomhook.loom_state()
    top, cfg = ls.load_repo_config(loomhook.hook_cwd(data))
    if cfg is None:
        return
    hooks = cfg.get("hooks") if isinstance(cfg.get("hooks"), dict) else {}
    if hooks.get("stopLint") is not True:
        return
    checks = cfg.get("checks") if isinstance(cfg.get("checks"), dict) else {}
    command = checks.get("lint")
    if not isinstance(command, str) or not command.strip():
        return
    tree, _ = ls.working_tree_status(top, cfg, extra_ignore=(LOOM_DIR, cfg["docsDir"]))
    if tree != "dirty":
        return  # no code changes (or git failed): nothing to lint
    code, output = loomhook.run_check(command, top, LINT_TIMEOUT)
    if code == 0:
        return
    what = "timed out after %d seconds" % LINT_TIMEOUT if code is None else "failed (exit %d)" % code
    sys.stderr.write(
        "loom: `%s` %s on your uncommitted changes. Fix the lint errors before you finish. "
        "If this change was left blocked on purpose (a blocked phase), report it instead of fixing it.\n\n%s\n"
        % (command, what, loomhook.output_tail(output))
    )
    sys.exit(2)


if __name__ == "__main__":
    try:
        sys.path.insert(0, HERE)
        import loomhook  # noqa: E402
    except Exception as exc:  # a broken install must not break the session
        sys.stderr.write("loom stop-lint hook: skipped, cannot load helpers: %s\n" % exc)
        sys.exit(0)
    loomhook.run_safely(main, "stop-lint")
