"""Tests for the subagent events hook, the task phase rule, and the process metrics (LOOM_SPEC.md 11.6)."""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import unittest

from loomtest import HOOKS_DIR, RepoTestCase, git, loom_state, run_hook, run_loom_state, write

ls = loom_state()
EVENTS = "subagent_events.py"


def hook_module():
    spec = importlib.util.spec_from_file_location("subagent_events_under_test", os.path.join(HOOKS_DIR, EVENTS))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ev = hook_module()

REVIEW_PASS = "## Verdict: pass\n### As planned\n- x\n### Deviations\nNone\n"
REVIEW_CHANGES = "## Verdict: changes-needed\n### As planned\nNone\n### Planned but missing\n- y. blocking\n"
IMPLEMENTER_REPORT = (
    "## Implementation phase 1: Add tiers\n\n### Files changed\n- `a.py` - modified - x\n\n"
    "### Checks\n`make check`: %s\nlint ✓ typecheck ✓ test ✓ (42 passed)\n\n"
    "### Deviations from the plan\nNone\n"
)


# ---------------------------------------------------------------------------
# Task phase rule (pure)
# ---------------------------------------------------------------------------


def impl(*statuses, blocked=None, in_progress=None):
    phases = [{"number": i + 1, "status": s, "commit": None} for i, s in enumerate(statuses)]
    return {"total": len(phases), "done": sum(1 for p in phases if p["status"] == "done"),
            "inProgress": in_progress, "blocked": blocked, "phases": phases}


def arts(**statuses):
    return [{"phase": phase.replace("_", "-"), "status": status} for phase, status in statuses.items()]


class TaskPhaseTest(unittest.TestCase):
    def test_full_mode_before_implementation(self):
        cases = [
            (arts(), "research-questions"),
            (arts(research_questions="draft"), "research-questions"),
            (arts(research_questions="in-review"), "research"),
            (arts(research_questions="approved"), "research"),
            (arts(research_questions="approved", research="draft"), "research"),  # claim check runs on the draft
            (arts(research_questions="approved", research="in-review"), "design"),
            (arts(research_questions="approved", research="approved", design="draft"), "design"),
            (arts(research_questions="approved", research="approved", design="in-review"), "design"),  # rounds
            (arts(research_questions="approved", research="approved", design="approved"), "plan"),
            (arts(research_questions="approved", research="approved", design="approved", plan="draft"), "plan"),
            (arts(research_questions="approved", research="approved", design="approved", plan="in-review"), "plan"),
        ]
        for artifacts, expected in cases:
            with self.subTest(artifacts=artifacts):
                self.assertEqual(ls.task_phase("full", artifacts, impl()), (expected, None))

    def test_quick_mode(self):
        self.assertEqual(ls.task_phase("quick", arts(), impl()), ("research", None))
        self.assertEqual(ls.task_phase("quick", arts(research="in-review"), impl()), ("plan", None))
        self.assertEqual(ls.task_phase("quick", arts(research="approved", plan="in-review"), impl("pending")),
                         ("plan", None))

    def test_plan_approved_before_the_first_phase(self):
        artifacts = arts(research="approved", plan="approved")
        self.assertEqual(ls.task_phase("quick", artifacts, impl("pending", "pending")), ("implement", 1))
        self.assertEqual(ls.task_phase("quick", artifacts, impl()), ("implement", 1))

    def test_implementation(self):
        artifacts = arts(research="approved", plan="approved")
        self.assertEqual(ls.task_phase("quick", artifacts, impl("done", "in-progress", "pending", in_progress=2)),
                         ("implement", 2))
        self.assertEqual(ls.task_phase("quick", artifacts, impl("done", "pending")), ("implement", 2))
        blocked = impl("done", "blocked", blocked={"phase": 2, "reason": "x"})
        self.assertEqual(ls.task_phase("quick", artifacts, blocked), ("implement", 2))

    def test_after_the_last_phase_is_iterate(self):
        artifacts = arts(research="approved", plan="approved")
        self.assertEqual(ls.task_phase("quick", artifacts, impl("done", "done")), ("iterate", None))
        self.assertEqual(ls.task_phase("oneshot", [], impl("done")), ("iterate", None))

    def test_plan_change_after_implementation_started(self):
        # decide_next row 4: /loom:iterate changes the plan (draft while it edits, then in review).
        for status in ("draft", "in-review"):
            artifacts = arts(research="approved", plan=status)
            with self.subTest(plan=status):
                self.assertEqual(ls.task_phase("quick", artifacts, impl("done", "done", "pending")), ("plan", None))
                self.assertEqual(ls.task_phase("full", artifacts, impl("done", "pending")), ("plan", None))
        # A blocked phase with a reopened plan: the plan change comes first (decide_next row 4).
        blocked = impl("done", "blocked", blocked={"phase": 2, "reason": "x"})
        self.assertEqual(ls.task_phase("quick", arts(research="approved", plan="in-review"), blocked), ("plan", None))
        self.assertEqual(ls.task_phase("quick", arts(research="approved", plan="approved"), blocked), ("implement", 2))
        self.assertEqual(ls.task_phase("oneshot", arts(plan="in-review"), impl("blocked", blocked={"phase": 1})),
                         ("implement", 1))
        # A design change after implementation started (full mode): the first gate that is not approved.
        full = arts(research_questions="approved", research="approved", design="in-review", plan="approved")
        self.assertEqual(ls.task_phase("full", full, impl("done", "pending")), ("design", None))
        full = arts(research_questions="approved", research="approved", design="approved", plan="draft")
        self.assertEqual(ls.task_phase("full", full, impl("done", "pending")), ("plan", None))
        # Approved again: the added phase 3 is implemented next.
        artifacts = arts(research="approved", plan="approved")
        self.assertEqual(ls.task_phase("quick", artifacts, impl("done", "done", "pending")), ("implement", 3))

    def test_oneshot(self):
        self.assertEqual(ls.task_phase("oneshot", [], impl("pending")), ("implement", 1))
        self.assertEqual(ls.task_phase("oneshot", [], impl("in-progress", in_progress=1)), ("implement", 1))

    def test_invalid_mode(self):
        self.assertEqual(ls.task_phase(None, [], impl()), (None, None))
        self.assertEqual(ls.task_phase("huge", arts(research="draft"), impl()), (None, None))


