import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    from tools.ctm_survival_compare import compare, extract_test
except ModuleNotFoundError:  # direct invocation from the tools directory
    from ctm_survival_compare import compare, extract_test


class TestCtmSurvivalCompare(unittest.TestCase):
    def fixture(self, root: Path):
        seeds = np.asarray([1, 1, 2, 3, 3, 4]); fights = np.asarray([0, 1, 0, 0, 1, 0])
        y = np.asarray([1, 0, 1, 1, 1, 0], dtype=np.int8)
        yh = np.asarray([.5, np.nan, .8, .4, .6, np.nan], dtype=np.float32)
        npz = root / "pred.npz"
        np.savez(npz, rowIndex=np.asarray([0, 2, 3, 5, 6, 8]), sourceSeed=seeds, fightIdx=fights,
                 y_win=y, y_hp=yh, deepsets_p=np.asarray([.9, .2, .8, .9, .8, .3]),
                 deepsets_hp=np.asarray([.5, .3, .7, .4, .6, .2]))
        with (root / "corpus.jsonl").open("w") as f:
            keys = {0: (1, 0), 2: (1, 1), 3: (2, 0), 5: (3, 0), 6: (3, 1), 8: (4, 0)}
            for i in range(9):
                s, fi = keys.get(i, (99, i))
                f.write(json.dumps({"sourceSeed": s, "fightIdx": fi}) + "\n")
        with (root / "scores.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["source_seed", "fight_idx", "act", "room_class", "scored", "p_death", "win_hp_fraction"])
            for s, fi, room, scored in ((1, 0, "BOSS", 1), (1, 1, "NORMAL", 1), (2, 0, "BOSS", 1),
                                        (3, 0, "ELITE", 1), (3, 1, "NORMAL", 0), (4, 0, "NORMAL", 1)):
                w.writerow([s, fi, 1, room, scored, .5 if scored else "", .5 if scored else ""])
        return npz

    def test_extract_and_compare(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); npz = self.fixture(root)
            self.assertEqual(extract_test(root / "corpus.jsonl", npz, root / "test.jsonl"), 6)
            r = compare(npz, root / "scores.csv", root / "out.json", "deepsets", 50, 1)
            self.assertEqual(r["productionSupported"], 5)
            self.assertEqual(r["slices"]["boss"]["production"]["n"], 2)
            self.assertAlmostEqual(r["slices"]["all"]["production"]["brier"], .25)
            self.assertLess(r["slices"]["all"]["refit"]["brier"], .25)
            self.assertIn("all", r["refitMinusProductionBootstrap"]["slices"])

    def test_rejects_mismatched_rows(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); npz = self.fixture(root)
            lines = (root / "scores.csv").read_text().splitlines()[:-1]
            (root / "scores.csv").write_text("\n".join(lines) + "\n")
            with self.assertRaisesRegex(ValueError, "exactly the TEST rows"):
                compare(npz, root / "scores.csv", root / "out.json", "deepsets", 10, 1)


if __name__ == "__main__":
    unittest.main()
