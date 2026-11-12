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
        ):
            with self.subTest(command=command):
                self.assertEqual(guard(command, self.repo)[0], "deny")

    def test_track_creates_main_when_it_does_not_exist_locally(self):
        git(self.repo, "switch", "-q", "feat/42-x")
        git(self.repo, "branch", "-D", "main")
        for command in (
            "git switch --track origin/main && git commit -m x",
            "git checkout -t origin/main && git push",
            "git checkout --track refs/remotes/origin/main && git commit -m x",
        ):
            with self.subTest(command=command):
                self.assertEqual(guard(command, self.repo)[0], "deny")

    def test_track_of_an_existing_local_branch_fails(self):
        # git refuses: "a branch named 'main' already exists"; the branch does not change.
        git(self.repo, "switch", "-q", "feat/42-x")
        for command in ("git switch --track origin/main; git commit -m x",
                        "git checkout -t origin/main; git commit -m x"):
            with self.subTest(command=command):
                self.assertIsNone(guard(command, self.repo))

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
        command = "echo 'unbalanced; git commit -m x"
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
    return loomhook.parse_script(command)


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

    def test_push_that_cannot_update_main_is_allowed(self):
        # Not the bootstrap exception: the main-branch rule for pushes that cannot update it.
        self.assertIsNone(guard("git push origin HEAD:refs/heads/other", self.repo))

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


# ---------------------------------------------------------------------------
# Hardening: the guard is conservative when it cannot resolve a command
# ---------------------------------------------------------------------------


