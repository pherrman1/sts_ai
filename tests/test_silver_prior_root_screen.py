import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

MODULE = Path(__file__).parents[1] / "tools/silver_prior_root_screen.py"
spec = importlib.util.spec_from_file_location("silver_prior_root_screen", MODULE)
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)


class RootScreenTests(unittest.TestCase):
    def test_selects_only_64_preselected_validation_roots(self):
        entries = [{"split": "VALIDATION", "judge_selected": True,
                    "root": {"root_id": f"v{i}", "source_seed": i}} for i in range(64)]
        entries += [{"split": "TRAIN", "judge_selected": True,
                     "root": {"root_id": f"t{i}", "source_seed": 100+i}} for i in range(5)]
        self.assertEqual(64, len(screen.selected_validation({"entries": entries}, set())))
        with self.assertRaises(ValueError):
            screen.selected_validation({"entries": entries[:63] + entries[64:]}, set())

    def test_quarantined_validation_root_is_rejected_without_replacement(self):
        entries = [{"split": "VALIDATION", "judge_selected": True,
                    "root": {"root_id": f"v{i}", "source_seed": i}} for i in range(64)]
        with self.assertRaises(ValueError):
            screen.selected_validation({"entries": entries}, {"v17"})

    def test_preparation_reader_rejects_j_paths(self):
        with self.assertRaises(ValueError):
            screen.read_validation_l_shard(Path("/corpus"), "raw/J/example.json.gz")

    def test_analyzer_j_path_rejects_non_validation_roots(self):
        entry = {"split": "LOCKED_TEST", "judge_selected": True,
                 "root": {"root_id": "unused"}}
        with self.assertRaises(ValueError):
            screen.validation_j_path(Path("/corpus"), entry)

    def test_frozen_checkpoint_metadata_mismatches_fail(self):
        valid = {"state_dict": {}, "config": {"seed": 20260922,
            "architecture": "SilverPriorNetV1", "temperatures": {"T2": screen.TAU},
            **{f"{k}_sha256": v for k, v in screen.CORPUS_SHA.items()}},
            "normalization": {}, "arm": "T2", "tau": screen.TAU, "epoch": 1}
        screen.validate_checkpoint_metadata(valid)
        for key, value in (("arm", "T1"), ("tau", 1.0)):
            broken = dict(valid); broken[key] = value
            with self.assertRaises(ValueError): screen.validate_checkpoint_metadata(broken)
        broken = {**valid, "config": {**valid["config"], "seed": 1}}
        with self.assertRaises(ValueError): screen.validate_checkpoint_metadata(broken)
        with tempfile.TemporaryDirectory() as temporary:
            wrong = Path(temporary) / "wrong.pt"
            wrong.write_bytes(b"not the frozen checkpoint")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                screen.validate_checkpoint(wrong)

    def test_root_replay_rng_is_deterministic_by_experiment_root_and_replicate(self):
        expected = screen.root_replay_seed("24000384/2/29/36/6", 0)
        self.assertEqual(expected, screen.root_replay_seed("24000384/2/29/36/6", 0))
        self.assertNotEqual(expected, screen.root_replay_seed("24000384/2/29/36/6", 1))
        self.assertNotEqual(expected, screen.root_replay_seed("24000385/2/22/27/21", 0))

    def test_selected_hash_lookup_ignores_all_unselected_hash_values(self):
        class HashBomb(dict):
            def __getitem__(self, key):
                if self.get("path") != "shards/L/selected.json.gz" and key == "sha256":
                    raise AssertionError("unselected artifact hash was accessed")
                return super().__getitem__(key)

        release = {"files": [HashBomb(path="raw/J/unselected.json.gz"),
                              HashBomb(path="shards/L/selected.json.gz", sha256="abc")]}
        self.assertEqual({"shards/L/selected.json.gz": "abc"},
                         screen.selected_hashes(release, {"shards/L/selected.json.gz"}))

    def test_model_softmax_has_no_added_temperature(self):
        values = [0.0, 1.0, 2.0]
        got = screen.softmax(values)
        expected = np.exp(np.asarray(values) - 2.0)
        expected /= expected.sum()
        np.testing.assert_allclose(got, expected, rtol=0, atol=1e-15)
        self.assertNotEqual(got, screen.softmax(values, screen.TAU))

    def test_oracle_uses_frozen_tau_and_all_priors_are_positive_normalized(self):
        oracle = screen.softmax([0.0, 1.0, 2.0], screen.TAU)
        self.assertEqual(3, len(oracle))
        self.assertTrue(all(p > 0 and np.isfinite(p) for p in oracle))
        self.assertAlmostEqual(1.0, sum(oracle), places=14)
        uniform = [1/3] * 3
        self.assertEqual(uniform, [1.0/3] * 3)

    def test_action_alignment_fails_closed_on_missing_duplicate_or_reordered_surface(self):
        order = ["a", "b", "c"]
        rows = [{"fingerprint": x} for x in order]
        screen.validate_action_alignment(order, rows, [1, 2, 3])
        for bad_order, bad_rows, values in (
                (order, rows[:-1], [1, 2, 3]),
                (order, [{"fingerprint": "a"}, {"fingerprint": "a"}, {"fingerprint": "c"}], [1, 2, 3]),
                (order, list(reversed(rows)), [1, 2, 3]),
                (["a", "a"], [{"fingerprint": "a"}, {"fingerprint": "a"}], [1, 2])):
            with self.assertRaises(ValueError):
                screen.validate_action_alignment(bad_order, bad_rows, values)

    def test_classification_implements_only_predeclared_outcomes(self):
        def ci(hi): return {"ci95": [-1.0, hi]}
        self.assertEqual("LEARNED_PRIOR_ROOT_REPLAY_CONFIRMED",
                         screen.classify(ci(-0.1), ci(-0.2), ci(-0.3)))
        self.assertEqual("LEARNED_PRIOR_PUCT_SIGNAL_ONLY",
                         screen.classify(ci(-0.1), ci(0.0), ci(-0.3)))
        self.assertEqual("LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED",
                         screen.classify(ci(0.0), ci(-0.2), ci(-0.1)))
        self.assertEqual("ROOT_PUCT_HEADROOM_NOT_CONFIRMED",
                         screen.classify(ci(0.0), ci(-0.2), ci(0.0)))

    def test_bootstrap_uses_64_source_seed_units_and_fixed_replicate_count(self):
        result = screen.bootstrap_paired(np.zeros(64), 1)
        self.assertEqual("source_seed", result["unit"])
        self.assertEqual(10_000, result["bootstrap_replicates"])
        with self.assertRaises(ValueError):
            screen.bootstrap_paired(np.zeros(63), 1)


if __name__ == "__main__":
    unittest.main()
