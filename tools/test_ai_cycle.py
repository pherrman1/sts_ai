from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from tools import ai_cycle


FINAL_BEGIN = ai_cycle.FINAL_RESPONSE_BEGIN
FINAL_END = ai_cycle.FINAL_RESPONSE_END


def plan_with(checks: list[dict]) -> dict:    return {
        "task_interpretation": "test",
        "current_behavior": "test",
        "design": "ordinary tooling change",
        "eli5_summary": "It changes a tool so its messages are easier to read.",
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
        self.assertIn("reviewer uncertainty is HIGH", reasons)


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

    def test_plan_without_eli5_is_rejected(self) -> None:
        plan = plan_with([check(cost="cheap")])
        del plan["eli5_summary"]
        with self.assertRaisesRegex(RuntimeError, "missing keys"):
            ai_cycle.validate_plan(plan)

    def test_plan_with_blank_eli5_is_rejected(self) -> None:
        plan = plan_with([check(cost="cheap")])
        plan["eli5_summary"] = "   "
        with self.assertRaisesRegex(RuntimeError, "eli5_summary"):
            ai_cycle.validate_plan(plan)

    def test_upgrade_legacy_eli5_fills_placeholder(self) -> None:
        plan = plan_with([check(cost="cheap")])
        del plan["eli5_summary"]
        ai_cycle.upgrade_legacy_eli5(plan)
        self.assertIn("Legacy plan", plan["eli5_summary"])
        ai_cycle.validate_plan(plan, allow_legacy_sweeps=True)

    def test_upgrade_legacy_eli5_keeps_existing(self) -> None:
        plan = plan_with([check(cost="cheap")])
        ai_cycle.upgrade_legacy_eli5(plan)
        self.assertEqual(
            "It changes a tool so its messages are easier to read.",
            plan["eli5_summary"],
        )


class Eli5ArtifactTests(unittest.TestCase):
    def test_extract_eli5_section(self) -> None:
        md = (
            "IMPLEMENTATION SUMMARY\n- change\n\n"
            "ELI5\n- simple words\n- plain language\n\n"
            "FILES CHANGED\n- x\n"
        )
        self.assertEqual("simple words\nplain language", ai_cycle.extract_eli5_section(md))

    def test_extract_eli5_section_missing(self) -> None:
        md = "IMPLEMENTATION SUMMARY\n- change\n"
        self.assertEqual("", ai_cycle.extract_eli5_section(md))

    def test_extract_eli5_section_heading_variants(self) -> None:
        for heading in ("ELI5", "## ELI5", "ELI5:"):
            md = f"summary\n\n{heading}\n- explained\n"
            self.assertEqual("explained", ai_cycle.extract_eli5_section(md))

    def test_save_summary_with_eli5_writes_pair(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            transcript = (
                f"noise\n{FINAL_BEGIN}\nsummary text\nELI5\n- the plain version\n"
                f"{FINAL_END}\n"
            )
            summary_file = session_dir / "implementation-1.md"
            output = StringIO()
            with redirect_stdout(output):
                text = ai_cycle.save_summary_with_eli5(summary_file, transcript)
            self.assertEqual("summary text\nELI5\n- the plain version\n", text)
            self.assertEqual(
                "the plain version\n",
                (session_dir / "implementation-1-eli5.md").read_text(encoding="utf-8"),
            )
            self.assertIn("ELI5 (implementer)", output.getvalue())

    def test_save_summary_with_eli5_missing_section(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            transcript = f"noise\n{FINAL_BEGIN}\nsummary only\n{FINAL_END}\n"
            with redirect_stdout(StringIO()):
                ai_cycle.save_summary_with_eli5(
                    session_dir / "implementation-1.md", transcript
                )
            self.assertEqual(
                "No ELI5 section was recorded in the implementer response.\n",
                (session_dir / "implementation-1-eli5.md").read_text(encoding="utf-8"),
            )

    def test_final_eli5_composes_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            (session_dir / "plan-eli5.md").write_text(
                "plan explanation\n", encoding="utf-8"
            )
            (session_dir / "implementation-1-eli5.md").write_text(
                "built explanation\n", encoding="utf-8"
            )
            (session_dir / "review-1-eli5.md").write_text(
                "review explanation\n", encoding="utf-8"
            )
            output = StringIO()
            with redirect_stdout(output):
                ai_cycle.print_final_eli5(session_dir, accepted=True)
            text = output.getvalue()
            self.assertIn("What we wanted:", text)
            self.assertIn("plan explanation", text)
            self.assertIn("What was built:", text)
            self.assertIn("built explanation", text)
            self.assertIn("What the reviewer found:", text)
            self.assertIn("review explanation", text)
            self.assertIn("Verdict: ACCEPTED", text)
            self.assertIn("What to do next", text)

    def test_final_eli5_composes_rejected_without_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            output = StringIO()
            with redirect_stdout(output):
                ai_cycle.print_final_eli5(session_dir, accepted=False)
            text = output.getvalue()
            self.assertIn("Verdict: NOT ACCEPTED", text)
            self.assertIn("--continue-rejected", text)


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

    def test_retry_recovery_clears_only_incomplete_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            (session_dir / "recovery-exhausted.json").write_text("{}", encoding="utf-8")
            (session_dir / "recovery-review-candidate.json").write_text(
                "{}", encoding="utf-8"
            )
            (session_dir / "recovery-review.log").write_text("", encoding="utf-8")
            (session_dir / "recovery-sol-review-candidate.json").write_text(
                "{}", encoding="utf-8"
            )
            (session_dir / "recovery-sol-review.log").write_text("", encoding="utf-8")
            completed = session_dir / "recovery-adjudication.json"
            completed.write_text("{}", encoding="utf-8")
            (session_dir / "recovery-adjudication-candidate.json").write_text(
                "{}", encoding="utf-8"
            )
            (session_dir / "recovery-adjudication.log").write_text(
                "complete", encoding="utf-8"
            )
            (session_dir / "recovery-fix-1.md").write_text("done", encoding="utf-8")
            (session_dir / "recovery-fix-1-source.json").write_text(
                "{}", encoding="utf-8"
            )

            cleared = ai_cycle.reset_incomplete_recovery(session_dir)

            self.assertIn("recovery-exhausted.json", cleared)
            self.assertIn("recovery-review-candidate.json", cleared)
            self.assertIn("recovery-review.log", cleared)
            self.assertIn("recovery-sol-review-candidate.json", cleared)
            self.assertIn("recovery-sol-review.log", cleared)
            self.assertFalse((session_dir / "recovery-exhausted.json").exists())
            self.assertFalse((session_dir / "recovery-review-candidate.json").exists())
            self.assertFalse((session_dir / "recovery-sol-review.log").exists())
            self.assertTrue(completed.exists())
            self.assertTrue((session_dir / "recovery-adjudication-candidate.json").exists())
            self.assertTrue((session_dir / "recovery-fix-1.md").exists())
            self.assertTrue((session_dir / "recovery-fix-1-source.json").exists())

    def test_retry_recovery_clears_interrupted_fix_marker(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            (session_dir / "recovery-fix-1-source.json").write_text(
                "{}", encoding="utf-8"
            )
            (session_dir / "recovery-fix-1.log").write_text("", encoding="utf-8")

            cleared = ai_cycle.reset_incomplete_recovery(session_dir)

            self.assertFalse((session_dir / "recovery-fix-1-source.json").exists())
            self.assertFalse((session_dir / "recovery-fix-1.log").exists())
            self.assertIn("recovery-fix-1-source.json", cleared)


class CostTrackingTests(unittest.TestCase):
    def test_summarize_cost_entries_aggregates_per_agent(self) -> None:
        entries = [
            {"agent": "reviewer", "cost": 0.01},
            {"agent": "reviewer", "cost": 0.02},
            {"agent": "implementer", "cost": 0.05},
            {"agent": "reviewer_escalation", "cost": 0.03},
        ]
        summary = ai_cycle.summarize_cost_entries(entries)
        self.assertAlmostEqual(0.03, summary["per_agent"]["reviewer"])
        self.assertAlmostEqual(0.05, summary["per_agent"]["implementer"])
        self.assertAlmostEqual(0.03, summary["per_agent"]["reviewer_escalation"])
        self.assertAlmostEqual(0.11, summary["total"])

    def test_summarize_cost_entries_handles_missing_cost(self) -> None:
        summary = ai_cycle.summarize_cost_entries(
            [{"agent": "reviewer", "cost": None}, {"agent": "architect"}]
        )
        self.assertAlmostEqual(0.0, summary["total"])

    def test_append_cost_entries_accumulates(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            ai_cycle.append_cost_entries(
                session_dir, [{"agent": "reviewer", "cost": 0.01}]
            )
            ai_cycle.append_cost_entries(
                session_dir, [{"agent": "reviewer_escalation", "cost": 0.03}]
            )
            loaded = json.loads(
                (session_dir / "costs.json").read_text(encoding="utf-8")
            )
            self.assertEqual(2, len(loaded["entries"]))
            self.assertEqual(0.01, loaded["entries"][0]["cost"])
            self.assertEqual(0.03, loaded["entries"][1]["cost"])


    def test_review_prompt_includes_orchestrator_changed_files(self) -> None:
        review = review_data("PASS")
        with tempfile.TemporaryDirectory() as raw_dir, mock.patch(
            "tools.ai_cycle.changed_diff_stats",
            return_value=(["src/foo.cpp", "tools/ai_cycle.py"], 10, 2),
        ), mock.patch(
            "tools.ai_cycle.run_agent", return_value=json.dumps(review)
        ) as agent_mock:
            ai_cycle.review(
                Path(raw_dir) / "plan.json",
                Path(raw_dir) / "task.md",
                Path(raw_dir) / "verification.json",
                log_file=Path(raw_dir) / "review-1.log",
            )
        prompt = agent_mock.call_args.args[1]
        self.assertIn("Orchestrator-provided changed files", prompt)
        self.assertIn("- src/foo.cpp", prompt)
        self.assertIn("- tools/ai_cycle.py", prompt)


class DeniedCallAndRecoveryTests(unittest.TestCase):
    def test_extract_denied_tool_calls(self) -> None:
        lines = [
            "→ Read src/foo.cpp",
            "\u2717 python3 -c \"import os\" failed",
            "Error: The user has specified a rule which prevents you from using "
            "this specific tool call. Here are some of the relevant rules [...]",
            "\u2717 git diff HEAD -- apps/one_combat.cpp | grep -n isfinite  failed",
            "Error: The user has specified a rule which prevents you from using "
            "this specific tool call. Here are some of the relevant rules [...]",
            "→ Read src/bar.cpp",
        ]
        calls = ai_cycle.extract_denied_tool_calls(lines)
        self.assertEqual(2, len(calls))
        self.assertIn("python3 -c", calls[0])
        self.assertIn("| grep", calls[1])

    def test_denied_calls_ignored_without_failed_marker(self) -> None:
        lines = [
            "Error: The user has specified a rule which prevents you from using "
            "this specific tool call.",
        ]
        self.assertEqual([], ai_cycle.extract_denied_tool_calls(lines))

    def test_append_denied_tool_calls_accumulates_per_agent(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            ai_cycle.append_denied_tool_calls(
                session_dir, "reviewer", ["python3 -c x"], "2026-08-07 10:00:00"
            )
            ai_cycle.append_denied_tool_calls(
                session_dir, "reviewer_escalation", ["git diff | grep"], "2026-08-07 11:00:00"
            )
            text = (session_dir / "denied-tool-calls.md").read_text(encoding="utf-8")
            self.assertIn("## reviewer", text)
            self.assertIn("## reviewer_escalation", text)
            self.assertIn("python3 -c x", text)
            self.assertIn("git diff | grep", text)

    def test_parse_json_response_accepts_fenced_json(self) -> None:
        text = (
            "Some tool output\n"
            "```json\n"
            '{"verdict": "PASS", "summary": "ok", '
            '"eli5_summary": "fine", "uncertainty": "LOW", "issues": []}\n'
            "```\n"
        )
        data = ai_cycle.parse_json_response(text, source="test")
        self.assertEqual("PASS", data["verdict"])

    def test_failed_run_review_recovered_from_log(self) -> None:
        review = review_data("PASS")
        review_text = "```json\n" + json.dumps(review) + "\n```\n"
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            log_file = session_dir / "recovery-sol-review.log"
            log_file.write_text(review_text, encoding="utf-8")
            with mock.patch(
                "tools.ai_cycle.review",
                side_effect=RuntimeError("opencode run exited 1"),
            ):
                path, data = ai_cycle.obtain_review(
                    session_dir=session_dir,
                    plan_file=session_dir / "plan.json",
                    task_file=session_dir / "task.md",
                    verification_file=session_dir / "cheap.json",
                    fingerprint="candidate",
                    round_number=1,
                    sol=True,
                    artifact_stem="recovery-sol-review",
                    single_attempt=True,
                )

            self.assertEqual("PASS", data["verdict"])
            self.assertTrue((session_dir / "recovery-sol-review.json").exists())
            self.assertFalse((session_dir / "recovery-exhausted.json").exists())

    def test_matching_marker_without_log_exhausts(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            (session_dir / "recovery-review-candidate.json").write_text(
                json.dumps({"candidate_fingerprint": "candidate"}),
                encoding="utf-8",
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
                        artifact_stem="recovery-review",
                        single_attempt=True,
                    )
            review_mock.assert_not_called()
            self.assertTrue((session_dir / "recovery-exhausted.json").exists())

    def test_stale_marker_triggers_fresh_call_not_exhaustion(self) -> None:
        review = review_data("PASS")
        with tempfile.TemporaryDirectory() as raw_dir:
            session_dir = Path(raw_dir)
            (session_dir / "recovery-review-candidate.json").write_text(
                json.dumps({"candidate_fingerprint": "old-candidate"}),
                encoding="utf-8",
            )
            with mock.patch(
                "tools.ai_cycle.review", return_value=review
            ) as review_mock:
                _, data = ai_cycle.obtain_review(
                    session_dir=session_dir,
                    plan_file=session_dir / "plan.json",
                    task_file=session_dir / "task.md",
                    verification_file=session_dir / "cheap.json",
                    fingerprint="new-candidate",
                    round_number=1,
                    artifact_stem="recovery-review",
                    single_attempt=True,
                )
            review_mock.assert_called_once()
            self.assertEqual("PASS", data["verdict"])
            self.assertFalse((session_dir / "recovery-exhausted.json").exists())
            marker = json.loads(
                (session_dir / "recovery-review-candidate.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("new-candidate", marker["candidate_fingerprint"])


def assistant_message_end(text: str, **overrides) -> dict:
    message = {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": "deepseek/deepseek-v4-flash:high",
        "stopReason": "stop",
        "usage": {
            "input": 10,
            "output": 5,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 15,
            "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0,
                     "cacheWrite": 0.0, "total": 0.001},
        },
    }
    message.update(overrides)
    return {"type": "message_end", "message": message}


def jsonl_lines(events: list[dict]) -> list[str]:
    return [json.dumps(event) + "\n" for event in events]


class FakeProcess:
    """Minimal subprocess.Popen stand-in for Pi/OpenCode child processes."""

    def __init__(
        self,
        *,
        stdout_lines: list[str],
        returncode: int = 0,
        stderr_lines: list[str] | None = None,
        timed_out: bool = False,
    ):
        self.stdout = iter(stdout_lines)
        self.stderr = iter(stderr_lines or [])
        self.returncode = returncode
        self._timed_out = timed_out
        self.terminated = False
        self.killed = False

    def wait(self, timeout=None):
        if self._timed_out and not self.terminated:
            raise subprocess.TimeoutExpired(["pi"], timeout)
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class PiFakeFactory:
    """Produces FakeProcess responses keyed on the Pi argv of each call.

    Roles are distinguished by model flag and the presence of --tools:
    - reviewer_escalation: deepseek/deepseek-v4-pro:xhigh
    - reviewer: --model deepseek/deepseek-v4-flash:high with --tools
    - implementer: --model deepseek/deepseek-v4-flash:high without --tools
    """

    def __init__(self, reviews=None, sol_reviews=None, fix_text=None):
        self.review_iter = iter(reviews or [])
        self.sol_iter = iter(sol_reviews or [])
        self.fix_text = fix_text or (
            f"{FINAL_BEGIN}\nfixed\nELI5\n- plain summary\n{FINAL_END}\n"
        )
        self.calls: list[list[str]] = []
        self.real_popen = subprocess.Popen

    def __call__(self, cmd, **kwargs):
        if not cmd or cmd[0] != "pi":
            if cmd and cmd[0] in {
                "python3", "python", "git", "cmake", "ctest", "pytest",
            }:
                return self.real_popen(cmd, **kwargs)
            raise AssertionError(
                f"unexpected real command through Popen mock: {cmd}"
            )
        self.calls.append(cmd)
        joined = " ".join(cmd)
        if "--model deepseek/deepseek-v4-pro:xhigh" in joined:
            data = next(self.sol_iter)
        elif "--tools" in joined:
            data = next(self.review_iter)
        else:
            return FakeProcess(
                stdout_lines=jsonl_lines(
                    [assistant_message_end(self.fix_text)]
                )
            )
        return FakeProcess(
            stdout_lines=jsonl_lines([assistant_message_end(json.dumps(data))])
        )


def write_pi_session_files(session_dir: Path) -> tuple[Path, Path]:
    plan_file = session_dir / "plan.json"
    task_file = session_dir / "task.md"
    plan_file.write_text(
        json.dumps(plan_with([check(cost="cheap")])), encoding="utf-8"
    )
    task_file.write_text("# User task\n\ntest\n", encoding="utf-8")
    return plan_file, task_file


class PiBackendUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(ai_cycle.CYCLE_COST_ENTRIES.clear)
        self.addCleanup(ai_cycle.CYCLE_DENIED_CALLS.clear)
        self.addCleanup(setattr, ai_cycle, "ACTIVE_BACKEND",
                        ai_cycle.OpenCodeBackend())

    def invoke(
        self,
        agent: str = "architect",
        prompt: str = "plan",
        *,
        files: list | None = None,
        log_file: Path | None = None,
        timeout_seconds: float | None = None,
        process: FakeProcess | None = None,
    ):
        backend = ai_cycle.PiBackend()
        return backend.invoke(
            agent=agent,
            prompt=prompt,
            files=files,
            log_file=log_file,
            timeout_seconds=timeout_seconds,
        )

    def test_backend_selection(self) -> None:
        self.assertIsInstance(ai_cycle.select_backend("opencode"),
                              ai_cycle.OpenCodeBackend)
        self.assertIsInstance(ai_cycle.select_backend("pi"),
                              ai_cycle.PiBackend)
        with self.assertRaises(ValueError):
            ai_cycle.select_backend("other")
        self.assertIsInstance(ai_cycle.ACTIVE_BACKEND,
                              ai_cycle.OpenCodeBackend)

    def test_run_agent_dispatches_to_active_backend(self) -> None:
        invoked = {}

        class StubBackend(ai_cycle.AgentBackend):
            def invoke(self, **kwargs) -> str:
                invoked.update(kwargs)
                return "answer"

        ai_cycle.ACTIVE_BACKEND = StubBackend()
        result = ai_cycle.run_agent(
            "reviewer", "prompt", files=[], log_file=None
        )
        self.assertEqual("answer", result)
        self.assertEqual("reviewer", invoked["agent"])
        self.assertEqual("prompt", invoked["prompt"])
        self.assertIsNone(invoked["timeout_seconds"])

    def test_pi_argv_construction_per_role(self) -> None:
        cases = [
            (
                "architect",
                "deepseek/deepseek-v4-pro:high",
                "read,grep,find,ls,sts_git,sts_inspect",
            ),
            (
                "reviewer",
                "deepseek/deepseek-v4-flash:high",
                "read,grep,find,ls,sts_git,sts_inspect",
            ),
            (
                "reviewer_escalation",
                "deepseek/deepseek-v4-pro:xhigh",
                "read,grep,find,ls,sts_git,sts_inspect",
            ),
            ("implementer", "deepseek/deepseek-v4-flash:high", None),
        ]
        for agent, model, tools in cases:
            with self.subTest(agent=agent), mock.patch(
                "tools.ai_cycle.subprocess.Popen",
                return_value=FakeProcess(
                    stdout_lines=jsonl_lines(
                        [assistant_message_end("ok")]
                    )
                ),
            ) as popen_mock:
                result = self.invoke(agent=agent)
            self.assertEqual("ok\n", result)
            cmd = popen_mock.call_args.args[0]
            self.assertEqual("pi", cmd[0])
            for expected in (
                "--mode", "json", "-p", "--no-session", "--approve",
                "--extension",
                str(ai_cycle.ROOT / ".pi/extensions/sts-tools.ts"),
                "--extension",
                str(ai_cycle.ROOT / ".pi/extensions/sts-safety.ts"),
                "--model", model,
            ):
                self.assertIn(expected, cmd)
            if tools is None:
                self.assertNotIn("--tools", cmd)
            else:
                self.assertIn("--tools", cmd)
                self.assertEqual(tools,
                                 cmd[cmd.index("--tools") + 1])
            self.assertEqual(cmd[-1], "Task: plan")
            self.assertEqual(
                "Task: plan", cmd[-1],
            )

    def test_pi_argv_attaches_files_and_prompt_body(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir, mock.patch(
            "tools.ai_cycle.subprocess.Popen",
            return_value=FakeProcess(
                stdout_lines=jsonl_lines(
                    [assistant_message_end('{"verdict": "PASS"}')]
                )
            ),
        ) as popen_mock:
            result = ai_cycle.PiBackend().invoke(
                agent="reviewer",
                prompt="review it",
                files=[Path(raw_dir) / "plan.json"],
            )
        self.assertEqual('{"verdict": "PASS"}\n', result)
        cmd = popen_mock.call_args.args[0]
        append_index = cmd.index("--append-system-prompt")
        prompt_path = Path(cmd[append_index + 1])
        self.assertTrue(prompt_path.exists() or not prompt_path.exists())
        body = ai_cycle.pi_agent_prompt_body("reviewer")
        self.assertIn("senior adversarial reviewer", body)
        self.assertNotIn("---", body.splitlines()[0])
        self.assertIn(f"@{raw_dir}/plan.json", cmd)
        self.assertEqual("Task: review it", cmd[-1])

    def test_pi_agent_prompt_body_strips_frontmatter(self) -> None:
        for agent, expected_fragment in [
            ("architect", "senior software and research architect"),
            ("implementer", "implementation agent"),
            ("reviewer", "adversarial reviewer"),
            ("reviewer_escalation", "escalation auditor"),
        ]:
            with self.subTest(agent=agent):
                body = ai_cycle.pi_agent_prompt_body(agent)
                self.assertIn(expected_fragment, body)
                self.assertNotIn("name:", body.splitlines()[0])
                self.assertNotIn("model:", body.splitlines()[0])

    def test_pi_final_response_extraction(self) -> None:
        events = [
            {"type": "session_header", "sessionId": "x"},
            {"type": "tool_execution_start", "toolName": "read"},
            {
                "type": "tool_result_end",
                "message": {
                    "role": "toolResult",
                    "toolName": "read",
                    "isError": False,
                    "content": [{"type": "text", "text": "file"}],
                },
            },
            assistant_message_end("first"),
            assistant_message_end("second"),
        ]
        self.assertEqual("second\n", ai_cycle.pi_final_response(events))
        self.assertEqual({}, ai_cycle.pi_last_assistant_message([]))

    def test_pi_final_response_ignores_thinking_parts(self) -> None:
        message = assistant_message_end("answer")
        message["message"]["content"] = [
            {"type": "thinking", "thinking": "hidden reasoning"},
            {"type": "text", "text": "answer"},
        ]
        events = [message]
        self.assertEqual("answer\n", ai_cycle.pi_final_response(events))

    def test_malformed_jsonl_ignored(self) -> None:
        with mock.patch(
            "tools.ai_cycle.subprocess.Popen",
            return_value=FakeProcess(
                stdout_lines=[
                    "not json\n",
                    "also not json\n",
                    '{"type": "agent_end", "messages": []}\n',
                ]
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "no final assistant response"
            ):
                self.invoke()

    def test_nonzero_pi_exit_raises(self) -> None:
        with mock.patch(
            "tools.ai_cycle.subprocess.Popen",
            return_value=FakeProcess(
                stdout_lines=jsonl_lines(
                    [assistant_message_end("partial answer")]
                ),
                returncode=1,
                stderr_lines=["api error: nope\n"],
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "exit code 1"):
                self.invoke()

    def test_pi_stop_reason_error_raises(self) -> None:
        with mock.patch(
            "tools.ai_cycle.subprocess.Popen",
            return_value=FakeProcess(
                stdout_lines=jsonl_lines(
                    [
                        assistant_message_end(
                            "x", stopReason="error",
                            errorMessage="rate limited",
                        )
                    ]
                )
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "stopped with error"):
                self.invoke()

    def test_timeout_propagates_and_terminates(self) -> None:
        process = FakeProcess(
            stdout_lines=[],
            timed_out=True,
        )
        with mock.patch(
            "tools.ai_cycle.subprocess.Popen", return_value=process
        ):
            with self.assertRaisesRegex(RuntimeError, "timed out after"):
                self.invoke(timeout_seconds=60)
        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)

    def test_timeout_without_deadline_wait_forever(self) -> None:
        process = FakeProcess(
            stdout_lines=jsonl_lines([assistant_message_end("ok")])
        )
        with mock.patch(
            "tools.ai_cycle.subprocess.Popen", return_value=process
        ):
            self.assertEqual("ok\n", self.invoke(timeout_seconds=None))
        self.assertFalse(process.terminated)

    def test_log_recovery_block_parses_after_failed_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir, mock.patch(
            "tools.ai_cycle.subprocess.Popen",
            return_value=FakeProcess(
                stdout_lines=jsonl_lines(
                    [assistant_message_end('{"verdict": "PASS"}')]
                ),
                returncode=1,
            ),
        ):
            log_file = Path(raw_dir) / "review-1.log"
            with self.assertRaisesRegex(RuntimeError, "exit code 1"):
                ai_cycle.PiBackend().invoke(
                    agent="reviewer",
                    prompt="review it",
                    log_file=log_file,
                )
            transcript = log_file.read_text(encoding="utf-8")
            self.assertIn(ai_cycle.PI_FINAL_RESPONSE_BEGIN, transcript)
            self.assertNotIn("PI FINAL RESPONSE END", transcript)
            data = ai_cycle.parse_json_response(
                transcript, source="test log"
            )
            self.assertEqual("PASS", data["verdict"])

    def test_pi_cost_entries_recorded_per_agent(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            log_file = Path(raw_dir) / "review-1.log"
            with mock.patch(
                "tools.ai_cycle.subprocess.Popen",
                return_value=FakeProcess(
                    stdout_lines=jsonl_lines(
                        [assistant_message_end("ok")]
                    )
                ),
            ):
                self.invoke(agent="reviewer", log_file=log_file)
            entry = ai_cycle.CYCLE_COST_ENTRIES[-1]
            self.assertEqual("reviewer", entry["agent"])
            self.assertEqual(0.001, entry["cost"])
            self.assertEqual(10, entry["tokens_input"])
            self.assertEqual(5, entry["tokens_output"])
            saved = json.loads(
                log_file.parent.joinpath("costs.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("reviewer", saved["entries"][-1]["agent"])

    def test_pi_denied_calls_extracted(self) -> None:
        events = [
            {
                "type": "tool_result_end",
                "message": {
                    "role": "toolResult",
                    "toolName": "bash",
                    "isError": True,
                    "content": [{
                        "type": "text",
                        "text": "Blocked STS command: git commit is "
                                "controlled by the human/orchestrator",
                    }],
                },
            },
            {
                "type": "tool_result_end",
                "message": {
                    "role": "toolResult",
                    "toolName": "write",
                    "isError": True,
                    "content": [{
                        "type": "text",
                        "text": "Protected STS workflow path: "
                                "tools/ai_cycle.py",
                    }],
                },
            },
            {
                "type": "tool_result_end",
                "message": {
                    "role": "toolResult",
                    "toolName": "bash",
                    "isError": False,
                    "content": [{"type": "text", "text": "clean run"}],
                },
            },
        ]
        calls = ai_cycle.extract_pi_denied_calls(events)
        self.assertEqual(2, len(calls))
        self.assertIn("bash: Blocked STS command", calls[0])
        self.assertIn("write: Protected STS workflow path", calls[1])

    def test_pi_denied_calls_recorded_with_log(self) -> None:
        events = [
            {
                "type": "tool_result_end",
                "message": {
                    "role": "toolResult",
                    "toolName": "bash",
                    "isError": True,
                    "content": [{
                        "type": "text",
                        "text": "Blocked STS command: git push is "
                                "controlled by the human/orchestrator",
                    }],
                },
            }
        ]
        with tempfile.TemporaryDirectory() as raw_dir:
            log_file = Path(raw_dir) / "implementer-1.log"
            with mock.patch(
                "tools.ai_cycle.subprocess.Popen",
                return_value=FakeProcess(
                    stdout_lines=jsonl_lines(
                        [*events, assistant_message_end("done")]
                    )
                ),
            ):
                self.invoke(agent="implementer", log_file=log_file)
            text = (log_file.parent / "denied-tool-calls.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("## implementer", text)
            self.assertIn("Blocked STS command", text)

    def test_opencode_backend_argv_and_failure(self) -> None:
        with mock.patch(
            "tools.ai_cycle.subprocess.Popen",
            return_value=FakeProcess(stdout_lines=["noise\n"]),
        ) as popen_mock:
            result = ai_cycle.OpenCodeBackend().invoke(
                agent="architect", prompt="plan",
                files=[Path("plan.json")],
            )
        self.assertEqual("noise\n", result)
        cmd = popen_mock.call_args.args[0]
        self.assertEqual(
            ["opencode", "run", "--auto", "--agent", "architect",
             "--dir", str(ai_cycle.ROOT), "--file", "plan.json",
             "--", "plan"],
            cmd,
        )

        with mock.patch(
            "tools.ai_cycle.subprocess.Popen",
            return_value=FakeProcess(stdout_lines=[], returncode=2),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "OpenCode agent 'architect' failed"
            ):
                ai_cycle.OpenCodeBackend().invoke(
                    agent="architect", prompt="plan"
                )


class PiLiveStreamingTests(unittest.TestCase):
    """Pi live status streaming: lifecycle-only stdout, no content dumping.

    Covers the JSONL lifecycle events (turn_start, message_update,
    tool_execution_start/end) surfaced by `pi_live_status_line` and the
    model-bearing Pi banner, with fake streams - no API calls.
    """

    def setUp(self) -> None:
        self.addCleanup(ai_cycle.CYCLE_COST_ENTRIES.clear)
        self.addCleanup(ai_cycle.CYCLE_DENIED_CALLS.clear)
        self.addCleanup(setattr, ai_cycle, "ACTIVE_BACKEND",
                        ai_cycle.OpenCodeBackend())

    def invoke_captured(
        self,
        agent: str = "architect",
        events: list[dict] | None = None,
        **kwargs,
    ) -> tuple[str, str]:
        stdout = StringIO()
        with redirect_stdout(stdout), mock.patch(
            "tools.ai_cycle.subprocess.Popen",
            return_value=FakeProcess(
                stdout_lines=jsonl_lines(events or [assistant_message_end("ok")])
            ),
        ):
            result = ai_cycle.PiBackend().invoke(
                agent=agent, prompt="plan", **kwargs
            )
        return result, stdout.getvalue()

    def test_thinking_responding_status_lifecycle(self) -> None:
        events = [
            {"type": "turn_start"},
            {"type": "message_start", "message": {"role": "user"}},
            {"type": "message_update",
             "assistantMessageEvent": {"type": "thinking_start"}},
            {"type": "message_update",
             "assistantMessageEvent": {"type": "thinking_delta",
                                       "delta": "secret reasoning"}},
            {"type": "message_update",
             "assistantMessageEvent": {"type": "text_start"}},
            {"type": "message_update",
             "assistantMessageEvent": {"type": "text_delta",
                                       "delta": "half an answer"}},
            assistant_message_end("final answer"),
        ]
        result, printed = self.invoke_captured(events=events)
        self.assertEqual("final answer\n", result)
        self.assertIn("[architect] model thinking...", printed)
        self.assertIn("[architect] model responding...", printed)
        self.assertLess(printed.index("model thinking..."),
                        printed.index("model responding..."))
        self.assertNotIn("secret reasoning", printed)
        self.assertNotIn("half an answer", printed)
        self.assertNotIn("final answer", printed)

    def test_tool_start_printed_before_tool_done(self) -> None:
        events = [
            {"type": "turn_start"},
            {"type": "tool_execution_start", "toolName": "read",
             "args": {"file_path": "AGENTS.md", "offset": 1, "limit": 20}},
            {"type": "tool_execution_update", "toolName": "read",
             "partialResult": {}},
            {"type": "tool_execution_end", "toolName": "read",
             "isError": False, "result": {}},
            assistant_message_end("done"),
        ]
        result, printed = self.invoke_captured(events=events)
        self.assertEqual("done\n", result)
        self.assertIn("[architect] tool: read AGENTS.md:1-20", printed)
        self.assertIn("[architect] tool done", printed)
        self.assertLess(printed.index("tool: read AGENTS.md:1-20"),
                        printed.index("tool done"))

    def test_tool_done_printed_for_success_and_failure(self) -> None:
        for is_error in (False, True):
            with self.subTest(isError=is_error):
                events = [
                    {"type": "tool_execution_start", "toolName": "bash",
                     "args": {"command": "make -j"}},
                    {"type": "tool_execution_end", "toolName": "bash",
                     "isError": is_error, "result": {}},
                    assistant_message_end("done"),
                ]
                _, printed = self.invoke_captured(agent="implementer",
                                                  events=events)
                self.assertIn("[implementer] tool: bash make -j", printed)
                self.assertEqual(1, printed.count("[implementer] tool done"))

    def test_responding_printed_once_per_response(self) -> None:
        events = [
            {"type": "turn_start"},
            {"type": "message_update",
             "assistantMessageEvent": {"type": "text_delta", "delta": "a"}},
            {"type": "message_update",
             "assistantMessageEvent": {"type": "text_delta", "delta": "b"}},
            {"type": "message_update",
             "assistantMessageEvent": {"type": "text_delta", "delta": "c"}},
            assistant_message_end("abc"),
        ]
        result, printed = self.invoke_captured(events=events)
        self.assertEqual("abc\n", result)
        self.assertEqual(1, printed.count("[architect] model responding..."))

    def test_responding_printed_again_on_next_turn(self) -> None:
        events = [
            {"type": "turn_start"},
            {"type": "message_update",
             "assistantMessageEvent": {"type": "text_delta", "delta": "a"}},
            {"type": "tool_execution_start", "toolName": "read",
             "args": {"file_path": "x"}},
            {"type": "tool_execution_end", "toolName": "read",
             "isError": False, "result": {}},
            {"type": "turn_start"},
            {"type": "message_update",
             "assistantMessageEvent": {"type": "text_delta", "delta": "b"}},
            assistant_message_end("done"),
        ]
        result, printed = self.invoke_captured(events=events)
        self.assertEqual("done\n", result)
        self.assertEqual(2, printed.count("[architect] model responding..."))

    def test_malformed_lines_interleaved_with_live_events(self) -> None:
        raw_lines = [
            "garbage\n",
            '{"type": "turn_start"}\n',
            '{"type": "message_update", "assistantMessageEvent": '
            '{"type": "thinking_start"}}\n',
            "not json either\n",
            json.dumps(assistant_message_end("ok")) + "\n",
        ]
        stdout = StringIO()
        with redirect_stdout(stdout), mock.patch(
            "tools.ai_cycle.subprocess.Popen",
            return_value=FakeProcess(stdout_lines=raw_lines),
        ):
            result = ai_cycle.PiBackend().invoke(agent="architect",
                                                 prompt="plan")
        self.assertEqual("ok\n", result)
        self.assertIn("[architect] model thinking...", stdout.getvalue())

    def test_pi_banner_shows_model_display_name(self) -> None:
        _, printed = self.invoke_captured(agent="architect")
        self.assertIn("====== ARCHITECT · DeepSeek V4 Pro ======", printed)
        _, printed = self.invoke_captured(agent="implementer")
        self.assertIn("====== IMPLEMENTER · DeepSeek V4 Flash ======", printed)
        _, printed = self.invoke_captured(agent="reviewer_escalation")
        self.assertIn("====== REVIEWER_ESCALATION · DeepSeek V4 Pro ======",
                      printed)

    def test_tool_line_formatting_unit(self) -> None:
        cases = [
            ("read", {"file_path": "AGENTS.md"}, "read AGENTS.md"),
            ("read", {"file_path": "AGENTS.md", "offset": 10},
             "read AGENTS.md:10"),
            ("read", {"file_path": "AGENTS.md", "offset": 10, "limit": 5},
             "read AGENTS.md:10-14"),
            ("read", {"path": "docs/knowledge-base/README.md", "limit": 3},
             "read docs/knowledge-base/README.md:1-3"),
            ("grep", {"pattern": "VNet", "path": "docs/knowledge-base/"},
             'grep "VNet" docs/knowledge-base/'),
            ("find", {"pattern": "*.cpp", "path": "src"},
             "find *.cpp in src"),
            ("ls", {"path": "build"}, "ls build"),
            ("edit", {"file_path": "src/a.cpp"}, "edit src/a.cpp"),
            ("write", {"path": "out.txt"}, "write out.txt"),
            ("sts_git", {"subcommand": "status", "args": ["--short"]},
             "sts_git status --short"),
            ("sts_inspect", {"args": ["show", "x.csv"]},
             "sts_inspect show x.csv"),
            ("mystery", {"file_path": "x", "other": 1},
             "mystery file_path=x other=1"),
            ("weird_tool", {"nested": {"deep": True}}, "weird_tool"),
        ]
        for tool_name, args, expected in cases:
            with self.subTest(tool=tool_name):
                self.assertEqual(
                    expected, ai_cycle.pi_format_tool_call(tool_name, args)
                )

    def test_tool_line_formatting_odd_args(self) -> None:
        self.assertEqual("read ?", ai_cycle.pi_format_tool_call("read", None))
        self.assertEqual("read ?", ai_cycle.pi_format_tool_call("read", 7))
        self.assertEqual("bash ?",
                         ai_cycle.pi_format_tool_call("bash", {"command": 7}))
        self.assertEqual('grep "?" ?',
                         ai_cycle.pi_format_tool_call("grep", {}))
        self.assertEqual("ls .", ai_cycle.pi_format_tool_call("ls", {}))

    def test_bash_command_truncated(self) -> None:
        line = ai_cycle.pi_format_tool_call(
            "bash", {"command": "cmake --build build -j" * 5}
        )
        self.assertTrue(line.startswith("bash cmake"))
        self.assertTrue(line.endswith("..."))
        self.assertLessEqual(len(line), 65)

    def test_unknown_tool_summary_truncated(self) -> None:
        line = ai_cycle.pi_format_tool_call(
            "mystery", {"file_path": "long" * 40}
        )
        self.assertTrue(line.startswith("mystery file_path="))
        self.assertTrue(line.endswith("..."))
        self.assertLessEqual(len(line), 90)


class PiBackendCycleTests(unittest.TestCase):
    """End-to-end orchestration driven through the Pi backend, no API calls."""

    def setUp(self) -> None:
        self.addCleanup(ai_cycle.CYCLE_COST_ENTRIES.clear)
        self.addCleanup(ai_cycle.CYCLE_DENIED_CALLS.clear)
        self.addCleanup(setattr, ai_cycle, "ACTIVE_BACKEND",
                        ai_cycle.OpenCodeBackend())
        ai_cycle.ACTIVE_BACKEND = ai_cycle.PiBackend()

    def test_cheap_review_fix_repair_rereview_through_pi(self) -> None:
        factory = PiFakeFactory(reviews=[review_data("FIX"), review_data("PASS")])
        with tempfile.TemporaryDirectory() as raw_dir, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ), mock.patch(
            "tools.ai_cycle.changed_diff_stats",
            return_value=([], 0, 0),
        ):
            session_dir = Path(raw_dir)
            plan_file, task_file = write_pi_session_files(session_dir)
            result = ai_cycle.complete_candidate_workflow(
                plan=plan_with([check(cost="cheap")]),
                plan_file=plan_file,
                task_file=task_file,
                session_dir=session_dir,
                allow_expensive=False,
            )
            self.assertEqual(0, result)
            self.assertEqual(3, len(factory.calls))
            self.assertTrue((session_dir / "review-1.json").exists())
            self.assertTrue((session_dir / "review-2.json").exists())
            self.assertTrue((session_dir / "review-fix-1.md").exists())
            escalation = json.loads(
                (session_dir / "escalation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(escalation["escalated"])
            self.assertFalse((session_dir / "sol-review-1.json").exists())
            reviews = [d["verdict"] for _, _, d in
                       ai_cycle.existing_review_rounds(session_dir)]
            self.assertEqual(["FIX", "PASS"], reviews)

    def test_high_risk_pass_escalates_through_pi(self) -> None:
        plan = plan_with([check(cost="cheap")])
        plan["design"] = "training/inference parity change"
        factory = PiFakeFactory(reviews=[review_data("PASS")],
                                sol_reviews=[review_data("PASS")])
        with tempfile.TemporaryDirectory() as raw_dir, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ), mock.patch(
            "tools.ai_cycle.changed_diff_stats",
            return_value=([], 0, 0),
        ):
            session_dir = Path(raw_dir)
            plan_file, task_file = write_pi_session_files(session_dir)
            result = ai_cycle.complete_candidate_workflow(
                plan=plan,
                plan_file=plan_file,
                task_file=task_file,
                session_dir=session_dir,
                allow_expensive=False,
            )
            self.assertEqual(0, result)
            self.assertTrue((session_dir / "escalation.json").exists())
            self.assertTrue((session_dir / "sol-review-1.json").exists())
            self.assertEqual(2, len(factory.calls))
            sol_model = [
                cmd for cmd in factory.calls
                if "--model deepseek/deepseek-v4-pro:xhigh" in " ".join(cmd)
            ]
            self.assertEqual(1, len(sol_model))

    def test_rejected_session_recovery_through_pi(self) -> None:
        factory = PiFakeFactory(sol_reviews=[review_data("PASS")])
        with tempfile.TemporaryDirectory() as raw_dir, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ):
            session_dir = Path(raw_dir)
            plan_file, task_file = write_pi_session_files(session_dir)
            rejected = review_data("FIX")
            rejected["candidate_fingerprint"] = "candidate"
            (session_dir / "review-2.json").write_text(
                json.dumps(rejected), encoding="utf-8"
            )
            result = ai_cycle.continue_rejected_workflow(
                plan=plan_with([check(cost="cheap")]),
                plan_file=plan_file,
                task_file=task_file,
                session_dir=session_dir,
                allow_expensive=False,
            )
            self.assertEqual(0, result)
            self.assertTrue(
                (session_dir / "recovery-complete.json").exists()
            )
            self.assertTrue(
                (session_dir / "recovery-adjudication.json").exists()
            )
            self.assertEqual(1, len(factory.calls))

    def test_verification_repair_retry_through_pi(self) -> None:
        failing = {"required_checks_passed": False, "checks": []}
        passing = {"required_checks_passed": True, "checks": []}
        factory = PiFakeFactory(fix_text=(
            f"{FINAL_BEGIN}\nfixed\nELI5\n- plain\n{FINAL_END}\n"
        ))
        with tempfile.TemporaryDirectory() as raw_dir, mock.patch(
            "tools.ai_cycle.subprocess.Popen", factory
        ), mock.patch(
            "tools.ai_cycle.run_verification",
            side_effect=[failing.copy(), passing.copy()],
        ), mock.patch(
            "tools.ai_cycle.candidate_fingerprint", return_value="candidate"
        ):
            session_dir = Path(raw_dir)
            plan_file, task_file = write_pi_session_files(session_dir)
            ok, verification_file = ai_cycle.run_verification_cycle(
                plan=plan_with([check(cost="cheap")]),
                plan_file=plan_file,
                task_file=task_file,
                session_dir=session_dir,
                phase="cheap",
            )
            self.assertTrue(ok)
            self.assertTrue(
                verification_file.name.startswith("cheap-verification-2")
            )
            self.assertEqual(1, len(factory.calls))
            self.assertTrue(
                (session_dir / "cheap-verification-fix-1.md").exists()
            )


class BackendSafetySyncTests(unittest.TestCase):
    def test_pi_safety_ts_seed_tables_match_python(self) -> None:
        source = (ai_cycle.ROOT / ".pi/extensions/sts-safety.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn("const MAX_AUTOMATED_SEEDS = 128", source)

        def parse_table(block_name: str) -> dict[str, int]:
            match = re.search(
                rf"const {block_name}.*?\{{(.*?)\}}",
                source,
                re.DOTALL,
            )
            self.assertIsNotNone(match, block_name)
            entries = {}
            for line in match.group(1).splitlines():
                stripped = line.strip().rstrip(",")
                if not stripped or ":" not in stripped:
                    continue
                key, _, value = stripped.partition(":")
                entries[key.strip().strip('"')] = int(value.strip())
            return entries

        self.assertEqual(
            parse_table("ONE_COMBAT_SEED_ARG_INDEX"),
            ai_cycle.KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX,
        )
        self.assertEqual(
            parse_table("PYTHON_SEED_ARG_INDEX"),
            ai_cycle.KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX,
        )
        self.assertEqual(
            ai_cycle.KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX["bestbench"], 3
        )

    def test_pi_control_plane_paths_protected(self) -> None:
        relative = {str(path) for path in ai_cycle.PROTECTED_WORKFLOW_PATHS}
        self.assertIn(".pi/agents/architect.md", relative)
        self.assertIn(".pi/agents/reviewer-pro.md", relative)
        self.assertIn(".pi/extensions/sts-safety.ts", relative)
        self.assertIn(".pi/extensions/sts-tools.ts", relative)
        self.assertIn(".pi/prompts/sts-investigate.md", relative)
        for path in ai_cycle.PROTECTED_WORKFLOW_PATHS:
            if str(path).startswith(".pi/"):
                self.assertTrue((ai_cycle.ROOT / path).exists(),
                                f"missing {path}")

    def test_implementer_protected_files_restored(self) -> None:
        protected = ai_cycle.ROOT / ".pi/agents/reviewer.md"
        original = protected.read_bytes()
        with mock.patch("tools.ai_cycle.run_agent") as run_mock:
            def sabotage(agent, prompt, **kwargs):
                protected.write_text(
                    "---\nname: hacked\n---\nrewritten", encoding="utf-8"
                )
                return "FINAL_RESPONSE_BEGIN\nx\nFINAL_RESPONSE_END\n"

            run_mock.side_effect = sabotage
            ai_cycle.run_implementer_agent(
                "task",
                log_file=Path(tempfile.mkdtemp()) / "implementation-1.log",
            )
        self.assertEqual(original, protected.read_bytes())

    def test_dirty_tree_refuses_before_agent_invocation(self) -> None:
        with mock.patch(
            "tools.ai_cycle.git",
            return_value=" M tools/ai_cycle.py\n",
        ):
            with self.assertRaisesRegex(RuntimeError, "Tracked working-tree"):
                ai_cycle.ensure_safe_start()


if __name__ == "__main__":
    unittest.main()
