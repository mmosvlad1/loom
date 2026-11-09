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
STATE_SKILLS = M3_SKILLS | M4_SKILLS
# Skills that `next` runs by reading their SKILL.md (§9.12).
NEXT_RUNS = {"research-questions", "research", "design", "plan", "implement"}
# Skill directories that only hold reference files until a later milestone (M5: backlog/SKILL.md).
REFERENCE_ONLY_DIRS = {"backlog": ["references/issue-format.md"]}
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

    def test_skills_take_the_date_from_loom_state(self):
        for name in M3_SKILLS | {"implement", "describe-pr"}:
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
        paths += glob.glob(os.path.join(SKILLS_DIR, "*", "references", "*.md"))
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
        paths += glob.glob(os.path.join(SKILLS_DIR, "*", "references", "*.md"))
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
        self.assertIn("oneshot PRs contain only `Closes`, Summary, and Verification", spec)
        template = reference("describe-pr", "pr-template.md")
        body = skill_md("describe-pr")
        for text in (template, body):
            self.assertIn("60,000", text)
            self.assertIn("Phase Overview", text)
        self.assertIn("oneshot: only `Closes #<n>`, Summary, and Verification", body)

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
        paths += glob.glob(os.path.join(SKILLS_DIR, "*", "references", "*.md"))
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


if __name__ == "__main__":
    unittest.main()
