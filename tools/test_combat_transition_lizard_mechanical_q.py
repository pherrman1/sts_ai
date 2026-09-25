import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from tools import analyze_combat_transition_lizard_mechanical_q as analyzer
from tools import combat_transition_lizard_mechanical_q as candidate
from tools import combat_transition_lizard_pair_pilot as pilot


ARTIFACT = (Path(__file__).parents[1] / 'docs/experiments/evidence'
            / 'lizard_tail_mechanical_q_qualification_2026-09-25'
            / 'frozen_qr_artifact.json')
EXPECTED_ARTIFACT_SHA = candidate.OLD_QR_ARTIFACT_SHA256
PR326_R_PREDICTOR_AST_SHA = 'ffb5307c7e3e8d9b8c781c296bb3effe11e8d130ca32b6ea72bdbe825dfaace3'


class MechanicalQLizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact, cls.artifact_sha = candidate.load_frozen_qr_artifact(
            ARTIFACT, EXPECTED_ARTIFACT_SHA)

    def test_mechanical_q_and_class_masses_equal_b1_survival_factorization(self):
        for p_ordinary, p_reserve in ((.80, .94), (.51, .51), (1.0, 1.0), (0.0, .2)):
            q, r, probabilities = candidate.predict(p_ordinary, p_reserve, self.artifact)
            self.assertEqual(q, 1.0 - p_ordinary)
            self.assertEqual(probabilities[0], p_ordinary)
            self.assertEqual(probabilities[1], (1.0 - p_ordinary) * r)
            self.assertEqual(probabilities[2], (1.0 - p_ordinary) * (1.0 - r))
            self.assertAlmostEqual(sum(probabilities), 1.0, places=14)

    def test_old_learned_q_coefficients_cannot_change_candidate(self):
        baseline = candidate.predict(.73, .91, self.artifact)
        changed_q = copy.deepcopy(self.artifact)
        changed_q['qModel']['featureMean'] = [1e9, -1e9]
        changed_q['qModel']['featureScale'] = [1e-9, 1e9]
        changed_q['qModel']['standardizedCoefficients'] = [1e100, -1e100, 1e100]
        changed_q['qModel']['rawCoefficientsInterceptFirst'] = [-1e100, 1e100, -1e100]
        self.assertEqual(candidate.predict(.73, .91, changed_q), baseline)

    def test_frozen_r_predictor_matches_pr326_implementation_and_golden_values(self):
        self.assertEqual(candidate._predictor_ast_sha256(), PR326_R_PREDICTOR_AST_SHA)
        p_reserve = np.asarray([[0.0], [.1], [.2], [.5], [.9], [1.0]], dtype=np.float64)
        actual = candidate._model_predict(self.artifact['rModel'], p_reserve)
        expected = np.asarray([
            .16407224885987237,
            .23783483810152178,
            .3316042285597052,
            .6659685360085501,
            .9272099850884482,
            .9529454360127504,
        ], dtype=np.float64)
        np.testing.assert_array_equal(actual, expected)

    def test_candidate_manifest_binds_r_artifact_components_teacher_and_t2(self):
        frozen = candidate.build_candidate_manifest(self.artifact, self.artifact_sha)
        self.assertEqual(frozen['qMode'], 'mechanical_b1')
        self.assertEqual(frozen['rMode'], 'frozen_learned_r')
        self.assertEqual(frozen['treatment'], 'T2_revive')
        self.assertEqual(frozen['rArtifact']['sha256'], EXPECTED_ARTIFACT_SHA)
        self.assertEqual(frozen['frozenCtmComponentHashes'],
                         self.artifact['frozenCtmComponentHashes'])
        self.assertEqual(frozen['silverTeacher']['identity'],
                         self.artifact['teacherIdentity'])
        self.assertEqual(frozen['t2Rule'], candidate.T2_RULE)

    def test_t2_remains_floor_of_max_hp_over_two(self):
        self.assertEqual(candidate.revive_hp(81), 40)
        self.assertEqual(candidate.revive_hp(80), 40)
        with self.assertRaisesRegex(ValueError, 'maxHP'):
            candidate.revive_hp(1)

    def test_unsupported_and_exact_boundaries_fail_closed(self):
        models = object()
        bloom = candidate.composed.base._RELIC_IDS['MARK_OF_THE_BLOOM']
        fairy = candidate.composed.base._POTION_IDS['FAIRY_POTION']
        base = {'relics': [], 'potions': [], 'relicBits': [0]}
        predictor = {'relics': [], 'potions': [], 'globals': {}}
        with mock.patch.object(candidate.composed, 'full_support_reasons', return_value=[]):
            eligible, reason = candidate._eligible_support(
                {**base, 'relics': [{'id': bloom, 'data': 0}]}, predictor, models)
            self.assertFalse(eligible)
            self.assertEqual(reason, 'mark_of_bloom_exact_path')
            eligible, reason = candidate._eligible_support(
                {**base, 'potions': [fairy]}, predictor, models)
            self.assertFalse(eligible)
            self.assertEqual(reason, 'fairy_potion_exact_boundary')
            eligible, reason = candidate._eligible_support(base, predictor, models)
            self.assertTrue(eligible)
            self.assertIsNone(reason)
        with mock.patch.object(candidate.composed, 'full_support_reasons',
                               return_value=['fixture']):
            eligible, reason = candidate._eligible_support(base, predictor, models)
        self.assertFalse(eligible)
        self.assertEqual(reason, 'unsupported:fixture')

    def test_pair_target_selection_is_outcome_blind_with_exact_hard_tie_break(self):
        hard = list(range(4202000, 4202288))
        broad = list(range(4202288, 4202320))
        cohorts = {'HARD288': hard, 'BROAD32': broad}
        rows = []
        for source in hard:
            rows.extend([
                {'sourceSeed': source, 'fightIdx': 9, 'pLossConsumed': .2,
                 'outcome': 'WIN_RETAINED'},
                {'sourceSeed': source, 'fightIdx': 3, 'pLossConsumed': .2,
                 'outcome': 'LOSS_CONSUMED'},
            ])
        for source in broad:
            rows.extend([
                {'sourceSeed': source, 'fightIdx': 2, 'pLossConsumed': .01,
                 'outcome': 'LOSS_CONSUMED'},
                {'sourceSeed': source, 'fightIdx': 7, 'pLossConsumed': .4,
                 'outcome': 'WIN_CONSUMED'},
            ])
        salt = 'fixed-mechanical-q-screen-salt'
        first = candidate.select_precomputed(rows, cohorts, salt)
        for row in rows:
            row['outcome'] = 'changed-after-selection'
        second = candidate.select_precomputed(rows, cohorts, salt)
        self.assertEqual(first, second)
        by_source = {row['sourceSeed']: row for row in first}
        self.assertEqual(len(first), 320)
        self.assertTrue(all(by_source[source]['fightIdx'] == 3 for source in hard))
        for source in broad:
            expected = min((2, 7), key=lambda fight: hashlib.sha256(
                f'{source}:{fight}:{salt}'.encode()).hexdigest())
            self.assertEqual(by_source[source]['fightIdx'], expected)

    def test_fresh_source_assignment_is_audited_disjoint_and_predeclared(self):
        assignment = candidate.build_fresh_source_assignment()
        self.assertEqual(assignment['baselineGitSha'], candidate.FRESH_BASELINE_GIT_SHA)
        self.assertTrue(assignment['recordedBeforeCandidateOrPairCollection'])
        self.assertEqual(assignment['freshnessAudit']['auditResult'], 'FRESH_320_SOURCE_BLOCK')
        self.assertEqual(assignment['freshnessAudit']['previousUniqueSourceSeeds'], 367)
        self.assertEqual(assignment['freshnessAudit']['candidateBlockIntersection'], [])
        self.assertEqual(assignment['cohorts']['HARD288'], list(range(4202000, 4202288)))
        self.assertEqual(assignment['cohorts']['BROAD32'], list(range(4202288, 4202320)))
        self.assertEqual(assignment['broad32Salt'], candidate.FRESH_BROAD32_SALT)

    def test_fresh_candidate_pool_must_match_pinned_native_teacher(self):
        teacher_path = (Path(__file__).parents[1] / 'docs/experiments/evidence'
                        / 'lizard_tail_mechanical_q_qualification_2026-09-25'
                        / 'native_teacher_transfer/native_silver_teacher.json')
        teacher = json.loads(teacher_path.read_text())
        manifest = {
            'combatTeacher': copy.deepcopy(teacher),
            'producerGitSha': teacher['git_sha'],
            'producerExecutableSha256': teacher['executable_sha256'],
        }
        with mock.patch.object(candidate, 'sha256', return_value='a' * 64):
            actual, digest = candidate._validate_native_candidate_pool(manifest, teacher_path)
        self.assertEqual(actual, teacher)
        self.assertEqual(digest, 'a' * 64)
        changed = copy.deepcopy(manifest)
        changed['combatTeacher']['combat_backend'] = 'silver_uct'
        changed_teacher = copy.deepcopy(changed['combatTeacher'])
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_teacher_path = Path(temp_dir) / 'teacher.json'
            invalid_teacher_path.write_text(json.dumps(changed_teacher))
            with self.assertRaisesRegex(ValueError, 'silver_uct.*retired'):
                candidate._validate_native_candidate_pool(changed, invalid_teacher_path)
        changed = copy.deepcopy(manifest)
        changed['producerExecutableSha256'] = '0' * 64
        with mock.patch.object(candidate, 'sha256', return_value='a' * 64):
            with self.assertRaisesRegex(ValueError, 'producer is not bound'):
                candidate._validate_native_candidate_pool(changed, teacher_path)

    def test_preexisting_active_or_spent_lizard_is_not_a_pair_target(self):
        self.assertFalse(candidate._candidate_has_lizard(
            {'relics': []}, {'relics': []}))
        for data in (0, 1):
            self.assertTrue(candidate._candidate_has_lizard(
                {'relics': [{'id': candidate.pilot.LIZARD_TAIL_ID, 'data': data}]},
                {'relics': []}))
            self.assertTrue(candidate._candidate_has_lizard(
                {'relics': []},
                {'relics': [{'relicId': candidate.pilot.LIZARD_TAIL_ID, 'data': data}]}))

    def test_retired_silver_is_rejected_by_default_but_exact_historical_teacher_is_pinnable(self):
        teacher = self.artifact['teacherProvenance']
        teacher_sha = self.artifact['teacherManifestSha256']
        with self.assertRaisesRegex(ValueError, 'silver_uct.*retired'):
            pilot.validate_teacher(teacher)

        manifest = {
            'combatTeacher': copy.deepcopy(teacher),
            'combatTeacherManifestSha256': teacher_sha,
        }
        expected = {'identity': self.artifact['teacherIdentity'],
                    'provenance': copy.deepcopy(teacher), 'manifestSha256': teacher_sha}
        pilot._validate_historical_teacher(manifest, expected)

        changed_teacher = copy.deepcopy(manifest)
        changed_teacher['combatTeacher']['search_configuration']['simulation_budgets'] = [9999]
        with self.assertRaisesRegex(ValueError, 'historical teacher differs'):
            pilot._validate_historical_teacher(changed_teacher, expected)
        changed_hash = copy.deepcopy(manifest)
        changed_hash['combatTeacherManifestSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'historical teacher differs'):
            pilot._validate_historical_teacher(changed_hash, expected)

    def test_existing_screen_is_pinned_to_the_exact_pr326_packet(self):
        packet = analyzer.PR326_SCREEN_PACKET
        path = Path('/tmp/pr326-screen-header-fixture.json')
        header = {
            'jsonl': {'sha256': packet['pairJsonlSha256']},
            'targetSelection': {'sha256': packet['targetSelectionSha256']},
        }
        with mock.patch.object(analyzer, 'sha256', return_value=packet['pairManifestSha256']), \
                mock.patch.object(Path, 'read_text', return_value=json.dumps(header)):
            self.assertEqual(analyzer._validate_existing_screen_packet_header(path), header)
        bad_header = copy.deepcopy(header)
        bad_header['jsonl']['sha256'] = '0' * 64
        with mock.patch.object(analyzer, 'sha256', return_value=packet['pairManifestSha256']), \
                mock.patch.object(Path, 'read_text', return_value=json.dumps(bad_header)):
            with self.assertRaisesRegex(ValueError, 'pair JSONL hash'):
                analyzer._validate_existing_screen_packet_header(path)
        with mock.patch.object(analyzer, 'sha256', return_value='0' * 64):
            with self.assertRaisesRegex(ValueError, 'exact pinned PR #326 packet'):
                analyzer._validate_existing_screen_packet_header(path)

    def test_native_transfer_agreement_compares_only_exact_matched_states(self):
        def pair(no_tail_outcome, active_tail_outcome, *, pre_value=5):
            pre = {'marker': pre_value}
            predictor = {'marker': pre_value}
            return {
                'pair': {'sourceSeed': 4201000, 'fightIdx': 4,
                         'sourceStateFingerprint': f'state-{pre_value}',
                         'activeTailPostData': 0},
                'noTail': {'transition': {'pre': pre, 'combatOutcome': no_tail_outcome},
                           'predictorInput': predictor},
                'activeTail': {'transition': {'pre': pre, 'combatOutcome': active_tail_outcome},
                               'predictorInput': predictor},
            }

        archived = [pair(pilot.WIN, pilot.WIN)]
        native = [pair(pilot.DEATH, pilot.DEATH)]
        result = analyzer._native_transfer_agreement(archived, native)
        self.assertEqual(result['exactPrecombatStateRows'], 1)
        self.assertEqual(result['threeClassLabelAgreement']['agreements'], 0)
        self.assertEqual(result['threeClassLabelAgreement']['disagreements'], 1)
        self.assertEqual(result['threeClassLabelAgreement']['matrixArchivedRowsByNativeColumns'][
            'WIN_CONSUMED']['LOSS_CONSUMED'], 1)
        self.assertEqual(result['combatOutcomeAgreementByArm']['noTail']['agreements'], 0)
        self.assertIn('never pooled', result['claimBoundary'])

        state_mismatch = analyzer._native_transfer_agreement(archived, [pair(
            pilot.DEATH, pilot.DEATH, pre_value=6)])
        self.assertEqual(state_mismatch['exactPrecombatStateRows'], 0)
        self.assertEqual(state_mismatch['stateMismatchRows'], 1)
        self.assertEqual(state_mismatch['threeClassLabelAgreement']['comparedRows'], 0)


if __name__ == '__main__':
    unittest.main()
