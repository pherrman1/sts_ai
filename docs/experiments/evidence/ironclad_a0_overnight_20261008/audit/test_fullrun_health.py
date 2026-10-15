#!/usr/bin/env python3
"""Synthetic artifacts only; never starts games or opens campaign outputs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import audit_fullrun_health as a


def row(seed=10, count=250, kind='victory'):
    return {'schema':1, 'seed':str(seed), 'combat_id':seed, 'decision':1,
            'error':'', 'adaptive':False, 'singleton_skip':False,
            'completed_simulations':count, 'configured_simulations':10000,
            'heuristic_evaluations':count, 'neural_evaluations':0,
            'rollout_calls':count, 'cycle_rollouts':0,
            'nonterminal_rollout_starts':count, 'descent_aborts':0,
            'root_actions':2, 'inherited_visits':9999,
            'endpoints':{k:{'count':count if k==kind else 0,
                            'tree_depth':{'1':count} if k==kind else {},
                            'total_depth':{'2':count} if k==kind else {}} for k in a.KINDS}}


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.report=self.root/'report.json';self.receipt=self.root/'A_0.receipt.json'
        self.tree=self.root/'A_0.tree.jsonl';self.csv=self.root/'A_0.csv'
        self.manifest=self.root/'manifest.json'
        self.env={'STS_SILVER_ADAPTIVE':'0','STS_SILVER_LEARNED_STOP':'1','STS_SILVER_EXACT_ROOT_BUDGETS':'0'}
        self.rows=[row(10),row(11)];self.complete=True

    def tearDown(self):self.temp.cleanup()

    def fixture(self):
        self.csv.write_text('seed,won\n10,not-interpreted\n11,not-interpreted\n')
        self.tree.write_text(''.join(json.dumps(r)+'\n' for r in self.rows))
        producer={'source_sha':'a'*40,'binary_sha256':'b'*64}
        self.manifest.write_text(json.dumps(dict(producer,analysis_seeds=[10,11],analysis_arms=['A'],
                                                profiles={'common':self.env,'arms':{'A':{}}})))
        outputs={k:{'path':str(p),'sha256':a.sha(p),'bytes':p.stat().st_size}
                 for k,p in [('tree',self.tree),('csv',self.csv)]}
        receipt=dict(producer,manifest=str(self.manifest),manifest_sha256=a.sha(self.manifest),arm='A',
                     status='completed',exit_code=0,outputs=outputs,
                     environment=dict(self.env,STS_SILVER_TREE_PROFILE=str(self.tree)))
        self.receipt.write_text(json.dumps(receipt))
        inputs=[{'kind':k,'path':str(p),'sha256':a.sha(p)} for k,p in
                [('receipt',self.receipt),('tree',self.tree),('csv',self.csv)]]
        self.report.write_text(json.dumps(dict(producer,all_pairs_complete=self.complete,phase='discovery',
                                              manifest_sha256=a.sha(self.manifest),arms={'A':{'n':2}},inputs=inputs)))

    def run_audit(self):
        self.fixture();return a.audit(self.report,a.sha(self.report))

    def test_learned_budget_and_inherited_denominator(self):
        d=self.run_audit();self.assertEqual(d['status'],'PASS')
        self.assertEqual(d['arms']['A']['completed_simulations'],500)
        self.assertEqual(set(d['per_arm_seed']['A']),{10,11})

    def test_flat_budget(self):
        self.env.update(STS_SILVER_LEARNED_STOP='0',STS_SILVER_EXACT_ROOT_BUDGETS='1')
        self.assertEqual(self.run_audit()['status'],'INVALID_RUNTIME_HEALTH')
        self.rows=[row(10,10000),row(11,10000)]
        self.assertEqual(self.run_audit()['status'],'PASS')

    def test_unknown_learned_checkpoint(self):
        self.rows[0]=row(10,777);self.assertEqual(self.run_audit()['status'],'INVALID_RUNTIME_HEALTH')

    def test_singleton_zero(self):
        self.rows[0]=row(10,0);self.rows[0].update(singleton_skip=True,root_actions=1)
        self.assertEqual(self.run_audit()['status'],'PASS')
        self.env['STS_SILVER_EXACT_ROOT_BUDGETS']='1'
        self.assertEqual(self.run_audit()['status'],'INVALID_RUNTIME_HEALTH')

    def test_expected_cycle_rollout(self):
        self.rows[0]['cycle_rollouts']=3
        d=self.run_audit();self.assertEqual(d['status'],'PASS');self.assertEqual(d['arms']['A']['cycle_rollouts'],3)

    def test_diagnostic_limits_not_deaths(self):
        self.rows=[row(10,kind='engine_stop'),row(11,kind='turn_limit')]
        d=self.run_audit();self.assertEqual(d['status'],'PASS_WITH_DIAGNOSTIC_LIMITS')
        self.assertEqual(d['arms']['A']['endpoints']['death'],0)

    def test_nonterminal_error_and_abort_are_fatal(self):
        self.rows[0]=row(10,kind='nonterminal')
        self.rows[1].update(error='descent bound',descent_aborts=1)
        d=self.run_audit();self.assertEqual(d['status'],'INVALID_RUNTIME_HEALTH')
        self.assertEqual(len(d['fatal_contract_findings']),2)
        self.assertEqual(d['arms']['A']['error_strings'],{'descent bound':1})

    def test_histogram_conservation(self):
        self.rows[0]['endpoints']['victory']['tree_depth']['1']+=1
        self.assertEqual(self.run_audit()['status'],'INVALID_RUNTIME_HEALTH')

    def test_endpoint_conservation(self):
        self.rows[0]['completed_simulations']+=1
        self.assertEqual(self.run_audit()['status'],'INVALID_RUNTIME_HEALTH')

    def test_duplicate_decision_and_missing_seed(self):
        self.rows=[row(10),row(10)]
        d=self.run_audit();self.assertEqual(d['status'],'INVALID_RUNTIME_HEALTH')
        self.assertTrue(any('missing_tree_sources' in e for e in d['fatal_contract_findings']))

    def test_extra_source_and_malformed_boolean(self):
        self.rows=[row(12),row(11)];self.rows[1]['adaptive']=0
        self.assertEqual(self.run_audit()['status'],'INVALID_RUNTIME_HEALTH')

    def test_incomplete_report_rejected(self):
        self.complete=False
        with self.assertRaisesRegex(ValueError,'not COMPLETE'):self.run_audit()

    def test_changed_hash_rejected(self):
        self.fixture();self.tree.write_text(self.tree.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'hash changed'):a.audit(self.report,a.sha(self.report))

    def test_json_duplicate_and_nonfinite_rejected(self):
        for text in ['{"a":1,"a":2}','{"a":NaN}']:
            with self.assertRaises(ValueError):a.parse(text)

    def test_cycle_counter_invalid(self):
        self.rows[0]['cycle_rollouts']=251
        self.assertEqual(self.run_audit()['status'],'INVALID_RUNTIME_HEALTH')

    def test_malformed_profile_containers(self):
        for broken in ([], dict(row(10), endpoints=list(a.KINDS)),
                       dict(row(10), endpoints={k:[] for k in a.KINDS})):
            with self.subTest(broken=broken):
                self.rows=[broken,row(11)]
                self.assertEqual(self.run_audit()['status'],'INVALID_RUNTIME_HEALTH')


if __name__=='__main__':unittest.main(verbosity=2)
