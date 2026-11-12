"""Tests for the markdown parsers in loom-state."""
from __future__ import annotations

import unittest

from loomtest import dedent, loom_state

ls = loom_state()


class FrontmatterTest(unittest.TestCase):
    def test_scalars_lists_and_comments(self):
        fm, body = ls.split_frontmatter(dedent("""
            ---
            task: 42-auth-flow
            phase: design            # ticket | research | design
            status: "in-review"
            based_on: [02-research.md, '01-research-questions.md']
            git_commit: a1b2c3d      # research only
            updated: 2026-11-08
            empty:
            ---
            # Body
        """))
        self.assertEqual(fm["task"], "42-auth-flow")
        self.assertEqual(fm["phase"], "design")
        self.assertEqual(fm["status"], "in-review")
        self.assertEqual(fm["based_on"], ["02-research.md", "01-research-questions.md"])
        self.assertEqual(fm["git_commit"], "a1b2c3d")
        self.assertEqual(fm["updated"], "2026-11-08")
        self.assertIsNone(fm["empty"])
        self.assertEqual(body, "# Body\n")

    def test_values_stay_strings(self):
        fm = ls.parse_frontmatter("---\nissue: 42\ngit_commit: 0123456\npr: 57\n---\n")
        self.assertEqual(fm["git_commit"], "0123456")  # no int conversion
        self.assertEqual(fm["issue"], "42")
        self.assertEqual(ls._to_int(fm["pr"]), 57)

    def test_hash_inside_quotes_is_kept(self):
        fm = ls.parse_frontmatter('---\nurl: "https://x/y#frag"\ntitle: a#b\n---\n')
        self.assertEqual(fm["url"], "https://x/y#frag")
        self.assertEqual(fm["title"], "a#b")

    def test_empty_inline_list(self):
        self.assertEqual(ls.parse_frontmatter("---\nbased_on: []\n---\n")["based_on"], [])

    def test_no_frontmatter(self):
        fm, body = ls.split_frontmatter("# Title\n---\n")
        self.assertEqual(fm, {})
        self.assertEqual(body, "# Title\n---\n")

    def test_unterminated_frontmatter(self):
        self.assertEqual(ls.parse_frontmatter("---\nstatus: draft\n"), {})

    def test_hash_number_is_a_value(self):
        fm = ls.parse_frontmatter("---\npr: #57\nissue: #42 # the issue\nnote: # a comment\n---\n")
        self.assertEqual((fm["pr"], fm["issue"], fm["note"]), ("#57", "#42", None))

    def test_to_int(self):
        for value, expected in (("57", 57), ("#57", 57), (" #57 ", 57), (57, 57), ("0", 0), ("²", None),
                                ("٥", None), ("5.7", None), ("# 57", None), ("abc", None), ("", None), (None, None),
                                (["57"], None)):
            with self.subTest(value=value):
                self.assertEqual(ls._to_int(value), expected)


class ArtifactStatusTest(unittest.TestCase):
    def test_known_statuses_are_normalized(self):
        for raw, status in (("draft", "draft"), ("Approved", "approved"), (" IN-REVIEW ", "in-review")):
            with self.subTest(raw=raw):
                self.assertEqual(ls.artifact_status("04-plan.md", raw), (status, []))

    def test_missing_status(self):
        self.assertEqual(ls.artifact_status("04-plan.md", None), (None, []))

    def test_unknown_status_is_in_review_with_a_warning(self):
        for raw in ("in review", "blocked", "", ["approved"]):
            with self.subTest(raw=raw):
                status, warnings = ls.artifact_status("03-design.md", raw)
                self.assertEqual(status, "in-review")
                self.assertEqual(len(warnings), 1)
                self.assertIn("03-design.md has an unknown status", warnings[0])
                self.assertIn("allowed: draft, in-review, approved", warnings[0])


