import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import combat_transition_lizard_qr_artifact as qr
from tools.combat_transition_lizard_minimal import LOSS_CONSUMED, WIN_CONSUMED, WIN_RETAINED


class LizardQrArtifactTests(unittest.TestCase):
    def test_frozen_fit_is_deterministic_and_three_classes_are_coherent(self):
        records = [
            {'pDeath': .10, 'pOrdinaryWin': .90, 'pReserveWin': .97, 'label': WIN_RETAINED},
            {'pDeath': .20, 'pOrdinaryWin': .80, 'pReserveWin': .95, 'label': WIN_RETAINED},
            {'pDeath': .35, 'pOrdinaryWin': .65, 'pReserveWin': .92, 'label': WIN_CONSUMED},
            {'pDeath': .50, 'pOrdinaryWin': .50, 'pReserveWin': .85, 'label': LOSS_CONSUMED},
            {'pDeath': .25, 'pOrdinaryWin': .75, 'pReserveWin': .98, 'label': WIN_CONSUMED},
            {'pDeath': .40, 'pOrdinaryWin': .60, 'pReserveWin': .90, 'label': WIN_RETAINED},
        ]
        first = qr.fit_qr_models(records)
        second = qr.fit_qr_models(records)
        self.assertEqual(first, second)
        artifact = {
            'schema': qr.ARTIFACT_SCHEMA,
            'qFeatureOrder': qr.Q_FEATURES,
            'rFeatureOrder': qr.R_FEATURES,
            't2Rule': qr.T2_RULE,
            'frozenCtmComponentHashes': {'survival': 'a' * 64},
            **{key: first[key] for key in ('qModel', 'rModel')},
        }
        q, r, classes = qr.predict_qr(.7, .94, artifact)
        self.assertGreaterEqual(q, 0)
        self.assertLessEqual(q, 1)
        self.assertGreaterEqual(r, 0)
        self.assertLessEqual(r, 1)
        self.assertAlmostEqual(sum(classes), 1.0)
        self.assertEqual(classes, [1-q, q*r, q*(1-r)])

    def test_signed_reserve_minus_ordinary_feature_is_not_clipped(self):
        artifact = {'qModel': 'q', 'rModel': 'r'}
        seen = []

        def fixed_prediction(model, features):
            seen.append((model, float(features[0, 1]) if model == 'q'
                         else float(features[0, 0])))
            return [.25 if model == 'q' else .75]

        with mock.patch.object(qr, '_model_predict', side_effect=fixed_prediction):
            q, r, classes = qr.predict_qr(.80, .60, artifact)
        self.assertTrue(0 <= q <= 1)
        self.assertTrue(0 <= r <= 1)
        self.assertEqual(seen[0][0], 'q')
        self.assertAlmostEqual(seen[0][1], -.20)
        self.assertEqual(seen[1][0], 'r')
        self.assertAlmostEqual(seen[1][1], .60)
        self.assertAlmostEqual(sum(classes), 1.0)

    def test_artifact_hash_and_schema_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'artifact.json'
            path.write_text('{"schema":"wrong"}\n')
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                qr.load_artifact(path, '0' * 64)
            with self.assertRaisesRegex(ValueError, 'schema'):
                qr.load_artifact(path, actual)

    def test_hard_max_risk_and_broad_hash_selection_are_fixed(self):
        hard = list(range(1000, 1096))
        broad = list(range(1096, 1128))
        rows = []
        for source in hard:
            rows.extend([
                {'sourceSeed': source, 'fightIdx': 8, 'pLossConsumed': .25},
                {'sourceSeed': source, 'fightIdx': 3, 'pLossConsumed': .25},
            ])
        for source in broad:
            rows.extend([
                {'sourceSeed': source, 'fightIdx': 2, 'pLossConsumed': .01},
                {'sourceSeed': source, 'fightIdx': 9, 'pLossConsumed': .95},
            ])
        salt = 'fixed-test-salt'
        selected = qr.select_precomputed(rows, hard, broad, salt)
        by_source = {row['sourceSeed']: row for row in selected}
        self.assertEqual(len(selected), 128)
        self.assertTrue(all(by_source[source]['fightIdx'] == 3 for source in hard))
        for source in broad:
            expected = min((2, 9), key=lambda fight: hashlib.sha256(
                f'{source}:{fight}:{salt}'.encode()).hexdigest())
            self.assertEqual(by_source[source]['fightIdx'], expected)
            self.assertIn('broadSelectionHash', by_source[source])

    def test_selection_does_not_use_outcome_fields(self):
        hard = list(range(96))
        broad = list(range(96, 128))
        rows = []
        for source in hard + broad:
            rows.append({'sourceSeed': source, 'fightIdx': 0, 'pLossConsumed': .2,
                         'outcome': 'WIN_RETAINED'})
            rows.append({'sourceSeed': source, 'fightIdx': 1, 'pLossConsumed': .3,
                         'outcome': 'LOSS_CONSUMED'})
        first = qr.select_precomputed(rows, hard, broad, 'same')
        for row in rows:
            row['outcome'] = 'opposite'
        second = qr.select_precomputed(rows, hard, broad, 'same')
        self.assertEqual([(r['sourceSeed'], r['fightIdx']) for r in first],
                         [(r['sourceSeed'], r['fightIdx']) for r in second])

    def test_invalid_postcombat_candidate_aborts_instead_of_being_skipped(self):
        with self.assertRaisesRegex(ValueError, 'refusing outcome-dependent selection'):
            qr.require_valid_candidate_row({'runValid': False}, 7)
        qr.require_valid_candidate_row({'runValid': True}, 8)

    def test_relative_manifest_path_cannot_escape_evidence_packet(self):
        from tools import combat_transition_lizard_pair_pilot as pilot

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = root / 'packet'
            packet.mkdir()
            (packet / 'outside.jsonl').write_text('inside packet sibling')
            with self.assertRaisesRegex(ValueError, 'escapes packet'):
                pilot._resolve_manifest_file('../outside.jsonl', packet)


if __name__ == '__main__':
    unittest.main()
