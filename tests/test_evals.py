"""Static checks of the eval suite in evals/ (LOOM_SPEC.md 20.2). No model calls.

The suite runs with `claude plugin eval` (`make eval`). These tests check what
can be checked without a model: the case and grader files use only documented
keys and model-free grader types, the scaffold scripts exist and are
executable, every scaffold builds a fixture that `loom-state` routes to the
skill the case runs, and the grader regexes match the fixture texts they are
written for.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from typing import Any, Dict, List, Tuple

from loomtest import LOOM_STATE, ROOT

EVALS = os.path.join(ROOT, "evals")
BUILD = os.path.join(EVALS, "_fixture", "build.py")
TASK_DIR = ".loom/tasks/7-bulk-discount-tiers"

# https://code.claude.com/docs/en/plugin-evals (Claude Code 2.1.318).
CASE_KEYS = {"schema_version", "name", "description", "tags", "plugins", "runs", "expected_outcome",
             "execution", "context", "graders"}
EXECUTION_KEYS = {"model", "max_turns", "timeout_seconds", "allowed_tools", "append_system_prompt", "env", "prompt"}
CONTEXT_KEYS = {"scaffold_script", "add_dirs", "history_file"}
COMMON_GRADER_KEYS = {"type", "weight", "arm"}
GRADER_KEYS = {
    "regex": {"pattern", "flags", "match", "target"},
    "tool_used": {"tool", "input_match", "min", "max"},
    "tool_order": {"before", "after"},
    "file_exists": {"path", "exists"},
}
# `llm` and `baseline` graders call a model; loom's evals never use them.
MODEL_FREE = set(GRADER_KEYS)

# What `loom-state --json` reports in each scaffolded fixture.
EXPECTED_STATE: Dict[str, Dict[str, Any]] = {
    "research-full": {"mode": "full", "next": "/loom:research",
                      "artifacts": {"01-research-questions.md": "approved"}},
    "design-full": {"mode": "full", "next": "/loom:design",
                    "artifacts": {"01-research-questions.md": "approved", "02-research.md": "approved"}},
    "implement-manual": {"mode": "quick", "next": "/loom:implement",
                         "artifacts": {"02-research.md": "approved", "04-plan.md": "approved"}},
    "guard-main": {"onMain": True},
}


# ---------------------------------------------------------------------------
# A minimal YAML reader for the subset the case and grader files use:
# block mappings (2-space indent), scalars, quoted strings, inline lists and
# maps, folded (>, >-) and literal (|, |-) blocks, and # comments.
# ---------------------------------------------------------------------------

def _scalar(text: str) -> Any:
    text = text.strip()
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), text[1:-1])
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~", ""):
        return None
    return text


def _split_flow(text: str) -> List[str]:
    """Split the inside of an inline list or map at top-level commas."""
    parts, buf, quote, depth = [], "", "", 0
    for ch in text:
        if quote:
            buf += ch
            if ch == quote:
                quote = ""
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
            continue
        buf += ch
    if buf.strip():
        parts.append(buf)
    return parts


def _value(text: str) -> Any:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [_value(p) for p in _split_flow(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        result = {}
        for part in _split_flow(text[1:-1]):
            key, _, val = part.partition(":")
            result[key.strip()] = _value(val)
        return result
    return _scalar(text)


def _strip_comment(line: str) -> str:
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def parse_yaml(text: str) -> Dict[str, Any]:
    lines = text.splitlines()

    def block(start: int, indent: int) -> Tuple[Dict[str, Any], int]:
        result: Dict[str, Any] = {}
        i = start
        while i < len(lines):
            raw = lines[i]
            line = _strip_comment(raw)
            if not line.strip():
                i += 1
                continue
            cur = len(line) - len(line.lstrip(" "))
            if cur < indent:
                break
            if cur > indent:
                raise ValueError("unexpected indentation: %r" % raw)
            key, sep, rest = line.strip().partition(":")
            if not sep or not re.fullmatch(r"[A-Za-z_][\w-]*", key):
                raise ValueError("unsupported line: %r" % raw)
            if key in result:
                raise ValueError("duplicate key %r" % key)
            rest = rest.strip()
            if rest in (">", ">-", "|", "|-"):
                body: List[str] = []
                i += 1
                while i < len(lines) and (not lines[i].strip() or
                                          len(lines[i]) - len(lines[i].lstrip(" ")) > indent):
                    body.append(lines[i].strip())
                    i += 1
                joined = (" " if rest.startswith(">") else "\n").join(body).strip()
                result[key] = joined if rest.endswith("-") else joined + "\n"
                continue
            if rest == "":
                child, i = block(i + 1, indent + 2)
                result[key] = child
                continue
            result[key] = _value(rest)
            i += 1
        return result, i

    data, end = block(0, 0)
    if end != len(lines):
        raise ValueError("could not parse line %d" % (end + 1))
    return data


def split_grader(text: str) -> Tuple[Dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("grader does not start with ---")
    end = lines.index("---", 1)
    return parse_yaml("\n".join(lines[1:end])), "\n".join(lines[end + 1:])


# ---------------------------------------------------------------------------
# Suite helpers
# ---------------------------------------------------------------------------

def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def case_dirs() -> List[str]:
    """Directories below evals/ that hold a case file (a case per the eval docs)."""
    result = []
    for path in sorted(glob.glob(os.path.join(EVALS, "*"))):
        if os.path.isdir(path) and any(os.path.isfile(os.path.join(path, f)) for f in ("case.yaml", "prompt.md")):
            result.append(path)
    return result


def case(name: str) -> Dict[str, Any]:
    return parse_yaml(read(os.path.join(EVALS, name, "case.yaml")))


def graders(case_dir: str) -> Dict[str, Dict[str, Any]]:
    return {
        os.path.splitext(os.path.basename(p))[0]: split_grader(read(p))[0]
        for p in sorted(glob.glob(os.path.join(case_dir, "graders", "*.md")))
    }


def js_regex(pattern: str, flags: str = "") -> "re.Pattern[str]":
    """Compile a grader regex in Python. The patterns use only syntax that JS and Python share."""
    py_flags = 0
    for flag in flags or "":
        if flag == "m":
            py_flags |= re.M
        elif flag == "i":
            py_flags |= re.I
        elif flag == "s":
            py_flags |= re.S
        else:
            raise ValueError("unsupported flag %r" % flag)
    return re.compile(pattern, py_flags)


def grader_regex(case_name: str, grader: str) -> "re.Pattern[str]":
    g = graders(os.path.join(EVALS, case_name))[grader]
    return js_regex(g["pattern"], g.get("flags", ""))


def scaffold_env(home: str) -> Dict[str, str]:
    """The minimal environment of `claude plugin eval --scaffold`: PATH, HOME, TMPDIR, TERM."""
    tmp = os.path.join(home, "tmp")
    os.makedirs(tmp, exist_ok=True)
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home, "TMPDIR": tmp, "TERM": "dumb"}


class Scaffolded:
    """Run a case's scaffold script in a fresh, empty workspace."""

    def __init__(self, test: unittest.TestCase, name: str) -> None:
        self.base = os.path.realpath(tempfile.mkdtemp(prefix="loom-eval-"))
        test.addCleanup(shutil.rmtree, self.base, True)
        self.home = os.path.join(self.base, "home")
        self.cwd = os.path.join(self.home, "cwd")
        os.makedirs(self.cwd)
        self.env = scaffold_env(self.home)
        script = os.path.join(EVALS, name, case(name)["context"]["scaffold_script"])
        proc = subprocess.run([script], cwd=self.cwd, env=self.env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, timeout=120)
        test.assertEqual(proc.returncode, 0, "scaffold of %s failed: %s" % (name, proc.stderr))

    def git(self, *args: str) -> str:
        env = dict(self.env, GIT_CONFIG_NOSYSTEM="1")
        return subprocess.run(["git"] + list(args), cwd=self.cwd, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, check=True).stdout.strip()

    def state(self) -> Dict[str, Any]:
        proc = subprocess.run([sys.executable, LOOM_STATE, "--json"], cwd=self.cwd, env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if proc.returncode != 0 or not proc.stdout.strip():
            raise AssertionError("loom-state failed: %s" % proc.stderr)
        return json.loads(proc.stdout)

    def read(self, rel: str) -> str:
        return read(os.path.join(self.cwd, rel))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class YamlReaderTest(unittest.TestCase):
    def test_subset(self):
        data = parse_yaml(
            "a: 1\n"
            "b: 'it''s'\n"
            "c: [x, \"y z\"]\n"
            "d: { source: file, path: \".loom/x.md\" }  # comment\n"
            "e:\n  f: >-\n    one\n    two\n  g: |\n    l1\n    l2\n"
            "h: '#not a comment'\n"
            "i: \"a\\\\. — b\"\n"
        )
        self.assertEqual(data["a"], 1)
        self.assertEqual(data["b"], "it's")
        self.assertEqual(data["c"], ["x", "y z"])
        self.assertEqual(data["d"], {"source": "file", "path": ".loom/x.md"})
        self.assertEqual(data["e"], {"f": "one two", "g": "l1\nl2\n"})
        self.assertEqual(data["h"], "#not a comment")
        self.assertEqual(data["i"], "a\\. — b")


class SuiteLayoutTest(unittest.TestCase):
    def test_expected_cases_exist(self):
        self.assertEqual({os.path.basename(d) for d in case_dirs()}, set(EXPECTED_STATE))

    def test_no_stray_directories(self):
        """Every directory in evals/ is a case, the shared fixture, or the ignored results."""
        cases = {os.path.basename(d) for d in case_dirs()}
        for name in os.listdir(EVALS):
            if os.path.isdir(os.path.join(EVALS, name)):
                self.assertIn(name, cases | {"_fixture", "results"})

    def test_results_are_ignored(self):
        self.assertIn("evals/results/", read(os.path.join(ROOT, ".gitignore")).splitlines())

    def test_spec_layout_lists_evals(self):
        self.assertIn("├── evals/", read(os.path.join(ROOT, "LOOM_SPEC.md")))


class CaseFileTest(unittest.TestCase):
    def test_case_files(self):
        for path in case_dirs():
            name = os.path.basename(path)
            with self.subTest(case=name):
                self.assertTrue(os.path.isfile(os.path.join(path, "case.yaml")))
                self.assertFalse(os.path.exists(os.path.join(path, "prompt.md")), "one case file per case")
                data = case(name)
                self.assertLessEqual(set(data), CASE_KEYS)
                self.assertEqual(data["schema_version"], "1.1")
                self.assertEqual(data["name"], name)
                self.assertEqual(data["runs"], 1, "runs: 1 keeps the default cost low; use --runs to repeat")
                self.assertNotIn("graders", data, "graders live in graders/*.md")
                self.assertLessEqual(set(data["execution"]), EXECUTION_KEYS)
                self.assertLessEqual(set(data["context"]), CONTEXT_KEYS)
                self.assertTrue(data["execution"]["prompt"].strip())
                self.assertLessEqual(data["execution"]["max_turns"], 200)
                self.assertLessEqual(data["execution"]["timeout_seconds"], 3600)

    def test_scaffold_scripts_exist_and_are_executable(self):
        for path in case_dirs():
            with self.subTest(case=os.path.basename(path)):
                script = os.path.join(path, case(os.path.basename(path))["context"]["scaffold_script"])
                self.assertTrue(os.path.isfile(script))
                self.assertTrue(os.stat(script).st_mode & stat.S_IXUSR, "%s is not executable" % script)
                self.assertTrue(read(script).startswith("#!/bin/bash\n"))
        self.assertTrue(os.stat(BUILD).st_mode & stat.S_IXUSR)

    def test_skill_prompts_name_an_existing_skill(self):
        for path in case_dirs():
            prompt = case(os.path.basename(path))["execution"]["prompt"].strip()
            m = re.match(r"^/loom:([a-z-]+)$", prompt)
            if m:
                with self.subTest(case=os.path.basename(path)):
                    self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills", m.group(1), "SKILL.md")))


class GraderFileTest(unittest.TestCase):
    def test_every_case_has_graders(self):
        for path in case_dirs():
            with self.subTest(case=os.path.basename(path)):
                self.assertGreaterEqual(len(graders(path)), 1)

    def test_graders_are_model_free_with_documented_keys(self):
        for path in case_dirs():
            for name, g in graders(path).items():
                with self.subTest(case=os.path.basename(path), grader=name):
                    self.assertIn(g.get("type"), MODEL_FREE)
                    self.assertLessEqual(set(g), COMMON_GRADER_KEYS | GRADER_KEYS[g["type"]])
                    if g["type"] == "regex":
                        js_regex(g["pattern"], g.get("flags", ""))
                        self.assertIn(g.get("match", "contains"), {"contains", "not_contains"})
                        target = g.get("target", "last_message")
                        if isinstance(target, dict):
                            self.assertEqual(set(target), {"source", "path"})
                            self.assertEqual(target["source"], "file")
                        else:
                            self.assertIn(target, {"last_message", "trace", "files"})
                    if g["type"] == "tool_used":
                        js_regex(g.get("input_match", ""))

    def test_grader_bodies_are_empty(self):
        """A body is an llm rubric; model-free graders have none."""
        for path in case_dirs():
            for p in glob.glob(os.path.join(path, "graders", "*.md")):
                with self.subTest(grader=p):
                    self.assertEqual(split_grader(read(p))[1].strip(), "")

    def test_research_never_reads_the_ticket(self):
        g = graders(os.path.join(EVALS, "research-full"))["ticket-never-read"]
        self.assertEqual((g["tool"], g["min"], g["max"]), ("Read", 0, 0))
        self.assertTrue(js_regex(g["input_match"]).search('{"file_path":"/w/%s/00-ticket.md"}' % TASK_DIR))

    def test_guard_reason_matches_the_hook(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "hooks"))
        try:
            import guard_main  # noqa: E402
        finally:
            sys.path.pop(0)
        reason = "git commit on the main branch '%s' is blocked. %s" % ("main", guard_main.REASON)
        self.assertTrue(grader_regex("guard-main", "guard-denied").search(reason))


