"""Tests for `loom-state --setup-path <main>` and the pure setup_path() (LOOM_SPEC.md 8.2, 9.13.1)."""
from __future__ import annotations

import copy
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from loomtest import RepoTestCase, git, loom_state, run_loom_state, run_loom_state_env, write

ls = loom_state()
setup_path = ls.setup_path

PATHS = ("switch", "rerun", "fast", "onboarding", "onboarding-rerun", "fast-resume")
SETUP = "chore/3-loom-setup"
KICKOFF = "chore(loom): start loom setup (#3)"
NON_CODE = ["README.md", "LICENSE", ".gitignore", ".gitattributes", ".editorconfig", "CODEOWNERS", "SECURITY.md",
            "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", ".github/ISSUE_TEMPLATE/bug.md",
            ".github/pull_request_template.md"]
CODE = ["src/app.py", "Makefile"]
NO_FOUND = {"instructionFiles": [], "workflows": [], "prTemplates": [], "docsDirs": []}


def facts(branch: Optional[str] = "main", main_files: Optional[List[str]] = None, **extra: Any) -> Dict[str, Any]:
    """Facts on `branch` with origin/main tracking `main_files` (None: no commits); no commits of its own."""
    base: Dict[str, Any] = {
        "branch": branch, "localSetupBranches": [], "originSetupBranches": [],
        "mainRef": None if main_files is None else "origin/main", "mainFiles": list(main_files or []),
        "ticketFound": False, "ticketMode": None, "branchSubjects": [], "noOwnCommits": True,
        "configInWorkingTree": False,
    }
    base.update(extra)
    return base


