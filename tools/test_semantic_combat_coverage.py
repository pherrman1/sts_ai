"""Offline coverage regressions; all rows/manifests are synthetic fixtures."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import analyze_semantic_combat_labels as coverage
from tools import test_combat_evaluator_semantic_branch as fixture_module


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.SemanticCombatContractTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def read(self):
        path = self.fixture.directory / 'combat-manifest.json'
        path.write_text(json.dumps(self.fixture.manifest()))
        return coverage.read_shard(path, 'a'*40)

    def test_hash_bound_sidecars_masks_and_conditional_labels(self):
        rows, branches, _, shard = self.read()
        report = coverage.summarize(rows, branches, range(40))
        self.assertEqual(report['counts']['wins'], 1)
        self.assertEqual(report['counts']['nonambiguous_deaths'], 1)
        self.assertEqual(report['labels']['lossRemainingFrac_nonambiguous_deaths']['min'], .2)
        self.assertEqual(report['labels']['winHpFrac_winners']['min'], .5)
        self.assertEqual(report['cost']['semantic_branch_silver_simulations'], 20000)
        self.assertEqual(report['cost']['semantic_branch_cpu_seconds'], .02)
        self.assertEqual(report['cost']['combat_labels_per_million_simulations'], 100)
        self.assertEqual(report['distributions']['semantic_family']['EVENT']['total'], 2)
        self.assertEqual(report['classification'], 'COMBAT LOSS TAIL LOW POWER')
        self.fixture.csv_path.write_text('corrupted')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            coverage.read_shard(Path(shard['manifest']), 'a'*40)

    def test_ambiguous_deaths_and_no_combat_branches(self):
        self.fixture.set_cell(self.fixture.rows[1], 'encounter', 'Awakened One')
        self.fixture.set_cell(self.fixture.rows[1], 'progressAmbiguous', 1)
        rows, branches, _, _ = self.read()
        report = coverage.summarize(rows, branches, range(40))
        self.assertEqual(report['counts']['true_deaths'], 1)
        self.assertEqual(report['counts']['nonambiguous_deaths'], 0)
        self.assertEqual(report['labels']['lossRemainingFrac_nonambiguous_deaths']['n'], 0)
        self.fixture.without_combat([1])
        self.fixture.rows.pop()
        rows, branches, _, _ = self.read()
        report = coverage.summarize(rows, branches, range(40))
        self.assertEqual(report['branches_without_combat']['count'], 1)
        self.assertIn('Inference', report['branches_without_combat']['reason_status'])
        branches[1]['silverSimulations'] = '10000'
        with self.assertRaisesRegex(ValueError, 'positive-cost'):
            coverage.summarize(rows, branches, range(40))

    def test_source_split_and_coverage_screen(self):
        rows, branches, _, _ = self.read()
        expanded = []
        for seed in range(200):
            for row in rows:
                expanded.append(dict(row, sourceSeed=seed))
        report = coverage.summarize(expanded, branches, range(200))
        split = coverage.stable_split(range(200))
        for name, counts in report['splits'].items():
            self.assertEqual(counts['wins'], sum(v == name for v in split.values()))
            self.assertEqual(counts['true_deaths'], counts['wins'])
        hypothetical = {name: dict(wins=1, nonambiguous_deaths=30) for name in ('train','validation','test')}
        self.assertEqual(coverage.classify(hypothetical), 'COMBAT LABELS ADEQUATE')
        hypothetical['test']['nonambiguous_deaths'] = 29
        self.assertEqual(coverage.classify(hypothetical), 'COMBAT LOSS TAIL LOW POWER')
        hypothetical['test']['nonambiguous_deaths'] = 30
        hypothetical['validation']['wins'] = 0
        self.assertEqual(coverage.classify(hypothetical), 'COMBAT LOSS TAIL LOW POWER')

    def test_exact_cohort_unique_sources_decisions_and_identities(self):
        rows, branches, _, _ = self.read()
        shards = [dict(source_seeds=list(range(start, start+16))) for start in range(992000,993024,16)]
        semantic = [dict(r, sourceSeed=seed) for seed in sorted(coverage.COHORT) for r in branches]
        combat = [dict(r, sourceSeed=seed) for seed in sorted(coverage.COHORT) for r in rows]
        self.assertEqual(len(coverage.validate_cohort(shards, semantic, combat)), 1024)
        for wrong_shards, wrong_semantic, wrong_combat, error in (
            (shards[:-1], semantic, combat, '64'),
            ([shards[0]]+shards[:-1], semantic, combat, 'overlapping'),
            (shards, semantic+[semantic[0]], combat, 'duplicate global semantic'),
            (shards, semantic, combat+[combat[0]], 'duplicate global combat'),
            (shards, semantic[2:], combat, 'one decision'),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                coverage.validate_cohort(wrong_shards, wrong_semantic, wrong_combat)
        altered = copy.deepcopy(shards)
        altered[0]['source_seeds'][0] = 990000
        with self.assertRaisesRegex(ValueError, 'wrong confirmation'):
            coverage.validate_cohort(altered, semantic, combat)

    def test_runner_cost_separates_process_time_and_elapsed(self):
        path = self.fixture.directory / 'runner.json'
        metadata = {name: dict(completed=64, workers=16, wall_seconds=10,
                    shards=[dict(shard=i, stage=name, returncode=0, wall_seconds=2, cpu_seconds=1)
                            for i in range(64)]) for name in ('capture','evaluate')}
        path.write_text(json.dumps(metadata))
        report = dict(cost={})
        coverage.add_runner_cost(report, path)
        self.assertEqual(report['cost']['runner']['process_cpu_seconds_total'], 128)
        self.assertEqual(report['cost']['runner']['stage_elapsed_wall_seconds_sum'], 20)
        metadata['evaluate']['shards'][0]['returncode'] = 1
        path.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'failed'):
            coverage.add_runner_cost(report, path)


if __name__ == '__main__':
    unittest.main()
