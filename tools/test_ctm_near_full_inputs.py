import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import ctm_near_full_inputs as m  # noqa: E402
from tools.combat_transition_surrogate import sha256  # noqa: E402
from tools.test_combat_transition_contract import predictor_input, state  # noqa: E402


class TestNearFullInputs(unittest.TestCase):
    def fixture(self, root: Path):
        rows, split, win = [], [], []
        dagger = {"id": m.DAGGER, "misc": 15, "upgraded": False}
        for i in range(6):
            pre, post, pi = state(), state(), predictor_input(i + 1)
            if i == 1:
                pi["globals"]["encounter"] = m.c.base.WRITHING_MASS_ID
            if i == 2:
                pre["deck"].append(dagger); post["deck"].append(dict(dagger, misc=18))
            outcome = 2 if i == 5 else 1
            rows.append({"sourceSeed": 100 + i, "fightIdx": 0, "predictorInput": pi,
                         "transition": {"combatOutcome": outcome, "pre": pre, "post": post}})
            split.append(i % 3); win.append(outcome == 1)
        corpus = root / "corpus.jsonl"
        corpus.write_text("".join(json.dumps(r) + "\n" for r in rows))
        folder = root / "parent" / "potion-trajectory-v2"; folder.mkdir(parents=True)
        np.savez_compressed(folder / "cache.npz", ids=np.arange(6), source=np.arange(100, 106),
                            split=np.asarray(split), win=np.asarray(win))
        (folder / "preparation.json").write_text(json.dumps({"cacheSha256": sha256(folder / "cache.npz"),
                                                             "hashes": {}}))
        return root / "parent", corpus

    def test_build_and_compare(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); parent, corpus = self.fixture(root)
            summary = m.build(parent, corpus, root / "a", "gate")
            self.assertEqual(summary["labels"]["rows"], 6)
            self.assertEqual(summary["labels"]["survivors"], 5)
            # Winning Writhing and Dagger rows need joint native targets.
            self.assertEqual(summary["labels"]["affectedRows"], 2)
            self.assertEqual(summary["testStates"], {"rows": 2, "previous179": 2})
            with np.load(root / "a" / m.LABELS / "labels.npz") as z:
                self.assertEqual(z["writhing"].tolist(), [False, True, False, False, False, False])
                self.assertEqual(z["dagger"].tolist(), [False, False, True, False, False, False])
                self.assertEqual(z["observed"].shape, (6, 4))
            m.build(parent, corpus, root / "b", "gate")
            self.assertEqual(m.compare(root / "a", root / "b")["problems"], [])
            path = root / "b" / f"{m.TEST_STATES}.jsonl"
            rows = [json.loads(l) for l in path.read_text().splitlines()]
            rows[0]["old"] = not rows[0]["old"]
            path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            self.assertEqual(m.compare(root / "a", root / "b")["problems"], ["test_states"])
            with self.assertRaisesRegex(ValueError, "overwrite"):
                m.build(parent, corpus, root / "a", "gate")


if __name__ == "__main__":
    unittest.main()
