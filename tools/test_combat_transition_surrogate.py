import unittest

import numpy as np

try:
    from tools.combat_predictor_input_contract import FIELD_SCHEMA_HASH, SCHEMA_VERSION
    from tools.combat_transition_surrogate import (
        CODE_AUDITED_MUTABLE_RELIC_IDS,
        EMPTY_POTION_SLOT_ID,
        ENTROPIC_BREW_ID,
        GOLD_MUTATING_ENCOUNTER_IDS,
        GOLD_MUTATING_POTION_IDS,
        GOLD_MUTATING_RELIC_IDS,
        HAND_OF_GREED_ID,
        JACK_OF_ALL_TRADES_ID,
        IRONCLAD_ID,
        MAX_RELICS,
        RITUAL_DAGGER_ID,
        SMOKE_BOMB_ID,
        TRANSMUTATION_ID,
        WRITHING_MASS_ID,
        _sample_persistent_transition,
        _exact_accuracy,
        _transition_metrics,
        _prepare_target_indices,
        _normalise_sampling_probabilities,
        hp_fraction_bin,
        supported_for_surrogate,
        supported_reasons,
        validate_sampled_state,
    )
except ModuleNotFoundError:
    from combat_predictor_input_contract import FIELD_SCHEMA_HASH, SCHEMA_VERSION
    from combat_transition_surrogate import (
        CODE_AUDITED_MUTABLE_RELIC_IDS,
        EMPTY_POTION_SLOT_ID,
        ENTROPIC_BREW_ID,
        GOLD_MUTATING_ENCOUNTER_IDS,
        GOLD_MUTATING_POTION_IDS,
        GOLD_MUTATING_RELIC_IDS,
        HAND_OF_GREED_ID,
        JACK_OF_ALL_TRADES_ID,
        IRONCLAD_ID,
        MAX_RELICS,
        RITUAL_DAGGER_ID,
        SMOKE_BOMB_ID,
        TRANSMUTATION_ID,
        WRITHING_MASS_ID,
        _sample_persistent_transition,
        _exact_accuracy,
        _transition_metrics,
        _prepare_target_indices,
        _normalise_sampling_probabilities,
        hp_fraction_bin,
        supported_for_surrogate,
        supported_reasons,
        validate_sampled_state,
    )


def predictor(encounter=1, card_id=10, potion_id=EMPTY_POTION_SLOT_ID, character_class=IRONCLAD_ID):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "fieldSchemaHash": FIELD_SCHEMA_HASH,
        "globals": {
            "characterClass": character_class, "ascension": 0, "act": 1, "floor": 1,
            "curHp": 40, "maxHp": 80, "gold": 99, "encounter": encounter,
            "roomClass": 4, "lastRoom": 1, "potionCount": int(potion_id > EMPTY_POTION_SLOT_ID),
            "potionCapacity": 3, "potionKeepValue": 4.0, "isBurningElite": False,
        },
        "cards": [{"cardId": card_id, "misc": 0, "upgraded": False, "bottleBinding": -1}],
        "relics": [{"relicId": 26, "data": 0, "orderIndex": 0}],
        "potions": [{"slot": i, "potionId": potion_id if i == 0 else EMPTY_POTION_SLOT_ID} for i in range(5)],
    }


def state():
    return {
        "curHp": 10, "maxHp": 20, "gold": 100, "potionCount": 1,
        "potionCapacity": 3, "potions": [2, EMPTY_POTION_SLOT_ID, EMPTY_POTION_SLOT_ID, EMPTY_POTION_SLOT_ID, EMPTY_POTION_SLOT_ID],
        "smokeBombUsed": False, "stolenGold": 0,
        "relics": [{"id": 26, "data": 0}, {"id": 0, "data": 3}],
        "relicBits": [1, 2, 3],
        "deck": [{"id": 10, "misc": 0, "upgraded": False}],
        "cardTypeCounts": [1, 0, 0, 0], "bottleIdxs": [-1, -1, -1],
        "upgradeableCount": 1, "transformableCount": 1,
        "combatRng": [{"counter": 0, "seed0": 1, "seed1": 2} for _ in range(6)],
    }