class GuardConservativeOnMainTest(RepoTestCase):
    """On main: forms that used to bypass the guard are denied; correct allows stay."""

    DENY = [
        # A1: a directory the guard cannot resolve means the original cwd.
        'cd "$(git rev-parse --show-toplevel)" && git commit -m x',
        "cd $(git rev-parse --show-toplevel) && git commit -m x",
        'git -C "$(pwd)" commit -m x',
        'git -C "$PWD" commit -m x',
        "D=sub; cd $D && git commit -m x",
        "cd /nonexistent-dir-xyz; git commit -m x",
        'cd "$UNSET_VAR/sub"; git commit -m x',
        "git worktree add ../wt -b feat/1-wt && cd ../wt && git commit -m x",  # not there yet
        # A2: subshell scope and the directory stack.
        "(cd ../outside && ls); git commit -m x",
        "(cd ../outside && ls) && git commit -m x",
        "cd ../outside && cd - && git commit -m x",
        "pushd ../outside; popd; git commit -m x",
        "pushd ../outside && pushd ../repo/sub && popd && popd && git commit -m x",
        "popd; git commit -m x",  # a stack from before the command: unknown
        "cd ../outside | true; git commit -m x",  # a pipeline stage is a subshell
        # A3: branch switches git refuses, and switches back.
        "git switch -c feat/9-existing; git commit -m x",
        "git checkout -b feat/9-existing\ngit commit -m x",
        "git switch -c feat/9-existing || true; git commit -m x",
        "git switch nosuchbranch; git commit -m x",
        "git switch -c feat/1-new && git switch - && git commit -m x",
        "git switch -c feat/1-new && git checkout - && git commit -m x",
        "git switch -c feat/1-new && git checkout @{-1} && git commit -m x",
        "git switch -c feat/1-new && git checkout main -- && git commit -m x",
        "git switch -c feat/1-new && git symbolic-ref HEAD refs/heads/main && git commit -m x",
        'git switch -c feat/1-new && git switch "$B" && git commit -m x',  # unknown: the real branch
        # A4: code the shell runs although it sits in a word or on stdin.
        'echo "$(git commit -m x)"',
        'x="$(git commit -m x 2>&1)"; echo "$x"',
        "echo `git commit -m x`",
        'echo "`git commit -m x`"',
        "cat <(git commit -m x)",
        "diff <(git log) >(git commit -m x)",
        "bash <<'EOF'\ngit commit -m x\nEOF",
        "sh -s <<EOF\ngit commit -m x\nEOF",
        "bash <<< 'git commit -m x'",
        "echo 'git commit -m x' | bash",
        "printf 'git commit -m x' | sh",
        "cat <<'EOF' | bash\ngit commit -m x\nEOF",
        "cat <<EOF > out.txt\n$(git commit -m x)\nEOF",  # unquoted here-doc bodies expand
        "xargs git commit -m <<< x",
        "echo msg | xargs git commit -m",
        "echo msg | xargs -n 1 git commit -m",
        # A5: wrappers and prefixes.
        "timeout 30 git commit -m x",
        "timeout -s KILL -k 5 30 git commit -m x",
        "nice -n 10 git commit -m x",
        "ionice -c 3 git commit -m x",
        "stdbuf -oL git commit -m x",
        "noglob git commit -m x",
        "=git commit -m x",
        "function f { git commit -m x; }; f",
        "bash -o pipefail -c 'git commit -m x'",
        "bash -euo pipefail -c 'git commit -m x'",
        "git --attr-source HEAD commit -m x",
        "git ci2 -m x",  # an alias of an alias
    ]
    ALLOW = [
        'echo "git commit -m x"',
        "git log --oneline --grep='git commit' -n 5",
        "git stash push -m 'before commit'",
        "git show HEAD --stat # git commit -m x",
        "git commit-graph write",
        "cat <<'EOF' > doc.md\ngit commit -m x\ngit push origin main\nEOF",
        "cat <<EOF > doc.md\nrun git push origin main\nEOF",
        "git -C ../outside commit -m x",
        "cd ../outside && git commit -m x",
        "(cd ../outside && git commit -m x)",
        "pushd ../outside && git commit -m x",
        "git switch -c feat/1-new && git commit -m x",
        "git switch --create=feat/1-new && git commit -m x",
        "git switch --create feat/1-new && git commit -m x",
        "git checkout -bfeat/1-new && git commit -m x",
        "git checkout -qb feat/1-new && git commit -m x",
        "git switch -C feat/9-existing && git commit -m x",  # -C resets an existing branch
        "git switch feat/9-existing && git commit -m x",
        "git switch -c feat/1-new && git switch main && git switch feat/1-new && git commit -m x",
        "git branch feat/2-new && git switch feat/2-new && git commit -m x",
        "git branch -m feat/3-renamed && git commit -m x",
        "git switch --detach && git commit -m x",
        "echo $'it\\'s'",
        "git merge --no-ff feat/9-existing -m merge",  # out of the guard's scope
        "timeout 30 git status",
    ]

    def setUp(self):
        super().setUp()
        self.commit_file("src/app.py", "x = 1\n", "second")
        os.makedirs(self.path("sub"))
        git(self.repo, "branch", "feat/9-existing")
        git(self.repo, "config", "alias.ci", "commit")
        git(self.repo, "config", "alias.ci2", "ci")
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        git(outside, "init", "-q", "-b", "main")
        git(outside, "commit", "-q", "--allow-empty", "-m", "init")

    def test_deny(self):
        for command in self.DENY:
            with self.subTest(command=command):
                result = guard(command, self.repo)
                self.assertIsNotNone(result, command)
                self.assertEqual(result[0], "deny")
                self.assertIn("Create a task branch with /loom:start-task", result[1])

    def test_allow(self):
        for command in self.ALLOW:
            with self.subTest(command=command):
                self.assertIsNone(guard(command, self.repo), command)

    def test_dollar_quote_and_quoted_heredoc_delimiters_parse(self):
        for command in ("echo $'it\\'s'; git commit -m x",
                        "cat > notes.md <<'END-MSG'\nit's a note\nEND-MSG\ngit commit -m x",
                        "cat > notes.md <<\\EOF\nit's\nEOF\ngit commit -m x"):
            with self.subTest(command=command):
                self.assertIsNotNone(loomhook_parse(command))
                result = guard(command, self.repo)
                self.assertEqual(result[0], "deny")
                self.assertNotIn("could not be parsed", result[1])

    def test_text_after_a_quoted_here_doc_marker_is_a_command(self):
        # `<<` inside quotes is not a here-doc: the next line is a real command.
        self.assertEqual(guard('echo "a << EOF"\ngit commit -m x\nEOF', self.repo)[0], "deny")


