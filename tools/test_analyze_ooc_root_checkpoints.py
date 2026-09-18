import unittest
from analyze_ooc_root_checkpoints import CHECKPOINTS, gap, leader, stable, summarize


class CheckpointTests(unittest.TestCase):
    def row(self):
        return dict(seed=1, decisionIndex=0, requestedSimulations=2048, shadowSimulations=2048,
                    shadowAborted=False, shadowAbortReason="", liveAction=2, liveSimulations=1100,
                    finalAction=2, checkpoints=[dict(simulations=budget, actions=[
                        dict(id=1, visits=budget//2, q=.25, prior=.5),
                        dict(id=2, visits=budget//2, q=.75, prior=.5)]) for budget in CHECKPOINTS])

    def test_ties_and_no_future_information(self):
        row = self.row()
        checkpoint = row["checkpoints"][0]
        self.assertEqual(leader(checkpoint), 2)
        self.assertEqual(gap(checkpoint), 0)
        checkpoint["actions"][0]["q"] = .75
        self.assertEqual(leader(checkpoint), 1)
        self.assertFalse(stable({entry["simulations"]: entry for entry in row["checkpoints"]}, 256))

    def test_rules_and_abort_accounting(self):
        row = self.row()
        aborted = self.row() | dict(decisionIndex=1, shadowAborted=True, shadowAbortReason="smoke_bomb",
                                   shadowSimulations=700, finalAction=None, checkpoints=self.row()["checkpoints"][:3])
        result = summarize([row, aborted])
        rules = result["cohorts"]["multiActionCompleted"]["rules"]
        self.assertEqual(rules["fixed512"]["savedVsFull2048"], 1536)
        self.assertEqual(rules["fixed512"]["additionalSavedVsLiveEarlyStop"], 588)
        self.assertEqual(rules["fixed512"]["allAbortedRootsWouldStopBeforeAbort"], 1)
        self.assertEqual(rules["512_if_gap>=0.1"]["earlyStops"], 0)
        self.assertEqual(result["lateShadowAbortsAfterLiveAction"], 1)

    def test_reject_duplicate_or_missing(self):
        with self.assertRaises(ValueError):
            summarize([self.row(), self.row()])
        row = self.row()
        row["checkpoints"].pop()
        with self.assertRaises(ValueError):
            summarize([row])


if __name__ == "__main__":
    unittest.main()
