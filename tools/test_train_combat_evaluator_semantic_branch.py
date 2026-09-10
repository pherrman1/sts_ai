"""Synthetic checks for the semantic-branch trainer adapter.

These tests exercise only pure feature, grouping, alias, and uncertainty
helpers. They do not require the preserved corpus, XGBoost training, or the
simulator.
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.train_combat_evaluator_semantic_branch import (  # noqa: E402
    LABEL_COLUMNS,
    PROVENANCE_COLUMNS,
    STATE_FEATURES,
    alias_audit,
    bootstrap_metric_difference,
    build_features,
    classify,
    source_macro,
    valid_mask,
)


def synthetic_frame() -> pd.DataFrame:
    rows = []
    for seed in range(10):
        for fight in range(2):
            won = int(fight == 0)
            encounter = "Cultist" if seed < 7 else "Unseen" if seed == 9 else "Champ"
            row = {name: 0.0 for name in STATE_FEATURES}
            row.update({
                "sourceSeed": seed, "act": 1, "floor": 8,
                "encounter": encounter, "roomClass": "NORMAL",
                "won": won, "trueDeath": 1 - won, "escaped": 0,
                "turnCapLoss": 0, "progressAmbiguous": 0, "labelValid": 1,
                "winHpFrac": .5 if won else .001,
                "lossRemainingFrac": .001 if won else .25,
                "signedOutcome": .5 if won else -.25,
            })
            row["ascension"] = float(seed)
            rows.append(row)
    return pd.DataFrame(rows)


class SemanticBranchTrainerHelpersTest(unittest.TestCase):
    def setUp(self):
        self.frame = synthetic_frame()
        self.split = self.frame.sourceSeed.map(
            {seed: "train" if seed < 7 else "validation" if seed == 7 else "test" for seed in range(10)}
        )
        self.features, self.contract = build_features(self.frame, self.split)

    def test_feature_contract_is_state_plus_train_encounters_only(self):
        self.assertEqual(self.contract["state_features"], STATE_FEATURES)
        self.assertNotIn("semanticKey", self.features)
        self.assertNotIn("semanticActionIdx", self.features)
        self.assertNotIn("signedOutcome", self.features)
        self.assertEqual(self.contract["unseen_encounter_rows"]["test"], 4)
        self.assertEqual(set(self.contract["excluded_columns"]), set(PROVENANCE_COLUMNS + LABEL_COLUMNS))

    def test_alias_audit_detects_conflicting_identical_inputs(self):
        audit = alias_audit(self.frame, pd.Series(True, index=self.frame.index))
        self.assertEqual(audit["duplicated_input_groups"], 10)
        self.assertEqual(audit["duplicate_groups_with_different_signedOutcome"], 10)
        self.assertEqual(audit["largest_duplicate_group"], 2)

    def test_source_bootstrap_is_deterministic_and_clustered(self):
        predictions = {
            "p_win": np.full(len(self.frame), .6),
            "predicted_win_hp_frac": np.full(len(self.frame), .5),
            "predicted_loss_remaining_frac": np.full(len(self.frame), .25),
            "expected_signed_outcome": np.full(len(self.frame), .05),
        }
        result_a = bootstrap_metric_difference(
            self.frame, self.split.eq("test"), predictions, .5,
            "expected_signed_mae", replicates=32, seed=7,
        )
        result_b = bootstrap_metric_difference(
            self.frame, self.split.eq("test"), predictions, .5,
            "expected_signed_mae", replicates=32, seed=7,
        )
        self.assertEqual(result_a, result_b)
        self.assertEqual(result_a["unit"], "sourceSeed")
        self.assertEqual(result_a["source_groups"], 2)
        self.assertEqual(result_a["effective_replicates"], 32)

    def test_source_macro_keeps_row_and_source_views_distinct(self):
        predictions = {
            "p_win": np.full(len(self.frame), .6),
            "expected_signed_outcome": np.full(len(self.frame), .05),
        }
        baseline = {"survival_prior": .5, "signed_mean": .1}
        report = source_macro(self.frame, self.split.eq("test"), predictions, baseline)
        self.assertEqual(report["source_seeds"], 2)
        self.assertIn("survival_brier_model", report)
        self.assertIn("expected_signed_abs_baseline", report)
        self.assertTrue(valid_mask(self.frame).all())

    def test_high_power_worse_loss_tail_is_weak(self):
        metrics = {
            "test": {
                "survival": {
                    "model": {"logloss": .1, "brier": .1},
                    "train_prior_baseline": {"logloss": .2, "brier": .2},
                },
                "winning_hp": {
                    "model": {"mae": .1},
                    "train_winner_mean_baseline": {"mae": .2},
                },
                "loss_severity": {
                    "model": {"mae": .3},
                    "train_death_mean_baseline": {"mae": .2},
                },
                "expected_signed_outcome": {
                    "model": {"mae": .1},
                    "train_signed_mean_baseline": {"mae": .2},
                },
            }
        }
        self.assertEqual(
            classify(metrics, {}, loss_sources=200),
            "COMBAT PREDICTOR WEAK",
        )


if __name__ == "__main__":
    unittest.main()
