#!/usr/bin/env python3
"""SubagentStart and SubagentStop hook: record loom subagent runs (LOOM_SPEC.md 11.6).

Appends one JSON line to `<task dir>/events.jsonl` per event:

- SubagentStart: a `start` line.
- SubagentStop: a `stop` line, with `duration_s` (since the latest `start` line
  of the same `session_id` and `agent_id`), `stop_hook_active`, and `result`. SubagentStop
  fires again when a stop hook keeps the subagent running (the implementer
  after failing checks), so one run can have several stop lines.

Both lines carry `session_id`, `agent_id`, `agent` (the agent name without `loom:`), `ts`
(UTC, ISO 8601), and the task `phase` (`task_phase()` in bin/loom-state);
implement-time lines also carry `implementation_phase`.

Matcher in hooks.json: `^loom:` (only loom's own agents). The script checks
the `loom:` prefix again. It never blocks or fails a subagent: it always
exits 0 and prints nothing to stdout. Outside a git repository, without
.claude/loom.json, on the main branch, or without an active task directory
it does nothing. bin/loom-state reads the file for `task.metrics`.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from typing import Any, Dict, Optional

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

AGENT_PREFIX = "loom:"
EVENTS = {"SubagentStart": "start", "SubagentStop": "stop"}
TS_FORMAT = "%Y-%m-%dT%H:%M:%S"

# `## Verdict: pass`, also `**Verdict:** changes-needed`; the template line `pass | changes-needed` does not match.
_VERDICT_RE = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\**[ \t]*Verdict[ \t]*:?[ \t]*\**[ \t]*:?[ \t]*"
    r"(pass|changes-needed)[ \t]*\**[ \t]*$",
    re.I | re.M,
)
# A command line of the implementer's `### Checks` section: `` `make check`: pass (42 passed) ``.
_CHECKS_RE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?\**`([^`\n]+)`\**[ \t]*:[ \t]*\**[ \t]*(pass|fail)\b", re.I | re.M)


def format_ts(moment: datetime.datetime) -> str:
    """UTC ISO 8601 with milliseconds and `Z`, e.g. 2026-11-11T12:34:56.789Z."""
    moment = moment.astimezone(datetime.timezone.utc)
    return moment.strftime(TS_FORMAT) + ".%03dZ" % (moment.microsecond // 1000)


def parse_ts(value: Any) -> Optional[datetime.datetime]:
    if not isinstance(value, str):
        return None
    for fmt in (TS_FORMAT + ".%fZ", TS_FORMAT + "Z"):
        try:
            return datetime.datetime.strptime(value, fmt).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


def parse_result(agent: str, message: Any, check_command: str = "make check") -> str:
    """The result of a run from its last message.

    - implementation-reviewer: the verdict line (`## Verdict: pass | changes-needed`):
      `pass`, `changes-needed`, or `unknown`.
    - implementer: the line of its `### Checks` section whose backticked command
      is `check_command` (`checks.check`), e.g. `` `make check`: pass (42 passed) ``:
      `pass`, `fail`, or `unknown`.
    - every other agent: `done`.
    """
    text = message if isinstance(message, str) else ""
    if agent == "implementation-reviewer":
        found = {m.group(1).lower() for m in _VERDICT_RE.finditer(text)}
        return found.pop() if len(found) == 1 else "unknown"
    if agent == "implementer":
        checks = re.split(r"^#{1,6}\s*Checks\s*$", text, maxsplit=1, flags=re.M)
        if len(checks) == 2:
            section = re.split(r"^#{1,6}\s", checks[1], maxsplit=1, flags=re.M)[0]
            for m in _CHECKS_RE.finditer(section):
                if m.group(1).strip() == check_command.strip():
                    return m.group(2).lower()
        return "unknown"
    return "done"


def start_time(ls: Any, path: str, session_id: Optional[str], agent_id: str) -> Optional[datetime.datetime]:
    """The time of the latest `start` line of this run in the events file.

    A run is (`session_id`, `agent_id`); a missing `session_id` is the value None.
    A resumed subagent gets a new `start` line, so the latest one opens the
    current segment.
    """
    found = None
    for event in ls.read_events(path):
        if event["event"] == "start" and event["agent_id"] == agent_id and ls.event_session(event) == session_id:
            found = event
    return parse_ts(found.get("ts")) if found else None


def append_line(path: str, record: Dict[str, Any]) -> None:
    """Append one JSON line with a single write (O_APPEND), so parallel hooks do not mix lines."""
    data = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell() > 0:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    data = "\n" + data  # a cut last line stays malformed on its own
    except OSError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)


def session_of(data: Dict[str, Any]) -> Optional[str]:
    value = data.get("session_id")
    return value if isinstance(value, str) and value else None


def build_record(
    data: Dict[str, Any], context: Dict[str, Any], now: datetime.datetime, started: Optional[datetime.datetime]
) -> Dict[str, Any]:
    event = EVENTS[data["hook_event_name"]]
    agent = data["agent_type"][len(AGENT_PREFIX):]
    record: Dict[str, Any] = {
        "event": event,
        "ts": format_ts(now),
        "session_id": session_of(data),
        "agent_id": data["agent_id"],
        "agent": agent,
        "phase": context.get("phase"),
    }
    if context.get("implementationPhase") is not None:
        record["implementation_phase"] = context["implementationPhase"]
    if event == "stop":
        record["result"] = parse_result(agent, data.get("last_assistant_message"), context.get("check") or "make check")
        record["stop_hook_active"] = bool(data.get("stop_hook_active"))
        record["duration_s"] = round((now - started).total_seconds(), 1) if started else None
    return record


def main() -> None:
    data = loomhook.read_input()
    agent_type = data.get("agent_type")
    agent_id = data.get("agent_id")
    if (
        data.get("hook_event_name") not in EVENTS
        or not isinstance(agent_type, str)
        or not agent_type.startswith(AGENT_PREFIX)
        or len(agent_type) == len(AGENT_PREFIX)
        or not isinstance(agent_id, str)
        or not agent_id
    ):
        return
    ls = loomhook.loom_state()
    context = ls.event_context(loomhook.hook_cwd(data))
    if context is None:
        return
    path = os.path.join(context["dir"], ls.EVENTS_FILE)
    now = datetime.datetime.now(datetime.timezone.utc)
    is_stop = EVENTS[data["hook_event_name"]] == "stop"
    started = start_time(ls, path, session_of(data), agent_id) if is_stop else None
    append_line(path, build_record(data, context, now, started))


if __name__ == "__main__":
    try:
        sys.path.insert(0, HERE)
        import loomhook  # noqa: E402
    except Exception as exc:  # a broken install must not break the session
        sys.stderr.write("loom subagent-events hook: skipped, cannot load helpers: %s\n" % exc)
        sys.exit(0)
    loomhook.run_safely(main, "subagent-events")
