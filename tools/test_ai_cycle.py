from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import ai_cycle


def plan_with(checks: list[dict]) -> dict:
    return {
        "task_interpretation": "test",
        "current_behavior": "test",
        "design": "ordinary tooling change",
        "implementation_steps": [],
        "verification": checks,
        "documentation": [],
        "acceptance_criteria": [],
        "risks": [],
    }


def check(*, cost: str, required: bool = True) -> dict:
    return {
        "name": f"{cost} check",
        "argv": ["python3", "--version"],
        "cwd": ".",
        "env": {},
        "required": required,
        "cost": cost,
        "timeout_seconds": 30,
    }


class PlanValidationTests(unittest.TestCase):
    def seed_plan(self, seed_count: int) -> dict:
        sweep = {
            "name": "seed sweep",
            "argv": [
                "./build/one_combat",
                "bestbench",
                "300",
                str(seed_count),
                "0",
            ],
            "cwd": ".",
            "env": {"STS_FAIR": "1"},
            "required": True,
            "cost": "expensive",
            "seed_count": seed_count,
            "timeout_seconds": 60,
        }
        return plan_with([sweep])

    def test_seed_count_129_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "maximum of 128"):
            ai_cycle.validate_plan(self.seed_plan(129))

    def test_seed_count_128_is_accepted(self) -> None:
        ai_cycle.validate_plan(self.seed_plan(128))

    def test_known_generator_must_declare_seed_count(self) -> None:
        generator = check(cost="expensive")
        generator["argv"] = ["./build/one_combat", "fairgen", "64", "300", "0"]
        with self.assertRaisesRegex(RuntimeError, "must declare seed_count"):
            ai_cycle.validate_plan(plan_with([generator]))

    def test_known_python_wrapper_enforces_seed_cap(self) -> None:
        replay = check(cost="expensive")
        replay["argv"] = ["python3", "check_replay.py", "300", "129", "0"]
        replay["seed_count"] = 129
        with self.assertRaisesRegex(RuntimeError, "maximum of 128"):
            ai_cycle.validate_plan(plan_with([replay]))


class VerificationPhaseTests(unittest.TestCase):
    @mock.patch("tools.ai_cycle.subprocess.run")
    def test_cheap_phase_ignores_expensive_required_check(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            ["python3", "--version"], 0, "Python test\n"
        )
        result = ai_cycle.run_verification(
            plan_with([check(cost="cheap"), check(cost="expensive")]),
            costs_to_run={"cheap"},
        )

        self.assertTrue(result["required_checks_passed"])
        self.assertEqual(1, run_mock.call_count)
        self.assertEqual("PASS", result["checks"][0]["status"])
        self.assertEqual("NOT_RUN_THIS_PHASE", result["checks"][1]["status"])

    @mock.patch("tools.ai_cycle.subprocess.run")
    def test_expensive_check_does_not_execute_in_cheap_phase(self, run_mock) -> None:
        result = ai_cycle.run_verification(
            plan_with([check(cost="expensive")]),
            costs_to_run={"cheap"},
        )

        run_mock.assert_not_called()
        self.assertTrue(result["required_checks_passed"])

    def test_iterative_cycle_requests_only_cheap_cost(self) -> None:
        report = {"required_checks_passed": True, "checks": []}
        with tempfile.TemporaryDirectory() as raw_dir, mock.patch(
            "tools.ai_cycle.run_verification", return_value=report.copy()
        ) as run_mock, mock.patch(
            "tools.ai_cycle.candidate_fingerprint", return_value="candidate"
        ):
            ok, _ = ai_cycle.run_verification_cycle(
                plan=plan_with([]),
                plan_file=Path(raw_dir) / "plan.json",
                task_file=Path(raw_dir) / "task.md",
                session_dir=Path(raw_dir),
                phase="test",
            )

        self.assertTrue(ok)
        run_mock.assert_called_once_with(plan_with([]), costs_to_run={"cheap"})