class SetupPathFunctionTest(unittest.TestCase):
    """setup_path() with plain dicts: every row of the path table, first match wins."""

    def assertPath(self, f: Dict[str, Any], path: str, reason_part: str = "") -> Dict[str, Any]:
        before = copy.deepcopy(f)
        result = setup_path(f)
        self.assertEqual(f, before, "setup_path must not mutate its input")
        self.assertEqual(set(result), {"path", "reason", "setupBranches", "codeFiles", "found"})
        self.assertIn(result["path"], PATHS)
        self.assertEqual(result["path"], path, result)
        self.assertNotIn("\n", result["reason"])
        if reason_part:
            self.assertIn(reason_part, result["reason"])
        return result

    # Row 1: not on a setup branch, a setup branch exists.
    def test_row1_switch(self):
        r = self.assertPath(facts(localSetupBranches=[SETUP]), "switch", SETUP)
        self.assertEqual(r["setupBranches"], [SETUP])
        r = self.assertPath(facts(localSetupBranches=["chore/12-loom-setup", SETUP]), "switch", "chore/12-loom-setup")
        self.assertEqual(r["setupBranches"], [SETUP, "chore/12-loom-setup"])
        r = self.assertPath(facts(main_files=CODE, originSetupBranches=[SETUP]), "switch", SETUP)
        self.assertEqual(r["setupBranches"], [SETUP])
        r = self.assertPath(facts(localSetupBranches=[SETUP], originSetupBranches=[SETUP, "chore/9-loom-setup"]),
                            "switch")
        self.assertEqual(r["setupBranches"], [SETUP, "chore/9-loom-setup"])

    def test_row1_local_branch_beats_rerun_and_the_first_table(self):
        f = facts(main_files=[".claude/loom.json"] + CODE, localSetupBranches=[SETUP])
        self.assertPath(f, "switch")
        self.assertPath(facts(branch=None, localSetupBranches=[SETUP]), "switch")

    def test_row1_origin_only_branch_is_stale_once_main_has_loom_json(self):
        f = facts(main_files=[".claude/loom.json"] + CODE, originSetupBranches=[SETUP])
        r = self.assertPath(f, "rerun")
        self.assertEqual(r["setupBranches"], [SETUP])  # still listed
        f = facts(main_files=[".claude/loom.json"], localSetupBranches=["chore/9-loom-setup"],
                  originSetupBranches=[SETUP])
        r = self.assertPath(f, "switch", "chore/9-loom-setup")
        self.assertNotIn(SETUP, r["reason"])
        self.assertEqual(r["setupBranches"], [SETUP, "chore/9-loom-setup"])

    # Row 2: the main ref has .claude/loom.json.
    def test_row2_rerun(self):
        self.assertPath(facts(main_files=[".claude/loom.json"] + CODE), "rerun", "origin/main has .claude/loom.json")
        self.assertPath(facts(main_files=[".claude/loom.json"]), "rerun")
        self.assertPath(facts(main_files=["README.md", ".claude/loom.json"], mainRef="main"), "rerun",
                        "main has .claude/loom.json")

    def test_row2_needs_the_file_at_the_top_level(self):
        self.assertPath(facts(main_files=["pkg/.claude/loom.json"]), "onboarding")
        self.assertPath(facts(main_files=[".claude/loom.jsonc"]), "onboarding")

    # Row 3: the first table.
    def test_row3_no_commits_is_fast(self):
        r = self.assertPath(facts(main_files=None), "fast", "the repository has no commits")
        self.assertEqual((r["codeFiles"], r["found"], r["setupBranches"]), (0, NO_FOUND, []))
        # mainFiles without a mainRef are never read.
        self.assertPath(facts(main_files=None, mainFiles=CODE), "fast")

    def test_row3_only_files_that_are_not_code_is_fast(self):
        r = self.assertPath(facts(main_files=NON_CODE), "fast", "origin/main tracks only files that are not code")
        self.assertEqual(r["codeFiles"], 0)
        self.assertPath(facts(main_files=["readme.md", "License", ".GitHub/FUNDING.yml"]), "fast")
        self.assertPath(facts(main_files=[]), "fast", "origin/main tracks no files")

    def test_row3_code_is_onboarding(self):
        files = NON_CODE + ["src/app.py", "src/util.py", ".github/workflows/ci.yml"]
        r = self.assertPath(facts(main_files=files), "onboarding")
        self.assertEqual(r["reason"], "origin/main tracks 3 files that count as code (first: src/app.py)")
        self.assertEqual(r["codeFiles"], 3)
        r = self.assertPath(facts(main_files=["README.md", "main.go"], mainRef="main"), "onboarding")
        self.assertEqual(r["reason"], "main tracks 1 file that counts as code (first: main.go)")

    def test_branches_that_are_not_setup_branches(self):
        for branch in ("main", None, "feat/3-loom-setup", "chore/3-loom-setup-task", "chore/x-loom-setup",
                       "chore/3-loom-setup/x", "fix/3-x", "chore/٣-loom-setup", "chore/３-loom-setup"):
            with self.subTest(branch=branch):
                f = facts(branch=branch, main_files=CODE, ticketMode="full", branchSubjects=[KICKOFF])
                self.assertPath(f, "onboarding")

    # Row 4: on a setup branch, the ticket has mode full.
    def test_row4_onboarding_rerun(self):
        f = facts(branch=SETUP, main_files=NON_CODE, ticketFound=True, ticketMode="full")
        self.assertPath(f, "onboarding-rerun", "mode full")
        # First match: also at the main tip without loom.json (row 6), and with setup branches listed.
        f = facts(branch=SETUP, main_files=None, ticketFound=True, ticketMode="full", localSetupBranches=[SETUP])
        r = self.assertPath(f, "onboarding-rerun")
        self.assertEqual(r["setupBranches"], [SETUP])

    def test_row4_needs_mode_full(self):
        for mode in ("oneshot", "quick"):
            with self.subTest(mode=mode):
                f = facts(branch=SETUP, main_files=CODE, ticketFound=True, ticketMode=mode,
                          branchSubjects=["chore(loom): set up loom (#3)"], noOwnCommits=False)
                self.assertPath(f, "fast-resume")

    # Row 5: the ticket is missing or its mode is not full, and the branch has the kickoff commit.
    def test_row5_kickoff_commit(self):
        f = facts(branch=SETUP, main_files=CODE, branchSubjects=[KICKOFF], noOwnCommits=False,
                  configInWorkingTree=True)
        self.assertPath(f, "onboarding-rerun", "the ticket is missing")
        f = facts(branch=SETUP, main_files=CODE, ticketFound=True, branchSubjects=["later", KICKOFF],
                  noOwnCommits=False)
        self.assertPath(f, "onboarding-rerun", "the ticket has no valid mode")

    def test_row5_any_mode_other_than_full(self):
        for mode in ("oneshot", "quick"):
            with self.subTest(mode=mode):
                f = facts(branch=SETUP, main_files=CODE, ticketFound=True, ticketMode=mode, branchSubjects=[KICKOFF],
                          noOwnCommits=False, configInWorkingTree=True)
                self.assertPath(f, "onboarding-rerun", "the ticket has mode %s" % mode)

    def test_row5_needs_the_exact_subject_of_this_issue(self):
        for subject in ("chore(loom): start loom setup (#4)", "chore(loom): start loom setup", KICKOFF + " again",
                        "chore(loom): set up loom (#3)"):
            with self.subTest(subject=subject):
                f = facts(branch=SETUP, main_files=CODE, branchSubjects=[subject], noOwnCommits=False)
                self.assertPath(f, "fast-resume")

    def test_row4_not_with_the_fast_setup_commit(self):
        # A ticket edited by hand to full on a branch that holds the fast setup commit stays on the fast path.
        fast = "chore(loom): set up loom (#3)"
        f = facts(branch=SETUP, main_files=CODE, ticketFound=True, ticketMode="full", branchSubjects=[fast],
                  noOwnCommits=False, configInWorkingTree=True)
        self.assertPath(f, "fast-resume", "commits of its own")
        # Rows 5-7 decide: the kickoff subject still gives the onboarding re-run.
        f = dict(f, branchSubjects=[fast, KICKOFF])
        self.assertPath(f, "onboarding-rerun", "the ticket has mode full")
        # Only this issue's fast setup subject counts.
        f = dict(f, branchSubjects=["chore(loom): set up loom (#4)"])
        self.assertPath(f, "onboarding-rerun")

    # Row 6: HEAD has no commit of its own (or no commits) and no .claude/loom.json: the first table.
    def test_row6_stopped_after_switch(self):
        r = self.assertPath(facts(branch=SETUP, main_files=CODE), "onboarding", "setup stopped after git switch -c")
        self.assertIn("first: src/app.py", r["reason"])
        self.assertPath(facts(branch=SETUP, main_files=NON_CODE), "fast", "only files that are not code")
        self.assertPath(facts(branch=SETUP, main_files=None), "fast", "no commits")
        # A ticket without a valid mode does not change row 6.
        self.assertPath(facts(branch=SETUP, main_files=CODE, ticketFound=True), "onboarding")
        # HEAD at the tip of a local main that is ahead of origin/main: the span is not empty.
        f = facts(branch=SETUP, main_files=CODE, branchSubjects=["local main commit"], noOwnCommits=True)
        self.assertPath(f, "onboarding")

    def test_row6_branch_behind_a_main_that_moved_on(self):
        # Cut, no commit, then main moved on: HEAD is an ancestor of the main tip.
        f = facts(branch=SETUP, main_files=CODE, branchSubjects=[], noOwnCommits=True)
        self.assertPath(f, "onboarding", "has no commit of its own")

    def test_row6_needs_no_commits_of_its_own(self):
        self.assertPath(facts(branch=SETUP, main_files=CODE, noOwnCommits=False), "fast-resume",
                        "commits of its own")
        self.assertPath(facts(branch=SETUP, main_files=CODE, noOwnCommits=None), "fast-resume")

    # Row 7: otherwise.
    def test_row7_fast_resume(self):
        # Stopped on failing checks: no commit, no ticket, but .claude/loom.json in the working tree.
        r = self.assertPath(facts(branch=SETUP, main_files=CODE, configInWorkingTree=True), "fast-resume",
                            ".claude/loom.json in the working tree")
        self.assertEqual(r["codeFiles"], 2)
        f = facts(branch=SETUP, main_files=NON_CODE, branchSubjects=["chore(loom): set up loom (#3)"],
                  noOwnCommits=False, configInWorkingTree=True)
        self.assertPath(f, "fast-resume", "commits of its own, .claude/loom.json in the working tree")

    def test_empty_facts(self):
        self.assertPath({}, "fast")