# ---------------------------------------------------------------------------
# Process metrics (pure)
# ---------------------------------------------------------------------------


def start(agent_id, agent, phase="research", **extra):
    return dict({"event": "start", "ts": "2026-11-11T10:00:00.000Z", "agent_id": agent_id, "agent": agent,
                 "phase": phase}, **extra)


def stop(agent_id, agent, phase="research", duration=60.0, result="done", active=False, **extra):
    return dict({"event": "stop", "ts": "2026-11-11T10:01:00.000Z", "agent_id": agent_id, "agent": agent,
                 "phase": phase, "result": result, "stop_hook_active": active, "duration_s": duration}, **extra)


class EventsMetricsTest(unittest.TestCase):
    def test_no_events(self):
        self.assertIsNone(ls.events_metrics([]))

    def test_full_example(self):
        events = [
            start("r1", "codebase-locator"), start("r2", "codebase-analyzer"),
            stop("r1", "codebase-locator", duration=30), stop("r2", "codebase-analyzer", duration=90),
            start("i1", "implementer", "implement", implementation_phase=1),
            stop("i1", "implementer", "implement", duration=200, result="fail"),
            stop("i1", "implementer", "implement", duration=300, result="pass", active=True),
            start("v1", "implementation-reviewer", "implement"),
            stop("v1", "implementation-reviewer", "implement", duration=60, result="changes-needed"),
            start("i2", "implementer", "implement"), stop("i2", "implementer", "implement", duration=120),
            start("v2", "implementation-reviewer", "implement"),
            stop("v2", "implementation-reviewer", "implement", duration=60, result="pass"),
        ]
        m = ls.events_metrics(events)
        self.assertEqual(m["runs"], 6)
        self.assertEqual(m["byPhase"], {"research": 2, "implement": 4})
        self.assertEqual(list(m["byPhase"]), ["research", "implement"])
        self.assertEqual((m["reviewRounds"], m["changesNeeded"], m["checkRetries"], m["unfinished"]), (2, 1, 1, 0))
        self.assertEqual(m["subagentSeconds"], 660.0)  # the last stop of i1 counts, not both
        self.assertEqual(
            m["line"],
            "6 subagent runs (research 2, implement 4), 2 review rounds (1 changes-needed), "
            "1 checks retry, subagent time 11 min",
        )

    def test_duration_text_rounds_first(self):
        for seconds, text in ((0.4, "0 s"), (59.4, "59 s"), (59.6, "1 min"), (89, "1 min"), (91, "2 min")):
            with self.subTest(seconds=seconds):
                m = ls.events_metrics([stop("a", "x", duration=seconds)])
                self.assertTrue(m["line"].endswith("subagent time " + text), m["line"])

    def test_short_line_and_singulars(self):
        m = ls.events_metrics([start("a", "codebase-locator"), stop("a", "codebase-locator", duration=12.4)])
        self.assertEqual(m["line"], "1 subagent run (research 1), subagent time 12 s")
        events = [start("v", "implementation-reviewer", "implement"),
                  stop("v", "implementation-reviewer", "implement", result="pass")]
        self.assertEqual(ls.events_metrics(events)["line"],
                         "1 subagent run (implement 1), 1 review round, subagent time 1 min")

    def test_retries_plural_and_unfinished(self):
        events = [start("i", "implementer", "implement"), stop("i", "implementer", "implement", duration=10),
                  stop("i", "implementer", "implement", duration=20, active=True),
                  stop("i", "implementer", "implement", duration=30, active=True),
                  start("x", "codebase-analyzer", "plan")]
        m = ls.events_metrics(events)
        self.assertEqual((m["checkRetries"], m["unfinished"], m["subagentSeconds"]), (2, 1, 30.0))
        self.assertEqual(m["line"], "2 subagent runs (plan 1, implement 1), 2 checks retries, 1 unfinished, subagent time 30 s")

    def test_phase_order_and_unknown(self):
        events = [start("a", "x", "iterate"), start("b", "x", None), start("c", "x", "research-questions"),
                  start("d", "x", "design"), start("e", "x", "other")]
        self.assertEqual(list(ls.events_metrics(events)["byPhase"]),
                         ["research-questions", "design", "iterate", "other", "unknown"])

    def test_resumed_reviewer_gives_two_review_rounds(self):
        events = [start("v", "implementation-reviewer", "implement"),
                  stop("v", "implementation-reviewer", "implement", duration=10, result="changes-needed"),
                  start("v", "implementation-reviewer", "implement"),
                  stop("v", "implementation-reviewer", "implement", duration=20, result="pass")]
        m = ls.events_metrics(events)
        self.assertEqual((m["runs"], m["checkRetries"], m["reviewRounds"], m["changesNeeded"], m["unfinished"]),
                         (1, 0, 2, 1, 0))
        self.assertEqual(m["subagentSeconds"], 30.0)  # the sum of the segments, without the idle time

    def test_retries_count_stop_hook_active_stops(self):
        events = [start("i", "implementer", "implement"),
                  stop("i", "implementer", "implement", duration=10, active=False),
                  stop("i", "implementer", "implement", duration=20, active=True),
                  stop("i", "implementer", "implement", duration=30, active=True)]
        m = ls.events_metrics(events)
        self.assertEqual((m["runs"], m["checkRetries"], m["subagentSeconds"]), (1, 2, 30.0))
        # A resumed run with a stop that is not a hook continuation is no retry.
        resumed = events + [start("i", "implementer", "implement"), stop("i", "implementer", "implement", duration=5)]
        m = ls.events_metrics(resumed)
        self.assertEqual((m["runs"], m["checkRetries"], m["subagentSeconds"]), (1, 2, 35.0))

    def test_unfinished_is_a_run_whose_last_line_is_a_start(self):
        events = [start("a", "x"), stop("a", "x", duration=10), start("a", "x")]
        m = ls.events_metrics(events)
        self.assertEqual((m["runs"], m["unfinished"], m["subagentSeconds"]), (1, 1, 10.0))

    def test_runs_are_grouped_by_session_and_agent_id(self):
        events = [start("a", "x", session_id="s1"), stop("a", "x", session_id="s1", duration=10),
                  start("a", "x", session_id="s2"), stop("a", "x", session_id="s2", duration=20),
                  start("b", "x"), stop("b", "x", duration=30)]  # older lines without session_id
        m = ls.events_metrics(events)
        self.assertEqual((m["runs"], m["checkRetries"], m["subagentSeconds"]), (3, 0, 60.0))

    def test_stop_without_start(self):
        m = ls.events_metrics([stop("a", "codebase-locator", "design", duration=None)])
        self.assertEqual((m["runs"], m["byPhase"], m["subagentSeconds"]), (1, {"design": 1}, 0.0))

    def test_start_phase_wins_over_stop_phase(self):
        m = ls.events_metrics([start("a", "implementer", "implement"), stop("a", "implementer", "iterate")])
        self.assertEqual(m["byPhase"], {"implement": 1})

    def test_invalid_durations_are_ignored(self):
        events = [stop("a", "x", duration="5"), stop("b", "x", duration=True), stop("c", "x", duration=-3),
                  stop("d", "x", duration=7)]
        self.assertEqual(ls.events_metrics(events)["subagentSeconds"], 7.0)


