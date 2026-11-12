"""Integration tests for loom-state on temporary git repositories."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from loomtest import LOOM_STATE, RepoTestCase, git, loom_state, run_loom_state, run_loom_state_env, write

ls = loom_state()


class NoOpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="loom-noop-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_outside_git_repo(self):
        for args in ([], ["--line"], ["--json"], ["--pr"], ["--docs"]):
            proc = run_loom_state(self.tmp, *args)
            self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""), args)
        self.assertIsNone(ls.compute_state(self.tmp))

    def test_git_repo_without_loom_json(self):
        git(self.tmp, "init", "-q", "-b", "main")
        git(self.tmp, "switch", "-q", "-c", "feat/1-x")
        for args in ([], ["--line"], ["--pr"], ["--docs"]):
            proc = run_loom_state(self.tmp, *args)
            self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""), args)


class ConfigTest(RepoTestCase):
    loom_config = {"mainBranch": "trunk", "checks": {"test": "make t"}}

    def test_defaults_fill_missing_keys(self):
        cfg, warnings = ls.load_config(self.repo)
        self.assertEqual(warnings, [])
        self.assertEqual(cfg["mainBranch"], "trunk")
        self.assertEqual(cfg["workDir"], ".loom/tasks")
        self.assertEqual(cfg["checks"]["test"], "make t")
        self.assertEqual(cfg["checks"]["check"], "make check")
        self.assertEqual(cfg["hooks"]["maxCheckAttempts"], 3)

    def test_main_branch_from_config(self):
        s = self.state()
        self.assertEqual(s["branch"], "main")
        self.assertFalse(s["onMain"])  # main is not the configured main branch
        git(self.repo, "branch", "-m", "trunk")
        self.assertTrue(self.state()["onMain"])

    def test_invalid_json_warns(self):
        write(self.path(".claude", "loom.json"), "{not json")
        s = self.state()
        self.assertTrue(any("loom.json" in w for w in s["warnings"]))
        self.assertTrue(s["onMain"])


DEFAULT_DOCS = {
    "dir": "docs", "vision": "docs/product/vision.md", "overview": "docs/architecture/overview.md",
    "decisions": {"dir": "docs/architecture/decisions", "pattern": "<NNNN>-<slug>.md"},
    "conventions": "docs/conventions.md", "tasks": "docs/tasks",
}
DEFAULT_CHECKS = {"lint": "make lint", "typecheck": "make typecheck", "test": "make test", "check": "make check"}


class ResolvedConfigTest(RepoTestCase):
    """docs, checks, ci, and pullRequest: defaults, custom values, invalid values (LOOM_SPEC.md 8.2, 19.1)."""

    loom_config = {}

    def resolved(self, config=None):
        if config is not None:
            self.write_config(config)
        proc = run_loom_state(self.repo, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        return data, data["warnings"]

    def test_defaults_in_every_output_also_without_a_task(self):
        data, warnings = self.resolved()
        self.assertTrue(data["onMain"])
        self.assertIsNone(data["task"])
        self.assertEqual(warnings, [])
        self.assertEqual(data["docs"], DEFAULT_DOCS)
        self.assertEqual(data["checks"], DEFAULT_CHECKS)
        self.assertEqual(data["ci"], {"requiredCheck": "check"})
        self.assertEqual(data["pullRequest"], {"requiredSections": []})
        git(self.repo, "switch", "-q", "-c", "spike/x")  # a branch without a task
        data, _ = self.resolved()
        self.assertIsNone(data["task"])
        self.assertEqual(data["docs"], DEFAULT_DOCS)

    def test_defaults_follow_docs_dir(self):
        data, warnings = self.resolved({"docsDir": "documentation/"})
        self.assertEqual(warnings, [])
        self.assertEqual(data["docs"]["dir"], "documentation")
        self.assertEqual(data["docs"]["vision"], "documentation/product/vision.md")
        self.assertEqual(data["docs"]["decisions"]["dir"], "documentation/architecture/decisions")
        self.assertEqual(data["docs"]["tasks"], "documentation/tasks")

    def test_custom_values(self):
        data, warnings = self.resolved({
            "docs": {"vision": "README.md", "overview": "./ARCHITECTURE.md",
                     "decisions": {"dir": "docs/adr/", "pattern": "ADR-<NNN>-<slug>.md"},
                     "conventions": "CONTRIBUTING.md", "tasks": "docs/loom-tasks"},
            "ci": {"requiredCheck": "test (3.12)"},
            "pullRequest": {"requiredSections": ["## Test plan", "### Risk "]},
            "checks": {"lint": "make lint", "typecheck": None, "test": "make test", "check": "make check"},
        })
        self.assertEqual(warnings, [])
        self.assertEqual(data["docs"], {
            "dir": "docs", "vision": "README.md", "overview": "ARCHITECTURE.md",
            "decisions": {"dir": "docs/adr", "pattern": "ADR-<NNN>-<slug>.md"},
            "conventions": "CONTRIBUTING.md", "tasks": "docs/loom-tasks",
        })
        self.assertEqual(data["ci"], {"requiredCheck": "test (3.12)"})
        self.assertEqual(data["pullRequest"], {"requiredSections": ["## Test plan", "### Risk"]})
        self.assertEqual(data["checks"], dict(DEFAULT_CHECKS, typecheck=None))

    def test_partial_docs_map_keeps_the_other_defaults(self):
        data, warnings = self.resolved({"docs": {"tasks": "notes/tasks", "decisions": {"pattern": "<N>-<slug>.md"}}})
        self.assertEqual(warnings, [])
        expected = dict(DEFAULT_DOCS, tasks="notes/tasks",
                        decisions={"dir": "docs/architecture/decisions", "pattern": "<N>-<slug>.md"})
        self.assertEqual(data["docs"], expected)

    def test_invalid_docs_paths_take_their_default(self):
        cases = {
            "vision": ["", "  ", "/abs/vision.md", "../vision.md", "docs/../../x.md", ".", "./", "README.txt",
                       ".loom/tasks/x.md", ".loom/vision.md", ".claude/vision.md", ".git/vision.md", 5, None, ["a.md"]],
            "tasks": ["", "/tmp/tasks", "a/../..", ".", ".loom/tasks", ".loom/tasks/sub", ".loom", ".claude",
                      ".claude/tasks", ".git", "./.git/tasks", 3],
        }
        for role, values in cases.items():
            for value in values:
                with self.subTest(role=role, value=value):
                    data, warnings = self.resolved({"docs": {role: value}})
                    self.assertEqual(data["docs"][role], DEFAULT_DOCS[role])
                    self.assertEqual(len(warnings), 1, warnings)
                    self.assertIn("docs.%s" % role, warnings[0])

    def test_reserved_dirs_and_a_custom_work_dir(self):
        data, warnings = self.resolved({"workDir": "work/tasks", "docs": {"tasks": "work/tasks/done",
                                                                         "decisions": {"dir": ".claude/adr"}}})
        self.assertEqual(data["docs"]["tasks"], DEFAULT_DOCS["tasks"])
        self.assertEqual(data["docs"]["decisions"], DEFAULT_DOCS["decisions"])
        self.assertEqual(len(warnings), 2, warnings)
        for value in (".github/ARCHITECTURE.md", ".loomx/a.md", "git/a.md", "claude.md"):
            with self.subTest(value=value):
                data, warnings = self.resolved({"docs": {"overview": value}})
                self.assertEqual((data["docs"]["overview"], warnings), (value, []))

    def test_invalid_decisions(self):
        for decisions, expected in (
            ("adr", DEFAULT_DOCS["decisions"]),
            ({"dir": "../adr"}, DEFAULT_DOCS["decisions"]),
            ({"dir": "adr", "pattern": "<NNNN>.md"}, {"dir": "adr", "pattern": "<NNNN>-<slug>.md"}),
            ({"pattern": "adr/<NNNN>-<slug>.md"}, DEFAULT_DOCS["decisions"]),
            ({"pattern": "<NNNN>-<slug>.txt"}, DEFAULT_DOCS["decisions"]),
            ({"pattern": "<NNNNNNN>-<slug>.md"}, DEFAULT_DOCS["decisions"]),
            ({"pattern": "<NN>-<NN>-<slug>.md"}, DEFAULT_DOCS["decisions"]),
            ({"pattern": "<NNNN>-<slug>-<slug>.md"}, DEFAULT_DOCS["decisions"]),
        ):
            with self.subTest(decisions=decisions):
                data, warnings = self.resolved({"docs": {"decisions": decisions}})
                self.assertEqual(data["docs"]["decisions"], expected)
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn("docs.decisions", warnings[0])

    def test_valid_patterns(self):
        for pattern in ("<N>-<slug>.md", "<NNNNNN>_<slug>.md", "ADR-<NNN>-<slug>.md", "<slug>-<NN>.md"):
            with self.subTest(pattern=pattern):
                self.assertTrue(ls.valid_decisions_pattern(pattern))

    def test_docs_not_an_object_and_unknown_keys(self):
        data, warnings = self.resolved({"docs": "docs"})
        self.assertEqual(data["docs"], DEFAULT_DOCS)
        self.assertEqual(len(warnings), 1)
        data, warnings = self.resolved({"docs": {"dir": "x", "decisions": {"dir": "adr", "glob": "*"}}})
        self.assertEqual(data["docs"]["dir"], "docs")  # dir is docsDir, not a map key
        self.assertEqual(data["docs"]["decisions"]["dir"], "adr")
        self.assertEqual(len(warnings), 2, warnings)
        self.assertTrue(any("docs.dir" in w for w in warnings))
        self.assertTrue(any("docs.decisions.glob" in w for w in warnings))

    def test_invalid_ci(self):
        for ci in ("check", {"requiredCheck": ""}, {"requiredCheck": 5}, {"requiredCheck": None}):
            with self.subTest(ci=ci):
                data, warnings = self.resolved({"ci": ci})
                self.assertEqual(data["ci"], {"requiredCheck": "check"})
                self.assertEqual(len(warnings), 1, warnings)
        data, warnings = self.resolved({"ci": {"requiredCheck": "build", "required": "x"}})
        self.assertEqual(data["ci"], {"requiredCheck": "build"})
        self.assertEqual(len(warnings), 1)

    def test_invalid_required_sections(self):
        data, warnings = self.resolved({"pullRequest": {"requiredSections": "## Test plan"}})
        self.assertEqual(data["pullRequest"], {"requiredSections": []})
        self.assertEqual(len(warnings), 1)
        data, warnings = self.resolved({"pullRequest": {"requiredSections": [
            "## Test plan", "Test plan", "# Title", "#### Deep", "##", "## ", "##No space", 5, None,
            "## Test plan", "### Risks", "## Two\nlines"]}})
        self.assertEqual(data["pullRequest"], {"requiredSections": ["## Test plan", "### Risks"]})
        self.assertEqual(len(warnings), 10, warnings)
        data, warnings = self.resolved({"pullRequest": []})
        self.assertEqual(data["pullRequest"], {"requiredSections": []})
        self.assertEqual(len(warnings), 1)

    def test_null_and_invalid_checks(self):
        data, warnings = self.resolved({"checks": {"lint": None, "typecheck": None, "test": None}})
        self.assertEqual(warnings, [])
        self.assertEqual(data["checks"], {"lint": None, "typecheck": None, "test": None, "check": "make check"})
        data, warnings = self.resolved({"checks": {"lint": "make lint", "typecheck": 5, "test": False, "check": None}})
        self.assertEqual(data["checks"], DEFAULT_CHECKS)
        self.assertEqual(len(warnings), 3, warnings)
        for key in ("checks.typecheck", "checks.test", "checks.check"):
            with self.subTest(key=key):
                self.assertTrue(any(key in w for w in warnings))
        # An empty optional check keeps its 1.1.0 meaning: off, now with a warning to use null.
        data, warnings = self.resolved({"checks": {"lint": "", "typecheck": "  ", "test": "make test"}})
        self.assertEqual(data["checks"], dict(DEFAULT_CHECKS, lint=None, typecheck=None))
        self.assertEqual(len(warnings), 2, warnings)
        self.assertTrue(all("use null" in w for w in warnings), warnings)
        data, warnings = self.resolved({"checks": {"check": "  "}})
        self.assertEqual(data["checks"]["check"], "make check")
        self.assertEqual(len(warnings), 1)

    def test_hooks_see_the_resolved_config(self):
        self.write_config({"checks": {"lint": None, "check": ""}, "docs": {"tasks": "notes/tasks"}})
        cfg, warnings = ls.load_config(self.repo)
        self.assertEqual(len(warnings), 1)
        self.assertIsNone(cfg["checks"]["lint"])
        self.assertEqual(cfg["checks"]["check"], "make check")
        self.assertEqual(cfg["docs"]["tasks"], "notes/tasks")
        self.assertEqual(ls.docs_change_paths(cfg), [
            "docs", "docs/architecture/decisions", "docs/product/vision.md", "docs/architecture/overview.md",
            "docs/conventions.md", "notes/tasks"])


class TodayTest(RepoTestCase):
    """`today` gives skills the date without a `date` command injection."""

    def test_today_on_main_and_on_a_task_branch(self):
        import datetime
        today = datetime.date.today().isoformat()
        proc = run_loom_state(self.repo, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertIsNone(data["task"])
        self.assertEqual(data["today"], today)
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")
        self.ticket(self.task_dir("42-auth-flow"))
        data = json.loads(run_loom_state(self.repo).stdout)
        self.assertEqual(data["task"]["number"], 42)
        self.assertEqual(data["today"], today)

    def test_today_with_pr(self):
        import datetime
        original = ls.fetch_pr
        ls.fetch_pr = lambda top, cfg: (None, ["gh is not installed; PR state unknown"])
        self.addCleanup(setattr, ls, "fetch_pr", original)
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")
        self.ticket(self.task_dir("42-auth-flow"))
        s = ls.compute_state(self.repo, with_pr=True)
        self.assertEqual(s["today"], datetime.date.today().isoformat())
        self.assertIsNone(s["pr"])


class TaskLookupTest(RepoTestCase):
    def test_on_main(self):
        s = self.state()
        self.assertTrue(s["onMain"])
        self.assertIsNone(s["task"])
        self.assertEqual(s["next"]["command"], "/loom:start-task #<n>")
        self.assertEqual(run_loom_state(self.repo, "--line").stdout, "")

    def test_lookup_by_number_with_renamed_slug(self):
        d = self.task_dir("42-old-title")
        self.ticket(d, mode="quick")
        git(self.repo, "switch", "-q", "-c", "feat/42-new-title")
        s = self.state()
        self.assertEqual(s["task"]["number"], 42)
        self.assertEqual(s["task"]["slug"], "old-title")
        self.assertEqual(s["task"]["dir"], ".loom/tasks/42-old-title")
        self.assertEqual(s["task"]["mode"], "quick")
        self.assertFalse(s["task"]["archived"])
        self.assertEqual(s["next"]["command"], "/loom:research")

    def test_number_prefix_is_exact(self):
        self.ticket(self.task_dir("420-other"), mode="full")
        git(self.repo, "switch", "-q", "-c", "fix/42-thing")
        s = self.state()
        self.assertIsNone(s["task"])
        self.assertEqual(s["next"]["command"], "/loom:start-task #42")

    def test_archived(self):
        self.ticket(self.task_dir("_archive/42-auth-flow"), mode="full")
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")
        s = self.state()
        self.assertTrue(s["task"]["archived"])
        self.assertEqual(s["task"]["dir"], ".loom/tasks/_archive/42-auth-flow")
        self.assertEqual(s["next"]["command"], "/loom:start-task #42")
        self.assertEqual(run_loom_state(self.repo, "--line").stdout, "#42 · archived\n")

    def test_active_dir_wins_over_archive(self):
        self.ticket(self.task_dir("_archive/42-auth-flow"), mode="full")
        self.ticket(self.task_dir("42-auth-flow"), mode="quick")
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")
        s = self.state()
        self.assertFalse(s["task"]["archived"])
        self.assertEqual(s["task"]["mode"], "quick")

    def test_unrecognized_branch(self):
        git(self.repo, "switch", "-q", "-c", "spike/try")
        s = self.state()
        self.assertIsNone(s["task"])
        self.assertIn("matches no task", s["next"]["reason"])

    def test_branch_types(self):
        for i, kind in enumerate(("feat", "fix", "chore", "docs", "refactor"), start=1):
            self.ticket(self.task_dir("%d-x" % i), mode="oneshot", issue=i)
            git(self.repo, "switch", "-q", "-c", "%s/%d-x" % (kind, i))
            self.assertEqual(self.state()["task"]["number"], i, kind)

    def test_custom_work_dir(self):
        self.write_config({"workDir": "work/tasks"})
        write(self.path(".gitignore"), ".loom/\nwork/\n")
        self.ticket(self.task_dir("5-x", work_dir="work/tasks"), mode="oneshot", issue=5)
        git(self.repo, "switch", "-q", "-c", "chore/5-x")
        s = self.state()
        self.assertEqual(s["task"]["dir"], "work/tasks/5-x")

    def test_ticket_pr_and_invalid_mode(self):
        d = self.task_dir("42-x")
        self.ticket(d, mode="huge", pr=57)
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        s = self.state()
        self.assertEqual(s["task"]["pr"], 57)
        self.assertTrue(any("mode" in w for w in s["warnings"]))


class ArtifactsAndLineTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.dir = self.task_dir("42-auth-flow")
        self.ticket(self.dir, mode="full")
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")

    def test_full_state_and_line(self):
        head = git(self.repo, "rev-parse", "--short", "HEAD")
        self.artifact(self.dir, "01-research-questions.md", "research-questions", "approved")
        self.artifact(self.dir, "02-research.md", "research", "in-review",
                      "## Findings\nSee `README.md:1`.\n", git_commit=head)
        self.artifact(self.dir, "03-design.md", "design", "in-review", """
            ## Open Questions — Round 1 of ~3
            **Q1. A?**
            - a) x — recommended: y
            **Q2. B?**
            **Q3. C?**
            ## Resolved Decisions
        """)
        proc = run_loom_state(self.repo)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        s = json.loads(proc.stdout)
        self.assertEqual(s["branch"], "feat/42-auth-flow")
        self.assertEqual(s["task"]["mode"], "full")
        self.assertEqual([a["file"] for a in s["artifacts"]],
                         ["01-research-questions.md", "02-research.md", "03-design.md"])
        research, design = s["artifacts"][1], s["artifacts"][2]
        self.assertEqual(research["status"], "in-review")
        self.assertFalse(research["stale"])
        self.assertEqual(design["openQuestions"], 3)
        self.assertEqual(design["acceptedByDefault"], 0)
        self.assertEqual(s["workingTree"], "clean")
        self.assertIsNone(s["pr"])
        self.assertEqual(s["next"]["command"], "/loom:iterate <answers>")
        self.assertIn("design has 3 open questions", s["next"]["reason"])
        line = run_loom_state(self.repo, "--line").stdout
        self.assertEqual(line, "#42 · full · design:in-review · 3 open Q\n")

    def test_line_ticket_only(self):
        self.assertEqual(run_loom_state(self.repo, "--line").stdout, "#42 · full · ticket\n")

    def test_implementation_progress_and_line(self):
        for name, phase in (("01-research-questions.md", "research-questions"), ("02-research.md", "research"),
                            ("03-design.md", "design")):
            self.artifact(self.dir, name, phase, "approved")
        self.artifact(self.dir, "04-plan.md", "plan", "approved", """
            ## Phase Overview
            - [x] 1. Endpoint
            - [ ] 2. Storage
            - [ ] 3. Auth
        """)
        write(os.path.join(self.dir, "log.md"), "## Phase 1 — done — abc1234\nChecks: ok\n")
        s = self.state()
        self.assertEqual((s["implementation"]["total"], s["implementation"]["done"]), (3, 1))
        self.assertEqual(s["next"]["command"], "/loom:implement")
        self.assertEqual(run_loom_state(self.repo, "--line").stdout, "#42 · full · impl 1/3\n")
        write(os.path.join(self.dir, "log.md"), "## Phase 1 — done — abc1234\n## Phase 2 — blocked\nReason: x\n")
        s = self.state()
        self.assertEqual(s["implementation"]["blocked"], {"phase": 2, "reason": "x"})
        self.assertEqual(s["next"]["command"], "/loom:iterate <fix>")
        self.assertEqual(run_loom_state(self.repo, "--line").stdout,
                         "#42 · full · impl 1/3 · blocked\n")

    def test_superseded_research_is_ignored(self):
        self.artifact(self.dir, "02-research.superseded.md", "research", "approved")
        s = self.state()
        self.assertEqual(s["artifacts"], [])
        self.assertEqual(s["next"]["command"], "/loom:research-questions")

    def test_missing_status_warns(self):
        write(os.path.join(self.dir, "01-research-questions.md"), "---\nphase: research-questions\n---\n")
        s = self.state()
        self.assertIsNone(s["artifacts"][0]["status"])
        self.assertTrue(any("no status" in w for w in s["warnings"]))
        self.assertEqual(s["next"]["command"], "/loom:research-questions")

    def test_docs_flag_not_implemented(self):
        proc = run_loom_state(self.repo, "--docs")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("not implemented yet (planned for v1.2)", proc.stderr)

    def fake_gh(self, script: str) -> dict:
        """Run loom-state --pr with a fake `gh` first on PATH."""
        bindir = os.path.join(self.tmp, "fakebin")
        gh = write(os.path.join(bindir, "gh"), "#!/bin/sh\n" + script)
        os.chmod(gh, 0o755)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""))
        proc = subprocess.run([sys.executable, LOOM_STATE, "--pr"], cwd=self.repo, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_pr_without_pull_request(self):
        s = self.fake_gh("echo 'no pull requests found for branch \"feat/42-auth-flow\"' >&2\nexit 1\n")
        self.assertIsNone(s["pr"])
        self.assertTrue(any("no pull requests found" in w for w in s["warnings"]), s["warnings"])

    def test_pr_state_and_routing(self):
        payload = {"number": 57, "state": "OPEN", "reviewDecision": "", "mergeStateStatus": "CLEAN",
                   "statusCheckRollup": [{"__typename": "CheckRun", "status": "COMPLETED",
                                          "conclusion": "FAILURE"}]}
        for name, phase in (("01-research-questions.md", "research-questions"), ("02-research.md", "research"),
                            ("03-design.md", "design")):
            self.artifact(self.dir, name, phase, "approved")
        self.artifact(self.dir, "04-plan.md", "plan", "approved", "## Phase Overview\n- [x] 1. Only\n")
        s = self.fake_gh("cat <<'EOF'\n%s\nEOF\n" % json.dumps(payload))
        self.assertEqual(s["pr"]["number"], 57)
        self.assertEqual(s["pr"]["checks"], "failing")
        self.assertIsNone(s["pr"]["reviewDecision"])
        self.assertEqual(s["pr"]["behindMain"], 0)  # no origin: local main is used
        self.assertEqual(s["next"]["command"], "/loom:iterate")


class FenceWarningTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.dir = self.task_dir("42-auth-flow")
        self.ticket(self.dir, mode="full")
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")

    def test_unclosed_fence_in_artifact_warns(self):
        self.artifact(self.dir, "03-design.md", "design", "in-review", """
            ## Proposed Architecture
            ````text
            ```
            ## Open Questions — Round 1 of ~3
            **Q1. Hidden by the open fence?**
        """)
        s = self.state()
        design = [a for a in s["artifacts"] if a["file"] == "03-design.md"][0]
        self.assertEqual(design["openQuestions"], 0)
        self.assertIn("03-design.md has an unclosed code fence; the rest of the file is ignored",
                      s["warnings"])

    def test_unclosed_fence_in_log_warns(self):
        write(os.path.join(self.dir, "log.md"), "## Phase 1 — done — abc123\n```\nlog\n")
        self.assertIn("log.md has an unclosed code fence; the rest of the file is ignored",
                      self.state()["warnings"])

    def test_closed_fences_do_not_warn(self):
        self.artifact(self.dir, "03-design.md", "design", "in-review", """
            ````markdown
            ```
            **Q9. Example**
            ```
            ````
            ## Open Questions — Round 1 of ~3
            **Q1. Real?**
        """)
        s = self.state()
        self.assertFalse([w for w in s["warnings"] if "unclosed" in w])
        design = [a for a in s["artifacts"] if a["file"] == "03-design.md"][0]
        self.assertEqual(design["openQuestions"], 1)


class TicketSizeTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.dir = self.task_dir("42-auth-flow")
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")

    def write_ticket(self, size_line: str) -> None:
        write(os.path.join(self.dir, "00-ticket.md"),
              "---\ntask: 42-auth-flow\nphase: ticket\nmode: quick\n%sissue: 42\n---\n# Ticket\n" % size_line)

    def test_size_is_read(self):
        self.write_ticket("size: M\n")
        self.assertEqual(self.state()["task"]["size"], "M")

    def test_size_is_normalized(self):
        self.write_ticket("size: l\n")
        self.assertEqual(self.state()["task"]["size"], "L")

    def test_size_is_optional(self):
        self.write_ticket("")
        s = self.state()
        self.assertIsNone(s["task"]["size"])
        self.assertFalse([w for w in s["warnings"] if "size" in w])

    def test_invalid_size_warns(self):
        self.write_ticket("size: XL\n")
        s = self.state()
        self.assertIsNone(s["task"]["size"])
        self.assertTrue([w for w in s["warnings"] if "invalid size" in w])


class WorkingTreeTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.dir = self.task_dir("42-x")
        self.ticket(self.dir, mode="oneshot")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")

    def test_clean_ignores_work_dir_even_when_not_gitignored(self):
        write(self.path(".gitignore"), "")
        git(self.repo, "commit", "-q", "-am", "unignore")
        self.assertEqual(self.state()["workingTree"], "clean")

    def test_untracked_file_is_dirty(self):
        write(self.path("new.py"), "x = 1\n")
        s = self.state()
        self.assertEqual(s["workingTree"], "dirty")
        self.assertEqual(s["next"]["command"], "/loom:implement")

    def test_modified_file_is_dirty(self):
        write(self.path("README.md"), "changed\n")
        self.assertEqual(self.state()["workingTree"], "dirty")

    def test_docs_only_flag(self):
        self.assertFalse(self.state()["workingTreeDocsOnly"])
        write(self.path("docs", "tasks", "42-x.md"), "# summary\n")
        s = self.state()
        self.assertEqual((s["workingTree"], s["workingTreeDocsOnly"]), ("dirty", True))
        write(self.path("src", "app.py"), "x = 1\n")
        self.assertEqual(self.state()["workingTreeDocsOnly"], False)

    def test_docs_only_flag_counts_every_docs_map_path(self):
        self.write_config({"docs": {"vision": "README.md", "overview": "ARCHITECTURE.md",
                                    "decisions": {"dir": "adr"}, "tasks": "notes/tasks"}})
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "docs map")
        for path in ("README.md", "ARCHITECTURE.md", "adr/0001-x.md", "notes/tasks/42-x.md", "docs/other.md"):
            write(self.path(*path.split("/")), "changed\n")
            with self.subTest(path=path):
                s = self.state()
                self.assertEqual((s["workingTree"], s["workingTreeDocsOnly"]), ("dirty", True))
        write(self.path("notes", "todo.md"), "x\n")  # next to a mapped path, not at or below it
        self.assertEqual(self.state()["workingTreeDocsOnly"], False)

    def test_all_done_docs_only_dirty_routes_to_describe_pr(self):
        write(os.path.join(self.dir, "log.md"), "## Phase 1 — done — abc1234\n")
        write(self.path("docs", "tasks", "42-x.md"), "# summary\n")
        self.assertEqual(self.state()["next"]["command"], "/loom:describe-pr")
        write(self.path("src", "app.py"), "x = 1\n")
        self.assertEqual(self.state()["next"]["command"], "/loom:iterate <feedback>")

    def test_oneshot_next(self):
        s = self.state()
        self.assertEqual(s["next"]["command"], "/loom:implement")
        self.assertEqual(run_loom_state(self.repo, "--line").stdout, "#42 · oneshot · impl 0/1\n")