class EscalationTests(unittest.TestCase):
    def escalate(self, **overrides):
        arguments = {
            "changed_paths": ["README.md"],
            "changed_lines": 2,
            "tracked_file_count": 1,
            "plan": plan_with([]),
            "verification_history": [],
            "luna_reviews": [],
            "latest_luna_review": {
                "verdict": "PASS",
                "summary": "ok",
                "eli5_summary": "Checked it; it passed; final checks are next.",
                "uncertainty": "LOW",
                "issues": [],
            },
        }
        arguments.update(overrides)
        return ai_cycle.should_escalate_to_sol(**arguments)

    def test_high_risk_search_path_escalates(self) -> None:
        escalated, reasons = self.escalate(changed_paths=["src/search/Searcher.cpp"])
        self.assertTrue(escalated)
        self.assertIn("high-risk subsystem changed: search", reasons)

    def test_trivial_documentation_diff_does_not_escalate(self) -> None:
        escalated, reasons = self.escalate(
            changed_paths=["docs/typo.md"], changed_lines=1
        )
        self.assertFalse(escalated)
        self.assertEqual([], reasons)

    def test_high_reviewer_uncertainty_escalates(self) -> None:
        review = {
            "verdict": "PASS",
            "summary": "ok",
            "eli5_summary": "Checked it; it passed; Sol checks uncertainty next.",
            "uncertainty": "HIGH",
            "issues": [],
        }
        escalated, reasons = self.escalate(latest_luna_review=review)
        self.assertTrue(escalated)
        self.assertIn("Luna reviewer uncertainty is HIGH", reasons)


class ReviewAndResumeTests(unittest.TestCase):
    def test_eli5_review_fields_validate(self) -> None:
        review = {
            "verdict": "PASS",
            "summary": "Technical checks passed.",
            "eli5_summary": "I checked the change. It passed. Final checks run next.",
            "uncertainty": "LOW",
            "issues": [],
        }
        ai_cycle.validate_review(review)
        for missing in ("eli5_summary", "uncertainty"):
            broken = review.copy()
            del broken[missing]
            with self.assertRaises(RuntimeError):
                ai_cycle.validate_review(broken)

    def test_pass_cannot_contain_blocking_issue(self) -> None:
        review = {
            "verdict": "PASS",
            "summary": "Inconsistent pass.",
            "eli5_summary": "I found a serious issue, so this should not pass.",
            "uncertainty": "LOW",
            "issues": [
                {
                    "severity": "MAJOR",
                    "location": "src/example.cpp:1",
                    "problem": "Broken behavior.",
                    "failure_mechanism": "The requested behavior does not run.",
                    "required_fix": "Implement it.",
                }
            ],
        }
        with self.assertRaisesRegex(RuntimeError, "PASS with a CRITICAL or MAJOR"):
            ai_cycle.validate_review(review)

    def test_existing_plan_resume_does_not_need_architect_log(self) -> None:
        plan = plan_with([check(cost="cheap")])
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            plan_file = session_dir / "plan.json"
            plan_file.write_text(json.dumps(plan), encoding="utf-8")

            with mock.patch(
                "tools.ai_cycle.parse_json_response",
                side_effect=AssertionError("architect recovery should not run"),
            ):
                recovered, recovered_path = ai_cycle.recover_or_load_plan(session_dir)

        self.assertEqual(plan, recovered)
        self.assertEqual(plan_file, recovered_path)

    def test_resume_upgrades_known_legacy_seed_sweep(self) -> None:
        sweep = {
            "name": "legacy sweep",
            "argv": ["./build/one_combat", "bestbench", "300", "32", "0"],
            "cwd": ".",
            "env": {},
            "required": False,
            "cost": "expensive",
            "timeout_seconds": 60,
        }
        plan = plan_with([sweep])
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            plan_file = session_dir / "plan.json"
            plan_file.write_text(json.dumps(plan), encoding="utf-8")
            recovered, _ = ai_cycle.recover_or_load_plan(session_dir)

        self.assertEqual(32, recovered["verification"][0]["seed_count"])


if __name__ == "__main__":
    unittest.main()