class OpenQuestionsTest(unittest.TestCase):
    def test_counts_latest_round_only(self):
        body = dedent("""
            ## Open Questions — Round 1 of ~3

            **Q1. Old question?**
            - a) x

            ## Resolved Decisions
            | 1 | Old question | a | because | 1 | no |

            ## Open Questions — Round 2 of ~3

            **Q2. Where is state stored?**
            - a) SQLite — recommended: already a dependency
            - b) Redis

            **Q3. Which protocol?**
            - a) HTTP

            ## Testing Approach
            **Q9. not a question in this section**
        """)
        self.assertEqual(ls.count_open_questions(body), 2)

    def test_no_section(self):
        self.assertEqual(ls.count_open_questions("## Summary\n**Q1. x**\n"), 0)

    def test_section_without_questions(self):
        self.assertEqual(ls.count_open_questions("## Open Questions — Round 3\n\nNone.\n"), 0)

    def test_code_fences_are_ignored(self):
        body = dedent("""
            ## Open Questions — Round 1
            **Q1. Real?**
            ```markdown
            ## Open Questions — Round 9
            **Q7. Example only**
            ```
            **Q2. Also real?**
        """)
        self.assertEqual(ls.count_open_questions(body), 2)

    def test_four_backtick_fence_with_inner_block(self):
        body = dedent("""
            ## Open Questions — Round 1
            **Q1. Real?**
            ````markdown
            ```markdown
            **Q7. Example only**
            ```
            ## Open Questions — Round 9
            **Q8. Example only**
            ````
            **Q2. Also real?**
        """)
        self.assertEqual(ls.count_open_questions(body), 2)

    def test_tilde_fence_with_inner_backtick_block(self):
        body = dedent("""
            ## Open Questions — Round 1
            **Q1. Real?**
            ~~~markdown
            ```
            **Q7. Example only**
            ```
            ## Open Questions — Round 9
            **Q8. Example only**
            ~~~
            **Q2. Also real?**
        """)
        self.assertEqual(ls.count_open_questions(body), 2)

    def test_backtick_fence_not_closed_by_tildes_or_shorter_run(self):
        body = dedent("""
            ## Open Questions — Round 1
            ````
            ~~~~
            ```
            **Q7. Example only**
            ````
            **Q1. Real?**
            **Q2. Also real?**
        """)
        self.assertEqual(ls.count_open_questions(body), 2)

    def test_closing_fence_needs_nothing_after_the_run(self):
        body = dedent("""
            ## Open Questions — Round 1
            ```
            ``` not a closing fence
            **Q7. Example only**
            ```
            **Q1. Real?**
            **Q2. Also real?**
        """)
        self.assertEqual(ls.count_open_questions(body), 2)

    def test_longer_run_closes_fence(self):
        body = dedent("""
            ## Open Questions — Round 1
            ~~~
            **Q7. Example only**
            ~~~~~
            **Q1. Real?**
        """)
        self.assertEqual(ls.count_open_questions(body), 1)

    def test_indented_fence_in_list_item_is_recognized(self):
        # Lenient on purpose: CommonMark allows at most 3 spaces of indentation,
        # loom-state accepts any, so fences nested in list items are code.
        body = dedent("""
            ## Open Questions — Round 1
            - Example:
                ```markdown
                **Q7. Example only**
                ```
            **Q1. Real?**
        """)
        self.assertEqual(ls.count_open_questions(body), 1)

    def test_indented_close_matches_unindented_open(self):
        body = dedent("""
            ## Open Questions — Round 1
            ```
            **Q7. Example only**
                    ```
            **Q1. Real?**
        """)
        self.assertEqual(ls.count_open_questions(body), 1)

    def test_unclosed_fence_detection(self):
        self.assertFalse(ls.has_unclosed_fence("```\ncode\n```\ntext\n"))
        self.assertFalse(ls.has_unclosed_fence("no fences\n"))
        self.assertTrue(ls.has_unclosed_fence("````\n```\ncode\n```\n"))
        self.assertTrue(ls.has_unclosed_fence("~~~\ntext\n```\n"))

    def test_fenced_accepted_by_default_is_not_counted(self):
        body = dedent("""
            ````markdown
            ```
            accepted by default — revisit if needed
            ```
            accepted by default — revisit if needed
            ````
            Q3 accepted by default — revisit if needed
        """)
        self.assertEqual(ls.count_accepted_by_default(body), 1)

    def test_subheadings_do_not_end_section(self):
        body = "## Open Questions — Round 1\n### Storage\n**Q1. A?**\n### API\n**Q2. B?**\n"
        self.assertEqual(ls.count_open_questions(body), 2)

    def test_accepted_by_default(self):
        body = dedent("""
            ## Open Questions — Round 5 of ~5
            **Q8. Minor naming?** — accepted by default — revisit if needed
            **Q9. Real one?**
            ## Resolved Decisions
            | 6 | Logging | a | recommended | 5 | no | accepted by default — revisit if needed |
            | 7 | Retry | b | recommended | 5 | no | Accepted by default — revisit if needed |
        """)
        self.assertEqual(ls.count_open_questions(body), 1)
        self.assertEqual(ls.count_accepted_by_default(body), 3)


