import copy
import tarfile
import time
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import heart_outcome_collect as collect


def record():
    return {'obs.fixed_observation':[70,80,100,12,3,1,20,0,0,1],
            'obs.deck.cards':[1,2],'obs.deck.upgrades':[0,1],
            'obs.relics.relics':[1],'obs.relics.relic_counters':[3],
            'obs.potions':[2],'obs.map.xs':[0,0],'obs.map.ys':[0,1],
            'obs.map.roomTypes':[4,3],'obs.map.pathXs':[[0,-1,-1],[-1,-1,-1]],
            'obs.map.burningEliteX':0,'obs.map.burningEliteY':1,'obs.mapX':0,'obs.mapY':0,
            'cards_offered.cards':[3],'cards_offered.upgrades':[0],
            'relics_offered':[],'potions_offered':[], 'fixed_actions':[],
            'paths_offered':[0],'screen_state':5,'select_screen_type':0}

def rows(label=0):
    return [dict(schema='heart-trajectory-v1', type='header', seed=7, producerSha='a'*40,
        objective='heart', ascension=20, combatSimulations=10000, collectKeys=True,
        stopAfterAct=0, capture=True, recordSchema='heart1-public-record-v2',
        recordPublicParityQualified=False, policy={'teacher':'fixed'}),
        dict(type='state', index=0, origin='real-run-driver', act=1, floor=0, screen=5,
             supported=True, record=record()),
        dict(type='outcome', complete=True, integrityPassed=True, label=label,
             heartKilled=bool(label), finalAct=4 if label else 1, states=1, supportedStates=1)]


