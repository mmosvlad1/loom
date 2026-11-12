#!/usr/bin/env python3
"""SessionStart hook: inject the loom task context (LOOM_SPEC.md 11.1).

Runs the loom-state logic without --pr (no network at session start) and
prints a short plain-text block; Claude Code adds stdout to the context.
On the main branch or a branch without a task it prints one hint line, plus
one line per loom-state warning (an invalid loom.json, for example).
A silent no-op outside a git repository and without .claude/loom.json.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def _artifact_text(art: Dict[str, Any]) -> str:
    text = "%s %s" % (art.get("file"), art.get("status") or "(no status)")
    extras = []
    if art.get("openQuestions"):
        extras.append("%d open questions" % art["openQuestions"])
    if art.get("acceptedByDefault"):
        extras.append("%d accepted by default" % art["acceptedByDefault"])
    if art.get("stale"):
        extras.append("stale")
    if extras:
        text += " (%s)" % ", ".join(extras)
    return text


def _warning_lines(state: Dict[str, Any]) -> List[str]:
    """One short line per loom-state warning."""
    return ["Warning: %s" % " ".join(str(w).split()) for w in state.get("warnings") or []]


def format_context(state: Dict[str, Any]) -> str:
    nxt = state.get("next") or {}
    task = state.get("task")
    if not task or task.get("archived") or state.get("onMain"):
        lines = ["[loom] %s. Next: %s" % (nxt.get("reason", "no active task"), nxt.get("command", ""))]
        lines.extend(_warning_lines(state))
        return "\n".join(lines)

    lines: List[str] = []
    lines.append("[loom] Task #%s (%s mode) in %s" % (task.get("number"), task.get("mode") or "unknown", task.get("dir")))
    lines.append("Branch: %s; working tree %s" % (state.get("branch"), state.get("workingTree") or "unknown"))
    artifacts = state.get("artifacts") or []
    if artifacts:
        lines.append("Artifacts: " + "; ".join(_artifact_text(a) for a in artifacts))
    else:
        lines.append("Artifacts: none yet besides 00-ticket.md")
    impl = state.get("implementation") or {}
    if impl.get("total"):
        text = "Implementation: %d of %d phases done" % (impl.get("done") or 0, impl["total"])
        if impl.get("inProgress"):
            text += "; phase %s in progress" % impl["inProgress"]
        blocked = impl.get("blocked")
        if blocked:
            text += "; phase %s blocked: %s" % (blocked.get("phase"), blocked.get("reason") or "no reason recorded")
        lines.append(text)
    if task.get("pr"):
        lines.append("PR: #%s" % task["pr"])
    lines.append("Next: %s (%s)" % (nxt.get("command"), nxt.get("reason")))
    lines.extend(_warning_lines(state))
    lines.append("Task state comes from loom-state; do not rely on memory of earlier sessions.")
    return "\n".join(lines)


def main() -> None:
    data = loomhook.read_input()
    cwd = loomhook.hook_cwd(data)
    state = loomhook.loom_state().compute_state(cwd, with_pr=False)
    if state is None:
        return
    sys.stdout.write(format_context(state) + "\n")


if __name__ == "__main__":
    try:
        sys.path.insert(0, HERE)
        import loomhook  # noqa: E402
    except Exception as exc:  # a broken install must not break the session
        sys.stderr.write("loom session-start hook: skipped, cannot load helpers: %s\n" % exc)
        sys.exit(0)
    loomhook.run_safely(main, "session-start")