class StaleResearchTest(RepoTestCase):
    """Research at C1; main later changes files; the task branch is rebased."""

    def setUp(self):
        super().setUp()
        self.commit_file("src/a.py", "a = 1\n", "add a")
        self.commit_file("src/b.py", "b = 1\n", "add b")
        self.research_commit = git(self.repo, "rev-parse", "--short", "HEAD")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        self.dir = self.task_dir("42-x")
        self.ticket(self.dir, mode="quick")
        self.artifact(self.dir, "02-research.md", "research", "approved",
                      "## Findings\n- `src/a.py:1` defines a\n- src/b.py defines b\n",
                      git_commit=self.research_commit)

    def research(self):
        s = self.state()
        return s, s["artifacts"][0]

    def test_not_stale_without_main_changes(self):
        s, research = self.research()
        self.assertFalse(research["stale"])
        self.assertEqual(s["warnings"], [])

    def test_task_commits_do_not_count(self):
        self.commit_file("src/a.py", "a = 2\n", "task change")
        _, research = self.research()
        self.assertFalse(research["stale"])

    def test_main_change_after_rebase_is_stale(self):
        self.commit_file("src/b.py", "b = 2\n", "task change")
        git(self.repo, "switch", "-q", "main")
        self.commit_file("src/a.py", "a = 3\n", "main change")
        git(self.repo, "switch", "-q", "feat/42-x")
        _, research = self.research()
        self.assertFalse(research["stale"])  # merge-base has not moved yet
        git(self.repo, "rebase", "-q", "main")
        s, research = self.research()
        self.assertTrue(research["stale"])
        self.assertEqual(research["staleFiles"], ["src/a.py"])
        self.assertIn("stale", s["next"]["reason"])

    def test_unreferenced_main_change_is_not_stale(self):
        git(self.repo, "switch", "-q", "main")
        self.commit_file("src/c.py", "c = 1\n", "main change")
        git(self.repo, "switch", "-q", "feat/42-x")
        git(self.repo, "rebase", "-q", "main")
        _, research = self.research()
        self.assertFalse(research["stale"])

    def test_origin_main_is_preferred(self):
        remote = os.path.join(self.tmp, "remote.git")
        git(self.tmp, "init", "-q", "--bare", "-b", "main", remote)
        git(self.repo, "remote", "add", "origin", remote)
        git(self.repo, "push", "-q", "origin", "main")
        # origin/main moves (simulated by a fetch from another clone)
        other = os.path.join(self.tmp, "other")
        git(self.tmp, "clone", "-q", remote, other)
        write(os.path.join(other, "src", "a.py"), "a = 9\n")
        git(other, "commit", "-q", "-am", "remote change")
        git(other, "push", "-q", "origin", "main")
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "rebase", "-q", "origin/main")
        _, research = self.research()
        self.assertTrue(research["stale"])  # local main is behind, origin/main counts

    def test_unknown_commit_warns(self):
        self.artifact(self.dir, "02-research.md", "research", "approved", "src/a.py\n", git_commit="deadbeef")
        s, research = self.research()
        self.assertFalse(research["stale"])
        self.assertTrue(any("deadbeef" in w for w in s["warnings"]))

    def test_missing_commit_warns(self):
        self.artifact(self.dir, "02-research.md", "research", "approved", "src/a.py\n")
        s, research = self.research()
        self.assertFalse(research["stale"])
        self.assertTrue(any("git_commit" in w for w in s["warnings"]))


