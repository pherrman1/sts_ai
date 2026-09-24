import copy
import unittest

import numpy as np

from tools import combat_transition_lizard_minimal as minimal
from tools import combat_transition_lizard_pair_pilot as pilot


class MinimalLizardTests(unittest.TestCase):
    def test_fixed_hp_treatments(self):
        self.assertEqual(minimal.hp_treatment(37, 80, 'T0_ordinary'), 37)
        self.assertEqual(minimal.hp_treatment(37, 80, 'T1_reserve'), 77)
        self.assertEqual(minimal.hp_treatment(60, 80, 'T1_reserve'), 80)
        self.assertEqual(minimal.hp_treatment(37, 80, 'T2_revive'), 40)
        with self.assertRaises(ValueError):
            minimal.hp_treatment(0, 80, 'T0_ordinary')

    def test_transformed_hp_envelope_exclusions_count_as_domain_failures(self):
        self.assertEqual(minimal.transformed_hp_domain_issue_count({
            'unsupported:hp_envelope': 2,
            'transformed_HP_target_outside_frozen_domain': 1,
            'unsupported:ritual_dagger': 4,
        }), 3)

    def test_three_class_mechanical_probabilities_conserve_mass(self):
        probabilities = minimal.legal_class_probabilities(.2, .7)
        self.assertEqual(probabilities, (.2, .49999999999999994, .30000000000000004))
        self.assertAlmostEqual(sum(probabilities), 1.0)
        self.assertIsNone(minimal.legal_class_probabilities(.7, .2))
        # Harmless floating point inversion is tolerated, meaningful inversion is not.
        self.assertEqual(minimal.legal_class_probabilities(.5, .5-1e-13)[1], 0.0)

    def test_impossible_loss_retained_has_zero_class_support(self):
        with self.assertRaisesRegex(ValueError, 'LOSS_RETAINED'):
            minimal.legal_outcome_label(pilot.DEATH, 1)
        self.assertEqual(minimal.legal_outcome_label(pilot.DEATH, 0), minimal.LOSS_CONSUMED)
        self.assertEqual(minimal.legal_outcome_label(pilot.WIN, 1), minimal.WIN_RETAINED)
        self.assertEqual(minimal.legal_outcome_label(pilot.WIN, 0), minimal.WIN_CONSUMED)

    def test_fairy_potion_and_bloom_are_native_calibration_boundaries(self):
        bloom = minimal.composed.base._RELIC_IDS['MARK_OF_THE_BLOOM']
        fairy = minimal.composed.base._POTION_IDS['FAIRY_POTION']
        pair = {'activeTail': {'transition': {'pre': {'relics': [], 'potions': []}}}}
        self.assertEqual(minimal.native_boundary_reasons(pair), [])
        pair['activeTail']['transition']['pre']['potions'] = [fairy]
        self.assertEqual(minimal.native_boundary_reasons(pair), ['fairy_potion_precedence_exact_boundary'])
        pair['activeTail']['transition']['pre']['relics'] = [{'id': bloom, 'data': 0}]
        self.assertEqual(set(minimal.native_boundary_reasons(pair)), {
            'mark_of_bloom_exact_boundary', 'fairy_potion_precedence_exact_boundary'})

    def test_source_grouped_folds_keep_repeated_source_together(self):
        folds = minimal.source_group_folds([11, 12, 11, 13, 14, 12, 15, 16], folds=3)
        self.assertEqual(folds[0], folds[2])
        self.assertEqual(folds[1], folds[5])
        self.assertEqual(len(set(folds)), 3)
        np.testing.assert_array_equal(folds, minimal.source_group_folds(
            [11, 12, 11, 13, 14, 12, 15, 16], folds=3))

    def test_feature_builder_ignores_outcome_poststate_and_action_trace(self):
        pair = {
            'pair': {'sourceSeed': 100, 'activeTailPostData': 0,
                     'activeTailOutcome': pilot.DEATH},
            'noTail': {'predictorInput': {'globals': {'curHp': 20, 'maxHp': 80}}},
            'activeTail': {'transition': {'combatOutcome': pilot.DEATH,
                                          'post': {'curHp': 0}},
                           'silverActionTraceBits': [1, 2, 3]},
        }

        class Models:
            def encode_visible(self, predictor):
                return predictor['globals']['curHp']

            def survival(self, visible_hp):
                return visible_hp / 100.0

        first = minimal._precombat_risk_features([pair], Models())
        mutated = copy.deepcopy(pair)
        mutated['activeTail']['transition']['combatOutcome'] = pilot.WIN
        mutated['activeTail']['transition']['post']['curHp'] = 73
        mutated['activeTail']['silverActionTraceBits'] = [99]
        mutated['pair']['activeTailPostData'] = 1
        second = minimal._precombat_risk_features([mutated], Models())
        self.assertEqual(first, second)
        q1, r1 = minimal.factorized_feature_arrays(first)
        q2, r2 = minimal.factorized_feature_arrays(second)
        np.testing.assert_array_equal(q1, q2)
        np.testing.assert_array_equal(r1, r2)

    def test_cross_validation_is_deterministic_and_factorized_probabilities_conserve(self):
        records = []
        for index in range(30):
            records.append({
                'sourceSeed': 1000 + index,
                'pDeath': .05 + .025 * (index % 10),
                'pOrdinaryWin': 1 - (.05 + .025 * (index % 10)),
                'pReserveWin': min(.99, 1 - (.05 + .025 * (index % 10)) + .15),
                'reserveUplift': .15,
                'label': (index % 3),
            })
        left = minimal._factorized_cv(records, folds=5)
        right = minimal._factorized_cv(records, folds=5)
        np.testing.assert_allclose(
            [row['classProbabilities'] for row in left['correction']['outOfFoldProbabilitiesBySource']],
            [row['classProbabilities'] for row in right['correction']['outOfFoldProbabilitiesBySource']],
        )
        for row in left['correction']['outOfFoldProbabilitiesBySource']:
            self.assertAlmostEqual(sum(row['classProbabilities']), 1.0)
            self.assertTrue(all(0 <= value <= 1 for value in row['classProbabilities']))

    def test_q_r_features_are_only_fixed_prediction_features(self):
        records = [
            {'pDeath': .2, 'pOrdinaryWin': .8, 'pReserveWin': .9, 'label': 0,
             'sourceSeed': 1, 'postHp': 12, 'silverActionTraceBits': [9]},
            {'pDeath': .5, 'pOrdinaryWin': .5, 'pReserveWin': .8, 'label': 2,
             'sourceSeed': 2, 'postHp': 1, 'silverActionTraceBits': [4]},
        ]
        q_before, r_before = minimal.factorized_feature_arrays(records)
        for row in records:
            row['label'] = 2-row['label']
            row['postHp'] += 20
            row['silverActionTraceBits'] = [0]
        q_after, r_after = minimal.factorized_feature_arrays(records)
        np.testing.assert_array_equal(q_before, q_after)
        np.testing.assert_array_equal(r_before, r_after)


if __name__ == '__main__':
    unittest.main()
