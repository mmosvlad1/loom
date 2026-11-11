"""Static, spec-driven checks for skills/*/SKILL.md and their templates (standard library only)."""
from __future__ import annotations

import glob
import os
import re
import unittest
from typing import Dict, List, Optional, Tuple

from loomtest import ROOT, loom_state

SKILLS_DIR = os.path.join(ROOT, "skills")
AGENTS_DIR = os.path.join(ROOT, "agents")
SPEC = os.path.join(ROOT, "LOOM_SPEC.md")

# Skills of milestone M3. Later milestones add more skill directories; the
# generic checks below cover every directory that exists.
M3_SKILLS = {"research-questions", "research", "design", "plan", "iterate"}
M4_SKILLS = {"implement", "describe-pr", "finish-task", "next"}
M5_SKILLS = {"setup", "backlog", "start-task"}
STATE_SKILLS = M3_SKILLS | M4_SKILLS | M5_SKILLS
# Skills that `next` runs by reading their SKILL.md (§9.12).
NEXT_RUNS = {"research-questions", "research", "design", "plan", "implement"}
# Skill directories that only hold reference files until a later milestone (none since M5).
REFERENCE_ONLY_DIRS: Dict[str, List[str]] = {}
PHASE_SKILLS = {"research-questions", "research", "design", "plan"}
# Artifact file -> skill that writes it from references/template.md.
ARTIFACT_SKILL = {
    "01-research-questions.md": "research-questions",
    "02-research.md": "research",
    "03-design.md": "design",
    "04-plan.md": "plan",
}
# §7.5 lists the skills that must not fork; research-questions and iterate also spawn agents.
EXTRA_NO_FORK = {"research-questions", "iterate"}
EFFORT_VALUES = {"low", "medium", "high", "xhigh", "max"}
STATE_INJECTION = '!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json`'
STATE_INJECTION_PR = '!`"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr`'
RESOLVED_TABLE_HEADER = "| # | Question | Decision | Rationale | Round | ADR? |"
FORBIDDEN = [
    r"humanlayer", r"\.humanlayer", r"thoughts/", r"SKILLBASE", r"rpi:", r"\blinear\b",
    r"riptide", r"structure outline", r"permalink",
]
_YAML_UNSAFE_START = tuple("!&*[]{}|>'\"%@`#,?:-")

ls = loom_state()


def reference_files(pattern: str = "*") -> List[str]:
    """Every file below skills/*/references/ (recursive), matching a glob pattern."""
    return sorted(
        p for p in glob.glob(os.path.join(SKILLS_DIR, "*", "references", "**", pattern), recursive=True)
        if os.path.isfile(p)
    )


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def split_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """Strict-enough parser for skill frontmatter: one `key: value` per line."""
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


def spec_text() -> str:
    return read(SPEC)


def spec_section(start: str, end: str) -> str:
    text = spec_text()
    for heading in (start, end):
        if heading not in text:
            raise AssertionError("LOOM_SPEC.md has no heading %r (renamed?)" % heading)
    return text.split(start, 1)[1].split(end, 1)[0]


def spec_model_effort() -> Dict[str, Tuple[str, str]]:
    """Parse the §9.0 table: skill -> (model, effort)."""
    section = spec_section("### 9.0 Common rules", "### 9.1 `setup`")
    table: Dict[str, Tuple[str, str]] = {}
    for line in section.splitlines():
        m = re.match(r"^\|\s*([a-z, -]+?)\s*\|\s*([\w.-]+)\s*\|\s*([\w-]+)\s*\|\s*$", line)
        if not m or not re.search(r"[a-z]", m.group(1)):
            continue  # header or separator row
        for name in m.group(1).split(","):
            table[name.strip()] = (m.group(2), m.group(3))
    return table


def spec_no_fork_skills() -> List[str]:
    section = spec_section("### 7.5 Skills and forked context", "## 8. The State Script")
    sentence = section.split("must **not**", 1)[0]
    return re.findall(r"`([a-z-]+)`", sentence)


def spec_layout_skills() -> List[str]:
    """Skill directory names from the §4.1 layout tree."""
    section = spec_section("### 4.1 Plugin repository layout", "### 4.2 Project-side footprint")
    tree = section.split("├── skills/", 1)[1].split("├── agents/", 1)[0]
    return [n for n in re.findall(r"^│   [├└]── ([a-z_-]+)/", tree, re.MULTILINE) if n != "_shared"]


def spec_artifact_blocks() -> Dict[str, List[str]]:
    """Parse §13.2: artifact file -> its markdown block lines."""
    section = spec_section("### 13.2 Working artifacts", "### 13.3 Visual conventions")
    blocks: Dict[str, List[str]] = {}
    for m in re.finditer(r"\*\*`([\w.-]+\.md)`\*\*[^\n]*\n```markdown\n(.*?)\n```", section, re.DOTALL):
        blocks[m.group(1)] = m.group(2).splitlines()
    return blocks


def spec_frontmatter_keys() -> List[str]:
    section = spec_section("### 13.1 Frontmatter and gates", "### 13.2 Working artifacts")
    block = re.search(r"```yaml\n---\n(.*?)\n---\n```", section, re.DOTALL).group(1)
    return [line.split(":", 1)[0].strip() for line in block.splitlines() if ":" in line]


def _strip_note(heading: str) -> str:
    return heading.split("←", 1)[0].strip()


def normalize_heading(text: str) -> str:
    """Map placeholder headings to one form: rounds and implementation phases."""
    text = _strip_note(text)
    if re.match(r"^Open Questions\b", text):
        return "Open Questions"
    if re.match(r"^Phase (\d+|N): ", text):
        return "Phase N:"
    return text


def h2_headings(lines: List[str]) -> List[str]:
    """`## ` headings (unindented, outside code fences), normalized, runs of Phase N collapsed."""
    result: List[str] = []
    for line, level, text in ls.iter_markdown_lines("\n".join(lines)):
        if level == 2 and line.startswith("## "):
            heading = normalize_heading(text)
            if heading == "Phase N:" and result and result[-1] == heading:
                continue
            result.append(heading)
    return result


def spec_h2_headings(block: List[str]) -> List[str]:
    result: List[str] = []
    for line in block:
        if line.startswith("## "):
            heading = normalize_heading(line[3:])
            if heading == "Phase N:" and result and result[-1] == heading:
                continue
            result.append(heading)
    return result


def skill_dirs() -> List[str]:
    """Skill directories with a SKILL.md (reference-only directories are checked separately)."""
    return sorted(
        d for d in os.listdir(SKILLS_DIR)
        if d != "_shared" and os.path.isfile(os.path.join(SKILLS_DIR, d, "SKILL.md"))
    )


def skill_md(name: str) -> str:
    return read(os.path.join(SKILLS_DIR, name, "SKILL.md"))


def template(name: str) -> str:
    return read(os.path.join(SKILLS_DIR, name, "references", "template.md"))


def allowed_tool_rules(value: str) -> List[str]:
    """Split an `allowed-tools` string into rules; spaces inside parentheses stay."""
    rules: List[str] = []
    buf, depth = "", 0
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch in " ," and depth == 0:
            if buf:
                rules.append(buf)
            buf = ""
            continue
        buf += ch
    if buf:
        rules.append(buf)
    return rules


def rule_allows(rule: str, tool: str, arg: str) -> bool:
    """Match one `Tool(spec)` permission rule: exact, or a trailing `*` as a prefix wildcard."""
    m = re.match(r"^(\w+)\((.*)\)$", rule)
    if not m or m.group(1) != tool:
        return False
    spec = m.group(2)
    if spec.endswith("*"):
        return arg.startswith(spec[:-1])
    return arg == spec


def skill_rules(name: str) -> List[str]:
    return allowed_tool_rules(split_frontmatter(skill_md(name))[0].get("allowed-tools", ""))


def agent_names() -> set:
    return {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(AGENTS_DIR, "*.md"))}


class SpecParsingTest(unittest.TestCase):
    """The spec tables these tests depend on still parse."""

    def test_model_effort_table(self):
        table = spec_model_effort()
        self.assertLessEqual(M3_SKILLS, set(table))
        self.assertEqual(table["design"], ("inherit", "high"))
        self.assertEqual(table["next"], ("inherit", "default"))
        self.assertEqual(table["finish-task"], ("haiku", "low"))

    def test_no_fork_list(self):
        self.assertEqual(set(spec_no_fork_skills()), {"research", "design", "plan", "implement"})

    def test_layout_lists_the_m3_skills(self):
        self.assertLessEqual(M3_SKILLS, set(spec_layout_skills()))

    def test_artifact_blocks(self):
        self.assertLessEqual(set(ARTIFACT_SKILL), set(spec_artifact_blocks()))

    def test_frontmatter_keys(self):
        self.assertEqual(
            spec_frontmatter_keys(), ["task", "phase", "status", "based_on", "git_commit", "updated"]
        )


class SkillFrontmatterTest(unittest.TestCase):
    def test_m3_skills_exist(self):
        self.assertLessEqual(M3_SKILLS, set(skill_dirs()))

    def test_m4_skills_exist(self):
        self.assertLessEqual(M4_SKILLS, set(skill_dirs()))

    def test_m5_skills_exist(self):
        self.assertLessEqual(M5_SKILLS, set(skill_dirs()))

    def test_spec_layout_has_a_skill_for_every_directory(self):
        self.assertEqual(set(spec_layout_skills()), set(skill_dirs()))

    def test_every_directory_is_a_skill_or_reference_only(self):
        dirs = {d for d in os.listdir(SKILLS_DIR) if os.path.isdir(os.path.join(SKILLS_DIR, d))} - {"_shared"}
        self.assertEqual(dirs - set(skill_dirs()), set(REFERENCE_ONLY_DIRS) - set(skill_dirs()))
        for name, files in REFERENCE_ONLY_DIRS.items():
            if name in skill_dirs():
                continue  # the later milestone added SKILL.md
            with self.subTest(dir=name):
                found = sorted(
                    os.path.relpath(os.path.join(r, f), os.path.join(SKILLS_DIR, name))
                    for r, _, fs in os.walk(os.path.join(SKILLS_DIR, name)) for f in fs
                )
                self.assertEqual(found, files)

    def test_every_skill_dir_is_in_the_spec_layout(self):
        layout = set(spec_layout_skills())
        for name in skill_dirs():
            with self.subTest(skill=name):
                self.assertIn(name, layout)

    def test_frontmatter_fields(self):
        for name in skill_dirs():
            with self.subTest(skill=name):
                fm, body = split_frontmatter(skill_md(name))
                self.assertEqual(_unquote(fm.get("name", name)), name)
                self.assertTrue(fm.get("description"), "description is missing")
                self.assertEqual(fm.get("disable-model-invocation"), "true")
                self.assertNotEqual(fm.get("context"), "fork")
                self.assertTrue(body.strip(), "skill body is empty")

    def test_description_is_a_safe_one_line_plain_scalar(self):
        for name in skill_dirs():
            with self.subTest(skill=name):
                desc = split_frontmatter(skill_md(name))[0]["description"]
                self.assertFalse(desc.startswith(_YAML_UNSAFE_START), desc[:20])
                self.assertNotIn(": ", desc)
                self.assertNotIn(" #", desc)
                self.assertNotRegex(desc, r"[<>]")  # shown as &lt; &gt; in the skill listing

    def test_argument_hint_is_quoted(self):
        for name in skill_dirs():
            hint = split_frontmatter(skill_md(name))[0].get("argument-hint")
            if hint is None:
                continue
            with self.subTest(skill=name):
                self.assertTrue(hint.startswith('"') and hint.endswith('"'), hint)

    def test_m3_skills_take_arguments(self):
        for name in STATE_SKILLS:
            with self.subTest(skill=name):
                fm, body = split_frontmatter(skill_md(name))
                self.assertIn("argument-hint", fm)
                self.assertIn("$ARGUMENTS", body)

    def test_model_and_effort_match_the_spec(self):
        table = spec_model_effort()
        for name in skill_dirs():
            with self.subTest(skill=name):
                fm = split_frontmatter(skill_md(name))[0]
                self.assertIn(name, table, "skill missing from the §9.0 table")
                model, effort = table[name]
                if "model" in fm or name in STATE_SKILLS:
                    self.assertEqual(fm.get("model"), model)
                if effort == "default":
                    self.assertNotIn("effort", fm, "'default' effort means: omit the field")
                else:
                    self.assertIn(effort, EFFORT_VALUES)
                    if "effort" in fm or name in STATE_SKILLS:
                        self.assertEqual(fm.get("effort"), effort)

    def test_no_fork_for_agent_spawning_skills(self):
        for name in set(spec_no_fork_skills()) | EXTRA_NO_FORK:
            path = os.path.join(SKILLS_DIR, name, "SKILL.md")
            if not os.path.isfile(path):
                continue  # later milestone
            with self.subTest(skill=name):
                self.assertNotIn("context", split_frontmatter(read(path))[0])


