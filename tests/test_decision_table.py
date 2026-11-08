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
    def test_row3_blocked_phase(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 1, blocked={"phase": 2, "reason": "API missing"}))
        self.assertNext(s, "/loom:iterate <fix>", "API missing")

    def test_row3_blocked_artifact(self):
        s = state(artifacts=[art("research", "blocked")])
        self.assertNext(s, "/loom:iterate <fix>", "02-research.md is blocked")

    def test_row3_beats_pr(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 2, blocked={"phase": 3, "reason": None}),
                  pr=open_pr(checks="failing"))
        self.assertNext(s, "/loom:iterate <fix>", "no reason recorded")

    def test_row3_blocked_beats_dirty_tree(self):
        s = state(artifacts=FULL_APPROVED, workingTree="dirty",
                  implementation=impl(3, 1, blocked={"phase": 2, "reason": "x"}))
        self.assertNext(s, "/loom:iterate <fix>", "phase 2 is blocked")

    def test_row3_blocked_beats_in_progress(self):
        s = state(artifacts=FULL_APPROVED,
                  implementation=impl(3, 1, in_progress=3, blocked={"phase": 2, "reason": "x"}))
        self.assertNext(s, "/loom:iterate <fix>", "phase 2 is blocked")

    def test_row3_blocked_with_approved_plan(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(2, 0, blocked={"phase": 1, "reason": "x"}))
        self.assertNext(s, "/loom:iterate <fix>", "phase 1 is blocked")

    def test_row3_oneshot_blocked(self):
        s = state(mode="oneshot", workingTree="dirty", implementation=impl(1, 0, blocked={"phase": 1, "reason": "x"}))
        self.assertNext(s, "/loom:iterate <fix>", "phase 1 is blocked")

    # Row 4: a blocked implementation phase waits for the changed plan's gate.
    def plan_changed(self, plan: Dict[str, Any], tree: str = "clean") -> Dict[str, Any]:
        arts = FULL_APPROVED[:3] + [plan]
        return state(artifacts=arts, workingTree=tree, implementation=impl(2, 0, blocked={"phase": 1, "reason": "x"}))

    def test_row4_blocked_plan_in_review(self):
        self.assertNext(self.plan_changed(art("plan", "in-review")), "/loom:iterate approve", "must be approved")

    def test_row4_blocked_plan_open_round(self):
        s = self.plan_changed(art("plan", "in-review", 1))
        self.assertNext(s, "/loom:iterate <answers>", "1 open questions")

    def test_row4_blocked_dirty_tree_plan_in_review(self):
        s = self.plan_changed(art("plan", "in-review"), tree="dirty")
        self.assertNext(s, "/loom:iterate approve")

    def test_row4_blocked_dirty_tree_plan_open_round(self):
        s = self.plan_changed(art("plan", "in-review", 2), tree="dirty")
        self.assertNext(s, "/loom:iterate <answers>")

    def test_row4_blocked_draft_plan_is_an_unfinished_edit(self):
        s = self.plan_changed(art("plan", "draft"), tree="dirty")
        self.assertNext(s, "/loom:iterate <feedback>", "edit not finished")

    # Row 4 without a blocked phase: a plan change after implementation started.
    def reopened(self, plan: Dict[str, Any], done: int = 2, **overrides: Any) -> Dict[str, Any]:
        return state(artifacts=FULL_APPROVED[:3] + [plan], implementation=impl(2, done), **overrides)

    def test_row4_draft_plan_all_done_is_an_unfinished_edit(self):
        self.assertNext(self.reopened(art("plan", "draft")), "/loom:iterate <feedback>", "edit not finished")

    def test_row4_draft_plan_pr_open_green(self):
        s = self.reopened(art("plan", "draft"), pr=open_pr())
        self.assertNext(s, "/loom:iterate <feedback>", "edit not finished")

    def test_row4_draft_plan_phases_left(self):
        self.assertNext(self.reopened(art("plan", "draft"), done=1), "/loom:iterate <feedback>", "implementation started")

    def test_row4_draft_wins_over_open_questions(self):
        self.assertNext(self.reopened(art("plan", "draft", 3), done=1), "/loom:iterate <feedback>")

    def test_row4_in_review_plan_pr_open(self):
        s = self.reopened(art("plan", "in-review"), pr=open_pr(checks="failing"))
        self.assertNext(s, "/loom:iterate approve", "must be approved first")

    def test_row4_open_round_dirty_tree(self):
        s = self.reopened(art("plan", "in-review", 1), done=1, workingTree="dirty")
        self.assertNext(s, "/loom:iterate <answers>", "1 open questions")

    def test_row4_from_log_entries_only(self):
        phases = [{"number": 1, "status": "done", "commit": "abc"}, {"number": 2, "status": "pending", "commit": None}]
        s = state(artifacts=FULL_APPROVED[:3] + [art("plan", "in-review")],
                  implementation={"total": 2, "done": 1, "inProgress": None, "blocked": None, "phases": phases})
        self.assertNext(s, "/loom:iterate approve")

    def test_row4_not_in_oneshot(self):
        s = state(mode="oneshot", artifacts=[art("plan", "in-review")], implementation=impl(1, 1))
        self.assertNext(s, "/loom:describe-pr")

    def test_row11_draft_plan_before_implementation_reruns_plan(self):
        s = state(artifacts=FULL_APPROVED[:3] + [art("plan", "draft")])
        self.assertNext(s, "/loom:plan", "04-plan.md is draft")

    def test_row4_blocked_quick_mode_plan_in_review(self):
        s = state(mode="quick", artifacts=[art("research", "approved"), art("plan", "in-review")],
                  implementation=impl(2, 0, blocked={"phase": 2, "reason": "x"}))
        self.assertNext(s, "/loom:iterate approve", "phase 2 is blocked")

    # Row 5
    def test_row5_dirty_tree(self):
        s = state(artifacts=[art("design", "in-review", 3)], workingTree="dirty")
        self.assertNext(s, "/loom:implement", "uncommitted")

    def test_row5_phases_left_and_dirty(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 1), workingTree="dirty")
        self.assertNext(s, "/loom:implement", "uncommitted")

    def test_row5_all_done_docs_only_dirty_falls_through_to_describe_pr(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(2, 2), workingTree="dirty", workingTreeDocsOnly=True)
        self.assertNext(s, "/loom:describe-pr", "all 2 implementation phases are done")

    def test_row5_all_done_code_dirty_goes_to_iterate(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(2, 2), workingTree="dirty", workingTreeDocsOnly=False)
        self.assertNext(s, "/loom:iterate <feedback>", "uncommitted code changes after all 2 implementation phases")

    def test_row5_all_done_dirty_without_flag_counts_as_code(self):
        s = state(mode="oneshot", implementation=impl(1, 1), workingTree="dirty")
        self.assertNext(s, "/loom:iterate <feedback>")

    def test_row5_all_done_docs_only_dirty_with_open_pr_routes_the_pr(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(2, 2), workingTree="dirty",
                  workingTreeDocsOnly=True, pr=open_pr(checks="pending"))
        self.assertNext(s, "/loom:finish-task")

    def test_row5_all_done_code_dirty_merged_goes_to_finish_task(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(2, 2), workingTree="dirty",
                  workingTreeDocsOnly=False, pr=open_pr(state="MERGED"))
        self.assertNext(s, "/loom:finish-task", "merged")

    def test_row5_all_done_code_dirty_open_pr_goes_to_iterate(self):
        for pr in (open_pr(), open_pr(checks="failing"), open_pr(behindMain=2)):
            with self.subTest(pr=pr):
                s = state(artifacts=FULL_APPROVED, implementation=impl(2, 2), workingTree="dirty",
                          workingTreeDocsOnly=False, pr=pr)
                self.assertNext(s, "/loom:iterate <feedback>", "uncommitted code changes")

    def test_row5_all_done_docs_only_dirty_open_pr_routes_the_pr(self):
        for pr, command in ((open_pr(checks="failing"), "/loom:iterate"), (open_pr(behindMain=1), "/loom:iterate rebase"),
                            (open_pr(), "/loom:finish-task")):
            with self.subTest(pr=pr):
                s = state(artifacts=FULL_APPROVED, implementation=impl(2, 2), workingTree="dirty",
                          workingTreeDocsOnly=True, pr=pr)
                self.assertNext(s, command)

    def test_row5_phase_in_progress(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 1, in_progress=2))
        self.assertNext(s, "/loom:implement", "phase 2 is in progress")

    # Row 6
    def test_row6_design_open_questions(self):
        s = state(artifacts=[art("research-questions", "approved"), art("research", "in-review"),
                             art("design", "in-review", 3)])
        r = self.assertNext(s, "/loom:iterate <answers>", "design has 3 open questions")
        self.assertIn("research not reviewed", r["reason"])

    def test_row6_plan_open_questions_quick(self):
        s = state("quick", [art("research", "approved"), art("plan", "in-review", 1)])
        self.assertNext(s, "/loom:iterate <answers>", "plan has 1 open questions")

    def test_row6_design_before_plan(self):
        s = state(artifacts=[art("design", "in-review", 1), art("plan", "in-review", 2)])
        self.assertNext(s, "/loom:iterate <answers>", "design")

    def test_row6_draft_gate_with_questions_reruns_phase(self):
        s = state(artifacts=[art("research-questions", "approved"), art("research", "approved"),
                             art("design", "draft", 2)])
        self.assertNext(s, "/loom:design", "draft")
        s = state("quick", [art("research", "approved"), art("plan", "draft", 1)])
        self.assertNext(s, "/loom:plan", "draft")

    def test_row6_approved_gate_with_questions_does_not_block(self):
        s = state(artifacts=[art("research", "approved"), art("design", "approved", 2)])
        self.assertNext(s, "/loom:plan")

    def test_row6_non_gate_questions_never_block(self):
        s = state("quick", [art("research", "in-review", 4)])
        self.assertNext(s, "/loom:plan")

    def test_row6_pr_open_plan_open_round(self):
        arts = FULL_APPROVED[:3] + [art("plan", "in-review", 2)]
        s = state(artifacts=arts, pr=open_pr(checks="failing"))
        self.assertNext(s, "/loom:iterate <answers>", "plan has 2 open questions")

    # Row 7
    def test_row7_design_in_review(self):
        s = state(artifacts=[art("research", "approved"), art("design", "in-review")])
        self.assertNext(s, "/loom:iterate approve", "design is in review")

    def test_row7_plan_in_review(self):
        s = state("quick", [art("research", "approved"), art("plan", "in-review")])
        self.assertNext(s, "/loom:iterate approve", "plan")

    def test_row7_design_ignored_in_quick_mode(self):
        s = state("quick", [art("research", "approved"), art("design", "in-review", 2)])
        self.assertNext(s, "/loom:plan")

    def test_row7_pr_open_plan_in_review(self):
        arts = FULL_APPROVED[:3] + [art("plan", "in-review")]
        s = state(artifacts=arts, pr=open_pr())
        self.assertNext(s, "/loom:iterate approve", "plan is in review")

    def test_row7_all_done_design_in_review(self):
        arts = [art("research-questions", "approved"), art("research", "approved"),
                art("design", "in-review"), art("plan", "approved")]
        self.assertNext(state(artifacts=arts, implementation=impl(2, 2)), "/loom:iterate approve", "design is in review")


    # Row 8 (section 6.2)
    def test_row8_checks_failing(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3),
                  pr=open_pr(checks="failing", reviewDecision="CHANGES_REQUESTED", behindMain=2))
        self.assertNext(s, "/loom:iterate", "failing checks")

    def test_row8_changes_requested(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3),
                  pr=open_pr(reviewDecision="CHANGES_REQUESTED", behindMain=2))
        self.assertNext(s, "/loom:iterate", "requested changes")

    def test_row8_behind_main(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(behindMain=2, checks="pending"))
        self.assertNext(s, "/loom:iterate rebase", "behind")

    def test_row8_behind_by_merge_state(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3),
                  pr=open_pr(behindMain=None, mergeStateStatus="BEHIND"))
        self.assertNext(s, "/loom:iterate rebase")

    def test_row8_checks_pending(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(checks="pending"))
        self.assertNext(s, "/loom:finish-task", "pending")

    def test_row8_green(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr())
        self.assertNext(s, "/loom:finish-task", "green")

    def test_row8_open_pr_with_phases_left_goes_to_implement_first(self):
        for pr in (open_pr(checks="failing"), open_pr(reviewDecision="CHANGES_REQUESTED"), open_pr(behindMain=3),
                   open_pr(checks="pending"), open_pr(), open_pr(checks="none")):
            with self.subTest(pr=pr):
                s = state(artifacts=FULL_APPROVED, implementation=impl(3, 2), pr=pr)
                self.assertNext(s, "/loom:implement", "PR #57 is open and 2 of 3")

    def test_row8_open_pr_oneshot_not_done_goes_to_implement(self):
        s = state(mode="oneshot", implementation=impl(1, 0), pr=open_pr())
        self.assertNext(s, "/loom:implement", "PR #57 is open")

    def test_row8_merged_pr_with_phases_left_stays_finish_task(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 2), pr=open_pr(state="MERGED"))
        self.assertNext(s, "/loom:finish-task", "merged")

    def test_row8_open_pr_with_reopened_plan_stays_row4(self):
        arts = FULL_APPROVED[:-1] + [art("plan", "in-review")]
        s = state(artifacts=arts, implementation=impl(3, 2), pr=open_pr())
        self.assertNext(s, "/loom:iterate approve")

    def test_row8_merged(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(state="MERGED"))
        self.assertNext(s, "/loom:finish-task", "merged")

    def test_row8_closed_pr_falls_through(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(state="CLOSED"))
        self.assertNext(s, "/loom:describe-pr")

    def test_row8_pr_known_from_ticket_only(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3))
        s["task"]["pr"] = 57
        self.assertNext(s, "/loom:finish-task", "PR #57")

    # Row 9
    def test_row9_all_phases_done(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3))
        self.assertNext(s, "/loom:describe-pr", "all 3")

    def test_row9_oneshot_done(self):
        self.assertNext(state("oneshot", implementation=impl(1, 1)), "/loom:describe-pr")

    def test_row9_comes_after_open_gate_questions(self):
        s = state(artifacts=[art("design", "in-review", 2), art("plan", "approved")], implementation=impl(2, 2))
        self.assertNext(s, "/loom:iterate <answers>", "design has 2 open questions")

    def test_row9_non_gate_review_does_not_block(self):
        s = state(artifacts=[art("research", "in-review"), art("design", "approved"), art("plan", "approved")],
                  implementation=impl(2, 2))
        self.assertNext(s, "/loom:describe-pr")

    def test_invalid_mode_still_routes_pr(self):
        s = state(mode=None, pr=open_pr(checks="failing"))
        self.assertNext(s, "/loom:iterate", "failing checks")

    # Row 10
    def test_row10_plan_approved(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 1))
        self.assertNext(s, "/loom:implement", "1 of 3")

    def test_row10_plan_approved_without_phases(self):
        s = state("quick", [art("research", "approved"), art("plan", "approved")])
        self.assertNext(s, "/loom:implement", "not started")

    def test_row10_oneshot(self):
        self.assertNext(state("oneshot", implementation=impl(1, 0)), "/loom:implement")

    def test_row10_oneshot_ignores_other_artifacts(self):
        s = state("oneshot", [art("plan", "draft")], implementation=impl(1, 0))
        self.assertNext(s, "/loom:implement")

    # Row 11
    def test_row11_full_starts_with_research_questions(self):
        self.assertNext(state(), "/loom:research-questions", "missing")

    def test_row11_quick_starts_with_research(self):
        self.assertNext(state("quick"), "/loom:research")

    def test_row11_full_research_after_questions(self):
        s = state(artifacts=[art("research-questions", "in-review")])
        r = self.assertNext(s, "/loom:research")
        self.assertIn("research-questions not reviewed", r["reason"])

    def test_row11_design_after_research_in_review(self):
        s = state(artifacts=[art("research-questions", "approved"), art("research", "in-review")])
        r = self.assertNext(s, "/loom:design")
        self.assertIn("research not reviewed", r["reason"])

    def test_row11_plan_after_design(self):
        s = state(artifacts=[art("research-questions", "approved"), art("research", "approved"),
                             art("design", "approved")])
        self.assertNext(s, "/loom:plan", "04-plan.md is missing")

    def test_row11_draft_is_rerun(self):
        s = state("quick", [art("research", "draft")])
        self.assertNext(s, "/loom:research", "draft")

    def test_row11_later_phase_wins(self):
        s = state(artifacts=[art("research", "draft"), art("design", "approved")])
        self.assertNext(s, "/loom:plan")

    def test_row11_stale_research_warning(self):
        s = state("quick", [art("research", "approved", stale=True)])
        r = self.assertNext(s, "/loom:plan")
        self.assertIn("stale", r["reason"])

    def test_invalid_mode(self):
        self.assertNext(state(mode=None), "/loom:iterate", "no valid mode")


if __name__ == "__main__":
    unittest.main()
