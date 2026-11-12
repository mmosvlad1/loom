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
run and counts as 0. `stop_hook_active` is recorded in the file.

When the counter cannot be read or written (permissions, a full disk), the
check still blocks while `stop_hook_active` is false, and lets the subagent
stop with a `systemMessage` while it is true: the loop ends after one retry.

A `.claude/loom.json` that exists but cannot be read as a JSON object does
not block: the hook exits 0 with a `systemMessage` that names the problem.
With a readable config, loom-state's config warnings are appended to the
failure text the subagent receives.

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
from typing import Any, Dict, List, Optional

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


def read_failures(path: str) -> Optional[int]:
    """Failed attempts so far: 0 for a missing or stale file, None when the file cannot be read."""
    try:
        if time.time() - os.path.getmtime(path) > STALE_SECONDS:
            return 0
        with open(path, "rb") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return 0
    except OSError:
        return None
    try:
        value = json.loads(raw.decode("utf-8")).get("failures", 0)
    except (ValueError, AttributeError):
        return 0  # a damaged file (also not UTF-8): start again
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


def config_problem(ls: Any, warnings: List[str]) -> Optional[str]:
    """The warning about a loom.json that cannot be read as a JSON object, if any."""
    prefixes = ("cannot read %s" % ls.CONFIG_PATH, "%s is not a JSON object" % ls.CONFIG_PATH)
    for warning in warnings:
        if warning.startswith(prefixes):
            return warning[:-len("; using defaults")] if warning.endswith("; using defaults") else warning
    return None


def main() -> None:
    data = loomhook.read_input()
    if data.get("agent_type") not in AGENT_TYPES:
        return
    ls = loomhook.loom_state()
    top = ls.find_toplevel(loomhook.hook_cwd(data))
    if not top:
        return
    cfg, warnings = ls.load_config(top)
    if cfg is None:
        return
    problem = config_problem(ls, warnings)
    if problem:
        loomhook.system_message(
            "loom: the implementer checks did not run: %s. Fix %s; /loom:implement still runs the checks "
            "itself before it commits." % (problem, ls.CONFIG_PATH)
        )
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

    what = "timed out after %d seconds" % CHECK_TIMEOUT if code is None else "failed (exit %d)" % code
    counter_error = None if failures is not None else "cannot read %s" % path
    if failures is not None:
        failures += 1
        if failures >= limit:
            remove(path)
            loomhook.system_message(
                "loom: `%s` %s for the implementer %d times (hooks.maxCheckAttempts = %d). "
                "The implementer may stop now; /loom:implement records the implementation phase as blocked."
                % (command, what, failures, limit)
            )
            return
        try:
            write_failures(path, failures, data)
        except OSError as exc:
            counter_error = "cannot write %s: %s" % (path, exc)
    if counter_error and data.get("stop_hook_active"):
        # Without a counter, one retry is the limit: the loop must end.
        loomhook.system_message(
            "loom: `%s` %s for the implementer again, and the attempt counter is not available (%s). "
            "The implementer may stop now; /loom:implement records the implementation phase as blocked."
            % (command, what, counter_error)
        )
        return
    attempt = "attempt %d of %d" % (failures, limit) if not counter_error else (
        "attempt counter not available: %s; you get one retry" % counter_error)
    notes = ""
    if warnings:
        notes = "\n\nWarnings about %s (loom-state):\n%s" % (
            ls.CONFIG_PATH, "\n".join("- %s" % w for w in warnings))
    sys.stderr.write(
        "loom: `%s` %s (%s). You cannot finish while the checks fail. "
        "Fix the cause inside the scope of your implementation phase, run the checks again, then finish. "
        "Do not weaken tests or checks.%s\n\n%s\n"
        % (command, what, attempt, notes, loomhook.output_tail(output))
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