class FetchEnvTest(RepoTestCase):
    def test_fetch_never_prompts(self):
        remote = os.path.join(self.tmp, "remote.git")
        git(self.tmp, "init", "-q", "--bare", "-b", "main", remote)
        git(self.repo, "remote", "add", "origin", remote)
        git(self.repo, "push", "-q", "origin", "main")
        calls = []
        original = ls.run

        def recording_run(args, cwd, timeout=ls.GIT_TIMEOUT, extra_env=None):
            calls.append((args, extra_env))
            return original(args, cwd, timeout, extra_env)

        ls.run = recording_run
        try:
            behind, warnings = ls.behind_main(self.repo, ls.load_config(self.repo)[0])
        finally:
            ls.run = original
        self.assertEqual((behind, warnings), (0, []))
        fetches = [env for args, env in calls if "fetch" in args]
        self.assertEqual(len(fetches), 1)
        self.assertEqual(fetches[0]["GIT_TERMINAL_PROMPT"], "0")
        others = [env for args, env in calls if "fetch" not in args]
        self.assertTrue(others and all(env is None for env in others))


class NonInteractiveEnvTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        saved = os.environ.pop("GIT_SSH_COMMAND", None)
        if saved is not None:
            self.addCleanup(os.environ.__setitem__, "GIT_SSH_COMMAND", saved)

    def test_default(self):
        self.assertEqual(ls.non_interactive_env(self.repo),
                         {"GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -oBatchMode=yes"})

    def test_existing_git_ssh_command_is_extended(self):
        os.environ["GIT_SSH_COMMAND"] = "ssh -i ~/.ssh/work"
        self.addCleanup(os.environ.pop, "GIT_SSH_COMMAND", None)
        self.assertEqual(ls.non_interactive_env(self.repo)["GIT_SSH_COMMAND"], "ssh -i ~/.ssh/work -oBatchMode=yes")

    def test_core_ssh_command_is_left_alone(self):
        git(self.repo, "config", "core.sshCommand", "ssh -i ~/.ssh/work")
        self.assertEqual(ls.non_interactive_env(self.repo), {"GIT_TERMINAL_PROMPT": "0"})


class EmptyRepoTest(RepoTestCase):
    initial_commit = False

    def test_unborn_main(self):
        s = self.state()
        self.assertEqual(s["branch"], "main")
        self.assertTrue(s["onMain"])



DEFAULT_SETTINGS = {
    "workDir": ".loom/tasks",
    "rounds": {"cap": {"S": 2, "M": 3, "L": 5}},
    "implement": {"maxFixAttempts": 2, "autoAdvance": True},
    "hooks": {"stopLint": False, "maxCheckAttempts": 3},
}


