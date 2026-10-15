#!/usr/bin/env python3
"""Synthetic cluster-inference and panel isolation checks; no game seeds."""
import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('larger', REPO / 'tools/analyze_a20_teachers_large.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class LargerTests(unittest.TestCase):
    def test_panels_and_old_module_isolation(self):
        a.configure(False)
        self.assertEqual(list(a.core.ARM_CONFIG), ['plain2k', 'prior2k'])
        self.assertEqual(len(a.arms()), 2)
        a.configure(True)
        self.assertEqual(len(a.arms(True)), 4)
        spec = importlib.util.spec_from_file_location('original', REPO / 'tools/analyze_a20_teachers.py')
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        self.assertEqual(old.REPLICATES, 4)
        self.assertEqual(old.COHORT, list(range(97150810, 97150814)))
        self.assertEqual(len(a.ANCHORS), 8)
        self.assertTrue(set(a.ANCHORS) <= set(a.COHORT))

    def test_bootstrap_pairs_sources_and_rmse_not_mean_rmse(self):
        a.configure(False)
        summaries = []
        for mse in (1., 9.):
            summaries.append({'forecast': {
                name: {'hpSquaredError': mse + (2 if name == 'prior2k' else 0), 'deathBrier': .25,
                       'hpBias': mse, 'deathBias': 0.} for name in a.core.FORECASTERS},
                'cost': {name: {'forecastCpuSeconds': mse} for name in a.MAIN},
                'controllerContrasts': {'prior2k_minus_plain2k': {'rawHp': 3., 'death': 0., 'cpuSeconds': .1}}})
        first = a.bootstrap(summaries)
        self.assertEqual(first, a.bootstrap(summaries))
        metrics = first['metrics']
        self.assertEqual(metrics['ctm.hpRmse']['estimate'], 5 ** .5)
        self.assertEqual(metrics['prior2k_minus_plain2k.forecast.hpSquaredError']['interval95'], [2., 2.])
        self.assertEqual(metrics['prior2k_minus_plain2k.controller.rawHp']['interval95'], [3., 3.])
        self.assertEqual(metrics['ctm.hpSquaredError']['interval95'], [1., 9.])


    def test_full_synthetic_main_anchor_pipeline_and_custody(self):
        spec = importlib.util.spec_from_file_location('fixture_library', REPO / 'tests/test_analyze_a20_teachers.py')
        fixtures = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixtures)
        fixtures.a = a.core
        a.configure()
        with tempfile.TemporaryDirectory() as temp:
            f = fixtures.Fixture(Path(temp))
            packet = f.repo / 'docs/experiments/evidence/a20_teacher_comparison_20261014'
            dependency = packet / 'run_pilot.py'
            dependency.write_text('SYNTHETIC DEPENDENCY')
            env = f.freeze['environment'] | {'STS_CTMSILVER_LARGE_ANCHOR': '0'}
            f.teacher['environment'] = env
            fixtures.dump(f.freeze['teacher'], f.teacher)
            anchor_path = f.root / 'anchor.json'
            anchor_env = env | {'STS_CTMSILVER_LARGE_ANCHOR': '1'}
            anchor_teacher = f.teacher | {'teacher_id': f.teacher['teacher_id'] + '-anchor', 'environment': anchor_env}
            fixtures.dump(anchor_path, anchor_teacher)
            f.freeze.update(environment=env, anchorSeeds=a.ANCHORS, anchorTeacher=str(anchor_path),
                            anchorEnvironment=anchor_env, anchorArms=a.arms(True), bootstrap=a.BOOTSTRAP,
                            coverageMinimum=a.COVERAGE)
            f.freeze['priorIdentity']['generation'] = 6
            for path in (dependency, anchor_path, Path(f.freeze['teacher']), Path(a.__file__)):
                f.freeze['artifactFiles'][str(path)] = a.core.sha(path)
            with mock.patch.object(a.core, 'CTM_HASHES', f.ctm_hashes), mock.patch.object(a, 'PRIOR_HASH', f.freeze['priorIdentity']['sha256']):
                teachers = a.validate_freeze(f.freeze)
                original = dict(f.freeze)
                for seed, anchor in ((a.COHORT[1], False), (a.CANARY, True)):
                    a.configure(anchor)
                    f.freeze = dict(original)
                    f.teacher = teachers[int(anchor)]
                    if anchor:
                        f.freeze.update(teacher=str(anchor_path), environment=anchor_env, arms=a.arms(True))
                    prefix = f.source(seed)
                    Path(str(prefix) + '.time').write_text('3.00 0.00\n')
                    report = a.job(original, seed, f.freeze_hash, teachers)
                    self.assertEqual(report['metrics'][0]['cost']['plain2k']['simulations'], 16 * 4000)
                    self.assertEqual(set(report['metrics'][0]['forecast']), set(('ctm', *(a.ALL if anchor else a.MAIN))))
                del original['artifactFiles'][str(dependency)]
                with self.assertRaisesRegex(a.core.Invalid, 'dependency'):
                    a.validate_freeze(original)

    def test_failure_stops_dispatch_and_drains(self):
        spec = importlib.util.spec_from_file_location('large_runner_test', REPO / 'docs/experiments/evidence/a20_teacher_comparison_20261014/run_large.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        for mode in ('returncode', 'exception', 'integrity'):
            with tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                (out / 'freeze.json').write_text('{}')
                digest = runner.base.sha(out / 'freeze.json')
                (out / 'canary-report.json').write_text(json.dumps({'verdict': 'CANARY_VALID', 'freezeSha256': digest}))
                freeze = {'outputs': {str(s): str(out / f's{s}') for s in a.COHORT}, 'environment': {},
                          'anchorEnvironment': {}, 'anchorTeacher': 'anchor', 'teacher': 'main'}
                completed = []
                def source(out, seed, freeze, digest):
                    completed.append(seed)
                    if mode == 'exception' and seed == a.COHORT[0]:
                        raise RuntimeError('synthetic worker failure')
                    return {'returncode': 1 if mode == 'returncode' and seed == a.COHORT[0] else 0, 'timedOut': False, 'cpuSeconds': 1.}
                def validate(freeze, seed, digest, teachers):
                    if mode == 'integrity' and seed == a.COHORT[0]:
                        raise ValueError('synthetic integrity failure')
                # Wait for the four dispatched jobs together, making the failure boundary deterministic.
                with mock.patch.object(runner, 'verify', return_value=freeze), mock.patch.object(runner.analysis, 'validate_freeze', return_value=(None, None)), mock.patch.object(runner.analysis, 'job', side_effect=validate), mock.patch.object(runner, 'run_source', side_effect=source), mock.patch.object(runner, 'wait', side_effect=lambda fs, **kw: __import__('concurrent.futures').futures.wait(fs)), mock.patch.object(runner.subprocess, 'run') as analyzed:
                    runner.execute(out, 'cohort')
                self.assertEqual(set(completed), set(a.COHORT[:4]))
                self.assertTrue((out / 'phase-cohort.started.json').is_file())
                self.assertEqual(len(analyzed.call_args.args[0][4:]), 32)

if __name__ == '__main__':
    unittest.main()
