"""Static checks for agents/*.md and skills/_shared/*.md (standard library only)."""
from __future__ import annotations

import glob
import os
import re
import unittest
from typing import Dict, List, Tuple

from loomtest import ROOT, loom_state

AGENTS_DIR = os.path.join(ROOT, "agents")
SHARED_DIR = os.path.join(ROOT, "skills", "_shared")
SPEC = os.path.join(ROOT, "LOOM_SPEC.md")

EXPECTED_AGENTS = {
    "codebase-locator",
    "codebase-analyzer",
    "codebase-pattern-finder",
    "web-search-researcher",
    "implementer",
    "implementation-reviewer",
}
ALLOWED_MODELS = {"sonnet", "haiku", "opus", "inherit"}
# Full model IDs (e.g. claude-sonnet-4-5, claude-opus-4-1-20250805) are also valid.
_MODEL_ID_RE = re.compile(r"^claude-[a-z0-9.-]+$")


def valid_model(model: str) -> bool:
    return model in ALLOWED_MODELS or bool(_MODEL_ID_RE.match(model))

KNOWN_TOOLS = {
    "Read", "Write", "Edit", "Grep", "Glob", "Bash", "WebSearch", "WebFetch",
    "NotebookEdit", "TodoWrite", "Skill", "Agent",
}
# Key sections each shared snippet must keep (headings, matched as line prefixes).
SHARED_SECTIONS = {
    "frontmatter.md": [
        "## Artifact frontmatter", "## Status values", "## Gates", "## Ticket frontmatter",
    ],
    "question-rounds.md": [
        "## Independence rule", "## Format", "## Numbering", "## Answering",
        "## Interactive questions", "## After each round", "## How many rounds",
        "### Accepted by default",
    ],
    "visual-conventions.md": [
        "## When a visual earns its place", "## File trees", "## Diff blocks", "## New shapes",
    ],
    "writing-style.md": ["## Rules", "## Where the rules apply", "## Glossary"],
    "final-answer.md": ["## Format", "## Fields", "## Rules", "## Examples"],
    "git-flow.md": [
        "## What needs confirmation", "## Checks", "## Commits", "### Subject", "### Body", "### Staging",
        "## Rebase", "## Push",
    ],
    "implementation-loop.md": ["## Inputs", "## Steps", "## Results", "## Rules"],
    "pr-update.md": ["## Steps"],
}
# HumanLayer-specific leftovers that must not appear in ported prompts.
FORBIDDEN = [
    r"humanlayer", r"\.humanlayer", r"thoughts/", r"SKILLBASE", r"rpi:", r"\blinear\b",
]
# Characters that would make an unquoted YAML scalar invalid or change its meaning.
_YAML_UNSAFE_START = tuple("!&*[]{}|>'\"%@`#,?:-")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def split_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """Strict-enough parser for agent frontmatter: one `key: value` per line."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("file does not start with a --- frontmatter line")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("frontmatter is not closed with ---")
    data: Dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line[0] in " \t" or ":" not in line:
            raise ValueError("unsupported frontmatter line: %r" % line)
        key, _, value = line.partition(":")
        key = key.strip()
        if key in data:
            raise ValueError("duplicate key %r" % key)
        data[key] = value.strip()
    return data, "\n".join(lines[end + 1:])


def spec_section(start: str, end: str) -> str:
    """Text of LOOM_SPEC.md between two headings; fails clearly if one is missing."""
    text = read(SPEC)
    for heading in (start, end):
        if heading not in text:
            raise AssertionError("LOOM_SPEC.md has no heading %r (renamed?)" % heading)
    return text.split(start, 1)[1].split(end, 1)[0]


def spec_agent_table() -> Dict[str, Tuple[str, List[str]]]:
    """Parse the LOOM_SPEC.md section 10.1 table: name -> (model, tools)."""
    section = spec_section("### 10.1 Definitions", "### 10.2 Reviewer verdict format")
    table: Dict[str, Tuple[str, List[str]]] = {}
    for line in section.splitlines():
        m = re.match(r"^\|\s*`([a-z-]+)`\s*\|\s*([\w.-]+)\s*\|\s*([^|]+)\|", line)
        if m:
            tools = [t.strip() for t in m.group(3).split(",") if t.strip()]
            table[m.group(1)] = (m.group(2), tools)
    return table


def agent_files() -> List[str]:
    return sorted(glob.glob(os.path.join(AGENTS_DIR, "*.md")))


class AgentFrontmatterTest(unittest.TestCase):
    def test_six_agents_exist(self):
        names = {os.path.splitext(os.path.basename(p))[0] for p in agent_files()}
        self.assertEqual(names, EXPECTED_AGENTS)

    def test_spec_table_lists_the_same_agents(self):
        self.assertEqual(set(spec_agent_table()), EXPECTED_AGENTS)

    def test_frontmatter_fields(self):
        for path in agent_files():
            stem = os.path.splitext(os.path.basename(path))[0]
            with self.subTest(agent=stem):
                fm, body = split_frontmatter(read(path))
                self.assertEqual(fm.get("name"), stem)
                self.assertNotIn(":", fm["name"])
                self.assertTrue(fm.get("description"), "description is missing")
                self.assertTrue(valid_model(fm.get("model", "")), "model %r" % fm.get("model"))
                self.assertTrue(body.strip(), "prompt body is empty")

    def test_description_is_a_safe_plain_scalar(self):
        for path in agent_files():
            with self.subTest(agent=os.path.basename(path)):
                desc = split_frontmatter(read(path))[0]["description"]
                self.assertFalse(desc.startswith(_YAML_UNSAFE_START), desc[:20])
                self.assertNotIn(": ", desc)
                self.assertNotIn(" #", desc)

    def test_description_says_loom_skills_invoke_it(self):
        for path in agent_files():
            stem = os.path.splitext(os.path.basename(path))[0]
            with self.subTest(agent=stem):
                desc = split_frontmatter(read(path))[0]["description"]
                self.assertIn("loom:%s" % stem, desc)
                self.assertIn("Invoked by", desc)

    def test_tools_are_known_and_match_the_spec(self):
        spec = spec_agent_table()
        for path in agent_files():
            stem = os.path.splitext(os.path.basename(path))[0]
            with self.subTest(agent=stem):
                fm = split_frontmatter(read(path))[0]
                tools = [t.strip() for t in fm.get("tools", "").split(",") if t.strip()]
                self.assertTrue(tools, "tools is missing")
                self.assertEqual(len(tools), len(set(tools)), "duplicate tools")
                self.assertLessEqual(set(tools), KNOWN_TOOLS)
                model, spec_tools = spec[stem]
                self.assertEqual(set(tools), set(spec_tools))
                self.assertEqual(fm["model"], model)


class AgentPromptTest(unittest.TestCase):
    def body(self, name: str) -> str:
        return split_frontmatter(read(os.path.join(AGENTS_DIR, name + ".md")))[1]

    def test_research_agents_document_and_never_critique(self):
        for name in ("codebase-locator", "codebase-analyzer", "codebase-pattern-finder"):
            with self.subTest(agent=name):
                self.assertIn("Document what exists, never critique", self.body(name))

    def test_read_only_bash_agents_list_allowed_commands(self):
        for name in ("codebase-locator", "implementation-reviewer"):
            with self.subTest(agent=name):
                body = self.body(name)
                self.assertIn("read-only", body)
                self.assertIn("git ls-files", body)
                self.assertRegex(body, r"Do not (modify|run any other command)")

    def test_web_researcher_requires_links(self):
        self.assertIn("Every finding has a link", self.body("web-search-researcher"))

    def test_implementer_rules(self):
        body = self.body("implementer")
        for needle in (
            "exactly ONE", "04-plan.md", "00-ticket.md", "`<docsDir>/conventions.md`", "`docsDir` from `.claude/loom.json`",
            ".claude/loom.json", "checks.check", "SubagentStop", "git commit", "git push",
            "git switch", "### Files changed", "### Checks", "### Deviations from the plan",
            "### Manual verification needed", "### Open problems", "## Ownership",
            "exactly as configured and unfiltered", "Run no other git command", "Use `rm` and `mv`", "continue from it",
            "Resolved Decisions",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_reviewer_verdict_format_matches_spec(self):
        body = self.body("implementation-reviewer")
        spec = spec_section("### 10.2 Reviewer verdict format", "## 11. Hooks")
        headings = re.findall(r"^(#{2,3} [^\n←]+?)\s*(?:←.*)?$", spec, re.MULTILINE)
        self.assertEqual(len(headings), 5, headings)
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertIn(heading, body)
        self.assertIn("`blocking` by default", body)

    def test_reviewer_fix_mode_respects_committed_phases(self):
        body = self.body("implementation-reviewer")
        self.assertIn("### Fix mode", body)
        self.assertIn("already committed are not missing", body)
        self.assertIn("--grep='^Phase N:' origin/<mainBranch>..HEAD", body)
        self.assertNotIn("-n 10", body)
        self.assertNotIn("edits files in the task directory", body)

    def test_read_only_agents_forbid_writing_flags(self):
        locator = self.body("codebase-locator")
        for flag in ("-exec", "-execdir", "-ok", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"):
            with self.subTest(flag=flag):
                self.assertIn("`%s`" % flag, locator)
        for name in ("codebase-locator", "implementation-reviewer"):
            with self.subTest(agent=name):
                self.assertIn("`>>`", self.body(name))
        self.assertIn("--output", self.body("implementation-reviewer"))


class SharedSnippetsTest(unittest.TestCase):
    def test_snippets_exist(self):
        names = {os.path.basename(p) for p in glob.glob(os.path.join(SHARED_DIR, "*.md"))}
        self.assertEqual(names, set(SHARED_SECTIONS))

    def test_h1_and_key_sections(self):
        for name, sections in SHARED_SECTIONS.items():
            lines = read(os.path.join(SHARED_DIR, name)).splitlines()
            with self.subTest(snippet=name):
                self.assertTrue(lines and lines[0].startswith("# "), "first line is not an H1")
                self.assertEqual(sum(1 for l in lines if re.match(r"^# ", l)), 1, "more than one H1")
            for section in sections:
                with self.subTest(snippet=name, section=section):
                    self.assertTrue(any(l.startswith(section) for l in lines))

    def test_glossary_has_every_spec_term(self):
        spec = spec_section("## 3. Glossary", "## 4. Architecture")
        terms = re.findall(r"^\|\s*\*\*([^*]+)\*\*", spec, re.MULTILINE)
        self.assertGreaterEqual(len(terms), 10)
        style = read(os.path.join(SHARED_DIR, "writing-style.md"))
        for term in terms:
            with self.subTest(term=term):
                self.assertIn("| **%s** |" % term, style)

    def test_final_answer_has_the_next_step(self):
        self.assertIn("Next: /clear, then /loom:next", read(os.path.join(SHARED_DIR, "final-answer.md")))

    def test_clarify_line_is_shared(self):
        final = read(os.path.join(SHARED_DIR, "final-answer.md"))
        rounds = read(os.path.join(SHARED_DIR, "question-rounds.md"))
        self.assertIn("`Clarify:`", final)
        self.assertIn("`Clarify:`", rounds)
        self.assertNotIn("ask about it in the final message.", rounds)

    def test_rounds_read_size_from_loom_state(self):
        self.assertIn("`task.size`", read(os.path.join(SHARED_DIR, "question-rounds.md")))

    def test_ticket_size_field_is_documented(self):
        self.assertRegex(read(os.path.join(SHARED_DIR, "frontmatter.md")), r"(?m)^size: [SML]")

    def test_question_round_example_parses_in_loom_state(self):
        text = read(os.path.join(SHARED_DIR, "question-rounds.md"))
        fmt = text.split("## Format", 1)[1]
        block = re.search(r"```markdown\n(.*?)```", fmt, re.DOTALL).group(1)
        self.assertEqual(loom_state().count_open_questions(block), 2)


class NoHumanLayerLeftoversTest(unittest.TestCase):
    def test_no_forbidden_strings(self):
        paths = agent_files() + sorted(glob.glob(os.path.join(SHARED_DIR, "*.md")))
        self.assertTrue(paths)
        for path in paths:
            text = read(path)
            for pattern in FORBIDDEN:
                with self.subTest(file=os.path.relpath(path, ROOT), pattern=pattern):
                    self.assertIsNone(re.search(pattern, text, re.IGNORECASE))

    def test_notice_credits_humanlayer(self):
        notice = read(os.path.join(ROOT, "NOTICE"))
        self.assertTrue(notice.startswith("loom\n"))
        self.assertIn("HumanLayer", notice)
        self.assertIn("Apache License, Version 2.0", notice)


if __name__ == "__main__":
    unittest.main()
