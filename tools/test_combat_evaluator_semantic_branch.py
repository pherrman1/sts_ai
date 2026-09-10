#!/usr/bin/env python3
"""Synthetic sidecar contracts; no simulator seeds or training dependencies."""
import copy
import csv
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.agent import test_ooc_semantic_pipeline as semantic_fixture
from tools import combat_evaluator_semantic_branch_contract as contract
from tools.combat_evaluator_contract import validate_label_row


class SemanticCombatContractTest(unittest.TestCase):
    def setUp(self):
        self.semantic = semantic_fixture.TestSemanticPipeline()
        self.semantic.setUp()
        self.addCleanup(self.semantic.doCleanups)
        self.semantic.write()
        self.directory = Path(self.semantic.temp.name)
        self.csv_path = self.directory / 'combat.csv'
        self.semantic_path = self.directory / 'semantic.json'
        self.semantic_path.write_text(json.dumps(self.semantic.manifest))
        self.header = contract.HEADER.copy()
        self.rows = [self.row(0), self.row(1, death=True)]

    def row(self, action, death=False):
        semantic = self.semantic.rows[action]
        metadata = {name: semantic.get(name) for name in contract.PREFIX}
        metadata.update(branchFightIdx=0, act=1, floor=8, roomClass='NORMAL', encounter='Cultist')
        features = [0] * len(contract.RICH_NAMES)
        features[contract.RICH_NAMES.index('act')] = 1
        features[contract.RICH_NAMES.index('floor')] = 8
        labels = [0, 1, 0, 0, 0, 1, 0, 100, 20, 100, .001, .2, -.2, ''] if death else [1, 0, 0, 0, 0, 1, 50, 100, 0, 100, .5, .001, .5, '']
        return [metadata[n] for n in contract.PREFIX] + features + labels

    def set_cell(self, row, name, value):
        row[self.header.index(name)] = value

    def write(self):
        with self.csv_path.open('w', newline='') as stream:
            csv.writer(stream).writerows([self.header] + self.rows)

    def without_combat(self, actions):
        for index in actions:
            self.semantic.rows[index].update(silverSimulations=0, combatDecisions=0,
                                              transactionSubdecisions=0, transactionDecisions=0)
        self.semantic.write()
        self.semantic_path.write_text(json.dumps(self.semantic.manifest))

    def manifest(self):
        self.write()
        result = contract.validate_csv(self.csv_path)
        return dict(schema_version=contract.SCHEMA_VERSION,
                    producer_git_sha='a'*40, producer_executable_sha256='b'*64,
                    teacher=copy.deepcopy(self.semantic.manifest['combat_teacher']),
                    frozen_manifest=copy.deepcopy(self.semantic.manifest['frozen_manifest']),
                    semantic_manifest=dict(path=str(self.semantic_path), sha256=contract.sha256(self.semantic_path)),
                    csv=dict(path=str(self.csv_path), sha256=contract.sha256(self.csv_path)),
                    seed_spec={'sourceSeeds': [10]},
                    feature_contract={'count':1017, 'state_names':contract.RICH_NAMES.copy()},
                    integrity={**result['counts'], **{k:result[k] for k in ('rows','source_seeds','quarantined_source_seeds')}})

    def test_valid_win_death_and_same_source_sibling_identity(self):
        result = contract.validate_manifest(self.manifest())
        self.assertEqual(result['counts'], dict(valid=2, invalid=0, wins=1, deaths=1, ambiguous=0))
        self.assertEqual(result['source_seeds'], 1)
        self.assertEqual(result['semantic_branches_without_combat'], 0)

    def test_zero_rows_and_no_combat_branch_are_legal(self):
        self.without_combat([0, 1])
        self.rows = []
        result = contract.validate_manifest(self.manifest())
        self.assertEqual(result['rows'], 0)
        self.assertEqual(result['semantic_branches_without_combat'], 2)
        self.rows = [self.row(0)]
        self.assertEqual(contract.validate_manifest(self.manifest())['semantic_branches_without_combat'], 1)

    def test_positive_semantic_simulations_require_combat_row(self):
        self.rows = []
        with self.assertRaisesRegex(ValueError, 'simulations lack a combat row'):
            contract.validate_manifest(self.manifest())

    def test_ambiguous_awakened_death_retains_v1_signed_label(self):
        self.set_cell(self.rows[1], 'encounter', 'Awakened One')
        self.set_cell(self.rows[1], 'progressAmbiguous', 1)
        result = contract.validate_manifest(self.manifest())
        self.assertEqual(result['counts']['valid'], 2)
        self.assertEqual(result['counts']['ambiguous'], 1)
        labels = dict(zip(contract.LABELS, self.rows[1][-len(contract.LABELS):]))
        self.assertEqual(validate_label_row(labels)['labelValid'], 1)
        self.assertEqual(labels['signedOutcome'], -.2)

    def test_escape_turncap_and_health_quarantine(self):
        self.without_combat([1])
        for mask in ('escaped', 'turnCapLoss'):
            with self.subTest(mask=mask):
                row = self.row(0)
                for name, value in ((mask, 1), ('labelValid', 0), ('signedOutcome', 0), ('quarantineReason', mask)):
                    self.set_cell(row, name, value)
                self.rows = [row]
                self.assertEqual(contract.validate_manifest(self.manifest())['counts']['invalid'], 1)
                self.set_cell(row, 'labelValid', 1)
                self.set_cell(row, 'signedOutcome', .5)
                self.write()
                with self.assertRaises(ValueError):
                    contract.validate_csv(self.csv_path)
        row = self.row(0)
        for name, value in (('labelValid', 0), ('signedOutcome', 0), ('quarantineReason', 'simulator_health_failure')):
            self.set_cell(row, name, value)
        self.rows = [row]
        self.assertEqual(contract.validate_manifest(self.manifest())['quarantined_source_seeds'], 1)

    def test_independent_ratios_reject_consistent_corrupt_targets(self):
        for index, ratio, signed in ((0, 'winHpFrac', .7), (1, 'lossRemainingFrac', -.7)):
            with self.subTest(ratio=ratio):
                self.rows = [self.row(0), self.row(1, death=True)]
                self.set_cell(self.rows[index], ratio, .7)
                self.set_cell(self.rows[index], 'signedOutcome', signed)
                self.write()
                with self.assertRaisesRegex(ValueError, 'ratio mismatch'):
                    contract.validate_csv(self.csv_path)

    def test_epsilon_ratios_and_zero_maximum(self):
        for name in ('terminalCombatHp', 'terminalCombatMaxHp', 'terminalNonMinionCurHp', 'terminalNonMinionMaxHp'):
            self.set_cell(self.rows[0], name, 0)
        for name in ('winHpFrac', 'lossRemainingFrac', 'signedOutcome'):
            self.set_cell(self.rows[0], name, .001)
        self.assertEqual(contract.validate_manifest(self.manifest())['counts']['valid'], 2)

    def test_raw_order_width_and_all_duplicate_numeric_cells(self):
        original = copy.deepcopy(self.rows)
        mutations = [lambda: self.header.reverse(), lambda: self.rows[0].append('0'),
                     lambda: self.rows[0].pop(), lambda: self.rows.append(self.rows[0]),
                     lambda: self.set_cell(self.rows[0], 'act', 'nan'),
                     lambda: self.set_cell(self.rows[0], 'floor', 'inf'),
                     lambda: self.set_cell(self.rows[0], 'act', 2),
                     lambda: self.rows[0].__setitem__(len(contract.PREFIX)+contract.RICH_NAMES.index('act'), 'nan'),
                     lambda: self.rows[0].__setitem__(len(contract.PREFIX)+contract.RICH_NAMES.index('floor'), 'inf'),
                     lambda: self.set_cell(self.rows[0], 'encounter', 'INVALID'),
                     lambda: self.set_cell(self.rows[0], 'encounter', 'invented'),
                     lambda: self.set_cell(self.rows[0], 'branchFightIdx', 1),
                     lambda: self.set_cell(self.rows[0], 'signedOutcome', .8),
                     lambda: self.set_cell(self.rows[0], 'terminalNonMinionCurHp', 'nan'),
                     lambda: self.set_cell(self.rows[0], 'progressAmbiguous', 1)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.header = contract.HEADER.copy()
                self.rows = copy.deepcopy(original)
                mutate()
                self.write()
                with self.assertRaises(ValueError):
                    contract.validate_csv(self.csv_path)

    def test_manifest_hash_teacher_order_counts_seed_fail_closed(self):
        manifest = self.manifest()
        mutations = [lambda m:m.update(schema_version='combat_evaluator_v1'),
                     lambda m:m.update(producer_git_sha='z'*40),
                     lambda m:m.update(producer_git_sha='0'*40),
                     lambda m:m.update(producer_git_sha='c'*40),
                     lambda m:m['csv'].update(sha256='0'*64),
                     lambda m:m['semantic_manifest'].update(sha256='c'*64),
                     lambda m:m['frozen_manifest'].update(sha256='c'*64),
                     lambda m:m['teacher'].update(teacher_id='different'),
                     lambda m:m['teacher']['search_configuration'].update(reuse_cap=0),
                     lambda m:m['feature_contract']['state_names'].reverse(),
                     lambda m:m['feature_contract'].update(count=True),
                     lambda m:m['integrity'].update(deaths=0),
                     lambda m:m['integrity'].update(rows=True),
                     lambda m:m['seed_spec'].update(sourceSeeds=[11])]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                broken = copy.deepcopy(manifest)
                mutate(broken)
                with self.assertRaises(ValueError):
                    contract.validate_manifest(broken)

    def test_semantic_branch_provenance_not_just_csv_shape(self):
        self.without_combat([1])
        for name, value in (('sourceSeed', 11), ('decisionIdx', 3), ('semanticActionIdx', 1),
                            ('semanticKey', 'ooc:v1:effect=26:source=5:event=17:option=3'),
                            ('continuationSeed', 21), ('hiddenSeed', 31), ('semanticSource', 6)):
            with self.subTest(name=name):
                self.rows = [self.row(0)]
                manifest = self.manifest()
                self.set_cell(self.rows[0], name, value)
                self.write()
                manifest['csv']['sha256'] = contract.sha256(self.csv_path)
                with self.assertRaises(ValueError):
                    contract.validate_manifest(manifest)

    def test_hash_bound_semantic_corpus_still_requires_complete_siblings(self):
        self.semantic.rows.pop()
        self.semantic.write()
        self.semantic_path.write_text(json.dumps(self.semantic.manifest))
        with self.assertRaisesRegex(ValueError, 'missing siblings'):
            contract.validate_manifest(self.manifest())


if __name__ == '__main__':
    unittest.main()