class ReadEventsTest(RepoTestCase):
    def test_malformed_lines_are_skipped(self):
        path = self.path("events.jsonl")
        good = [start("a", "codebase-locator"), stop("a", "codebase-locator")]
        lines = [json.dumps(good[0]), "not json", "", "[1, 2]", '{"event": "start"}',
                 '{"event": "begin", "agent_id": "z"}', '{"event": "stop", "agent_id": ""}',
                 '{"event": "stop", "agent_id": 5}', '{"event": "sto', json.dumps(good[1])]
        write(path, "\n".join(lines) + "\n")
        self.assertEqual(ls.read_events(path), good)
        self.assertEqual(ls.read_events(self.path("missing.jsonl")), [])


# ---------------------------------------------------------------------------
# Result parsing and timestamps (hook helpers)
# ---------------------------------------------------------------------------


class ParseResultTest(unittest.TestCase):
    def test_reviewer_verdict(self):
        self.assertEqual(ev.parse_result("implementation-reviewer", REVIEW_PASS), "pass")
        self.assertEqual(ev.parse_result("implementation-reviewer", REVIEW_CHANGES), "changes-needed")
        self.assertEqual(ev.parse_result("implementation-reviewer", "Intro.\n\n**Verdict:** Changes-needed\n"),
                         "changes-needed")
        for text in ("## Verdict: pass | changes-needed\n", "no verdict here", "", None,
                     "## Verdict: pass\n## Verdict: changes-needed\n", "## Verdict: passed\n"):
            with self.subTest(text=text):
                self.assertEqual(ev.parse_result("implementation-reviewer", text), "unknown")

    def test_implementer_checks_line(self):
        self.assertEqual(ev.parse_result("implementer", IMPLEMENTER_REPORT % "pass"), "pass")
        self.assertEqual(ev.parse_result("implementer", IMPLEMENTER_REPORT % "fail"), "fail")
        self.assertEqual(ev.parse_result("implementer", IMPLEMENTER_REPORT % "**pass**"), "pass")
        self.assertEqual(ev.parse_result("implementer", "### Checks\nlint: fail\n`make check`: pass\n"), "pass")
        self.assertEqual(ev.parse_result("implementer", "### Checks\n`make check`: pass (42 passed)\n"), "pass")
        self.assertEqual(ev.parse_result("implementer", "### Checks\n- `make check`: **fail** - 2 errors\n"), "fail")
        self.assertEqual(ev.parse_result("implementer", "### Checks\n`make lint`: pass\n"), "unknown")
        self.assertEqual(ev.parse_result("implementer", "### Checks\n`make ci`: fail\n", "make ci"), "fail")
        self.assertEqual(ev.parse_result("implementer", "### Checks\n`make check`: passing\n"), "unknown")
        no_line = IMPLEMENTER_REPORT.replace("`make check`: %s\n", "")
        self.assertEqual(ev.parse_result("implementer", no_line), "unknown")
        self.assertEqual(ev.parse_result("implementer", "I could not finish."), "unknown")
        # A pass outside the Checks section does not count.
        self.assertEqual(ev.parse_result("implementer", "### Files changed\n- x: pass\n"), "unknown")

    def test_reviewer_near_misses(self):
        for text, expected in (
            ("## Verdict: pass.\n", "pass"),
            ("## Verdict: Pass!\n", "pass"),
            ("## Verdict: pass (with nits)\n", "pass"),
            ("**Verdict:** pass (minor nits).\n", "pass"),
            ("## Verdict: Changes needed\n", "changes-needed"),
            ("Verdict: changes needed.\n", "changes-needed"),
            ("## Verdict: **changes-needed**\n", "changes-needed"),
            ("## Verdict\npass\n### As planned\n", "pass"),
            ("## Verdict\n\n**Changes needed**\n", "changes-needed"),
            ("**Verdict:**\nchanges-needed\n", "changes-needed"),
            ("## Verdict: pass, but see below\n", "unknown"),
            ("## Verdict\nI think it passes\n", "unknown"),
            ("## Verdict: pass\n\n## Verdict\nChanges needed\n", "unknown"),
        ):
            with self.subTest(text=text):
                self.assertEqual(ev.parse_result("implementation-reviewer", text), expected)

    def test_implementer_near_misses(self):
        for text, expected in (
            ("### Checks\n`make check`: passed (42 tests)\n", "pass"),
            ("### Checks\n`make check`: failed\n", "fail"),
            ("### Checks\n- `make check` - pass\n", "pass"),
            ("### Checks\n`make check` \u2014 fail\n", "fail"),
            ("### Checks:\n`make check`: pass\n", "pass"),
            ("**Checks**\n`make check`: pass\n\n**Deviations**\nNone\n", "pass"),
            ("**Checks:**\n- `make check`: **failed**\n", "fail"),
            ("**Checks**\n\n**Deviations**\n`make check`: pass\n", "unknown"),
            ("### Checks\n`make check`: passing\n", "unknown"),
            ("### Checks\n`make check` pass\n", "unknown"),
        ):
            with self.subTest(text=text):
                self.assertEqual(ev.parse_result("implementer", text), expected)

    def test_other_agents_are_done(self):
        for agent in ("codebase-locator", "codebase-analyzer", "codebase-pattern-finder", "web-search-researcher"):
            with self.subTest(agent=agent):
                self.assertEqual(ev.parse_result(agent, REVIEW_CHANGES), "done")

    def test_timestamps(self):
        moment = datetime.datetime(2026, 11, 11, 12, 34, 56, 789123, tzinfo=datetime.timezone.utc)
        self.assertEqual(ev.format_ts(moment), "2026-11-11T12:34:56.789Z")
        self.assertEqual(ev.parse_ts("2026-11-11T12:34:56.789Z"), moment.replace(microsecond=789000))
        self.assertEqual(ev.parse_ts("2026-11-11T12:34:56Z"), moment.replace(microsecond=0))
        for bad in (None, 5, "", "yesterday", "2026-11-11 12:34:56"):
            self.assertIsNone(ev.parse_ts(bad))


