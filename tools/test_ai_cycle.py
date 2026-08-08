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


if __name__ == "__main__":
    unittest.main()