class PermissionTest(unittest.TestCase):
    """Outside auto mode an injected command without an allow rule aborts the skill (§24.2)."""

    def test_every_injection_has_an_allowed_tools_rule(self):
        for name in skill_dirs():
            body = split_frontmatter(skill_md(name))[1]
            commands = re.findall(r"(?:^|(?<=\s))!`([^`]+)`", body)
            rules = skill_rules(name)
            for command in commands:
                with self.subTest(skill=name, command=command):
                    self.assertTrue(any(rule_allows(r, "Bash", command) for r in rules), rules)
            if name in STATE_SKILLS:
                self.assertTrue(commands, "%s injects no state" % name)

    def test_only_loom_state_is_injected(self):
        for name in skill_dirs():
            for command in re.findall(r"!`([^`]+)`", skill_md(name)):
                with self.subTest(skill=name, command=command):
                    self.assertTrue(command.startswith('"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state '), command)
                    self.assertNotIn("date", command)

    def test_loom_state_calls_in_the_body_are_allowed(self):
        for name in STATE_SKILLS:
            body = split_frontmatter(skill_md(name))[1]
            calls = set(re.findall(r"`(loom-state --[^`]*)`", body))
            calls.add("loom-state --json")  # final-answer.md runs the bare form (bin/ is on PATH)
            for call in calls:
                with self.subTest(skill=name, call=call):
                    self.assertTrue(any(rule_allows(r, "Bash", call) for r in skill_rules(name)))

    def test_body_calls_use_the_bare_form(self):
        # Full path only in the injection line (and its rule); body Bash calls match the §19.3 allowlist.
        full = '"${CLAUDE_PLUGIN_ROOT}"/bin/loom-state'
        for name in skill_dirs():
            body = split_frontmatter(skill_md(name))[1]
            with self.subTest(skill=name):
                for line in body.splitlines():
                    if full in line:
                        self.assertTrue(line.startswith("!`"), line)
                calls = re.findall(r"`(loom-state [^`]*)`", body)
                for call in calls:
                    if call.startswith("loom-state --"):
                        self.assertTrue(any(rule_allows(r, "Bash", call) for r in skill_rules(name)), call)
            if name in STATE_SKILLS:
                self.assertIn("`loom-state --json`", body)

    def test_full_path_rules_match_only_injections(self):
        for name in skill_dirs():
            body = split_frontmatter(skill_md(name))[1]
            injected = re.findall(r"!`([^`]+)`", body)
            for rule in skill_rules(name):
                if "${CLAUDE_PLUGIN_ROOT}\"/bin/" in rule:
                    with self.subTest(skill=name, rule=rule):
                        self.assertTrue(any(rule_allows(rule, "Bash", c) for c in injected))

    def test_shared_reads_are_allowed(self):
        for name in skill_dirs():
            body = skill_md(name)
            reads = re.findall(r"\$\{(?:CLAUDE_PLUGIN_ROOT\}/skills|CLAUDE_SKILL_DIR\})/[\w./-]+", body)
            if not reads:
                continue
            with self.subTest(skill=name):
                self.assertIn("Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)", skill_rules(name))

    def test_plugin_files_are_read_before_any_question(self):
        # allowed-tools lasts one turn: plugin-file reads belong before step 1 (which may ask the user).
        for name in skill_dirs():
            body = split_frontmatter(skill_md(name))[1]
            if "## 1. Check preconditions" not in body:
                continue
            before = body.split("## 1. Check preconditions", 1)[0]
            with self.subTest(skill=name):
                self.assertIn("Read these files before you ask the user anything.", before)
                self.assertIn("last only until the user's next message", before)
                if name in ARTIFACT_SKILL.values():
                    self.assertIn("${CLAUDE_SKILL_DIR}/references/template.md", before)
                after = body.split("## 1. Check preconditions", 1)[1]
                self.assertNotRegex(after, r"(?m)^\s*(?:\d+\.\s+)?Read `\$\{CLAUDE_(?:SKILL_DIR|PLUGIN_ROOT)\}")

    def test_spec_allowlists_loom_state(self):
        section = spec_section("### 19.3 `.claude/settings.json`", "## 20. Testing the Harness")
        self.assertIn("`loom-state --json`, `loom-state --json --pr`", section)
        self.assertIn("`loom-state --slug *`", section)

    def test_skills_take_the_date_from_loom_state(self):
        for name in M3_SKILLS | M5_SKILLS | {"implement", "describe-pr"}:
            with self.subTest(skill=name):
                self.assertIn('"Today" below means `today` from the state.', skill_md(name))

    def test_rule_matcher(self):
        self.assertTrue(rule_allows("Bash(git add *)", "Bash", "git add x"))
        self.assertFalse(rule_allows("Bash(loom-state --json)", "Bash", "loom-state --json --pr"))
        self.assertFalse(rule_allows("Read(/x/**)", "Bash", "/x/**"))
        self.assertEqual(allowed_tool_rules("Bash(a b) Read(c), Bash(d)"), ["Bash(a b)", "Read(c)", "Bash(d)"])


class SnippetVariableTest(unittest.TestCase):
    """Files read with the Read tool get no ${...} substitution."""

    def test_shared_snippets_and_templates_have_no_variables(self):
        paths = glob.glob(os.path.join(SKILLS_DIR, "_shared", "*.md"))
        paths += reference_files()  # also templates/ and stacks/ of setup, and non-markdown templates
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(file=os.path.relpath(path, ROOT)):
                self.assertNotIn("${", read(path))

    def test_superseded_plan_is_documented(self):
        self.assertIn("04-plan.superseded.md", read(os.path.join(SKILLS_DIR, "_shared", "frontmatter.md")))


class SkillBodyTest(unittest.TestCase):
    def test_phase_skills_inject_state(self):
        for name in PHASE_SKILLS:
            with self.subTest(skill=name):
                self.assertIn(STATE_INJECTION, skill_md(name))
        self.assertIn(STATE_INJECTION_PR, skill_md("iterate"))

    def test_injections_start_a_line_or_follow_whitespace(self):
        for name in skill_dirs():
            for m in re.finditer(r"!`", skill_md(name)):
                with self.subTest(skill=name, offset=m.start()):
                    before = skill_md(name)[m.start() - 1] if m.start() else "\n"
                    self.assertIn(before, " \t\n")

    def test_plugin_and_skill_paths_resolve(self):
        pattern = re.compile(r"\$\{(CLAUDE_PLUGIN_ROOT|CLAUDE_SKILL_DIR)\}\"?/([\w./-]+)")
        for name in skill_dirs():
            for m in pattern.finditer(skill_md(name)):
                rel = m.group(2).rstrip(".")
                base = ROOT if m.group(1) == "CLAUDE_PLUGIN_ROOT" else os.path.join(SKILLS_DIR, name)
                with self.subTest(skill=name, path=m.group(0)):
                    self.assertTrue(os.path.exists(os.path.join(base, rel)), rel)

    def test_templates_name_shared_snippets_without_variables(self):
        # Skills read templates with the Read tool, so ${...} variables are not substituted there.
        for name in ARTIFACT_SKILL.values():
            text = template(name)
            with self.subTest(skill=name):
                self.assertNotIn("${", text)
            for snippet in re.findall(r"shared `([\w-]+\.md)`", text):
                with self.subTest(skill=name, snippet=snippet):
                    self.assertTrue(os.path.isfile(os.path.join(SKILLS_DIR, "_shared", snippet)))

    def test_referenced_agents_exist(self):
        agents = agent_names()
        for name in skill_dirs():
            refs = set(re.findall(r"(?<![/\w])loom:([a-z][a-z-]*)", skill_md(name)))
            for ref in refs:
                with self.subTest(skill=name, agent=ref):
                    self.assertIn(ref, agents)

    def test_referenced_commands_are_spec_skills(self):
        layout = set(spec_layout_skills())
        for name in skill_dirs():
            for ref in set(re.findall(r"/loom:([a-z][a-z-]*)", skill_md(name))):
                with self.subTest(skill=name, command=ref):
                    self.assertIn(ref, layout)

    def test_research_skills_spawn_research_agents(self):
        for name in ("research-questions", "research"):
            body = skill_md(name)
            for agent in ("codebase-locator", "codebase-analyzer", "codebase-pattern-finder", "web-search-researcher"):
                with self.subTest(skill=name, agent=agent):
                    self.assertIn("`loom:%s`" % agent, body)

    def test_shared_snippets_are_referenced(self):
        expected = {
            "research-questions": ["frontmatter.md", "writing-style.md", "final-answer.md"],
            "research": ["frontmatter.md", "writing-style.md", "visual-conventions.md", "final-answer.md"],
            "design": ["frontmatter.md", "question-rounds.md", "visual-conventions.md", "writing-style.md", "final-answer.md"],
            "plan": ["frontmatter.md", "question-rounds.md", "visual-conventions.md", "writing-style.md", "final-answer.md"],
            "iterate": ["frontmatter.md", "question-rounds.md", "visual-conventions.md", "writing-style.md",
                        "final-answer.md", "git-flow.md", "implementation-loop.md", "pr-update.md"],
            "implement": ["implementation-loop.md", "git-flow.md", "pr-update.md", "frontmatter.md", "writing-style.md",
                          "final-answer.md"],
            "describe-pr": ["git-flow.md", "visual-conventions.md", "writing-style.md", "final-answer.md"],
            "finish-task": ["git-flow.md", "writing-style.md", "final-answer.md"],
            "next": ["final-answer.md", "writing-style.md"],
        }
        for name, snippets in expected.items():
            for snippet in snippets:
                with self.subTest(skill=name, snippet=snippet):
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/_shared/%s" % snippet, skill_md(name))

    def test_artifact_skills_use_their_template(self):
        for name in ARTIFACT_SKILL.values():
            with self.subTest(skill=name):
                self.assertIn("${CLAUDE_SKILL_DIR}/references/template.md", skill_md(name))

    def test_no_hard_coded_main_branch_or_work_dir(self):
        for name in skill_dirs():
            body = skill_md(name)
            with self.subTest(skill=name):
                self.assertNotIn(".loom/tasks", body)
                self.assertNotRegex(body, r"origin/main\b")
                self.assertNotRegex(body, r"git (switch|rebase|checkout|pull origin) main\b")

    def test_no_forbidden_strings(self):
        paths = glob.glob(os.path.join(SKILLS_DIR, "*", "SKILL.md"))
        paths += reference_files()
        for path in paths:
            text = read(path)
            for pattern in FORBIDDEN:
                with self.subTest(file=os.path.relpath(path, ROOT), pattern=pattern):
                    self.assertIsNone(re.search(pattern, text, re.IGNORECASE))