class PlanAndLogTest(unittest.TestCase):
    PLAN = dedent("""
        ## Phase Overview
        - [x] 1. Fixed-response endpoint, verifiable via curl
        - [ ] 2. Wire to real storage
        - [ ] 3. Add auth

        ## Phase 1: Endpoint
        ### Verification
        - [x] Automated: make test
        - [ ] Manual: none
    """)

    def test_phase_overview(self):
        self.assertEqual(ls.parse_phase_overview(self.PLAN), [(1, True), (2, False), (3, False)])

    def test_indented_sub_checkboxes_are_ignored(self):
        plan = dedent("""
            ## Phase Overview
            - [x] 1. Endpoint
            - [ ] 2. Storage
              - [ ] migrate the schema
              - [x] add the index
        """)
        self.assertEqual(ls.parse_phase_overview(plan), [(1, True), (2, False)])

    def test_indented_top_level_items_still_count(self):
        plan = "## Phase Overview\n   - [ ] 1. A\n   - [x] 2. B\n      - [ ] sub\n"
        self.assertEqual(ls.parse_phase_overview(plan), [(1, False), (2, True)])

    def test_phase_overview_without_numbers(self):
        self.assertEqual(ls.parse_phase_overview("## Phase Overview\n- [X] a\n- [ ] b\n"), [(1, True), (2, False)])

    def test_log_headings(self):
        log = dedent("""
            ## Phase 1 — done — d4e5f6
            Checks: lint ✓ typecheck ✓ test ✓ (42 passed)

            ## Phase 2 — in-progress

            ## Phase 2 — blocked
            Reason: storage API missing

            ## Phase 3 - done - abc1234
        """)
        phases = ls.parse_log(log)
        self.assertEqual(phases[1], {"status": "done", "commit": "d4e5f6", "reason": None})
        self.assertEqual(phases[2], {"status": "blocked", "commit": None, "reason": "storage API missing"})
        self.assertEqual(phases[3]["commit"], "abc1234")

    def test_blocked_reason_in_heading(self):
        phases = ls.parse_log("## Phase 1 — blocked — tests keep failing\n")
        self.assertEqual(phases[1]["reason"], "tests keep failing")

    def test_progress_log_wins_over_checkbox(self):
        log = "## Phase 1 — done — d4e5f6\n## Phase 2 — in-progress\n"
        impl, warnings = ls.implementation_progress("full", self.PLAN, log)
        self.assertEqual(warnings, [])
        self.assertEqual(impl["total"], 3)
        self.assertEqual(impl["done"], 1)
        self.assertEqual(impl["inProgress"], 2)
        self.assertIsNone(impl["blocked"])
        self.assertEqual(impl["phases"][0]["commit"], "d4e5f6")

    def test_progress_checkbox_without_log(self):
        impl, _ = ls.implementation_progress("quick", self.PLAN, None)
        self.assertEqual((impl["total"], impl["done"]), (3, 1))

    def test_progress_blocked(self):
        impl, _ = ls.implementation_progress("full", self.PLAN, "## Phase 2 — blocked\nReason: flaky\n")
        self.assertEqual(impl["blocked"], {"phase": 2, "reason": "flaky"})

    def test_oneshot_single_implicit_phase(self):
        impl, _ = ls.implementation_progress("oneshot", None, None)
        self.assertEqual((impl["total"], impl["done"]), (1, 0))
        impl, _ = ls.implementation_progress("oneshot", None, "## Phase 1 — done — abc123\n")
        self.assertEqual((impl["total"], impl["done"]), (1, 1))

    def test_plan_without_overview_warns(self):
        impl, warnings = ls.implementation_progress("full", "## Goal\n", None)
        self.assertEqual(impl["total"], 0)
        self.assertEqual(len(warnings), 1)

    def test_no_plan(self):
        impl, warnings = ls.implementation_progress("full", None, None)
        self.assertEqual((impl["total"], warnings), (0, []))