class GraderRegexTest(unittest.TestCase):
    """The regexes match the texts the skills and templates produce, and only those."""

    RESOLVED_EMPTY = (
        "## Open Questions — Round 1 of ~3\n\n**Q1. Where?**\n- a) here — recommended: x\n- b) there\n\n"
        "## Resolved Decisions\n\n| # | Question | Decision | Rationale | Round | ADR? |\n"
        "|---|---|---|---|---|---|\n\n## Testing Approach\n\n| Test | File |\n|---|---|\n| unit | t.py |\n"
    )

    def test_resolved_decisions_empty(self):
        rx = grader_regex("design-full", "resolved-decisions-empty")
        self.assertIsNone(rx.search(self.RESOLVED_EMPTY))
        self.assertIsNone(rx.search(self.RESOLVED_EMPTY.replace("|---|---|---|---|---|---|", "| --- | :-- | --- | --- | --- | --- |")))
        with_row = self.RESOLVED_EMPTY.replace(
            "|---|---|---|---|---|---|\n", "|---|---|---|---|---|---|\n| Q1 | Where? | here | x | 1 | no |\n")
        self.assertIsNotNone(rx.search(with_row))
        self.assertIsNotNone(rx.search(with_row.replace("\n\n| # |", "\n| # |")))

    def test_resolved_decisions_no_list(self):
        rx = grader_regex("design-full", "resolved-decisions-no-list")
        self.assertIsNone(rx.search(self.RESOLVED_EMPTY))
        self.assertIsNone(rx.search(self.RESOLVED_EMPTY.replace("|---|---|---|---|---|---|\n", "|---|---|---|---|---|---|\n\nNone.\n")))
        for item in ("- Q1: here", "* Q1 - here", "**Q1. Where?** here", "Q1. here"):
            with self.subTest(item=item):
                self.assertIsNotNone(rx.search(self.RESOLVED_EMPTY.replace(
                    "|---|---|---|---|---|---|\n", "|---|---|---|---|---|---|\n\n%s\n" % item)))

    def test_status_in_review(self):
        for name in ("research-full", "design-full"):
            rx = grader_regex(name, "status-in-review")
            for line in ("status: in-review", "status: in-review  ", 'status: "in-review"', "status:'in-review'"):
                with self.subTest(case=name, line=line):
                    self.assertIsNotNone(rx.search("---\ntask: x\n%s\nupdated: y\n---\n" % line))
            for line in ("status: draft", "status: in-review-later", "  status: in-review"):
                with self.subTest(case=name, line=line):
                    self.assertIsNone(rx.search("---\n%s\n---\n" % line))

    def test_design_template_passes_the_design_graders(self):
        text = read(os.path.join(ROOT, "skills", "design", "references", "template.md")).replace("~<M>", "~3")
        self.assertIsNone(grader_regex("design-full", "resolved-decisions-empty").search(text))
        self.assertIsNone(grader_regex("design-full", "resolved-decisions-no-list").search(text))
        self.assertIsNotNone(grader_regex("design-full", "round-1-heading").search(text))

    def test_plan_ticks(self):
        rx = grader_regex("implement-manual", "plan-ticks-phase-1-only")
        self.assertIsNotNone(rx.search("## Phase Overview\n\n- [x] 1. A, verifiable via x\n- [ ] 2. B\n"))
        self.assertIsNone(rx.search("- [x] 1. A\n- [x] 2. B\n"))
        self.assertIsNone(rx.search("- [ ] 1. A\n- [ ] 2. B\n"))

    def test_log_entries(self):
        done = grader_regex("implement-manual", "phase-1-logged-done")
        phase2 = grader_regex("implement-manual", "phase-2-not-started")
        log = "## Phase 1 — in-progress\nStarted: x\n\n## Phase 1 — done — d4e5f6a\nChecks: pass\n"
        self.assertIsNotNone(done.search(log))
        self.assertIsNone(phase2.search(log))
        self.assertIsNotNone(phase2.search(log + "\n## Phase 2 — in-progress\n"))

    def test_final_message(self):
        rx = grader_regex("implement-manual", "stops-for-manual-verification")
        example = read(os.path.join(ROOT, "skills", "_shared", "final-answer.md")).split(
            "Implementation phase that needs manual verification:", 1)[1]
        self.assertIsNotNone(rx.search(example))

    def test_commit_count_pattern(self):
        g = graders(os.path.join(EVALS, "implement-manual"))["one-commit"]
        rx = js_regex(g["input_match"])
        self.assertIsNotNone(rx.search('{"command":"git commit -F .loom/tasks/7-x/commit-msg.txt"}'))
        self.assertIsNotNone(rx.search('{"command":"git -C /w/cwd commit -F x"}'))
        self.assertIsNone(rx.search('{"command":"git status --porcelain"}'))
        self.assertIsNone(rx.search('{"command":"git log --grep=commit"}'))


