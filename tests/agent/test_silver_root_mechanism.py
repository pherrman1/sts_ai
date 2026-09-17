import importlib.util
import unittest
import json
import subprocess
import tempfile
import sys
import hashlib
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "mechanism", Path(__file__).resolve().parents[2] / "tools/analyze_silver_root_mechanism.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MechanismTest(unittest.TestCase):
    def rows(self):
        orders = {"A": ["card", "defend"], "B": ["defend", "card"],
                  "E": ["card", "defend"], "F": ["defend", "card"],
                  "C": ["card", "defend"], "D": ["defend", "card"]}
        priors = {arm: ([] if arm in ("A", "B") else
                        [0.5, 0.5] if arm in ("E", "F") else [0.6, 0.4])
                  for arm in "ABEFCD"}
        regrets = {"A": 6.0, "B": 5.0, "E": 4.0, "F": 3.0, "C": 2.0, "D": 1.0}
        return [{"root_id": str(root), "source_seed": 100 + root,
                 "arm": arm, "replicate": replicate, "search_seed": 1000 + replicate,
                 "simulations": 32, "selected_action_fingerprint": "card",
                 "b_regret": regrets[arm], "b_best": False,
                 "replay_order": orders[arm], "priors": priors[arm],
                 "state_hash": f"state-{root}", "teacher_a_hash": f"teacher-a-{root}",
                 "teacher_b_hash": f"teacher-b-{root}",
                 "executable_git_sha": "a" * 40, "silver_upstream_sha": "b" * 40,
                 "native_order": ["card", "defend"], "fixture_only": False}
                for root in range(3) for arm in "ABEFCD" for replicate in range(4)]

    def test_root_pairing(self):
        result = MODULE.analyze(self.rows(), expected_roots=3)
        self.assertEqual(result["roots"], 3)
        self.assertEqual(result["contrasts"]["C-E"]["regret_ci95"], [-2.0, -2.0])
        self.assertEqual(result["contrasts"]["C-E"]["improved"], 3)
        self.assertEqual(result["bootstrap_resamples"], 10000)
        self.assertIsNone(result["classification"])
        self.assertEqual(set(result["contrasts"]),
                         {"E-A", "C-E", "F-B", "D-F", "B-A", "F-E", "D-C", "D-A"})

    def test_incomplete_duplicate_and_unpaired_rejected(self):
        for change in (lambda rows: rows[:-1], lambda rows: rows + [rows[0]],
                       lambda rows: [{**rows[0], "search_seed": 99}] + rows[1:]):
            with self.assertRaises(ValueError):
                MODULE.analyze(change(self.rows()), expected_roots=3)

    def test_invalid_values_rejected(self):
        for field, value in (("b_regret", float("nan")), ("b_regret", -1),
                             ("b_best", "false"), ("simulations", 31)):
            rows = self.rows()
            rows[0][field] = value
            with self.assertRaises(ValueError):
                MODULE.analyze(rows, expected_roots=3)

    def test_mixed_provenance_rejected_before_aggregation(self):
        for field in ("state_hash", "teacher_a_hash", "teacher_b_hash",
                      "executable_git_sha", "silver_upstream_sha"):
            rows = self.rows()
            rows[0][field] = "mixed"
            with self.assertRaises(ValueError):
                MODULE.analyze(rows, expected_roots=3)

    def test_selection_ignores_outcome_and_input_order(self):
        rows = [{"root_id": str(index), "source_seed": 10, "outcome": index}
                for index in range(70)]
        selected = MODULE.select(rows)
        changed = [{**row, "outcome": -99} for row in reversed(rows)]
        self.assertEqual([row["root_id"] for row in selected],
                         [row["root_id"] for row in MODULE.select(changed)])
        self.assertEqual(len(selected), 64)
        with self.assertRaises(ValueError):
            MODULE.select(rows[:63])

    def test_cli_selection_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "capture.jsonl"
            output = Path(directory) / "selected.jsonl"
            source.write_text("".join(json.dumps({"root_id": str(index), "source_seed": index % 8})
                                      + "\n" for index in range(80)))
            command = [sys.executable, str(SPEC.origin), "select", str(source), str(output)]
            subprocess.run(command, check=True, capture_output=True)
            manifest = json.loads(Path(str(output) + ".manifest.json").read_text())
            self.assertEqual(manifest["source_capture_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(manifest["selected_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(len(manifest["selected_root_ids"]), 64)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
