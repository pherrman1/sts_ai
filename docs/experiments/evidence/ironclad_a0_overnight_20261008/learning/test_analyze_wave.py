#!/usr/bin/env python3
"""Synthetic receipt-contract checks; no simulator or game seeds are executed."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'analyze_wave.py'
spec = importlib.util.spec_from_file_location('analyze_wave', SCRIPT)
aw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aw)


class EvidenceContractTest(unittest.TestCase):
    def setUp(self):
        scratch = aw.ROOT / 'build/overnight_20261008/learning'
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-analyzer-', dir=scratch)
        self.root = Path(self.tmp.name)
        self.binary = self.root / 'one_combat'
        self.binary.write_text('synthetic non-executable fixture\n')
        (self.root / 'models').mkdir()
        for name in ('v_rich_trees.txt', 'v_win_trees.txt'):
            (self.root / 'models' / name).write_text('synthetic model fixture\n')
        self.run = self.root / 'runs'; self.run.mkdir()
        common = {'STS_FAIR':'1','STS_STOP_AFTER_ACT':'3','STS_COLLECT_KEYS':'0',
                  'STS_OOC_MCTS':'0','STS_OOC_PUBLIC_FUTURES':'8','OMP_NUM_THREADS':'1'}
        self.m = {'schema':1, 'phase':'discovery', 'root':str(self.root),
                  'source_sha':'a'*40, 'binary':str(self.binary), 'binary_sha256':aw.digest(self.binary),
                  'artifacts':{str(p.relative_to(self.root)):aw.digest(p) for p in (self.root/'models').iterdir()},
                  'analysis_seeds':[900001,900002,900003], 'allowed_seeds':[900001,900002,900003],
                  'analysis_arms':['Fprod','Candidate'], 'comparisons':[['Candidate','Fprod']],
                  'profiles':{'common':common,'arms':{a:{'STS_SILVER_EXACT_ROOT_BUDGETS':'0',
                      'STS_SILVER_LEARNED_STOP':'1'} for a in ('Fprod','Candidate')}}}
        self.manifest = self.root/'manifest.json'
        self.save_manifest()
        for arm, won in [('Fprod',[0,1,0]),('Candidate',[1,0,1])]:
            prefix = self.run / (arm + '_shard0')
            paths = {k:Path(str(prefix)+s) for k,s in aw.SUFFIXES.items()}
            paths['csv'].write_text(','.join(aw.pa.EXPECTED)+'\n'+''.join(
                f'{s},{w},50,3,40,80,0,0,none,1.0\n' for s,w in zip(self.m['analysis_seeds'],won)))
            meta = {'asc':0,'threads':1,'sims':10000,'nSeeds':3,'seedBlock':{'lo':900001,'hi':900003},
                    'models':{'floor':'models/v_rich_trees.txt','win':'models/v_win_trees.txt'},
                    'config':{'fairPlay':True,'collectKeys':False,'executableGitSha':'a'*40,
                       'effectiveCombatBackend':'native_silver','silverExactRootBudgets':False,
                       'silverLearnedStopModel':'embedded-model','silverAdaptiveEnabled':False,
                       'silverReuseCapMode':'allocated','silverReuseCap':32768,
                       'silverLearnedStopBossFallback':False,'silverLearnedStopBossMax':0}}
            paths['meta'].write_text(json.dumps(meta)+'\n')
            paths['log'].write_text('[native OOC public encounter mixture: 8 futures]\n'
                '[benchmark stops after Act 3 boss]\n'+''.join(
                f'[public OOC receipt seed={s} futures=8 scorers=7]\n' for s in self.m['analysis_seeds']))
            paths['profile'].write_text(''.join(json.dumps({'seed':s,'thread_cpu_seconds':0.5})+'\n'
                for s in self.m['analysis_seeds']))
            env = dict(common,**self.m['profiles']['arms'][arm], STS_EXECUTABLE_GIT_SHA='a'*40,
                       STS_RUN_PROFILE=str(paths['profile']))
            receipt = {'arm':arm,'status':'completed','exit_code':0,'manifest':str(self.manifest),
                       'manifest_sha256':aw.digest(self.manifest),'source_sha':'a'*40,
                       'binary_sha256':aw.digest(self.binary), 'started_epoch':100.0,
                       'environment':env,'wall_seconds':3.0,
                       'command':['bash','tools/seed_guard.sh',str(self.binary),'bestbench','10000','3','0',
                                  '900001',str(paths['csv'])],
                       'outputs':{k:{'path':str(p),'sha256':aw.digest(p),'bytes':p.stat().st_size}
                                  for k,p in paths.items() if p.exists()}}
            self.receipt_path(arm).write_text(json.dumps(receipt))

    def tearDown(self): self.tmp.cleanup()
    def save_manifest(self): self.manifest.write_text(json.dumps(self.m))
    def receipt_path(self, arm='Fprod'): return self.run/(arm+'_shard0.receipt.json')
    def edit_receipt(self, change):
        p=self.receipt_path(); r=json.loads(p.read_text()); change(r); p.write_text(json.dumps(r))
    def rehash_output(self, key):
        def update(r):
            p=Path(r['outputs'][key]['path']); r['outputs'][key].update(sha256=aw.digest(p),bytes=p.stat().st_size)
        self.edit_receipt(update)
    def check(self): return aw.analyze(self.manifest,self.run)

    def test_complete_pairs_and_cpu(self):
        r=self.check(); c=r['comparisons']['Candidate-Fprod']
        self.assertEqual((c['candidate_only'],c['control_only']),(2,1))
        self.assertAlmostEqual(c['gain'],1/3)
        self.assertEqual(c['decision'],'DISCOVERY_OR_DEVELOPMENT_ONLY')
        self.assertEqual(r['arms']['Fprod']['observed_profile_thread_cpu_seconds_sum'],1.5)
        self.assertGreater(aw.wilson95(3,3)[1]-aw.wilson95(3,3)[0],0)
        self.assertEqual(len(r['inputs']),10)
    def test_changed_csv_refused(self):
        with (self.run/'Fprod_shard0.csv').open('a') as f: f.write('\n')
        with self.assertRaisesRegex(ValueError,'hash/size'): self.check()
    def test_changed_manifest_refused(self):
        self.m['purpose']='later alteration'; self.save_manifest()
        with self.assertRaisesRegex(ValueError,'manifest hash'): self.check()
    def test_extra_environment_refused(self):
        self.edit_receipt(lambda r:r['environment'].update(STS_CARD_WIN='1'))
        with self.assertRaisesRegex(ValueError,'environment'): self.check()
    def test_failed_attempt_without_csv_refused(self):
        failed = json.loads(self.receipt_path().read_text())
        failed.update(status='timeout',exit_code=124)
        (self.run/'Fprod_attemptfailed.receipt.json').write_text(json.dumps(failed))
        with self.assertRaisesRegex(ValueError,'unsuccessful subprocess'): self.check()
    def test_arbitrary_output_path_refused(self):
        self.edit_receipt(lambda r:r['outputs']['csv'].update(path=str(self.root/'foreign.csv')))
        with self.assertRaisesRegex(ValueError,'output path'): self.check()
    def test_missing_public_receipt_refused(self):
        p=self.run/'Fprod_shard0.log'; p.write_text('\n'.join(p.read_text().splitlines()[:-1])+'\n')
        self.rehash_output('log')
        with self.assertRaisesRegex(ValueError,'public receipt source coverage'): self.check()
    def test_wrong_loaded_model_refused(self):
        p=self.run/'Fprod_shard0.csv.meta.json'; m=json.loads(p.read_text()); m['models']['win']='elsewhere.txt'
        p.write_text(json.dumps(m)+'\n'); self.rehash_output('meta')
        with self.assertRaisesRegex(ValueError,'loaded model path'): self.check()
    def test_duplicate_and_reserved_seeds_refused(self):
        self.m['analysis_seeds'].append(900001)
        with self.assertRaisesRegex(ValueError,'duplicates'): aw.validate_manifest(self.m)
        self.m['analysis_seeds']=[610083000]; self.m['allowed_seeds']=[610083000]
        with self.assertRaisesRegex(ValueError,'confirmation cohort'): aw.validate_manifest(self.m)
    def test_confirmation_gates_and_one_contrast(self):
        self.m['phase']='confirmation'; self.m['confirmation']={'comparator':'Fprod','champion':'Candidate',
          'fixed_pairs':3,'frozen_epoch':90.0,'gates':{k:True for k in
          ('implementation_review','scientific_review','information_boundary','holdout_unopened_at_freeze')}}
        with self.assertRaisesRegex(ValueError,'outside reserved cohort'): aw.validate_manifest(self.m)
        self.m['analysis_seeds']=[610083000,610083001,610083002]
        self.m['allowed_seeds']=list(self.m['analysis_seeds'])
        aw.validate_manifest(self.m)
        self.m['confirmation']['gates']['scientific_review']=False
        with self.assertRaisesRegex(ValueError,'confirmation gate'): aw.validate_manifest(self.m)
        self.m['confirmation']['gates']['scientific_review']=True
        self.m['comparisons'].append(['Fprod','Candidate'])
        with self.assertRaisesRegex(ValueError,'one champion'): aw.validate_manifest(self.m)


if __name__=='__main__': unittest.main(verbosity=2)
