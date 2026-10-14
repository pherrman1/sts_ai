"""Seed-free rejection and command-boundary checks for the fixed pilot runner."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "teacher_pilot", REPO / "docs/experiments/evidence/a20_teacher_comparison_20261014/run_pilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class RunnerTests(unittest.TestCase):
    def test_missing_prior_does_not_create_output_or_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(pilot.subprocess, "run") as run:
                with self.assertRaises(FileNotFoundError):
                    pilot.prepare(root / "out", root / "missing", root / "ctm", 5, "a" * 64, "fixture")
                run.assert_not_called()
                self.assertFalse((root / "out").exists())

    def test_corrupt_prior_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prior").write_text("not the frozen model")
            with self.assertRaisesRegex(RuntimeError, "wrong frozen prior"):
                pilot.prepare(root / "out", root / "prior", root / "ctm", 5, "a" * 64, "fixture")
            self.assertFalse((root / "out").exists())

    def test_artifact_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "model"
            artifact.write_text("frozen")
            freeze = {"schemaVersion": "a20_teacher_comparison_freeze_v1",
                      "canarySeed": pilot.CANARY, "cohortSeeds": pilot.COHORT,
                      "repository": str(pilot.REPO),
                      "artifactFiles": {str(artifact): pilot.sha(artifact)}}
            pilot.write_new(root / "freeze.json", freeze)
            pilot.verify(root)
            artifact.write_text("changed")
            with self.assertRaisesRegex(RuntimeError, "frozen artifact changed"):
                pilot.verify(root)

    def test_canary_phase_latch_is_distinct_and_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "freeze.json").write_text("{}")
            observed = []

            def source(out, seed):
                self.assertEqual(seed, pilot.CANARY)
                self.assertFalse(list(out.glob("canary.*")))
                observed.append(seed)
                return out / "canary"

            with patch.object(pilot, "verify", return_value={}), \
                    patch.object(pilot, "run_source", side_effect=source), \
                    patch.object(pilot.subprocess, "run") as run:
                pilot.execute(root, "canary")
                self.assertEqual(observed, [pilot.CANARY])
                self.assertIn("--canary", run.call_args.args[0])
                with self.assertRaises(FileExistsError):
                    pilot.execute(root, "canary")
                self.assertEqual(observed, [pilot.CANARY])

    def test_failed_canary_blocks_cohort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pilot.write_new(root / "canary-report.json", {"verdict": "INVALID_OR_INSUFFICIENT"})
            with patch.object(pilot, "verify", return_value={}), \
                    patch.object(pilot, "run_source") as source:
                with self.assertRaisesRegex(RuntimeError, "canary did not pass"):
                    pilot.execute(root, "cohort")
                source.assert_not_called()
                self.assertFalse((root / "phase-cohort.started.json").exists())

    def test_existing_source_output_blocks_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "canary.log").write_text("preserve me")
            with patch.object(pilot, "verify", return_value={}), \
                    patch.object(pilot.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(RuntimeError, "existing source outputs"):
                    pilot.run_source(root, pilot.CANARY)
                launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
