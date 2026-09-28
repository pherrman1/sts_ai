#!/usr/bin/env python3
"""Regression test for sorting labels while streaming raw-order state rows."""

import hashlib
import pathlib
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from strategic_tok_state_cache import (
    STATE_CACHE_LAYOUT_VERSION,
    add_layout_version,
    build_raw_to_grouped,
    train_mask_for_raw_chunk,
    write_raw_state_chunk,
)


class StrategicTokenStateCacheOrderTest(unittest.TestCase):
    def test_shuffled_decisions_scatter_and_train_mask_follow_grouped_order(self):
        # Decisions are intentionally interleaved in raw CSV order and include
        # multiple candidate rows per state.
        source = pd.DataFrame({
            "seed": [3, 1, 2, 1, 3, 2, 1, 3],
            "decIdx": [0, 1, 0, 0, 0, 0, 1, 0],
            "candidate": [0, 0, 0, 1, 1, 1, 1, 2],
            "state_a": [30, 11, 20, 10, 30, 20, 11, 30],
            "state_b": [3, 1, 2, 1, 3, 2, 1, 3],
        })
        raw_seed = source.seed.to_numpy(np.int64)
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = pathlib.Path(tmp) / "shuffled.csv"
            state_path = pathlib.Path(tmp) / "states.bin"
            source.to_csv(csv_path, index=False)

            labels = pd.read_csv(csv_path, usecols=["seed", "decIdx"])
            labels["_raw_row"] = np.arange(len(labels), dtype=np.int64)
            labels.sort_values(["seed", "decIdx"], kind="stable", inplace=True,
                               ignore_index=True)
            sorted_raw_rows = labels.pop("_raw_row").to_numpy(np.int64)
            sorted_group = (labels.seed.to_numpy(np.int64) * 1_000_000
                            + labels.decIdx.to_numpy(np.int64))
            _, sorted_group_ids = np.unique(sorted_group, return_inverse=True)
            grouped_order = np.argsort(sorted_group_ids, kind="stable")
            raw_to_grouped = build_raw_to_grouped(sorted_raw_rows, grouped_order)

            expected_csv = pd.read_csv(csv_path).iloc[sorted_raw_rows[grouped_order]]
            expected = expected_csv[["state_a", "state_b"]].to_numpy(np.float32)
            cache = np.memmap(state_path, dtype=np.float32, mode="w+",
                              shape=(len(source), 2))
            raw_lo = 0
            for chunk in pd.read_csv(csv_path, usecols=["state_a", "state_b"],
                                     chunksize=3, dtype=np.float32):
                rows = chunk.to_numpy(np.float32)
                write_raw_state_chunk(cache, raw_to_grouped, raw_lo, rows)
                raw_lo += len(chunk)
            cache.flush()
            cached = np.memmap(state_path, dtype=np.float32, mode="r",
                               shape=(len(source), 2))
            np.testing.assert_array_equal(cached, expected)

            sorted_train_rows = np.isin(raw_seed[sorted_raw_rows], [1, 3])
            grouped_train_rows = sorted_train_rows[grouped_order]
            raw_train_mask = np.empty(len(raw_seed), dtype=bool)
            for lo, hi in ((0, 2), (2, 5), (5, len(raw_seed))):
                raw_train_mask[lo:hi] = train_mask_for_raw_chunk(
                    grouped_train_rows, raw_to_grouped, lo, hi)
            np.testing.assert_array_equal(raw_train_mask, np.isin(raw_seed, [1, 3]))

            for group_id in np.unique(sorted_group_ids):
                grouped_rows = np.flatnonzero(
                    sorted_group_ids[grouped_order] == group_id)
                np.testing.assert_array_equal(cached[grouped_rows], expected[grouped_rows])

    def test_layout_version_changes_cache_fingerprint(self):
        def fingerprint(version):
            digest = hashlib.sha256(b"same-corpus-and-trainer-inputs")
            add_layout_version(digest, version)
            return digest.digest()

        self.assertEqual(STATE_CACHE_LAYOUT_VERSION, "raw-to-grouped-v2")
        self.assertNotEqual(fingerprint("raw-order-v1"),
                            fingerprint(STATE_CACHE_LAYOUT_VERSION))

    def test_mapping_rejects_non_permutations(self):
        with self.assertRaises(ValueError):
            build_raw_to_grouped(np.asarray([0, 0]), np.asarray([0, 1]))
        with self.assertRaises(ValueError):
            build_raw_to_grouped(np.asarray([0, 1]), np.asarray([0, 0]))


if __name__ == "__main__":
    unittest.main()
