#!/usr/bin/env python3
"""Stop hook: quick lint before Claude ends its turn (LOOM_SPEC.md 11.5).

Off unless .claude/loom.json sets `hooks.stopLint` to true, and a no-op when
`checks.lint` is null (the project has no lint). When on, and the working tree
has changes outside `.loom/`, the work directory, and the docs paths (docsDir
and every path of the docs map), it runs `checks.lint` at the git top level.
On failure it exits 2 with the tail of the output on stderr, so Claude sees it
and continues.

Loop guard: when `stop_hook_active` is true (Claude already continues because
a stop hook blocked it), the hook does nothing. Each stop sequence gets at
most one lint block.

The hook also does nothing in plan mode (`permission_mode` is "plan": no code
is written) and while background work is in flight (`background_tasks` has an
entry that is not finished, for example a background implementer still
writing code). The Claude Code hooks docs (Stop input) describe
`background_tasks` as the list of in-flight tasks, empty when nothing is in
flight; an entry with a finished status is ignored to be safe.
The hook cannot tell who changed the working tree: changes the user made by
hand are linted too.

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
# Task statuses that mean the task no longer runs (the docs do not list the
# statuses; in-flight tasks are the norm in `background_tasks`).
FINISHED_STATUSES = {"completed", "done", "failed", "killed", "stopped", "cancelled", "canceled", "error"}


def background_work(data: dict) -> bool:
    """True when the Stop input lists background work that is still in flight."""
    tasks = data.get("background_tasks")
    if not isinstance(tasks, list):
        return False
    for task in tasks:
        status = task.get("status") if isinstance(task, dict) else None
        if not (isinstance(status, str) and status.lower() in FINISHED_STATUSES):
            return True
    return False


def main() -> None:
    data = loomhook.read_input()
    if data.get("stop_hook_active"):
        return
    if data.get("permission_mode") == "plan" or background_work(data):
        return  # plan mode writes no code; background work is still changing the tree
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
    ignore = (LOOM_DIR,) + tuple(ls.docs_change_paths(cfg))
    tree, _ = ls.working_tree_status(top, cfg, extra_ignore=ignore)
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