class ScaffoldTest(unittest.TestCase):
    """Each scaffold builds a fixture that `loom-state` routes to the case's skill."""

    def test_states(self):
        for name, expected in EXPECTED_STATE.items():
            with self.subTest(case=name):
                fx = Scaffolded(self, name)
                state = fx.state()
                self.assertEqual(state["warnings"], [])
                if expected.get("onMain"):
                    self.assertTrue(state["onMain"])
                    self.assertIsNone(state["task"])
                    continue
                self.assertEqual(state["branch"], "feat/7-bulk-discount-tiers")
                self.assertFalse(state["onMain"])
                self.assertEqual(state["task"]["dir"], TASK_DIR)
                self.assertEqual(state["task"]["mode"], expected["mode"])
                self.assertEqual(state["workingTree"], "clean")
                self.assertEqual({a["file"]: a["status"] for a in state["artifacts"]}, expected["artifacts"])
                self.assertFalse(any(a.get("stale") for a in state["artifacts"]))
                self.assertEqual(state["next"]["command"], expected["next"])
                self.assertEqual(case(name)["execution"]["prompt"].strip(), expected["next"])

    def test_research_fixture(self):
        fx = Scaffolded(self, "research-full")
        self.assertFalse(os.path.exists(os.path.join(fx.cwd, TASK_DIR, "02-research.md")))
        questions = fx.read(TASK_DIR + "/01-research-questions.md").split("\n---\n", 1)[1]
        ticket = fx.read(TASK_DIR + "/00-ticket.md")
        # The questions are blind: nothing of the goal leaks into their body (the task slug in
        # the frontmatter is the branch name, which research must not read as intent).
        for word in ("bulk", "tier", "wholesale"):
            self.assertIn(word, ticket.lower())
            self.assertNotIn(word, questions.lower())

    def test_ticket_marker_is_unique_to_the_ticket(self):
        """The ticket-content-absent grader only works if its marker occurs nowhere but the ticket body."""
        marker = graders(os.path.join(EVALS, "research-full"))["ticket-content-absent"]["pattern"]
        fx = Scaffolded(self, "research-full")
        found = []
        for base, dirs, files in os.walk(fx.cwd):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in files:
                if marker in read(os.path.join(base, f)):
                    found.append(os.path.relpath(os.path.join(base, f), fx.cwd))
        self.assertEqual(found, [TASK_DIR + "/00-ticket.md"])
        ticket_body = fx.read(TASK_DIR + "/00-ticket.md").split("\n---\n", 1)[1]
        self.assertIn(marker, ticket_body)
        # Nothing the skill or the agents get besides the ticket carries it: loom-state, plugin files, the case.
        self.assertNotIn(marker, json.dumps(fx.state()))
        for d in ("skills", "agents", "scripts", "bin"):
            for base, _, files in os.walk(os.path.join(ROOT, d)):
                for f in files:
                    if not f.endswith(".pyc"):
                        with self.subTest(file=os.path.join(base, f)):
                            self.assertNotIn(marker, read(os.path.join(base, f)))
        self.assertNotIn(marker, read(os.path.join(EVALS, "research-full", "case.yaml")))

    def test_design_fixture_research_references_are_real(self):
        fx = Scaffolded(self, "design-full")
        research = fx.read(TASK_DIR + "/02-research.md")
        refs = re.findall(r"`((?:shop|tests)/\w+\.py):(\d+)(?:-(\d+))?`", research)
        self.assertGreater(len(refs), 10)
        for path, start, end in refs:
            with self.subTest(ref="%s:%s" % (path, start)):
                lines = fx.read(path).splitlines()
                self.assertLessEqual(int(end or start), len(lines))
        self.assertIsNotNone(grader_regex("research-full", "file-line-references").search(research))

    def test_implement_fixture(self):
        fx = Scaffolded(self, "implement-manual")
        plan = fx.read(TASK_DIR + "/04-plan.md")
        phase1 = plan.split("## Phase 1:", 1)[1].split("## Phase 2:", 1)[0]
        phase2 = plan.split("## Phase 2:", 1)[1]
        self.assertIn("- [ ] Manual:", phase1)
        self.assertNotIn("Manual:", phase2)
        self.assertFalse(os.path.exists(os.path.join(fx.cwd, TASK_DIR, "log.md")))
        # The checks pass with the standard library only, as the implementer and the hook run them.
        proc = subprocess.run(["make", "check"], cwd=fx.cwd, env=fx.env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, universal_newlines=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(fx.git("status", "--porcelain"), "")

    def test_guard_fixture(self):
        fx = Scaffolded(self, "guard-main")
        self.assertEqual(fx.git("branch", "--show-current"), "main")
        self.assertEqual(fx.git("diff", "--cached", "--name-only"), "README.md")
        head = fx.git("rev-parse", "HEAD")
        self.assertIsNotNone(grader_regex("guard-main", "main-unchanged").search(fx.read(".git/refs/heads/main")))
        self.assertEqual(fx.read(".git/refs/heads/main").strip(), head)
        self.assertEqual(fx.git("rev-list", "--count", "HEAD"), "1")

    def test_loom_json_matches_the_spec(self):
        fx = Scaffolded(self, "guard-main")
        spec = read(os.path.join(ROOT, "LOOM_SPEC.md"))
        block = spec.split("### 19.1 `.claude/loom.json` (committed)", 1)[1].split("```json\n", 1)[1].split("```", 1)[0]
        self.assertEqual(json.loads(fx.read(".claude/loom.json")), json.loads(block))

    def test_build_refuses_a_non_empty_directory(self):
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="loom-eval-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, "x"), "w"):
            pass
        proc = subprocess.run([sys.executable, BUILD, "guard-main"], cwd=tmp, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)
        self.assertNotEqual(proc.returncode, 0)


class MakefileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read(os.path.join(ROOT, "Makefile"))

    def recipe(self, target: str) -> str:
        """The lines of a target up to the next blank line (recipe lines and make conditionals)."""
        m = re.search(r"^%s:[^\n]*\n((?:[^\n]+\n)*)" % re.escape(target), self.text + "\n", re.M)
        self.assertIsNotNone(m, "no %s target" % target)
        return m.group(1)

    def test_eval_is_not_part_of_check(self):
        check = re.search(r"^check:([^\n]*)$", self.text, re.M).group(1)
        self.assertNotIn("eval", check.split())

    def test_eval_flags(self):
        recipe = self.recipe("eval")
        for flag in ("plugin eval .", "--scaffold", "--ablation none", "--no-publish", "--trust-plugin",
                     "--max-cost-usd $(EVAL_MAX_COST)", "--allow-tools $(EVAL_TOOLS)", "$(EVAL_FILTER)",
                     "$(EVAL_ARGS)", 'PATH="$(EVAL_PATH):$$PATH"'):
            with self.subTest(flag=flag):
                self.assertIn(flag, recipe)
        for forbidden in ("--dangerously-skip-permissions", "bypassPermissions", "--mocks off"):
            self.assertNotIn(forbidden, self.text)

    def test_macos_runs_only_local_cases_by_default(self):
        darwin = self.text.split("ifeq ($(shell uname -s),Darwin)", 1)[1].split("endif", 1)[0]
        self.assertIn("EVAL_FILTER ?= --tag local", darwin)
        self.assertIn("xcode-select -p", darwin)
        self.assertNotIn("xcode-select", self.text.split("ifeq ($(shell uname -s),Darwin)", 1)[0])
        note = self.recipe("eval")
        for part in ("implement-manual", "Bash git", "24.2", "EVAL_FILTER="):
            self.assertIn(part, note)
        local = {os.path.basename(d) for d in case_dirs() if "local" in case(os.path.basename(d)).get("tags", [])}
        self.assertEqual(local, set(EXPECTED_STATE) - {"implement-manual"})


class WorkflowTest(unittest.TestCase):
    """loom's own CI (LOOM_SPEC.md 21): `make check` on PRs and main; evals only on demand."""

    def workflow(self, name: str) -> str:
        return read(os.path.join(ROOT, ".github", "workflows", name))

    def test_ci_runs_make_check(self):
        text = self.workflow("ci.yml")
        self.assertRegex(text, r"(?m)^on:\n  pull_request:\n  push:\n    branches: \[main\]$")
        self.assertRegex(text, r"(?m)^permissions:\n  contents: read$")
        self.assertRegex(text, r"(?m)^  check:$")
        self.assertIn("run: make check", text)
        self.assertNotIn("ANTHROPIC_API_KEY", text)

    def test_actions_are_pinned_as_in_the_spec(self):
        spec = read(os.path.join(ROOT, "LOOM_SPEC.md"))
        for name in ("ci.yml", "eval.yml"):
            for action in re.findall(r"uses: ([\w./-]+@[\w.-]+)", self.workflow(name)):
                with self.subTest(workflow=name, action=action):
                    self.assertRegex(action, r"@v\d+\.\d+\.\d+$")
                    self.assertIn("`%s`" % action, spec)
        self.assertIn("@anthropic-ai/claude-code@2.1.318", self.workflow("ci.yml"))

    def test_evals_run_only_on_demand(self):
        text = self.workflow("eval.yml")
        on = text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("workflow_dispatch:", on)
        for trigger in ("schedule", "push", "pull_request"):
            self.assertNotIn(trigger, on)
        self.assertIn("secrets.ANTHROPIC_API_KEY", text)
        self.assertIn("bubblewrap socat", text)
        self.assertIn("make eval", text)
        self.assertIn("--json", text)
        self.assertIn("actions/upload-artifact@", text)


if __name__ == "__main__":
    unittest.main()
