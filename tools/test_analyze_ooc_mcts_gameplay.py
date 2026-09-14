import csv,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import analyze_ooc_mcts_gameplay as a

FIXTURE=Path(__file__).resolve().parents[1]/'docs/experiments/evidence/live_ooc_mcts_2048_2026-09-14'


class GameplayAnalysisTest(unittest.TestCase):
    def test_historical_result_reproduces(self):
        actual=json.loads(json.dumps(a.analyze(FIXTURE/'control.csv',FIXTURE/'treatment.csv',combat_sims=10000,mcts_sims=2048)))
        expected=json.loads((FIXTURE/'result.json').read_text())
        for key,value in expected.items():
            if key!='input_sha256': self.assertEqual(actual[key],value,key)

    def synthetic64(self,folder):
        for arm in ('control','treatment'):
            for suffix in ('.csv','.csv.mcts.csv'):
                with (FIXTURE/(arm+suffix)).open() as f: original=sorted(csv.DictReader(f),key=lambda r:int(r['seed']));headers=list(original[0])
                data=[]
                for i in range(64):
                    row=dict(original[i%32],seed=str(980000+i))
                    if suffix.endswith('.mcts.csv') and arm=='treatment':
                        row['simulations']=str(10000*int(row['mctsOwned'])+int(row['discardedSimulations']))
                        row['simulationAttempts']=str(int(row['simulations'])+int(row['mctsSupportAborts']))
                    data.append(row)
                with (folder/(arm+suffix)).open('w') as f:
                    writer=csv.DictWriter(f,fieldnames=headers);writer.writeheader();writer.writerows(data)
            config=json.loads((FIXTURE/(arm+'.config.json')).read_text())
            if arm=='treatment': config['env']['STS_OOC_MCTS_SIMS']='10000'
            (folder/(arm+'.config.json')).write_text(json.dumps(config))
            (folder/(arm+'.csv.meta.json')).write_text((FIXTURE/(arm+'.csv.meta.json')).read_text())
            reasons=sorted(map(json.loads,(FIXTURE/(arm+'.csv.mcts.csv.support.jsonl')).read_text().splitlines()),key=lambda r:r['seed'])
            (folder/(arm+'.csv.mcts.csv.support.jsonl')).write_text('\n'.join(json.dumps(dict(reasons[i%32],seed=980000+i)) for i in range(64))+'\n')

    def test_64_membership_aggregation_and_corruption_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);self.synthetic64(folder)
            result=a.analyze(folder/'control.csv',folder/'treatment.csv',bootstrap_samples=1000,combat_sims=10000,mcts_sims=10000,seed_start=980000,seed_count=64)
            self.assertEqual(result['seeds'],list(range(980000,980064)))
            self.assertEqual((result['control_wins'],result['treatment_wins']),(42,48))
            self.assertEqual(result['same_result_seeds'],38)
            self.assertAlmostEqual(result['diagnostics']['mean_mctsOwned_per_run'],3861/32)
            with self.assertRaises(ValueError): a.analyze(folder/'control.csv',folder/'treatment.csv',seed_count=0)
            with self.assertRaises(ValueError): a.analyze(folder/'control.csv',folder/'treatment.csv',seed_start=980001,seed_count=64)
            p=folder/'treatment.csv.mcts.csv.support.jsonl';lines=p.read_text().splitlines();p.write_text('\n'.join(lines[:-1])+'\n')
            with self.assertRaisesRegex(ValueError,'support reason seed'): a.analyze(folder/'control.csv',folder/'treatment.csv',combat_sims=10000,mcts_sims=10000,seed_start=980000,seed_count=64)
            self.synthetic64(folder);p=folder/'control.csv';lines=p.read_text().splitlines();p.write_text('\n'.join(lines[:-1])+'\n')
            with self.assertRaisesRegex(ValueError,'exactly paired seeds'): a.analyze(folder/'control.csv',folder/'treatment.csv',seed_start=980000,seed_count=64)


if __name__=='__main__': unittest.main()
