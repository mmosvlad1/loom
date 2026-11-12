#!/usr/bin/env python3
"""SubagentStop hook: enforce checks for loom:implementer (LOOM_SPEC.md 11.4).

When the `loom:implementer` subagent tries to finish, run `checks.check` from
.claude/loom.json at the git top level:

- pass: exit 0, the subagent finishes; the attempt counter is reset.
- fail: exit 2 with the tail of the output on stderr. Claude Code keeps the
  subagent running and gives it stderr as its next instruction.
- fail for the `hooks.maxCheckAttempts`-th time (default 3) in a row: exit 0,
  so the subagent can stop, with a `systemMessage` for the user. `implement`
  runs `checks.check` itself afterwards and records the implementation phase
  as blocked, because it never commits on failing checks.

Attempt counter: one small JSON file per subagent run in
`<tempdir>/loom-subagent-checks/` (tempdir honors $TMPDIR), named by a hash of
`session_id` and `agent_id`. A temp file keeps the repository and the task
directory clean, works without a task directory, and is removed on pass and
when the cap is reached.

The counter is always read: it, not `stop_hook_active`, ends the loop
(Claude Code's own cap of 8 stop-hook continuations resets on every tool
call). A counter file older than STALE_SECONDS is left from an interrupted
run and counts as 0. `stop_hook_active` is only recorded in the file.

Matcher in hooks.json: `^loom:implementer$` (plugin agents report the
plugin-scoped `agent_type`). The script checks `agent_type` again, so it never
runs checks for another agent. A silent no-op outside a git repository and
without .claude/loom.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from typing import Any, Dict, Optional

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

AGENT_TYPES = {"loom:implementer"}
DEFAULT_MAX_ATTEMPTS = 3
# hooks.json gives this hook 600 seconds; the check gets less, so the hook can
# still report a timeout before Claude Code cancels it.
CHECK_TIMEOUT = 540
COUNTER_DIR_NAME = "loom-subagent-checks"
STALE_SECONDS = 3600


def counter_path(session_id: str, agent_id: str) -> str:
    key = hashlib.sha256(("%s\0%s" % (session_id, agent_id)).encode("utf-8")).hexdigest()[:24]
    return os.path.join(tempfile.gettempdir(), COUNTER_DIR_NAME, key + ".json")


def read_failures(path: str) -> int:
    """Failed attempts so far; 0 for a missing, unreadable, or stale file."""
    try:
        if time.time() - os.path.getmtime(path) > STALE_SECONDS:
            return 0
    except OSError:
        return 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            value = json.load(fh).get("failures", 0)
    except (OSError, ValueError, AttributeError):
        return 0
    return value if isinstance(value, int) and value >= 0 else 0


def write_failures(path: str, failures: int, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({
            "failures": failures,
            "session_id": data.get("session_id"),
            "agent_id": data.get("agent_id"),
            "agent_type": data.get("agent_type"),
            "stop_hook_active": bool(data.get("stop_hook_active")),
            "cwd": data.get("cwd"),
        }, fh)
    os.replace(tmp, path)


def remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def max_attempts(cfg: Dict[str, Any]) -> int:
    hooks = cfg.get("hooks") if isinstance(cfg.get("hooks"), dict) else {}
    value = hooks.get("maxCheckAttempts", DEFAULT_MAX_ATTEMPTS)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return DEFAULT_MAX_ATTEMPTS
    return value


def check_command(cfg: Dict[str, Any]) -> Optional[str]:
    checks = cfg.get("checks") if isinstance(cfg.get("checks"), dict) else {}
    command = checks.get("check")
    return command if isinstance(command, str) and command.strip() else None


def main() -> None:
    data = loomhook.read_input()
    if data.get("agent_type") not in AGENT_TYPES:
        return
    ls = loomhook.loom_state()
    top, cfg = ls.load_repo_config(loomhook.hook_cwd(data))
    if cfg is None:
        return
    command = check_command(cfg)
    if command is None:
        return  # loom-state always resolves checks.check to a command; a guard only
    limit = max_attempts(cfg)
    path = counter_path(str(data.get("session_id") or ""), str(data.get("agent_id") or ""))
    failures = read_failures(path)

    code, output = loomhook.run_check(command, top, CHECK_TIMEOUT)
    if code == 0:
        remove(path)
        return

    failures += 1
    what = "timed out after %d seconds" % CHECK_TIMEOUT if code is None else "failed (exit %d)" % code
    if failures >= limit:
        remove(path)
        loomhook.system_message(
            "loom: `%s` %s for the implementer %d times (hooks.maxCheckAttempts = %d). "
            "The implementer may stop now; /loom:implement records the implementation phase as blocked."
            % (command, what, failures, limit)
        )
        return
    write_failures(path, failures, data)
    sys.stderr.write(
        "loom: `%s` %s (attempt %d of %d). You cannot finish while the checks fail. "
        "Fix the cause inside the scope of your implementation phase, run the checks again, then finish. "
        "Do not weaken tests or checks.\n\n%s\n"
        % (command, what, failures, limit, loomhook.output_tail(output))
    )
    sys.exit(2)


if __name__ == "__main__":
    try:
        sys.path.insert(0, HERE)
        import loomhook  # noqa: E402
    except Exception as exc:  # a broken install must not break the session
        sys.stderr.write("loom subagent-checks hook: skipped, cannot load helpers: %s\n" % exc)
        sys.exit(0)
    loomhook.run_safely(main, "subagent-checks")