class NonCodeFilesTest(unittest.TestCase):
    def test_files_that_are_not_code(self):
        for path in NON_CODE + ["README", "README.rst", "LICENSE.txt", "LICENSE-MIT", ".github/CODEOWNERS",
                                ".github/dependabot.yml", ".github/FUNDING.yml", ".github/workflows-old/x.yml",
                                "readme.md", "Readme.MD", "License", "license-apache", "codeowners", "Security.md",
                                "Contributing.md", ".GitIgnore", ".GITHUB/x.md"]:
            with self.subTest(path=path):
                self.assertFalse(ls.is_code_file(path))

    def test_files_that_count_as_code(self):
        for path in CODE + [".github/workflows/ci.yml", ".github/workflows/sub/x.yaml", ".github/workflows",
                            ".github/Workflows/ci.yml", "src/README.md", "docs/LICENSE", "pkg/readme.md",
                            ".githubx/a", "github/x.md", ".claude/loom.json", "docs/index.md", ".gitmodules",
                            "SECURITY.txt", "AGENTS.md"]:
            with self.subTest(path=path):
                self.assertTrue(ls.is_code_file(path))


class FoundPathsTest(unittest.TestCase):
    def test_found(self):
        files = [
            ".claude/rules/a.md", ".claude/rules/sub/b.md", ".cursor/rules/x.mdc", ".cursorrules",
            ".github/PULL_REQUEST_TEMPLATE/feature.md", ".github/copilot-instructions.md",
            ".github/instructions/py.instructions.md", ".github/instructions/ts.instructions.md",
            ".github/pull_request_template.md", ".github/workflows/ci.yml", ".github/workflows/release.yaml",
            ".github/workflows/notes.txt", ".github/workflows/sub/x.yml",
            "ADR/0001-x.md", "AGENTS.md", "CLAUDE.local.md", "CLAUDE.md", "Docs/a.md", "GEMINI.md",
            "PULL_REQUEST_TEMPLATE.md", "doc/x.md", "docs/adr/0001-x.md", "docs/architecture/Decisions/0001-y.md",
            "docs/pull_request_template.md", "pkg/.claude/CLAUDE.md", "pkg/AGENTS.md", "pkg/docs/a.md",
            "src/agents.md", "src/app.py", "src/docs.py", "src/pull_request_template.md",
        ]
        self.assertEqual(ls.found_paths(files), {
            "instructionFiles": [".cursorrules", "AGENTS.md", "CLAUDE.local.md", "CLAUDE.md", "GEMINI.md",
                                 ".claude/rules", ".cursor/rules", ".github/copilot-instructions.md",
                                 ".github/instructions", "pkg/AGENTS.md", "pkg/.claude/CLAUDE.md"],
            "workflows": [".github/workflows/ci.yml", ".github/workflows/release.yaml"],
            "prTemplates": ["PULL_REQUEST_TEMPLATE.md", ".github/pull_request_template.md",
                            "docs/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE/feature.md"],
            "docsDirs": ["ADR", "Docs", "doc", "docs", "docs/adr", "pkg/docs", "docs/architecture/Decisions"],
        })

    def test_at_most_20_paths_per_list_fewest_segments_first(self):
        files = ["p%02d/q/AGENTS.md" % i for i in range(15)] + ["p%02d/AGENTS.md" % i for i in range(15)]
        files += ["AGENTS.md", "z/docs/x.md"] + ["d%02d/docs/x.md" % i for i in range(25)] + ["docs/x.md"]
        found = ls.found_paths(files)
        self.assertEqual(found["instructionFiles"],
                         ["AGENTS.md"] + ["p%02d/AGENTS.md" % i for i in range(15)] +
                         ["p%02d/q/AGENTS.md" % i for i in range(4)])
        self.assertEqual(found["docsDirs"], ["docs"] + ["d%02d/docs" % i for i in range(19)])
        many = ["src/m%03d.py" % i for i in range(5000)] + ["docs/%d.md" % i for i in range(5000)]
        self.assertEqual(ls.found_paths(many)["docsDirs"], ["docs"])

    def test_nothing_found(self):
        self.assertEqual(ls.found_paths([]), NO_FOUND)
        self.assertEqual(ls.found_paths(["src/app.py", "docs"]), NO_FOUND)


