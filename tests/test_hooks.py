"""Tests for the hook scripts, fed with Claude Code style JSON on stdin."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from loomtest import RepoTestCase, bash_payload, git, run_hook, write

GUARD = "guard_main.py"
FILTER = "block_output_filtering.py"
SESSION = "session_start.py"


def decision(proc):
    """Return the permissionDecision, or None when the hook allowed silently."""
    if proc.returncode != 0:
        raise AssertionError("hook exited %d: %s" % (proc.returncode, proc.stderr))
    if not proc.stdout.strip():
        return None
    out = json.loads(proc.stdout)
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    return spec["permissionDecision"], spec["permissionDecisionReason"]


class GuardMainOnMainTest(RepoTestCase):
    """Current branch is main (with commits)."""

    DENY = [
        'git commit -m "x"',
        "git commit --amend --no-edit",
        "git push",
        "git push origin HEAD",
        "git add -A && git commit -m wip",
        "git status; git commit -am x",
        "cd sub && git commit -m x",
        "(cd sub; git push)",
        "git -C sub commit -m x",
        "git -c user.name=x --no-pager commit -m x",
        "FOO=1 git commit -m x",
        "env GIT_EDITOR=true git commit",
        "bash -c 'git commit -m x'",
        "git commit -m \"$(cat <<'EOF'\nfix: thing\n\nbody\nEOF\n)\"",
        "echo ok\ngit commit -m x",
        "git ci -m x",  # alias for commit
        "git switch main && git commit -m x",
    ]
    ALLOW = [
        "git status",
        'echo "git commit -m x"',
        "echo 'git push origin main'",
        "git log --grep 'git commit'",
        "git commit-tree HEAD^{tree} -m x",
        "# git commit -m x",
        "git switch -c feat/1-x && git commit -m x",
        "git checkout -b fix/2-y && git push -u origin fix/2-y",
        "ls | grep commit",
        "git -C ../outside commit -m x",  # another repo without loom.json
    ]

    def setUp(self):
        super().setUp()
        # Two commits: the bootstrap push exception (one commit) does not apply.
        self.commit_file("src/app.py", "x = 1\n", "second")
        os.makedirs(self.path("sub"))
        git(self.repo, "config", "alias.ci", "commit")
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        git(outside, "init", "-q", "-b", "main")
        git(outside, "commit", "-q", "--allow-empty", "-m", "init")

    def test_deny(self):
        for command in self.DENY:
            with self.subTest(command=command):
                result = decision(run_hook(GUARD, bash_payload(command, self.repo)))
                self.assertIsNotNone(result, command)
                self.assertEqual(result[0], "deny")
                self.assertIn("Create a task branch with /loom:start-task", result[1])

    def test_allow(self):
        for command in self.ALLOW:
            with self.subTest(command=command):
                self.assertIsNone(decision(run_hook(GUARD, bash_payload(command, self.repo))), command)

    def test_subdirectory_cwd(self):
        result = decision(run_hook(GUARD, bash_payload("git commit -m x", self.path("sub"))))
        self.assertEqual(result[0], "deny")


class GuardMainOnTaskBranchTest(RepoTestCase):
    DENY = [
        "git push origin main",
        "git push origin HEAD:main",
        "git push origin feat/42-x:main",
        "git push origin +main",
        "git push origin +HEAD:refs/heads/main",
        "git push --force origin main",
        "git push -f origin main",
        "git push --force-with-lease origin main",
        "git push origin :main",
        "git push origin --delete main",
        "git push origin feat/42-x main",
        "git push --all origin",
        "git push --mirror origin",
        "git push origin 'refs/heads/*:refs/heads/*'",
        "git fetch && git -C . push -u origin HEAD:main",
        "git checkout -b fix/1-y && git switch main && git push",
    ]
    ALLOW = [
        "git commit -m 'feat(auth): add token storage (#42)'",
        "git push",
        "git push -u origin feat/42-x",
        "git push --force-with-lease origin feat/42-x",
        "git push --force-with-lease=main origin feat/42-x",
        "git push origin HEAD",
        "git push origin main-fixes",
        "git push origin HEAD:refs/heads/feat/42-x",
        "git push origin tag v1.0",
        "git push origin tag main",
        "git rebase origin/main",
        "git pull origin main",
        "git switch main",
    ]

    def setUp(self):
        super().setUp()
        self.commit_file("src/app.py", "x = 1\n", "second")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")

    def test_deny(self):
        for command in self.DENY:
            with self.subTest(command=command):
                result = decision(run_hook(GUARD, bash_payload(command, self.repo)))
                self.assertIsNotNone(result, command)
                self.assertEqual(result[0], "deny")

    def test_allow(self):
        for command in self.ALLOW:
            with self.subTest(command=command):
                self.assertIsNone(decision(run_hook(GUARD, bash_payload(command, self.repo))), command)


class GuardMainConfigTest(RepoTestCase):
    loom_config = {"mainBranch": "trunk"}

    def test_configured_main_branch(self):
        # On "main", which is not the configured main branch here.
        self.assertIsNone(decision(run_hook(GUARD, bash_payload("git commit -m x", self.repo))))
        result = decision(run_hook(GUARD, bash_payload("git push origin trunk", self.repo)))
        self.assertEqual(result[0], "deny")
        self.assertIn("trunk", result[1])
        git(self.repo, "branch", "-m", "trunk")
        self.assertEqual(decision(run_hook(GUARD, bash_payload("git commit -m x", self.repo)))[0], "deny")


class GuardMainEmptyRepoTest(RepoTestCase):
    initial_commit = False

    def test_first_commit_allowed(self):
        command = "git add .gitignore README.md && git commit -m 'chore: initial commit'"
        self.assertIsNone(decision(run_hook(GUARD, bash_payload(command, self.repo))))

    def test_second_commit_denied(self):
        write(self.path("README.md"), "# x\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "initial")
        self.assertEqual(decision(run_hook(GUARD, bash_payload("git commit -m x", self.repo)))[0], "deny")


class NoLoomJsonTest(unittest.TestCase):
    """All hooks are silent no-ops without loom.json and outside git."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="loom-hooks-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "repo")
        self.plain = os.path.join(self.tmp, "plain")
        os.makedirs(self.repo)
        os.makedirs(self.plain)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")

    def assertSilent(self, proc):
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_guard(self):
        for cwd in (self.repo, self.plain):
            self.assertSilent(run_hook(GUARD, bash_payload("git commit -m x && git push origin main", cwd)))

    def test_filter(self):
        for cwd in (self.repo, self.plain):
            self.assertSilent(run_hook(FILTER, bash_payload("pytest | tail -5", cwd)))

    def test_session_start(self):
        for cwd in (self.repo, self.plain):
            payload = {"session_id": "s", "transcript_path": "/tmp/t", "cwd": cwd,
                       "hook_event_name": "SessionStart", "source": "startup"}
            self.assertSilent(run_hook(SESSION, payload))

    def test_bad_input_never_crashes(self):
        for script in (GUARD, FILTER, SESSION, "subagent_checks.py", "stop_lint.py", "subagent_events.py"):
            for raw in ("", "not json", "[]", '{"tool_input": 5}'):
                proc = run_hook(script, None, raw=raw, cwd=self.plain)
                self.assertEqual(proc.returncode, 0, (script, raw, proc.stderr))
                self.assertEqual(proc.stdout, "", (script, raw))


