#!/usr/bin/env python3
"""Synthetic custody, pairing, choice and cluster math checks. No game seeds."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from threading import Event

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audit_analysis_test', REPO / 'tools/analyze_ooc_selective_silver.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
runner_spec = importlib.util.spec_from_file_location('audit_runner_test', REPO / 'docs/experiments/evidence/ooc_selective_silver_audit_20261014/run.py')
runner = importlib.util.module_from_spec(runner_spec); runner_spec.loader.exec_module(runner)
STREAMS = a.streams()


def dump(path, value):
    Path(path).write_text(json.dumps(value))


def fixture(root):
    seed = a.CANARY; prefix = str(root / 'canary'); plan = root / 'plan.json'
    dump(plan, {'streams': STREAMS})
    f = {'outputs': {str(seed): prefix}, 'repository': str(REPO), 'binary': '/SYNTHETIC/one_combat',
         'producerGitSha': '0' * 40, 'plan': str(plan), 'mapScreenEnum': 2,
         'spec': {'sourcePolicy': {'synthetic': True}, 'ctmLoadedIdentity': {'synthetic': True}}}
    argv = ['bash', str(REPO / 'tools/seed_guard.sh'), f['binary'], 'oocselectivesilvergen', '1', str(seed), str(plan), prefix + '.jsonl']
    Path(prefix + '.time').write_text('99.00 1.00 120.00\n')
    dump(prefix + '.started.json', {'argv': argv, 'freezeSha256': 'synthetic'})
    dump(prefix + '.receipt.json', {'argv': argv, 'seed': seed, 'freezeSha256': 'synthetic', 'returncode': 0,
                                   'timedOut': False, 'cpuSeconds': 100., 'gnuWallSeconds': 120., 'wallSeconds': 120.})
    def value(x):
        return {'value': x, 'terminal': False, 'hp': 50, 'maxHp': 80, 'floor': 7, 'combats': 3, 'steps': 10, 'evaluatorCpuSeconds': .001}
    stream = STREAMS[str(seed)]['1']
    def arm(n, phase, values):
        rows = [{'k': k, 'candidate': c, 'futureSeed': stream[phase][k], 'result': value(values[c]),
                 'parentCpuSeconds': .001, 'childCpuSeconds': .5} for k in range(n) for c in range(2)]
        return {'rows': rows, 'means': list(values), 'selected': int(values[1] > values[0]),
                'parentCpuSeconds': 1., 'childCpuSeconds': n}
    baseline = {'result': {'selectedKey': 'A', 'work': {'simulations': 4096, 'attempts': 4096},
                          'actions': [{'key': 'A', 'visits': 3000}, {'key': 'B', 'visits': 1096}]},
                'parentCpuSeconds': .1, 'childCpuSeconds': 1.}
    ctm = arm(8, 'rescore', (.5, .4)); silver = arm(8, 'rescore', (.4, .6)); ref = arm(16, 'reference', (.2, .8))
    matched_rows = [{'k': k, 'futureSeed': stream['rescore'][k] if k < 8 else stream['matched'][0],
                     'results': [value(.5), value(.4)], 'cpuAfterPair': float(k + 1)} for k in range(9)]
    root_row = {'type': 'root_complete', 'seed': seed, 'act': 1, 'floor': 3, 'decisionOrdinal': 0,
                'keys': ['A', 'B'], 'bits': [11, 12], 'baseline': baseline, 'baselineControl': copy.deepcopy(baseline),
                'ctm8': ctm, 'silver8': silver, 'reference': ref,
                'matched': {'result': {'rows': matched_rows, 'count': 9, 'means': [.5, .4], 'selected': 0, 'evaluatorCpuSeconds': 9.},
                            'parentCpuSeconds': .1, 'childCpuSeconds': 9.01}, 'matchedCostRatio': 9.11 / 9., 'matchedCostValid': True}
    # C++ arithmetic stores sums/n, including floating accumulation roundoff.
    for field in ('ctm8', 'silver8', 'reference'):
        v = root_row[field]; v['means'] = []
        for c in range(2):
            total = 0.
            for r in v['rows']:
                if r['candidate'] == c: total += r['result']['value']
            v['means'].append(total / (len(v['rows']) // 2))
    root_row['matched']['result']['means'] = []
    for c in range(2):
        total = 0.
        for r in matched_rows: total += r['results'][c]['value']
        root_row['matched']['result']['means'].append(total / 9)
    source = {'roots': [root_row], 'actions': [{'act': 1, 'floor': 3, 'screen': 2, 'bits': 11, 'legalCount': 2, 'realCombatsInAct': 1}],
              'battles': [{'synthetic': True}], 'summary': {'synthetic': True}}
    control_source = copy.deepcopy(source); control_source['roots'] = []
    rows = [{'type': 'header', 'seed': seed, 'planSha256': a.sha(plan), 'producerGitSha': f['producerGitSha'], **f['spec']},
            {'type': 'source_control_start'}, {'type': 'source_control_complete', 'result': {'result': control_source, 'parentCpuSeconds': .1, 'childCpuSeconds': 1.}},
            {'type': 'root_start', 'act': 1, 'seed': seed, 'decisionOrdinal': 0}]
    rows[0]['policy'] = rows[0].pop('sourcePolicy')
    for name in ('ctm8', 'silver8', 'reference'):
        if name == 'reference': rows.append({'type': 'matched_start', 'act': 1, 'targetCpuSeconds': 9.})
        for row in root_row[name]['rows']:
            rows.append({'type': 'evaluation_start', 'act': 1, 'selector': name, 'k': row['k'], 'candidate': row['candidate']})
            rows.append({'type': 'evaluation_complete', 'act': 1, 'selector': name, 'row': row})
    rows += [root_row, {'type': 'source_complete', 'seed': seed, 'source': source, 'parentCpuSeconds': 5.3, 'childCpuSeconds': 44.01}]
    def save(): Path(prefix + '.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    save(); return f, rows, root_row, save


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.f, self.rows, self.root, self.save = fixture(Path(self.temp.name))

    def test_complete_synthetic_choice_and_prefix(self):
        report = a.job(self.f, a.CANARY, 'synthetic')
        r = report['roots'][0]
        self.assertEqual(r['choices'], {'baseline': 0, 'ctm8': 0, 'silver8': 1, 'reference': 1, 'matched': 0})
        self.assertAlmostEqual(r['referenceUtility']['silver8'] - r['referenceUtility']['baseline'], .6)
        self.assertTrue(r['matchedCostValid'])
        self.assertEqual(report['absentActs'], [2, 3])

    def test_wrong_pairing_rejected(self):
        self.root['silver8']['rows'][0]['futureSeed'] += 1; self.save()
        with self.assertRaisesRegex(ValueError, 'draw identity'): a.job(self.f, a.CANARY, 'synthetic')

    def test_prefix_mismatch_rejected(self):
        self.root['matched']['result']['rows'][0]['results'][0]['hp'] = 49; self.save()
        with self.assertRaisesRegex(ValueError, 'prefix'): a.job(self.f, a.CANARY, 'synthetic')

    def test_partial_and_out_of_order_rejected(self):
        self.rows[4], self.rows[5] = self.rows[5], self.rows[4]; self.save()
        with self.assertRaisesRegex(ValueError, 'progress order'): a.job(self.f, a.CANARY, 'synthetic')

    def test_zero_root_rejected_and_budget_gate(self):
        self.rows[-1]['source']['roots'] = []; self.save()
        with self.assertRaisesRegex(ValueError, 'source root panel'): a.job(self.f, a.CANARY, 'synthetic')

    def test_checkpoint_chain_allowed_nonterminal_shortcut_rejected(self):
        a.result(dict(self.root['ctm8']['rows'][0]['result'], combats=4))
        with self.assertRaisesRegex(ValueError, 'horizon'): a.result(dict(self.root['ctm8']['rows'][0]['result'], combats=2))

    def test_impossible_endpoint_and_fractional_terminal(self):
        value = self.root['ctm8']['rows'][0]['result']
        for key, bad in (('hp', -1), ('maxHp', 0), ('floor', -1), ('steps', -1)):
            with self.assertRaisesRegex(ValueError, 'endpoint/work'):
                a.result(dict(value, **{key: bad}))
        with self.assertRaisesRegex(ValueError, 'fractional terminal'):
            a.result(dict(value, terminal=True))

    def test_resource_receipt_and_child_settlement(self):
        self.rows[-1]['childCpuSeconds'] += 1; self.save()
        with self.assertRaisesRegex(ValueError, 'child settlement'): a.job(self.f, a.CANARY, 'synthetic')
        self.rows[-1]['childCpuSeconds'] -= 1; self.save()
        Path(self.f['outputs'][str(a.CANARY)] + '.time').write_text('99 0 120\n')
        with self.assertRaisesRegex(ValueError, 'GNU-time'): a.job(self.f, a.CANARY, 'synthetic')

    def test_cpu_wrappers_and_matched_stop(self):
        self.root['baseline']['childCpuSeconds'] = 61.; self.save()
        with self.assertRaisesRegex(ValueError, 'fork child CPU'): a.job(self.f, a.CANARY, 'synthetic')
        self.root['baseline']['childCpuSeconds'] = 1.
        self.root['matched']['result']['rows'][-1]['cpuAfterPair'] = 8.; self.root['matched']['result']['evaluatorCpuSeconds'] = 8.; self.save()
        with self.assertRaisesRegex(ValueError, 'premature'): a.job(self.f, a.CANARY, 'synthetic')

    def test_runner_failed_dispatch_drains_existing_worker(self):
        out = Path(self.temp.name); attempted = []; finished = []; second_started = Event(); failure_seen = Event()
        def source(_out, _freeze, seed, _digest):
            attempted.append(seed)
            if seed == a.COHORT[0]:
                self.assertTrue(second_started.wait(2))
                return {'returncode': 1, 'timedOut': False}
            second_started.set(); self.assertTrue(failure_seen.wait(2)); finished.append(seed)
            return {'returncode': 0, 'timedOut': False}
        with patch.object(runner.a, 'validate_freeze', return_value={}), patch.object(runner.a, 'sha', return_value='frozen'), \
             patch.object(runner.a, 'read', return_value={'verdict': 'CANARY_VALID', 'freezeSha256': 'frozen'}), \
             patch.object(runner.a, 'job'), patch.object(runner, 'source', side_effect=source), patch.object(runner.subprocess, 'run'), patch('builtins.print', side_effect=lambda *args, **kwargs: failure_seen.set()):
            runner.execute(out, 'cohort')
        self.assertEqual(sorted(attempted), a.COHORT[:2])
        self.assertEqual(finished, [a.COHORT[1]])

    def test_runner_nonzero_exit_kills_owned_group(self):
        class Process:
            pid = 12345
            def __init__(self, code): self.code = code
            def wait(self, timeout=None): return self.code
        for code in (0, 1):
            with tempfile.TemporaryDirectory() as td:
                out = Path(td); prefix = str(out / 'sample')
                f = {'outputs': {str(a.CANARY): prefix}, 'binary': '/SYNTHETIC/one_combat', 'plan': '/SYNTHETIC/plan', 'environment': {}}
                def launch(*args, **kwargs):
                    Path(prefix + '.time').write_text('1.00 0.00 0.00\n')
                    return Process(code)
                with patch.object(runner.subprocess, 'Popen', side_effect=launch), patch.object(runner.os, 'killpg') as kill, patch('builtins.print'):
                    receipt = runner.source(out, f, a.CANARY, 'frozen')
                self.assertEqual(receipt['returncode'], code)
                if code: kill.assert_called_once_with(12345, runner.signal.SIGKILL)
                else: kill.assert_not_called()

    def test_model_custody_mandatory_and_identity_join(self):
        manifest = '/SYNTHETIC/manifest'; models = [{'role': role, 'path': role, 'sha256': role} for role in ('floor', 'win', 'ooc_strategic_tok')]
        f = {'repository': str(REPO), 'ctmManifest': manifest, 'artifactFiles': {manifest: a.CTM},
             'spec': {'sourcePolicy': {'model_artifacts': models}, 'ctmLoadedIdentity': {'correct': True}}}
        for model in models: f['artifactFiles'][str(REPO / model['path'])] = model['sha256']
        for name, digest in a.NATIVE_CTM_HASHES.items(): f['artifactFiles'][str(REPO / 'selfplay/models' / name)] = digest
        with patch.object(a, 'sha', side_effect=lambda path: f['artifactFiles'].get(str(path))), patch.object(a, 'read', return_value={'correct': True}):
            a.validate_model_custody(f)
            absent = copy.deepcopy(f); absent['artifactFiles'].pop(str(REPO / 'win'))
            with self.assertRaisesRegex(ValueError, 'source policy'): a.validate_model_custody(absent)
            absent = copy.deepcopy(f); absent['artifactFiles'].pop(str(REPO / 'selfplay/models' / next(iter(a.NATIVE_CTM_HASHES))))
            with self.assertRaisesRegex(ValueError, 'native CTM'): a.validate_model_custody(absent)
            absent = copy.deepcopy(f); absent['spec']['ctmLoadedIdentity'] = {'wrong': True}
            with self.assertRaisesRegex(ValueError, 'identity join'): a.validate_model_custody(absent)

    def test_matched_claim_requires_primary_improvement(self):
        effects = {'silver8_minus_baseline': {'interval95': [0., .1]},
                   'silver8_minus_matched': {'interval95': [.1, .2]}}
        self.assertEqual(a.improvement_flags(effects, True),
                         {'directionalImprovement': False, 'matchedComputeImprovement': False})
        effects['silver8_minus_baseline']['interval95'] = [.01, .1]
        self.assertTrue(a.improvement_flags(effects, True)['matchedComputeImprovement'])
        self.assertFalse(a.improvement_flags(effects, False)['matchedComputeImprovement'])

    def test_duplicate_json_and_bootstrap_source_math(self):
        with self.assertRaisesRegex(ValueError, 'nonfinite'): a.decode('{"x":1e999}')
        with self.assertRaisesRegex(ValueError, 'duplicate'): a.decode('{"x":1,"x":2}')
        b = a.bootstrap([1., 3.]); self.assertEqual(b['estimate'], 2.); self.assertEqual(b['interval95'], [1., 3.])
        self.assertEqual(b, a.bootstrap([1., 3.]))


if __name__ == '__main__': unittest.main()
