import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_TMP = ROOT / "build"
TEST_TMP.mkdir(exist_ok=True)


class SilverLeafPipelineTest(unittest.TestCase):
    def test_selector_keeps_complete_groups_and_is_deterministic(self):
        tmp = TEST_TMP
        paths = [tmp / name for name in ("selector_test_corpus.jsonl", "selector_test_a.json", "selector_test_b.json")]
        try:
            rows = []
            for group, act, leaves in (("g1", 1, (("a", "x"), ("b", "y"))),
                                       ("g2", 3, (("c", "x"), ("d", "y")))):
                for leaf, incoming in leaves:
                    rows.append({"corpus_schema": "silver_leaf_corpus_v1", "group_id": group,
                        "leaf_snapshot_id": leaf, "act": act, "cur_hp": 20, "max_hp": 80,
                        "encounter_category": "hallway", "aux_rollout": {"turn_delta": 8},
                        "parent_legal_action_fingerprints": ["x", "y"],
                        "incoming_action_fingerprint": incoming})
            corpus = paths[0]
            corpus.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            outputs = paths[1:]
            for output in outputs:
                subprocess.run([sys.executable, ROOT / "tools/select_silver_leaf_corpus.py",
                    corpus, output, "--target-groups", "1"], check=True, capture_output=True, text=True)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            manifest = json.loads(outputs[0].read_text())
            self.assertEqual(manifest["selected_groups"], 1)
            self.assertEqual(manifest["selected_leaves"], 2)
            self.assertEqual(manifest["groups_with_at_least_two_unique_leaves"], 1)
        finally:
            for path in paths:
                path.unlink(missing_ok=True)

    def test_analyzer_uses_independent_25k_b(self):
        def row(leaf, group, budget, replicate, selected, q):
            actions = [{"action_fingerprint": action, "leaf_root_q_valid": True,
                        "original_root_corrected_q": value, "visits": 10,
                        "child_simulations": 10, "child_victories": 5,
                        "selected": action == selected}
                       for action, value in (("left", q), ("right", q - 1))]
            return {"relabel_schema": "silver_leaf_teacher_v1", "state_kind": "leaf",
                "leaf_snapshot_id": leaf, "group_id": group, "budget": budget,
                "replicate": replicate, "selected_action_fingerprint": selected,
                "original_root_corrected_teacher_value": q, "root_actions": actions,
                "act": 3, "hp_fraction": 0.2, "rollout_turn_delta": 8,
                "encounter_category": "hallway"}
        tmp = TEST_TMP
        paths = [tmp / "analyzer_test_relabels.jsonl", tmp / "analyzer_test_output.json"]
        try:
            relabels = paths[0]
            rows = []
            for leaf, q in (("a", 5.0), ("b", 4.0)):
                for budget in (1000, 3700, 10000, 25000):
                    rows.append(row(leaf, "g", budget, "A", "left", q))
                rows.append(row(leaf, "g", 25000, "B", "left", q))
            relabels.write_text("".join(json.dumps(value) + "\n" for value in rows), encoding="utf-8")
            output = paths[1]
            subprocess.run([sys.executable, ROOT / "tools/analyze_silver_leaf_teacher.py",
                            relabels, output], check=True, capture_output=True, text=True)
            report = json.loads(output.read_text())
            self.assertEqual(report["independent_reference"], "25k replicate B")
            self.assertEqual(report["state_value_and_action"]["1000"]["top_action_agreement"], 1.0)
            self.assertEqual(report["sibling_value"]["1000"]["strict_pairwise_concordance"], 1.0)
            bootstrap = report["group_bootstrap_uncertainty"]
            self.assertEqual(bootstrap["method"], "paired sibling-group bootstrap with replacement")
            self.assertEqual(bootstrap["anchor_groups"], 1)
            self.assertEqual(bootstrap["replicates"], 2000)
            self.assertEqual(bootstrap["candidates"]["1000"]
                             ["top_action_agreement_margin_vs_25k_ceiling"],
                             {"p025": 0.0, "p975": 0.0})
            self.assertEqual(bootstrap["candidates"]["1000"]["global_bar_pass_probability"], 1.0)
        finally:
            for path in paths:
                path.unlink(missing_ok=True)

    def test_selector_preserves_rollout_diversity(self):
        tmp = TEST_TMP
        paths = [tmp / "selector_diverse_corpus.jsonl", tmp / "selector_diverse.json"]
        try:
            rows = []
            for index, turns in enumerate((1, 1, 4, 4, 8, 8)):
                group = f"g{index}"
                for leaf, incoming in ((f"{group}a", "x"), (f"{group}b", "y")):
                    rows.append({"corpus_schema": "silver_leaf_corpus_v1", "group_id": group,
                        "leaf_snapshot_id": leaf, "act": 1, "cur_hp": 20, "max_hp": 80,
                        "encounter_category": "hallway", "aux_rollout": {"turn_delta": turns},
                        "parent_legal_action_fingerprints": ["x", "y"],
                        "incoming_action_fingerprint": incoming})
            paths[0].write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            subprocess.run([sys.executable, ROOT / "tools/select_silver_leaf_corpus.py",
                            paths[0], paths[1], "--target-groups", "3"],
                           check=True, capture_output=True, text=True)
            manifest = json.loads(paths[1].read_text())
            self.assertEqual(manifest["groups_by_rollout_length_band"],
                             {"long": 1, "medium": 1, "short": 1})
        finally:
            for path in paths:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
