"""Tests for the pure decision table (LOOM_SPEC.md section 9.12)."""
from __future__ import annotations

import copy
import unittest
from typing import Any, Dict, List

from loomtest import loom_state

decide = loom_state().decide_next
warn = loom_state().routing_warnings
UNCOMMITTED = ("working tree has uncommitted changes; they are not part of research, design, or plan "
               "(commit, stash, or discard them before /loom:implement)")


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

    def test_row3_no_artifact_status_blocked(self):
        # Artifacts have no `blocked` status (artifact_status reports it as unknown, in-review).
        s = state(artifacts=[art("research", "blocked")])
        self.assertNext(s, "/loom:research-questions")

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
        self.assertNext(s, "/loom:iterate <answers>", "04-plan.md has 1 open question")

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
        r = self.assertNext(s, "/loom:iterate <answers>", "1 open question")
        self.assertNotIn("questions", r["reason"])

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
    def test_row5_dirty_tree_before_the_plan_gate_falls_through(self):
        # Research, design, and plan never change code: a dirty tree is not implement's work.
        s = state(artifacts=[art("design", "in-review", 3)], workingTree="dirty")
        self.assertNext(s, "/loom:iterate <answers>", "design has 3 open questions")
        self.assertEqual(warn(s), [UNCOMMITTED])
        s = state("quick", [art("research", "approved"), art("plan", "in-review")], workingTree="dirty")
        self.assertNext(s, "/loom:iterate approve", "plan is in review")
        s = state(artifacts=[art("research-questions", "approved")], workingTree="dirty")
        self.assertNext(s, "/loom:research", "02-research.md is missing")
        s = state("quick", [art("research", "approved"), art("plan", "draft")], workingTree="dirty")
        self.assertNext(s, "/loom:plan", "draft")
        self.assertEqual(warn(s), [UNCOMMITTED])

    def test_row5_in_progress_without_an_approved_plan_falls_through(self):
        s = state("quick", [art("research", "approved")], implementation=impl(1, 0, in_progress=1))
        self.assertNext(s, "/loom:plan", "04-plan.md is missing")
        self.assertEqual(len(warn(s)), 1)
        self.assertIn("phase 1 in progress, but 04-plan.md is not approved", warn(s)[0])

    def test_row5_no_warning_once_the_gate_holds(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 1), workingTree="dirty")
        self.assertEqual(warn(s), [])
        s = state("oneshot", implementation=impl(1, 0), workingTree="dirty")
        self.assertNext(s, "/loom:implement", "uncommitted")
        self.assertEqual(warn(s), [])
        # Row 4 (a plan change) explains itself: no extra warning.
        s = self.reopened(art("plan", "in-review"), done=1, workingTree="dirty")
        self.assertEqual(warn(s), [])

    def test_implement_needs_the_plan_gate(self):
        """Invariant: /loom:implement only for oneshot or an approved 04-plan.md."""
        earlier = {"full": FULL_APPROVED[:3], "quick": [art("research", "approved")], "oneshot": [], None: []}
        for mode in ("full", "quick", "oneshot", None):
            for plan_status in (None, "draft", "in-review", "approved"):
                for tree in ("clean", "dirty", None):
                    for progress in (impl(), impl(2, 0, in_progress=1), impl(2, 1), impl(2, 1, in_progress=2),
                                     impl(2, 2), impl(1, 0, blocked={"phase": 1, "reason": "x"})):
                        for ticket_pr in (None, 57):
                            for pr in (None, open_pr(), open_pr(checks="failing")):
                                arts = list(earlier[mode])
                                if plan_status:
                                    arts.append(art("plan", plan_status))
                                s = state(mode=mode, artifacts=arts, workingTree=tree,
                                          implementation=copy.deepcopy(progress), pr=pr)
                                s["task"]["pr"] = ticket_pr
                                with self.subTest(mode=mode, plan=plan_status, tree=tree, impl=progress,
                                                  ticket_pr=ticket_pr, pr=pr):
                                    r = decide(s)
                                    if r["command"] == "/loom:implement":
                                        self.assertTrue(mode == "oneshot" or plan_status == "approved", r)
                                    if tree is None:
                                        self.assertNotIn(r["command"], ("/loom:describe-pr", "/loom:finish-task"))

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
        r = self.assertNext(s, "/loom:iterate <answers>", "plan has 1 open question")
        self.assertNotIn("1 open questions", r["reason"])

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

    def test_row8_pr_from_ticket_with_phases_left_goes_to_implement(self):
        # A plan change on an open PR, approved again; SessionStart and Next: lines run without --pr.
        for mode, arts, progress in (("full", FULL_APPROVED, impl(3, 2)), ("oneshot", [], impl(1, 0)),
                                     ("quick", [art("research", "approved"), art("plan", "approved")], impl())):
            with self.subTest(mode=mode):
                s = state(mode, arts, implementation=progress)
                s["task"]["pr"] = 57
                r = self.assertNext(s, "/loom:implement", "PR #57 exists (its state was not read)")
                self.assertIn("%d of %d implementation phases are done" % (progress["done"], progress["total"]),
                              r["reason"])

    def test_row8_pr_from_ticket_without_the_plan_gate_falls_through(self):
        s = state("quick", [art("research", "approved")], implementation=impl(2, 1))
        s["task"]["pr"] = 57
        self.assertNext(s, "/loom:plan", "missing")

    # Row 8: the required check (ci.requiredCheck) decides when the PR reports it.
    def test_row8_required_check_decides(self):
        cases = (
            ("failing", "passing", "/loom:iterate", "required check 'build' is failing"),
            ("passing", "failing", "/loom:finish-task", "required check 'build' passed"),
            ("pending", "failing", "/loom:finish-task", "required check 'build' is pending"),
            ("missing", "failing", "/loom:iterate", "has failing checks"),
            ("missing", "passing", "/loom:finish-task", "checks are green"),
            ("missing", "pending", "/loom:finish-task", "checks are pending"),
        )
        for required, overall, command, reason in cases:
            with self.subTest(required=required, overall=overall):
                s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3),
                          pr=open_pr(checks=overall, requiredCheck=required), ci={"requiredCheck": "build"})
                self.assertNext(s, command, reason)

    def test_row8_required_check_passing_still_routes_review_and_rebase(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3),
                  pr=open_pr(checks="failing", requiredCheck="passing", reviewDecision="CHANGES_REQUESTED"))
        self.assertNext(s, "/loom:iterate", "requested changes")
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3),
                  pr=open_pr(checks="failing", requiredCheck="pending", behindMain=1))
        self.assertNext(s, "/loom:iterate rebase", "behind")

    def test_row8_required_check_without_ci_in_state(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(requiredCheck="failing"))
        self.assertNext(s, "/loom:iterate", "the required check is failing")

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

    def test_invalid_mode_beats_pr_routing(self):
        s = state(mode=None, pr=open_pr(checks="failing"))
        self.assertNext(s, "/loom:iterate mode <oneshot|quick|full>", "no valid mode")

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
        self.assertNext(state(mode=None), "/loom:iterate mode <oneshot|quick|full>", "no valid mode")

    def test_invalid_mode_always_routes_to_a_mode_change(self):
        """With an invalid mode only rows 1, 2, and the rebase row come first."""
        approved = [art("research", "approved"), art("plan", "approved")]
        variants = {
            "in-progress": dict(implementation=impl(2, 1, in_progress=2)),
            "dirty": dict(implementation=impl(2, 1), workingTree="dirty"),
            "dirty all done": dict(implementation=impl(2, 2), workingTree="dirty"),
            "ticket pr": dict(implementation=impl(2, 1)),
            "ticket pr all done": dict(implementation=impl(2, 2)),
            "open pr": dict(implementation=impl(2, 1), pr=open_pr()),
            "merged pr": dict(implementation=impl(2, 2), pr=open_pr(state="MERGED")),
            "all done": dict(implementation=impl(2, 2)),
            "blocked": dict(implementation=impl(2, 1, blocked={"phase": 2, "reason": "x"})),
            "plan reopened": dict(implementation=impl(2, 1)),
            "unknown tree": dict(implementation=impl(2, 2), workingTree=None),
        }
        for mode in (None, "fast", "Quick"):
            for name, overrides in variants.items():
                arts = approved[:1] + [art("plan", "in-review")] if name == "plan reopened" else approved
                s = state(mode=mode, artifacts=arts, **overrides)
                if name.startswith("ticket pr"):
                    s["task"]["pr"] = 57
                with self.subTest(mode=mode, variant=name):
                    self.assertNext(s, "/loom:iterate mode <oneshot|quick|full>", "no valid mode")
        self.assertNext(state(mode="fast", onMain=True), "/loom:start-task #<n>")
        self.assertNext(state(mode="fast", rebaseInProgress=True), "/loom:iterate rebase")
        s = state(mode="fast")
        s["task"]["archived"] = True
        self.assertNext(s, "/loom:start-task #42", "archived")

    # A stopped rebase of the task branch.
    def test_rebase_in_progress(self):
        for overrides in ({}, {"workingTree": "dirty"}, {"implementation": impl(2, 1, in_progress=2)},
                          {"pr": open_pr(checks="failing")}):
            with self.subTest(overrides=overrides):
                s = state(artifacts=FULL_APPROVED, rebaseInProgress=True, **overrides)
                self.assertNext(s, "/loom:iterate rebase",
                                "a rebase of feat/42-auth-flow is in progress and has to be continued or aborted")

    def test_rebase_in_progress_without_a_task(self):
        self.assertNext(state(branch="spike/x", task=None, rebaseInProgress=True), "/loom:start-task #<n>")
        s = state(rebaseInProgress=True)
        s["task"]["archived"] = True
        self.assertNext(s, "/loom:start-task #42", "archived")

    # An unknown working tree (git status failed) fails closed.
    def test_unknown_tree_never_describes_or_finishes(self):
        cases = (
            state(artifacts=FULL_APPROVED, implementation=impl(3, 3)),
            state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr()),
            state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(state="MERGED")),
            state(artifacts=FULL_APPROVED, implementation=impl(3, 3), pr=open_pr(checks="pending")),
        )
        for s in cases:
            s["workingTree"] = None
            with self.subTest(pr=s["pr"]):
                r = self.assertNext(s, "/loom:iterate <feedback>", "git status failed")
                self.assertIn("needs a known working tree", r["reason"])

    def test_unknown_tree_keeps_other_routes(self):
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 1), workingTree=None)
        self.assertNext(s, "/loom:implement", "1 of 3")
        s = state(artifacts=FULL_APPROVED, implementation=impl(3, 3), workingTree=None, pr=open_pr(checks="failing"))
        self.assertNext(s, "/loom:iterate", "failing checks")
        s = state(artifacts=[art("design", "in-review", 2)], workingTree=None)
        self.assertNext(s, "/loom:iterate <answers>")


class PlanGateTest(unittest.TestCase):
    def test_plan_gate_holds(self):
        gate = loom_state().plan_gate_holds
        self.assertTrue(gate({"mode": "oneshot"}, []))
        self.assertTrue(gate({"mode": "quick"}, [art("plan", "approved")]))
        self.assertFalse(gate({"mode": None}, [art("plan", "approved")]))
        self.assertFalse(gate({"mode": "fast"}, [art("plan", "approved")]))
        for status in ("draft", "in-review", None):
            self.assertFalse(gate({"mode": "full"}, [art("plan", status)]))
        self.assertFalse(gate({"mode": "full"}, []))

    def test_routing_warnings_outside_a_task(self):
        self.assertEqual(warn(state(onMain=True, workingTree="dirty")), [])
        self.assertEqual(warn(state(task=None, workingTree="dirty")), [])
        s = state(workingTree="dirty")
        s["task"]["archived"] = True
        self.assertEqual(warn(s), [])


if __name__ == "__main__":
    unittest.main()
