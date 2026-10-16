import importlib.util
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('plan', REPO/'tools/heart_distill_native_plan.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class NativePlanTest(unittest.TestCase):
    def test_fixed_disjoint_partition_and_teacher(self):
        plan = p.assignment(REPO, 4)
        self.assertEqual([s['seed'] for s in plan['sources']], list(range(110164000, 110164064)))
        self.assertEqual([sum(s['split'] == name for s in plan['sources'])
                          for name in ('train', 'validation', 'test')], [40, 8, 16])
        env = plan['environment']
        self.assertEqual(env['STS_OOC_MCTS_LEAF_POLICY'], 'heart1')
        self.assertEqual(env['STS_OOC_MCTS_PRIOR'], 'heart1')
        self.assertNotIn('STS_OOC_MCTS_CPU_SECONDS', env)
        self.assertEqual([c['seed'] for c in plan['canaries']], [110163994,110163994,110163995])
        for count in (0,65,True):
            with self.assertRaises(ValueError): p.assignment(REPO,count)

    def test_guarded_spec_and_deadline(self):
        plan = p.assignment(REPO, 1)
        s = p.shard_spec(plan,110164063,'/bundle','/output',17)
        self.assertEqual(s['timeoutSeconds'],17)
        self.assertEqual(s['command'][:3],['bash','/bundle/seed_guard.sh','/bundle/one_combat'])
        self.assertEqual(s['command'][3:8],['bestbench','10000','1','20','110164063'])
        self.assertEqual(s['environment']['STS_OOC_SIBLING_REPEATS'],'64')
        self.assertEqual(p.shard_spec(plan,110164000,'/bundle','/output',21600)['timeoutSeconds'],3600)
        for seed, remaining in [(110163000,10),(110164064,10),(110164000,0),(110164000,21601)]:
            with self.assertRaises(ValueError): p.shard_spec(plan,seed,'/bundle','/output',remaining)
        for seed in (110164000.0, '110164000', True, None):
            with self.assertRaises(ValueError): p.shard_spec(plan,seed,'/bundle','/output',10)


if __name__ == '__main__': unittest.main()
