"""Tests for the pure decision table (LOOM_SPEC.md section 9.12)."""
from __future__ import annotations

import copy
import unittest
from typing import Any, Dict, List

from loomtest import loom_state

decide = loom_state().decide_next


def art(phase: str, status: str, open_q: int = 0, **extra: Any) -> Dict[str, Any]:
    files = {"research-questions": "01-research-questions.md", "research": "02-research.md",
             "design": "03-design.md", "plan": "04-plan.md"}
    item = {"file": files[phase], "phase": phase, "status": status, "openQuestions": open_q}
    item.update(extra)
    return item


def impl(total: int = 0, done: int = 0, in_progress=None, blocked=None) -> Dict[str, Any]:
    return {"total": total, "done": done, "inProgress": in_progress, "blocked": blocked, "phases": []}


def state(mode: str = "full", artifacts: List[Dict[str, Any]] = (), **overrides: Any) -> Dict[str, Any]:
    base = {
        "branch": "feat/42-auth-flow",
        "onMain": False,
        "task": {"number": 42, "slug": "auth-flow", "dir": ".loom/tasks/42-auth-flow",
                 "mode": mode, "archived": False, "pr": None},
        "artifacts": list(artifacts),
        "implementation": impl(),
        "workingTree": "clean",
        "pr": None,
    }
    for key, value in overrides.items():
        base[key] = value
    return base


FULL_APPROVED = [art("research-questions", "approved"), art("research", "approved"),
                 art("design", "approved"), art("plan", "approved")]


def open_pr(**fields: Any) -> Dict[str, Any]:
    pr = {"number": 57, "state": "OPEN", "reviewDecision": None, "checks": "passing",
          "mergeStateStatus": "CLEAN", "behindMain": 0}
    pr.update(fields)
    return pr