class SetupPathRepoTest(RepoTestCase):
    """`--setup-path main` on fixture repositories; no .claude/loom.json unless a test writes one."""

    loom_config = None
    initial_commit = False

    def setUp(self) -> None:
        super().setUp()
        os.remove(self.path(".gitignore"))
        self.remote = os.path.join(self.tmp, "origin.git")

    def commit(self, files: Dict[str, str], message: str = "change") -> None:
        for rel, text in files.items():
            write(self.path(*rel.split("/")), text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)

    def add_origin(self, push: bool = True) -> None:
        git(self.tmp, "init", "-q", "--bare", "-b", "main", self.remote)
        git(self.repo, "remote", "add", "origin", self.remote)
        if push:
            git(self.repo, "push", "-q", "-u", "origin", "main")

    def code_repo(self) -> None:
        self.commit({"README.md": "# x\n", ".gitignore": ".loom/\n", "src/app.py": "x = 1\n",
                     "AGENTS.md": "rules\n", ".github/workflows/ci.yml": "on: push\n", "docs/index.md": "x\n",
                     ".github/pull_request_template.md": "## Summary\n"}, "initial")
        self.add_origin()

    def new_repo(self) -> None:
        self.commit({"README.md": "# x\n", ".gitignore": ".loom/\n", "LICENSE": "MIT\n"}, "initial")
        self.add_origin()

    def run_setup_path(self, cwd: str, *args: str) -> subprocess.CompletedProcess:
        """Run --setup-path; stdout and stderr decoded as UTF-8 whatever the locale."""
        proc = run_loom_state_env(cwd, {}, "--setup-path", *args)
        proc.stdout = proc.stdout.decode("utf-8")
        proc.stderr = proc.stderr.decode("utf-8")
        return proc

    def setup_path(self, cwd: Optional[str] = None, main: str = "main") -> Dict[str, Any]:
        proc = self.run_setup_path(cwd or self.repo, main)
        self.assertEqual((proc.returncode, proc.stderr), (0, ""), proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual(set(data), {"path", "reason", "setupBranches", "codeFiles", "found"})
        return data

    def ticket(self, mode: str = "full", work_dir: str = ".loom/tasks", dirname: str = "3-loom-setup") -> None:  # type: ignore[override]
        write(self.path(work_dir, dirname, "00-ticket.md"),
              "---\ntask: 3-loom-setup\nphase: ticket\nmode: %s\nsize: M\nissue: 3\n---\n# Set up loom\n" % mode)

    def kickoff(self) -> None:
        """The onboarding kickoff on the setup branch: minimal loom.json, kickoff commit."""
        self.commit({".claude/loom.json": '{"version": 1, "mainBranch": "main"}\n'}, KICKOFF)

    # Rows 1-3: not on a setup branch.
    def test_row1_switch_local_remote_and_both(self):
        self.code_repo()
        git(self.repo, "branch", SETUP)
        data = self.setup_path()
        self.assertEqual((data["path"], data["setupBranches"]), ("switch", [SETUP]))
        git(self.repo, "push", "-q", "origin", SETUP)
        self.assertEqual(self.setup_path()["setupBranches"], [SETUP])  # local and remote: listed once
        git(self.repo, "branch", "-q", "-D", SETUP)
        data = self.setup_path()  # a fresh clone has only the remote branch
        self.assertEqual((data["path"], data["setupBranches"]), ("switch", [SETUP]))
        git(self.repo, "branch", "chore/12-loom-setup")
        git(self.repo, "branch", "chore/4-loom-setup-task")
        git(self.repo, "branch", "feat/5-loom-setup")
        self.assertEqual(self.setup_path()["setupBranches"], [SETUP, "chore/12-loom-setup"])

    def test_row1_stale_remote_setup_branch_after_the_merge(self):
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        self.kickoff()
        git(self.repo, "push", "-q", "origin", SETUP)
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "merge", "-q", "--ff-only", SETUP)
        git(self.repo, "push", "-q", "origin", "main")
        self.assertEqual(self.setup_path()["path"], "switch")  # the local branch still counts
        git(self.repo, "branch", "-q", "-D", SETUP)  # deleted locally; origin/chore/3-loom-setup not pruned
        data = self.setup_path()
        self.assertEqual((data["path"], data["setupBranches"]), ("rerun", [SETUP]))

    def test_row2_rerun(self):
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", "chore/2-x")
        self.commit({".claude/loom.json": "{}\n"}, "add loom")
        git(self.repo, "switch", "-q", "main")
        self.assertEqual(self.setup_path()["path"], "onboarding")  # origin/main has no loom.json yet
        git(self.repo, "merge", "-q", "--ff-only", "chore/2-x")
        self.assertEqual(self.setup_path()["path"], "onboarding")  # only the local main has it
        git(self.repo, "push", "-q", "origin", "main")
        data = self.setup_path()
        self.assertEqual(data["path"], "rerun")
        self.assertIn("origin/main has .claude/loom.json", data["reason"])

    def test_row2_rerun_from_the_local_main_without_origin(self):
        self.commit({"README.md": "# x\n", ".claude/loom.json": "{}\n"}, "initial")
        data = self.setup_path()
        self.assertEqual(data["path"], "rerun")
        self.assertIn("main has .claude/loom.json", data["reason"])

    def test_row3_onboarding(self):
        self.code_repo()
        data = self.setup_path()
        self.assertEqual(data, {
            "path": "onboarding",
            "reason": "origin/main tracks 4 files that count as code (first: .github/workflows/ci.yml)",
            "setupBranches": [], "codeFiles": 4,
            "found": {"instructionFiles": ["AGENTS.md"], "workflows": [".github/workflows/ci.yml"],
                      "prTemplates": [".github/pull_request_template.md"], "docsDirs": ["docs"]},
        })

    def test_row3_fast(self):
        self.new_repo()
        data = self.setup_path()
        self.assertEqual((data["path"], data["codeFiles"]), ("fast", 0))
        self.assertIn("origin/main tracks only files that are not code", data["reason"])

    def test_row3_reads_origin_main_not_the_local_main(self):
        self.new_repo()
        self.commit({"src/app.py": "x = 1\n"}, "local only")
        self.assertEqual(self.setup_path()["path"], "fast")
        git(self.repo, "push", "-q", "origin", "main")
        self.assertEqual(self.setup_path()["path"], "onboarding")

    def test_row3_local_main_when_origin_has_none(self):
        self.commit({"README.md": "# x\n", "src/app.py": "x = 1\n"}, "initial")
        self.add_origin(push=False)
        data = self.setup_path()
        self.assertEqual(data["path"], "onboarding")
        self.assertTrue(data["reason"].startswith("main tracks 1 file that counts as code"), data["reason"])

    def test_row3_no_commits(self):
        data = self.setup_path()
        self.assertEqual((data["path"], data["codeFiles"], data["setupBranches"]), ("fast", 0, []))
        self.assertIn("the repository has no commits", data["reason"])
        write(self.path("src", "app.py"), "x = 1\n")  # untracked files are not tracked by main
        self.assertEqual(self.setup_path()["path"], "fast")
        self.add_origin(push=False)
        self.assertEqual(self.setup_path()["path"], "fast")
        self.assertEqual(self.setup_path(main="trunk")["path"], "fast")  # no commits: no main ref needed

    def test_main_branch_argument(self):
        self.commit({"src/app.py": "x = 1\n"}, "initial")
        git(self.repo, "branch", "-m", "trunk")
        self.assertEqual(self.setup_path(main="trunk")["path"], "onboarding")
        proc = self.run_setup_path(self.repo, "main")  # commits, but no branch main: exit 1
        self.assertEqual((proc.returncode, proc.stdout), (1, ""))
        self.assertIn("'main' exists neither locally nor on origin", proc.stderr)

    def test_missing_main_while_head_has_no_commit(self):
        self.commit({"src/app.py": "x = 1\n"}, "initial")
        git(self.repo, "branch", "-m", "trunk")
        git(self.repo, "switch", "-q", "--orphan", "fresh")  # HEAD unborn, but trunk has a commit
        proc = self.run_setup_path(self.repo, "main")
        self.assertEqual((proc.returncode, proc.stdout), (1, ""))
        self.assertIn("'main' exists neither locally nor on origin", proc.stderr)
        self.assertEqual(self.setup_path(main="trunk")["path"], "onboarding")

    # Rows 4-7: on a setup branch.
    def test_row4_ticket_with_mode_full(self):
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        self.ticket("full")
        data = self.setup_path()  # before the kickoff commit, without loom.json
        self.assertEqual((data["path"], data["setupBranches"]), ("onboarding-rerun", [SETUP]))
        self.kickoff()
        self.assertEqual(self.setup_path()["path"], "onboarding-rerun")
        self.ticket(" Full ")
        self.assertEqual(self.setup_path()["path"], "onboarding-rerun")

    def test_row4_fast_setup_commit_with_a_ticket_edited_to_full(self):
        self.new_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        self.ticket("full")
        self.commit({".claude/loom.json": "{}\n", "Makefile": "check:\n"}, "chore(loom): set up loom (#3)")
        data = self.setup_path()
        self.assertEqual(data["path"], "fast-resume")
        self.assertIn("commits of its own", data["reason"])

    def test_row4_ticket_below_the_configured_work_dir(self):
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        self.ticket("full", work_dir="work/tasks")
        self.assertEqual(self.setup_path()["path"], "onboarding")  # the default workDir has no ticket
        write(self.path(".claude", "loom.json"), '{"workDir": "work/tasks"}\n')
        self.assertEqual(self.setup_path()["path"], "onboarding-rerun")

    def test_row4_archived_ticket_does_not_count(self):
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        self.ticket("full", work_dir=".loom/tasks/_archive")
        self.assertEqual(self.setup_path()["path"], "onboarding")  # row 6, not row 4
        self.ticket("full", dirname="3-renamed")  # the active directory, matched by number
        self.assertEqual(self.setup_path()["path"], "onboarding-rerun")

    def test_row5_fresh_clone(self):
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        self.ticket("full")
        self.kickoff()
        git(self.repo, "push", "-q", "origin", SETUP)
        clone = os.path.join(self.tmp, "clone")
        git(self.tmp, "clone", "-q", self.remote, clone)
        git(clone, "switch", "-q", SETUP)
        self.assertFalse(os.path.exists(os.path.join(clone, ".loom")))  # the task directory is ignored
        data = self.setup_path(clone)
        self.assertEqual(data["path"], "onboarding-rerun")
        self.assertIn("the ticket is missing", data["reason"])
        ticket = os.path.join(clone, ".loom", "tasks", "3-loom-setup", "00-ticket.md")
        for mode, reason in (("huge", "no valid mode"), ("oneshot", "mode oneshot"), ("quick", "mode quick")):
            with self.subTest(mode=mode):
                write(ticket, "---\nmode: %s\n---\n" % mode)
                data = self.setup_path(clone)
                self.assertEqual(data["path"], "onboarding-rerun")
                self.assertIn(reason, data["reason"])

    def test_row5_reads_the_span_from_origin_main(self):
        # The local main was fast-forwarded to the setup branch (not pushed): main..HEAD is empty,
        # origin/main..HEAD has the kickoff commit.
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        self.kickoff()
        git(self.repo, "branch", "-f", "main", SETUP)
        data = self.setup_path()
        self.assertEqual(data["path"], "onboarding-rerun")
        self.assertIn("the ticket is missing", data["reason"])

    def test_row6_stopped_after_switch(self):
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        data = self.setup_path()
        self.assertEqual(data["path"], "onboarding")
        self.assertIn("setup stopped after git switch -c", data["reason"])
        write(self.path(".gitignore"), ".loom/\nnew\n")  # an uncommitted change that is not loom.json
        self.assertEqual(self.setup_path()["path"], "onboarding")

    def test_row6_branch_cut_from_a_local_main_ahead_of_origin(self):
        self.new_repo()
        self.commit({"notes.txt": "local\n"}, "local only")  # local main is ahead of origin/main
        git(self.repo, "switch", "-q", "-c", SETUP)
        data = self.setup_path()
        self.assertEqual(data["path"], "fast")  # the first table reads origin/main
        self.assertIn("origin/main tracks only files that are not code", data["reason"])
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "switch", "-q", "-c", "chore/4-loom-setup", "origin/main")  # cut from origin/main
        self.assertEqual(self.setup_path()["path"], "fast")
        self.commit({"x.txt": "x\n"}, "a commit of its own")
        self.assertEqual(self.setup_path()["path"], "fast-resume")

    def test_row6_branch_behind_a_main_that_moved_on(self):
        # The setup branch was cut and got no commit; then main moved on (another clone pushed, git pull).
        self.new_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        other = os.path.join(self.tmp, "other")
        git(self.tmp, "clone", "-q", self.remote, other)
        write(os.path.join(other, "src", "app.py"), "x = 1\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "code on main")
        git(other, "push", "-q", "origin", "main")
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "pull", "-q", "--ff-only", "origin", "main")
        git(self.repo, "switch", "-q", SETUP)
        data = self.setup_path()
        self.assertEqual(data["path"], "onboarding")  # the first table reads the moved origin/main
        self.assertIn("has no commit of its own", data["reason"])
        # Only the remote-tracking ref moved (git fetch, local main behind): still no commit of its own.
        git(self.repo, "branch", "-f", "main", SETUP)
        self.assertEqual(self.setup_path()["path"], "onboarding")
        # A commit of its own: fast-resume, and the reason says so.
        self.commit({"x.txt": "x\n"}, "own commit")
        data = self.setup_path()
        self.assertEqual(data["path"], "fast-resume")
        self.assertIn("commits of its own", data["reason"])

    def test_row6_fast_repository(self):
        self.new_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        self.assertEqual(self.setup_path()["path"], "fast")

    def test_row6_on_an_empty_repository(self):
        git(self.repo, "switch", "-q", "-c", SETUP)  # unborn branch
        data = self.setup_path()
        self.assertEqual(data["path"], "fast")
        self.assertEqual(data["setupBranches"], [])  # an unborn branch has no ref yet

    def test_row7_fast_path_stopped_on_failing_checks(self):
        # Setup branch, no commit beyond main, .claude/loom.json in the working tree, no ticket.
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        write(self.path(".claude", "loom.json"), '{"version": 1}\n')
        write(self.path("Makefile"), "check:\n\tfalse\n")
        data = self.setup_path()
        self.assertEqual(data["path"], "fast-resume")
        self.assertIn(".claude/loom.json in the working tree", data["reason"])

    def test_row7_fast_path_after_its_commit(self):
        self.new_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        self.ticket("oneshot")
        self.commit({".claude/loom.json": "{}\n", "Makefile": "check:\n"}, "chore(loom): set up loom (#3)")
        self.assertEqual(self.setup_path()["path"], "fast-resume")
        os.remove(self.path(".loom", "tasks", "3-loom-setup", "00-ticket.md"))  # a fresh clone
        self.assertEqual(self.setup_path()["path"], "fast-resume")

    # The command line.
    def test_works_without_loom_json_and_in_a_subdirectory(self):
        self.code_repo()
        self.assertFalse(os.path.exists(self.path(".claude", "loom.json")))
        self.assertEqual(self.setup_path(self.path("src"))["path"], "onboarding")
        self.assertEqual(run_loom_state(self.repo, "--json").stdout, "")  # the state stays a no-op

    def test_paths_with_spaces_and_non_ascii_characters(self):
        self.commit({"README.md": "# x\n", "my src/app ü.py": "x = 1\n", "Dökü/AGENTS.md": "x\n",
                     "Dökü/Docs/plan ä.md": "x\n", "naïve/\"quoted\".py": "x\n"}, "initial")
        data = self.setup_path()
        self.assertEqual(data["path"], "onboarding")
        self.assertEqual(data["reason"], "main tracks 4 files that count as code (first: Dökü/AGENTS.md)")
        self.assertEqual(data["found"]["instructionFiles"], ["Dökü/AGENTS.md"])
        self.assertEqual(data["found"]["docsDirs"], ["Dökü/Docs"])

    def test_outside_a_git_repository(self):
        outside = os.path.realpath(tempfile.mkdtemp(prefix="loom-setup-path-"))
        self.addCleanup(shutil.rmtree, outside, True)
        proc = self.run_setup_path(outside, "main")
        self.assertEqual((proc.returncode, proc.stdout), (2, ""))
        self.assertIn("git repository", proc.stderr)

    def test_invalid_main_branch_name(self):
        self.code_repo()
        for main in ("", "  ", "a..b", "x y", "a\nb"):
            with self.subTest(main=main):
                proc = self.run_setup_path(self.repo, main)
                self.assertEqual((proc.returncode, proc.stdout), (2, ""))
                self.assertIn("invalid main branch name", proc.stderr)

    def test_other_options_are_rejected(self):
        self.code_repo()
        cases = (["--setup-path"], ["--setup-path", "main", "--line"], ["--setup-path", "main", "--json"],
                 ["--json", "--setup-path", "main"], ["--setup-path", "main", "--slug", "x"],
                 ["--slug", "x", "--setup-path", "main"], ["--setup-path", "main", "--pr"],
                 ["--pr", "--setup-path", "main"], ["--setup-path", "main", "--docs"])
        for args in cases:
            with self.subTest(args=args):
                proc = run_loom_state(self.repo, *args)
                self.assertEqual((proc.returncode, proc.stdout), (2, ""))
                self.assertIn("--setup-path", proc.stderr)

    def test_no_network_call(self):
        self.code_repo()
        git(self.repo, "switch", "-q", "-c", SETUP)
        git(self.repo, "remote", "set-url", "origin", "https://invalid.invalid/o/r.git")
        fake_bin = os.path.join(self.tmp, "bin")
        os.makedirs(fake_bin)
        marker = os.path.join(self.tmp, "gh-called")
        gh = os.path.join(fake_bin, "gh")
        with open(gh, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\ntouch '%s'\nexit 1\n" % marker)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
        trace = os.path.join(self.tmp, "trace.txt")
        env = {"PATH": fake_bin + os.pathsep + os.environ.get("PATH", ""), "GIT_TRACE": trace}
        proc = run_loom_state_env(self.repo, env, "--setup-path", "main")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout.decode("utf-8"))["path"], "onboarding")
        self.assertFalse(os.path.exists(marker))
        with open(trace, encoding="utf-8", errors="replace") as fh:
            traced = fh.read()
        for command in ("git fetch", "git ls-remote", "git pull", "git remote-"):
            self.assertNotIn(command, traced)