class InputDisciplineTest(unittest.TestCase):
    """The input rules that the M6 evals grade are stated explicitly."""

    def test_research_full_mode_never_reads_the_ticket(self):
        body = skill_md("research")
        self.assertIn("### Full mode: read only `01-research-questions.md`", body)
        self.assertIn("**Never read `00-ticket.md`.**", body)
        self.assertIn("Tell your agents nothing from the ticket.", body)
        self.assertIn("### Quick mode: read `00-ticket.md`", body)

    def test_design_and_plan_never_read_research_questions(self):
        for name in ("design", "plan"):
            with self.subTest(skill=name):
                self.assertIn("**Never read `01-research-questions.md`.**", skill_md(name))

    def test_research_describes_only(self):
        body = skill_md("research")
        self.assertIn("Your only job: describe what exists", body)
        self.assertIn("2-6 agent tasks", body)
        self.assertIn("## 5. Claim check", body)
        self.assertIn("**one** `loom:codebase-analyzer`", body)
        self.assertIn("Not Found / Unclear", body)
        self.assertIn("git rev-parse --short HEAD", body)

    def test_questions_never_reveal_what_will_be_built(self):
        self.assertIn("The questions never reveal what will be built", skill_md("research-questions"))

    def test_design_writes_all_questions_open(self):
        body = skill_md("design")
        self.assertIn("### All questions are open", body)
        self.assertIn("Leave **Resolved Decisions** empty", body)

    def test_plan_is_vertical_and_written_at_once(self):
        body = skill_md("plan")
        self.assertIn("**vertical slice**", body)
        self.assertIn("Write the **whole**", body)
        self.assertIn("Phase N never needs phase N+1 to verify.", body)