class ResearchReferencesTest(unittest.TestCase):
    def test_paths_with_and_without_lines(self):
        body = dedent("""
            The handler lives in `src/auth/handler.py:42` and calls src/db.py:10-20.
            See ./README.md and pyproject.toml. URL https://example.com/a/b.html is not a path.
            Version 1.2 is not a path either; neither is e.g.
        """)
        refs = ls.research_references(body)
        self.assertIn("src/auth/handler.py", refs)
        self.assertIn("src/db.py", refs)
        self.assertIn("README.md", refs)
        self.assertIn("pyproject.toml", refs)
        self.assertFalse(any("example.com" in r for r in refs))

    def test_extensionless_paths(self):
        refs = ls.research_references("Build via `Makefile` and Dockerfile; state in bin/loom-state:12. LICENSE.")
        for path in ("Makefile", "Dockerfile", "bin/loom-state", "LICENSE"):
            self.assertIn(path, refs)
        self.assertNotIn("Build", refs)
        self.assertNotIn("12", refs)


class ChecksSummaryTest(unittest.TestCase):
    def test_summary(self):
        ok = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}
        bad = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}
        running = {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}
        ctx_pending = {"__typename": "StatusContext", "state": "PENDING"}
        self.assertEqual(ls.summarize_checks([]), "none")
        self.assertEqual(ls.summarize_checks([ok]), "passing")
        self.assertEqual(ls.summarize_checks([ok, bad, running]), "failing")
        self.assertEqual(ls.summarize_checks([ok, running]), "pending")
        self.assertEqual(ls.summarize_checks([ok, ctx_pending]), "pending")

    def test_checks_by_name(self):
        rollup = [
            {"__typename": "CheckRun", "name": "build", "status": "COMPLETED", "conclusion": "FAILURE"},
            {"__typename": "StatusContext", "context": "ci/legacy", "state": "PENDING"},
            {"__typename": "CheckRun", "name": "build", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"},  # no name
            "not an object",
        ]
        self.assertEqual(ls.checks_by_name(rollup), {"build": "passing", "ci/legacy": "pending"})
        self.assertEqual(ls.required_check_state(rollup, "build"), "passing")
        self.assertEqual(ls.required_check_state(rollup, "ci/legacy"), "pending")
        self.assertEqual(ls.required_check_state(rollup, "check"), "missing")
        self.assertEqual(ls.required_check_state(None, "check"), "missing")

    def test_latest_by_start_time(self):
        rollup = [
            {"name": "build", "status": "COMPLETED", "conclusion": "SUCCESS", "startedAt": "2026-11-12T10:00:00Z"},
            {"name": "build", "status": "COMPLETED", "conclusion": "FAILURE", "startedAt": "2026-11-12T09:00:00Z"},
        ]
        self.assertEqual(ls.required_check_state(rollup, "build"), "passing")
        rollup[1]["startedAt"] = "2026-11-12T11:00:00Z"
        self.assertEqual(ls.required_check_state(rollup, "build"), "failing")


class PipedFilterTest(unittest.TestCase):
    def test_filters(self):
        cases = {
            "make test | grep -v x": "grep",
            "go test ./... 2>&1|tail -5": "tail",
            "pytest |& FOO=1 /usr/bin/head": "head",
            "pytest | tee out.log | wc -l": "wc",
            "pytest | rg FAIL": "rg",
            "make check": None,
            "make test | tee out.log": None,
            "make test || head x": None,
            "npm ci && npm run check": None,
            "echo 'a | grep'": None,
            "echo \"unclosed": None,
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(ls.piped_filter(command), expected)


class MetricsDurationTest(unittest.TestCase):
    def test_non_finite_and_absurd_durations_are_skipped(self):
        events = []
        for i, value in enumerate((float("inf"), float("nan"), -1, 10 ** 400, ls.MAX_SEGMENT_SECONDS + 1, True, 30)):
            events.append({"event": "start", "agent_id": "a%d" % i, "phase": "implement"})
            events.append({"event": "stop", "agent_id": "a%d" % i, "phase": "implement", "duration_s": value})
        self.assertEqual(ls.events_metrics(events)["subagentSeconds"], 30)


if __name__ == "__main__":
    unittest.main()