class TestCombatTransitionSurrogate(unittest.TestCase):
    def test_support_predicate_is_predictor_visible_and_fail_closed(self):
        self.assertTrue(supported_for_surrogate(predictor(), state()))
        cases = (
            ("writhing_mass", predictor(encounter=WRITHING_MASS_ID)),
            ("ritual_dagger", predictor(card_id=RITUAL_DAGGER_ID)),
            ("smoke_bomb", predictor(potion_id=SMOKE_BOMB_ID)),
            ("entropic_brew", predictor(potion_id=ENTROPIC_BREW_ID)),
            ("gold_mutating_potion", predictor(potion_id=next(iter(GOLD_MUTATING_POTION_IDS)))),
            ("gold_mutating_card", predictor(card_id=HAND_OF_GREED_ID)),
            ("gold_mutating_card", predictor(card_id=JACK_OF_ALL_TRADES_ID)),
            ("gold_mutating_card", predictor(card_id=TRANSMUTATION_ID)),
            ("non_ironclad", predictor(character_class=IRONCLAD_ID + 1)),
        ) + tuple(
            ("gold_mutating_encounter", predictor(encounter=encounter))
            for encounter in sorted(GOLD_MUTATING_ENCOUNTER_IDS)
        )
        toolbox = predictor()
        toolbox["relics"][0]["relicId"] = next(iter(GOLD_MUTATING_RELIC_IDS))
        cases += (("gold_mutating_relic", toolbox),)
        for reason, value in cases:
            with self.subTest(reason=reason):
                self.assertFalse(supported_for_surrogate(value, state()))
                self.assertIn(reason, supported_reasons(value, state()))
        pre_smoke = state()
        pre_smoke["smokeBombUsed"] = True
        self.assertFalse(supported_for_surrogate(predictor(), pre_smoke))
        self.assertIn("pre_smoke_bomb_used", supported_reasons(predictor(), pre_smoke))
        pre_stolen = state()
        pre_stolen["stolenGold"] = 1
        self.assertFalse(supported_for_surrogate(predictor(), pre_stolen))
        self.assertIn("pre_stolen_gold_nonzero", supported_reasons(predictor(), pre_stolen))

    def test_hp_bins_use_round_half_up_and_are_bounded(self):
        self.assertEqual(hp_fraction_bin(1, 3), 33)
        self.assertEqual(hp_fraction_bin(2, 3), 67)
        self.assertEqual(hp_fraction_bin(0, 80), 0)
        self.assertEqual(hp_fraction_bin(80, 80), 100)

    def test_sampled_transition_uses_copy_through_and_masked_delta_classes(self):
        pre = state()
        target_spec = {
            "maxHpDeltaValues": [0, 5],
            "relicDeltaValues": [0, 6],
            "relicDeltaValuesById": {"26": [0, 6]},
        }
        potion_probs = np.zeros((5, 48), dtype=np.float64)
        potion_probs[:, EMPTY_POTION_SLOT_ID] = 1.0
        potion_probs[0, 2] = 1.0
        potion_probs[0, EMPTY_POTION_SLOT_ID] = 0.0
        relic_probs = {"26": np.asarray([0.0, 1.0])}
        prediction = {
            "pWin": 1.0,
            "pDelta": np.asarray([0.0, 1.0]),
            "hpConditional": np.eye(101, dtype=np.float64)[[50, 50]],
            "potionProbs": potion_probs,
            "relicDeltaProbs": relic_probs,
        }
        sampled = _sample_persistent_transition(
            pre, prediction, target_spec, np.random.default_rng(7)
        )
        self.assertIsNotNone(sampled)
        self.assertNotIn("combatRng", sampled)
        self.assertEqual(sampled["maxHp"], 25)
        self.assertEqual(sampled["curHp"], 13)
        self.assertEqual(sampled["potions"][0], 2)
        self.assertEqual(sampled["potionCount"], 1)
        self.assertEqual(sampled["relics"][0]["data"], 6)
        self.assertEqual(sampled["relics"][1], pre["relics"][1])
        self.assertEqual(sampled["gold"], pre["gold"])
        self.assertEqual(sampled["stolenGold"], pre["stolenGold"])
        self.assertFalse(sampled["smokeBombUsed"])
        validate_sampled_state(pre, sampled, target_spec)

    def test_sampled_hp_bin_50_at_post_max_80_is_exactly_40(self):
        pre = state()
        pre["curHp"] = 40
        pre["maxHp"] = 80
        target_spec = {
            "maxHpDeltaValues": [0],
            "relicDeltaValues": [0],
            "relicDeltaValuesById": {"26": [0]},
        }
        prediction = {
            "pWin": 1.0,
            "pDelta": np.asarray([1.0]),
            "hpConditional": np.eye(101, dtype=np.float64)[[50]],
            "potionProbs": np.eye(48, dtype=np.float64)[EMPTY_POTION_SLOT_ID][None, :].repeat(5, axis=0),
            "relicDeltaProbs": {"26": np.asarray([1.0])},
        }
        sampled = _sample_persistent_transition(pre, prediction, target_spec, np.random.default_rng(3))
        self.assertIsNotNone(sampled)
        self.assertEqual(sampled["maxHp"], 80)
        self.assertEqual(sampled["curHp"], 40)

    def test_structured_exact_match_is_rowwise(self):
        potions_actual = np.asarray([[1, 2, 3, 4, 5], [1, 2, 3, 4, 5]])
        potions_predicted = np.asarray([[1, 2, 3, 4, 5], [1, 2, 3, 4, 6]])
        self.assertEqual(_exact_accuracy(potions_actual, potions_predicted), 0.5)
        hp_actual = np.asarray([[40, 80], [40, 80]])
        hp_predicted = np.asarray([[40, 80], [41, 80]])
        self.assertEqual(_exact_accuracy(hp_actual, hp_predicted), 0.5)

    def test_relic_exact_match_compares_predicted_post_state_to_actual_post_state(self):
        arrays = {
            "y_win": np.asarray([1, 1]),
            "preHpFrac": np.asarray([0.5, 0.5], dtype=np.float32),
            "preMaxHp": np.asarray([20, 20], dtype=np.int16),
            "y_post_hp": np.asarray([10, 10], dtype=np.int16),
            "y_post_max_hp": np.asarray([20, 20], dtype=np.int16),
            "y_hp_bin": np.asarray([50, 50], dtype=np.int8),
            "potionCapacity": np.asarray([1, 1], dtype=np.int8),
            "potions": np.zeros((2, 5, 2), dtype=np.int16),
            "y_potions": np.zeros((2, 5), dtype=np.int16),
            "relics": np.zeros((2, MAX_RELICS, 3), dtype=np.int16),
            "y_relic_delta": np.zeros((2, MAX_RELICS), dtype=np.int16),
            "y_relic_mask": np.zeros((2, MAX_RELICS), dtype=np.bool_),
        }
        arrays["relics"][:, 0, 0] = 26
        arrays["y_relic_delta"][0, 0] = 6
        arrays["y_relic_mask"][:, 0] = True
        predictions = {
            "pDelta": np.ones((2, 1), dtype=np.float64),
            "hpConditional": np.eye(101, dtype=np.float64)[[50, 50]][:, None, :],
            "potionLogits": np.full((2, 5, 48), -100.0),
            "relicLogits": np.zeros((2, MAX_RELICS, 2), dtype=np.float64),
        }
        predictions["potionLogits"][:, :, 0] = 100.0
        predictions["relicLogits"][0, 0] = [0.0, 1.0]
        predictions["relicLogits"][1, 0] = [1.0, 0.0]
        target_spec = {
            "maxHpDeltaValues": [0],
            "relicDeltaValues": [0, 6],
            "relicDeltaValuesById": {"26": [0, 6]},
        }
        metrics = _transition_metrics(
            arrays, target_spec, np.asarray([0, 1]), predictions, test_rows=2
        )
        self.assertEqual(metrics["relicCounters"]["exactAllCounterVectorAccuracy"], 1.0)
        self.assertEqual(
            metrics["relicCounters"]["copyThroughBaseline"]["exactAllCounterVectorAccuracy"],
            0.5,
        )

    def test_sampler_normalizes_softmax_roundoff_before_choice(self):
        probabilities = _normalise_sampling_probabilities(np.asarray([0.2, 0.8000001]))
        self.assertEqual(float(probabilities.sum()), 1.0)
        self.assertTrue(np.all(probabilities >= 0.0))

    def test_mutable_relic_audit_is_nonempty_and_includes_raw_omamori(self):
        self.assertTrue(CODE_AUDITED_MUTABLE_RELIC_IDS)
        self.assertIn(46, CODE_AUDITED_MUTABLE_RELIC_IDS)

    def test_target_index_preparation_ignores_fallback_and_death_labels(self):
        arrays = {
            "y_max_hp_delta": np.asarray([0, 999]),
            "y_relic_delta": np.asarray([[0, 0], [999, 0]]),
            "y_relic_mask": np.asarray([[True, False], [True, False]]),
            "supported": np.asarray([True, False]),
            "y_win": np.asarray([1, 0]),
        }
        target_spec = {
            "maxHpDeltaValues": [0],
            "relicDeltaValues": [0],
        }
        _prepare_target_indices(arrays, target_spec)
        self.assertEqual(arrays["delta_index"].tolist(), [0, -1])
        self.assertEqual(arrays["relic_delta_index"].tolist(), [[0, 0], [-1, 0]])


if __name__ == "__main__":
    unittest.main()
