"""setup templates, the setup handover, the ticket template, the slug helper, and the status line script.

Standard library only. Fixture repositories live in temporary directories.
"""
from __future__ import annotations

import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Dict, List, Optional

from loomtest import LOOM_STATE, ROOT, RepoTestCase, git, loom_state, run_loom_state, write

ls = loom_state()

SKILLS = os.path.join(ROOT, "skills")
SETUP = os.path.join(SKILLS, "setup")
TEMPLATES = os.path.join(SETUP, "references", "templates")
TICKET_TEMPLATE = os.path.join(SKILLS, "start-task", "references", "ticket-template.md")
SPEC = os.path.join(ROOT, "LOOM_SPEC.md")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def spec_section(start: str, end: str) -> str:
    text = read(SPEC)
    for heading in (start, end):
        if heading not in text:
            raise AssertionError("LOOM_SPEC.md has no heading %r (renamed?)" % heading)
    return text.split(start, 1)[1].split(end, 1)[0]


def template(*parts: str) -> str:
    return read(os.path.join(TEMPLATES, *parts))


def fill_ticket(task: str, mode: str, issue: int, size: Optional[str] = "S", title: str = "Add token refresh",
                labels: str = "type:feat, size:S", body: str = "## Context\n\nWhy.\n") -> str:
    """Fill ticket-template.md the way start-task (and setup) do."""
    url = "https://github.com/o/r/issues/%d" % issue
    text = read(TICKET_TEMPLATE)
    text = text.replace("<n>-<slug>", task).replace("<oneshot | quick | full>", mode)
    if size is None:
        text = re.sub(r"(?m)^size: .*\n", "", text)
    else:
        text = text.replace("<S | M | L>", size)
    text = text.replace("issue: <n>", "issue: %d" % issue).replace("<issue URL>", url)
    text = text.replace("<issue title>", title).replace("<labels, comma-separated, or None>", labels)
    return text.replace("<issue body, verbatim>", body)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class LoomJsonTemplateTest(unittest.TestCase):
    def test_equals_spec_19_1(self):
        section = spec_section("### 19.1 `.claude/loom.json` (committed)", "### 19.2 Issue labels")
        expected = json.loads(re.search(r"```json\n(.*?)```", section, re.DOTALL).group(1))
        self.assertEqual(json.loads(template("loom.json")), expected)

    def test_equals_loom_state_defaults(self):
        self.assertEqual(json.loads(template("loom.json")), ls.DEFAULT_CONFIG)


def spec_docs_tree() -> List[str]:
    """Paths below docs/ in the §15 tree: files, and directories as `dir/`."""
    section = spec_section("## 15. Project Documentation Structure", "## 16. Git Conventions")
    tree = re.search(r"```\n(.*?)```", section, re.DOTALL).group(1).splitlines()
    paths: List[str] = []
    stack: List[str] = []
    for line in tree:
        m = re.match(r"^((?:│   |    )*)[├└]── (\S+)", line)
        if not m:
            continue
        depth = len(m.group(1)) // 4
        stack = stack[:depth] + [m.group(2)]
        paths.append("".join(stack))
    return paths


