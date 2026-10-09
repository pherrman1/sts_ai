"""Brew-generated escapes are a reported exposure slice, kept out of every gated cohort (#418)."""
import unittest

import numpy as np

from tools import combat_transition_near_full_exposure as exposure
from tools import combat_transition_potion_trajectory as t


class TestExposureCohorts(unittest.TestCase):
    def test_brew_generated_escapes_leave_the_gated_cohorts(self):
        # Row 0 ordinary win, row 1 escape with a Smoke Bomb held, row 2 escape with no Smoke Bomb before combat.
        potions = np.zeros((3, 5), np.int64)
        potions[1, 0] = t.SMOKE
        potions[2, 0] = t.BREW
        test = dict(potions=potions, old=np.array([True, True, False]), writhing=np.zeros(3, bool),
                    dagger=np.zeros(3, bool), escaped=np.array([0, 1, 1]))
        rows = [dict(pi=dict(cards=[])) for _ in range(3)]
        cohorts = exposure.cohort_masks(test, np.arange(3), rows, records=set(), recursive_ids=set())
        self.assertEqual(cohorts['brewGeneratedEscape'].tolist(), [False, False, True])
        self.assertEqual(cohorts['escape'].tolist(), [False, True, False])
        self.assertEqual(cohorts['entireFinalUnion'].tolist(), [True, True, False])
        self.assertEqual(cohorts['brew'].tolist(), [False, False, False])
        self.assertIn('brewGeneratedEscape', exposure.DIAGNOSTIC_COHORTS)

    def test_only_gated_entries_block_export(self):
        report = dict(components=dict(relic=dict(
            entireFinalUnion=dict(gate=True, zeroExactMassRows=0, diagnosticOnly=False),
            brewGeneratedEscape=dict(gate=False, zeroExactMassRows=0, diagnosticOnly=True))))
        self.assertEqual([v['gate'] for v in exposure.gated_entries(report)], [True])


if __name__ == '__main__':
    unittest.main()