class GuardConservativeOnTaskBranchTest(RepoTestCase):
    """On a task branch whose previous branch is main."""

    DENY = [
        "git switch - && git commit -m x",
        "git checkout - && git commit -m x",
        "git checkout @{-1} && git commit -m x",
        "git checkout main -- && git commit -m x",
        "git symbolic-ref HEAD refs/heads/main && git commit -m x",
        "git symbolic-ref -m why HEAD refs/heads/main && git commit -m x",
        'echo "$(git push origin HEAD:main 2>&1)"',
        'x="$(git push origin HEAD:main 2>&1)"',
        "bash <<'EOF'\ngit push origin HEAD:main\nEOF",
        "timeout 60 git push origin main",
        "git push --repo=origin main",
        "git push --repo origin main",
        "git push origin :",
        "echo $'it\\'s'; git push origin HEAD:main",
        "cat > n.md <<'END-MSG'\nit's\nEND-MSG\ngit push origin HEAD:main",
        "git branch -m main && git commit -m x",
    ]
    ALLOW = [
        "git switch main && git pull && git switch - && git push -u origin feat/42-x",
        "git stash && git switch main && git pull && git switch - && git stash pop && git commit -m ok",
        "git switch main; git pull; git switch -c feat/43-y; git commit -m x",
        "git switch main && git pull && git switch feat/42-x && git commit -m x",
        "git checkout main -- README.md && git commit -m x",
        "git checkout main README.md && git commit -m x",
        "git commit -m 'fix: handle main branch'",
        'git commit -m "docs: explain git push origin main"',
        "cat <<'EOF' > doc.md\ngit push origin main\nEOF",
        "git switch --track origin/main; git commit -m x",  # git refuses: main exists locally
        "git push --dry-run origin main",
        "git push -n origin HEAD:main",
        "git push origin feat/42-x 2>&1 | tee push.log",
        "git push origin tag main",
        "B=main; git push origin \"HEAD:$B\"",  # a known limit: variables in a refspec
    ]

    def setUp(self):
        super().setUp()
        self.commit_file("src/app.py", "x = 1\n", "second")
        git(self.repo, "update-ref", "refs/remotes/origin/main", git(self.repo, "rev-parse", "HEAD"))
        git(self.repo, "switch", "-q", "-c", "feat/42-x")

    def test_deny(self):
        for command in self.DENY:
            with self.subTest(command=command):
                result = guard(command, self.repo)
                self.assertIsNotNone(result, command)
                self.assertEqual(result[0], "deny")

    def test_allow(self):
        for command in self.ALLOW:
            with self.subTest(command=command):
                self.assertIsNone(guard(command, self.repo), command)

    def test_no_previous_branch(self):
        # A fresh clone has no previous branch: `git switch -` fails and the branch stays main.
        fresh = os.path.join(self.tmp, "fresh")
        git(self.tmp, "clone", "-q", "--branch", "main", self.repo, fresh)
        self.assertEqual(guard("git switch -; git commit -m x", fresh)[0], "deny")
        self.assertIsNone(guard("git switch -c feat/2-y && git commit -m x", fresh))