class OutcomeTests(unittest.TestCase):
    def check(self, data):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'states.jsonl'
            path.write_text(''.join(json.dumps(r)+'\n' for r in data))
            return collect.trajectory(path,7,'a'*40)

    def test_completed_loss_is_label_zero_and_win_is_one(self):
        for label in (0,1):self.assertEqual(self.check(rows(label))[1]['label'],label)

    def test_timeout_or_partial_file_is_never_a_loss(self):
        for data in (rows()[:-1], rows()[1:], rows()[:1]):
            with self.assertRaises(ValueError):self.check(data)

    def test_integrity_failure_and_nonheart_victory_refused(self):
        for field,value in [('integrityPassed',False),('complete',False),('finalAct',3),('label',True)]:
            data=rows(1);data[-1][field]=value
            with self.assertRaises(ValueError):self.check(data)

    def test_counterfactual_and_duplicate_observation_refused(self):
        for field,value in [('origin','hypothetical'),('index',5),('supported',1)]:
            data=rows();data[1][field]=value
            with self.assertRaises(ValueError):self.check(data)

    def test_label_and_rng_never_features(self):
        for key in ('seed','rng','label','target','outcome'):
            data=rows();data[1]['record'][key]=1
            with self.assertRaises(ValueError):self.check(data)

    def test_fixed_disjoint_splits_and_balanced_worker_assignments(self):
        sources=collect.assignments()
        self.assertEqual(len({s['seed'] for s in sources}),1800)
        self.assertEqual([sum(s['split']==part for s in sources) for part in ('train','validation','test')],[1080,360,360])
        for worker in range(45):
            assigned=[s for s in sources if s['worker']==worker]
            self.assertEqual(len(assigned),40)
            self.assertEqual([sum(s['split']==part for s in assigned) for part in ('train','validation','test')],[24,8,8])

    def test_model_or_seed_drift_refused(self):
        for field,value in [('seed',8),('producerSha','b'*40),('collectKeys',False),('stopAfterAct',3)]:
            data=rows();data[0][field]=value
            with self.assertRaises(ValueError):self.check(data)

    def test_seed_guard_refuses_more_than_one_source(self):
        guard=Path(__file__).resolve().parents[1]/'tools/seed_guard.sh'
        checked=subprocess.run(['bash',str(guard),'guard-only','one_combat','heartoutcomegen','2','7','unused','on'],capture_output=True)
        self.assertNotEqual(checked.returncode,0)
        self.assertIn(b'exactly one',checked.stderr)

    def test_activation_requires_exact_canary_and_export_and_is_once(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); bundle=root/'bundle';bundle.mkdir()
            collect.write(bundle/'bundle.json',{})
            plan=root/'plan.json';collect.write(plan,{})
            q=root/'qualification';q.mkdir()
            canary=q/'canary.json';collect.write(canary,{'verdict':'PASS','role':'cloud',
                'planSha256':collect.sha(plan),'bundleSha256':collect.sha(bundle/'bundle.json'),'policy':{'teacher':'fixed'},'actionParity':True,'files':{}})
            export=q/'export-roundtrip.json';collect.write(export,{'bytes':256*1024**2,
                'sourceHost':'vm-a','destinationHost':'vm-b','sourceSha256':'a'*64,'returnedSha256':'a'*64})
            data={'verdict':'PASS','sourceSha':'b'*40,'planSha256':collect.sha(plan),
                'bundleSha256':collect.sha(bundle/'bundle.json'),'durableExportRoundtrip':True,
                'canarySha256':collect.sha(canary),'exportReceiptSha256':collect.sha(export)}
            review=q/'review.json';collect.write(review,data)
            with patch.object(collect,'verify_plan',return_value={'sourceSha':'b'*40}):
                bad=q/'bad.json';collect.write(bad,{**data,'canarySha256':'wrong'})
                with self.assertRaisesRegex(ValueError,'qualification'):
                    collect.activate(plan,bundle,bad,root/'activation.json')
                self.assertFalse((root/'COHORT-STARTED.json').exists())
                collect.activate(plan,bundle,review,root/'activation.json')
                activated=json.loads((root/'activation.json').read_text())
                self.assertEqual(activated['deadlineUtc']-activated['startedUtc'],21600)
                with self.assertRaises(FileExistsError):
                    collect.activate(plan,bundle,review,root/'activation.json')

    def test_worker_refuses_expired_campaign_before_source_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bundle=root/'bundle';bundle.mkdir()
            collect.write(bundle/'bundle.json',{});plan=root/'plan.json';collect.write(plan,{})
            activation=root/'activation.json';collect.write(activation,{'planSha256':collect.sha(plan),
                'bundleSha256':collect.sha(bundle/'bundle.json'),'startedUtc':0,'deadlineUtc':21600})
            with patch.object(collect,'verify_plan'),patch.object(collect,'unit') as unit:
                with self.assertRaisesRegex(ValueError,'expired'):
                    collect.worker(plan,bundle,activation,root/'worker',0,collect.sha(activation))
            unit.assert_not_called();self.assertFalse((root/'worker').exists())


    def test_malformed_supported_records_refused(self):
        for bad in ({'screen_state':5}, {**record(),'obs.deck.upgrades':[]},
                    {**record(),'obs.fixed_observation':[float('nan')]*10},
                    {**record(),'obs.map.pathXs':[[0],[-1,-1,-1]]},
                    {**record(),'obs.deck.cards':[999,2]}):
            data=rows();data[1]['record']=bad
            with self.assertRaises(ValueError):self.check(data)

    def test_runtime_contract_shape_prior_and_rollout_support(self):
        bundle=Path(__file__).resolve().parents[1]/'tools'
        text='[heart1] loaded studentc.bin (dim 64, heads 4, hidden 256, layers 2, trim_map 1) prior=heart1 x leaf_policy=heart1'
        support=dict(seed=7,heart1_prior_nodes=100,heart1_prior_fallbacks=0,
                     prior_leaf_steps=0,heart1_leaf_steps=100,heart1_leaf_fallbacks=0)
        self.assertEqual(collect.runtime_contract(bundle,text,support,7)['share'],1)
        with self.assertRaises(ValueError):collect.runtime_contract(bundle,text.replace('dim 64','dim 32'),support,7)
        for key,value in [('heart1_prior_fallbacks',20),('heart1_prior_nodes',True),
                          ('heart1_leaf_fallbacks',20),('prior_leaf_steps',1)]:
            with self.assertRaises(ValueError):collect.runtime_contract(bundle,text,{**support,key:value},7)

    def test_semantic_failure_persists_failed_unit_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bundle=root/'bundle';bundle.mkdir();out=root/'out';out.mkdir()
            (bundle/'one_combat').write_bytes(b'synthetic executable')
            class Child:
                def wait(self, timeout):return 0
            with patch.object(collect.subprocess,'Popen',return_value=Child()):
                receipt=collect.unit({'sourceSha':'a'*40,'environment':{}},bundle,out,7,'synthetic')
            self.assertEqual(receipt['returncode'],65)
            self.assertEqual(receipt['processReturncode'],0)
            self.assertIn('contractError',receipt)
            self.assertTrue((out/'synthetic.receipt.json').exists())

    def test_worker_refuses_unapproved_or_changed_activation_before_units(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bundle=root/'bundle';bundle.mkdir()
            collect.write(bundle/'bundle.json',{});plan=root/'plan.json';collect.write(plan,{})
            start=time.time();activation=root/'activation.json'
            collect.write(activation,{'planSha256':collect.sha(plan),
                'bundleSha256':collect.sha(bundle/'bundle.json'),'startedUtc':start,'deadlineUtc':start+21600})
            with patch.object(collect,'verify_plan'),patch.object(collect,'unit') as unit:
                with self.assertRaisesRegex(ValueError,'approved identity'):
                    collect.worker(plan,bundle,activation,root/'worker',0,'wrong')
                with self.assertRaises((KeyError,ValueError)):
                    collect.worker(plan,bundle,activation,root/'worker',0,collect.sha(activation))
            unit.assert_not_called();self.assertFalse((root/'worker').exists())

    def test_worker_failure_still_exports_partial_and_completed_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bundle=root/'bundle';bundle.mkdir()
            collect.write(bundle/'bundle.json',{});plan=root/'plan.json';collect.write(plan,{})
            approval=root/'review.json';collect.write(approval,{})
            start=time.time();latch=root/'COHORT-STARTED.json'
            collect.write(latch,{'planSha256':collect.sha(plan),'startedUtc':start})
            activation=root/'activation.json';collect.write(activation,{'planSha256':collect.sha(plan),
                'bundleSha256':collect.sha(bundle/'bundle.json'),'startedUtc':start,'deadlineUtc':start+21600,
                'approvalRelativePath':'review.json','approvalSha256':collect.sha(approval),
                'latchSha256':collect.sha(latch),'policy':{'teacher':'fixed'}})
            def fake_unit(plan,bundle,out,seed,tag,**kwargs):
                (out/(tag+'.partial')).write_text('preserved partial')
                if seed==collect.FIRST:raise ValueError('synthetic schema failure')
                return {'seed':seed,'returncode':0}
            original_read=Path.read_text
            def read(path,*args,**kwargs):
                if str(path)=='/sys/fs/cgroup/cpu.max':return '400000 100000'
                return original_read(path,*args,**kwargs)
            with patch.object(collect,'verify_plan',return_value={'sources':collect.assignments()}), \
                 patch.object(collect,'qualification',return_value={'policy':{'teacher':'fixed'}}), \
                 patch.object(collect,'unit',side_effect=fake_unit), \
                 patch.object(collect.os,'sched_getaffinity',return_value={0,1,2,3}), \
                 patch.object(Path,'read_text',read):
                collect.worker(plan,bundle,activation,root/'worker',0,collect.sha(activation))
            receipt=json.loads((root/'worker/worker-receipt.json').read_text())
            self.assertFalse(receipt['complete']);self.assertEqual(len(receipt['sources']),40)
            self.assertEqual(receipt['returncodes'].count(70),1)
            self.assertEqual(len(receipt['archives']),3)
            with tarfile.open(root/'worker/train.tar.gz') as tar:
                self.assertIn('train/seed-'+str(collect.FIRST)+'.partial',tar.getnames())


if __name__=='__main__':unittest.main()