class OutputFilteringTest(RepoTestCase):
    loom_config = {"checks": {"lint": "./scripts/lint.sh --all", "check": "make check"}}

    DENY = [
        "pytest | tail -20",
        "pytest 2>&1 | head -50",
        "uv run pytest -q | grep FAILED",
        "uv run --frozen ruff check . | head",
        "make test | tail",
        "make -k check 2>&1 | less",
        "make lint | more",
        "make typecheck | cut -c1-80",
        "npm test | grep fail",
        "npm run lint | sed -n 1,20p",
        "npm run typecheck | awk '{print $1}'",
        "pyright | tail -3",
        "mypy src | head",
        "python -m pytest | tail",
        "cd app && pytest -x | tail -5",
        "pytest | tee out.log | tail -5",
        "./scripts/lint.sh --all | head",
        "bash -c 'pytest | tail'",
        "CI=1 pytest |& tail",
    ]
    ALLOW = [
        "pytest",
        "pytest | tee pytest.log",
        "make check 2>&1 | tee /tmp/check.log",
        "pytest > out.log; tail -20 out.log",
        "git log | head",
        "grep -r pytest . | head",
        'echo "pytest | tail"',
        "ls | grep test",
        "make build | tail",
        "npm run build | tail",
        "pytest && echo done | tail -1",
        "cat pytest.log | tail",
    ]

    def test_deny(self):
        for command in self.DENY:
            with self.subTest(command=command):
                result = decision(run_hook(FILTER, bash_payload(command, self.repo)))
                self.assertIsNotNone(result, command)
                self.assertEqual(result[0], "deny")
                self.assertIn("Run checks unfiltered", result[1])

    def test_allow(self):
        for command in self.ALLOW:
            with self.subTest(command=command):
                self.assertIsNone(decision(run_hook(FILTER, bash_payload(command, self.repo))), command)