class IterateTest(unittest.TestCase):
    def test_situations_are_covered(self):
        body = skill_md("iterate")
        for section in (
            "## Answer a round", "## Feedback on an artifact", "## Approve",
            "## Fix an implemented phase", "### The fix loop", "## Change an approved plan",
            "## Post-PR fix", "## Rebase", "## Mode change",
        ):
            with self.subTest(section=section):
                self.assertIn(section, body)

    def test_answer_forms(self):
        body = skill_md("iterate")
        for form in ("`ok`", "`1a, 2b`", "`3: <text>`", "`accept all except 2, 4`"):
            with self.subTest(form=form):
                self.assertIn(form, body)

    def test_round_cap_marker_matches_loom_state(self):
        body = skill_md("iterate")
        marker = "accepted by default — revisit if needed"
        self.assertIn(marker, body)
        self.assertIn(ls.ACCEPTED_BY_DEFAULT, marker)
        self.assertIn(marker, read(os.path.join(SKILLS_DIR, "_shared", "question-rounds.md")))

    def test_approve_repeat_is_defined(self):
        body = skill_md("iterate")
        self.assertIn("/loom:iterate approve approve", body)
        self.assertIn("contains the word `approve` twice", body)

    def test_git_commands_and_confirmations(self):
        body = skill_md("iterate")
        for needle in (
            "gh run view <databaseId> --log-failed", "gh pr view --comments",
            "git rebase origin/<main>", "git push --force-with-lease", "Ask for confirmation.",
            "gh pr edit", "`loom:implementer`", "`loom:implementation-reviewer` in fix mode",
            "implement.maxFixAttempts", "02-research.superseded.md", "04-plan.superseded.md",
            "## Plan change — <today>", "git remote get-url origin",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def detection_rows(self) -> List[Tuple[int, str, str]]:
        body = skill_md("iterate")
        table = body.split("## 2. Detect the situation", 1)[1].split("\n---\n", 1)[0]
        return [
            (int(m.group(1)), m.group(2), m.group(3))
            for m in re.finditer(r"(?m)^\| (\d+) \| (.+?) \| (.+?) \|$", table)
        ]

    def test_detection_rows_are_numbered_and_link_to_sections(self):
        rows = self.detection_rows()
        self.assertEqual([r[0] for r in rows], list(range(1, len(rows) + 1)))
        headings = {
            re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-")
            for h in re.findall(r"(?m)^#{2,3} (.+)$", skill_md("iterate"))
        }
        for anchor in re.findall(r"\]\(#([a-z0-9-]+)\)", skill_md("iterate")):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, headings)

    def test_blocked_row_comes_before_pr_and_done_phase_rows(self):
        order = [section for _, _, section in self.detection_rows()]
        def index(fragment: str) -> int:
            return next(i for i, s in enumerate(order) if fragment in s)
        blocked = index("Fix a blocked phase")
        self.assertIn("`implementation.blocked` is set", self.detection_rows()[blocked][1])
        self.assertLess(blocked, index("Post-PR fix"))
        self.assertLess(blocked, index("Fix an implemented phase"))
        self.assertGreater(blocked, index("Answer a round"))

    def test_gate_rows_come_before_pr_and_blocked_rows(self):
        order = [section for _, _, section in self.detection_rows()]
        def index(fragment: str) -> int:
            return next(i for i, s in enumerate(order) if fragment in s)
        for gate in ("Approve", "Answer a round"):
            with self.subTest(gate=gate):
                self.assertLess(index(gate), index("Post-PR fix"))
                self.assertLess(index(gate), index("Fix a blocked phase"))

    def test_plan_change_row_comes_before_the_open_pr_row(self):
        rows = self.detection_rows()
        order = [section for _, _, section in rows]
        plan = next(i for i, s in enumerate(order) if "Change an approved plan" in s)
        pr = next(i for i, s in enumerate(order) if "Post-PR fix" in s)
        self.assertLess(plan, pr)
        between = [s for s in order[plan + 1:pr]]
        self.assertEqual(between, ["[Uncommitted changes after implementation](#uncommitted-changes-after-implementation)"])
        self.assertIn("adds, removes, or changes an implementation phase", rows[plan][1])
        self.assertIn("also with a PR open", rows[plan][1])
        self.assertGreater(plan, next(i for i, s in enumerate(order) if "Fix a blocked phase" in s))

    def test_uncommitted_changes_row(self):
        rows = self.detection_rows()
        order = [section for _, _, section in rows]
        def index(fragment: str) -> int:
            return next(i for i, s in enumerate(order) if fragment in s)
        row = index("Uncommitted changes after implementation")
        self.assertGreater(row, index("Change an approved plan"))
        self.assertGreater(row, index("Fix a blocked phase"))
        self.assertLess(row, index("Post-PR fix"))
        self.assertLess(row, index("Fix an implemented phase"))
        self.assertIn("`workingTreeDocsOnly` is `false`", rows[row][1])
        section = skill_md("iterate").split("## Uncommitted changes after implementation", 1)[1].split("\n---\n", 1)[0]
        for needle in ("git status --short", "git diff --stat HEAD", "keep these changes as a fix", "`loom:implementation-reviewer` in fix mode",
                       "[the fix loop](#the-fix-loop)", "git commit -F", "`log-format.md`", "`pr-update.md`",
                       '"Stash and discard" in `git-flow.md`', "lost and cannot be recovered", "`Next:` from `loom-state`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, section)

    def test_finish_plan_change_row_position(self):
        rows = self.detection_rows()
        order = [section for _, _, section in rows]
        def index(fragment: str) -> int:
            return next(i for i, s in enumerate(order) if fragment in s)
        finish = index("Finish a plan change")
        self.assertEqual(finish, index("Answer a round") + 1)
        self.assertLess(finish, index("Fix a blocked phase"))
        self.assertLess(finish, index("Post-PR fix"))
        self.assertIn("`04-plan.md` is `draft`", rows[finish][1])
        self.assertIn("Implementation started", rows[finish][1])
        feedback = rows[index("Feedback on an artifact")][1]
        self.assertNotIn("draft", feedback)

    def test_finish_plan_change_section(self):
        body = skill_md("iterate")
        section = body.split("## Finish a plan change", 1)[1].split("\n---\n", 1)[0]
        self.assertIn("Set `status: in-review`", section)
        self.assertIn("Never read `01-research-questions.md`", section)
        self.assertIn("If implementation started, set `status: draft` in `04-plan.md` before the first change", body)

    def test_open_round_means_in_review(self):
        body = skill_md("iterate")
        self.assertIn("- **Open round**: an artifact in `artifacts` with `status: in-review` and `openQuestions` > 0.", body)

    def test_blocked_row_requires_the_plan_gate(self):
        row = next(r for r in self.detection_rows() if "Fix a blocked phase" in r[2])
        self.assertIn("`04-plan.md` is `approved` (or the mode is oneshot)", row[1])
        self.assertIn("`04-plan.md` has no open round", row[1])
        section = skill_md("iterate").split("## Fix a blocked phase", 1)[1].split("### Steps", 1)[0]
        self.assertIn("Mode is not oneshot and `04-plan.md` is not `approved`", section)
        self.assertIn("`04-plan.md` has an open round", section)
        self.assertIn("`### Changes` of `## Phase N:`", section)
        self.assertNotIn("implementer report in `log.md`", section)

    def test_blocked_clean_tree_restarts_in_phase_mode(self):
        self.assertIn("in normal phase mode, not `Fix`", skill_md("iterate"))

    def test_blocked_phase_section(self):
        body = skill_md("iterate")
        section = body.split("## Fix a blocked phase", 1)[1].split("\n---\n", 1)[0]
        for needle in (
            "also when the working tree is dirty",
            "--grep='^Phase N:' origin/<main>..HEAD", "use `<main>..HEAD`",
            "**(a) No commit**", "**(b) A commit exists**",
            "body `Phase N: <name>`", "tick the phase's Phase Overview checkbox",
            "## Phase N — done — <commit short hash>",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, section)
        self.assertNotIn("Reason: fix:", body)

    def test_next_line_is_computed(self):
        body = skill_md("iterate")
        self.assertIn("### The `Next:` line (all sections)", body)
        # Only stop tables and the refusal example may name a fixed command after "Next:".
        # Dirty-tree refusals name the handling skill on purpose (a computed `next.command` could loop).
        computed = "\n".join(l for l in body.splitlines() if "uncommitted" not in l)
        fixed = re.findall(r"`Next: (/loom:[a-z-]+)", computed)
        self.assertLessEqual(set(fixed), {"/loom:setup", "/loom:start-task"}, fixed)

    def test_plan_change_log_heading_is_not_a_phase_entry(self):
        log = "## Phase 1 — done — abc1234\nChecks: ok\n\n## Plan change — 2026-11-08\nDeviations: x\n"
        phases = ls.parse_log(log)
        self.assertEqual(list(phases), [1])
        self.assertEqual(phases[1]["status"], "done")

    def test_fix_log_entry_keeps_the_phase_done(self):
        log = (
            "## Phase 1 — done — abc1234\nChecks: ok\n\n"
            "## Phase 1 — done — def5678\nFix: handle empty input\nReviewer: pass\n"
        )
        self.assertEqual(ls.parse_log(log)[1], {"status": "done", "commit": "def5678", "reason": None})


class TemplateTest(unittest.TestCase):
    def test_artifact_skills_have_a_template(self):
        for name in ARTIFACT_SKILL.values():
            with self.subTest(skill=name):
                self.assertTrue(os.path.isfile(os.path.join(SKILLS_DIR, name, "references", "template.md")))

    def test_only_artifact_skills_have_a_template(self):
        for name in skill_dirs():
            if name in ARTIFACT_SKILL.values():
                continue
            with self.subTest(skill=name):
                self.assertFalse(os.path.exists(os.path.join(SKILLS_DIR, name, "references", "template.md")))

    def test_headings_match_spec_13_2(self):
        blocks = spec_artifact_blocks()
        for artifact, name in ARTIFACT_SKILL.items():
            with self.subTest(artifact=artifact):
                body = ls.split_frontmatter(template(name))[1]
                self.assertEqual(h2_headings(body.splitlines()), spec_h2_headings(blocks[artifact]))

    def test_round_heading_forms(self):
        design = ls.split_frontmatter(template("design"))[1]
        plan = ls.split_frontmatter(template("plan"))[1]
        self.assertRegex(design, r"(?m)^## Open Questions — Round 1 of ~\S+$")
        self.assertRegex(plan, r"(?m)^## Open Questions — Round 1$")

    def test_plan_phase_subsections_match_spec(self):
        block = spec_artifact_blocks()["04-plan.md"]
        expected = [l.strip() for l in block if l.strip().startswith("### ")]
        self.assertEqual(expected, ["### Goal", "### Changes", "### Verification"])
        body = ls.split_frontmatter(template("plan"))[1]
        phases = re.split(r"(?m)^## Phase \d+: ", body)[1:]
        self.assertGreaterEqual(len(phases), 1)
        for index, phase in enumerate(phases, 1):
            with self.subTest(phase=index):
                self.assertEqual(re.findall(r"(?m)^### .+$", phase), expected)
                self.assertRegex(phase, r"(?m)^- \[ \] Automated: ")
        self.assertRegex(phases[0], r"(?m)^- \[ \] Manual: ")

    def test_resolved_decisions_table_header(self):
        for artifact in ("03-design.md", "04-plan.md"):
            block = "\n".join(spec_artifact_blocks()[artifact])
            self.assertIn(RESOLVED_TABLE_HEADER, block)
            with self.subTest(artifact=artifact):
                section = ls.section_lines(ls.split_frontmatter(template(ARTIFACT_SKILL[artifact]))[1], "resolved decisions")
                rows = [l for l in section if l.startswith("|")]
                self.assertEqual(rows[0], RESOLVED_TABLE_HEADER)
                self.assertEqual(len(rows), 2, "Resolved Decisions starts empty (header and separator only)")

    def test_frontmatter_keys_match_spec_13_1(self):
        keys = spec_frontmatter_keys()
        for artifact, name in ARTIFACT_SKILL.items():
            with self.subTest(artifact=artifact):
                fm = ls.split_frontmatter(template(name))[0]
                expected = keys if name == "research" else [k for k in keys if k != "git_commit"]
                self.assertEqual(list(fm), expected)
                self.assertEqual(fm["phase"], name)
                self.assertEqual(fm["status"], "draft")
                self.assertIsInstance(fm["based_on"], list)

    def test_templates_have_no_unclosed_fence(self):
        for name in ARTIFACT_SKILL.values():
            with self.subTest(skill=name):
                self.assertFalse(ls.has_unclosed_fence(ls.split_frontmatter(template(name))[1]))


class LoomStateRoundTripTest(unittest.TestCase):
    """Templates (and samples filled from them) parse in loom-state as intended."""

    def body(self, name: str) -> str:
        return ls.split_frontmatter(template(name))[1]

    def test_design_template_questions_are_counted(self):
        body = self.body("design")
        self.assertEqual(ls.count_open_questions(body), 2)
        self.assertEqual(ls.count_accepted_by_default(body), 0)

    def test_plan_template_questions_are_counted(self):
        body = self.body("plan")
        self.assertEqual(ls.count_open_questions(body), 1)
        self.assertEqual(ls.count_accepted_by_default(body), 0)

    def test_other_templates_have_no_open_questions(self):
        for name in ("research-questions", "research"):
            with self.subTest(skill=name):
                self.assertEqual(ls.count_open_questions(self.body(name)), 0)
                self.assertIsNone(ls.section_lines(self.body(name), "open questions"))

    def test_answered_round_sample(self):
        """Answer Q1 normally and Q2 at the round cap: no open questions, one marker."""
        body = self.body("design")
        rounds = re.compile(r"(?ms)^## Open Questions — Round 1 of ~\S+\n.*?(?=^## Resolved Decisions)")
        body = rounds.sub("## Open Questions\n\nNone.\n\n", body)
        body = body.replace(
            RESOLVED_TABLE_HEADER + "\n|---|---|---|---|---|---|\n",
            RESOLVED_TABLE_HEADER + "\n|---|---|---|---|---|---|\n"
            "| Q1 | Storage? | SQLite | Already a dependency | 1 | yes |\n"
            "| Q2 | Retries? | The HTTP client — accepted by default — revisit if needed | All calls pass through it | 5 | no |\n",
        )
        self.assertEqual(ls.count_open_questions(body), 0)
        self.assertEqual(ls.count_accepted_by_default(body), 1)

    def test_next_round_sample(self):
        body = self.body("design").replace("Round 1 of", "Round 2 of").replace("**Q1.", "**Q3.")
        self.assertEqual(ls.count_open_questions(body), 2)

    def test_plan_phase_overview_parses(self):
        body = self.body("plan")
        overview = ls.parse_phase_overview(body)
        phases = re.findall(r"(?m)^## Phase (\d+): ", body)
        self.assertEqual(overview, [(int(n), False) for n in phases])
        progress, warnings = ls.implementation_progress("quick", body, None)
        self.assertEqual(warnings, [])
        self.assertEqual(progress["total"], len(phases))
        self.assertEqual(progress["done"], 0)

    def test_plan_verification_checkboxes_are_not_phases(self):
        body = self.body("plan").replace("- [ ] Automated:", "- [x] Automated:")
        self.assertEqual(len(ls.parse_phase_overview(body)), 2)
        ticked = body.replace("- [ ] 1.", "- [x] 1.", 1)
        self.assertEqual(ls.parse_phase_overview(ticked)[0], (1, True))

    def test_frontmatter_parses_in_loom_state(self):
        for artifact, name in ARTIFACT_SKILL.items():
            with self.subTest(artifact=artifact):
                fm = ls.parse_frontmatter(template(name))
                self.assertEqual(fm.get("status"), "draft")



def reference(skill: str, name: str) -> str:
    return read(os.path.join(SKILLS_DIR, skill, "references", name))


def shared(name: str) -> str:
    return read(os.path.join(SKILLS_DIR, "_shared", name))


def spec_markdown_block(start: str, end: str) -> List[str]:
    section = spec_section(start, end)
    return re.search(r"```markdown\n(.*?)\n```", section, re.DOTALL).group(1).splitlines()


def strip_comments(text: str) -> str:
    """Drop HTML guidance comments, as the skills do before they write the file."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def section(body: str, start: str) -> str:
    return body.split(start, 1)[1].split("\n## ", 1)[0]


class DocsTemplateTest(unittest.TestCase):
    """describe-pr templates match §13.4, §13.5, and §13.6."""

    def test_summary_template_matches_13_4(self):
        block = spec_markdown_block("### 13.4 Task summary", "### 13.5 ADR")
        text = reference("describe-pr", "summary-template.md")
        lines = strip_comments(text).splitlines()
        self.assertEqual(h2_headings(lines), spec_h2_headings(block))
        h1 = [l for l in lines if l.startswith("# ")]
        self.assertRegex(block[0], r"^# #\d+ \S")
        self.assertEqual(len(h1), 1)
        self.assertRegex(h1[0], r"^# #<n> \S")
        self.assertIn("commit subject", text)  # hashes change on rebase and squash merge

    def test_adr_template_matches_13_5(self):
        block = spec_markdown_block("### 13.5 ADR", "### 13.6 PR body")
        status_re = r"^Status: Accepted · Task: #\S+ · Date: \S+$"
        self.assertRegex(block[0], r"^# NNNN\. \S")
        self.assertRegex(block[1], status_re)
        lines = [l for l in strip_comments(reference("describe-pr", "adr-template.md")).splitlines() if l.strip()]
        self.assertRegex(lines[0], r"^# NNNN\. \S")
        self.assertRegex(lines[1], status_re)
        self.assertEqual(h2_headings(lines), spec_h2_headings(block))

    def test_pr_template_matches_13_6(self):
        block = spec_markdown_block("### 13.6 PR body", "## 14. Writing Style")
        text = reference("describe-pr", "pr-template.md")
        lines = [l for l in strip_comments(text).splitlines() if l.strip()]
        self.assertRegex(block[0], r"^Closes #\d+$")
        self.assertEqual(lines[0], "Closes #<n>")
        self.assertEqual(h2_headings(lines), spec_h2_headings(block))
        details = [l for l in block if l.startswith("<details>") or l.startswith("</details>")]
        self.assertEqual(details, ["<details><summary>Implementation plan</summary>", "</details>"])
        for line in details:
            with self.subTest(line=line):
                self.assertIn(line, lines)
        self.assertLess(lines.index(details[0]), lines.index(details[1]))

    def test_pr_size_limit_and_oneshot_rules(self):
        spec = spec_section("### 13.6 PR body", "## 14. Writing Style")
        self.assertIn("60,000 characters", spec)
        self.assertIn("oneshot PRs contain only `Closes`, Why, and Verification", spec)
        template = reference("describe-pr", "pr-template.md")
        body = skill_md("describe-pr")
        for text in (template, body):
            self.assertIn("60,000", text)
            self.assertIn("Phase Overview", text)
        self.assertIn("oneshot: only `Closes #<n>`, Why, and Verification", body)
        oneshot = template.rsplit("<!--", 1)[1]
        self.assertIn("the `Closes #<n>` line, the Why section, and the Verification section", oneshot)
        self.assertIn("No Special things to note, no Change outline, no Decisions, and no plan", oneshot)

    # The PR layout (§13.6, §23.1 v1.1): section names in order, as the template writes them.
    PR_SECTIONS = ["Why", "Special things to note", "Change outline", "Verification", "Decisions"]

    def test_pr_sections_in_order(self):
        block = spec_markdown_block("### 13.6 PR body", "## 14. Writing Style")
        self.assertEqual(spec_h2_headings(block), self.PR_SECTIONS)
        lines = [l for l in strip_comments(reference("describe-pr", "pr-template.md")).splitlines() if l.strip()]
        self.assertEqual(h2_headings(lines), self.PR_SECTIONS)
        self.assertEqual(lines[:2], ["Closes #<n>", "## Why"])
        self.assertEqual(lines[-2:], ["<details><summary>Implementation plan</summary>", "</details>"])
        body = skill_md("describe-pr")
        self.assertIn("quick and full, in this order: `Closes #<n>`, Why, Special things to note, Change outline, "
                      "Verification, Decisions, then the body of `04-plan.md`", body)
        self.assertIn("| PR body | short: `Closes`, Why, Verification | full: `Closes`, Why, Special things to note, "
                      "Change outline, Verification, Decisions, with the plan attached |", body)

    def test_no_old_pr_sections(self):
        template = reference("describe-pr", "pr-template.md")
        spec = spec_section("### 13.6 PR body", "## 14. Writing Style")
        for text in (template, strip_comments(template), spec):
            for old in ("## Summary", "## Changes"):
                with self.subTest(old=old):
                    self.assertNotRegex(text, r"(?m)^%s\b" % re.escape(old))
        for name, text in (("template", template), ("spec", spec), ("describe-pr", skill_md("describe-pr")),
                           ("pr-update", shared("pr-update.md"))):
            for old in ("Summary,", ", Summary", "Changes,", "the Summary section", "Summary, Changes"):
                with self.subTest(file=name, old=old):
                    self.assertNotIn(old, text)

    def test_why_is_one_sentence(self):
        spec = spec_section("### 13.6 PR body", "## 14. Writing Style")
        self.assertIn("## Why                       ← exactly one sentence", spec)
        self.assertIn("on one line, not a list of what changed.", spec)
        why = section(reference("describe-pr", "pr-template.md"), "## Why")
        self.assertIn("Exactly one sentence of at most 25 words, on one line", why)
        self.assertIn("Not a list of what changed", why)
        self.assertIn("**Why** is exactly one sentence of at most 25 words", skill_md("describe-pr"))
        self.assertIn("one sentence of at most 25 words (§14.1 rule 3)", spec)

    def test_special_things_has_1_to_3_items_or_none(self):
        spec = spec_section("### 13.6 PR body", "## 14. Writing Style")
        self.assertIn("## Special things to note    ← 1–3 items, or the single line None.", spec)
        self.assertIn("If nothing qualifies, the section is the single line None. (no filler, §14.1 rule 6)", spec)
        special = section(reference("describe-pr", "pr-template.md"), "## Special things to note")
        body = skill_md("describe-pr")
        for text in (special, body):
            with self.subTest(text=text[:40]):
                self.assertIn("1-3 list items", text)
                self.assertIn("most important first", text.lower())
                self.assertIn("the single line None. (", text)
                self.assertIn("no backticks", text)
                self.assertNotIn("`None.`", text)  # models copy the backticks
                self.assertIn("cannot see quickly in the diff", text)
        for candidate in ("log.md", "a risk", "a non-obvious decision", "a migration or a manual step", "a known limit"):
            with self.subTest(candidate=candidate):
                self.assertIn(candidate, special)
        self.assertIn("never add filler", body)
        self.assertIn("rule 6", spec)
        self.assertIn("### 6. No introductions, recaps, or filler", shared("writing-style.md"))

    def test_change_outline_is_phase_lines_then_tree_or_interface_diff(self):
        spec = spec_section("### 13.6 PR body", "## 14. Writing Style")
        outline = section(reference("describe-pr", "pr-template.md"), "## Change outline")
        body = skill_md("describe-pr")
        for text in (spec, outline, body):
            with self.subTest(text=text[:40]):
                self.assertIn("`1. <phase name> — <commit subject>`", text)
                self.assertIn("file tree", text)
                self.assertRegex(text, r"interface `diff` block")
                self.assertRegex(text, r"(signatures and public API|signatures/public API)")
                self.assertRegex(text, r"[Oo]mit(ted)? unchanged parts|Unchanged parts are omitted")
        self.assertIn("changed files only", outline)
        self.assertIn("`visual-conventions.md`", outline)
        self.assertIn("(§13.3)", spec)
        # The summary template keeps its own Implementation format; both name the phases the same way.
        self.assertIn("`1. <phase name> — <commit subject>`", reference("describe-pr", "summary-template.md"))

    def test_pr_update_names_the_new_sections(self):
        text = shared("pr-update.md")
        self.assertIn("(Why, Special things to note, Change outline, Verification, Decisions, or the attached plan)", text)
        for needle in ("Why stays one sentence", "1-3 list items, or the single line None. (no backticks)",
                       "one line per implementation phase, then a file tree or an interface `diff` block",
                       "A body in the layout before loom v1.1 (`## Summary` and `## Changes`",
                       "is rewritten into this layout", "A phase line names the phase's own commit subject",
                       "Fix commits get no phase line"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_known_pr_with_failed_gh_stops(self):
        body = skill_md("describe-pr")
        self.assertIn("| `task.pr` is set and `pr` is `null` (`gh` failed) | `PR #<task.pr> state unknown (gh: <the gh warning>)` |", body)
        self.assertIn("While `task.pr` is not set, other `gh` warnings", body)
        self.assertIn("With `task.pr` set, a failed `gh` stops it (the row above)", body)
        self.assertLess(body.index("`PR #<task.pr> state unknown"), body.index("While `task.pr` is not set"))
        spec = spec_section("### 9.10 `describe-pr`", "### 9.11")
        self.assertIn("So does a failed `gh` when the ticket already has `pr:` (`PR #<n> state unknown`)", spec)

    def test_roadmap_records_the_pr_layout_as_done(self):
        roadmap = spec_section("### 23.1 v1.1 (planned)", "### 23.2")
        planned, done = roadmap.split("Done in v1.1:", 1)
        self.assertNotIn("PR layout", planned)
        self.assertIn("**PR layout:**", done)
        self.assertIn("§13.6", done)

    def test_templates_have_no_unclosed_fence(self):
        for name in ("summary-template.md", "adr-template.md", "pr-template.md"):
            with self.subTest(template=name):
                self.assertFalse(ls.has_unclosed_fence(reference("describe-pr", name)))

    def test_issue_format(self):
        text = reference("backlog", "issue-format.md")
        for needle in ("## Title", "## Body", "## Labels", "## Context", "## Acceptance Criteria",
                       "Follow-up from #<n>", "gh issue create", "confirmation"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        spec_labels = spec_section("### 19.2 Issue labels", "### 19.3")
        for label in re.findall(r"^\| `(\w+:)` \|", spec_labels, re.MULTILINE):
            with self.subTest(label=label):
                self.assertIn("`%s`" % label, text)


class LogFormatTest(unittest.TestCase):
    """implement/references/log-format.md is consistent with loom-state's parser."""

    def text(self) -> str:
        return reference("implement", "log-format.md")

    def examples(self) -> List[str]:
        entries = self.text().split("## Grammar", 1)[0]
        return re.findall(r"```markdown\n(.*?)```", entries, re.DOTALL)

    def fill(self, block: str) -> str:
        return (block.replace("Phase N", "Phase 2").replace("<commit short hash>", "abc1234")
                .replace("<fix commit short hash>", "def5678"))

    def test_every_example_parses(self):
        examples = [self.fill(b) for b in self.examples()]
        self.assertEqual(len(examples), 5)
        parsed = [ls.parse_log(b) for b in examples]
        self.assertEqual(parsed[0], {2: {"status": "in-progress", "commit": None, "reason": None}})
        self.assertEqual(parsed[1], {2: {"status": "done", "commit": "abc1234", "reason": None}})
        self.assertEqual(parsed[2], {2: {"status": "done", "commit": "def5678", "reason": None}})
        self.assertEqual(parsed[3][2]["status"], "blocked")
        self.assertTrue(parsed[3][2]["reason"].startswith("<one line"))
        self.assertEqual(parsed[4], {}, "a plan change is not a phase entry")

    def test_whole_log_sequence(self):
        log = "\n".join(self.fill(b) for b in self.examples())
        progress, warnings = ls.implementation_progress("quick", "## Phase Overview\n- [ ] 1. a\n- [ ] 2. b\n", log)
        self.assertEqual(warnings, [])
        self.assertEqual(progress["blocked"]["phase"], 2, "the last entry of phase 2 is blocked")
        self.assertEqual(ls.parse_log(self.fill(self.examples()[0]) + "\n" + self.fill(self.examples()[1]))[2]["status"], "done")

    def test_grammar_statements_hold(self):
        cases = {
            "## Phase 3 - done - 1a2b3c4 extra": ("done", "1a2b3c4", None),
            "## Phase 3 – DONE – 1a2b3c4": ("done", "1a2b3c4", None),
            "## phase 3 — blocked — tests fail": ("blocked", None, "tests fail"),
            "## Phase 3 — blocked\n### Details\nReason: first\nReason: second": ("blocked", None, "first"),
            "## Phase 3 — in-progress — ignored": ("in-progress", None, None),
        }
        for log, (status, commit, reason) in cases.items():
            with self.subTest(log=log):
                self.assertEqual(ls.parse_log(log)[3], {"status": status, "commit": commit, "reason": reason})
        for log in ("### Phase 3 — done — abc", "# Phase 3 — done — abc", "  ## Phase 3 — done — abc",
                    "```\n## Phase 3 — done — abc\n```", "## Plan change — 2026-11-08"):
            with self.subTest(log=log):
                self.assertEqual(ls.parse_log(log), {})
        self.assertIsNone(ls.parse_log("## Phase 3 — blocked\n## Other\nReason: late")[3]["reason"])

    def test_documented_separator_and_statuses(self):
        text = self.text()
        for needle in ("`in-progress`, `done`, or `blocked`", "**Last entry wins.**", "**Append only.**",
                       "`Reason: <text>`", "`## Plan change — <date>`", "case-insensitive"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_spec_example_matches(self):
        block = spec_section("### 13.2 Working artifacts", "### 13.3 Visual conventions")
        example = block.split("**`log.md`**", 1)[1]
        example = re.search(r"```markdown\n(.*?)```", example, re.DOTALL).group(1)
        for line in ("## Phase 1 — done — d4e5f6", "## Phase 2 — blocked"):
            self.assertIn(line, example)
        for prefix in ("Checks:", "Reviewer:", "Deviations:"):
            with self.subTest(prefix=prefix):
                self.assertIn("\n" + prefix, self.text())

    def test_users_read_the_log_format(self):
        for name in ("implement", "iterate", "describe-pr"):
            with self.subTest(skill=name):
                self.assertRegex(skill_md(name), r"\$\{CLAUDE_(SKILL_DIR|PLUGIN_ROOT\}/skills/implement)\}?/references/log-format\.md")
        self.assertIn("skills/implement/references/log-format.md", shared("frontmatter.md"))


class GitFlowConsistencyTest(unittest.TestCase):
    """implement, iterate, and describe-pr share one commit and loop definition."""

    def test_commit_forms(self):
        flow = shared("git-flow.md")
        for needle in ("`<type>(<scope>): <summary> (#<n>)`", "`Phase N: <name>`", "`Phase 1: oneshot`",
                       "`docs(#<n>): record decisions and summary`", "`docs(#<n>): update task summary`",
                       "`Fix: <item>`", "git add -- <paths>", "--force-with-lease", "git remote get-url origin",
                       "git fetch origin <main>"):
            with self.subTest(needle=needle):
                self.assertIn(needle, flow)
        spec = spec_section("### 16.2 Commits", "### 16.3")
        self.assertIn("`docs(#42): record decisions and summary`", spec)

    def test_skills_use_the_same_forms(self):
        for name in ("implement", "iterate"):
            body = skill_md(name)
            with self.subTest(skill=name):
                self.assertIn("`<type>(<scope>): <summary of phase N> (#<n>)`", body)
                self.assertIn("`Phase N: <name>`", body)
                self.assertIn("`Phase 1: oneshot`", body)
                self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/_shared/implementation-loop.md", body)
                self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/_shared/git-flow.md", body)
        self.assertIn("Write `docs(#<n>): record decisions and summary` to `<task dir>/commit-msg.txt`", skill_md("describe-pr"))

    def test_commit_messages_go_through_a_file(self):
        for name in ("implement", "iterate", "describe-pr"):
            with self.subTest(skill=name):
                self.assertIn("git commit -F <task dir>/commit-msg.txt", skill_md(name))
        for snippet in ("git-flow.md", "pr-update.md"):
            with self.subTest(snippet=snippet):
                self.assertIn("git commit -F <task dir>/commit-msg.txt", shared(snippet))
        self.assertIn("Write every `'` of the text as `'\\''`", shared("git-flow.md"))

    def test_no_double_quoted_messages_or_titles(self):
        # Double quotes expand backticks and `$` from plan headings, and need a permission prompt.
        paths = glob.glob(os.path.join(SKILLS_DIR, "*", "SKILL.md")) + glob.glob(os.path.join(SKILLS_DIR, "_shared", "*.md"))
        paths += reference_files()
        for path in paths:
            text = read(path)
            for bad in ('git commit -m "', '--title "', '--subject "', "git commit -m '", '--label "', '-m "'):
                with self.subTest(file=os.path.relpath(path, ROOT), bad=bad):
                    self.assertNotIn(bad, text)

    def test_loop_rules(self):
        loop = shared("implementation-loop.md")
        for needle in ("`loom:implementer`", "`loom:implementation-reviewer`", "`implement.maxFixAttempts`",
                       "`hooks.maxCheckAttempts`", "**only** the `blocking` items", "Never commit while the checks fail.",
                       "## Phase N — blocked", "fix mode"):
            with self.subTest(needle=needle):
                self.assertIn(needle, loop)

    def test_reused_files_are_read_before_write(self):
        self.assertIn("**if `commit-msg.txt` exists, Read it first, then Write the new message.**", shared("git-flow.md"))
        for name in ("implement", "iterate", "describe-pr", "setup", "backlog", "start-task", "finish-task"):
            with self.subTest(skill=name):
                self.assertRegex(skill_md(name), r"Read it (first|before you Write it)|Read the file first|Read before Write")
        self.assertIn("pr-body.md` from `pr-template.md`. A re-run finds the file of the earlier run: Read it before you Write it",
                      skill_md("describe-pr"))
        self.assertIn("If the file exists (a re-run), Read it before you Write it", skill_md("finish-task"))
        self.assertEqual(skill_md("iterate").count("Read the file first") + skill_md("iterate").count("Read before Write"), 3)
        self.assertIn("Read the file first if it exists", shared("pr-update.md"))
        self.assertIn("Read it before you Write it", reference("backlog", "issue-format.md"))

    def test_gh_api_reads_always_ask(self):
        self.assertIn("always asks", shared("git-flow.md"))
        self.assertIn("The permission system still asks for it", skill_md("finish-task"))
        self.assertNotIn("may still ask", spec_section("### 16.4 What needs user confirmation", "### 16.5"))

    def test_stash_rule(self):
        flow = shared("git-flow.md")
        stash = flow.split("### Stash", 1)[1].split("### Discard", 1)[0]
        for needle in ("git check-ignore -q <task dir>", "Exit status 0", "`git stash push --include-untracked -m '<message>'`",
                       "Exit status 1", "-- . ':(exclude)<task dir>'", "Check the exit status of `git stash`",
                       "git stash pop"):
            with self.subTest(needle=needle):
                self.assertIn(needle, stash)
        self.assertIn("cannot be recovered", flow.split("### Discard", 1)[1])
        for name in ("implement", "iterate"):
            with self.subTest(skill=name):
                self.assertIn('"Stash and discard" in `git-flow.md`', skill_md(name))
                self.assertNotIn("git stash push", skill_md(name).replace("`git stash push --include-untracked`", ""))

    def test_dirty_tree_refusals_never_loop(self):
        # A stop because of uncommitted changes must name the skill that handles them, not `next.command`
        # (which can route back to the refusing skill).
        paths = glob.glob(os.path.join(SKILLS_DIR, "*", "SKILL.md")) + glob.glob(os.path.join(SKILLS_DIR, "_shared", "*.md"))
        found = 0
        for path in paths:
            for line in read(path).splitlines():
                if "uncommitted" in line and ("Result:" in line or line.startswith("| `workingTree`")):
                    found += 1
                    with self.subTest(file=os.path.relpath(path, ROOT), line=line[:90]):
                        self.assertNotIn("from `next.command`", line)
                        self.assertRegex(line, r"Next:|`/loom:")
        self.assertGreaterEqual(found, 6)

    def test_docs_only_dirty_tree_is_handled_by_docs_writers(self):
        self.assertIn("is an interrupted earlier run of these steps", shared("pr-update.md"))
        self.assertIn("| `workingTree` is `dirty` and `workingTreeDocsOnly` is `true` | The docs changes are an interrupted docs refresh. Run the shared `pr-update.md`", skill_md("finish-task"))
        iterate = skill_md("iterate")
        for section in ("## Post-PR fix", "## Rebase"):
            with self.subTest(section=section):
                self.assertIn("workingTreeDocsOnly", iterate.split(section, 1)[1].split("\n---\n", 1)[0])

    def test_no_shell_variables_outside_plugin_paths(self):
        # Live (§24.2): a `${...}` variable in a Bash command needs a permission prompt; Read does
        # not substitute variables in snippets. Allowed: plugin paths, the injection line, frontmatter.
        allowed = re.compile(
            r"\$\{CLAUDE_PLUGIN_ROOT\}/skills/|\$\{CLAUDE_SKILL_DIR\}/references/|\$\{CLAUDE_PLUGIN_ROOT\}`$"
        )
        for name in skill_dirs():
            body = split_frontmatter(skill_md(name))[1]
            for line in body.splitlines():
                if line.startswith("!`") or "${" not in line:
                    continue
                rest = allowed.sub("", line)
                with self.subTest(skill=name, line=line):
                    self.assertNotIn("${", rest)
        for path in glob.glob(os.path.join(SKILLS_DIR, "_shared", "*.md")):
            with self.subTest(snippet=os.path.basename(path)):
                self.assertNotIn("${", read(path))


class ImplementTest(unittest.TestCase):
    def body(self) -> str:
        return split_frontmatter(skill_md("implement"))[1]

    def test_frontmatter(self):
        fm = split_frontmatter(skill_md("implement"))[0]
        self.assertEqual(fm.get("model"), "inherit")
        self.assertNotIn("effort", fm)
        self.assertNotIn("context", fm)
        self.assertIn(STATE_INJECTION_PR, skill_md("implement"))

    def test_resume_flow(self):
        body = self.body()
        resume = body.split("## 2. Resume flow", 1)[1].split("## 3.", 1)[0]
        for needle in ("**resume**", "**stash**", "**discard**", "cannot be recovered", "Confirm them before you run anything",
                       "git check-ignore -q <task dir>", "Check the exit status", "Never touch `<task dir>`",
                       "implementation.inProgress", "--grep='^Phase N:' <base>..HEAD", "do not implement phase N again"):
            with self.subTest(needle=needle):
                self.assertIn(needle, resume)

    def test_blocked_phase_goes_to_iterate(self):
        body = self.body()
        pre = body.split("## 1. Check preconditions", 1)[1].split("## 2.", 1)[0]
        self.assertIn("| `implementation.blocked` is set | `implementation phase <k> is blocked: <reason>` | `/loom:iterate <fix>` |", pre)
        self.assertIn("A blocked implementation phase is never resumed here", pre)

    def test_all_done_stops_also_with_a_dirty_tree(self):
        pre = self.body().split("## 1. Check preconditions", 1)[1].split("## 2.", 1)[0]
        self.assertIn("`implementation.done` equals `implementation.total` (clean or dirty working tree)", pre)

    def test_open_pr_is_updated_after_the_last_phase(self):
        body = self.body()
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/_shared/pr-update.md", body)
        self.assertIn("If `pr.state` is `OPEN`, first run the shared `pr-update.md`", body)

    def test_plan_gate_and_oneshot(self):
        body = self.body()
        self.assertIn("`04-plan.md` is missing or not `approved`", body)
        self.assertIn("the reviewer compares the diff with the ticket", body)
        self.assertIn("`<task dir>/00-ticket.md`", body)

    def test_per_phase_steps(self):
        body = self.body()
        phase = body.split("## 4. Run one implementation phase", 1)[1].split("## 5.", 1)[0]
        order = ["`## Phase N — in-progress`", "implementation-loop.md", "## Phase N — blocked", "git add -- <paths>",
                 "`- [x] N.`", "`done` entry"]
        positions = [phase.index(n) for n in order]
        self.assertEqual(positions, sorted(positions))
        for needle in ("`implement.maxFixAttempts`", "`hooks.maxCheckAttempts`", "you run `checks.check` once more",
                       "Leave `Manual:` checkboxes unchecked", "Do not commit."):
            with self.subTest(needle=needle):
                self.assertIn(needle, phase)

    def test_auto_advance_and_overrides(self):
        body = self.body()
        for needle in ("`implement.autoAdvance`", "do all phases and stop at the end", "stop after every phase",
                       "`Manual:` line", "fresh `loom:implementer`", "A blocked phase always stops the run"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_last_phase_next_comes_from_loom_state(self):
        body = self.body()
        final = body.split("## 6. Final message", 1)[1]
        self.assertIn("`/clear, then /loom:describe-pr`", final)
        self.assertIn("Run `loom-state --json` after your last write", final)


class DescribePrTest(unittest.TestCase):
    def body(self) -> str:
        return split_frontmatter(skill_md("describe-pr"))[1]

    def test_reads_templates_and_issue_format_first(self):
        before = self.body().split("## 1. Check preconditions", 1)[0]
        for path in ("${CLAUDE_SKILL_DIR}/references/summary-template.md", "${CLAUDE_SKILL_DIR}/references/adr-template.md",
                     "${CLAUDE_SKILL_DIR}/references/pr-template.md",
                     "${CLAUDE_PLUGIN_ROOT}/skills/backlog/references/issue-format.md"):
            with self.subTest(path=path):
                self.assertIn(path, before)

    def test_steps_in_order(self):
        body = self.body()
        steps = ["## 3. Task summary", "## 4. ADRs", "## 5. Architecture overview", "## 6. Docs commit",
                 "## 7. Rebase", "## 8. Pull request", "## 9. Follow-up issues"]
        positions = [body.index(s) for s in steps]
        self.assertEqual(positions, sorted(positions))

    def test_key_rules(self):
        body = self.body()
        for needle in ("`<docs>/tasks/<n>-<slug>.md`", "`<docs>/architecture/decisions/`", "`ADR?` = `yes`",
                       "plus 1, with four digits", "`0001`", "`<docs>/architecture/overview.md`",
                       "only if `<docs>/architecture/overview.md` changed", "git fetch origin <main>",
                       "run `checks.check` again", "`git push -u origin <branch>`", "gh pr create --base <main>",
                       "`<type>(<scope>): <summary of the task> (#<n>)`", "`pr: <number>`", "Ask for one confirmation",
                       "Create only confirmed issues"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_docs_only_dirty_tree_is_a_partial_run(self):
        body = self.body()
        self.assertIn("| `workingTree` is `dirty` and `workingTreeDocsOnly` is `false` (code changes) |", body)
        self.assertIn("is an earlier partial run of this skill", body)
        self.assertIn("--title '<title>'", body)

    def test_mode_table_matches_5_4(self):
        spec = spec_section("### 5.4 Mode differences", "## 6. End-to-End Lifecycle")
        self.assertIn("| Docs commit in describe-pr | only if `overview.md` changed | ✓ | ✓ |", spec)
        self.assertIn("| PR description | short | full | full |", spec)
        self.assertIn("| PR body | short: `Closes`, Why, Verification |", self.body())
        body = self.body()
        self.assertIn("| Docs commit | only if `overview.md` changed | if any docs file changed |", body)
        self.assertIn("| Task summary `<docs>/tasks/<n>-<slug>.md` | no | yes |", body)


class FinishTaskTest(unittest.TestCase):
    def body(self) -> str:
        return split_frontmatter(skill_md("finish-task"))[1]

    def test_frontmatter(self):
        fm = split_frontmatter(skill_md("finish-task"))[0]
        self.assertEqual((fm.get("model"), fm.get("effort")), ("haiku", "low"))
        self.assertIn(STATE_INJECTION_PR, skill_md("finish-task"))

    def test_commands(self):
        body = self.body()
        for needle in ("gh pr checks --required --watch", "600000 ms", "Pending is not failed", "no required checks",
                       "`gh pr merge --squash --delete-branch --subject '<title>' --match-head-commit <head sha>`",
                       "gh pr view --json headRefOid,title", "Give no PR number", "git fetch --prune",
                       "refs/heads/<branch>", "git branch -D <branch>", "<workDir>/_archive", "Ask for confirmation.",
                       "`chore/<n>-loom-setup`", "`Set up loom`", "gh api repos/{owner}/{repo}/rules/branches/<main>",
                       "read-only and needs no confirmation", "`~DEFAULT_BRANCH`", "no bypass actors",
                       "gh api --method POST repos/{owner}/{repo}/rulesets",
                       '"required_approving_review_count": 0', '"context": "check"', "non_fast_forward", "deletion"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)
        self.assertNotRegex(body, r"gh pr merge \d")

    def test_stops_after_the_merge_resume_with_the_issue(self):
        body = self.body()
        after = body.split("## 4. Merge", 1)[1].split("## Resume on the main branch", 1)[0]
        self.assertIn("**From here on, every stop ends with `Next: /loom:finish-task #<n>`.**", after)
        for stop in re.findall(r"stop[^\n]*`Result:[^\n]*", after.split("## 5.", 1)[1]):
            with self.subTest(stop=stop):
                self.assertIn("Next: /loom:finish-task #<n>", stop)
        self.assertIn("resumes with /loom:finish-task #<n>", body.split("## 2.", 1)[0])

    def test_idempotent_steps(self):
        body = self.body()
        for needle in ("`pr.state` is `MERGED` | The merge already happened.", "offer the stash of `git-flow.md`",
                       "the archive is done. Skip this step", "a ruleset already protects `<main>`: skip this step",
                       "## Resume on the main branch"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_ruleset_json_is_valid(self):
        import json
        block = re.search(r"```json\n(.*?)```", self.body(), re.DOTALL).group(1)
        data = json.loads(re.sub(r"^ {3}", "", block, flags=re.MULTILINE))
        self.assertEqual(data["conditions"]["ref_name"]["include"], ["<ref>"])
        self.assertEqual(data["bypass_actors"], [])
        self.assertEqual({r["type"] for r in data["rules"]},
                         {"deletion", "non_fast_forward", "pull_request", "required_status_checks"})


class NextTest(unittest.TestCase):
    def raw(self) -> str:
        return skill_md("next")

    def body(self) -> str:
        return split_frontmatter(self.raw())[1]

    def test_frontmatter_runs_phases_on_the_session_model(self):
        fm = split_frontmatter(self.raw())[0]
        self.assertEqual(fm.get("model"), "inherit")
        self.assertNotIn("effort", fm)
        self.assertNotIn("context", fm)

    def test_permissions_are_the_union_of_the_phase_skills(self):
        own = set(skill_rules("next"))
        self.assertIn('Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json --pr)', own)
        for name in NEXT_RUNS:
            for rule in skill_rules(name):
                if rule.startswith('Bash("${CLAUDE_PLUGIN_ROOT}"'):
                    continue  # next replaces the phase's injection with its own
                with self.subTest(skill=name, rule=rule):
                    self.assertIn(rule, own)

    def test_substituted_variables_appear_only_where_intended(self):
        # Claude Code substitutes these in next's own body, so the prompt must not name them literally.
        body = self.body()
        self.assertNotIn("${CLAUDE_SKILL_DIR}", body)
        self.assertEqual(body.count("$ARGUMENTS"), 1)
        self.assertIn("Arguments: $ARGUMENTS", body)
        for line in body.splitlines():
            if "${CLAUDE_PLUGIN_ROOT}" not in line:
                continue
            with self.subTest(line=line):
                ok = (line.startswith("!`") or line.startswith("Plugin root")
                      or all(m.startswith("/skills/") for m in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}(\S*)", line)))
                self.assertTrue(ok, line)

    def test_placeholders_are_named(self):
        body = self.body()
        for needle in ("Do not run its state injection", "`CLAUDE_PLUGIN_ROOT` in dollar-brace form",
                       "`CLAUDE_SKILL_DIR` in dollar-brace form", "`<plugin root>/skills/<phase>`",
                       "`ARGUMENTS` after a dollar sign", "Ignore its frontmatter", "session's model and effort",
                       "`/loom:design` or `/loom:plan` directly"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_every_next_command_is_routed(self):
        commands = set(re.findall(r'"(/loom:[a-z-]+)', read(os.path.join(ROOT, "bin", "loom-state"))))
        self.assertTrue(commands)
        table = self.body().split("## 3. Run or name the next command", 1)[1]
        for command in commands:
            with self.subTest(command=command):
                self.assertIn("`%s" % command, table)
        run_row = next(l for l in table.splitlines() if "**Run**" in l)
        for phase in NEXT_RUNS:
            with self.subTest(phase=phase):
                self.assertIn("`/loom:%s`" % phase, run_row)
        for named in ("/loom:iterate", "/loom:describe-pr", "/loom:finish-task"):
            with self.subTest(named=named):
                self.assertNotIn(named, run_row)

    def test_summary_and_research_warnings(self):
        body = self.body()
        for needle in ("3-5 lines", "Warning: research not reviewed", "Warning: research is stale", "Offer a rerun"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_spec_documents_the_fix(self):
        spec = spec_section("### 9.12 `next`", "## 10. Subagents")
        for needle in ("does not run the phase file's", "union", "`model: inherit`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, spec)



class SetupSkillTest(unittest.TestCase):
    """setup (§9.1): bootstrap order, confirmations, and the describe-pr handover."""

    def body(self) -> str:
        return split_frontmatter(skill_md("setup"))[1]

    def test_frontmatter(self):
        fm = split_frontmatter(skill_md("setup"))[0]
        self.assertEqual(fm.get("model"), "inherit")
        self.assertNotIn("effort", fm)
        self.assertIn(STATE_INJECTION, skill_md("setup"))
        self.assertEqual(skill_rules("setup"), [
            'Bash("${CLAUDE_PLUGIN_ROOT}"/bin/loom-state --json)', "Bash(loom-state --json)",
            "Read(/${CLAUDE_PLUGIN_ROOT}/skills/**)",
        ])

    def test_reads_every_template_before_any_question(self):
        before = self.body().split("## 1. Check preconditions", 1)[0]
        templates = os.path.join(SKILLS_DIR, "setup", "references", "templates")
        for path in reference_files():
            rel = os.path.relpath(path, os.path.join(SKILLS_DIR, "setup"))
            if not rel.startswith("references/") or os.path.basename(path) == ".gitkeep":
                continue
            with self.subTest(file=rel):
                self.assertIn("${CLAUDE_SKILL_DIR}/%s" % rel, before)
        self.assertTrue(os.path.isdir(templates))
        for shared_file in ("git-flow.md", "frontmatter.md", "writing-style.md", "final-answer.md"):
            with self.subTest(shared=shared_file):
                self.assertIn("${CLAUDE_PLUGIN_ROOT}/skills/_shared/%s" % shared_file, before)
        for path in ("${CLAUDE_PLUGIN_ROOT}/skills/start-task/references/ticket-template.md",
                     "${CLAUDE_PLUGIN_ROOT}/skills/implement/references/log-format.md"):
            with self.subTest(path=path):
                self.assertIn(path, before)

    def test_bootstrap_order(self):
        body = self.body()
        steps = ["## 3. Plan and confirm", "## 4. Bootstrap", "## 5. Issue", "## 6. Branch",
                 "## 7. Write the files", "## 8. Checks", "## 9. Task directory and commit", "## 10. Final message"]
        positions = [body.index(s) for s in steps]
        self.assertEqual(positions, sorted(positions))
        boot = section(body, "## 4. Bootstrap")
        order = ["Ignore the work directory", "git add -- .gitignore README.md", "git commit -F <drafts>/commit-msg.txt",
                 "git push -u origin <main>", "gh label create"]
        self.assertEqual([boot.index(n) for n in order], sorted(boot.index(n) for n in order))
        write = section(body, "## 7. Write the files")
        self.assertIn("`.claude/loom.json` first", write)

    def test_handover_matches_loom_state_and_finish_task(self):
        body = self.body()
        for needle in ("`chore/<n>-loom-setup`", "`<workDir>/<n>-loom-setup`", "--title 'Set up loom'",
                       "`mode: oneshot`", "`size: S`", "`chore(loom): set up loom (#<n>)`", "`Phase 1: oneshot`",
                       "## Phase 1 — done — <commit short hash>", "## Phase 1 — in-progress",
                       "git commit -F <task dir>/commit-msg.txt", "`/loom:describe-pr`",
                       "--label 'type:chore' --label 'size:S' --label 'mode:oneshot'"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)
        finish = skill_md("finish-task")
        self.assertIn("`<branch>` is `chore/<n>-loom-setup`, or the first `# ` heading of `00-ticket.md` is `Set up loom`", finish)
        self.assertTrue(ls.BRANCH_RE.match("chore/7-loom-setup"))
        self.assertIn("The title is `Set up loom`", skill_md("start-task"))

    def test_confirmations(self):
        plan = section(self.body(), "## 3. Plan and confirm")
        for needle in ("git push -u origin <main>", "gh label create", "gh issue create", "uv add --dev",
                       "`diff` block", "Never write a file the plan does not show", "ask for confirmation once"):
            with self.subTest(needle=needle):
                self.assertIn(needle, plan)

    def test_settings_are_merged_not_replaced(self):
        body = self.body()
        self.assertIn("### Merge settings.json", body)
        merge = body.split("### Merge settings.json", 1)[1].split("## 8.", 1)[0]
        for needle in ("Never replace the file and never remove a key", "`permissions.allow` and `permissions.ask`",
                       "`enabledPlugins[\"loom@loom\"]`", "`extraKnownMarketplaces.loom`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, merge)

    def test_checks_before_commit_and_no_commit_on_failure(self):
        checks = section(self.body(), "## 8. Checks")
        self.assertIn("Do not commit.", checks)
        self.assertIn("`checks.check`", checks)

    def test_unknown_stack_and_detection(self):
        body = self.body()
        for needle in ("investigate before you ask", "`pyproject.toml` and `uv.lock`", "`package.json` and a lock file",
                       "git symbolic-ref --short refs/remotes/origin/HEAD", "git symbolic-ref --short HEAD"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_resume_on_the_setup_branch(self):
        body = self.body()
        self.assertIn("[Resume on the setup branch](#resume-on-the-setup-branch)", body)
        resume = body.split("## Resume on the setup branch", 1)[1]
        for needle in ("--grep='^Phase 1: oneshot' origin/<main>..HEAD", "Never write a second `in-progress` entry",
                       "Write nothing.", "skip [Nothing to change](#nothing-to-change)",
                       "git diff --name-only origin/<main>...HEAD", "git fetch origin <main>", "also when they are identical to the templates"):
            with self.subTest(needle=needle):
                self.assertIn(needle, resume)
        self.assertIn("Only on `<main>`, never on the setup branch", section(body, "### Nothing to change").split("\n## ", 1)[0]
                      if "### Nothing to change" in body else "")

    def test_preconditions_find_branches_and_origin(self):
        pre = section(self.body(), "## 1. Check preconditions")
        order = ["`<current>` matches `chore/<k>-loom-setup`", "git branch --list 'chore/*-loom-setup'",
                 "git ls-remote --exit-code --heads origin <main>", "the working tree is dirty (see Values)"]
        self.assertEqual([pre.index(o) for o in order], sorted(pre.index(o) for o in order))
        self.assertIn("Next: push <main> yourself (git push -u origin <main>), then /loom:setup", pre)
        self.assertIn("Write nothing before this table is through.", pre)
        values = self.body().split("### Values", 1)[1].split("## 1.", 1)[0]
        for needle in ("gh repo view --json defaultBranchRef --jq .defaultBranchRef.name",
                       "git symbolic-ref --short refs/remotes/origin/HEAD", "ask the user", "git symbolic-ref --short HEAD",
                       "Read it first, then Write it", "Paths below `<workDir>` do not count"):
            with self.subTest(needle=needle):
                self.assertIn(needle, values)

    def test_main_is_updated_before_detection(self):
        body = self.body()
        start = body.split("### Start from `<main>`", 1)[1].split("## 2. Detect", 1)[0]
        self.assertLess(body.index("### Start from `<main>`"), body.index("## 2. Detect"))
        self.assertLess(body.index("## 1. Check preconditions"), body.index("### Start from `<main>`"))
        self.assertLess(start.index("git switch <main>"), start.index("git pull --ff-only origin <main>"))
        boot = section(body, "## 4. Bootstrap")
        self.assertNotIn("git switch <main>", boot)
        order = ["git branch -m <main>", "Ignore the work directory", "git push -u origin <main>"]
        self.assertEqual([boot.index(o) for o in order], sorted(boot.index(o) for o in order))

    def test_status_never_collapses_untracked_directories(self):
        body = self.body()
        for m in re.finditer(r"git status --porcelain[^`]*", body):
            with self.subTest(at=m.start()):
                self.assertIn("--untracked-files=all", m.group(0))
        self.assertGreaterEqual(body.count("git status --porcelain --untracked-files=all"), 4)

    def test_merged_setup_pr_goes_to_finish_task(self):
        body = self.body()
        self.assertEqual(body.count("gh pr list --head <that branch> --state merged --json number")
                         + body.count("gh pr list --head <branch> --state merged --json number"), 2)
        self.assertIn("`Next: /loom:finish-task #<n>`", body)
        resume = body.split("## Resume on the setup branch", 1)[1]
        self.assertIn("If `<task dir>/00-ticket.md` is missing, write it from the issue", resume)

    def test_in_progress_entry_comes_right_before_the_commit(self):
        step = section(self.body(), "## 9. Task directory and commit")
        order = ["git add -- <paths>", "Ask all questions now", "`## Phase 1 — in-progress`",
                 "run `git commit -F <task dir>/commit-msg.txt`", "## Phase 1 — done — <commit short hash>"]
        self.assertEqual([step.index(o) for o in order], sorted(step.index(o) for o in order))
        self.assertIn("not `/loom:next`", step)
        self.assertIn("git status --porcelain", step.split("Stage the setup commit", 1)[1])


class BacklogSkillTest(unittest.TestCase):
    """backlog (§9.2)."""

    def body(self) -> str:
        return split_frontmatter(skill_md("backlog"))[1]

    def test_frontmatter(self):
        fm = split_frontmatter(skill_md("backlog"))[0]
        self.assertEqual(fm.get("model"), "inherit")
        self.assertNotIn("effort", fm)
        self.assertIn(STATE_INJECTION, skill_md("backlog"))

    def test_reads_issue_format_and_context(self):
        body = self.body()
        self.assertIn("${CLAUDE_SKILL_DIR}/references/issue-format.md", body.split("## 1. Check preconditions", 1)[0])
        for needle in ("`<docs>/product/vision.md`", "gh issue list --state open", "Skeleton written by /loom:setup",
                       "| The state is empty |", "`Next: /loom:setup`", "new issues do not change it"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_issues_are_created_after_confirmation(self):
        create = self.body().split("## Create issues", 1)[1].split("\n## ", 1)[0]
        for needle in ("Show the full list", "Ask for confirmation", "After \"yes\"",
                       "gh issue create --title '<title>' --body-file <drafts>/", "`'\\''`", "Depends on #<k>"):
            with self.subTest(needle=needle):
                self.assertIn(needle, create)
        self.assertLess(create.index("Ask for confirmation"), create.index("gh issue create"))

    def test_drafts_live_in_the_ignored_work_directory(self):
        self.assertIn("`<drafts>` is `<workDir>/_drafts`", self.body())
        self.assertIn("Issue bodies always go to `<drafts>`, also with an active task.", self.body())
        self.assertIn("`<n>` is `task.number` and `<task dir>` is `task.dir`", self.body())
        self.assertIn("also when a task is active", reference("backlog", "issue-format.md"))
        self.assertIn("`<workDir>/_drafts/`", reference("backlog", "issue-format.md"))
        self.assertIsNone(re.match(r"^\d+-", "_drafts"), "loom-state matches task directories by <n>-")

    def test_writing_style_exception(self):
        self.assertIn("It does not apply to the discussion with the user or to `vision.md`", self.body())
        spec = spec_section("### 14.2 Where it applies", "## 15. Project Documentation Structure")
        self.assertIn("| `vision.md`, `backlog` discussion | No |", spec)

    def test_vision_never_commits_on_main(self):
        vision = self.body().split("## Fill the vision", 1)[1].split("\n## ", 1)[0]
        self.assertIn("docs(#<n>): update product vision", vision)
        self.assertIn("`workingTree` is `clean`", vision)
        self.assertIn("Do not write the file.", vision)
        self.assertIn("`docs(#<n>): update product vision`", shared("git-flow.md"))


class StartTaskSkillTest(unittest.TestCase):
    """start-task (§9.3, §5.2, §13.1)."""

    def body(self) -> str:
        return split_frontmatter(skill_md("start-task"))[1]

    def test_frontmatter_allows_the_slug_helper(self):
        fm = split_frontmatter(skill_md("start-task"))[0]
        self.assertEqual(fm.get("model"), "inherit")
        self.assertNotIn("effort", fm)
        self.assertIn("Bash(loom-state --slug *)", skill_rules("start-task"))
        self.assertTrue(any(rule_allows(r, "Bash", "loom-state --slug 'Add x'") for r in skill_rules("start-task")))

    def test_steps_in_order(self):
        body = self.body()
        steps = ["## 2. Free text", "## 3. Read the issue", "## 4. Existing task directory", "## 5. Mode",
                 "## 6. Branch type and slug", "## 7. Branch", "## 8. Write the ticket", "## 9. Final message"]
        positions = [body.index(s) for s in steps]
        self.assertEqual(positions, sorted(positions))

    def test_mode_precedence_matches_5_2(self):
        mode = section(self.body(), "## 5. Mode")
        order = ["A mode flag", "A `mode:*` label", "A `size:*` label"]
        self.assertEqual([mode.index(o) for o in order], sorted(mode.index(o) for o in order))
        self.assertIn("`S` → oneshot, `M` → quick, `L` → full", mode)
        spec = spec_section("### 5.2 Choosing a mode", "### 5.3 Changing the mode")
        self.assertIn("(`S` → oneshot, `M` → quick, `L` → full)", spec)

    def test_commands(self):
        body = self.body()
        for needle in ("gh issue view <n> --json title,body,labels,url", "loom-state --slug '<issue title>'",
                       "git switch <main>", "git pull", "git switch -c <branch>", "<workDir>/_archive/<n>-*",
                       "mv <workDir>/_archive/<dir> <workDir>/", "Offer the stash of `git-flow.md`",
                       "git rev-parse --verify --quiet refs/heads/<branch>", "Next: /clear, then /loom:next",
                       "never build it yourself", "The ticket has no `status` and no `updated`"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)
        self.assertLess(body.index("git switch <main>"), body.index("git switch -c <branch>"))

    def test_slug_rule_matches_the_spec(self):
        spec = spec_section("### 9.3 `start-task`", "### 9.4")
        self.assertIn("`loom-state --slug '<title>'`", spec)
        self.assertIn("at most 5 words / 40 characters", spec)
        self.assertEqual((ls.SLUG_MAX_WORDS, ls.SLUG_MAX_CHARS), (5, 40))
        interface = spec_section("### 8.2 Interface", "### 8.3 Rules")
        self.assertIn("--slug '<issue title>'", interface)

    def test_ticket_fields_match_13_1_and_frontmatter_md(self):
        fm = ls.parse_frontmatter(reference("start-task", "ticket-template.md"))
        self.assertEqual(list(fm), ["task", "phase", "mode", "size", "issue", "url"])
        self.assertEqual(fm["phase"], "ticket")
        documented = shared("frontmatter.md").split("## Ticket frontmatter", 1)[1].split("\n## ", 1)[0]
        for key in fm:
            with self.subTest(key=key):
                self.assertIn("| `%s` |" % key, documented)
        spec = spec_section("### 13.1 Frontmatter and gates", "### 13.2 Working artifacts")
        self.assertIn("The ticket has no `status`, `based_on`, `git_commit`, or `updated`.", spec)


if __name__ == "__main__":
    unittest.main()
