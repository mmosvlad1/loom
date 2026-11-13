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
BRANCH = "feat/7-bulk-discount-tiers"
SETUP_TASK_DIR = ".loom/tasks/1-loom-setup"
SETUP_BRANCH = "chore/1-loom-setup"

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
    "describe-pr-quick": {"mode": "quick", "next": "/loom:describe-pr",
                          "artifacts": {"02-research.md": "approved", "04-plan.md": "approved"}},
    # The onboarding task: a setup task in full mode after the kickoff (LOOM_SPEC.md 9.13).
    "design-onboarding": {"mode": "full", "next": "/loom:design", "setup": True,
                          "branch": SETUP_BRANCH, "dir": SETUP_TASK_DIR,
                          "artifacts": {"01-research-questions.md": "approved", "02-research.md": "approved"}},
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

    def test_readme_lists_every_case(self):
        readme = read(os.path.join(ROOT, "README.md"))
        for name in EXPECTED_STATE:
            with self.subTest(case=name):
                self.assertRegex(readme, r"(?m)^  \| `%s` \| " % re.escape(name))

    def test_readme_describes_both_setup_paths(self):
        readme = read(os.path.join(ROOT, "README.md"))
        setup = readme.split("2. **`/loom:setup`**", 1)[1].split("\n3. ", 1)[0]
        self.assertIn("**Fast setup** (an empty or new repository, or `/loom:setup --oneshot`)", setup)
        self.assertIn("**Onboarding** (a repository with code): a `full`-mode setup task", setup)

    def test_spec_layout_lists_evals(self):
        self.assertIn("├── evals/", read(os.path.join(ROOT, "LOOM_SPEC.md")))

    def test_spec_20_2_lists_every_case(self):
        """The §20.2 tree and grader list name every case directory, and the case counts are true."""
        spec = read(os.path.join(ROOT, "LOOM_SPEC.md")).split("### 20.2 Evals", 1)[1].split("### 20.3", 1)[0]
        tree = spec.split("```", 2)[1]
        cases = {os.path.basename(d) for d in case_dirs()}
        self.assertEqual(set(re.findall(r"(?m)^[├└]── ([\w-]+)/", tree)), cases | {"_fixture", "results"})
        for name in sorted(cases):
            with self.subTest(case=name):
                self.assertRegex(spec, r"(?m)^  - `%s` \(" % re.escape(name))
        self.assertEqual(re.findall(r"all (\d+) cases", spec), [str(len(cases))])
        latest = re.findall(r"passed (\d+) of (\d+) cases", spec)[-1]
        self.assertEqual(latest, (str(len(cases)), str(len(cases))))


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
        for name in ("research-full", "design-full", "design-onboarding"):
            rx = grader_regex(name, "status-in-review")
            for line in ("status: in-review", "status: in-review  ", 'status: "in-review"', "status:'in-review'"):
                with self.subTest(case=name, line=line):
                    self.assertIsNotNone(rx.search("---\ntask: x\n%s\nupdated: y\n---\n" % line))
            for line in ("status: draft", "status: in-review-later", "  status: in-review"):
                with self.subTest(case=name, line=line):
                    self.assertIsNone(rx.search("---\n%s\n---\n" % line))

    def test_design_template_passes_the_design_graders(self):
        text = read(os.path.join(ROOT, "skills", "design", "references", "template.md")).replace("~<M>", "~3")
        for name in ("design-full", "design-onboarding"):
            with self.subTest(case=name):
                self.assertIsNone(grader_regex(name, "resolved-decisions-empty").search(text))
                self.assertIsNone(grader_regex(name, "resolved-decisions-no-list").search(text))
                self.assertIsNotNone(grader_regex(name, "round-1-heading").search(text))
                self.assertIsNotNone(grader_regex(name, "questions-open").search(text))

    def test_onboarding_design_shares_the_design_graders(self):
        """design-onboarding keeps every grader of design-full, on its own task directory (LOOM_SPEC.md 20.2)."""
        full = graders(os.path.join(EVALS, "design-full"))
        onboarding = graders(os.path.join(EVALS, "design-onboarding"))
        self.assertLessEqual(set(full), set(onboarding))
        for name, g in full.items():
            with self.subTest(grader=name):
                expected = json.loads(json.dumps(g).replace(TASK_DIR, SETUP_TASK_DIR))
                self.assertEqual(onboarding[name], expected)
        extra = set(onboarding) - set(full)
        self.assertEqual(extra, {"agents-md-question", "required-check-named", "onboarding-reference-read"})
        for name in ("agents-md-question", "required-check-named"):
            with self.subTest(grader=name):
                self.assertEqual(onboarding[name]["target"], {"source": "file", "path": SETUP_TASK_DIR + "/03-design.md"})
                self.assertEqual(onboarding[name].get("match", "contains"), "contains")

    ROUND = ("## Open Questions — Round 1 of ~3\n\n"
             "**Q1. Which command is checks.check?**\n- a) make check — recommended: passes in 0.4 s\n- b) make test\n\n"
             "**Q2. Who wins on push confirmations?**\n`AGENTS.md:5` says to push without confirmation.\n"
             "- a) loom asks — recommended: the safety rules win\n- b) the project rule\n\n"
             "**Q3. Which CI job runs checks.check?**\nThe job `test` runs `make test` only.\n"
             "- a) change the job `test` to run `checks.check`, and record `test` in `ci.requiredCheck` — recommended: "
             "it already runs on pull requests\n- b) add a job named `check`\n\n"
             "## Resolved Decisions\n")

    def test_agents_md_question(self):
        rx = grader_regex("design-onboarding", "agents-md-question")
        self.assertIsNotNone(rx.search(self.ROUND))
        self.assertIsNotNone(rx.search(self.ROUND.replace("**Q2. Who wins on push confirmations?**",
                                                          "**Q2. Does AGENTS.md win on confirmations?**")
                                       .replace("`AGENTS.md:5` says", "It says")))
        # AGENTS.md without the push or the confirmation in the same question.
        self.assertIsNone(rx.search(self.ROUND.replace("**Q2. Who wins on push confirmations?**\n`AGENTS.md:5` says to "
                                                       "push without confirmation.", "**Q2. Which branch format?**\n"
                                                       "`AGENTS.md:4` names `feature/<name>`.")))
        # AGENTS.md outside every question: in another section, or in another question than the push.
        outside = self.ROUND.replace("`AGENTS.md:5` says", "The project rule says")
        self.assertIsNone(rx.search(outside))
        self.assertIsNone(rx.search("## Proposed Architecture\n\n@AGENTS.md\n\n" + outside))
        self.assertIsNone(rx.search(outside + "\n## Testing Approach\n\nThe new CLAUDE.md imports AGENTS.md.\n"))
        self.assertIsNone(rx.search(outside.replace("**Q1. Which command", "**Q1. Per AGENTS.md, which command")))

    def test_required_check_question(self):
        rx = grader_regex("design-onboarding", "required-check-named")
        self.assertIsNotNone(rx.search(self.ROUND))
        q = "**Q6. Which CI check runs checks.check?**\nRecord its check name in `ci.requiredCheck`. %s\n- a) x\n- b) y\n"
        for text in ('Change the "test" job.', "Change job **test**.", "Change `jobs.test`.", "Change the job `test`.",
                     "Change the test job.", "Change the job named test.", "Keep the jobs; test runs there."):
            with self.subTest(positive=text):
                self.assertIsNotNone(rx.search(q % text))
        for text in ("The check keys are `lint`, `typecheck`, `test`.",  # no job named
                     "Change the job that runs `checks.test`.",        # test only as a key path
                     "Change the job of the tests.", "Change the job `test-unit`.", "Change the job `check`."):
            with self.subTest(negative=text):
                self.assertIsNone(rx.search(q % text))
        # ci.requiredCheck outside every question.
        self.assertIsNone(rx.search("## Desired End State\n\n- `ci.requiredCheck` names the job `test`.\n\n" +
                                    self.ROUND.replace("record `test` in `ci.requiredCheck`", "record its check name")))

    def test_reference_read(self):
        g = graders(os.path.join(EVALS, "design-onboarding"))
        read_ref = g["onboarding-reference-read"]
        self.assertEqual((read_ref["tool"], read_ref["min"]), ("Read", 1))
        self.assertNotIn("max", read_ref)
        rx = js_regex(read_ref["input_match"])
        self.assertTrue(rx.search('{"file_path":"/p/loom/skills/design/references/onboarding.md"}'))
        for other in ("skills/setup/references/onboarding.md", "skills/research/references/onboarding.md",
                      "skills/design/references/template.md"):
            with self.subTest(path=other):
                self.assertIsNone(rx.search('{"file_path":"/p/loom/%s"}' % other))
        never = g["research-questions-never-read"]
        self.assertEqual((never["tool"], never["min"], never["max"]), ("Read", 0, 0))
        self.assertTrue(js_regex(never["input_match"]).search(
            '{"file_path":"/w/%s/01-research-questions.md"}' % SETUP_TASK_DIR))

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

    def test_research_events_graders(self):
        """The events graders match the lines the subagent events hook writes (LOOM_SPEC.md 11.6)."""
        import datetime
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "subagent_events_for_evals", os.path.join(ROOT, "scripts", "hooks", "subagent_events.py"))
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        now = datetime.datetime.now(datetime.timezone.utc)

        def line(event, agent, phase="research"):
            data = {"hook_event_name": event, "agent_id": "a1", "agent_type": "loom:" + agent,
                    "last_assistant_message": "done", "stop_hook_active": False}
            record = hook.build_record(data, {"phase": phase, "implementationPhase": None}, now, now)
            return json.dumps(record, separators=(",", ":"))

        start_rx = grader_regex("research-full", "events-research-start")
        stop_rx = grader_regex("research-full", "events-research-stop")
        for agent in ("codebase-locator", "codebase-analyzer", "codebase-pattern-finder"):
            with self.subTest(agent=agent):
                self.assertIsNotNone(start_rx.search(line("SubagentStart", agent)))
                self.assertIsNone(start_rx.search(line("SubagentStop", agent)))
                self.assertIsNotNone(stop_rx.search(line("SubagentStop", agent)))
                self.assertIsNone(stop_rx.search(line("SubagentStart", agent)))
        design_line = line("SubagentStart", "codebase-locator", "design")
        # Another agent, another phase, and a phase on the next line do not count.
        for wrong in (line("SubagentStart", "implementer"), design_line, design_line + '\n"phase":"research"'):
            with self.subTest(line=wrong):
                self.assertIsNone(start_rx.search(wrong))
        events_path = "%s/events.jsonl" % TASK_DIR
        g = graders(os.path.join(EVALS, "research-full"))
        self.assertEqual(g["events-written"]["path"], events_path)
        for name in ("events-research-start", "events-research-stop"):
            self.assertEqual(g[name]["target"], {"source": "file", "path": events_path})

    def test_implement_events_graders(self):
        """The implement-manual events graders need a parsed result, not `unknown` (LOOM_SPEC.md 11.6)."""
        import datetime
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "subagent_events_for_implement", os.path.join(ROOT, "scripts", "hooks", "subagent_events.py"))
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        now = datetime.datetime.now(datetime.timezone.utc)

        def line(event, agent, message):
            data = {"hook_event_name": event, "session_id": "s", "agent_id": "a1", "agent_type": "loom:" + agent,
                    "last_assistant_message": message, "stop_hook_active": False}
            context = {"phase": "implement", "implementationPhase": 1, "check": "make check"}
            return json.dumps(hook.build_record(data, context, now, now), separators=(",", ":"))

        reviewer = grader_regex("implement-manual", "events-reviewer-verdict")
        implementer = grader_regex("implement-manual", "events-implementer-checks")
        for verdict in ("pass", "changes-needed"):
            with self.subTest(verdict=verdict):
                self.assertIsNotNone(reviewer.search(
                    line("SubagentStop", "implementation-reviewer", "## Verdict: %s\n" % verdict)))
        for result in ("pass", "fail"):
            with self.subTest(result=result):
                self.assertIsNotNone(implementer.search(
                    line("SubagentStop", "implementer", "### Checks\n`make check`: %s\n" % result)))
        # A report that is not in last_assistant_message gives `unknown`: the graders fail.
        self.assertIsNone(reviewer.search(line("SubagentStop", "implementation-reviewer", "done")))
        self.assertIsNone(implementer.search(line("SubagentStop", "implementer", "done")))
        self.assertIsNone(reviewer.search(line("SubagentStart", "implementation-reviewer", "")))
        self.assertIsNone(implementer.search(line("SubagentStop", "implementation-reviewer", "## Verdict: pass\n")))
        events_path = "%s/events.jsonl" % TASK_DIR
        g = graders(os.path.join(EVALS, "implement-manual"))
        for name in ("events-reviewer-verdict", "events-implementer-checks"):
            self.assertEqual(g[name]["target"], {"source": "file", "path": events_path})


