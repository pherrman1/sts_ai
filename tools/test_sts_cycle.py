#!/usr/bin/env python3
"""Tests for the /sts-cycle state machine and shared runner architecture.

Covers:
- Policy pure-function behavior (via Python ai_cycle reference)
- Runner shared-usage verification (no duplicate implementations)
- Simulated cycle orchestration with fake agents
- Artifact and cost tracking
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def repo_root() -> Path:
    start = Path(__file__).resolve().parent
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return Path(result.stdout.strip()).resolve()


ROOT = repo_root()
sys.path.insert(0, str(ROOT))
from tools import ai_cycle


# ============================================================================
# Helpers
# ============================================================================

def ts_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def make_pass_review():
    return {
        "verdict": "PASS",
        "summary": "Implementation satisfies all requirements.",
        "eli5_summary": "Looks good, no issues found.",
        "uncertainty": "LOW",
        "issues": [],
    }


def make_fix_review():
    return {
        "verdict": "FIX",
        "summary": "A behavior is wrong.",
        "eli5_summary": "Found a problem that needs fixing.",
        "uncertainty": "MEDIUM",
        "issues": [{
            "severity": "MAJOR",
            "location": "src/test.cpp:1",
            "problem": "Behavior is incorrect.",
            "failure_mechanism": "Does not run the expected path.",
            "required_fix": "Wire the correct path.",
        }],
    }


def make_pass_verification():
    return {
        "required_checks_passed": True,
        "costs_run": ["cheap"],
        "checks": [{
            "name": "git diff --check",
            "argv": ["git", "diff", "--check"],
            "cwd": ".", "env": {}, "required": True, "cost": "cheap",
            "status": "PASS", "returncode": 0, "stdout": "",
            "duration_ms": 10,
        }],
    }


def _plan():
    return {
        "task_interpretation": "test",
        "current_behavior": "test",
        "design": "ordinary tooling change",
        "eli5_summary": "It changes a tool so its messages are easier to read.",
        "implementation_steps": [],
        "verification": [{
            "name": "git diff --check",
            "argv": ["git", "diff", "--check"],
            "cwd": ".", "env": {}, "required": True,
            "cost": "cheap", "timeout_seconds": 30,
        }],
        "documentation": [],
        "acceptance_criteria": [],
        "risks": [],
    }


# ============================================================================
# Policy behavior tests
# ============================================================================

class PolicyBehaviorTests(unittest.TestCase):

    def test_classify_comment_task_is_candidate(self):
        ok, _ = ai_cycle.classify_fast_path_task(
            "fix a misleading comment; do not change behavior")
        self.assertTrue(ok)

    def test_classify_bugfix_is_normal(self):
        ok, _ = ai_cycle.classify_fast_path_task("fix the bug in combat search")
        self.assertFalse(ok)

    def test_classify_comment_without_no_behavior_is_normal(self):
        ok, _ = ai_cycle.classify_fast_path_task("improve comments in Searcher.cpp")
        self.assertFalse(ok)

    def test_validate_plan_rejects_missing_eli5(self):
        plan = {
            "task_interpretation": "t", "current_behavior": "c",
            "design": "d", "eli5_summary": "   ",
            "implementation_steps": [], "verification": [],
            "documentation": [], "acceptance_criteria": [], "risks": [],
        }
        with self.assertRaisesRegex(RuntimeError, "eli5_summary"):
            ai_cycle.validate_plan(plan)

    def test_validate_review_rejects_pass_with_critical(self):
        with self.assertRaisesRegex(RuntimeError, "PASS with a CRITICAL"):
            ai_cycle.validate_review({
                "verdict": "PASS", "summary": "bad",
                "eli5_summary": "I found a bug.", "uncertainty": "LOW",
                "issues": [{"severity": "CRITICAL", "location": "x:1",
                            "problem": "b", "failure_mechanism": "c",
                            "required_fix": "d"}],
            })

    def test_validate_review_requires_fix_issues(self):
        with self.assertRaisesRegex(RuntimeError, "supplied no issues"):
            ai_cycle.validate_review({
                "verdict": "FIX", "summary": "bad",
                "eli5_summary": "Needs fixing.", "uncertainty": "MEDIUM",
                "issues": [],
            })

    def test_should_escalate_search_path(self):
        escalated, reasons = ai_cycle.should_escalate_to_sol(
            changed_paths=["src/search/Searcher.cpp"],
            changed_lines=10, tracked_file_count=1,
            plan={"design": "fix", "risks": [], "acceptance_criteria": []},
            verification_history=[], luna_reviews=[],
            latest_luna_review=make_pass_review(),
        )
        self.assertTrue(escalated)

    def test_confirmed_trivial_suppresses_escalation(self):
        escalated, _ = ai_cycle.should_escalate_to_sol(
            changed_paths=["src/search/Searcher.cpp"],
            changed_lines=1, tracked_file_count=1,
            plan={"design": "fix", "risks": [], "acceptance_criteria": []},
            verification_history=[], luna_reviews=[],
            latest_luna_review=make_pass_review(),
            confirmed_trivial=True,
        )
        self.assertFalse(escalated)

    def test_uncertainty_high_escalates(self):
        r = make_pass_review()
        r["uncertainty"] = "HIGH"
        escalated, _ = ai_cycle.should_escalate_to_sol(
            changed_paths=[], changed_lines=1, tracked_file_count=1,
            plan={"design": "fix", "risks": [], "acceptance_criteria": []},
            verification_history=[], luna_reviews=[], latest_luna_review=r,
        )
        self.assertTrue(escalated)

    def test_normal_task_no_escalation(self):
        escalated, _ = ai_cycle.should_escalate_to_sol(
            changed_paths=["README.md"], changed_lines=1,
            tracked_file_count=1,
            plan={"design": "doc fix", "risks": [], "acceptance_criteria": []},
            verification_history=[], luna_reviews=[],
            latest_luna_review=make_pass_review(),
        )
        self.assertFalse(escalated)

    def test_critical_review_always_escalates(self):
        escalated, _ = ai_cycle.should_escalate_to_sol(
            changed_paths=["README.md"], changed_lines=1,
            tracked_file_count=1,
            plan={"design": "doc fix", "risks": [], "acceptance_criteria": []},
            verification_history=[], luna_reviews=[{
                "verdict": "FIX", "summary": "bad",
                "eli5_summary": "bad", "uncertainty": "LOW",
                "issues": [{"severity": "CRITICAL", "location": "x:1",
                            "problem": "b", "failure_mechanism": "c",
                            "required_fix": "d"}],
            }],
            latest_luna_review=make_pass_review(),
        )
        self.assertTrue(escalated)


# ============================================================================
# Runner shared-usage verification
# ============================================================================

class RunnerSharedUsageTests(unittest.TestCase):

    def test_subagent_imports_runner(self):
        source = ts_source(".pi/extensions/subagent/index.ts")
        self.assertIn('from "./runner.ts"', source)
        self.assertIn("runPiChild", source)
        self.assertNotIn('import { spawn } from "node:child_process"', source)

    def test_sts_cycle_imports_runner(self):
        source = ts_source(".pi/extensions/sts-cycle/index.ts")
        self.assertIn('from "../subagent/runner.ts"', source)
        self.assertIn("runPiChild", source)

    def test_no_duplicate_lifecycle_constants_in_index(self):
        source = ts_source(".pi/extensions/subagent/index.ts")
        self.assertNotIn("const AGENT_END_CLOSE_GRACE_MS", source)
        self.assertNotIn("const CHILD_TERMINATION_GRACE_MS", source)
        self.assertNotIn("const SUBAGENT_HARD_TIMEOUT_MS", source)

    def test_runner_exports_lifecycle_constants(self):
        source = ts_source(".pi/extensions/subagent/runner.ts")
        self.assertIn("export const AGENT_END_CLOSE_GRACE_MS", source)
        self.assertIn("export const SUBAGENT_HARD_TIMEOUT_MS", source)

    def test_sts_cycle_no_duplicate_pi_model_by_role(self):
        source = ts_source(".pi/extensions/sts-cycle/index.ts")
        self.assertNotIn("PI_MODEL_BY_ROLE", source)
        self.assertIn("frontmatter", source.lower())
        self.assertIn("model", source.lower())

    def test_subagent_fork_marker_preserved(self):
        source = ts_source(".pi/extensions/subagent/index.ts")
        self.assertIn("STS-LOCAL FORK", source)
        self.assertIn("STS-SUBAGENT-LIFECYCLE-GUARD", source)

    def test_subagent_lifecycle_delegated_to_runner(self):
        source = ts_source(".pi/extensions/subagent/index.ts")
        self.assertIn("runner.ts", source)
        self.assertIn("delegated", source.lower())


# ============================================================================
# Simulated cycle orchestration tests
# ============================================================================

class SimulatedCycleTests(unittest.TestCase):

    def setUp(self):
        self.addCleanup(ai_cycle.CYCLE_COST_ENTRIES.clear)
        self.addCleanup(ai_cycle.CYCLE_DENIED_CALLS.clear)
        self.addCleanup(setattr, ai_cycle, "ACTIVE_BACKEND", ai_cycle.OpenCodeBackend())
        ai_cycle.ACTIVE_BACKEND = ai_cycle.PiBackend()

    def _make_factory(self, reviews=None, sol_reviews=None):
        from tools.test_ai_cycle import PiFakeFactory, FINAL_BEGIN, FINAL_END
        return PiFakeFactory(
            reviews=reviews or [make_pass_review()],
            sol_reviews=sol_reviews or [make_pass_review()],
            fix_text=f"{FINAL_BEGIN}\ndone\nELI5\n- plain\n{FINAL_END}\n",
        )

    @mock.patch("tools.ai_cycle.changed_diff_stats", return_value=([], 0, 0))
    @mock.patch("tools.ai_cycle.run_verification")
    @mock.patch("tools.ai_cycle.candidate_fingerprint", return_value="candidate")
    @mock.patch("tools.ai_cycle.snapshot_git_state")
    def test_normal_pass(self, snap, fp, verif, diff):
        """NORMAL task reaches ACCEPTED. No escalation for ordinary change."""
        verif.return_value = make_pass_verification()
        factory = self._make_factory()

        with tempfile.TemporaryDirectory() as d, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ):
            sd = Path(d)
            plan = _plan()
            (sd / "plan.json").write_text(json.dumps(plan))
            (sd / "task.md").write_text("# task\n\ntest\n")

            result = ai_cycle.complete_candidate_workflow(
                plan=plan, plan_file=sd / "plan.json",
                task_file=sd / "task.md", session_dir=sd,
                allow_expensive=False,
            )

            self.assertEqual(0, result)
            # Verify no escalation calls
            sol = [c for c in [" ".join(x) for x in factory.calls] if "xhigh" in c]
            self.assertEqual(0, len(sol), "No escalation expected for ordinary task")

    @mock.patch("tools.ai_cycle.changed_diff_stats", return_value=([], 0, 0))
    @mock.patch("tools.ai_cycle.run_verification")
    @mock.patch("tools.ai_cycle.candidate_fingerprint", return_value="candidate")
    @mock.patch("tools.ai_cycle.snapshot_git_state")
    def test_reviewer_fix_then_pass(self, snap, fp, verif, diff):
        """FIX → repair → PASS cycle succeeds."""
        verif.return_value = make_pass_verification()
        factory = self._make_factory(reviews=[make_fix_review(), make_pass_review()])

        with tempfile.TemporaryDirectory() as d, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ):
            sd = Path(d)
            plan = _plan()
            (sd / "plan.json").write_text(json.dumps(plan))
            (sd / "task.md").write_text("# task\n\ntest\n")

            result = ai_cycle.complete_candidate_workflow(
                plan=plan, plan_file=sd / "plan.json",
                task_file=sd / "task.md", session_dir=sd,
                allow_expensive=False,
            )

            self.assertEqual(0, result)
            # At minimum, a fix artifact should exist
            self.assertTrue((sd / "review-fix-1.md").exists(),
                            "Fix artifact not created")

    @mock.patch("tools.ai_cycle.changed_diff_stats", return_value=([], 0, 0))
    @mock.patch("tools.ai_cycle.run_verification")
    @mock.patch("tools.ai_cycle.candidate_fingerprint", return_value="candidate")
    @mock.patch("tools.ai_cycle.snapshot_git_state")
    def test_reviewer_retry_exhaustion(self, snap, fp, verif, diff):
        """Two consecutive FIX verdicts → REJECTED."""
        verif.return_value = make_pass_verification()
        factory = self._make_factory(
            reviews=[make_fix_review(), make_fix_review()]
        )

        with tempfile.TemporaryDirectory() as d, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ):
            sd = Path(d)
            plan = _plan()
            (sd / "plan.json").write_text(json.dumps(plan))
            (sd / "task.md").write_text("# task\n\ntest\n")

            result = ai_cycle.complete_candidate_workflow(
                plan=plan, plan_file=sd / "plan.json",
                task_file=sd / "task.md", session_dir=sd,
                allow_expensive=False,
            )

        self.assertEqual(2, result)  # REJECTED

    @mock.patch("tools.ai_cycle.changed_diff_stats")
    @mock.patch("tools.ai_cycle.run_verification")
    @mock.patch("tools.ai_cycle.candidate_fingerprint", return_value="candidate")
    @mock.patch("tools.ai_cycle.snapshot_git_state")
    def test_high_risk_escalation(self, snap, fp, verif, diff):
        """High-risk search path → escalation reviewer called."""
        diff.return_value = (["src/search/Searcher.cpp"], 10, 1)
        verif.return_value = make_pass_verification()
        factory = self._make_factory(
            reviews=[make_pass_review()],
            sol_reviews=[make_pass_review()],
        )

        with tempfile.TemporaryDirectory() as d, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ):
            sd = Path(d)
            plan = _plan()
            plan["design"] = "search algorithm restructure"
            (sd / "plan.json").write_text(json.dumps(plan))
            (sd / "task.md").write_text("# task\n\ntest\n")

            result = ai_cycle.complete_candidate_workflow(
                plan=plan, plan_file=sd / "plan.json",
                task_file=sd / "task.md", session_dir=sd,
                allow_expensive=False,
            )

            self.assertEqual(0, result)
            sol = [c for c in [" ".join(x) for x in factory.calls] if "xhigh" in c]
            self.assertGreaterEqual(len(sol), 1, "Expected escalation review call")

    @mock.patch("tools.ai_cycle.changed_diff_stats", return_value=([], 0, 0))
    @mock.patch("tools.ai_cycle.run_verification")
    @mock.patch("tools.ai_cycle.confirm_trivial_diff", return_value=(True, []))
    @mock.patch("tools.ai_cycle.candidate_fingerprint", return_value="candidate")
    @mock.patch("tools.ai_cycle.snapshot_git_state")
    def test_trivial_fast_path(self, snap, fp, ctd, verif, diff):
        """TRIVIAL: implementer → diff check → verify → reviewer. No Pro."""
        verif.return_value = make_pass_verification()
        from tools.test_ai_cycle import PiFakeFactory, FINAL_BEGIN, FINAL_END
        factory = PiFakeFactory(
            reviews=[make_pass_review()],
            fix_text=f"{FINAL_BEGIN}\ndone\nELI5\n- fix\n{FINAL_END}\n",
        )

        with tempfile.TemporaryDirectory() as d, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ):
            sd = Path(d)
            task = "fix a typo; no behavior change"
            (sd / "task.md").write_text(f"# task\n\n{task}\n")
            plan = ai_cycle.create_trivial_plan(task)
            (sd / "plan.json").write_text(json.dumps(plan))

            result = ai_cycle.run_fast_path_workflow(
                task=task, plan=plan,
                plan_file=sd / "plan.json",
                task_file=sd / "task.md",
                session_dir=sd,
            )

        self.assertEqual(0, result)
        sol = [c for c in [" ".join(x) for x in factory.calls] if "xhigh" in c]
        self.assertEqual(0, len(sol), "No Pro escalation in trivial path")

    @mock.patch("tools.ai_cycle.changed_diff_stats", return_value=([], 0, 0))
    @mock.patch("tools.ai_cycle.snapshot_git_state")
    @mock.patch("tools.ai_cycle.confirm_trivial_diff",
                return_value=(False, ["Non-comment change"]))
    def test_trivial_nontrivial_diff(self, ctd, snap, diff):
        """Trivial candidate with non-trivial diff → NOT accepted."""
        from tools.test_ai_cycle import PiFakeFactory, FINAL_BEGIN, FINAL_END
        factory = PiFakeFactory(
            fix_text=f"{FINAL_BEGIN}\nx=2\nELI5\n- changed\n{FINAL_END}\n",
        )

        with tempfile.TemporaryDirectory() as d, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ):
            sd = Path(d)
            task = "fix a typo; no behavior change"
            (sd / "task.md").write_text(f"# task\n\n{task}\n")
            plan = ai_cycle.create_trivial_plan(task)
            (sd / "plan.json").write_text(json.dumps(plan))

            result = ai_cycle.run_fast_path_workflow(
                task=task, plan=plan,
                plan_file=sd / "plan.json",
                task_file=sd / "task.md",
                session_dir=sd,
            )

            self.assertEqual(2, result)  # NOT accepted
            self.assertTrue((sd / "diff-confirmation.json").exists())

    @mock.patch("tools.ai_cycle.changed_diff_stats", return_value=([], 0, 0))
    @mock.patch("tools.ai_cycle.run_verification")
    @mock.patch("tools.ai_cycle.candidate_fingerprint", return_value="candidate")
    @mock.patch("tools.ai_cycle.snapshot_git_state")
    def test_verification_failure(self, snap, fp, verif, diff):
        """Cheap verification failure → NOT accepted."""
        verif.return_value = {
            "required_checks_passed": False, "costs_run": ["cheap"],
            "checks": [{"name": "test", "argv": ["git", "diff"],
                        "cwd": ".", "env": {}, "required": True,
                        "cost": "cheap", "status": "FAIL",
                        "returncode": 1, "stdout": "error",
                        "duration_ms": 5}],
        }
        factory = self._make_factory()

        with tempfile.TemporaryDirectory() as d, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ):
            sd = Path(d)
            plan = _plan()
            (sd / "plan.json").write_text(json.dumps(plan))
            (sd / "task.md").write_text("# task\n\ntest\n")

            result = ai_cycle.complete_candidate_workflow(
                plan=plan, plan_file=sd / "plan.json",
                task_file=sd / "task.md", session_dir=sd,
                allow_expensive=False,
            )

            self.assertEqual(2, result)  # NOT ACCEPTED

    def test_seed_exceeds_128_rejected(self):
        check = {
            "name": "too many", "argv": ["./build/one_combat", "bestbench", "300", "256", "0"],
            "cwd": ".", "env": {}, "required": True, "cost": "expensive",
            "seed_count": 256, "timeout_seconds": 60,
        }
        plan = _plan()
        plan["verification"] = [check]
        with self.assertRaisesRegex(RuntimeError, "maximum of 128"):
            ai_cycle.validate_plan(plan)

    @mock.patch("tools.ai_cycle.git")
    def test_dirty_tree_rejected(self, git_mock):
        git_mock.return_value = " M src/main.cpp\n"
        with self.assertRaisesRegex(RuntimeError, "Tracked working-tree"):
            ai_cycle.ensure_safe_start()


# ============================================================================
# Artifact and completeness tests
# ============================================================================

class ArtifactTests(unittest.TestCase):

    def test_eli5_composition(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d)
            (sd / "plan-eli5.md").write_text("plan\n")
            (sd / "implementation-1-eli5.md").write_text("built\n")
            (sd / "review-1-eli5.md").write_text("review\n")
            from io import StringIO
            from contextlib import redirect_stdout
            out = StringIO()
            with redirect_stdout(out):
                ai_cycle.print_final_eli5(sd, accepted=True)
            self.assertIn("ACCEPTED", out.getvalue())

    def test_cost_summary(self):
        entries = [
            {"agent": "architect", "cost": 0.05},
            {"agent": "implementer", "cost": 0.03},
        ]
        summary = ai_cycle.summarize_cost_entries(entries)
        self.assertAlmostEqual(0.08, summary["total"])

    def test_all_required_files_exist(self):
        for p in [
            ".pi/extensions/sts-cycle/index.ts",
            ".pi/extensions/sts-cycle/policy.ts",
            ".pi/extensions/sts-cycle/verification.ts",
            ".pi/extensions/sts-cycle/git-state.ts",
            ".pi/extensions/sts-cycle/artifacts.ts",
            ".pi/extensions/sts-cycle/types.ts",
            ".pi/extensions/subagent/runner.ts",
            ".pi/extensions/subagent/index.ts",
        ]:
            self.assertTrue((ROOT / p).exists(), f"Missing: {p}")

    def test_legacy_unchanged(self):
        self.assertTrue((ROOT / "tools/ai_cycle.py").exists())
        self.assertTrue((ROOT / "tools/test_ai_cycle.py").exists())
        self.assertTrue((ROOT / "tools/ai_inspect.py").exists())


if __name__ == "__main__":
    unittest.main()