class ConfigHardeningTest(RepoTestCase):
    """BOM, whitespace, workDir and docsDir rules, null objects, control characters (LOOM_SPEC.md 19.1)."""

    loom_config = {}

    def resolved(self, config=None, raw=None):
        if raw is not None:
            with open(self.path(".claude", "loom.json"), "wb") as fh:
                fh.write(raw)
        elif config is not None:
            self.write_config(config)
        proc = run_loom_state(self.repo, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        return data, data["warnings"]

    def test_unknown_top_level_keys(self):
        data, warnings = self.resolved({"version": 1, "tracker": "github", "mainbranch": "trunk", "stopLint": True})
        self.assertEqual(data["mainBranch"], "main")
        self.assertEqual(warnings, [".claude/loom.json: unknown key 'mainbranch' ignored",
                                    ".claude/loom.json: unknown key 'stopLint' ignored"])

    def test_docs_default_inside_work_dir(self):
        data, warnings = self.resolved({"workDir": "work/tasks", "docsDir": "work"})
        self.assertEqual(data["docs"]["tasks"], "work/tasks")  # the only default: kept
        self.assertEqual(warnings, [
            ".claude/loom.json: 'docs.tasks' (work/tasks) is at or below workDir (work/tasks), where loom ignores "
            "changes; set 'docs.tasks' or docsDir to a path outside workDir"])
        data, warnings = self.resolved({"workDir": "work/tasks", "docsDir": "work", "docs": {"tasks": "work/done"}})
        self.assertEqual((data["docs"]["tasks"], warnings), ("work/done", []))
        data, warnings = self.resolved({"workDir": "docs", "docsDir": "documentation"})
        self.assertEqual(warnings, [])

    def test_byte_order_mark(self):
        data, warnings = self.resolved(raw=b"\xef\xbb\xbf" + json.dumps({"mainBranch": "trunk"}).encode())
        self.assertEqual(warnings, [])
        self.assertEqual(data["mainBranch"], "trunk")
        cfg, warnings = ls.load_config(self.repo)
        self.assertEqual((cfg["mainBranch"], warnings), ("trunk", []))

    def test_surrounding_whitespace_is_stripped(self):
        data, warnings = self.resolved({"mainBranch": " main ", "workDir": " work/tasks/ ", "docsDir": "\tdocumentation "})
        self.assertEqual(warnings, [])
        self.assertEqual((data["mainBranch"], data["workDir"], data["docs"]["dir"]),
                         ("main", "work/tasks", "documentation"))
        self.assertTrue(data["onMain"])
        self.assertEqual(data["docs"]["tasks"], "documentation/tasks")

    def test_invalid_main_branch(self):
        for value in ("", "  ", 5, None, "ma\nin", "main\x00"):
            with self.subTest(value=value):
                data, warnings = self.resolved({"mainBranch": value})
                self.assertEqual(data["mainBranch"], "main")
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn("'mainBranch'", warnings[0])

    def test_invalid_work_dir(self):
        for value in ("", "/abs/tasks", "../tasks", "a/../../x", ".", ".git", ".git/tasks", ".GIT/tasks",
                      ".claude/tasks", ".Claude", "ta\nsks", "tasks\x00", 7, None, ["x"]):
            with self.subTest(value=value):
                data, warnings = self.resolved({"workDir": value})
                self.assertEqual(data["workDir"], ".loom/tasks")
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn("'workDir'", warnings[0])
        for value in (".loom", ".loom/tasks", "work/tasks", "./work"):
            with self.subTest(value=value):
                data, warnings = self.resolved({"workDir": value})
                self.assertEqual((data["workDir"], warnings), (value.lstrip("./") if value == "./work" else value, []))

    def test_invalid_docs_dir(self):
        for value in ("", "/docs", "../docs", ".", ".git", ".claude/docs", ".loom/docs", ".LOOM", ".loom/tasks/docs",
                      "do\tcs", 3, None):
            with self.subTest(value=value):
                data, warnings = self.resolved({"docsDir": value})
                self.assertEqual(data["docs"], DEFAULT_DOCS)
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn("'docsDir'", warnings[0])
        data, warnings = self.resolved({"workDir": "work/tasks", "docsDir": "work/tasks/docs"})
        self.assertEqual((data["docs"]["dir"], len(warnings)), ("docs", 1))
        self.assertEqual(ls.load_config(self.repo)[0]["docsDir"], "docs")

    def test_reserved_dirs_ignore_case(self):
        for value in (".GIT/vision.md", ".Claude/vision.md", ".LOOM/vision.md", ".Loom/Tasks/x.md"):
            with self.subTest(value=value):
                data, warnings = self.resolved({"docs": {"vision": value}})
                self.assertEqual(data["docs"]["vision"], DEFAULT_DOCS["vision"])
                self.assertEqual(len(warnings), 1, warnings)
        data, warnings = self.resolved({"workDir": "Work/Tasks", "docs": {"tasks": "work/tasks/done"}})
        self.assertEqual(data["docs"]["tasks"], DEFAULT_DOCS["tasks"])
        self.assertEqual(len(warnings), 1, warnings)

    def test_markdown_extension_ignores_case(self):
        data, warnings = self.resolved({"docs": {"vision": "README.MD", "overview": "docs/Arch.Md",
                                                 "decisions": {"pattern": "ADR-<NNN>-<slug>.MD"}}})
        self.assertEqual(warnings, [])
        self.assertEqual((data["docs"]["vision"], data["docs"]["overview"], data["docs"]["decisions"]["pattern"]),
                         ("README.MD", "docs/Arch.Md", "ADR-<NNN>-<slug>.MD"))

    def test_null_objects_warn(self):
        for key, expected in (("docs", DEFAULT_DOCS), ("ci", {"requiredCheck": "check"}),
                              ("pullRequest", {"requiredSections": []})):
            for value in (None, [], "x", 5):
                with self.subTest(key=key, value=value):
                    data, warnings = self.resolved({key: value})
                    self.assertEqual(data[key], expected)
                    self.assertEqual(len(warnings), 1, warnings)
                    self.assertIn(key, warnings[0])

    def test_control_characters_are_rejected(self):
        data, warnings = self.resolved({
            "docs": {"vision": "READ\nME.md", "tasks": "notes\ttasks",
                     "decisions": {"dir": "adr\x00", "pattern": "<NNNN>-<slug>\n.md"}},
            "ci": {"requiredCheck": "build\ntest"},
            "pullRequest": {"requiredSections": ["## Test\tplan", "## Risks\x07", "## Fine"]},
        })
        self.assertEqual(data["docs"], DEFAULT_DOCS)
        self.assertEqual(data["ci"], {"requiredCheck": "check"})
        self.assertEqual(data["pullRequest"], {"requiredSections": ["## Fine"]})
        self.assertEqual(len(warnings), 7, warnings)

    def test_lone_surrogate_does_not_crash(self):
        raw = b'{"mainBranch": "m\\ud800", "ci": {"requiredCheck": "\\udc80x"}, "docs": {"vision": "\\ud800.md"},' \
              b' "checks": {"test": "make test \\ud800"}, "unknown\\ud800": 1}'
        data, warnings = self.resolved(raw=raw)
        self.assertEqual(data["mainBranch"], "main")
        self.assertEqual(data["ci"], {"requiredCheck": "check"})
        self.assertEqual(data["docs"]["vision"], DEFAULT_DOCS["vision"])
        self.assertEqual(len(warnings), 4, warnings)  # mainBranch, ci, docs.vision, the unknown key
        self.assertIn(".claude/loom.json: unknown key 'unknown\\ud800' ignored", warnings)
        for warning in warnings:
            warning.encode("utf-8")  # printable: no lone surrogate left
        proc = run_loom_state(self.repo, "--line")
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))

    def test_check_command_with_an_output_filter_warns(self):
        data, warnings = self.resolved({"checks": {
            "lint": "make lint", "typecheck": None,
            "test": "go test ./... | grep -v 'no test files'", "check": "make check 2>&1 | tail -n 50"}})
        self.assertEqual(data["checks"]["test"], "go test ./... | grep -v 'no test files'")  # kept as configured
        self.assertEqual(warnings, [
            ".claude/loom.json: 'checks.test' pipes its output into grep; filtered output can hide failures",
            ".claude/loom.json: 'checks.check' pipes its output into tail; filtered output can hide failures",
        ])
        for command in ("make test | tee test.log", "npm ci && npm run check", "make check || true", "echo 'a | grep'"):
            with self.subTest(command=command):
                _, warnings = self.resolved({"checks": {"check": command}})
                self.assertEqual(warnings, [])
        for command, name in (("pytest | rg FAIL", "rg"), ("pytest |& LC_ALL=C wc -l", "wc"),
                              ("make check | /usr/bin/head", "head")):
            with self.subTest(command=command):
                _, warnings = self.resolved({"checks": {"check": command}})
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn("pipes its output into %s" % name, warnings[0])

    def test_filters_match_the_hook(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "block_output_filtering", os.path.join(os.path.dirname(LOOM_STATE), "..", "scripts", "hooks",
                                                   "block_output_filtering.py"))
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        self.assertLessEqual(set(hook.FILTERS), set(ls.OUTPUT_FILTERS))