class DecisionTableTest(unittest.TestCase):
    def assertNext(self, s: Dict[str, Any], command: str, reason_part: str = "") -> Dict[str, str]:
        before = copy.deepcopy(s)
        result = decide(s)
        self.assertEqual(s, before, "decide_next must not mutate its input")
        self.assertEqual(set(result), {"command", "reason"})
        self.assertEqual(result["command"], command, result)
        if reason_part:
            self.assertIn(reason_part, result["reason"])
        return result

    # Row 1
    def test_row1_on_main(self):
        s = state(branch="main", onMain=True, task=None, workingTree="dirty")
        r = self.assertNext(s, "/loom:start-task #<n>")
        self.assertIn("/loom:backlog", r["reason"])

    # Row 2
    def test_row2_branch_matches_no_task(self):
        self.assertNext(state(branch="spike/x", task=None), "/loom:start-task #<n>", "matches no task")

    def test_row2_task_branch_without_directory(self):
        self.assertNext(state(branch="fix/7-typo", task=None), "/loom:start-task #7", "no task directory")

    def test_row2_detached_head(self):
        self.assertNext(state(branch=None, task=None), "/loom:start-task #<n>", "detached")

    def test_row2_archived_wins_over_dirty(self):
        s = state(workingTree="dirty")
        s["task"]["archived"] = True
        self.assertNext(s, "/loom:start-task #42", "archived")

    # Row 3
    def test_row3_dirty_tree(self):
        s = state(artifacts=[art("design", "in-review", 3)], workingTree="dirty")
        self.assertNext(s, "/loom:implement", "uncommitted")

    def test_row3_phase_in_progress(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 1, in_progress=2))
        self.assertNext(s, "/loom:implement", "phase 2 is in progress")

    def test_row3_beats_blocked(self):
        s = state(artifacts=FULL_APPROVED, workingTree="dirty",
                  implementation=impl(3, 1, blocked={"phase": 2, "reason": "x"}))
        self.assertNext(s, "/loom:implement")

    # Row 4
    def test_row4_blocked_phase(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 1, blocked={"phase": 2, "reason": "API missing"}))
        self.assertNext(s, "/loom:iterate <fix>", "API missing")

    def test_row4_blocked_artifact(self):
        s = state(artifacts=[art("research", "blocked")])
        self.assertNext(s, "/loom:iterate <fix>", "02-research.md is blocked")

    def test_row4_beats_pr(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 2, blocked={"phase": 3, "reason": None}),
                  pr=open_pr(checks="failing"))
        self.assertNext(s, "/loom:iterate <fix>", "no reason recorded")

    # Row 5 (section 6.2)
    def test_row5_checks_failing(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3),
                  pr=open_pr(checks="failing", reviewDecision="CHANGES_REQUESTED", behindMain=2))
        self.assertNext(s, "/loom:iterate", "failing checks")

    def test_row5_changes_requested(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3),
                  pr=open_pr(reviewDecision="CHANGES_REQUESTED", behindMain=2))
        self.assertNext(s, "/loom:iterate", "requested changes")

    def test_row5_behind_main(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(behindMain=2, checks="pending"))
        self.assertNext(s, "/loom:iterate rebase", "behind")

    def test_row5_behind_by_merge_state(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3),
                  pr=open_pr(behindMain=None, mergeStateStatus="BEHIND"))
        self.assertNext(s, "/loom:iterate rebase")

    def test_row5_checks_pending(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(checks="pending"))
        self.assertNext(s, "/loom:finish-task", "pending")

    def test_row5_green(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr())
        self.assertNext(s, "/loom:finish-task", "green")

    def test_row5_merged(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(state="MERGED"))
        self.assertNext(s, "/loom:finish-task", "merged")

    def test_row5_closed_pr_falls_through(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(state="CLOSED"))
        self.assertNext(s, "/loom:describe-pr")

    def test_row5_pr_known_from_ticket_only(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3))
        s["task"]["pr"] = 57
        self.assertNext(s, "/loom:finish-task", "PR #57")

    # Row 6
    def test_row6_all_phases_done(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3))
        self.assertNext(s, "/loom:describe-pr", "all 3")

    def test_row6_oneshot_done(self):
        self.assertNext(state("oneshot", implementation=impl(1, 1)), "/loom:describe-pr")

    def test_row6_beats_open_questions(self):
        s = state(artifacts=[art("design", "in-review", 2), art("plan", "approved")], implementation=impl(2, 2))
        self.assertNext(s, "/loom:describe-pr")

    # Row 7
    def test_row7_design_open_questions(self):
        s = state(artifacts=[art("research-questions", "approved"), art("research", "in-review"),
                             art("design", "in-review", 3)])
        r = self.assertNext(s, "/loom:iterate <answers>", "design has 3 open questions")
        self.assertIn("research not reviewed", r["reason"])

    def test_row7_plan_open_questions_quick(self):
        s = state("quick", [art("research", "approved"), art("plan", "in-review", 1)])
        self.assertNext(s, "/loom:iterate <answers>", "plan has 1 open questions")

    def test_row7_design_before_plan(self):
        s = state(artifacts=[art("design", "in-review", 1), art("plan", "in-review", 2)])
        self.assertNext(s, "/loom:iterate <answers>", "design")

    def test_row7_draft_gate_with_questions_reruns_phase(self):
        s = state(artifacts=[art("research-questions", "approved"), art("research", "approved"),
                             art("design", "draft", 2)])
        self.assertNext(s, "/loom:design", "draft")
        s = state("quick", [art("research", "approved"), art("plan", "draft", 1)])
        self.assertNext(s, "/loom:plan", "draft")

    def test_row7_approved_gate_with_questions_does_not_block(self):
        s = state(artifacts=[art("research", "approved"), art("design", "approved", 2)])
        self.assertNext(s, "/loom:plan")

    def test_row7_non_gate_questions_never_block(self):
        s = state("quick", [art("research", "in-review", 4)])
        self.assertNext(s, "/loom:plan")

    # Row 8
    def test_row8_design_in_review(self):
        s = state(artifacts=[art("research", "approved"), art("design", "in-review")])
        self.assertNext(s, "/loom:iterate approve", "design is in review")

    def test_row8_plan_in_review(self):
        s = state("quick", [art("research", "approved"), art("plan", "in-review")])
        self.assertNext(s, "/loom:iterate approve", "plan")

    def test_row8_design_ignored_in_quick_mode(self):
        s = state("quick", [art("research", "approved"), art("design", "in-review", 2)])
        self.assertNext(s, "/loom:plan")

    # Row 9
    def test_row9_plan_approved(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 1))
        self.assertNext(s, "/loom:implement", "1 of 3")

    def test_row9_plan_approved_without_phases(self):
        s = state("quick", [art("research", "approved"), art("plan", "approved")])
        self.assertNext(s, "/loom:implement", "not started")

    def test_row9_oneshot(self):
        self.assertNext(state("oneshot", implementation=impl(1, 0)), "/loom:implement")

    def test_row9_oneshot_ignores_other_artifacts(self):
        s = state("oneshot", [art("plan", "draft")], implementation=impl(1, 0))
        self.assertNext(s, "/loom:implement")

    # Row 10
    def test_row10_full_starts_with_research_questions(self):
        self.assertNext(state(), "/loom:research-questions", "missing")

    def test_row10_quick_starts_with_research(self):
        self.assertNext(state("quick"), "/loom:research")

    def test_row10_full_research_after_questions(self):
        s = state(artifacts=[art("research-questions", "in-review")])
        r = self.assertNext(s, "/loom:research")
        self.assertIn("research-questions not reviewed", r["reason"])

    def test_row10_design_after_research_in_review(self):
        s = state(artifacts=[art("research-questions", "approved"), art("research", "in-review")])
        r = self.assertNext(s, "/loom:design")
        self.assertIn("research not reviewed", r["reason"])

    def test_row10_plan_after_design(self):
        s = state(artifacts=[art("research-questions", "approved"), art("research", "approved"),
                             art("design", "approved")])
        self.assertNext(s, "/loom:plan", "04-plan.md is missing")

    def test_row10_draft_is_rerun(self):
        s = state("quick", [art("research", "draft")])
        self.assertNext(s, "/loom:research", "draft")

    def test_row10_later_phase_wins(self):
        s = state(artifacts=[art("research", "draft"), art("design", "approved")])
        self.assertNext(s, "/loom:plan")

    def test_row10_stale_research_warning(self):
        s = state("quick", [art("research", "approved", stale=True)])
        r = self.assertNext(s, "/loom:plan")
        self.assertIn("stale", r["reason"])

    def test_invalid_mode(self):
        self.assertNext(state(mode=None), "/loom:iterate", "no valid mode")


if __name__ == "__main__":
    unittest.main()