class GuardPushFromMainTest(RepoTestCase):
    """On main, a push that cannot update the main branch is allowed (LOOM_SPEC.md 11.2)."""

    ALLOW = [
        "git push origin v1.0.0",
        "git push origin tag v1.0.0",
        "git push origin --tags",
        "git push --tags origin",
        "git push origin feat/9-x",
        "git push -u origin feat/9-x",
        "git push origin feat/9-x:feat/9-x",
        "git push origin HEAD:refs/heads/feat/9-x",
        "git push origin --delete feat/9-x",
        "git push origin :feat/9-x",
        "git push --follow-tags origin feat/9-x",
        "git push --dry-run",
        "git push -n",
        "git push -n origin main",
    ]
    DENY = [
        ("git push", "without a refspec"),
        ("git push origin", "without a refspec"),
        ("git push -u origin", "without a refspec"),
        ("git push --follow-tags", "without a refspec"),
        ("git push origin --follow-tags", "without a refspec"),
        ("git push origin HEAD", "(HEAD)"),
        ("git push origin main", "(main)"),
        ("git push origin --tags main", "(main)"),
        ("git push origin feat/9-x main", "(main)"),
        ("git push --all origin", "(--all)"),
        ("git push --mirror", "(--mirror)"),
        ("git push --branches origin", "(--branches)"),
        ("git push origin :", "(:)"),
        ('git push origin "$B"', "cannot be resolved"),
        ("git push origin $(echo feat/9-x)", "cannot be resolved"),
    ]

    def setUp(self):
        super().setUp()
        self.commit_file("src/app.py", "x = 1\n", "second")
        git(self.repo, "update-ref", "refs/remotes/origin/main", git(self.repo, "rev-parse", "HEAD"))
        git(self.repo, "branch", "feat/9-x")

    def test_allow(self):
        for command in self.ALLOW:
            with self.subTest(command=command):
                self.assertIsNone(guard(command, self.repo), command)

    def test_deny(self):
        for command, detail in self.DENY:
            with self.subTest(command=command):
                result = guard(command, self.repo)
                self.assertIsNotNone(result, command)
                self.assertEqual(result[0], "deny")
                self.assertIn(detail, result[1])
                self.assertIn("Create a task branch with /loom:start-task", result[1])

    def test_reason_text(self):
        self.assertEqual(guard("git push", self.repo)[1], (
            "git push of the main branch 'main' is blocked: without a refspec it pushes the current branch. "
            "On the main branch only a push that cannot update it is allowed (tags, other branches, --dry-run). "
            "Create a task branch with /loom:start-task"))


class GuardUnparsableFallbackTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.commit_file("src/app.py", "x = 1\n", "second")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")

    def test_push_to_main_from_a_task_branch_is_denied(self):
        for command in ("echo 'x; git push origin HEAD:main",
                        "echo 'x; git push -u origin main",
                        "echo 'x; git push origin +main",
                        "echo 'x; git push origin :main",
                        "echo 'x; git push origin refs/heads/main"):
            with self.subTest(command=command):
                self.assertIsNone(loomhook_parse(command))
                result = guard(command, self.repo)
                self.assertEqual(result[0], "deny")
                self.assertIn("could not be parsed", result[1])

    def test_other_pushes_and_commits_are_allowed(self):
        for command in ("echo 'x; git push origin feat/42-x",
                        "echo 'x; git push origin main-fixes",
                        "echo 'x; git commit -m main"):
            with self.subTest(command=command):
                self.assertIsNone(guard(command, self.repo))