class DocsSkeletonTest(unittest.TestCase):
    def template_paths(self) -> List[str]:
        root = os.path.join(TEMPLATES, "docs")
        found = []
        for base, dirs, files in os.walk(root):
            for name in files:
                found.append(os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/"))
        return sorted(found)

    def test_matches_spec_15_tree(self):
        spec = spec_docs_tree()
        self.assertIn("product/vision.md", spec)
        expected = set()
        for path in spec:
            if path.endswith("/"):
                children = [p for p in spec if p.startswith(path) and p != path]
                # A directory whose only children are placeholders (NNNN-*.md, <n>-<slug>.md) starts empty.
                if all(re.search(r"[<*]", p[len(path):]) for p in children):
                    expected.add(path + ".gitkeep")
            elif not re.search(r"[<*]", path):
                expected.add(path)
        self.assertEqual(set(self.template_paths()), expected)

    def test_skeleton_by_docs_role(self):
        """setup writes one skeleton target per docs role, at the path of the docs map (LOOM_SPEC.md 15)."""
        body = read(os.path.join(SETUP, "SKILL.md"))
        table = body.split("The docs skeleton, by docs role.", 1)[1].split("\n\n", 2)[1]
        rows = re.findall(r"^\| `(\w+)` \| `([^`]+)` \| `templates/([^`]+)`", table, re.MULTILINE)
        self.assertEqual([r[0] for r in rows], ["vision", "overview", "conventions", "decisions", "tasks"])
        defaults = ls.default_docs("docs")
        for role, target, skeleton in rows:
            with self.subTest(role=role):
                self.assertTrue(os.path.isfile(os.path.join(TEMPLATES, *skeleton.split("/"))), skeleton)
                # Before loom.json exists, the default path of a role is its skeleton path below templates/.
                default = defaults[role]["dir"] if role == "decisions" else defaults[role]
                expected = default + "/.gitkeep" if role in ("decisions", "tasks") else default
                self.assertEqual(skeleton, expected)
                self.assertIn("docs.%s" % ("decisions.dir" if role == "decisions" else role), target)
        self.assertIn("the path of its skeleton file relative to `templates/`", body)
        self.assertIn("Then run `loom-state --json`. Take `checks` and the docs paths (`docs`) from it", body)

    def test_spec_9_1_lists_the_skeleton(self):
        section = spec_section("### 9.1 `setup`", "### 9.2 `backlog`")
        for path in ("product/vision.md", "architecture/overview.md", "architecture/decisions/", "conventions.md", "tasks/"):
            with self.subTest(path=path):
                self.assertIn("`%s`" % path, section)

    def test_skeleton_files_have_a_title_and_sections(self):
        for rel in ("product/vision.md", "architecture/overview.md", "conventions.md"):
            with self.subTest(file=rel):
                text = template("docs", *rel.split("/"))
                self.assertRegex(text, r"^# \S")
                self.assertGreaterEqual(len(re.findall(r"(?m)^## ", text)), 3)
                self.assertIn("/loom:setup", text)

    def test_vision_skeleton_marker_matches_backlog(self):
        marker = "Skeleton written by /loom:setup"
        self.assertIn(marker, template("docs", "product", "vision.md"))
        self.assertIn(marker, read(os.path.join(SKILLS, "backlog", "SKILL.md")))
        for heading in ("## What", "## For Whom", "## Goals", "## Non-Goals"):
            with self.subTest(heading=heading):
                self.assertIn(heading, template("docs", "product", "vision.md"))

    def test_claude_md_is_short_and_links_docs(self):
        text = template("CLAUDE.md")
        self.assertLessEqual(len(text.splitlines()), 30)
        # Doc links are the docs map paths of the state (LOOM_SPEC.md 15), filled in by setup.
        for link in ("`<docs.vision>`", "`<docs.overview>`", "`<docs.decisions.dir>/`", "`<docs.conventions>`",
                     "`<docs.tasks>/`", "<checks.check>", "/loom:start-task", "/loom:next"):
            with self.subTest(link=link):
                self.assertIn(link, text)


def yaml_block(lines: List[str], key: str, indent: int) -> List[str]:
    """Lines of the block under `<indent spaces><key>:` (line-based; no YAML library)."""
    prefix = " " * indent + key + ":"
    start = next(i for i, l in enumerate(lines) if l.rstrip() == prefix or l.startswith(prefix + " "))
    block = []
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith(" " * (indent + 1)):
            break
        block.append(line)
    return block


class CiTemplateTest(unittest.TestCase):
    TEMPLATES = {"ci.python-uv.yml": ["uv sync --locked", "enable-cache: true", "make check"],
                 "ci.node.yml": ["npm ci", "npm run check", "cache: npm"]}

    def lines(self, name: str) -> List[str]:
        return [l for l in template(name).splitlines() if not l.lstrip().startswith("#")]

    def test_triggers(self):
        for name in self.TEMPLATES:
            with self.subTest(template=name):
                on = [l.strip() for l in yaml_block(self.lines(name), "on", 0) if l.strip()]
                self.assertEqual(on, ["pull_request:", "push:", "branches: [<main>]"])

    def test_one_job_named_check(self):
        for name in self.TEMPLATES:
            with self.subTest(template=name):
                jobs = yaml_block(self.lines(name), "jobs", 0)
                job_ids = [l.strip()[:-1] for l in jobs if re.match(r"^  [\w-]+:$", l)]
                self.assertEqual(job_ids, ["check"])
                self.assertIn("    name: check", jobs)

    def test_pinned_actions(self):
        for name in self.TEMPLATES:
            uses = re.findall(r"(?m)^\s*-?\s*uses: (\S+)$", template(name))
            self.assertTrue(uses)
            for action in uses:
                with self.subTest(template=name, action=action):
                    self.assertRegex(action, r"^[\w.-]+/[\w.-]+@v\d+\.\d+\.\d+$")
            with self.subTest(template=name):
                self.assertRegex(template(name), r"checked on \d{4}-\d{2}-\d{2}")

    def test_steps_and_single_version(self):
        for name, needles in self.TEMPLATES.items():
            text = template(name)
            for needle in needles:
                with self.subTest(template=name, needle=needle):
                    self.assertIn(needle, text)
            with self.subTest(template=name):
                self.assertEqual(len(re.findall(r"(?m)^\s+(python|node)-version: ", text)), 1)
                self.assertNotIn("matrix", text)
                self.assertNotIn("${", text)

    def test_versions_match_the_spec_and_the_node_recipe(self):
        spec = spec_section("### 17.2 CI workflow (v1)", "### 17.3 Ruleset")
        node = read(os.path.join(SETUP, "references", "stacks", "node.md"))
        for name in self.TEMPLATES:
            for action in re.findall(r"uses: (\S+)", template(name)):
                with self.subTest(action=action):
                    self.assertIn("`%s`" % action, spec)
        for action in re.findall(r"uses: (\S+)`", node):
            with self.subTest(action=action):
                self.assertIn("`%s`" % action, spec)


class MakefileTemplateTest(unittest.TestCase):
    def test_tab_recipes_and_targets(self):
        text = template("Makefile")
        targets = re.findall(r"(?m)^([a-z]+):", text)
        self.assertEqual(targets, ["lint", "typecheck", "test", "check"])
        self.assertIn(".PHONY: lint typecheck test check", text)
        self.assertIn("check: lint typecheck test", text)
        recipes = [l for l in text.splitlines() if l.startswith((" ", "\t"))]
        self.assertTrue(recipes)
        for line in recipes:
            with self.subTest(line=line):
                self.assertTrue(line.startswith("\t") and not line.startswith("\t "), repr(line))
        for command in ("uv run ruff check .", "uv run ruff format --check .", "uv run pyright", "uv run pytest"):
            with self.subTest(command=command):
                self.assertIn("\t" + command, text)

    def test_matches_spec_17_1(self):
        section = spec_section("### 17.1 Single entry point", "### 17.2 CI workflow")
        block = re.search(r"```makefile\n(.*?)```", section, re.DOTALL).group(1)
        body = "\n".join(l for l in template("Makefile").splitlines() if l and not l.startswith(("#", ".PHONY")))
        self.assertEqual(body, "\n".join(l for l in block.splitlines() if l))

    @unittest.skipUnless(shutil.which("make"), "make is not installed")
    def test_make_parses_it(self):
        proc = subprocess.run(["make", "-n", "--no-print-directory", "-f", os.path.join(TEMPLATES, "Makefile"), "check"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, cwd=tempfile.gettempdir())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), [
            "uv run ruff check .", "uv run ruff format --check .", "uv run pyright", "uv run pytest || [ $? -eq 5 ]",
        ])

    @unittest.skipUnless(shutil.which("make"), "make is not installed")
    def test_no_tests_passes_and_failures_fail(self):
        # The `test` recipe accepts exit status 5 (pytest: no tests collected) and nothing else.
        tmp = tempfile.mkdtemp(prefix="loom-make-")
        self.addCleanup(shutil.rmtree, tmp, True)
        recipe = [l for l in template("Makefile").splitlines() if "pytest" in l and l.startswith("\t")][0]
        for code, expected in ((0, 0), (5, 0), (1, 2), (2, 2)):
            with self.subTest(code=code):
                with open(os.path.join(tmp, "Makefile"), "w") as fh:
                    fh.write("test:\n" + recipe.replace("uv run pytest", "sh -c 'exit %d'" % code) + "\n")
                proc = subprocess.run(["make", "-s", "test"], cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(proc.returncode, expected)


def spec_19_3() -> str:
    return spec_section("### 19.3 `.claude/settings.json`", "## 20. Testing the Harness")


class SettingsTemplateTest(unittest.TestCase):
    def data(self) -> Dict:
        return json.loads(template("settings.json"))

    def test_marketplace_and_plugin(self):
        data = self.data()
        market = json.loads(read(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
        plugin = json.loads(read(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        name = market["name"]
        self.assertEqual(data["extraKnownMarketplaces"], {name: {"source": {"source": "github", "repo": "mmosvlad1/loom"}}})
        self.assertEqual(data["enabledPlugins"], {"%s@%s" % (plugin["name"], name): True})
        self.assertIn("mmosvlad1/loom", plugin["repository"])
        self.assertEqual(market["plugins"][0]["source"], "./", "the plugin sits at the repository root")
        # A project-enabled plugin still needs a per-clone install (LOOM_SPEC.md 19.3, 24.2).
        self.assertIn("claude plugin install loom@loom --scope project", spec_19_3())
        self.assertNotIn("loads without a per-user install", spec_19_3())

    def test_rule_syntax(self):
        perms = self.data()["permissions"]
        for rule in perms["allow"] + perms["ask"]:
            with self.subTest(rule=rule):
                self.assertRegex(rule, r"^Bash\([^()]+\)$")
                self.assertNotIn(":*", rule)
        self.assertEqual(set(perms), {"allow", "ask"})

    def spec_items(self, label: str) -> List[str]:
        section = spec_19_3()
        part = section.split(label, 1)[1]
        part = part.split("\n- **", 1)[0] if label.startswith("- **Not**") else part.split("\n- **Not**", 1)[0]
        return re.findall(r"`([^`]+)`", part)

    def test_allowlist_matches_19_3(self):
        allow = self.data()["permissions"]["allow"]
        items = self.spec_items("- Permission allowlist")
        expected = []
        for item in items:
            if item.startswith(("git ", "gh ")):
                expected.append("Bash(%s *)" % item)
            elif item == "make *":
                expected.append("Bash(make *)")
            elif item.startswith("loom-state "):
                expected.append("Bash(%s)" % item)
        self.assertIn("Bash(git status *)", expected)
        self.assertIn("Bash(loom-state --slug *)", expected)
        for rule in expected:
            with self.subTest(rule=rule):
                self.assertIn(rule, allow)
        moves = [r for r in allow if r.startswith(("Bash(mv ", "Bash(mkdir "))]
        self.assertEqual(len(moves), 3)
        for rule in moves:
            with self.subTest(rule=rule):
                self.assertTrue(all(p.startswith(".loom/") for p in rule[5:-1].split()[1:] if p != "-p"), rule)
        self.assertEqual(set(allow), set(expected) | set(moves), "every allow rule comes from §19.3")

    def test_not_allowlisted_are_ask_rules(self):
        perms = self.data()["permissions"]
        items = self.spec_items("- **Not** allowlisted")
        commands = [i for i in items if i.startswith(("git ", "gh "))]
        self.assertEqual(len(commands), 7)
        self.assertEqual(perms["ask"], ["Bash(%s *)" % c for c in commands])
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(any(r.startswith("Bash(%s" % command) for r in perms["allow"]))

    def test_skill_loom_state_rules_are_allowlisted(self):
        # The allowed-tools grant lasts one turn; the project allowlist must cover later calls.
        allow = self.data()["permissions"]["allow"]
        for name in os.listdir(SKILLS):
            path = os.path.join(SKILLS, name, "SKILL.md")
            if not os.path.isfile(path):
                continue
            for rule in re.findall(r"Bash\(loom-state [^)]*\)", read(path).split("\n---", 1)[0]):
                if name == "setup" and rule == "Bash(loom-state --setup-path *)":
                    # setup runs --setup-path before the project settings exist; §19.3 does not list it.
                    continue
                with self.subTest(skill=name, rule=rule):
                    self.assertIn(rule, allow)

    def test_status_line(self):
        status = self.data()["statusLine"]
        self.assertEqual(status["type"], "command")
        self.assertIn(".claude/loom-statusline.py", status["command"])
        self.assertIn("git rev-parse --show-toplevel 2>/dev/null", status["command"])
        self.assertTrue(status["command"].endswith(" 2>/dev/null"))
        self.assertIn(".claude/loom-statusline.py", spec_19_3())

    def test_stash_rules_never_lose_work(self):
        allow = self.data()["permissions"]["allow"]
        stash = sorted(r for r in allow if r.startswith("Bash(git stash"))
        self.assertEqual(stash, ["Bash(git stash list *)", "Bash(git stash pop *)", "Bash(git stash push *)",
                                 "Bash(git stash show *)"])
        flow = read(os.path.join(SKILLS, "_shared", "git-flow.md"))
        for command in re.findall(r"`(git stash [a-z]+)", flow):
            with self.subTest(command=command):
                self.assertIn("Bash(%s *)" % command, allow)

    def test_template_has_no_extra_keys(self):
        self.assertEqual(set(self.data()), {"$schema", "extraKnownMarketplaces", "enabledPlugins", "permissions", "statusLine"})


class SetupIssueTemplateTest(unittest.TestCase):
    def test_issue_format(self):
        text = template("setup-issue.md")
        self.assertEqual(re.findall(r"(?m)^## (.+)$", text), ["Context", "Acceptance Criteria", "Out of Scope"])
        self.assertRegex(text, r"(?m)^- \[ \] ")
        self.assertIn("/loom:finish-task", text)

    def test_onboarding_issue_format(self):
        text = template("setup-issue-onboarding.md")
        self.assertEqual(re.findall(r"(?m)^## (.+)$", text), ["Context", "Acceptance Criteria", "Out of Scope"])
        criteria = text.split("## Acceptance Criteria", 1)[1].split("## Out of Scope", 1)[0]
        self.assertGreaterEqual(len(re.findall(r"(?m)^- \[ \] ", criteria)), 5)
        for needle in ("full mode", "`ci.requiredCheck`", "`checks.check`", "540 seconds", "`@AGENTS.md`",
                       "docs role", "`.gitignore`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        out = text.split("## Out of Scope", 1)[1]
        for needle in ("follow-up issue", "No migration of issues, labels, or branches", "/loom:finish-task"):
            with self.subTest(needle=needle):
                self.assertIn(needle, out)
        self.assertNotRegex(text, r"<[a-z]")  # no placeholder: setup copies it as it is
        self.assertIn("`templates/setup-issue-onboarding.md`",
                      spec_section("#### 9.13.2 Kickoff (`setup`)", "#### 9.13.3"))

    def test_stack_recipes_name_existing_templates(self):
        for name in ("python-uv.md", "node.md"):
            text = read(os.path.join(SETUP, "references", "stacks", name))
            for ref in re.findall(r"`templates/([\w./-]+)`", text):
                with self.subTest(recipe=name, template=ref):
                    self.assertTrue(os.path.isfile(os.path.join(TEMPLATES, ref)), ref)


# ---------------------------------------------------------------------------
# Ticket template and setup handover through loom-state
# ---------------------------------------------------------------------------


class TicketTemplateRoundTripTest(RepoTestCase):
    def start(self, branch: str, task: str, text: str) -> None:
        git(self.repo, "switch", "-q", "-c", branch)
        write(os.path.join(self.task_dir(task), "00-ticket.md"), text)

    def test_frontmatter_parses(self):
        fm = ls.parse_frontmatter(fill_ticket("42-add-token-refresh", "full", 42, size="L"))
        self.assertEqual(fm, {"task": "42-add-token-refresh", "phase": "ticket", "mode": "full", "size": "L",
                              "issue": "42", "url": "https://github.com/o/r/issues/42"})

    def test_modes_route_to_their_first_phase(self):
        expected = {"oneshot": "/loom:implement", "quick": "/loom:research", "full": "/loom:research-questions"}
        for number, (mode, command) in enumerate(sorted(expected.items()), start=40):
            with self.subTest(mode=mode):
                git(self.repo, "switch", "-q", "main")
                self.start("feat/%d-add-token-refresh" % number, "%d-add-token-refresh" % number,
                           fill_ticket("%d-add-token-refresh" % number, mode, number, size="M"))
                state = self.state()
                self.assertEqual(state["warnings"], [])
                self.assertEqual(state["task"]["mode"], mode)
                self.assertEqual(state["task"]["size"], "M")
                self.assertEqual(state["task"]["url"], "https://github.com/o/r/issues/%d" % number)
                self.assertEqual(state["workingTree"], "clean")
                self.assertEqual(state["next"]["command"], command)

    def test_without_size(self):
        self.start("fix/7-crash", "7-crash", fill_ticket("7-crash", "quick", 7, size=None))
        state = self.state()
        self.assertEqual(state["warnings"], [])
        self.assertIsNone(state["task"]["size"])

    def test_verbatim_body_does_not_disturb_parsing(self):
        body = "## Context\n\n```python\nprint('x')\n```\n\n---\nstatus: approved\n## Phase 1 — done — abc\n"
        self.start("feat/9-x", "9-x", fill_ticket("9-x", "oneshot", 9, body=body))
        state = self.state()
        self.assertEqual(state["task"]["mode"], "oneshot")
        self.assertEqual(state["implementation"]["done"], 0)
        self.assertEqual(state["next"]["command"], "/loom:implement")

    def test_first_heading_is_the_issue_title(self):
        # finish-task finds the setup task by the first `# ` heading of 00-ticket.md.
        text = fill_ticket("3-loom-setup", "oneshot", 3, title="Set up loom", body="# Not this\n")
        heading = next(l for l in ls.split_frontmatter(text)[1].splitlines() if l.startswith("# "))
        self.assertEqual(heading, "# Set up loom")


class SetupHandoverTest(RepoTestCase):
    """A repository with the files /loom:setup writes routes to /loom:describe-pr (§9.1 step 2.4)."""

    loom_config = None  # setup writes loom.json itself

    def setUp(self) -> None:
        super().setUp()
        self.number = 3
        self.branch = "chore/%d-loom-setup" % self.number
        self.task = self.path(".loom", "tasks", "%d-loom-setup" % self.number)
        git(self.repo, "switch", "-q", "-c", self.branch)
        files = {
            ".claude/loom.json": template("loom.json"),
            ".claude/settings.json": template("settings.json"),
            ".claude/loom-statusline.py": template("loom-statusline.py"),
            ".github/workflows/ci.yml": template("ci.python-uv.yml").replace("<main>", "main"),
            "Makefile": template("Makefile"),
            "CLAUDE.md": template("CLAUDE.md"),
            "docs/product/vision.md": template("docs", "product", "vision.md"),
            "docs/architecture/overview.md": template("docs", "architecture", "overview.md"),
            "docs/architecture/decisions/.gitkeep": "",
            "docs/conventions.md": template("docs", "conventions.md"),
            "docs/tasks/.gitkeep": "",
        }
        for rel, text in files.items():
            path = self.path(*rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        self.files = sorted(files)

    def write_ticket(self) -> None:
        text = fill_ticket("%d-loom-setup" % self.number, "oneshot", self.number, size="S", title="Set up loom",
                           labels="type:chore, size:S, mode:oneshot", body=template("setup-issue.md"))
        write(os.path.join(self.task, "00-ticket.md"), text)

    def commit(self) -> str:
        git(self.repo, "add", "--", *self.files)
        write(os.path.join(self.task, "commit-msg.txt"), "chore(loom): set up loom (#%d)\n\nPhase 1: oneshot\n" % self.number)
        git(self.repo, "commit", "-q", "-F", os.path.join(self.task, "commit-msg.txt"))
        return git(self.repo, "rev-parse", "--short", "HEAD")

    def log(self, text: str) -> None:
        with open(os.path.join(self.task, "log.md"), "a", encoding="utf-8") as fh:
            fh.write(text)

    def done_entry(self, sha: str) -> str:
        return ("## Phase 1 — done — %s\nChecks: make check: pass; lint ✓ typecheck ✓ test ✓\n"
                "Reviewer: not run (the setup commit comes from /loom:setup); nits: None\n"
                "Deviations: None\nAdditions: None\nManual verification: None\n" % sha)

    def test_full_handover_routes_to_describe_pr(self):
        self.write_ticket()
        self.log("## Phase 1 — in-progress\nStarted: 2026-11-09\n\n")
        sha = self.commit()
        self.log("\n" + self.done_entry(sha))
        proc = run_loom_state(self.repo, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = json.loads(proc.stdout)
        self.assertEqual(state["warnings"], [])
        self.assertEqual(state["workingTree"], "clean")
        self.assertEqual(state["task"]["mode"], "oneshot")
        self.assertEqual(state["task"]["size"], "S")
        self.assertEqual(state["implementation"]["total"], 1)
        self.assertEqual(state["implementation"]["phases"][0], {"number": 1, "status": "done", "commit": sha})
        self.assertEqual(state["next"]["command"], "/loom:describe-pr")
        self.assertEqual(run_loom_state(self.repo, "--line").stdout.strip(), "#3 · oneshot · impl 1/1")

    def test_commit_message_and_finish_task_detection(self):
        self.write_ticket()
        self.commit()
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s"), "chore(loom): set up loom (#3)")
        self.assertEqual(git(self.repo, "log", "--format=%h", "--grep=^Phase 1: oneshot", "main..HEAD"),
                         git(self.repo, "rev-parse", "--short", "HEAD"))
        self.assertTrue(re.match(r"^chore/\d+-loom-setup$", self.branch))
        self.assertEqual(self.state()["task"]["slug"], "loom-setup")

    def test_interrupted_states_route_to_a_recovery(self):
        # loom.json written, no task directory yet: start-task, which sends the setup issue back to /loom:setup.
        self.assertEqual(self.state()["next"]["command"], "/loom:start-task #3")
        # Ticket and in-progress entry, commit done, no done entry: the setup task goes back to
        # /loom:setup (§9.12 row 2c), whose fast-path resume finds the commit.
        self.write_ticket()
        self.log("## Phase 1 — in-progress\nStarted: 2026-11-09\n")
        self.commit()
        state = self.state()
        self.assertTrue(state["task"]["setup"])
        self.assertEqual(state["next"]["command"], "/loom:setup")
        self.assertEqual(state["implementation"]["inProgress"], 1)

    def test_loom_json_must_exist_for_loom_state(self):
        os.remove(self.path(".claude", "loom.json"))
        self.assertEqual(run_loom_state(self.repo, "--json").stdout, "")


# ---------------------------------------------------------------------------
# Onboarding kickoff (§9.13.2, §9.13.3)
# ---------------------------------------------------------------------------

ONBOARDING = os.path.join(SETUP, "references", "onboarding.md")
QUESTIONS = os.path.join(SETUP, "references", "onboarding-questions.md")
FOUND_PLACEHOLDERS = {"instructionFiles": "<found.instructionFiles>", "workflows": "<found.workflows>",
                      "prTemplates": "<found.prTemplates>", "docsDirs": "<found.docsDirs>"}


def fill_questions(number: int, today: str, found: Dict[str, List[str]], added: List[str] = ()) -> str:
    """Fill onboarding-questions.md the way setup does (onboarding.md, "Research questions file")."""
    text = read(QUESTIONS).replace("<n>-loom-setup", "%d-loom-setup" % number).replace("YYYY-MM-DD", today)
    for key, placeholder in FOUND_PLACEHOLDERS.items():
        paths = found.get(key) or []
        text = text.replace(placeholder, ", ".join("`%s`" % p for p in paths) if paths else "None.")
    for offset, question in enumerate(added, start=8):
        text += "%d. %s\n" % (offset, question)
    return text


def kickoff_settings_text() -> str:
    return read(ONBOARDING).split("### Kickoff settings", 1)[1].split("\n### ", 1)[0]


def kickoff_left_out() -> List[str]:
    """The template rules that the kickoff leaves out, as the reference names them ("Leave out `<rule>`")."""
    return re.findall(r"Leave out `(Bash\([^`]+\))`", kickoff_settings_text())


def kickoff_no_keys() -> List[str]:
    """The keys the kickoff never writes, as the reference names them ("no `<key>`")."""
    line = next(l for l in kickoff_settings_text().splitlines() if l.startswith("- No other key"))
    return re.findall(r"no `([^`]+)`", line)


def kickoff_settings() -> Dict:
    """A new .claude/settings.json of the kickoff, built by the reference's rules from the template."""
    tpl = json.loads(template("settings.json"))
    skipped = set(kickoff_left_out())
    data: Dict = {}
    if "the `$schema` line of the template" in kickoff_settings_text():
        data["$schema"] = tpl["$schema"]
    data["permissions"] = {"allow": [r for r in tpl["permissions"]["allow"] if r not in skipped],
                           "ask": list(tpl["permissions"]["ask"])}
    return data


# Places where the questions file differs from §9.13.3 on purpose: the project has no spec,
# so its references become words (each pair: spec text, template text).
QUESTION_ADAPTATIONS = [
    ("(the check runs rule below)", "(the check runs rule of research)"),
    ("(the instruction files rule below)", "(the instruction files rule of research)"),
    ("a document in each docs role (§15);",
     "a document in each docs role: `vision` (what the product is, for whom, non-goals), `overview` (components "
     "and data flow), `decisions` (decision records), `conventions` (code style, testing rules, module layout), "
     "`tasks` (notes on past work);"),
]


def normalized_questions(text: str) -> str:
    """The numbered questions, with whitespace collapsed (markup kept: backticks and bold are content)."""
    return " ".join(text.split())


def question_items(text: str) -> List[str]:
    """Top-level numbered items under `## Questions`."""
    part = text.split("## Questions", 1)[1]
    return re.findall(r"(?m)^(\d+)\. ", part)


class OnboardingQuestionsTemplateTest(unittest.TestCase):
    def text(self) -> str:
        return read(QUESTIONS)

    def test_frontmatter(self):
        fm = ls.parse_frontmatter(self.text())
        self.assertEqual(list(fm), ["task", "phase", "status", "based_on", "updated"])
        self.assertEqual((fm["phase"], fm["status"], fm["based_on"]), ("research-questions", "approved", []))
        spec_keys = re.findall(r"(?m)^(\w+):", re.search(r"```yaml\n(.*?)```", spec_section(
            "### 13.1 Frontmatter and gates", "### 13.2"), re.DOTALL).group(1))
        self.assertTrue(set(fm) <= set(spec_keys), fm)
        self.assertIn("`setup` writes the fixed `01-research-questions.md` of the onboarding task as `approved`",
                      spec_section("### 13.1 Frontmatter and gates", "### 13.2"))

    def test_layout_matches_13_2(self):
        block = re.search(r"\*\*`01-research-questions\.md`\*\* \(full\)\n```markdown\n(.*?)```",
                          spec_section("### 13.2 Working artifacts", "### 13.3"), re.DOTALL).group(1)
        expected = [re.sub(r"\s+←.*$", "", l)[3:].strip() for l in block.splitlines() if l.startswith("## ")]
        self.assertEqual(re.findall(r"(?m)^## (.+)$", self.text()), expected)
        self.assertEqual(re.findall(r"(?m)^# (.+)$", ls.split_frontmatter(self.text())[1]), ["Research Questions"])
        research_questions = read(os.path.join(SKILLS, "research-questions", "references", "template.md"))
        self.assertIn("# Research Questions", research_questions)

    def test_seven_questions_match_9_13_3(self):
        spec = spec_section("#### 9.13.3 Research: the fixed question list", "#### 9.13.4")
        spec_titles = re.findall(r"(?m)^\d\. \*\*(.+?)\*\*", spec)
        titles = re.findall(r"(?m)^\d\. \*\*(.+?)\*\*", self.text())
        self.assertEqual(len(spec_titles), 7)
        self.assertEqual(titles, spec_titles)
        self.assertEqual(question_items(self.text()), [str(i) for i in range(1, 8)])
        self.assertIn("The fixed list has 7 questions", spec)
        # Sub-items per question, as in the spec (questions 4, 6, and 7).
        def sub_items(text: str) -> List[int]:
            parts = re.split(r"(?m)^\d\. \*\*", text.split("## Questions", 1)[-1])[1:]
            return [len(re.findall(r"(?m)^   - ", p)) for p in parts]
        self.assertEqual(sub_items(self.text()), sub_items(spec.split("Rules for the onboarding research", 1)[0]))

    def test_question_text_matches_9_13_3(self):
        spec = spec_section("#### 9.13.3 Research: the fixed question list", "#### 9.13.4")
        spec_list = spec[spec.index("1. **Stacks"):spec.index("Rules for the onboarding research")]
        for old, new in QUESTION_ADAPTATIONS:
            self.assertEqual(spec_list.count(old), 1, old)
            spec_list = spec_list.replace(old, new)
        mine = self.text().split("## Questions", 1)[1]
        self.assertEqual(normalized_questions(mine), normalized_questions(spec_list))

    def test_questions_are_descriptive(self):
        questions = self.text().split("## Questions", 1)[1]
        for word in (r"\bshould\b", r"\bmust\b", r"\bhow (would|do) we\b", r"\bmissing\b", r"\bneeds? to\b"):
            with self.subTest(word=word):
                self.assertNotRegex(questions, r"(?i)" + word)
        self.assertNotIn("§", self.text())  # spec references mean nothing in the project
        self.assertNotIn("<!--", self.text())

    def test_key_context_pointers_name_found(self):
        pointers = self.text().split("## Key Context Pointers", 1)[1].split("## Questions", 1)[0]
        self.assertEqual(re.findall(r"<found\.(\w+)>", pointers), list(FOUND_PLACEHOLDERS))
        self.assertEqual(set(ls.found_paths([])), set(FOUND_PLACEHOLDERS))
        self.assertIn("`found` lists paths for the Key Context Pointers",
                      spec_section("### 8.2 Interface", "### 8.3 Rules"))

    def test_filled_file_has_no_placeholder(self):
        text = fill_questions(3, "2026-11-12", {"instructionFiles": ["AGENTS.md"]}, ["How does `src/x` start?"])
        self.assertNotRegex(text, r"<[a-zA-Z.]+>")
        self.assertNotIn("YYYY", text)
        self.assertEqual(question_items(text), [str(i) for i in range(1, 9)])
        self.assertIn("- Instruction files: `AGENTS.md`", text)
        self.assertIn("- Workflows: None.", text)


class OnboardingKickoffTest(RepoTestCase):
    """The kickoff of §9.13.2 on a fixture repository with code: loom-state reads it as setup describes it."""

    loom_config = None  # the kickoff writes loom.json itself
    initial_commit = False

    def setUp(self) -> None:
        super().setUp()
        self.number = 3
        self.branch = "chore/%d-loom-setup" % self.number
        self.task = self.path(".loom", "tasks", "%d-loom-setup" % self.number)
        for rel, text in {"README.md": "# x\n", "src/app.py": "x = 1\n", "AGENTS.md": "Push without confirmation.\n",
                          ".github/workflows/ci.yml": "on: push\n", "docs/index.md": "x\n"}.items():
            write(self.path(*rel.split("/")), text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "initial")
        remote = os.path.join(self.tmp, "origin.git")
        git(self.tmp, "init", "-q", "--bare", "-b", "main", remote)
        git(self.repo, "remote", "add", "origin", remote)
        git(self.repo, "push", "-q", "-u", "origin", "main")

    def setup_path(self) -> Dict:
        proc = run_loom_state(self.repo, "--setup-path", "main")
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        return json.loads(proc.stdout)

    def minimal_config(self) -> Dict:
        steps = read(ONBOARDING).split("### Kickoff steps", 1)[1]
        block = re.search(r"```json\n(.*?)```", steps, re.DOTALL).group(1)
        return json.loads(re.sub(r"(?m)^ {3}", "", block).replace("<main>", "main"))

    def subject(self) -> str:
        m = re.search(r"only the subject `(chore\(loom\): start loom setup \(#<n>\))`", read(ONBOARDING))
        return m.group(1).replace("<n>", str(self.number))

    def kickoff(self) -> Dict:
        """Kickoff steps 5-9: branch, ticket, minimal loom.json, permission rules, kickoff commit."""
        found = self.setup_path()
        self.assertEqual(found["path"], "onboarding")
        git(self.repo, "switch", "-q", "-c", self.branch)
        write(os.path.join(self.task, "00-ticket.md"), fill_ticket(
            "%d-loom-setup" % self.number, "full", self.number, size="M", title="Set up loom",
            labels="type:chore, size:M, mode:full", body=template("setup-issue-onboarding.md")))
        os.makedirs(self.path(".claude"))
        with open(self.path(".claude", "loom.json"), "w", encoding="utf-8") as fh:
            json.dump(self.minimal_config(), fh, indent=2)
        with open(self.path(".claude", "settings.json"), "w", encoding="utf-8") as fh:
            json.dump(kickoff_settings(), fh, indent=2)
        git(self.repo, "add", "--", ".claude/loom.json", ".claude/settings.json")
        write(os.path.join(self.task, "commit-msg.txt"), self.subject() + "\n")
        git(self.repo, "commit", "-q", "-F", os.path.join(self.task, "commit-msg.txt"))
        return found["found"]

    def test_kickoff_routes_to_research(self):
        found = self.kickoff()
        self.assertEqual(found["instructionFiles"], ["AGENTS.md"])
        self.assertEqual(found["workflows"], [".github/workflows/ci.yml"])
        # Before the questions file: the kickoff did not finish, so loom-state names /loom:setup (row 2c).
        state = self.state()
        self.assertTrue(state["task"]["setup"])
        self.assertEqual(state["next"]["command"], "/loom:setup")
        self.assertEqual(self.setup_path()["path"], "onboarding-rerun")
        # Kickoff step 10: the fixed list, approved with the plan confirmation.
        write(os.path.join(self.task, "01-research-questions.md"), fill_questions(self.number, "2026-11-12", found))
        state = self.state()
        self.assertEqual(state["warnings"], [])
        self.assertEqual(state["workingTree"], "clean")
        self.assertEqual((state["task"]["mode"], state["task"]["size"]), ("full", "M"))
        self.assertEqual([(a["file"], a["phase"], a["status"], a["openQuestions"]) for a in state["artifacts"]],
                         [("01-research-questions.md", "research-questions", "approved", 0)])
        self.assertEqual(state["next"]["command"], "/loom:research")
        self.assertEqual(self.setup_path()["path"], "onboarding-rerun")

    def test_minimal_config_takes_the_defaults(self):
        self.kickoff()
        self.assertEqual(self.minimal_config(), {"version": 1, "mainBranch": "main"})
        state = self.state()
        self.assertEqual(state["warnings"], [])
        self.assertEqual(state["checks"], ls.DEFAULT_CONFIG["checks"])
        self.assertEqual(state["ci"], {"requiredCheck": "check"})
        self.assertIs(state["hooks"]["stopLint"], False)

    def test_kickoff_commit_has_no_phase_line(self):
        self.kickoff()
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s"), ls.KICKOFF_SUBJECT % self.number)
        self.assertEqual(git(self.repo, "log", "-1", "--format=%b"), "")
        self.assertEqual(git(self.repo, "log", "--format=%h", "--grep=^Phase", "origin/main..HEAD"), "")
        self.assertEqual(sorted(git(self.repo, "diff", "--name-only", "origin/main..HEAD").splitlines()),
                         [".claude/loom.json", ".claude/settings.json"])

    def test_kickoff_settings(self):
        tpl = json.loads(template("settings.json"))
        # The reference leaves out exactly the check-command rules of the template (§9.13.2 step 8).
        self.assertEqual(kickoff_left_out(), ["Bash(make *)"])
        self.assertEqual([r for r in tpl["permissions"]["allow"] if r.startswith("Bash(make ")], ["Bash(make *)"])
        self.assertIn("every other rule that runs a check command (for Node, one rule per check command)",
                      kickoff_settings_text())
        # It names every other key of the template as one it never writes; a new file gets $schema.
        self.assertEqual(set(kickoff_no_keys()), set(tpl) - {"$schema", "permissions"})
        self.assertIn("the `$schema` line of the template", kickoff_settings_text())
        self.assertIn("writes only the `permissions` key of `.claude/settings.json` (and `$schema` in a new file)",
                      kickoff_settings_text())
        data = kickoff_settings()
        self.assertEqual(list(data), ["$schema", "permissions"])
        allow, ask = data["permissions"]["allow"], data["permissions"]["ask"]
        self.assertEqual(ask, tpl["permissions"]["ask"])
        # The phases of the onboarding task run these without a prompt (§9.13.2 step 8, §9.13.3 GitHub
        # facts); gh api and git push stay ask rules.
        for command in ("loom-state --json", "loom-state --json --pr", "git status --porcelain", "git log --oneline",
                        "gh repo view --json name", "gh label list", "gh issue list", "gh run list", "gh run view 1"):
            with self.subTest(command=command):
                self.assertTrue(any(r == "Bash(%s)" % command or (r.endswith(" *)") and
                                    (command + " ").startswith(r[5:-3] + " ")) for r in allow), command)
        self.assertIn("Bash(gh api *)", ask)
        self.assertIn("Bash(git push *)", ask)
        self.assertFalse(any(r.startswith("Bash(make") for r in allow))
        # The merge into an existing file follows the skill's own rules.
        for needle in ("\"Merge settings.json\" in step 7 of the skill", "Append the missing rules",
                       "Keep the existing rules and their order", "Keep every other key as it is",
                       "Never replace the file, and never remove a key."):
            with self.subTest(needle=needle):
                self.assertIn(needle, kickoff_settings_text())


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------


class SlugTest(unittest.TestCase):
    CASES = {
        "Add token refresh to the auth client": "add-token-refresh-to-the",
        "Fix the user's $HOME `expansion` bug!": "fix-the-user-s-home",
        "Ünïcödé façade résumé": "unicode-facade-resume",
        "日本語のタイトル": "task",
        "": "task",
        "---": "task",
        "Set up loom": "set-up-loom",
        "a b c d e f g": "a-b-c-d-e",
        "  Leading   and trailing  ": "leading-and-trailing",
        "Supercalifragilisticexpialidocious and even longer words": "supercalifragilisticexpialidocious-and",
        "x" * 60: "x" * 40,
        "API v2: GET /users/{id}": "api-v2-get-users-id",
        "Update CI (#12)": "update-ci-12",
        "-x": "x",
        "--json output omits pr": "json-output-omits-pr",
        "Straße für Æsir": "strasse-fur-aesir",
        "Søren's œuvre in Łódź": "soren-s-oeuvre-in-lodz",
        "a " + "y" * 50 + " word": "a",  # accepted quirk (§8.2)
        # The slug loom-setup is reserved for the setup task (§8.2, §9.13.1).
        "Loom setup": "loom-setup-task",
        "  LOOM: Setup! ": "loom-setup-task",
        "Loom-setup": "loom-setup-task",
        "Loom setup notes": "loom-setup-notes",
        "Loom setup task": "loom-setup-task",
    }

    def test_reserved_setup_slug_on_the_cli(self):
        proc = subprocess.run([sys.executable, LOOM_STATE, "--slug", "Loom setup"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "loom-setup-task\n", ""))
        self.assertFalse(ls.SETUP_BRANCH_RE.match("chore/1-%s" % ls.slugify("Loom setup")))

    def test_cases(self):
        for title, slug in self.CASES.items():
            with self.subTest(title=title):
                self.assertEqual(ls.slugify(title), slug)

    def test_rule_holds_for_every_case(self):
        for title in self.CASES:
            slug = ls.slugify(title)
            with self.subTest(title=title):
                self.assertRegex(slug, r"^[a-z0-9]+(-[a-z0-9]+)*$")
                self.assertLessEqual(len(slug), 40)
                self.assertLessEqual(len(slug.split("-")), 5)
                self.assertTrue(ls.BRANCH_RE.match("feat/1-%s" % slug))

    def test_cli_outside_a_repository(self):
        tmp = tempfile.mkdtemp(prefix="loom-slug-")
        self.addCleanup(shutil.rmtree, tmp, True)
        proc = subprocess.run([sys.executable, LOOM_STATE, "--slug", "Add the user's token store"], cwd=tmp,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "add-the-user-s-token\n", ""))

    def test_cli_titles_that_look_like_options(self):
        for title, slug in (("-x", "x"), ("--json output omits pr", "json-output-omits-pr"), ("---", "task"),
                            ("--slug", "slug"), ("-h", "h")):
            with self.subTest(title=title):
                proc = subprocess.run([sys.executable, LOOM_STATE, "--slug", title],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, slug + "\n", ""))

    def test_spec_documents_the_quirks(self):
        interface = spec_section("### 8.2 Interface", "### 8.3 Rules")
        for needle in ("starts with `-`", "`ß` → `ss`", "`a <50-character word>` → `a`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, interface)

    def test_cli_rejects_slug_with_another_format(self):
        proc = subprocess.run([sys.executable, LOOM_STATE, "--slug", "x", "--json"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(proc.returncode, 2)


# ---------------------------------------------------------------------------
# Status line script
# ---------------------------------------------------------------------------


class StatuslineScriptTest(RepoTestCase):
    SCRIPT = os.path.join(TEMPLATES, "loom-statusline.py")

    def setUp(self) -> None:
        super().setUp()
        git(self.repo, "switch", "-q", "-c", "feat/42-auth-flow")
        self.ticket(self.task_dir("42-auth-flow"), mode="full")
        self.root = os.path.join(self.tmp, "plugins")
        os.makedirs(self.root)

    def plugin(self, *parts: str) -> str:
        """A fake installed plugin directory with a copy of the real bin/loom-state."""
        path = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.join(path, "bin"), exist_ok=True)
        shutil.copy(LOOM_STATE, os.path.join(path, "bin", "loom-state"))
        return path

    def installs(self, entries: List[Dict]) -> None:
        with open(os.path.join(self.root, "installed_plugins.json"), "w") as fh:
            json.dump({"version": 2, "plugins": {"loom@loom": entries, "other@x": [{"installPath": "/nope"}]}}, fh)

    def run_script(self, stdin: Optional[str] = None, env: Optional[Dict[str, str]] = None,
                   cwd: Optional[str] = None) -> subprocess.CompletedProcess:
        full_env = {k: v for k, v in os.environ.items() if k not in ("LOOM_PLUGIN_ROOT", "CLAUDE_CONFIG_DIR")}
        full_env["CLAUDE_CODE_PLUGIN_CACHE_DIR"] = self.root
        full_env.update(env or {})
        if stdin is None:
            stdin = json.dumps({"cwd": self.repo, "workspace": {"current_dir": self.repo, "project_dir": self.repo}})
        return subprocess.run([sys.executable, self.SCRIPT], input=stdin, cwd=cwd or self.tmp, env=full_env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def assert_line(self, proc: subprocess.CompletedProcess) -> None:
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        self.assertEqual(proc.stdout, "#42 · full · ticket\n")

    def test_compiles_on_this_python(self):
        py_compile.compile(self.SCRIPT, doraise=True, cfile=os.path.join(self.tmp, "statusline.pyc"))

    def test_installed_plugins_json(self):
        install = self.plugin("cache", "loom", "loom", "0.1.0")
        self.installs([{"scope": "project", "projectPath": "/elsewhere", "installPath": "/missing"},
                       {"scope": "project", "projectPath": self.repo, "installPath": install}])
        self.assert_line(self.run_script())

    def test_prefers_the_install_of_this_project(self):
        mine = self.plugin("mine")
        other = self.plugin("other")
        os.remove(os.path.join(other, "bin", "loom-state"))
        with open(os.path.join(other, "bin", "loom-state"), "w") as fh:
            fh.write("import sys\nprint('wrong plugin')\n")
        self.installs([{"scope": "user", "installPath": other},
                       {"scope": "project", "projectPath": self.repo, "installPath": mine}])
        self.assert_line(self.run_script())

    def test_marketplace_fallback(self):
        market = self.plugin("marketplaces", "loom")
        with open(os.path.join(self.root, "known_marketplaces.json"), "w") as fh:
            json.dump({"loom": {"source": {"source": "github", "repo": "mmosvlad1/loom"}, "installLocation": market}}, fh)
        self.assert_line(self.run_script())

    def test_cache_fallback_skips_orphaned_versions(self):
        self.root = os.path.join(self.tmp, "plugins2")
        good = os.path.join(self.root, "cache", "loom", "loom", "0.1.0")
        old = os.path.join(self.root, "cache", "loom", "loom", "0.0.9")
        for path in (good, old):
            os.makedirs(os.path.join(path, "bin"))
            shutil.copy(LOOM_STATE, os.path.join(path, "bin", "loom-state"))
        with open(os.path.join(old, "bin", "loom-state"), "w") as fh:
            fh.write("print('orphaned version')\n")
        write(os.path.join(old, ".orphaned_at"), "1\n")
        os.utime(os.path.join(old, "bin", "loom-state"), None)  # newest, but orphaned
        self.assert_line(self.run_script())

    def test_config_dir(self):
        config = os.path.join(self.tmp, "config")
        self.root = os.path.join(config, "plugins")
        os.makedirs(self.root)
        self.installs([{"scope": "user", "installPath": self.plugin("cfg")}])
        env = {"CLAUDE_CONFIG_DIR": config}
        proc = subprocess.run(
            [sys.executable, self.SCRIPT], input=json.dumps({"workspace": {"current_dir": self.repo}}),
            env={**{k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_PLUGIN_CACHE_DIR", "LOOM_PLUGIN_ROOT")}, **env},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assert_line(proc)

    def test_override(self):
        self.assert_line(self.run_script(env={"LOOM_PLUGIN_ROOT": self.plugin("dev", "loom")}))

    def test_no_plugin_prints_nothing(self):
        proc = self.run_script()
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_bad_input_and_failures_print_nothing(self):
        install = self.plugin("cache", "loom", "loom", "0.1.0")
        self.installs([{"scope": "user", "installPath": install}])
        # Invalid stdin: the script falls back to its own working directory.
        self.assert_line(self.run_script(stdin="not json", cwd=self.repo))
        # Outside a loom project loom-state prints nothing, so the line stays empty.
        proc = self.run_script(stdin=json.dumps({"workspace": {"current_dir": self.tmp}}))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))
        # A broken loom-state never shows an error.
        with open(os.path.join(install, "bin", "loom-state"), "w") as fh:
            fh.write("raise SystemExit('boom')\n")
        proc = self.run_script()
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))
        with open(os.path.join(self.root, "installed_plugins.json"), "w") as fh:
            fh.write("{broken")
        self.assertEqual(self.run_script().returncode, 0)

    def test_settings_command_is_silent_outside_a_repository(self):
        command = json.loads(template("settings.json"))["statusLine"]["command"]
        outside = tempfile.mkdtemp(prefix="loom-nogit-")
        self.addCleanup(shutil.rmtree, outside, True)
        proc = subprocess.run(["sh", "-c", command], input="{}", cwd=outside, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual((proc.stdout, proc.stderr), ("", ""))

    def test_settings_command_finds_the_script(self):
        # The statusLine command of the settings template, run by a shell from a subdirectory.
        os.makedirs(self.path(".claude"), exist_ok=True)
        shutil.copy(self.SCRIPT, self.path(".claude", "loom-statusline.py"))
        os.makedirs(self.path("src", "pkg"))
        install = self.plugin("cache", "loom", "loom", "0.1.0")
        self.installs([{"scope": "user", "installPath": install}])
        command = json.loads(template("settings.json"))["statusLine"]["command"]
        env = {k: v for k, v in os.environ.items() if k != "LOOM_PLUGIN_ROOT"}
        env["CLAUDE_CODE_PLUGIN_CACHE_DIR"] = self.root
        proc = subprocess.run(["sh", "-c", command], input=json.dumps({"workspace": {"current_dir": self.repo}}),
                              cwd=self.path("src", "pkg"), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assert_line(proc)


if __name__ == "__main__":
    unittest.main()
