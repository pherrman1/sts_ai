"""Small strict-fixture and numerical tests; never access the real corpus."""
import hashlib
import unittest
from unittest.mock import patch

import numpy as np

from tools import test_vwin_refresh_corpus as corpus_fixtures
from tools.vwin_refresh_contract import ContractError, _sha256
from tools.vwin_refresh_dataset import Dataset, half_train_sources, source_split, validated_dataset, preboss_map_state


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.fixture = corpus_fixtures.CorpusTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def dataset(self):
        return validated_dataset(self.fixture.index_path,
            expected_sha=_sha256(self.fixture.index_path),
            expected_counts={"TRAIN": 2, "VALIDATION": 0, "TEST": 0})

    def test_strict_entry_component_label_join_and_metadata(self):
        from tools.vwin_refresh_corpus import validate_corpus
        with patch("tools.vwin_refresh_dataset.validate_corpus", wraps=validate_corpus) as validate:
            data = self.dataset()
            x, labels, meta = data.read("TRAIN")
            self.assertEqual(validate.call_count, 1)
        self.assertEqual(x.dtype, np.float32)
        self.assertEqual(x.shape[1], 1017)
        self.assertEqual(set(labels.tolist()), {1.0})
        self.assertEqual(len({m["componentManifestSha256"] for m in meta}), 2)
        self.assertTrue(all(m["sourceSeed"] in data.corpus.source_seeds for m in meta))
        self.assertTrue(all("rowIdx" in m and "act" in m and "feature_0" not in m for m in meta))
        self.assertEqual(data.read("VALIDATION")[0].shape, (0, 1017))
        self.assertEqual(len(data.branches("TRAIN")), 4)

    def test_label_join_uses_component_and_trajectory_key(self):
        data = self.dataset()
        expected = {}
        for component in data.corpus.components:
            joins = data._runouts[component.manifest_path]
            for i, key in enumerate(joins):
                joins[key] = i % 2
                expected[(component.manifest_sha256, *key)] = i % 2
        _, labels, metadata = data.read("TRAIN")
        self.assertEqual(set(labels.tolist()), {0., 1.})
        for label, row in zip(labels, metadata):
            self.assertEqual(label, expected[(row["componentManifestSha256"], row["sourceSeed"], row["branchId"])])

    def test_row_limits_are_smoke_only(self):
        data = self.dataset()
        self.assertEqual(len(data.read('TRAIN', row_limit=1)[0]), 1)
        with self.assertRaisesRegex(ContractError, 'row limits'):
            data.read('TEST', allow_test=True, row_limit=1)
        with self.assertRaisesRegex(ContractError, 'row limits'):
            data.read('TRAIN', row_limit=0)

    def test_preboss_uses_exact_native_map_transition(self):
        for act in (1, 2, 3):
            self.assertEqual(preboss_map_state(dict(act=act, mapY=14)), 1)
            self.assertEqual(preboss_map_state(dict(act=act, mapY=13)), 0)
        self.assertEqual(preboss_map_state(dict(act=4, mapY=2)), 1)
        self.assertEqual(preboss_map_state(dict(act=4, mapY=1)), 0)
        _, _, metadata = self.dataset().read("TRAIN")
        self.assertTrue(all("preBossRule" in m for m in metadata))

    def test_bad_hash_and_counts_fail_closed(self):
        with self.assertRaisesRegex(ContractError, "SHA-256"):
            validated_dataset(self.fixture.index_path)
        with self.assertRaisesRegex(ContractError, "split counts"):
            validated_dataset(self.fixture.index_path, expected_sha=_sha256(self.fixture.index_path))

    def test_missing_join_and_invalid_label_are_rejected(self):
        data = self.dataset()
        data._runouts[data.corpus.components[0].manifest_path].clear()
        with self.assertRaisesRegex(ContractError, "missing MAP/runout"):
            data.read("TRAIN")
        # The only supported entry point is still the strict validator, which
        # rejects a corrupt runout even before numerical ingestion.
        from pathlib import Path
        runout = Path(str(self.fixture.paths[0]).replace(".manifest.json", ".runout.csv"))
        text = runout.read_text()
        runout.write_text(text.replace(",1,", ",2,", 1))
        with self.assertRaises(ContractError):
            self.dataset()

    def test_test_access_requires_explicit_frozen_caller(self):
        data = self.dataset()
        for method in (data.read, data.branches):
            with self.assertRaisesRegex(ContractError, "before freeze"):
                method("TEST")
        self.assertEqual(data.read("TEST", allow_test=True)[0].shape, (0, 1017))

    def test_train_variance_ignores_other_splits(self):
        data = self.dataset()
        n = len(data.feature_names)
        calls = []
        def rows(kind, splits, numerical=True):
            calls.append((set(splits), numerical))
            if splits == {"TRAIN"}:
                x = np.zeros(n, np.float32)
                yield "TRAIN", x.copy(), 0, {}
                x[0] = 1
                yield "TRAIN", x.copy(), 1, {}
            else:
                # Non-TRAIN vectors are deliberately inaccessible; they could
                # vary every other feature without changing TRAIN selection.
                self.assertFalse(numerical)
                yield "VALIDATION", None, 1, {}
                yield "TEST", None, 0, {}
        with patch.object(data, "_rows", side_effect=rows):
            report = data.preflight(["feature_0"])
        self.assertEqual(report["selected_feature_names"], ["feature_0"])
        self.assertEqual(report["selected_feature_indices"], [0])
        self.assertEqual(report["label_join_checks"]["MAP_rows_checked"], 4)
        self.assertEqual(report["variance_split"], "TRAIN")
        self.assertEqual(calls, [({"TRAIN"}, True), ({"VALIDATION", "TEST"}, False)])
        with self.assertRaisesRegex(ContractError, "B0 required"):
            data.preflight(["absent"])


class SplitTests(unittest.TestCase):
    def test_exact_split_and_no_source_leakage(self):
        self.assertEqual([source_split(s) for s in (0, 4, 5)], ["TRAIN", "TEST", "VALIDATION"])
        grouped = {s: set() for s in ("TRAIN", "VALIDATION", "TEST")}
        for seed in range(100):
            ratio = int(hashlib.sha256(f"vwin-refresh-334-v1:{seed}".encode()).hexdigest()[:8], 16) / 2**32
            expected = "TRAIN" if ratio < .7 else "VALIDATION" if ratio < .85 else "TEST"
            for branch in ("source", "a", "b"):
                grouped[source_split(seed)].add(seed)
                self.assertEqual(source_split(seed), expected)
        self.assertFalse(grouped["TRAIN"] & grouped["VALIDATION"])
        self.assertFalse(grouped["TRAIN"] & grouped["TEST"])
        self.assertFalse(grouped["VALIDATION"] & grouped["TEST"])

    def test_half_train_selection_is_exact_deterministic_source_half(self):
        seeds = [s for s in range(100) if source_split(s) == "TRAIN"]
        result = half_train_sources(seeds)
        self.assertEqual(result, half_train_sources(reversed(seeds)))
        self.assertEqual(len(result), len(seeds) // 2)
        self.assertTrue(set(result) <= set(seeds))
        with self.assertRaisesRegex(ContractError, "non-TRAIN"):
            half_train_sources([4])


if __name__ == "__main__":
    unittest.main()