class GuardRound2Test(RepoTestCase):
    """Review round 2: config aliases, git environment, `||`, brace groups, and cost."""

    def setUp(self):
        super().setUp()
        self.commit_file("src/app.py", "x = 1\n", "second")
        git(self.repo, "branch", "feat/9-x")
        git(self.repo, "update-ref", "refs/remotes/origin/main", git(self.repo, "rev-parse", "HEAD"))
        self.outside = os.path.join(self.tmp, "outside")
        os.makedirs(self.outside)
        git(self.outside, "init", "-q", "-b", "main")
        git(self.outside, "commit", "-q", "--allow-empty", "-m", "init")

    def on_task_branch(self):
        git(self.repo, "switch", "-q", "-c", "feat/42-x")

    def assert_deny(self, commands, cwd=None):
        for command in commands:
            with self.subTest(command=command):
                result = guard(command, cwd or self.repo)
                self.assertIsNotNone(result, command)
                self.assertEqual(result[0], "deny")

    def assert_allow(self, commands, cwd=None):
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(guard(command, cwd or self.repo), command)

    def test_command_line_aliases_on_main(self):
        self.assert_deny([
            "git -c alias.x=commit x -m y",
            "git -c 'alias.x=!git commit' x",
            "git -c alias.X=commit x -m y",  # alias names ignore case
            "git -c alias.x=ci -c alias.ci=commit x -m y",
            "git --config-env=alias.x=CMD x -m y",
            "git --config-env alias.x=CMD x -m y",
            "git -c alias.x=\"$CMD\" x -m y",
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0=commit git x -m y",
        ])
        self.assert_allow(["git -c alias.x=status x", "git -c alias.x=commit status",
                           "git -c alias.p=push p origin feat/9-x"])

    def test_command_line_aliases_on_a_task_branch(self):
        self.on_task_branch()
        self.assert_deny(["git -c alias.p=push p origin main", "git -c alias.p='push origin' p HEAD:main",
                          "git --config-env=alias.p=CMD p origin main"])
        self.assert_allow(["git -c alias.p=push p origin feat/42-x", "git -c alias.x=commit x -m y",
                           "git --config-env=alias.p=CMD p origin feat/42-x"])

    def test_git_environment_selects_the_repository(self):
        repo, gitdir = self.repo, os.path.join(self.repo, ".git")
        self.assert_deny([
            "cd /tmp && GIT_DIR=%s GIT_WORK_TREE=%s git commit -m x" % (gitdir, repo),
            "cd /tmp && GIT_DIR=%s git commit -m x" % gitdir,
            "env GIT_DIR=%s GIT_WORK_TREE=%s git commit -m x" % (gitdir, repo),
            "env -C %s git commit -m x" % repo,
            "env --chdir=%s git push" % repo,
            "export GIT_DIR=%s; git commit -m x" % gitdir,
        ], cwd=self.outside)
        self.assert_deny(['cd ../outside && GIT_DIR="$D" git commit -m x'])  # unresolvable: the original cwd
        self.assert_allow(["GIT_DIR=%s git commit -m x" % os.path.join(self.outside, ".git"),
                           "env -C %s git commit -m x" % self.outside])

    def test_right_side_of_or_runs_after_a_failed_switch(self):
        self.assert_deny([
            "git switch feat/9-x || git commit -m x",
            "git switch -c feat/1-new || git commit -m x",
            "git switch -c feat/1-new && git switch -c feat/2-new || git commit -m x",
            "git switch feat/9-x ||\ngit commit -m x",
        ])
        self.assert_allow([
            "git switch -c feat/1-new && git commit -m x || true",
            "git switch -c feat/1-new || exit 1; git commit -m x",
            "git switch feat/9-x && git commit -m x",
        ])
        self.on_task_branch()
        self.assert_deny(["git switch main && git switch -c feat/3-y || git commit -m x"])

    def test_brace_group_runs_in_the_current_shell(self):
        self.assert_allow(["{ cd ../outside; } && git commit -m x"])
        self.assert_deny(["{ git commit -m x; }", "true && { git push; }", "( cd ../outside ); git commit -m x",
                          "{ cd ../outside; } | true; git commit -m x"])

    def test_cost_stays_linear(self):
        # A timeout of the hook (10 seconds) lets the command run: adversarial input must stay cheap.
        import time
        commands = [
            "git a " * 34000 + "'",
            "git " * 50000 + "'",
            "git x commit " * 16000 + "'",
            "git push origin x " * 12000 + "'",
            " ; ".join(["echo $(echo $(echo $(echo $(echo $(git status)))))"] * 2000),
            "; ".join(["git checkout feat/9-x", "git push origin feat/9-x", "git commit -m x",
                       "git checkout main"] * 250),
        ]
        for branch in ("main", "feat/42-x"):
            if branch != "main":
                self.on_task_branch()
            for command in commands:
                with self.subTest(branch=branch, command=command[:40]):
                    started = time.time()
                    proc = run_hook(GUARD, bash_payload(command, self.repo))
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(proc.stderr, "")
                    self.assertLess(time.time() - started, 3.0)