class DocsOverlapTest(RepoTestCase):
    """Docs map roles that collide get a warning; the configured values stay (LOOM_SPEC.md 19.1)."""

    loom_config = {}

    def resolved(self, docs):
        self.write_config({"docs": docs})
        cfg, warnings = ls.load_config(self.repo)
        return cfg["docs"], warnings

    def test_shared_role_file_is_allowed(self):
        docs, warnings = self.resolved({"vision": "README.md", "overview": "README.md", "conventions": "README.md"})
        self.assertEqual(warnings, [])
        self.assertEqual((docs["vision"], docs["overview"], docs["conventions"]), ("README.md",) * 3)

    def test_tasks_and_decisions_overlap(self):
        for tasks, decisions in (("docs/adr", "docs/adr"), ("docs/adr/tasks", "docs/adr"), ("docs/notes", "docs/notes/adr"),
                                 ("Docs/ADR", "docs/adr")):
            with self.subTest(tasks=tasks, decisions=decisions):
                docs, warnings = self.resolved({"tasks": tasks, "decisions": {"dir": decisions}})
                self.assertEqual((docs["tasks"], docs["decisions"]["dir"]), (tasks, decisions))
                self.assertEqual(warnings, [
                    ".claude/loom.json: 'docs.tasks' (%s) and 'docs.decisions.dir' (%s) overlap; task summaries "
                    "and decision records would mix" % (tasks, decisions)])

    def test_role_file_below_a_role_directory(self):
        docs, warnings = self.resolved({"vision": "docs/tasks/vision.md", "conventions": "docs/adr/conventions.md",
                                        "decisions": {"dir": "docs/adr"}})
        self.assertEqual(docs["vision"], "docs/tasks/vision.md")
        self.assertEqual(warnings, [
            ".claude/loom.json: 'docs.vision' (docs/tasks/vision.md) is at or below 'docs.tasks' (docs/tasks); "
            "keep role files outside the task summary and decision directories",
            ".claude/loom.json: 'docs.conventions' (docs/adr/conventions.md) is at or below 'docs.decisions.dir' "
            "(docs/adr); keep role files outside the task summary and decision directories",
        ])

    def test_neighbours_do_not_overlap(self):
        _, warnings = self.resolved({"tasks": "docs/task", "decisions": {"dir": "docs/tasks-adr"},
                                     "vision": "docs/tasks.md"})
        self.assertEqual(warnings, [])


