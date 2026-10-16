import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import heart_outcome_collect as collect


def rows(label=0):
    return [dict(schema='heart-trajectory-v1', type='header', seed=7, producerSha='a'*40,
        objective='heart', ascension=20, combatSimulations=10000, collectKeys=True,
        stopAfterAct=0, capture=True, recordSchema='heart1-public-record-v2',
        recordPublicParityQualified=False),
        dict(type='state', index=0, origin='real-run-driver', act=1, floor=0, screen=1,
             supported=True, record={'screen_state':1}),
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
                'planSha256':collect.sha(plan),'bundleSha256':collect.sha(bundle/'bundle.json'),'files':{}})
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
                    collect.worker(plan,bundle,activation,root/'worker',0)
            unit.assert_not_called();self.assertFalse((root/'worker').exists())


if __name__=='__main__':unittest.main()