# ---------------------------------------------------------------------------
# Hardening: output filtering
# ---------------------------------------------------------------------------


def filtered(command, cwd):
    return decision(run_hook(FILTER, bash_payload(command, cwd)))


class OutputFilteringHardeningTest(RepoTestCase):
    DENY = [
        "make check | rg FAILED",
        "make check | wc -l",
        "(make check) | tail",
        "(make check 2>&1) | tail -20",
        "(cd app && pytest) | tail",
        "timeout 600 make check 2>&1 | tail -20",
        "timeout 600 pytest -q | tail",
        "nice -n 5 pytest | tail",
        "pnpm test | tail",
        "pnpm run lint | head",
        "pnpm typecheck | head",
        "yarn test | tail",
        "yarn run typecheck | head",
        "bun test | tail",
        "bun run test | tail",
        'result="$(make check 2>&1 | tail -20)"; echo "$result"',
        'echo "$(pytest -q | tail -5)"',
        "bash -o pipefail -c 'pytest | tail'",
        "{ make check; } 2>&1 | tail",
        "{ pytest -q; } | tail -5",
        "true && { make lint 2>&1; } | head",
        "bash -c 'make check' | head",
        "sh -c \"pytest -q\" 2>&1 | tail",
    ]
    ALLOW = [
        "command -v pytest | head",
        "command -V pytest | head -1",
        "which pytest | head",
        "type pytest | head",
        "{ ls; } | head",
        "bash -c 'ls' | head",
        "pytest --version | head -1",
        "ruff --version | cut -d' ' -f2",
        "mypy --help | grep strict",
        "pytest -h | grep strict",
        "make -n check | head",
        "make --dry-run check | head",
        "pytest --collect-only -q | grep test_login",
        "python -m pytest --co | grep test_login",
        "make check | tee check.log",
        "rg pattern src | head",
        "wc -l src/*.py | tail -1",
        "bun run build | tail",
    ]

    def test_deny(self):
        for command in self.DENY:
            with self.subTest(command=command):
                result = filtered(command, self.repo)
                self.assertIsNotNone(result, command)
                self.assertEqual(result[0], "deny")

    def test_allow(self):
        for command in self.ALLOW:
            with self.subTest(command=command):
                self.assertIsNone(filtered(command, self.repo), command)


class ConfiguredCheckWithFilterTest(RepoTestCase):
    """A configured check runs exactly as configured, even with a filter (LOOM_SPEC.md 9.0, 11.3)."""

    loom_config = {"checks": {"lint": "golangci-lint run", "typecheck": None,
                              "test": "go test ./... | grep -v 'no test files'",
                              "check": "npm ci && npm run check"}}

    def test_configured_command_runs(self):
        for command in ("go test ./... | grep -v 'no test files'",
                        "  go test ./...   |  grep -v 'no test files'  ",
                        "npm ci && npm run check"):
            with self.subTest(command=command):
                self.assertIsNone(filtered(command, self.repo))

    def test_filter_and_setup_stages_are_not_checks(self):
        for command in ("grep -v 'no test files' out.txt | head", "npm ci 2>&1 | tail -5",
                        "npm ci --silent | tail"):
            with self.subTest(command=command):
                self.assertIsNone(filtered(command, self.repo))

    def test_the_checks_themselves_stay_guarded(self):
        for command in ("go test ./... | tail", "golangci-lint run | head", "npm run check | tail",
                        "go test ./... | grep -v 'no test files' | head"):
            with self.subTest(command=command):
                self.assertEqual(filtered(command, self.repo)[0], "deny")


# ---------------------------------------------------------------------------
# Hardening: SessionStart, hooks.json, status line
# ---------------------------------------------------------------------------


