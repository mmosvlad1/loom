"""Tests for the SubagentStop (checks) and Stop (lint) hooks and their hooks.json entries."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest

from loomtest import ROOT, RepoTestCase, git, run_hook, stop_payload, write

CHECKS = "subagent_checks.py"
LINT = "stop_lint.py"
HOOKS_JSON = os.path.join(ROOT, "hooks", "hooks.json")


def hooks_config():
    with open(HOOKS_JSON, encoding="utf-8") as fh:
        return json.load(fh)["hooks"]


def js_matcher_matches(matcher: str, value: str) -> bool:
    """Claude Code matcher rules: exact names (letters, digits, _, -, |, spaces, commas), else an unanchored regex."""
    if matcher in ("", "*"):
        return True
    if re.fullmatch(r"[A-Za-z0-9_|, -]+", matcher):
        return value in [part.strip() for part in re.split(r"[|,]", matcher)]
    return re.search(matcher, value) is not None


class HooksJsonTest(unittest.TestCase):
    def test_subagent_stop_entry(self):
        entries = hooks_config()["SubagentStop"]
        self.assertEqual(len(entries), 2)  # the checks, and the subagent events (tests/test_subagent_events.py)
        entry = entries[0]
        self.assertEqual(entry["matcher"], "^loom:implementer$")
        hook = entry["hooks"][0]
        self.assertIn("scripts/hooks/subagent_checks.py", hook["command"])
        self.assertGreaterEqual(hook["timeout"], 600)

    def test_matcher_selects_only_the_plugin_implementer(self):
        matcher = hooks_config()["SubagentStop"][0]["matcher"]
        self.assertTrue(js_matcher_matches(matcher, "loom:implementer"))
        for other in ("implementer", "loom:implementation-reviewer", "other:implementer", "loom:implementer-x", ""):
            with self.subTest(agent_type=other):
                self.assertFalse(js_matcher_matches(matcher, other))

    def test_stop_entry(self):
        entry = hooks_config()["Stop"][0]
        self.assertNotIn("matcher", entry)  # Stop has no matcher
        hook = entry["hooks"][0]
        self.assertIn("scripts/hooks/stop_lint.py", hook["command"])
        self.assertGreaterEqual(hook["timeout"], 120)

    def test_script_timeouts_fit_the_hook_timeouts(self):
        import importlib.util
        for script, event in ((CHECKS, "SubagentStop"), (LINT, "Stop")):
            spec = importlib.util.spec_from_file_location("m_" + event, os.path.join(ROOT, "scripts", "hooks", script))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            limit = module.CHECK_TIMEOUT if script == CHECKS else module.LINT_TIMEOUT
            with self.subTest(script=script):
                self.assertLess(limit, hooks_config()[event][0]["hooks"][0]["timeout"])

    def test_commands_quote_the_plugin_root(self):
        for event in ("SubagentStop", "Stop"):
            command = hooks_config()[event][0]["hooks"][0]["command"]
            with self.subTest(event=event):
                self.assertTrue(command.startswith('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/'))


class SubagentChecksTest(RepoTestCase):
    loom_config = {"checks": {"check": "test -f pass.flag"}, "hooks": {"maxCheckAttempts": 3}}

    def setUp(self):
        super().setUp()
        self.tmpdir = os.path.join(self.tmp, "hooktmp")
        os.makedirs(self.tmpdir)
        self.env = {"TMPDIR": self.tmpdir}

    def run_checks(self, agent_type="loom:implementer", stop_hook_active=False, agent_id="agent-1", cwd=None):
        payload = stop_payload(
            cwd or self.repo, event="SubagentStop", stop_hook_active=stop_hook_active,
            agent_id=agent_id, agent_type=agent_type,
            agent_transcript_path="/tmp/subagents/agent-1.jsonl",
        )
        return run_hook(CHECKS, payload, env=self.env)

    def counter_files(self):
        path = os.path.join(self.tmpdir, "loom-subagent-checks")
        return sorted(os.listdir(path)) if os.path.isdir(path) else []

    def set_pass(self, passing: bool):
        flag = self.path("pass.flag")
        if passing:
            write(flag, "ok\n")
        elif os.path.exists(flag):
            os.remove(flag)

    def test_pass_lets_the_agent_stop(self):
        self.set_pass(True)
        proc = self.run_checks()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(self.counter_files(), [])

    def test_fail_blocks_with_the_output_tail(self):
        self.write_config({"checks": {"check": "echo first-line; echo 'FAILED tests/test_x.py::test_y'; exit 1"}})
        proc = self.run_checks()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("attempt 1 of 3", proc.stderr)
        self.assertIn("FAILED tests/test_x.py::test_y", proc.stderr)
        self.assertIn("You cannot finish while the checks fail", proc.stderr)
        self.assertEqual(len(self.counter_files()), 1)

    def test_attempt_cap_lets_the_agent_stop(self):
        self.set_pass(False)
        self.assertEqual(self.run_checks().returncode, 2)
        second = self.run_checks(stop_hook_active=True)
        self.assertEqual(second.returncode, 2)
        self.assertIn("attempt 2 of 3", second.stderr)
        third = self.run_checks(stop_hook_active=True)
        self.assertEqual(third.returncode, 0, third.stderr)
        message = json.loads(third.stdout)["systemMessage"]
        self.assertIn("3 times", message)
        self.assertIn("blocked", message)
        self.assertEqual(self.counter_files(), [], "the counter is removed at the cap")

    def test_configured_cap(self):
        self.write_config({"checks": {"check": "false"}, "hooks": {"maxCheckAttempts": 1}})
        proc = self.run_checks()
        self.assertEqual(proc.returncode, 0)
        self.assertIn("systemMessage", proc.stdout)

    def test_invalid_cap_uses_the_default(self):
        self.write_config({"checks": {"check": "false"}, "hooks": {"maxCheckAttempts": "two"}})
        self.assertIn("attempt 1 of 3", self.run_checks().stderr)

    def test_success_resets_the_counter(self):
        self.set_pass(False)
        self.assertEqual(self.run_checks().returncode, 2)
        self.assertEqual(self.run_checks(stop_hook_active=True).returncode, 2)
        self.set_pass(True)
        self.assertEqual(self.run_checks(stop_hook_active=True).returncode, 0)
        self.assertEqual(self.counter_files(), [])
        self.set_pass(False)
        self.assertIn("attempt 1 of 3", self.run_checks(stop_hook_active=True).stderr)

    def test_counter_is_read_also_without_stop_hook_active(self):
        self.set_pass(False)
        self.run_checks()
        self.assertIn("attempt 2 of 3", self.run_checks(stop_hook_active=False).stderr)
        self.assertEqual(self.run_checks(stop_hook_active=False).returncode, 0, "the cap holds without the flag")

    def test_stale_counter_counts_as_zero(self):
        self.set_pass(False)
        self.run_checks()
        self.run_checks(stop_hook_active=True)
        (name,) = self.counter_files()
        path = os.path.join(self.tmpdir, "loom-subagent-checks", name)
        old = os.path.getmtime(path) - 2 * 3600
        os.utime(path, (old, old))
        self.assertIn("attempt 1 of 3", self.run_checks(stop_hook_active=True).stderr)

    def test_counter_file_content(self):
        self.set_pass(False)
        self.run_checks(stop_hook_active=True)
        (name,) = self.counter_files()
        with open(os.path.join(self.tmpdir, "loom-subagent-checks", name)) as fh:
            data = json.load(fh)
        self.assertEqual((data["failures"], data["agent_id"], data["stop_hook_active"]), (1, "agent-1", True))

    def test_counter_is_per_agent(self):
        self.set_pass(False)
        self.run_checks(agent_id="agent-1")
        self.run_checks(agent_id="agent-1", stop_hook_active=True)
        self.assertIn("attempt 1 of 3", self.run_checks(agent_id="agent-2", stop_hook_active=True).stderr)
        self.assertEqual(len(self.counter_files()), 2)

    def test_other_agents_are_ignored(self):
        self.set_pass(False)
        for agent_type in ("implementer", "loom:implementation-reviewer", "Explore", "", None):
            with self.subTest(agent_type=agent_type):
                proc = self.run_checks(agent_type=agent_type)
                self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))
        self.assertEqual(self.counter_files(), [])

    def test_no_config_is_a_silent_no_op(self):
        os.remove(self.path(".claude", "loom.json"))
        proc = self.run_checks()
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_outside_git_is_a_silent_no_op(self):
        outside = os.path.join(self.tmp, "plain")
        os.makedirs(outside)
        proc = self.run_checks(cwd=outside)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_runs_at_the_git_top_level(self):
        self.set_pass(True)
        os.makedirs(self.path("sub", "dir"))
        self.assertEqual(self.run_checks(cwd=self.path("sub", "dir")).returncode, 0)

    def test_default_check_command_is_make_check(self):
        self.write_config({})
        write(self.path("Makefile"), "check:\n\t@echo make-check-ran; exit 1\n")
        proc = self.run_checks()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("make-check-ran", proc.stderr)
        self.assertIn("`make check`", proc.stderr)

    def test_long_output_is_shortened(self):
        self.write_config({"checks": {"check": "for i in $(seq 1 500); do echo line-$i; done; exit 1"}})
        proc = self.run_checks()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("line-500", proc.stderr)
        self.assertNotIn("line-1\n", proc.stderr)
        self.assertIn("output shortened", proc.stderr)

    def test_invalid_check_command_takes_the_default(self):
        # checks.check is never null or empty (LOOM_SPEC.md 19.1): an invalid value takes `make check`.
        write(self.path("Makefile"), "check:\n\t@echo make-check-ran; exit 1\n")
        for value in ("", None, 5):
            with self.subTest(value=value):
                self.write_config({"checks": {"check": value}})
                proc = self.run_checks(agent_id="agent-%r" % (value,))  # a fresh attempt counter
                self.assertEqual(proc.returncode, 2)
                self.assertIn("make-check-ran", proc.stderr)
                self.assertIn("`make check`", proc.stderr)

    def test_invalid_input_is_ignored(self):
        proc = run_hook(CHECKS, None, raw="not json", cwd=self.repo, env=self.env)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))


class SubagentChecksHardeningTest(RepoTestCase):
    """Counter I/O failures and a broken loom.json (LOOM_SPEC.md 11.4)."""

    loom_config = {"checks": {"check": "echo check-ran; exit 1"}}

    def setUp(self):
        super().setUp()
        self.tmpdir = os.path.join(self.tmp, "hooktmp")
        os.makedirs(self.tmpdir)
        self.env = {"TMPDIR": self.tmpdir}

    def run_checks(self, stop_hook_active=False):
        payload = stop_payload(self.repo, event="SubagentStop", stop_hook_active=stop_hook_active,
                               agent_id="agent-1", agent_type="loom:implementer")
        return run_hook(CHECKS, payload, env=self.env)

    def lock_counter_dir(self, mode):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        path = os.path.join(self.tmpdir, "loom-subagent-checks")
        os.makedirs(path, exist_ok=True)
        os.chmod(path, mode)
        self.addCleanup(os.chmod, path, 0o700)

    def test_unwritable_counter_still_blocks_once(self):
        self.lock_counter_dir(0o500)
        first = self.run_checks()
        self.assertEqual(first.returncode, 2, first.stdout)
        self.assertIn("attempt counter not available", first.stderr)
        self.assertIn("check-ran", first.stderr)
        second = self.run_checks(stop_hook_active=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        message = json.loads(second.stdout)["systemMessage"]
        self.assertIn("attempt counter is not available", message)
        self.assertIn("blocked", message)

    def test_unreadable_counter_still_blocks_once(self):
        self.lock_counter_dir(0o000)
        self.assertEqual(self.run_checks().returncode, 2)
        self.assertEqual(self.run_checks(stop_hook_active=True).returncode, 0)

    def test_pass_with_a_locked_counter(self):
        self.lock_counter_dir(0o000)
        self.write_config({"checks": {"check": "true"}})
        proc = self.run_checks()
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_counter_that_is_not_utf8_counts_as_zero(self):
        self.write_config({"checks": {"check": "echo check-ran; exit 1"}, "hooks": {"maxCheckAttempts": 3}})
        self.assertEqual(self.run_checks().returncode, 2)
        directory = os.path.join(self.tmpdir, "loom-subagent-checks")
        (name,) = os.listdir(directory)
        with open(os.path.join(directory, name), "wb") as fh:
            fh.write(b"\xff\xfe{")
        proc = self.run_checks(stop_hook_active=True)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("attempt 1 of 3", proc.stderr)

    def test_broken_config_does_not_block(self):
        write(self.path("Makefile"), "check:\n\t@echo make-check-ran; exit 1\n")
        for raw in ("{ not json", "", "[1, 2]"):
            with self.subTest(raw=raw):
                with open(self.path(".claude", "loom.json"), "w") as fh:
                    fh.write(raw)
                proc = self.run_checks()
                self.assertEqual(proc.returncode, 0, proc.stderr)
                message = json.loads(proc.stdout)["systemMessage"]
                self.assertIn(".claude/loom.json", message)
                self.assertIn("did not run", message)
                self.assertNotIn("using defaults", message)

    def test_config_warnings_reach_the_implementer(self):
        self.write_config({"checks": {"check": "echo check-ran; exit 1"}, "docs": {"nope": "x"}})
        proc = self.run_checks()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Warnings about .claude/loom.json (loom-state):", proc.stderr)
        self.assertIn("docs.nope", proc.stderr)

    def test_no_warning_section_without_warnings(self):
        self.assertNotIn("Warnings about", self.run_checks().stderr)


class CheckTimeoutTest(unittest.TestCase):
    def test_timeout_kills_the_process_group(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "scripts", "hooks"))
        try:
            import loomhook
        finally:
            sys.path.pop(0)
        tmp = tempfile.mkdtemp(prefix="loom-timeout-")
        self.addCleanup(shutil.rmtree, tmp, True)
        code, output = loomhook.run_check("echo started; sleep 30; echo never", tmp, timeout=1)
        self.assertIsNone(code)
        self.assertIn("started", output)
        self.assertNotIn("never", output)
        self.assertEqual(loomhook.run_check("exit 3", tmp, timeout=5)[0], 3)

    def test_output_tail(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "scripts", "hooks"))
        try:
            import loomhook
        finally:
            sys.path.pop(0)
        self.assertEqual(loomhook.output_tail("a\nb\n"), "a\nb")
        tail = loomhook.output_tail("\n".join("x%d" % i for i in range(10)), max_lines=3)
        self.assertTrue(tail.startswith("[... output shortened"))
        self.assertTrue(tail.endswith("x7\nx8\nx9"))
        long_line = loomhook.output_tail("y" * 100 + "\nend", max_chars=10)
        self.assertTrue(long_line.endswith("end"))
        self.assertLessEqual(len(long_line.splitlines()[-1]), 10)


class StopLintTest(RepoTestCase):
    loom_config = {"checks": {"lint": "echo lint-ran; exit 1"}, "hooks": {"stopLint": True}}

    def run_lint(self, stop_hook_active=False, cwd=None):
        return run_hook(LINT, stop_payload(cwd or self.repo, stop_hook_active=stop_hook_active))

    def test_off_by_default(self):
        self.write_config({"checks": {"lint": "exit 1"}})
        write(self.path("src", "app.py"), "x = 1\n")
        proc = self.run_lint()
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_clean_tree_skips_lint(self):
        proc = self.run_lint()
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))

    def test_code_change_with_failing_lint_blocks(self):
        write(self.path("src", "app.py"), "x = 1\n")
        proc = self.run_lint()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("lint-ran", proc.stderr)
        self.assertIn("Fix the lint errors", proc.stderr)
        self.assertIn("If this change was left blocked on purpose (a blocked phase), report it instead of fixing it.", proc.stderr)

    def test_modified_tracked_file_counts(self):
        write(self.path("README.md"), "# changed\n")
        self.assertEqual(self.run_lint().returncode, 2)

    def test_passing_lint_allows_the_stop(self):
        self.write_config({"checks": {"lint": "true"}, "hooks": {"stopLint": True}})
        write(self.path("src", "app.py"), "x = 1\n")
        proc = self.run_lint()
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))

    def test_only_docs_and_loom_changes_skip_lint(self):
        write(self.path("docs", "tasks", "42-x.md"), "# summary\n")
        write(self.path(".loom", "tasks", "42-x", "log.md"), "## Phase 1 — in-progress\n")
        self.assertEqual(self.run_lint().returncode, 0)

    def test_custom_docs_and_work_dirs(self):
        self.write_config({"checks": {"lint": "exit 1"}, "hooks": {"stopLint": True},
                           "docsDir": "documentation", "workDir": "work/tasks"})
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "config")
        write(self.path("documentation", "a.md"), "x\n")
        write(self.path("work", "tasks", "1-x", "log.md"), "x\n")
        self.assertEqual(self.run_lint().returncode, 0)
        write(self.path("docs", "a.md"), "x\n")  # not the configured docsDir
        self.assertEqual(self.run_lint().returncode, 2)

    def test_stop_hook_active_prevents_a_loop(self):
        write(self.path("src", "app.py"), "x = 1\n")
        proc = self.run_lint(stop_hook_active=True)
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))

    def run_lint_with(self, **extra):
        return run_hook(LINT, stop_payload(self.repo, **extra))

    def test_plan_mode_skips_lint(self):
        write(self.path("src", "app.py"), "x = 1\n")
        proc = self.run_lint_with(permission_mode="plan")
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))
        self.assertEqual(self.run_lint_with(permission_mode="acceptEdits").returncode, 2)

    def test_background_work_skips_lint(self):
        # Stop input `background_tasks`: in-flight tasks (Claude Code hooks docs, Stop input).
        write(self.path("src", "app.py"), "x = 1\n")
        running = [{"id": "task-001", "type": "subagent", "status": "running",
                    "description": "implement phase 2", "agent_type": "loom:implementer"}]
        for tasks in (running, [{"id": "t", "type": "shell"}], ["opaque"]):
            with self.subTest(tasks=tasks):
                proc = self.run_lint_with(background_tasks=tasks)
                self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_finished_or_no_background_work_still_lints(self):
        write(self.path("src", "app.py"), "x = 1\n")
        for tasks in ([], None, "x", [{"id": "t", "type": "shell", "status": "completed"}]):
            with self.subTest(tasks=tasks):
                self.assertEqual(self.run_lint_with(background_tasks=tasks).returncode, 2)

    def test_no_config_is_a_silent_no_op(self):
        os.remove(self.path(".claude", "loom.json"))
        write(self.path("src", "app.py"), "x = 1\n")
        proc = self.run_lint()
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_null_lint_command_is_a_no_op(self):
        self.write_config({"checks": {"lint": None}, "hooks": {"stopLint": True}})
        write(self.path("src", "app.py"), "x = 1\n")
        proc = self.run_lint()
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_empty_lint_command_is_off(self):
        # An empty optional check means "no such check", as in 1.1.0 (loom-state warns: use null).
        self.write_config({"checks": {"lint": "  "}, "hooks": {"stopLint": True}})
        write(self.path("Makefile"), "lint:\n\t@echo make-lint-ran; exit 1\n")
        write(self.path("src", "app.py"), "x = 1\n")
        proc = self.run_lint()
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_invalid_lint_command_takes_the_default(self):
        self.write_config({"checks": {"lint": 5}, "hooks": {"stopLint": True}})
        write(self.path("Makefile"), "lint:\n\t@echo make-lint-ran; exit 1\n")
        write(self.path("src", "app.py"), "x = 1\n")
        proc = self.run_lint()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("make-lint-ran", proc.stderr)

    def test_docs_map_paths_skip_lint(self):
        self.write_config({"checks": {"lint": "exit 1"}, "hooks": {"stopLint": True},
                           "docs": {"overview": "ARCHITECTURE.md", "decisions": {"dir": "adr"},
                                    "tasks": "notes/tasks"}})
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "config")
        write(self.path("ARCHITECTURE.md"), "# Architecture\n")
        write(self.path("adr", "0001-x.md"), "# 0001. X\n")
        write(self.path("notes", "tasks", "42-x.md"), "# summary\n")
        write(self.path("docs", "conventions.md"), "x\n")  # the default role path below docsDir
        self.assertEqual(self.run_lint().returncode, 0)
        write(self.path("notes", "other.md"), "x\n")  # next to a mapped path, not below it
        self.assertEqual(self.run_lint().returncode, 2)

    def test_style_guide_and_screens_skip_lint(self):
        self.write_config({"checks": {"lint": "exit 1"}, "hooks": {"stopLint": True},
                           "docs": {"style": "ui/STYLE.md", "screens": "ui/screens"}})
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "config")
        write(self.path("ui", "STYLE.md"), "# Style guide\n")
        write(self.path("ui", "screens", "home.dc.html"), "<div></div>\n")
        self.assertEqual(self.run_lint().returncode, 0)
        write(self.path("ui", "app.css"), "x\n")  # next to the mapped paths, not below them
        self.assertEqual(self.run_lint().returncode, 2)


if __name__ == "__main__":
    unittest.main()
