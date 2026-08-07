from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
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


def review_data(verdict: str = "PASS") -> dict:
    issues = []
    if verdict == "FIX":
        issues = [
            {
                "severity": "MAJOR",
                "location": "src/example.cpp:1",
                "problem": "Behavior is wrong.",
                "failure_mechanism": "The requested path does not run.",
                "required_fix": "Wire the requested path.",
            }
        ]
    return {
        "verdict": verdict,
        "summary": "Technical assessment.",
        "eli5_summary": "I checked it. A real issue remains. Sol decides next.",
        "uncertainty": "MEDIUM",
        "issues": issues,
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

    def test_legacy_over_cap_sweep_resumes_without_seed_count(self) -> None:
        sweep = {
            "name": "legacy 256-seed gate",
            "argv": ["./build/one_combat", "bestbench", "1000", "256", "0", "126700"],
            "cwd": ".",
            "env": {},
            "required": True,
            "cost": "expensive",
            "timeout_seconds": 7200,
        }
        plan = plan_with([sweep])
        with self.assertRaisesRegex(RuntimeError, "must declare seed_count"):
            ai_cycle.validate_plan(plan)

        self.assertFalse(ai_cycle.upgrade_legacy_seed_counts(plan))
        self.assertIsNone(plan["verification"][0].get("seed_count"))
        ai_cycle.validate_plan(plan, allow_legacy_sweeps=True)


class RejectedRecoveryTests(unittest.TestCase):
    def make_rejected_session(self, session_dir: Path) -> tuple[Path, dict]:
        data = review_data("FIX")
        review_file = session_dir / "review-2.json"
        review_file.write_text(json.dumps(data), encoding="utf-8")
        return review_file, data

    def test_round_limit_stops_before_another_fix(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            review_file, data = self.make_rejected_session(session_dir)
            data["candidate_fingerprint"] = "candidate"
            review_file.write_text(json.dumps(data), encoding="utf-8")
            with mock.patch(
                "tools.ai_cycle.candidate_fingerprint", return_value="candidate"
            ), mock.patch(
                "tools.ai_cycle.matching_successful_verification",
                return_value=session_dir / "cheap-verification-1.json",
            ), mock.patch(
                "tools.ai_cycle.reject_after_semantic_limit", return_value=2
            ) as reject_mock, mock.patch(
                "tools.ai_cycle.fix_review"
            ) as fix_mock:
                result = ai_cycle.complete_candidate_workflow(
                    plan=plan_with([]),
                    plan_file=session_dir / "plan.json",
                    task_file=session_dir / "task.md",
                    session_dir=session_dir,
                    allow_expensive=False,
                )

        self.assertEqual(2, result)
        reject_mock.assert_called_once()
        fix_mock.assert_not_called()

    def test_recovery_cheap_check_never_auto_repairs(self) -> None:
        report = {"required_checks_passed": False, "checks": []}
        with tempfile.TemporaryDirectory() as raw_dir, mock.patch(
            "tools.ai_cycle.matching_successful_verification", return_value=None
        ), mock.patch(
            "tools.ai_cycle.run_verification", return_value=report.copy()
        ) as run_mock, mock.patch(
            "tools.ai_cycle.run_verification_cycle"
        ) as cycle_mock, mock.patch(
            "tools.ai_cycle.candidate_fingerprint", return_value="candidate"
        ):
            ok, report_file, _ = ai_cycle.ensure_cheap_candidate_verification(
                plan=plan_with([]),
                plan_file=Path(raw_dir) / "plan.json",
                task_file=Path(raw_dir) / "task.md",
                session_dir=Path(raw_dir),
                phase="recovery-cheap",
            )

        self.assertFalse(ok)
        self.assertEqual("recovery-cheap-verification-1.json", report_file.name)
        run_mock.assert_called_once_with(plan_with([]), costs_to_run={"cheap"})
        cycle_mock.assert_not_called()

    def test_failed_recovery_check_is_reused_without_rerun(self) -> None:
        report = {
            "required_checks_passed": False,
            "costs_run": ["cheap"],
            "candidate_fingerprint": "candidate",
            "checks": [],
        }
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            report_file = session_dir / "recovery-cheap-verification-1.json"
            report_file.write_text(json.dumps(report), encoding="utf-8")
            with mock.patch(
                "tools.ai_cycle.candidate_fingerprint", return_value="candidate"
            ), mock.patch("tools.ai_cycle.run_verification") as run_mock:
                ok, reused_file, _ = ai_cycle.ensure_cheap_candidate_verification(
                    plan=plan_with([]),
                    plan_file=session_dir / "plan.json",
                    task_file=session_dir / "task.md",
                    session_dir=session_dir,
                    phase="recovery-cheap",
                )

        self.assertFalse(ok)
        self.assertEqual(report_file, reused_file)
        run_mock.assert_not_called()

    def test_rejection_prints_eli5_and_recovery_command(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            review_file, data = self.make_rejected_session(session_dir)
            output = StringIO()
            with redirect_stdout(output):
                result = ai_cycle.reject_after_semantic_limit(
                    session_dir=session_dir,
                    review_round=2,
                    review_file=review_file,
                    review_data=data,
                    fingerprint="candidate",
                    allow_expensive=True,
                )

            text = output.getvalue()
            self.assertEqual(2, result)
            self.assertIn("ELI5:", text)
            self.assertIn("--continue-rejected", text)
            self.assertIn("--allow-expensive", text)
            self.assertIn("will NOT be regenerated", text)
            self.assertTrue((session_dir / "semantic-rejection.json").exists())

            with redirect_stdout(StringIO()):
                ai_cycle.reject_after_semantic_limit(
                    session_dir=session_dir,
                    review_round=2,
                    review_file=review_file,
                    review_data=data,
                    fingerprint="candidate",
                    allow_expensive=False,
                )
            rejection = json.loads(
                (session_dir / "semantic-rejection.json").read_text(encoding="utf-8")
            )
            self.assertTrue(rejection["allow_expensive"])

    def test_sol_adjudication_pass_skips_architect_and_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            self.make_rejected_session(session_dir)
            adjudication_file = session_dir / "recovery-adjudication.json"
            adjudication_file.write_text("{}", encoding="utf-8")
            with mock.patch(
                "tools.ai_cycle.candidate_fingerprint", return_value="candidate"
            ), mock.patch(
                "tools.ai_cycle.ensure_cheap_candidate_verification",
                return_value=(True, session_dir / "cheap.json", "candidate"),
            ), mock.patch(
                "tools.ai_cycle.obtain_review",
                return_value=(adjudication_file, review_data("PASS")),
            ) as obtain_mock, mock.patch(
                "tools.ai_cycle.run_recovery_final_gate",
                return_value=(True, session_dir / "final.json"),
            ), mock.patch(
                "tools.ai_cycle.finish_accepted", return_value=0
            ), mock.patch(
                "tools.ai_cycle.run_agent"
            ) as agent_mock:
                result = ai_cycle.continue_rejected_workflow(
                    plan=plan_with([]),
                    plan_file=session_dir / "plan.json",
                    task_file=session_dir / "task.md",
                    session_dir=session_dir,
                    allow_expensive=False,
                )

        self.assertEqual(0, result)
        self.assertEqual("recovery-adjudication", obtain_mock.call_args.kwargs["artifact_stem"])
        agent_mock.assert_not_called()

    def test_sol_fix_uses_one_fix_then_final_audit(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            self.make_rejected_session(session_dir)
            files = [
                session_dir / "recovery-adjudication.json",
                session_dir / "recovery-review.json",
                session_dir / "recovery-sol-review.json",
            ]
            reviews = [review_data("FIX"), review_data("PASS"), review_data("FIX")]
            with mock.patch(
                "tools.ai_cycle.candidate_fingerprint", return_value="candidate"
            ), mock.patch(
                "tools.ai_cycle.ensure_cheap_candidate_verification",
                side_effect=[
                    (True, session_dir / "cheap-1.json", "candidate"),
                    (True, session_dir / "cheap-2.json", "candidate"),
                ],
            ), mock.patch(
                "tools.ai_cycle.obtain_review",
                side_effect=list(zip(files, reviews)),
            ) as obtain_mock, mock.patch(
                "tools.ai_cycle.fix_review",
                return_value="FINAL_RESPONSE_BEGIN\nfixed\nFINAL_RESPONSE_END\n",
            ) as fix_mock, mock.patch(
                "tools.ai_cycle.snapshot_git_state"
            ):
                result = ai_cycle.continue_rejected_workflow(
                    plan=plan_with([]),
                    plan_file=session_dir / "plan.json",
                    task_file=session_dir / "task.md",
                    session_dir=session_dir,
                    allow_expensive=False,
                )

            self.assertEqual(2, result)
            self.assertEqual(1, fix_mock.call_count)
            self.assertEqual(3, obtain_mock.call_count)
            self.assertTrue((session_dir / "recovery-exhausted.json").exists())

    def test_interrupted_fix_marker_prevents_second_deepseek_fix(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            self.make_rejected_session(session_dir)
            (session_dir / "recovery-fix-1-source.json").write_text(
                json.dumps({"source": "recovery-adjudication.json"}),
                encoding="utf-8",
            )
            reviews = [review_data("PASS"), review_data("FIX")]
            files = [
                session_dir / "recovery-review.json",
                session_dir / "recovery-sol-review.json",
            ]
            with mock.patch(
                "tools.ai_cycle.candidate_fingerprint", return_value="candidate"
            ), mock.patch(
                "tools.ai_cycle.ensure_cheap_candidate_verification",
                return_value=(True, session_dir / "cheap.json", "candidate"),
            ), mock.patch(
                "tools.ai_cycle.obtain_review", side_effect=list(zip(files, reviews))
            ), mock.patch("tools.ai_cycle.fix_review") as fix_mock, mock.patch(
                "tools.ai_cycle.fix_verification"
            ) as verification_fix_mock:
                result = ai_cycle.continue_rejected_workflow(
                    plan=plan_with([]),
                    plan_file=session_dir / "plan.json",
                    task_file=session_dir / "task.md",
                    session_dir=session_dir,
                    allow_expensive=False,
                )

        self.assertEqual(2, result)
        fix_mock.assert_not_called()
        verification_fix_mock.assert_not_called()

    def test_final_sol_fix_eli5_is_normalized(self) -> None:
        data = review_data("FIX")
        data["eli5_summary"] = "The implementer will fix this automatically next."
        ai_cycle.normalize_recovery_final_eli5(data)
        self.assertIn("exhausted", data["eli5_summary"])
        self.assertIn("manual intervention", data["eli5_summary"])

    def test_incomplete_paid_recovery_review_is_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            (session_dir / "recovery-adjudication-candidate.json").write_text(
                json.dumps({"candidate_fingerprint": "candidate"}),
                encoding="utf-8",
            )
            (session_dir / "recovery-adjudication.log").write_text(
                "incomplete output", encoding="utf-8"
            )
            with mock.patch("tools.ai_cycle.review") as review_mock:
                with self.assertRaises(ai_cycle.RejectedRecoveryExhausted):
                    ai_cycle.obtain_review(
                        session_dir=session_dir,
                        plan_file=session_dir / "plan.json",
                        task_file=session_dir / "task.md",
                        verification_file=session_dir / "cheap.json",
                        fingerprint="candidate",
                        round_number=1,
                        sol=True,
                        artifact_stem="recovery-adjudication",
                        single_attempt=True,
                    )

            review_mock.assert_not_called()
            self.assertTrue((session_dir / "recovery-exhausted.json").exists())


if __name__ == "__main__":
    unittest.main()