class SessionStartWarningsTest(RepoTestCase):
    loom_config = {"docs": {"nope": "x"}}

    def payload(self):
        return {"session_id": "s", "transcript_path": "/tmp/t", "cwd": self.repo,
                "hook_event_name": "SessionStart", "source": "fork"}

    def test_warnings_on_main(self):
        lines = run_hook(SESSION, self.payload()).stdout.strip().splitlines()
        self.assertIn("/loom:start-task", lines[0])
        self.assertTrue(any(line.startswith("Warning: ") and "docs.nope" in line for line in lines[1:]), lines)

    def test_warnings_on_a_branch_without_a_task(self):
        git(self.repo, "switch", "-q", "-c", "spike/x")
        lines = run_hook(SESSION, self.payload()).stdout.strip().splitlines()
        self.assertIn("matches no task", lines[0])
        self.assertTrue(any("docs.nope" in line for line in lines[1:]), lines)

    def test_no_warning_lines_without_warnings(self):
        self.write_config({})
        self.assertEqual(len(run_hook(SESSION, self.payload()).stdout.strip().splitlines()), 1)


class SessionStartMatcherTest(unittest.TestCase):
    def test_fork_is_matched(self):
        from loomtest import ROOT
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as fh:
            entry = json.load(fh)["hooks"]["SessionStart"][0]
        self.assertEqual(entry["matcher"].split("|"), ["startup", "resume", "clear", "compact", "fork"])


class StatuslineMalformedInstallsTest(RepoTestCase):
    """A malformed installed_plugins.json falls through to the marketplace and the cache."""

    def setUp(self):
        super().setUp()
        import sys
        from loomtest import ROOT
        self.python = sys.executable
        self.script = os.path.join(ROOT, "skills", "setup", "references", "templates", "loom-statusline.py")
        self.loom_state = os.path.join(ROOT, "bin", "loom-state")
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")
        self.ticket(self.task_dir("42-auth-flow"), mode="full")
        self.root = os.path.join(self.tmp, "plugins")
        os.makedirs(self.root)

    def plugin(self, path):
        os.makedirs(os.path.join(path, "bin"), exist_ok=True)
        shutil.copy(self.loom_state, os.path.join(path, "bin", "loom-state"))
        return path

    def run_script(self):
        import subprocess
        env = {k: v for k, v in os.environ.items() if k not in ("LOOM_PLUGIN_ROOT", "CLAUDE_CONFIG_DIR")}
        env["CLAUDE_CODE_PLUGIN_CACHE_DIR"] = self.root
        return subprocess.run([self.python, self.script], input=json.dumps({"cwd": self.repo}), cwd=self.tmp,
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def test_falls_through(self):
        market = self.plugin(os.path.join(self.tmp, "marketplaces", "loom"))
        with open(os.path.join(self.root, "known_marketplaces.json"), "w") as fh:
            json.dump({"loom": {"installLocation": market}}, fh)
        for installs in ({"plugins": []}, {"plugins": {"loom@loom": [{"installPath": 5, "projectPath": []}]}},
                         {"plugins": {"loom@loom": {"installPath": "/x"}}}, [1, 2]):
            with self.subTest(installs=installs):
                with open(os.path.join(self.root, "installed_plugins.json"), "w") as fh:
                    json.dump(installs, fh)
                proc = self.run_script()
                self.assertEqual((proc.returncode, proc.stderr), (0, ""))
                self.assertIn("#42", proc.stdout)

    def test_falls_through_to_the_cache(self):
        self.plugin(os.path.join(self.root, "cache", "loom", "loom", "0.1.0"))
        with open(os.path.join(self.root, "installed_plugins.json"), "w") as fh:
            json.dump({"plugins": "broken"}, fh)
        with open(os.path.join(self.root, "known_marketplaces.json"), "w") as fh:
            json.dump({"loom": {"installLocation": ["broken"]}}, fh)
        self.assertIn("#42", self.run_script().stdout)


if __name__ == "__main__":
    unittest.main()
