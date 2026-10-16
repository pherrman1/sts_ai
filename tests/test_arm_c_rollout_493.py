"""Synthetic research checks; no simulator seeds or real campaign data."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from arm_c_rollout_493 import analyze, mcnemar, resource_summary, verify_custody_set


def decision(**changes):
    return {'singleton_bypass':0,'aborted':False,'completed_simulations':500,
            'executed':True,'selected_action':1,'actions':[{'id':1}],
            'thread_cpu_seconds':.251,'early_stop_budget':1,'attempts':500,
            'early_stop_lock':0,'early_stop_gap':0,**changes}


class ResearchTests(unittest.TestCase):
    def test_budget_boundary_and_excluded_roots(self):
        rows=[decision() for _ in range(100)]
        rows += [decision(singleton_bypass=1,completed_simulations=0),decision(aborted=True,executed=False)]
        result=resource_summary(rows)
        self.assertTrue(result['pass']);self.assertEqual(result['validSearches'],100)
        for changes in ({'thread_cpu_seconds':.36},{'completed_simulations':8192}, {'early_stop_budget':0}):
            self.assertFalse(resource_summary([decision(**changes) for _ in range(100)])['pass'])

    def test_illegal_or_empty_completed_search_rejected(self):
        for changes in ({'selected_action':9},{'completed_simulations':0},{'executed':False}, {'thread_cpu_seconds':float('nan')}):
            with self.assertRaises(ValueError):resource_summary([decision(**changes)])
        with self.assertRaises(ValueError):resource_summary([decision(singleton_bypass=1)])

    def test_root_boundary_is_no_search_with_exact_bypass_contract(self):
        boundary=decision(execution_reason='root_boundary',completed_simulations=0,
                          executed=False,selected_action=None,actions=[],early_stop_budget=0,attempts=0)
        result=resource_summary([decision(),boundary])
        self.assertTrue(result['pass']);self.assertEqual(result['validSearches'],1)
        self.assertEqual(result['rootBoundaryBypasses'],1)
        for change in ({'completed_simulations':1},{'selected_action':1},{'actions':[{'id':1}]},
                       {'executed':True},{'aborted':True},{'singleton_bypass':1},
                       {'attempts':1},{'early_stop_budget':1},{'early_stop_lock':1},{'early_stop_gap':1}):
            with self.assertRaisesRegex(ValueError,'root-boundary'):
                resource_summary([decision(),{**boundary,**change}])

    def fixture(self,root,treatment,control):
        seeds=list(range(1,len(treatment)+1))
        for arm,outcomes in [('chain',control),('armc',treatment)]:
            for seed,won in zip(seeds,outcomes):
                base=root/f'cohort-{seed}-{arm}'
                path=base.with_suffix('.csv');path.write_text(f'seed,won,floor,hpEnd,act\n{seed},{won},50,20,3\n')
                receipt={'returncode':0,'seconds':1,'files':{path.name:hashlib.sha256(path.read_bytes()).hexdigest()},
                         'validation':{k:1 for k in ['realCombatCpuSeconds','floorThreadCpuSeconds','processCpuSeconds','oocCpuSeconds','otherAndFallbackCpuSeconds']}}
                base.with_suffix('.receipt.json').write_text(json.dumps(receipt))
        return seeds

    def test_primary_requires_interval_and_exact_test(self):
        for treatment,control,verdict in [([1]*8,[0]*8,'IMPROVED'),([0]*8,[1]*8,'WORSE'),
                                           ([0]*8,[0]*8,'NOT_SHOWN'),([1]*4,[0]*4,'NOT_SHOWN')]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);seeds=self.fixture(root,treatment,control)
                result=analyze(root,seeds)
                self.assertEqual(result['verdict'],verdict)
                self.assertFalse(result['runtimePromotion'])
        self.assertEqual(mcnemar(0,0),1);self.assertAlmostEqual(mcnemar(8,0),.0078125)

    def test_accepted_unit_receipts_and_files_are_rechecked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);seeds=self.fixture(root,[0]*8,[0]*8)
            hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.receipt.json')}
            verify_custody_set(root,hashes,'cohort',seeds)
            p=root/'cohort-1-armc.receipt.json';p.write_text(p.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'receipt changed'):verify_custody_set(root,hashes,'cohort',seeds)

    def test_post_run_bytes_and_source_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);seeds=self.fixture(root,[0]*8,[0]*8)
            p=root/'cohort-1-armc.csv';p.write_text(p.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'artifact changed'):analyze(root,seeds)


if __name__=='__main__':unittest.main()
