import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

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


if __name__=='__main__':unittest.main()
