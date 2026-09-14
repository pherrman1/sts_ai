"""Deterministic support, composition, and scoring checks; no model fitting."""
import copy
import unittest

import numpy as np

try:
    from tools import combat_transition_frozen_composition as frozen
except ModuleNotFoundError:
    import combat_transition_frozen_composition as frozen


class FrozenCompositionTests(unittest.TestCase):
    def test_visible_predicate_rejects_actual_creation(self):
        pi = {"globals": {"characterClass": frozen.base.IRONCLAD_ID},
              "cards": [{"cardId": frozen.base._CARD_IDS["BASH"]}],
              "potions": [{"slot": i, "potionId": 1} for i in range(5)]}
        self.assertTrue(frozen.potion_consumption_only(pi))
        for field, value in (("cards", [{"cardId": frozen.base._CARD_IDS["ALCHEMIZE"]}]),
                             ("potions", [{"slot": 0, "potionId": frozen.base.ENTROPIC_BREW_ID}])):
            bad = copy.deepcopy(pi); bad[field] = value
            self.assertFalse(frozen.potion_consumption_only(bad))
        for name in ("FOREIGN_INFLUENCE", "DISTRACTION", "DISCOVERY", "CHRYSALIS",
                     "METAMORPHOSIS", "CREATIVE_AI", "MAGNETISM", "BANE"):
            harmless = copy.deepcopy(pi)
            harmless["cards"] = [{"cardId": frozen.base._CARD_IDS[name]}]
            self.assertTrue(frozen.potion_consumption_only(harmless), name)
        bad = copy.deepcopy(pi); bad["globals"]["characterClass"] = 1
        self.assertFalse(frozen.potion_consumption_only(bad))
        # Outcome, RNG, and post-state are absent from the predicate interface.
        augmented = {**pi, "post": {"potions": [47] * 5}, "seed": 99, "outcome": 2}
        self.assertEqual(frozen.potion_consumption_only(augmented), frozen.potion_consumption_only(pi))

    def test_support_retain_consume_multiple_empty_and_unavailable(self):
        slots = np.array([[2, 3, 1, 4, 1]])
        allowed = frozen.allowed_potion_support(slots, np.array([3]))[0]
        for target in ([2, 3, 1, 4, 1], [1, 3, 1, 4, 1], [2, 1, 1, 4, 1], [1, 1, 1, 4, 1]):
            self.assertTrue(allowed[np.arange(5), target].all())
        # Swap two different potion identities, creation in empty, and a
        # consumed unavailable slot are all forbidden independently.
        for target in ([3, 2, 1, 4, 1], [2, 3, 2, 4, 1], [2, 3, 1, 1, 1], [2, 2, 1, 4, 1]):
            self.assertFalse(allowed[np.arange(5), target].all())
        self.assertEqual(allowed.sum(axis=-1).tolist(), [2, 2, 1, 1, 1])

    def test_stable_mask_renormalization_and_uncertified_identity(self):
        slots = np.array([[2, 3, 1, 1, 1], [2, 3, 1, 1, 1]])
        caps = np.array([3, 3])
        logits = np.zeros((2, 5, 48))
        logits[0, 0, 47] = 10000  # supported logits must be normalized directly
        b = frozen.potion_log_probabilities(logits, slots, caps)
        c = frozen.potion_log_probabilities(logits, slots, caps, np.array([True, False]))
        self.assertTrue(np.array_equal(b[1], c[1]))
        self.assertTrue(np.allclose(np.exp(c).sum(-1), 1))
        self.assertEqual(float(np.exp(c[0, 0, 2])), .5)
        self.assertEqual(float(np.exp(c[0, 2, 1])), 1)
        self.assertEqual(float(np.exp(c[0, 0, 47])), 0)
        self.assertTrue(np.all(np.isneginf(c[..., 0])))
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            frozen.potion_log_probabilities(np.full_like(logits, np.nan), slots, caps)
        with self.assertRaises(ValueError):
            frozen.allowed_potion_support(np.array([[0, 1, 1, 1, 1]]), np.array([3]))

    def test_nochange_probability_invalid_mass_and_nll_monotonicity(self):
        slots = np.array([[2, 3, 1, 1, 1]])
        caps = np.array([3])
        logits = np.zeros((1, 5, 48))
        b = frozen.potion_log_probabilities(logits, slots, caps)
        c = frozen.potion_log_probabilities(logits, slots, caps, np.array([True]))
        allowed = frozen.allowed_potion_support(slots, caps)
        invalid = 1 - np.where(allowed, np.exp(b), 0).sum(-1).prod(-1)
        self.assertAlmostEqual(invalid[0], 1 - 4 / 47**3)
        for target in (slots, np.array([[1, 1, 1, 1, 1]])):
            sb = frozen.potion_row_scores(b, target, slots, caps)
            sc = frozen.potion_row_scores(c, target, slots, caps)
            self.assertLessEqual(sc["vectorNll"][0], sb["vectorNll"][0])
            self.assertAlmostEqual(sc["noChangeProbability"][0], .25)
        impossible = np.array([[3, 2, 1, 1, 1]])
        with self.assertRaisesRegex(ValueError, "zero probability"):
            frozen.potion_row_scores(c, impossible, slots, caps)

    def test_exact_composition_and_joint_nll_identity(self):
        a = {"pWin": np.array([.7, .2]), "pDelta": np.array([[.6, .4], [.6, .4]]),
             "hpConditional": np.array([[[.3, .7], [.5, .5]], [[.3, .7], [.5, .5]]]),
             "potionLogits": np.zeros((2, 5, 48)), "relicLogits": np.zeros((2, 64, 19))}
        p = np.array([.8, .1])
        b = frozen.compose_predictions(a, p)
        self.assertIs(b["pWin"], p)
        for key in a:
            if key != "pWin":
                self.assertIs(a[key], b[key])
        arrays = {"y_win": np.array([1, 0]), "delta_index": np.array([1, -1]), "y_hp_bin": np.array([0, -1])}
        ids = np.arange(2)
        delta = frozen.joint_nll(arrays, ids, b) - frozen.joint_nll(arrays, ids, a)
        self.assertTrue(np.allclose(delta, frozen.outcome_nll(arrays["y_win"], p)
                                    - frozen.outcome_nll(arrays["y_win"], a["pWin"])))
        self.assertAlmostEqual(frozen.joint_nll(arrays, ids, b)[1], -np.log(.9))

    def test_death_terminates_before_state_access(self):
        prediction = {"pWin": 0., "pDelta": np.array([1.]), "hpConditional": np.array([[1.]]),
                      "potionProbs": np.eye(48)[np.ones(5, dtype=int)]}
        self.assertIsNone(frozen.sample_prediction({}, prediction, {}, np.random.default_rng(1)))
        prediction["potionProbs"][0] = 0
        with self.assertRaisesRegex(ValueError, "invalid sampler"):
            frozen.sample_prediction({}, prediction, {}, np.random.default_rng(1))

    def test_draw_preserves_support_and_derives_count(self):
        pre = {key: [] for key in frozen.base.PERSISTENT_KEYS}
        pre.update(maxHp=80, curHp=60, gold=10, stolenGold=0, potionCapacity=3,
                   potions=[2, 3, 1, 4, 1], potionCount=3, relics=[])
        spec = {"maxHpDeltaValues": [0], "relicDeltaValues": [0]}
        for target in ([2, 3, 1, 4, 1], [1, 1, 1, 4, 1]):
            pred = {"pWin": 1., "pDelta": np.array([1.]), "hpConditional": np.array([[1.]]),
                    "potionProbs": np.eye(48)[target], "relicDeltaProbs": {}}
            sampled = frozen.sample_prediction(pre, pred, spec, np.random.default_rng(1))
            self.assertEqual(sampled["potions"], target)
            self.assertEqual(sampled["potionCount"], sum(p > 1 for p in target))
            self.assertEqual(pre["potions"], [2, 3, 1, 4, 1])
        pred["potionProbs"][0] = 0
        pred["potionProbs"][0, [1, 2]] = [.1, .9]
        for _ in range(20):
            sample = frozen.sample_prediction(pre, pred, spec, np.random.default_rng(_))
            self.assertIn(sample["potions"][0], (1, 2))

    def test_paired_bootstrap_resamples_groups_and_is_deterministic(self):
        seeds = np.array([1, 1, 2])
        diffs = {"delta": np.array([1., 1., -1.])}
        first = frozen.paired_bootstrap(seeds, diffs, reps=100)
        self.assertEqual(first, frozen.paired_bootstrap(seeds, diffs, reps=100))
        self.assertAlmostEqual(first["delta"]["mean"], 1/3)
        self.assertEqual(first["delta"]["sources"], 2)


if __name__ == "__main__":
    unittest.main()