# ---------------------------------------------------------------------------
# The hook script on a fixture repository
# ---------------------------------------------------------------------------


class SubagentEventsHookTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")
        self.dir = self.task_dir("42-auth-flow")
        self.ticket(self.dir, mode="quick")
        self.events_path = os.path.join(self.dir, "events.jsonl")

    def payload(self, event, agent_id="agent-1", agent_type="loom:codebase-locator", **extra):
        data = {"session_id": "s", "transcript_path": "/tmp/t.jsonl", "cwd": self.repo,
                "permission_mode": "default", "hook_event_name": event,
                "agent_id": agent_id, "agent_type": agent_type}
        if event == "SubagentStop":
            data.update({"stop_hook_active": False, "agent_transcript_path": "/tmp/a.jsonl",
                         "last_assistant_message": "done"})
        data.update(extra)
        return data

    def fire(self, event, **kwargs):
        proc = run_hook(EVENTS, self.payload(event, **kwargs))
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))
        return proc

    def lines(self):
        with open(self.events_path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh.read().splitlines()]

    def test_start_and_stop_lines(self):
        self.fire("SubagentStart")
        self.fire("SubagentStop")
        first, second = self.lines()
        self.assertEqual(list(first), ["event", "ts", "session_id", "agent_id", "agent", "phase"])
        self.assertEqual((first["event"], first["session_id"], first["agent_id"], first["agent"], first["phase"]),
                         ("start", "s", "agent-1", "codebase-locator", "research"))
        self.assertIsNotNone(ev.parse_ts(first["ts"]))
        self.assertEqual(list(second), ["event", "ts", "session_id", "agent_id", "agent", "phase", "result",
                                        "stop_hook_active", "duration_s"])
        self.assertEqual((second["event"], second["result"], second["stop_hook_active"]), ("stop", "done", False))
        self.assertIsInstance(second["duration_s"], float)
        self.assertGreaterEqual(second["duration_s"], 0)
        with open(self.events_path, encoding="utf-8") as fh:
            self.assertRegex(fh.read(), r'^\{"event":"start","ts":"[^"]+","session_id":"s","agent_id":"agent-1",'
                                        r'"agent":"codebase-locator","phase":"research"\}\n')

    def test_duration_pairs_by_agent_id(self):
        write(self.events_path, "\n".join(json.dumps(e) for e in [
            {"event": "start", "ts": "2000-01-01T00:00:00Z", "session_id": "s", "agent_id": "agent-1"},
            {"event": "start", "ts": "2026-11-11T10:00:00.000Z", "session_id": "s", "agent_id": "other"},
        ]) + "\n")
        self.fire("SubagentStop")
        stop_line = self.lines()[-1]
        self.assertGreater(stop_line["duration_s"], 26 * 365 * 24 * 3600)  # paired with agent-1's start, not other's

    def test_duration_pairs_by_session_and_agent_id(self):
        write(self.events_path, "\n".join(json.dumps(e) for e in [
            {"event": "start", "ts": "2000-01-01T00:00:00Z", "session_id": "old", "agent_id": "agent-1"},
            {"event": "start", "ts": "2026-11-11T10:00:00.000Z", "session_id": "s", "agent_id": "agent-1"},
        ]) + "\n")
        self.fire("SubagentStop")
        self.assertLess(self.lines()[-1]["duration_s"], 26 * 365 * 24 * 3600)  # not the other session's start

    def test_line_without_session_is_another_run(self):
        write(self.events_path, json.dumps(
            {"event": "start", "ts": "2000-01-01T00:00:00Z", "agent_id": "agent-1"}) + "\n")
        self.fire("SubagentStop")
        self.assertIsNone(self.lines()[-1]["duration_s"])  # a null session_id is an ordinary value

    def test_resumed_run_pairs_with_the_latest_start(self):
        write(self.events_path, "\n".join(json.dumps(e) for e in [
            {"event": "start", "ts": "2000-01-01T00:00:00Z", "session_id": "s", "agent_id": "agent-1"},
            {"event": "stop", "ts": "2000-01-01T00:01:00Z", "session_id": "s", "agent_id": "agent-1"},
        ]) + "\n")
        self.fire("SubagentStart")  # Claude Code resumes the subagent
        self.fire("SubagentStop")
        self.assertLess(self.lines()[-1]["duration_s"], 3600)

    def test_missing_session_id_is_null(self):
        payload = self.payload("SubagentStart")
        del payload["session_id"]
        run_hook(EVENTS, payload)
        self.assertIsNone(self.lines()[0]["session_id"])

    def test_implementer_result_uses_the_configured_check(self):
        self.write_config({"checks": {"check": "make ci"}})
        report = "### Checks\n`make check`: fail\n`make ci`: pass (12 passed)\n"
        self.fire("SubagentStop", agent_type="loom:implementer", last_assistant_message=report)
        self.assertEqual(self.lines()[0]["result"], "pass")

    def test_missing_start_gives_null_duration(self):
        self.fire("SubagentStop")
        self.assertIsNone(self.lines()[0]["duration_s"])

    def test_repeated_stops_are_all_recorded(self):
        self.artifact(self.dir, "02-research.md", "research", "approved")
        self.artifact(self.dir, "04-plan.md", "plan", "approved", body="## Phase Overview\n- [ ] 1. A\n- [ ] 2. B\n")
        write(os.path.join(self.dir, "log.md"), "## Phase 1 — in-progress\n")
        impl_type = "loom:implementer"
        self.fire("SubagentStart", agent_id="imp", agent_type=impl_type)
        self.fire("SubagentStop", agent_id="imp", agent_type=impl_type,
                  last_assistant_message=IMPLEMENTER_REPORT % "fail")
        self.fire("SubagentStop", agent_id="imp", agent_type=impl_type, stop_hook_active=True,
                  last_assistant_message=IMPLEMENTER_REPORT % "pass")
        self.fire("SubagentStart", agent_id="rev", agent_type="loom:implementation-reviewer")
        self.fire("SubagentStop", agent_id="rev", agent_type="loom:implementation-reviewer",
                  last_assistant_message=REVIEW_CHANGES)
        lines = self.lines()
        self.assertEqual([(l["event"], l["agent"]) for l in lines], [
            ("start", "implementer"), ("stop", "implementer"), ("stop", "implementer"),
            ("start", "implementation-reviewer"), ("stop", "implementation-reviewer")])
        self.assertTrue(all(l["phase"] == "implement" and l["implementation_phase"] == 1 for l in lines))
        self.assertEqual([l.get("result") for l in lines], [None, "fail", "pass", None, "changes-needed"])
        self.assertEqual([l.get("stop_hook_active") for l in lines], [None, False, True, None, False])
        metrics = self.state()["task"]["metrics"]
        self.assertEqual((metrics["runs"], metrics["reviewRounds"], metrics["changesNeeded"], metrics["checkRetries"]),
                         (2, 1, 1, 1))
        self.assertTrue(metrics["line"].startswith("2 subagent runs (implement 2), 1 review round (1 changes-needed), "
                                                   "1 checks retry, subagent time "))

    def test_cut_last_line_does_not_swallow_the_new_line(self):
        write(self.events_path, '{"event":"start","agent_id":"x"')
        self.fire("SubagentStart")
        with open(self.events_path, encoding="utf-8") as fh:
            raw = fh.read().splitlines()
        self.assertEqual(len(raw), 2)
        self.assertEqual(json.loads(raw[1])["agent_id"], "agent-1")

    def test_subdirectory_cwd(self):
        os.makedirs(self.path("src", "pkg"))
        run_hook(EVENTS, dict(self.payload("SubagentStart"), cwd=self.path("src", "pkg")))
        self.assertEqual(len(self.lines()), 1)

    def test_other_agents_and_events_are_ignored(self):
        for agent_type in ("codebase-locator", "Explore", "other:implementer", "loom:", "", None, 5):
            with self.subTest(agent_type=agent_type):
                self.fire("SubagentStart", agent_type=agent_type)
        for event in ("Stop", "PreToolUse", None):
            with self.subTest(event=event):
                self.fire(event)
        for agent_id in ("", None, 7):
            with self.subTest(agent_id=agent_id):
                self.fire("SubagentStart", agent_id=agent_id)
        self.assertFalse(os.path.exists(self.events_path))

    def test_no_task_is_a_no_op(self):
        git(self.repo, "switch", "-q", "main")
        self.fire("SubagentStart")  # on the main branch
        git(self.repo, "switch", "-q", "-c", "feat/43-other")
        self.fire("SubagentStart")  # no task directory for #43
        git(self.repo, "switch", "-q", "-c", "spike")
        self.fire("SubagentStart")  # not a task branch
        self.assertFalse(os.path.exists(self.events_path))
        self.assertEqual(os.listdir(self.path(".loom", "tasks")), ["42-auth-flow"])

    def test_archived_task_is_a_no_op(self):
        archive = self.path(".loom", "tasks", "_archive")
        os.makedirs(archive)
        os.rename(self.dir, os.path.join(archive, "42-auth-flow"))
        self.fire("SubagentStart")
        self.assertEqual(os.listdir(os.path.join(archive, "42-auth-flow")), ["00-ticket.md"])

    def test_no_config_and_outside_git_are_no_ops(self):
        os.remove(self.path(".claude", "loom.json"))
        self.fire("SubagentStart")
        outside = os.path.join(self.tmp, "plain")
        os.makedirs(outside)
        self.fire("SubagentStart", cwd=outside)
        self.assertFalse(os.path.exists(self.events_path))

    def test_bad_input_never_fails(self):
        for raw in ("", "not json", "[]", "5", '{"hook_event_name": "SubagentStop", "agent_type": "loom:x"}'):
            with self.subTest(raw=raw):
                proc = run_hook(EVENTS, None, raw=raw, cwd=self.repo)
                self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_unwritable_task_directory_exits_zero(self):
        os.makedirs(self.events_path)  # a directory where the file should be: the write fails
        proc = run_hook(EVENTS, self.payload("SubagentStart"))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))
        self.assertIn("subagent-events", proc.stderr)