class PrBodyGraderTest(unittest.TestCase):
    """The describe-pr-quick graders accept a body in the 13.6 layout and reject the old or loose ones."""

    CASE = "describe-pr-quick"
    GOOD = (
        "Closes #7\n\n"
        "## Why\n\n"
        "Wholesale orders get no discount, so customers who buy 10 or more items pay the full price.\n\n"
        "## Special things to note\n\n"
        "- The bulk discount wins a tie with a code; the plan did not define a tie.\n"
        "- The manual receipt check of phase 1 is not confirmed yet.\n\n"
        "## Change outline\n\n"
        "1. Bulk discount tiers — feat(pricing): add bulk discount tiers (#7)\n"
        "2. Larger discount wins — feat(pricing): apply the larger of code and bulk discount (#7)\n\n"
        "```diff\n"
        " shop/pricing.py\n"
        "+BULK_TIERS = ((50, 0.10), (10, 0.05))\n"
        "+def bulk_discount(item_count: int) -> float\n"
        "+def applied_discount(cart: Cart, code: Optional[str] = None) -> Tuple[str, float]\n"
        "```\n\n"
        "## Verification\n\n"
        "- `make check`: pass (12 tests)\n\n"
        "## Decisions\n\n"
        "- Task summary: [notes/loom-tasks/7-bulk-discount-tiers.md](notes/loom-tasks/7-bulk-discount-tiers.md)\n\n"
        "## Test plan\n\n"
        "- `make check` covers the bulk tiers and the tie rule.\n\n"
        "<details><summary>Implementation plan</summary>\n\n"
        "## Phase Overview\n\n- [x] 1. A\n- [x] 2. B\n\n## Phase 1: A\n\n### Changes\n\n## Phase 2: B\n\n"
        "</details>\n"
    )
    TREE = (
        "```text\n"
        "shop/\n"
        "├── pricing.py   # changed: bulk_discount, applied_discount\n"
        "└── receipt.py   # changed: prints the discount that applies\n"
        "```\n"
    )

    def rx(self, grader: str) -> "re.Pattern[str]":
        return grader_regex(self.CASE, grader)

    def section(self, name: str, body: str) -> str:
        """GOOD with the body of one `## ` section replaced."""
        head, rest = self.GOOD.split("## %s\n\n" % name, 1)
        return head + "## %s\n\n" % name + body + "\n## " + rest.split("\n## ", 1)[1]

    def test_good_body_passes(self):
        for grader in ("closes-first-line", "section-order", "why-one-sentence", "special-things-1-to-3",
                       "change-outline-shape", "plan-attached", "required-section-after-decisions"):
            with self.subTest(grader=grader):
                self.assertIsNotNone(self.rx(grader).search(self.GOOD))
        self.assertIsNone(self.rx("no-old-sections").search(self.GOOD))

    def test_targets_and_types(self):
        for name, g in graders(os.path.join(EVALS, self.CASE)).items():
            with self.subTest(grader=name):
                if g["type"] == "regex":
                    self.assertEqual(g["target"], {"source": "file", "path": TASK_DIR + "/pr-body.md"})
                elif g["type"] == "file_exists" and name == "summary-at-mapped-path":
                    # The fixture maps docs.tasks (LOOM_SPEC.md 19.1); the file name stays <n>-<slug>.md.
                    self.assertEqual(g["path"], "notes/loom-tasks/7-bulk-discount-tiers.md")
                elif g["type"] == "file_exists":
                    self.assertEqual(g["path"], TASK_DIR + "/pr-body.md")
                else:
                    self.assertEqual((g["type"], g["tool"], g["min"], g["max"]), ("tool_used", "Bash", 0, 0))

    def test_closes_is_the_first_line(self):
        rx = self.rx("closes-first-line")
        self.assertIsNone(rx.search("\n" + self.GOOD))
        self.assertIsNone(rx.search(self.GOOD.replace("Closes #7", "Closes #70")))
        self.assertIsNone(rx.search("## Why\n\n" + self.GOOD))

    def test_section_order_and_old_sections(self):
        order = self.rx("section-order")
        swapped = self.GOOD.replace("## Verification", "## X").replace("## Change outline", "## Verification").replace(
            "## X", "## Change outline")
        self.assertIsNone(order.search(swapped))
        self.assertIsNone(order.search(self.GOOD.replace("## Why", "## Summary")))
        old = self.rx("no-old-sections")
        self.assertIsNotNone(old.search(self.GOOD.replace("## Why", "## Summary")))
        self.assertIsNotNone(old.search(self.GOOD.replace("## Change outline", "## Changes")))
        self.assertIsNone(old.search("### Changes\n## Changelog\n"))

    def test_why_is_one_sentence(self):
        rx = self.rx("why-one-sentence")
        for good in ("The demo uses `shop.receipt` and `make check`.\n",
                     "Bulk buyers (e.g. wholesale customers) pay full price, i.e. they get no discount.\n"):
            with self.subTest(why=good):
                self.assertIsNotNone(rx.search(self.section("Why", good)))
        for bad in ("Wholesale orders get no discount. This PR adds tiers.\n",
                    "Wholesale orders get no discount\n",
                    "- Wholesale orders get no discount.\n",
                    "Wholesale orders get no discount.\nThis PR adds tiers.\n",
                    "<!-- One sentence. -->\n"):
            with self.subTest(why=bad):
                self.assertIsNone(rx.search(self.section("Why", bad)))

    def test_special_things_has_1_to_3_items_or_none(self):
        rx = self.rx("special-things-1-to-3")
        for good in ("None.\n", "- one\n", "- one\n- two\n- three\n", "- one\n  continued\n- two\n",
                     "- one\n\n- two\n"):
            with self.subTest(good=good):
                self.assertIsNotNone(rx.search(self.section("Special things to note", good)))
        for bad in ("- 1\n- 2\n- 3\n- 4\n", "", "Nothing special here.\n", "None.\n- one\n",
                    "* one\n", "1. one\n"):
            with self.subTest(bad=bad):
                self.assertIsNone(rx.search(self.section("Special things to note", bad)))

    def test_change_outline_has_phase_lines_and_a_tree_or_diff(self):
        rx = self.rx("change-outline-shape")
        phases = self.GOOD.split("## Change outline\n\n", 1)[1].split("```", 1)[0]
        self.assertIsNotNone(rx.search(self.section("Change outline", phases + self.TREE)))
        self.assertIsNone(rx.search(self.section("Change outline", phases)))
        self.assertIsNone(rx.search(self.section("Change outline", self.TREE)))
        one_phase = phases.split("2. ", 1)[0]
        self.assertIsNone(rx.search(self.section("Change outline", one_phase + self.TREE)))
        python = "```python\ndef bulk_discount(item_count: int) -> float: ...\n```\n"
        self.assertIsNone(rx.search(self.section("Change outline", phases + python)))
        # A closing fence never counts as an opening one: a bullet after a python block is not a diff line.
        self.assertIsNone(rx.search(self.section("Change outline", phases + python + "\n- note\n")))
        self.assertIsNone(rx.search(self.section("Change outline", phases + python + "\n" + self.TREE)))
        for info in ("txt", "plaintext", "", "diff"):
            with self.subTest(info=info):
                tree = self.TREE.replace("```text", "```" + info, 1)
                self.assertIsNotNone(rx.search(self.section("Change outline", phases + tree)))
        tilde = self.TREE.replace("```text", "~~~", 1).replace("```\n", "~~~\n")
        self.assertIsNotNone(rx.search(self.section("Change outline", phases + tilde)))
        # The visual must be inside the block, and the block inside the section.
        no_visual = "```text\nshop/pricing.py\n```\n"
        self.assertIsNone(rx.search(self.section("Change outline", phases + no_visual)))

    def test_required_section_comes_after_decisions(self):
        rx = self.rx("required-section-after-decisions")
        self.assertIsNotNone(rx.search(self.GOOD))
        moved = self.GOOD.replace("## Test plan\n\n- `make check` covers the bulk tiers and the tie rule.\n\n", "")
        self.assertIsNone(rx.search(moved))
        before = moved.replace("## Decisions\n", "## Test plan\n\nNone.\n\n## Decisions\n")
        self.assertIsNone(rx.search(before))
        after_details = moved + "\n## Test plan\n\nNone.\n"
        self.assertIsNone(rx.search(after_details))
        self.assertIsNone(rx.search(self.GOOD.replace("## Test plan", "## Test Plan")))
        self.assertIsNotNone(rx.search(self.GOOD.replace("## Test plan\n\n- `make check` covers the bulk tiers "
                                                         "and the tie rule.", "## Test plan\n\nNone.")))

    def test_plan_is_attached(self):
        rx = self.rx("plan-attached")
        self.assertIsNotNone(rx.search(self.GOOD.replace(
            "<details><summary>Implementation plan</summary>", "<details>\n<summary>Implementation plan</summary>")))
        self.assertIsNone(rx.search(self.GOOD.split("<details>", 1)[0]))
        self.assertIsNone(rx.search(self.GOOD.replace("## Phase 2: B", "")))

    def test_template_passes_the_layout_graders(self):
        text = re.sub(r"<!--.*?-->", "", read(os.path.join(ROOT, "skills", "describe-pr", "references", "pr-template.md")),
                      flags=re.S).lstrip().replace("#<n>", "#7")
        self.assertIsNotNone(self.rx("closes-first-line").search(text))
        self.assertIsNotNone(self.rx("section-order").search(text))
        self.assertIsNone(self.rx("no-old-sections").search(text))

    def test_push_and_pr_create_patterns(self):
        push = js_regex(graders(os.path.join(EVALS, self.CASE))["no-git-push"]["input_match"])
        create = js_regex(graders(os.path.join(EVALS, self.CASE))["no-gh-pr-create"]["input_match"])
        for cmd in ("git push -u origin feat/7-bulk-discount-tiers", "git -C /w/cwd push", "git push --force-with-lease"):
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(push.search('{"command":"%s"}' % cmd))
        for cmd in ("git status --porcelain", "git log --oneline main..HEAD", "git commit -F x/commit-msg.txt"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(push.search('{"command":"%s"}' % cmd))
        self.assertIsNotNone(create.search('{"command":"gh pr create --base main --title \'x\' --body-file y"}'))
        self.assertIsNone(create.search('{"command":"gh pr view --json number"}'))


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
                self.assertEqual(state["branch"], expected.get("branch", BRANCH))
                self.assertFalse(state["onMain"])
                self.assertEqual(state["task"]["dir"], expected.get("dir", TASK_DIR))
                self.assertEqual(state["task"]["mode"], expected["mode"])
                self.assertIs(state["task"]["setup"], expected.get("setup", False))
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

    def test_describe_pr_fixture(self):
        """Both phases committed as implement makes them, so describe-pr reaches its PR body step."""
        fx = Scaffolded(self, "describe-pr-quick")
        state = fx.state()
        self.assertEqual((state["implementation"]["total"], state["implementation"]["done"]), (2, 2))
        self.assertIsNone(state["task"]["pr"])
        plan = fx.read(TASK_DIR + "/04-plan.md")
        self.assertRegex(plan, r"(?m)^- \[x\] 1\. [^\n]*\n- \[x\] 2\. ")
        self.assertEqual(plan.count("- [x] Automated: make check"), 2)
        self.assertIn("- [ ] Manual:", plan)  # implement leaves Manual lines for the user
        names = re.findall(r"(?m)^## Phase (\d+): (.+)$", plan)
        log = fx.read(TASK_DIR + "/log.md")
        logged = re.findall(r"(?m)^## Phase (\d+) — done — ([0-9a-f]{7,})$", log)
        commits = fx.git("log", "--reverse", "--format=%h%x00%s%x00%b%x01", "main..HEAD").split("\x01")
        commits = [c.strip("\n").split("\x00") for c in commits if c.strip()]
        self.assertEqual(len(commits), 2)
        for (number, name), (log_n, log_hash), (short, subject, body) in zip(names, logged, commits):
            with self.subTest(phase=number):
                self.assertEqual(log_n, number)
                self.assertEqual(log_hash, short)
                self.assertEqual(body.strip(), "Phase %s: %s" % (number, name))
                self.assertRegex(subject, r"^feat\(pricing\): .+ \(#7\)$")
        # The optional loom.json keys of the case (LOOM_SPEC.md 19.1, 20.2): a mapped docs.tasks and one
        # required PR section; docs.decisions keeps its default (no decision has ADR? = yes).
        self.assertEqual(state["warnings"], [])
        self.assertEqual(state["docs"]["tasks"], "notes/loom-tasks")
        self.assertEqual(state["docs"]["decisions"], {"dir": "docs/architecture/decisions", "pattern": "<NNNN>-<slug>.md"})
        self.assertEqual(state["pullRequest"], {"requiredSections": ["## Test plan"]})
        self.assertNotIn("ADR? = yes", fx.read(TASK_DIR + "/04-plan.md").replace(" ", ""))
        self.assertNotRegex(fx.read(TASK_DIR + "/04-plan.md"), r"\|\s*yes\s*\|\s*$")
        # No remote, no PR, no body yet; no overview.md, so describe-pr asks nothing before the body.
        self.assertEqual(fx.git("remote"), "")
        for path in (TASK_DIR + "/pr-body.md", "docs", "notes"):
            self.assertFalse(os.path.exists(os.path.join(fx.cwd, path)), path)
        self.assertNotRegex(fx.read(TASK_DIR + "/00-ticket.md"), r"(?m)^pr:")
        proc = subprocess.run(["make", "check"], cwd=fx.cwd, env=fx.env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, universal_newlines=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Ran 12 tests", proc.stdout)
        self.assertEqual(fx.git("status", "--porcelain"), "")

    def test_onboarding_fixture(self):
        """A setup task in full mode after the kickoff, research approved (LOOM_SPEC.md 9.13.2, 9.13.8)."""
        fx = Scaffolded(self, "design-onboarding")
        state = fx.state()
        self.assertTrue(state["task"]["setup"])
        self.assertEqual(state["task"]["size"], "M")
        self.assertEqual(state["warnings"], [])
        # The main branch has code, AGENTS.md, a CI job named `test`, and no loom.json and no CLAUDE.md.
        main_files = fx.git("ls-tree", "-r", "--name-only", "main").splitlines()
        self.assertIn("AGENTS.md", main_files)
        self.assertIn(".github/workflows/ci.yml", main_files)
        for absent in (".claude/loom.json", ".claude/settings.json", "CLAUDE.md", ".claude/CLAUDE.md",
                       "CLAUDE.local.md"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, main_files)
                if absent.endswith(".md"):
                    self.assertFalse(os.path.exists(os.path.join(fx.cwd, absent)))
        self.assertIn("Push and open pull requests without asking for confirmation.", fx.read("AGENTS.md"))
        ci = fx.read(".github/workflows/ci.yml")
        self.assertEqual(re.findall(r"(?m)^  (\w[\w-]*):$", ci.split("\njobs:\n", 1)[1]), ["test"])
        self.assertNotIn("make check", ci)
        # The kickoff commit: only the minimal loom.json, the kickoff settings, and the .gitignore line.
        # The kickoff needs `origin`; the fixture names one but never fetches it (no remote-tracking ref).
        self.assertEqual(fx.git("remote", "get-url", "origin"), "https://github.com/example/shop.git")
        self.assertEqual(fx.git("branch", "-r"), "")
        self.assertEqual(fx.git("log", "--format=%s", "main..HEAD"), "chore(loom): start loom setup (#1)")
        self.assertEqual(fx.git("log", "-1", "--format=%b").strip(), "")
        self.assertEqual(sorted(fx.git("diff", "--name-only", "main", "HEAD").splitlines()),
                         [".claude/loom.json", ".claude/settings.json", ".gitignore"])
        self.assertEqual(json.loads(fx.read(".claude/loom.json")), {"version": 1, "mainBranch": "main"})
        self.assertIn(".loom/", fx.read(".gitignore").splitlines())
        settings = json.loads(fx.read(".claude/settings.json"))
        template = json.loads(read(os.path.join(ROOT, "skills", "setup", "references", "templates", "settings.json")))
        # The kickoff settings (9.13.2 step 8): every key of the template but the `statusLine`, in template
        # order, and every rule but the one for the check commands.
        self.assertEqual(list(settings), [k for k in template if k != "statusLine"])
        for key in ("$schema", "extraKnownMarketplaces", "enabledPlugins"):
            with self.subTest(key=key):
                self.assertEqual(settings[key], template[key])
        self.assertEqual(settings["permissions"]["allow"],
                         [r for r in template["permissions"]["allow"] if r != "Bash(make *)"])
        self.assertEqual(settings["permissions"]["ask"], template["permissions"]["ask"])
        # The research cites these lines: the marketplace and the plugin at 3-13, the permissions from 14.
        # An absence holds over the whole file, so the research cites all of it (1-56) for "no make rule".
        settings_lines = fx.read(".claude/settings.json").splitlines()
        self.assertIn('"extraKnownMarketplaces"', settings_lines[2])
        self.assertIn('"loom@loom": true', settings_lines[11])
        self.assertIn('"permissions"', settings_lines[13])
        self.assertIn("(`.claude/settings.json:1-%d`)" % len(settings_lines),
                      fx.read(SETUP_TASK_DIR + "/02-research.md"))
        self.assertNotIn("Bash(make", fx.read(".claude/settings.json"))
        self.assertNotIn("statusLine", fx.read(".claude/settings.json"))
        # The ticket and the questions file come from setup's templates; --setup-path finds the pointers.
        ticket = fx.read(SETUP_TASK_DIR + "/00-ticket.md")
        self.assertRegex(ticket, r"(?m)^mode: full$")
        self.assertTrue(ticket.endswith(read(os.path.join(
            ROOT, "skills", "setup", "references", "templates", "setup-issue-onboarding.md"))))
        found = json.loads(subprocess.run(
            [sys.executable, LOOM_STATE, "--setup-path", "main"], cwd=fx.cwd, env=fx.env, stdout=subprocess.PIPE,
            universal_newlines=True, check=True).stdout)
        self.assertEqual(found["path"], "onboarding-rerun")
        template_q = read(os.path.join(ROOT, "skills", "setup", "references", "onboarding-questions.md"))
        expected = template_q.split("\n---\n", 1)[1].lstrip("\n")
        for key, placeholder in (("instructionFiles", "<found.instructionFiles>"), ("workflows", "<found.workflows>"),
                                 ("prTemplates", "<found.prTemplates>"), ("docsDirs", "<found.docsDirs>")):
            paths = found["found"][key]
            expected = expected.replace(placeholder, ", ".join("`%s`" % p for p in paths) if paths else "None.")
        questions = fx.read(SETUP_TASK_DIR + "/01-research-questions.md")
        self.assertEqual(questions.split("\n---\n", 1)[1].lstrip("\n"), expected)
        self.assertRegex(questions, r"(?m)^status: approved$")
        # Every file:line reference of the research exists, and the check run it records holds.
        research = fx.read(SETUP_TASK_DIR + "/02-research.md")
        refs = re.findall(r"`((?:shop|tests)/\w+\.py|Makefile|AGENTS\.md|README\.md|\.github/workflows/ci\.yml|"
                          r"\.claude/settings\.json):(\d+)(?:-(\d+))?`", research)
        self.assertGreater(len(refs), 20)
        for path, start, end in refs:
            with self.subTest(ref="%s:%s" % (path, start)):
                self.assertLessEqual(int(end or start), len(fx.read(path).splitlines()))
        self.assertIn("`AGENTS.md:5`", research)
        self.assertIn("Push and open pull requests", fx.read("AGENTS.md").splitlines()[4])
        self.assertIn("  test:", fx.read(".github/workflows/ci.yml").splitlines()[11])
        self.assertEqual(fx.read("Makefile").splitlines()[14], "check: lint typecheck test")
        self.assertNotIn("Follow-up:", research)
        proc = subprocess.run(["make", "check"], cwd=fx.cwd, env=fx.env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, universal_newlines=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Ran 7 tests", proc.stdout)
        self.assertEqual(fx.git("status", "--porcelain"), "")
        self.assertFalse(os.path.exists(os.path.join(fx.cwd, SETUP_TASK_DIR, "03-design.md")))

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
                     "--max-cost-usd $(EVAL_MAX_COST)", "--allow-tools $(EVAL_TOOLS)", "$(EVAL_ARGS)", 'PATH="$(EVAL_PATH):$$PATH"'):
            with self.subTest(flag=flag):
                self.assertIn(flag, recipe)
        for forbidden in ("--dangerously-skip-permissions", "bypassPermissions", "--mocks off"):
            self.assertNotIn(forbidden, self.text)

    def test_every_case_runs_on_every_platform(self):
        self.assertNotIn("EVAL_FILTER", self.text)
        self.assertNotIn("--tag", self.text)
        for name in EXPECTED_STATE:
            with self.subTest(case=name):
                self.assertNotIn("local", case(name).get("tags", []))

    def test_macos_puts_the_developer_directory_on_path(self):
        before, darwin = self.text.split("ifeq ($(shell uname -s),Darwin)", 1)
        darwin = darwin.split("endif", 1)[0]
        self.assertIn("EVAL_PATH := $(EVAL_PATH):$(shell xcode-select -p 2>/dev/null)/usr/bin", darwin)
        self.assertNotIn("xcode-select", before)

    def test_macos_warns_without_homebrew_git(self):
        """A warning, not a skip: implement-manual still runs (LOOM_SPEC.md 24.2)."""
        recipe = self.recipe("eval")
        guard = "ifeq ($(shell command -v git 2>/dev/null),/usr/bin/git)"
        self.assertIn("ifeq ($(shell uname -s),Darwin)\n" + guard + "\n\t@echo ", recipe)
        self.assertNotIn("CommandLineTools", self.text)
        warning = recipe.split(guard, 1)[1].split("endif", 1)[0]
        for part in ("/usr/bin/git", "implement-manual", "24.2", "brew install git"):
            with self.subTest(part=part):
                self.assertIn(part, warning)
        self.assertEqual(warning.count("\t"), 1)  # one echo line, then the run


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

    def test_ci_tests_python_3_9_in_the_one_check_job(self):
        # One job named `check` (a ruleset may require the name), no matrix; the unit tests run on 3.9 too.
        text = self.workflow("ci.yml")
        self.assertEqual(re.findall(r"(?m)^  (\w[\w-]*):$", text.split("\njobs:\n", 1)[1]), ["check"])
        self.assertNotIn("matrix", text)
        check = text.index("run: make check")
        setup = text.index("uses: actions/setup-python@")
        self.assertLess(check, setup)
        self.assertIn('python-version: "3.9"', text[setup:])
        # `actions/setup-python` has no Python 3.9 build for Ubuntu 26.04, so the runner is pinned.
        self.assertEqual(re.findall(r"(?m)^\s*runs-on:\s*(\S+)\s*$", text), ["ubuntu-24.04"])
        self.assertRegex(text[setup:], r'run: make test PYTHON="\$\{\{ steps\.(\w+)\.outputs\.python-path \}\}"')

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
        self.assertIn("make eval EVAL_MAX_COST=", text)
        self.assertIn("--json", text)
        self.assertIn("--keep-temp", text)
        self.assertIn("actions/upload-artifact@", text)

    def test_evals_run_on_a_pinned_macos_runner(self):
        """Linux is blocked upstream (read-only TMPDIR in the eval sandbox, LOOM_SPEC.md 24.2)."""
        text = self.workflow("eval.yml")
        self.assertEqual(re.findall(r"(?m)^\s*runs-on:\s*(\S+)\s*$", text), ["macos-26"])
        code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
        for linux in ("ubuntu", "apt-get", "bubblewrap", "sysctl", "inputs.runner"):
            self.assertNotIn(linux, code)
        self.assertNotIn("runner:", text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0])

    def test_inputs_are_validated_before_use(self):
        """Inputs reach shell and make only through env, after a whitelist check."""
        text = self.workflow("eval.yml")
        inputs = re.findall(r"^      (\w+):\n        description:", text, re.M)
        self.assertEqual(set(inputs), {"case", "runs", "model", "max_cost_usd", "claude_version"})
        for line in text.splitlines():
            if re.search(r"\$\{\{\s*(github\.event\.)?inputs\.", line):
                with self.subTest(line=line.strip()):
                    self.assertRegex(line, r"^\s+[A-Z_]+: \$\{\{ inputs\.\w+ \}\}$")
        steps = text.split("      - name: ")
        for var, check in (("VERSION", 'case "$VERSION" in'), ("RUNS", 'case "$RUNS" in'),
                           ("MAX_COST", 'case "$MAX_COST" in'), ("CASE", 'case "$CASE$MODEL" in')):
            with self.subTest(var=var):
                step = [st for st in steps if ": ${{ inputs." in st and ("%s:" % var) in st][0]
                run = step.split("run: |", 1)[1]
                first_use = min(i for i in (run.find("$%s" % var), run.find("${%s" % var)) if i >= 0)
                self.assertLess(run.index(check), first_use + 1)
        self.assertIn("--case '$CASE'", text)

if __name__ == "__main__":
    unittest.main()