class SettingsTest(RepoTestCase):
    """workDir, rounds, implement, and hooks in the state (LOOM_SPEC.md 8.2, 19.1)."""

    loom_config = {}

    def resolved(self, config):
        self.write_config(config)
        proc = run_loom_state(self.repo, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        return data, data["warnings"]

    def test_defaults_in_every_output(self):
        data, warnings = self.resolved({})
        self.assertEqual(warnings, [])
        for key, value in DEFAULT_SETTINGS.items():
            self.assertEqual(data[key], value, key)
        self.assertIs(data["rebaseInProgress"], False)
        keys = list(data)
        self.assertEqual(keys[keys.index("workDir"):keys.index("hooks") + 1],
                         ["workDir", "docs", "checks", "ci", "pullRequest", "rounds", "implement", "hooks"])
        git(self.repo, "switch", "-q", "-c", "spike/x")
        data, _ = self.resolved({})
        self.assertEqual(data["hooks"], DEFAULT_SETTINGS["hooks"])

    def test_custom_values(self):
        data, warnings = self.resolved({
            "workDir": "work/tasks", "rounds": {"cap": {"S": 1, "L": 9}},
            "implement": {"maxFixAttempts": 0, "autoAdvance": False},
            "hooks": {"stopLint": True, "maxCheckAttempts": 5}})
        self.assertEqual(warnings, [])
        self.assertEqual(data["workDir"], "work/tasks")
        self.assertEqual(data["rounds"], {"cap": {"S": 1, "M": 3, "L": 9}})
        self.assertEqual(data["implement"], {"maxFixAttempts": 0, "autoAdvance": False})
        self.assertEqual(data["hooks"], {"stopLint": True, "maxCheckAttempts": 5})

    def test_invalid_values_take_their_default(self):
        cases = (
            ({"rounds": None}, "rounds", DEFAULT_SETTINGS["rounds"]),
            ({"rounds": {"cap": [2, 3, 5]}}, "rounds", DEFAULT_SETTINGS["rounds"]),
            ({"rounds": {"cap": {"S": 0}}}, "rounds", DEFAULT_SETTINGS["rounds"]),
            ({"rounds": {"cap": {"M": True}}}, "rounds", DEFAULT_SETTINGS["rounds"]),
            ({"rounds": {"cap": {"L": 2.5}}}, "rounds", DEFAULT_SETTINGS["rounds"]),
            ({"rounds": {"cap": {"L": "5"}}}, "rounds", DEFAULT_SETTINGS["rounds"]),
            ({"implement": {"maxFixAttempts": -1}}, "implement", DEFAULT_SETTINGS["implement"]),
            ({"implement": {"maxFixAttempts": False}}, "implement", DEFAULT_SETTINGS["implement"]),
            ({"implement": {"autoAdvance": 1}}, "implement", DEFAULT_SETTINGS["implement"]),
            ({"implement": {"autoAdvance": "true"}}, "implement", DEFAULT_SETTINGS["implement"]),
            ({"implement": "fast"}, "implement", DEFAULT_SETTINGS["implement"]),
            ({"hooks": {"stopLint": None}}, "hooks", DEFAULT_SETTINGS["hooks"]),
            ({"hooks": {"maxCheckAttempts": 0}}, "hooks", DEFAULT_SETTINGS["hooks"]),
            ({"hooks": {"maxCheckAttempts": True}}, "hooks", DEFAULT_SETTINGS["hooks"]),
            ({"hooks": []}, "hooks", DEFAULT_SETTINGS["hooks"]),
        )
        for config, key, expected in cases:
            with self.subTest(config=config):
                data, warnings = self.resolved(config)
                self.assertEqual(data[key], expected)
                self.assertEqual(len(warnings), 1, warnings)
                self.assertIn(key, warnings[0])

    def test_unknown_keys_are_ignored(self):
        data, warnings = self.resolved({"rounds": {"cap": {"XL": 9}, "max": 1}, "hooks": {"stopLint": True, "x": 1}})
        self.assertEqual(data["rounds"], DEFAULT_SETTINGS["rounds"])
        self.assertEqual(data["hooks"], {"stopLint": True, "maxCheckAttempts": 3})
        self.assertEqual(sorted(warnings), sorted([
            ".claude/loom.json: unknown key 'rounds.cap.XL' ignored",
            ".claude/loom.json: unknown key 'rounds.max' ignored",
            ".claude/loom.json: unknown key 'hooks.x' ignored"]))

    def test_warning_text(self):
        _, warnings = self.resolved({"hooks": {"maxCheckAttempts": True}})
        self.assertEqual(warnings, [".claude/loom.json: invalid 'hooks.maxCheckAttempts' (true); using the default 3 "
                                    "(an integer of at least 1)"])

    def test_hooks_see_the_validated_values(self):
        self.write_config({"hooks": {"stopLint": "yes", "maxCheckAttempts": -2}})
        cfg, warnings = ls.load_config(self.repo)
        self.assertEqual(cfg["hooks"], {"stopLint": False, "maxCheckAttempts": 3})
        self.assertEqual(len(warnings), 2)


class ArtifactFrontmatterTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.dir = self.task_dir("42-auth-flow")
        self.ticket(self.dir, mode="quick")
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")

    def research(self) -> None:
        self.artifact(self.dir, "02-research.md", "research", "approved",
                      git_commit=git(self.repo, "rev-parse", "--short", "HEAD"))

    def write_plan(self, status_line: str, phase_line: str = "phase: plan\n") -> None:
        self.research()
        write(os.path.join(self.dir, "04-plan.md"),
              "---\n%s%s---\n## Phase Overview\n- [ ] 1. A\n" % (phase_line, status_line))

    def test_status_case_and_whitespace(self):
        for line, status in (("status: Approved\n", "approved"), ("status: '  IN-REVIEW '\n", "in-review"),
                             ("status: DRAFT # note\n", "draft")):
            with self.subTest(line=line):
                self.write_plan(line)
                s = self.state()
                self.assertEqual(s["artifacts"][1]["status"], status)
                self.assertEqual(s["warnings"], [])

    def test_unknown_status_counts_as_in_review(self):
        for line, raw in (("status: in review\n", '"in review"'), ("status: blocked\n", '"blocked"'),
                          ("status: [approved]\n", '["approved"]'), ("status: done\n", '"done"')):
            with self.subTest(line=line):
                self.write_plan(line)
                s = self.state()
                self.assertEqual(s["artifacts"][1]["status"], "in-review")
                self.assertEqual(s["warnings"], [
                    "04-plan.md has an unknown status %s (allowed: draft, in-review, approved); treated as in-review"
                    % raw])
                self.assertEqual(s["next"]["command"], "/loom:iterate approve")  # never /loom:plan (overwrite)

    def test_unknown_status_in_event_context(self):
        self.write_plan("status: in review\n")
        self.assertEqual(ls.event_context(self.repo)["phase"], "plan")  # in review: the plan gate

    def test_file_name_wins_over_frontmatter_phase(self):
        self.write_plan("status: in-review\n", "phase: design\n")
        s = self.state()
        self.assertEqual(s["artifacts"][1]["phase"], "plan")
        self.assertEqual(s["warnings"], [
            '04-plan.md has phase "design" in its frontmatter; the file name says plan, and the file name wins'])
        self.assertEqual(s["next"]["command"], "/loom:iterate approve")
        self.assertEqual(ls.event_context(self.repo)["phase"], "plan")
        self.write_plan("status: in-review\n", "phase: Plan\n")
        self.assertEqual(self.state()["warnings"], [])

    def test_phase_zero_is_a_phase(self):
        self.write_plan("status: approved\n")
        write(os.path.join(self.dir, "log.md"), "## Phase 0 — in-progress\n")
        s = self.state()
        self.assertEqual(s["implementation"]["inProgress"], 0)
        self.assertEqual(s["next"]["command"], "/loom:implement")
        self.assertIn("phase 0 is in progress", s["next"]["reason"])
        self.assertEqual(ls.event_context(self.repo)["implementationPhase"], 0)
        self.assertEqual(run_loom_state(self.repo, "--line").stdout, "#42 · quick · impl 0/2 · in progress\n")

    def test_ticket_pr_forms(self):
        for line, number, warned in (("pr: #57\n", 57, False), ("pr: '#57'\n", 57, False), ("pr: 57\n", 57, False),
                                     ("pr: 0\n", None, True), ("pr: '#0'\n", None, True), ("pr: -5\n", None, True),
                                     ("pr: abc\n", None, True), ("pr: ²\n", None, True), ("pr: 5.7\n", None, True),
                                     ("pr: # 57\n", None, False), ("pr:\n", None, False)):
            with self.subTest(line=line):
                write(os.path.join(self.dir, "00-ticket.md"), "---\nmode: quick\nissue: 42\n%s---\n" % line)
                s = self.state()
                self.assertEqual(s["task"]["pr"], number)
                self.assertEqual(any("invalid pr" in w for w in s["warnings"]), warned, s["warnings"])
                proc = run_loom_state(self.repo, "--line")
                self.assertEqual((proc.returncode, proc.stderr), (0, ""))

    def test_line_shows_only_the_mode_phases(self):
        # A full task changed to quick: the leftover design does not show.
        self.research()
        self.artifact(self.dir, "03-design.md", "design", "in-review", "## Open Questions\n**Q1. A?**\n")
        self.assertEqual(run_loom_state(self.repo, "--line").stdout, "#42 · quick · research:approved\n")
        self.artifact(self.dir, "04-plan.md", "plan", "in-review", "## Open Questions\n**Q1. A?**\n")
        self.assertEqual(run_loom_state(self.repo, "--line").stdout, "#42 · quick · plan:in-review · 1 open Q\n")
        s = self.state()
        self.assertEqual(s["next"]["reason"], "plan has 1 open question")


class LineModeTest(RepoTestCase):
    def test_line_skips_the_stale_check_and_the_docs_only_status(self):
        d = self.task_dir("42-x")
        self.ticket(d, mode="quick")
        self.artifact(d, "02-research.md", "research", "approved", "src/a.py\n")  # no git_commit
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        write(self.path("docs", "x.md"), "x\n")
        calls = []
        original = ls.working_tree_status
        ls.working_tree_status = lambda *a, **k: (calls.append(k), original(*a, **k))[1]
        self.addCleanup(setattr, ls, "working_tree_status", original)
        s = ls.compute_state(self.repo, for_line=True)
        self.assertEqual(len(calls), 1)
        self.assertFalse(any("git_commit" in w for w in s["warnings"]))
        self.assertEqual(ls.format_line(s), "#42 · quick · research:approved")
        calls.clear()
        s = ls.compute_state(self.repo)
        self.assertEqual(len(calls), 2)
        self.assertTrue(any("git_commit" in w for w in s["warnings"]))


class TicketModeTest(RepoTestCase):
    """The ticket mode is normalized; an invalid mode routes to a mode change before everything else."""

    def setUp(self):
        super().setUp()
        self.dir = self.task_dir("42-x")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        self.artifact(self.dir, "02-research.md", "research", "approved",
                      git_commit=git(self.repo, "rev-parse", "--short", "HEAD"))
        self.artifact(self.dir, "04-plan.md", "plan", "approved", "## Phase Overview\n- [x] 1. A\n- [ ] 2. B\n")

    def write_ticket(self, mode_line: str, extra: str = "") -> None:
        write(os.path.join(self.dir, "00-ticket.md"), "---\n%sissue: 42\n%s---\n" % (mode_line, extra))

    def test_mode_is_normalized(self):
        for line in ("mode: Quick\n", "mode: ' QUICK '\n", "mode: quick # small\n"):
            with self.subTest(line=line):
                self.write_ticket(line)
                s = self.state()
                self.assertEqual(s["task"]["mode"], "quick")
                self.assertEqual(s["warnings"], [])
                self.assertEqual(s["next"]["command"], "/loom:implement")
                self.assertEqual(ls.event_context(self.repo)["phase"], "implement")

    def test_invalid_mode_with_an_approved_plan(self):
        cases = {
            "in progress": lambda: write(os.path.join(self.dir, "log.md"), "## Phase 2 — in-progress\n"),
            "dirty": lambda: write(self.path("notes.txt"), "x\n"),
            "ticket pr": lambda: self.write_ticket("mode: fast\n", "pr: 57\n"),
        }
        for name, prepare in cases.items():
            with self.subTest(case=name):
                self.write_ticket("mode: fast\n")
                for path in (os.path.join(self.dir, "log.md"), self.path("notes.txt")):
                    if os.path.exists(path):
                        os.remove(path)
                prepare()
                s = self.state()
                self.assertEqual(s["task"]["mode"], "fast")
                self.assertTrue(any("no valid mode" in w for w in s["warnings"]), s["warnings"])
                self.assertEqual(s["next"], {"command": "/loom:iterate mode <oneshot|quick|full>",
                                             "reason": "00-ticket.md has no valid mode; set it with a mode change"})


class PlanParseErrorTest(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.dir = self.task_dir("42-x")
        self.ticket(self.dir, mode="quick")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")

    def flag(self, plan_body, status="approved", phase="plan"):
        write(os.path.join(self.dir, "04-plan.md"),
              "---\nphase: %s\nstatus: %s\n---\n%s" % (phase, status, plan_body))
        s = self.state()
        return s["implementation"]["planParseError"], s["warnings"]

    def test_flag(self):
        self.assertEqual(self.flag("## Phase Overview\n- [ ] 1. A\n")[0], False)
        self.assertEqual(self.flag("## Phase Overview\nnone yet\n")[0], True)
        self.assertEqual(self.flag("## Phase Overview\n- [ ] 1. A\n```\nopen fence\n")[0], True)
        self.assertEqual(self.flag("```\n## Phase Overview\n- [ ] 1. A\n")[0], True)
        # Warnings that name 04-plan.md but are not plan-parse problems.
        flag, warnings = self.flag("## Phase Overview\n- [ ] 1. A\n", status="in review", phase="design")
        self.assertEqual(flag, False)
        self.assertEqual(len([w for w in warnings if "04-plan.md" in w]), 2)

    def test_flag_without_a_plan(self):
        self.assertIs(self.state()["implementation"]["planParseError"], False)
        self.assertIs(ls.implementation_progress("oneshot", None, None)[0]["planParseError"], False)


class TicketPrWithoutPrStateTest(RepoTestCase):
    def test_phases_left_goes_to_implement(self):
        d = self.task_dir("42-x")
        self.ticket(d, mode="quick", pr=57)
        self.artifact(d, "02-research.md", "research", "approved")
        self.artifact(d, "04-plan.md", "plan", "approved", "## Phase Overview\n- [x] 1. A\n- [ ] 2. B\n")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        s = self.state()
        self.assertEqual(s["next"], {"command": "/loom:implement", "reason":
                                     "PR #57 exists (its state was not read) and 1 of 2 implementation phases are done"})
        self.artifact(d, "04-plan.md", "plan", "approved", "## Phase Overview\n- [x] 1. A\n- [x] 2. B\n")
        self.assertEqual(self.state()["next"]["command"], "/loom:finish-task")


class RebaseInProgressTest(RepoTestCase):
    """A stopped rebase of the task branch (HEAD detached) keeps the task (LOOM_SPEC.md 8.2)."""

    def setUp(self):
        super().setUp()
        self.commit_file("app.txt", "base\n", "base")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        self.dir = self.task_dir("42-x")
        self.ticket(self.dir, mode="quick")
        self.artifact(self.dir, "02-research.md", "research", "approved")
        self.artifact(self.dir, "04-plan.md", "plan", "approved", "## Phase Overview\n- [x] 1. A\n- [ ] 2. B\n")
        write(os.path.join(self.dir, "log.md"), "## Phase 1 — done — abc1234\n")
        self.commit_file("app.txt", "task\n", "task change")
        git(self.repo, "switch", "-q", "main")
        self.commit_file("app.txt", "main\n", "main change")

    def conflicted_rebase(self, cwd, *options):
        proc = subprocess.run(["git", "rebase"] + list(options) + ["main", "feat/42-x"], cwd=cwd,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(proc.returncode, 0, "the rebase should stop on a conflict")
        self.assertEqual(subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=cwd).returncode, 1)

    def assert_rebasing(self, cwd):
        s = ls.compute_state(cwd)
        self.assertEqual(s["branch"], "feat/42-x")
        self.assertIs(s["rebaseInProgress"], True)
        self.assertFalse(s["onMain"])
        self.assertEqual(s["task"]["number"], 42)
        self.assertEqual(s["next"], {"command": "/loom:iterate rebase", "reason":
                                     "a rebase of feat/42-x is in progress and has to be continued or aborted"})
        self.assertIn("a rebase of feat/42-x is in progress (HEAD is detached); continue it with "
                      "`git rebase --continue` or abort it with `git rebase --abort`", s["warnings"])
        context = ls.event_context(cwd)
        self.assertIsNotNone(context)
        self.assertEqual((context["phase"], context["implementationPhase"]), ("implement", 2))
        self.assertEqual(run_loom_state(cwd, "--line").stdout, "#42 · quick · impl 1/2\n")
        return s

    def test_merge_backend(self):
        self.conflicted_rebase(self.repo)
        self.assert_rebasing(self.repo)
        git(self.repo, "rebase", "--abort")
        s = self.state()
        self.assertIs(s["rebaseInProgress"], False)
        self.assertEqual(s["next"]["command"], "/loom:implement")

    def test_apply_backend(self):
        self.conflicted_rebase(self.repo, "--apply")
        self.assertTrue(os.path.isdir(self.path(".git", "rebase-apply")))
        self.assert_rebasing(self.repo)

    def test_linked_worktree(self):
        git(self.repo, "switch", "-q", "--detach")
        worktree = os.path.join(self.tmp, "wt")
        git(self.repo, "worktree", "add", "-q", worktree, "feat/42-x")
        self.dir = self.task_dir("42-x")  # the task directory is ignored, so the worktree needs its own copy
        shutil.copytree(self.dir, os.path.join(worktree, ".loom", "tasks", "42-x"))
        self.conflicted_rebase(worktree)
        self.assert_rebasing(worktree)
        self.assertIs(ls.compute_state(self.repo)["rebaseInProgress"], False)

    def test_plain_detached_head(self):
        git(self.repo, "switch", "-q", "--detach", "feat/42-x")
        s = self.state()
        self.assertIsNone(s["branch"])
        self.assertIs(s["rebaseInProgress"], False)
        self.assertIsNone(s["task"])
        self.assertIn("detached HEAD", s["next"]["reason"])
        self.assertIsNone(ls.event_context(self.repo))


class UnknownWorkingTreeTest(RepoTestCase):
    def test_git_status_failure_fails_closed(self):
        d = self.task_dir("42-x")
        self.ticket(d, mode="oneshot")
        write(os.path.join(d, "log.md"), "## Phase 1 — done — abc1234\n")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        self.assertEqual(self.state()["next"]["command"], "/loom:describe-pr")
        with open(self.path(".git", "index"), "wb") as fh:
            fh.write(b"not an index")
        s = self.state()
        self.assertIsNone(s["workingTree"])
        self.assertTrue(any(w.startswith("git status failed") for w in s["warnings"]), s["warnings"])
        self.assertEqual(s["next"]["command"], "/loom:iterate <feedback>")
        self.assertIn("git status failed", s["next"]["reason"])


class OutputEncodingTest(RepoTestCase):
    def test_ascii_locale(self):
        git(self.repo, "switch", "-q", "-c", "feat/42-ünïcode")
        d = self.task_dir("42-ünïcode")
        write(os.path.join(d, "00-ticket.md"), "---\nmode: full\nurl: https://example.com/Ж\n---\n")
        for env in ({"PYTHONIOENCODING": "ascii"}, {"PYTHONIOENCODING": "", "LC_ALL": "C", "LANG": "C"}):
            with self.subTest(env=env):
                proc = run_loom_state_env(self.repo, env, "--json")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                data = json.loads(proc.stdout.decode("utf-8"))
                self.assertEqual(data["task"]["url"], "https://example.com/Ж")
                proc = run_loom_state_env(self.repo, env, "--line")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.decode("utf-8"), "#42 · full · ticket\n")


class PrRequiredCheckTest(RepoTestCase):
    """`pr.requiredCheck` from statusCheckRollup by the name in ci.requiredCheck."""

    loom_config = {"ci": {"requiredCheck": "build"}}

    def setUp(self):
        super().setUp()
        d = self.task_dir("42-x")
        self.ticket(d, mode="quick")
        self.artifact(d, "02-research.md", "research", "approved")
        self.artifact(d, "04-plan.md", "plan", "approved", "## Phase Overview\n- [x] 1. A\n")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")

    def fake_gh(self, output: str) -> dict:
        bindir = os.path.join(self.tmp, "fakebin")
        gh = write(os.path.join(bindir, "gh"), "#!/bin/sh\ncat <<'EOF'\n%s\nEOF\n" % output)
        os.chmod(gh, 0o755)
        proc = run_loom_state_env(self.repo, {"PATH": bindir + os.pathsep + os.environ.get("PATH", "")}, "--pr")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.decode("utf-8"))

    def pr(self, rollup):
        payload = {"number": 57, "state": "OPEN", "reviewDecision": "", "mergeStateStatus": "CLEAN",
                   "statusCheckRollup": rollup}
        return self.fake_gh(json.dumps(payload))

    @staticmethod
    def run_(name, conclusion="SUCCESS", status="COMPLETED", started=None):
        item = {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}
        if started:
            item["startedAt"] = started
        return item

    def test_states_and_routing(self):
        lint_fails = self.run_("lint", "FAILURE")
        cases = (
            ([self.run_("build"), lint_fails], "passing", "failing", "/loom:finish-task"),
            ([self.run_("build", "FAILURE"), self.run_("lint")], "failing", "failing", "/loom:iterate"),
            ([self.run_("build", "", "IN_PROGRESS"), lint_fails], "pending", "failing", "/loom:finish-task"),
            ([self.run_("test"), lint_fails], "missing", "failing", "/loom:iterate"),
            ([{"__typename": "StatusContext", "context": "build", "state": "SUCCESS"}], "passing", "passing",
             "/loom:finish-task"),
        )
        for rollup, required, overall, command in cases:
            with self.subTest(required=required, rollup=rollup):
                s = self.pr(rollup)
                self.assertEqual((s["pr"]["requiredCheck"], s["pr"]["checks"]), (required, overall))
                self.assertEqual(s["next"]["command"], command)
                others = [w for w in s["warnings"] if "besides the required check" in w]
                if required != "missing" and lint_fails in rollup:
                    self.assertEqual(others, ["PR #57 has failing checks besides the required check 'build': lint"])
                else:
                    self.assertEqual(others, [])

    def test_latest_entry_wins(self):
        rollup = [self.run_("build", "SUCCESS", started="2026-11-12T10:00:00Z"),
                  self.run_("build", "FAILURE", started="2026-11-12T09:00:00Z")]
        self.assertEqual(self.pr(rollup)["pr"]["requiredCheck"], "passing")
        rollup = [self.run_("build", "FAILURE"), self.run_("build", "SUCCESS")]
        self.assertEqual(self.pr(rollup)["pr"]["requiredCheck"], "passing")

    def test_gh_output_that_is_not_an_object(self):
        for output in ("[]", '"x"', "57"):
            with self.subTest(output=output):
                s = self.fake_gh(output)
                self.assertIsNone(s["pr"])
                self.assertIn("gh pr view returned no JSON object; PR state unknown", s["warnings"])


class MetricsRobustnessTest(RepoTestCase):
    def test_infinite_and_absurd_durations_are_skipped(self):
        d = self.task_dir("42-x")
        self.ticket(d, mode="oneshot")
        git(self.repo, "switch", "-q", "-c", "feat/42-x")
        lines = []
        for i, duration in enumerate(("Infinity", "NaN", "-Infinity", "1e400", "99999999999", "10" + "0" * 400, "12.5")):
            lines.append('{"event":"start","agent_id":"a%d","agent":"implementer","phase":"implement"}' % i)
            lines.append('{"event":"stop","agent_id":"a%d","agent":"implementer","phase":"implement",'
                         '"duration_s":%s}' % (i, duration))
        write(os.path.join(d, "events.jsonl"), "\n".join(lines) + "\n")
        proc = run_loom_state(self.repo, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        metrics = json.loads(proc.stdout)["task"]["metrics"]
        self.assertEqual(metrics["subagentSeconds"], 12.5)
        self.assertIn("subagent time 12 s", metrics["line"])

if __name__ == "__main__":
    unittest.main()
