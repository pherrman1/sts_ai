"""Focused checks for the offline model-comparison guardrails."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.compare_combat_evaluator_models import (  # noqa: E402
    DIRECT_GRID,
    EARLY_STOPPING,
    FACTORIAL_GRID,
    TARGET_DEATH_RECALL,
    choose_risk_threshold,
    bootstrap,
    factorized_weights,
    leave_one_loss,
    pairwise_concordance,
    ranking,
    select_nn_finalist,
)
from tools.train_combat_evaluator_semantic_branch import STATE_FEATURES, valid_mask  # noqa: E402


def frame() -> pd.DataFrame:
    rows = []
    for source in range(4):
        for decision in range(2):
            for branch in range(2):
                won = int(branch == 0)
                row = {name: 0.0 for name in STATE_FEATURES}
                row.update({"sourceSeed": source, "decisionIdx": decision, "won": won, "trueDeath": 1 - won,
                            "progressAmbiguous": 0, "labelValid": 1, "signedOutcome": .6 if won else -.4,
                            "winHpFrac": .6 if won else .001, "lossRemainingFrac": .4 if not won else .001})
                rows.append(row)
    return pd.DataFrame(rows)


class ComparisonGuardrailTest(unittest.TestCase):
    def test_grids_are_exact_and_early_stop_is_fixed(self):
        self.assertEqual(list(FACTORIAL_GRID), ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7"])
        self.assertEqual(list(DIRECT_GRID), ["C1", "C2", "C3", "C4"])
        self.assertEqual(EARLY_STOPPING, 75)

    def test_source_balancing_is_per_head_eligible_subset(self):
        data = frame()
        mask = pd.Series([True, True, True, True, True, True, False, False, True, True, False, False, True, True, False, False])
        weights = factorized_weights(data, mask)
        weighted = data.loc[mask].assign(weight=weights).groupby("sourceSeed").weight.sum()
        self.assertTrue(np.allclose(weighted.to_numpy(), 1.0))

    def test_risk_threshold_meets_declared_validation_recall(self):
        data = frame()
        split = pd.Series(["validation"] * len(data))
        p_win = np.array([.95, .2] * (len(data) // 2))
        threshold = choose_risk_threshold(data, split.eq("validation"), {"p_win": p_win})
        self.assertGreaterEqual(threshold["validation_death_recall"], TARGET_DEATH_RECALL)

    def test_ranking_counts_each_decision_once(self):
        data = frame()
        result = ranking(data, pd.Series([True] * len(data)), np.array(data.signedOutcome))
        self.assertEqual(result["eligible_decisions"], 8)
        self.assertEqual(result["macro_pairwise_concordance"], 1.0)

    def test_pairwise_concordance_skips_truth_ties(self):
        self.assertEqual(pairwise_concordance(np.array([1.0, 1.0, 0.0]), np.array([1.0, .8, 0.0])), 1.0)

    def test_survival_bootstrap_uses_squared_error(self):
        data = frame()
        test = pd.Series([True] * len(data))
        candidate_p = np.array([.9, .8, .7, .6] * 4)
        baseline_p = np.full(len(data), .5)
        candidate = {"p_win": candidate_p}
        baseline = {"p_win": baseline_p}
        result = bootstrap(data, test, candidate, baseline, "survival_brier",
                           {"survival_prior": .5}, replicates=32, seed=7)
        truth = data.won.to_numpy(dtype=float)
        expected = np.mean((candidate_p - truth) ** 2 - (baseline_p - truth) ** 2)
        self.assertAlmostEqual(result["difference"], expected)

    def test_nn_selection_uses_direct_signed_metric(self):
        candidates = {
            "factorized_better": {"validation_factorized_expected_signed_mae": .1, "validation_direct_signed_mae": .3},
            "direct_better": {"validation_factorized_expected_signed_mae": .3, "validation_direct_signed_mae": .1},
        }
        self.assertEqual(select_nn_finalist(candidates), "direct_better")

    def test_loss_tail_is_source_clustered(self):
        data = frame()
        preds = {"predicted_loss_remaining_frac": np.full(len(data), .4)}
        result = leave_one_loss(data, pd.Series([True] * len(data)), preds, .2)
        self.assertEqual(result["independent_death_sources"], 4)
        self.assertTrue(np.allclose(result["model_minus_trivial_mae_range"], [-0.2, -0.2]))


if __name__ == "__main__":
    unittest.main()