class HooksJsonTest(unittest.TestCase):
    def entries(self):
        from test_stop_hooks import hooks_config
        config = hooks_config()
        command = 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/subagent_events.py"'
        found = {}
        for event in ("SubagentStart", "SubagentStop"):
            matching = [e for e in config[event] if any(h["command"] == command for h in e["hooks"])]
            self.assertEqual(len(matching), 1, event)
            found[event] = matching[0]
        return found

    def test_registered_for_start_and_stop(self):
        for event, entry in self.entries().items():
            with self.subTest(event=event):
                self.assertEqual(entry["matcher"], "^loom:")
                (hook,) = entry["hooks"]
                self.assertEqual(hook["type"], "command")
                self.assertLessEqual(hook["timeout"], 10)

    def test_matcher_selects_only_loom_agents(self):
        from test_stop_hooks import js_matcher_matches
        for event, entry in self.entries().items():
            for agent_type in ("loom:codebase-locator", "loom:implementer", "loom:implementation-reviewer"):
                with self.subTest(event=event, agent_type=agent_type):
                    self.assertTrue(js_matcher_matches(entry["matcher"], agent_type))
            for agent_type in ("codebase-locator", "Explore", "general-purpose", "other:loom:x", "xloom:a"):
                with self.subTest(event=event, agent_type=agent_type):
                    self.assertFalse(js_matcher_matches(entry["matcher"], agent_type))

    def test_checks_hook_is_unchanged(self):
        from test_stop_hooks import hooks_config
        checks = [e for e in hooks_config()["SubagentStop"] if e["matcher"] == "^loom:implementer$"]
        self.assertEqual(len(checks), 1)
        self.assertIn("subagent_checks.py", checks[0]["hooks"][0]["command"])


class TaskMetricsStateTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")
        self.dir = self.task_dir("42-auth-flow")
        self.ticket(self.dir, mode="full")

    def test_metrics_null_without_events(self):
        self.assertIsNone(self.state()["task"]["metrics"])
        write(os.path.join(self.dir, "events.jsonl"), "garbage\n")
        self.assertIsNone(self.state()["task"]["metrics"])

    def test_metrics_in_json_output(self):
        write(os.path.join(self.dir, "events.jsonl"),
              json.dumps(start("a", "codebase-locator")) + "\n" + json.dumps(stop("a", "codebase-locator")) + "\n")
        proc = run_loom_state(self.repo, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        metrics = json.loads(proc.stdout)["task"]["metrics"]
        self.assertEqual(metrics["line"], "1 subagent run (research 1), subagent time 1 min")
        self.assertEqual(list(metrics), ["runs", "byPhase", "reviewRounds", "changesNeeded", "checkRetries",
                                         "unfinished", "subagentSeconds", "line"])
        # The statusline does not change.
        self.assertEqual(run_loom_state(self.repo, "--line").stdout.strip(), "#42 · full · ticket")

    def test_event_context(self):
        ctx = ls.event_context(self.repo)
        self.assertEqual(ctx, {"dir": self.dir, "phase": "research-questions", "implementationPhase": None,
                               "check": "make check"})
        self.write_config({"checks": {"check": ""}})
        self.assertEqual(ls.event_context(self.repo)["check"], "make check")
        git(self.repo, "switch", "-q", "main")
        self.assertIsNone(ls.event_context(self.repo))


if __name__ == "__main__":
    unittest.main()