class SessionStartTest(RepoTestCase):
    def payload(self, source="startup"):
        return {"session_id": "s", "transcript_path": "/tmp/t", "cwd": self.repo,
                "hook_event_name": "SessionStart", "source": source}

    def test_on_main_one_hint_line(self):
        proc = run_hook(SESSION, self.payload())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("/loom:start-task", lines[0])

    def test_unrecognized_branch_one_hint_line(self):
        git(self.repo, "switch", "-q", "-c", "spike/x")
        lines = run_hook(SESSION, self.payload("clear")).stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("matches no task", lines[0])

    def test_task_context(self):
        d = self.task_dir("42-auth-flow")
        self.ticket(d, mode="full")
        self.artifact(d, "01-research-questions.md", "research-questions", "approved")
        self.artifact(d, "02-research.md", "research", "in-review")
        self.artifact(d, "03-design.md", "design", "in-review",
                      "## Open Questions — Round 1\n**Q1. A?**\n**Q2. B?**\n")
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")
        proc = run_hook(SESSION, self.payload("compact"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        self.assertIn("Task #42 (full mode) in .loom/tasks/42-auth-flow", out)
        self.assertIn("03-design.md in-review (2 open questions)", out)
        self.assertIn("02-research.md in-review", out)
        self.assertIn("Next: /loom:iterate <answers>", out)
        self.assertIn("working tree clean", out)



class RunSafelyTest(unittest.TestCase):
    def test_unexpected_error_exits_zero(self):
        import io
        import sys
        from loomtest import HOOKS_DIR
        sys.path.insert(0, HOOKS_DIR)
        try:
            import loomhook
        finally:
            sys.path.remove(HOOKS_DIR)

        def boom():
            raise RuntimeError("boom")

        err = io.StringIO()
        old, sys.stderr = sys.stderr, err
        try:
            with self.assertRaises(SystemExit) as ctx:
                loomhook.run_safely(boom, "test")
        finally:
            sys.stderr = old
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("boom", err.getvalue())


def guard(command, cwd):
    return decision(run_hook(GUARD, bash_payload(command, cwd)))


class GuardBranchSwitchTest(RepoTestCase):
    """`git switch|checkout` earlier in the same command changes the branch."""

    def setUp(self):
        super().setUp()
        self.commit_file("src/app.py", "x = 1\n", "second")
        head = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "update-ref", "refs/remotes/origin/main", head)
        git(self.repo, "update-ref", "refs/remotes/origin/feat/9-remote", head)
        git(self.repo, "branch", "feat/42-x")

    def test_from_task_branch_to_main_is_denied(self):
        git(self.repo, "switch", "-q", "feat/42-x")
        for command in (
            "git checkout main && git commit -am x",
            "git checkout main && git push",
            "git checkout -q main; git commit -m x",
            "git switch main && git commit -m x",
            "git switch --track origin/main && git commit -m x",
            "git checkout -t origin/main && git push",
            "git checkout --track refs/remotes/origin/main && git commit -m x",
        ):
            with self.subTest(command=command):
                self.assertEqual(guard(command, self.repo)[0], "deny")

    def test_from_main_to_task_branch_is_allowed(self):
        for command in (
            "git checkout feat/42-x && git commit -m x",
            "git checkout feat/9-remote && git commit -m x",  # DWIM from origin
            "git switch -c feat/1-y --track origin/main && git commit -m x",
            "git checkout -b fix/2-z origin/main && git push -u origin fix/2-z",
            "git checkout origin/main && git commit -m x",  # detached HEAD
        ):
            with self.subTest(command=command):
                self.assertIsNone(guard(command, self.repo))

    def test_checkout_of_a_file_keeps_main(self):
        for command in (
            "git checkout README.md && git commit -m x",
            "git checkout -- README.md && git commit -m x",
            "git checkout feat/42-x -- README.md && git commit -m x",
            "git checkout HEAD~1 README.md && git commit -m x",
            "git checkout no-such-thing && git commit -m x",
        ):
            with self.subTest(command=command):
                self.assertEqual(guard(command, self.repo)[0], "deny")


class GuardAliasAndFallbackTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.commit_file("src/app.py", "x = 1\n", "second")

    def test_shell_alias_is_followed(self):
        git(self.repo, "config", "alias.sci", "!git commit")
        git(self.repo, "config", "alias.pm", "!f() { git push origin main; }; f")
        self.assertEqual(guard("git sci -m x", self.repo)[0], "deny")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        self.assertIsNone(guard("git sci -m x", self.repo))
        self.assertEqual(guard("git pm", self.repo)[0], "deny")

    def test_unparsable_command_on_main_is_denied(self):
        command = "git commit -m $'don\\'t'"
        self.assertIsNone(loomhook_parse(command))
        result = guard(command, self.repo)
        self.assertEqual(result[0], "deny")
        self.assertIn("could not be parsed", result[1])
        self.assertEqual(guard("echo 'x && git push", self.repo)[0], "deny")

    def test_unparsable_command_off_main_is_allowed(self):
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        self.assertIsNone(guard("git commit -m $'don\\'t'", self.repo))
        self.assertIsNone(guard("echo 'unbalanced", self.repo))


def loomhook_parse(command):
    import sys
    from loomtest import HOOKS_DIR
    sys.path.insert(0, HOOKS_DIR)
    try:
        import loomhook
    finally:
        sys.path.remove(HOOKS_DIR)
    return loomhook.parse_pipelines(command)


class GuardBootstrapPushTest(RepoTestCase):
    """First push of main on an empty remote (section 9.1): only a plain push."""

    ALLOW = [
        "git push -u origin main",
        "git push",
        "git push -q --set-upstream origin main",
        "git push origin HEAD",
        "git push -u origin HEAD:main",
        "git push -v origin main:main",
        "git push --quiet origin refs/heads/main",
    ]
    DENY = [
        "git push --force origin main",
        "git push -f origin main",
        "git push -uf origin main",
        "git push origin +main",
        "git push origin +HEAD:main",
        "git push --force-with-lease origin main",
        "git push --mirror origin",
        "git push --all origin",
        "git push --branches origin",
        "git push origin --delete main",
        "git push -d origin main",
        "git push origin :main",
        "git push origin feat/42-x:main",
        "git push origin main feat/42-x",
        "git push origin HEAD:refs/heads/other",
        "git push upstream main",
        "git push https://example.com/r.git main",
        "git push -u origin main -- main",
    ]

    def setUp(self):
        super().setUp()
        remote = os.path.join(self.tmp, "remote.git")
        git(self.tmp, "init", "-q", "--bare", "-b", "main", remote)
        git(self.repo, "remote", "add", "origin", remote)
        git(self.repo, "remote", "add", "upstream", remote)
        git(self.repo, "branch", "feat/42-x")  # no new commit on main

    def test_plain_first_push_is_allowed(self):
        for command in self.ALLOW:
            with self.subTest(command=command):
                self.assertIsNone(guard(command, self.repo))

    def test_anything_else_is_denied(self):
        for command in self.DENY:
            with self.subTest(command=command):
                self.assertEqual(guard(command, self.repo)[0], "deny")

    def test_other_remote_with_tracking_ref_is_denied(self):
        git(self.repo, "update-ref", "refs/remotes/upstream/main", git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(guard("git push upstream main", self.repo)[0], "deny")

    def test_configured_push_remote_other_than_origin_is_denied(self):
        git(self.repo, "config", "branch.main.pushRemote", "upstream")
        self.assertEqual(guard("git push", self.repo)[0], "deny")
        self.assertIsNone(guard("git push -u origin main", self.repo))

    def test_switch_earlier_in_command_does_not_qualify(self):
        git(self.repo, "switch", "-q", "feat/42-x")
        for command in ("git switch main && git push origin feat/42-x:main",
                        "git switch main && git push -f origin main",
                        "git switch main && git push -u origin main",
                        "git checkout main && git push"):
            with self.subTest(command=command):
                self.assertEqual(guard(command, self.repo)[0], "deny")

    def test_two_commits_are_denied(self):
        self.commit_file("src/app.py", "x = 1\n", "second")
        self.assertEqual(guard("git push -u origin main", self.repo)[0], "deny")

    def test_existing_remote_main_is_denied(self):
        git(self.repo, "update-ref", "refs/remotes/origin/main", git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(guard("git push -u origin main", self.repo)[0], "deny")

    def test_commit_is_still_denied(self):
        self.assertEqual(guard("git commit -m x", self.repo)[0], "deny")

    def test_push_to_main_from_task_branch_is_still_denied(self):
        git(self.repo, "switch", "-q", "feat/42-x")
        self.assertEqual(guard("git push origin HEAD:main", self.repo)[0], "deny")


class ConfiguredChecksTest(RepoTestCase):
    loom_config = {"checks": {"lint": "cd app && npm run lint", "test": "./scripts/run-tests.sh --fast",
                              "check": "make check"}}

    def test_cd_segment_is_not_a_check(self):
        self.assertIsNone(decision(run_hook(FILTER, bash_payload("cd app | head", self.repo))))
        self.assertIsNone(decision(run_hook(FILTER, bash_payload("cd app && ls | head", self.repo))))

    def test_configured_script_matches_by_first_word(self):
        for command in ("./scripts/run-tests.sh | tail", "scripts/run-tests.sh -k auth | grep FAIL",
                        "cd app && npm run lint | head"):
            with self.subTest(command=command):
                self.assertEqual(decision(run_hook(FILTER, bash_payload(command, self.repo)))[0], "deny")
        self.assertIsNone(decision(run_hook(FILTER, bash_payload("./scripts/other.sh | tail", self.repo))))


class NullChecksTest(RepoTestCase):
    """A null check does not exist in the project: the filter hook skips it (LOOM_SPEC.md 11.3, 19.1)."""

    loom_config = {"checks": {"lint": None, "typecheck": None, "test": "./scripts/t.sh", "check": "make check"}}

    def test_null_checks_are_skipped(self):
        self.assertEqual(decision(run_hook(FILTER, bash_payload("./scripts/t.sh | tail", self.repo)))[0], "deny")
        self.assertEqual(decision(run_hook(FILTER, bash_payload("make lint | head", self.repo)))[0], "deny")
        self.assertIsNone(decision(run_hook(FILTER, bash_payload("null | tail", self.repo))))
        proc = run_hook(FILTER, bash_payload("ls | head", self.repo))
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))


class BrokenHelperImportTest(unittest.TestCase):
    """A hook whose helper module cannot load exits 0 with a stderr message."""

    def test_broken_import(self):
        import subprocess
        import sys
        from loomtest import HOOKS_DIR
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="loom-broken-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, "loomhook.py"), "w") as fh:
            fh.write("raise ImportError('broken helper')\n")
        for script in (GUARD, FILTER, SESSION, "subagent_checks.py", "stop_lint.py", "subagent_events.py"):
            shutil.copy(os.path.join(HOOKS_DIR, script), tmp)
            proc = subprocess.run(
                [sys.executable, os.path.join(tmp, script)], input=json.dumps(bash_payload("git commit", tmp)),
                cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            )
            self.assertEqual(proc.returncode, 0, script)
            self.assertEqual(proc.stdout, "", script)
            self.assertIn("cannot load helpers", proc.stderr, script)


if __name__ == "__main__":
    unittest.main()
