import unittest
from unittest.mock import patch

from tools import combat_transition_composed as composed
from tools import combat_transition_lizard_offline_audit as audit


class OfflineLizardAuditTest(unittest.TestCase):
    def test_exception_is_active_lizard_only_and_restored(self):
        original = composed.relic.legal_posts
        lizard = composed.base._RELIC_IDS['LIZARD_TAIL']
        flower = composed.base._RELIC_IDS['HAPPY_FLOWER']
        seen = {}

        def probe(pre, pi, models):
            seen['active'] = composed.relic.legal_posts(lizard, 1, 0, False)
            seen['spent'] = composed.relic.legal_posts(lizard, 0, 0, False)
            seen['flower'] = composed.relic.legal_posts(flower, 0, 0, False)
            return []

        pre = {'relics': [{'id': lizard, 'data': 1}]}
        with patch.object(composed, 'full_support_reasons', side_effect=probe):
            self.assertEqual(audit.offline_reasons(pre, {}, None), [])
        self.assertEqual(seen['active'], frozenset({1}))
        self.assertEqual(seen['spent'], frozenset({0}))
        self.assertEqual(seen['flower'], original(flower, 0, 0, False))
        self.assertIs(composed.relic.legal_posts, original)

    def test_mark_of_bloom_keeps_original_lizard_rule_and_restores_on_error(self):
        original = composed.relic.legal_posts
        lizard = composed.base._RELIC_IDS['LIZARD_TAIL']
        bloom = composed.base._RELIC_IDS['MARK_OF_THE_BLOOM']
        seen = {}

        def probe(pre, pi, models):
            seen['allowed'] = composed.relic.legal_posts(lizard, 1, 0, True)
            raise RuntimeError('probe')

        pre = {'relics': [{'id': lizard, 'data': 1}, {'id': bloom, 'data': 0}]}
        with patch.object(composed, 'full_support_reasons', side_effect=probe):
            with self.assertRaisesRegex(RuntimeError, 'probe'):
                audit.offline_reasons(pre, {}, None)
        self.assertEqual(seen['allowed'], frozenset({1}))
        self.assertIs(composed.relic.legal_posts, original)

    def test_unmodeled_mutable_counter_is_excluded_from_offline_support(self):
        lizard = composed.base._RELIC_IDS['LIZARD_TAIL']
        omamori = composed.base._RELIC_IDS['OMAMORI']
        encounter = composed.base._ENCOUNTER_IDS['WRITHING_MASS']
        pre = {'relics': [{'id': lizard, 'data': 1}, {'id': omamori, 'data': 2}]}
        pi = {'globals': {'encounter': encounter}}
        with patch.object(composed, 'full_support_reasons', return_value=[]):
            self.assertEqual(audit.offline_reasons(pre, pi, None),
                             ['unmodeled_mutable_relic:OMAMORI'])


if __name__ == '__main__':
    unittest.main()
