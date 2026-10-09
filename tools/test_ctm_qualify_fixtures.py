"""#418 G22: qualify builds a fail-closed fixture for an exclusion the TEST split lacks."""
import unittest

from tools import combat_transition_composed as c
from tools import qualify_combat_transition_near_full as q


def row(index):
    return dict(index=index, pi=dict(globals=dict(encounter=0)),
                pre=dict(potions=[1, 1, 1], smokeBombUsed=False, deck=[]))


class TestSyntheticExclusions(unittest.TestCase):
    def test_pre_state_exclusions_are_synthesized(self):
        for label in ('smoke_bomb', 'pre_smoke_bomb_used'):
            fixture = q.synthetic_exclusion([row(7)], label)
            self.assertEqual(fixture['synthetic'], label)
            self.assertEqual(q.support.final_exclusions(fixture['pi'], fixture['pre']), [label])
        self.assertIn(c.base._POTION_IDS['SMOKE_BOMB'], q.synthetic_exclusion([row(7)], 'smoke_bomb')['pre']['potions'])

    def test_other_labels_still_need_a_real_row(self):
        with self.assertRaisesRegex(ValueError, 'no TEST row'):
            q.synthetic_exclusion([row(7)], 'writhing_ritual_intersection')


if __name__ == '__main__':
    unittest.main()
