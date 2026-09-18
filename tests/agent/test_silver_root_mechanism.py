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
                  "G": ["defend", "card"], "H": ["defend", "card"]}
        priors = {arm: [] for arm in "ABGH"}
        regrets = {"A": 6.0, "B": 5.0, "G": 4.5, "H": 4.0}
        return [{"root_id": str(root), "source_seed": 100 + root // 2,
                 "arm": arm, "replicate": replicate, "search_seed": 1000 + replicate,
                 "simulations": 32, "selected_action_fingerprint": "card",
                 "b_regret": regrets[arm], "b_best": False,
                 "replay_order": orders[arm], "priors": priors[arm],
                 "state_hash": f"state-{root}", "teacher_a_hash": f"teacher-a-{root}",
                 "teacher_b_hash": f"teacher-b-{root}",
                 "executable_git_sha": "a" * 40, "silver_upstream_sha": "b" * 40,
                 "native_order": ["card", "defend"], "fixture_only": False}
                for root in range(4) for arm in "ABGH" for replicate in range(4)]

    def test_root_pairing(self):
        result = MODULE.analyze(self.rows(), expected_roots=4)
        self.assertEqual(result["roots"], 4)
        self.assertEqual(result["contrasts"]["G-A"]["regret_ci95"], [-1.5, -1.5])
        self.assertEqual(result["contrasts"]["G-A"]["improved"], 2)
        self.assertEqual(result["bootstrap_resamples"], 10000)
        self.assertEqual(result["bootstrap_unit"], "source_seed")
        self.assertEqual(result["source_seeds"], 2)
        self.assertEqual(result["contrasts"]["G-A"]["sign_test_p_two_sided"], 0.5)
        self.assertIsNone(result["classification"])
        self.assertEqual(result["predeclared_classifications"], (
            "ROOT_PRIOR_SIGNAL_CONFIRMED", "ROOT_ORDER_SIGNAL_ONLY",
            "ROOT_COMBINATION_ONLY", "ROOT_GUIDANCE_SIGNAL_NOT_CONFIRMED",
            "ROOT_GUIDANCE_INCONCLUSIVE"))
        self.assertEqual(set(result["contrasts"]),
                         {"G-A", "H-A", "G-B", "H-B", "B-A"})

    def test_bootstrap_and_sign_test_use_source_seed_means(self):
        rows = self.rows()
        for row in rows:
            row["source_seed"] = 100 if row["root_id"] in ("0", "1") else 101
            if row["root_id"] == "0" and row["arm"] == "G":
                row["b_regret"] = 3.0
            if row["root_id"] == "1" and row["arm"] == "G":
                row["b_regret"] = 5.0
            if row["root_id"] == "2" and row["arm"] == "G":
                row["b_regret"] = 8.0
        result = MODULE.analyze(rows, expected_roots=4)
        contrast = result["contrasts"]["G-A"]
        self.assertEqual(contrast["improved"], 1)
        self.assertEqual(contrast["worsened"], 1)
        self.assertEqual(contrast["tied"], 0)
        self.assertEqual(contrast["sign_test_p_two_sided"], 1.0)
        self.assertEqual(set(contrast["source_seed_deltas"]), {100, 101})

    def test_incomplete_duplicate_and_unpaired_rejected(self):
        for change in (lambda rows: rows[:-1], lambda rows: rows + [rows[0]],
                       lambda rows: [{**rows[0], "search_seed": 99}] + rows[1:]):
            with self.assertRaises(ValueError):
                MODULE.analyze(change(self.rows()), expected_roots=4)

    def test_invalid_values_rejected(self):
        for field, value in (("b_regret", float("nan")), ("b_regret", -1),
                             ("b_best", "false"), ("simulations", 31)):
            rows = self.rows()
            rows[0][field] = value
            with self.assertRaises(ValueError):
                MODULE.analyze(rows, expected_roots=4)

    def test_mixed_provenance_rejected_before_aggregation(self):
        for field in ("state_hash", "teacher_a_hash", "teacher_b_hash",
                      "executable_git_sha", "silver_upstream_sha"):
            rows = self.rows()
            rows[0][field] = "mixed"
            with self.assertRaises(ValueError):
                MODULE.analyze(rows, expected_roots=4)
        rows = self.rows()
        for row in rows:
            if row["root_id"] == "1":
                row["executable_git_sha"] = "c" * 40
        with self.assertRaises(ValueError):
            MODULE.analyze(rows, expected_roots=4)

    def test_cross_arm_treatment_contract_rejected(self):
        rows = self.rows()
        rows[next(index for index, row in enumerate(rows) if row["arm"] == "G")]["priors"] = [0.6, 0.4]
        with self.assertRaises(ValueError):
            MODULE.analyze(rows, expected_roots=4)

    def test_teacher_order_may_equal_native_order(self):
        rows = self.rows()
        for row in rows:
            if row["arm"] in ("B", "G", "H"):
                row["replay_order"] = ["card", "defend"]
        result = MODULE.analyze(rows, expected_roots=4)
        self.assertEqual(result["roots"], 4)
        rows = self.rows()
        rows[next(index for index, row in enumerate(rows) if row["arm"] == "H")]["replay_order"] = ["card", "defend"]
        with self.assertRaises(ValueError):
            MODULE.analyze(rows, expected_roots=4)

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