QUICK_WARNING = "00-ticket.md has no valid mode for the setup task (got 'quick'); no setup path uses quick"


class SetupTaskStateTest(RepoTestCase):
    """task.setup and rows 2b and 2c on a fixture setup branch (LOOM_SPEC.md 9.12)."""

    def test_quick_on_a_setup_task_warns(self):
        git(self.repo, "switch", "-q", "-c", SETUP)
        d = self.task_dir("3-loom-setup")
        self.ticket(d, mode=" Quick ", issue=3)
        s = self.state()
        self.assertEqual(s["task"]["mode"], "quick")
        self.assertEqual(s["warnings"], [QUICK_WARNING])
        self.assertEqual(s["next"]["command"], "/loom:setup")
        proc = run_loom_state(self.repo, "--line")
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "#3 · quick · ticket\n", ""))
        # The same mode on another task: valid, no warning.
        git(self.repo, "switch", "-q", "main")
        self.ticket(self.task_dir("5-x"), mode="quick", issue=5)
        git(self.repo, "switch", "-q", "-c", "chore/5-x")
        s = self.state()
        self.assertEqual(s["warnings"], [])
        self.assertEqual(s["next"]["command"], "/loom:research")

    def test_onboarding_kickoff_routes(self):
        git(self.repo, "switch", "-q", "-c", SETUP)
        d = self.task_dir("3-loom-setup")
        self.ticket(d, mode="full", issue=3)
        write(self.path(".gitignore"), ".loom/\nchanged\n")  # an uncommitted kickoff file
        s = self.state()
        self.assertTrue(s["task"]["setup"])
        self.assertEqual(s["next"]["command"], "/loom:setup")
        self.assertEqual(s["warnings"], [])
        self.artifact(d, "01-research-questions.md", "research-questions", "in-review")
        s = self.state()
        self.assertEqual(s["next"]["command"], "/loom:setup")
        self.assertIn("not approved", s["next"]["reason"])
        self.artifact(d, "01-research-questions.md", "research-questions", "approved")
        self.assertEqual(self.state()["next"]["command"], "/loom:research")
        for mode, reason, warnings in (("huge", "has no valid mode", ["00-ticket.md has no valid mode (got 'huge')"]),
                                       ("quick", "has mode quick", [QUICK_WARNING])):
            with self.subTest(mode=mode):
                self.ticket(d, mode=mode, issue=3)
                s = self.state()
                self.assertEqual(s["next"]["command"], "/loom:setup")
                self.assertIn(reason, s["next"]["reason"])
                self.assertEqual(s["warnings"], warnings)

    def test_draft_research_without_the_questions_file_goes_to_setup(self):
        git(self.repo, "switch", "-q", "-c", SETUP)
        d = self.task_dir("3-loom-setup")
        self.ticket(d, mode="full", issue=3)
        self.artifact(d, "02-research.md", "research", "draft")
        s = self.state()
        self.assertEqual(s["next"]["command"], "/loom:setup")
        self.assertIn("01-research-questions.md is missing", s["next"]["reason"])
        self.artifact(d, "02-research.md", "research", "in-review")
        self.assertEqual(self.state()["next"]["command"], "/loom:design")

    def test_fast_path_routes(self):
        git(self.repo, "switch", "-q", "-c", SETUP)
        d = self.task_dir("3-loom-setup")
        self.ticket(d, mode="oneshot", issue=3)
        self.assertEqual(self.state()["next"]["command"], "/loom:setup")
        write(os.path.join(d, "log.md"), "## Phase 1 — blocked\nReason: check failed on the PR\n")
        s = self.state()
        self.assertEqual(s["next"]["command"], "/loom:iterate <fix>")
        self.assertIn("check failed on the PR", s["next"]["reason"])
        write(os.path.join(d, "log.md"), "## Phase 1 — done — abc123\n")
        self.assertEqual(self.state()["next"]["command"], "/loom:describe-pr")


if __name__ == "__main__":
    unittest.main()
