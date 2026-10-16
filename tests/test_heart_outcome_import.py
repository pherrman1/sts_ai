import copy
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import heart_outcome_import as audit


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


def encode(value):return json.dumps(value).encode()
def lines(rows):return b'\n'.join(encode(r) for r in rows)+b'\n'


def payload():
    seed=110180000;prefix=f'seed-{seed}';policy={'fixed':'policy'}
    header=dict(schema='heart-trajectory-v1',type='header',seed=seed,producerSha=audit.SOURCE,
                objective='heart',ascension=20,combatSimulations=10000,collectKeys=True,
                stopAfterAct=0,capture=True,recordSchema='heart1-public-record-v2',
                recordPublicParityQualified=False,policy=policy)
    state=dict(type='state',index=0,origin='real-run-driver',act=1,floor=12,screen=5,supported=True,record=record())
    footer=dict(type='outcome',complete=True,integrityPassed=True,label=0,heartKilled=False,
                finalAct=1,finalFloor=12,finalHp=0,states=1,supportedStates=1)
    pre=dict(act=1,floor=12,screen='MAP',hp=70,maxHp=80,gold=100,x=0,y=0)
    support=dict(seed=seed,heart1_prior_nodes=10,heart1_prior_fallbacks=0,prior_leaf_steps=0,
                 heart1_leaf_steps=20,heart1_leaf_fallbacks=0)
    log=b'[heart1] loaded studentc.bin (dim 64, heads 4, hidden 256, layers 2, trim_map 1) prior=heart1 x leaf_policy=heart1'
    files={'.states.jsonl':lines([header,state,footer]),'.trace.jsonl':lines([dict(seed=seed,pre=pre,post={**pre,'hp':0})]),
           '.started.json':encode({'seed':seed,'capture':True,'sourceSha':audit.SOURCE}),
           '.log':log,'.mcts.csv':b'opaque fixture csv','.mcts.csv.actions.jsonl':b'',
           '.mcts.csv.support.jsonl':lines([support])}
    receipt={'seed':seed,'sourceSha':audit.SOURCE,'binarySha256':audit.BINARY,'returncode':0,
             'processReturncode':0,'seconds':10.,'policy':policy,'states':1,'supportedStates':1,
             'environment':{'HOME':'/tmp','PATH':'/bin','STS_OOC_DECISION_TRACE':'/out/'+prefix+'.trace.jsonl',
                            'STS_OOC_MCTS_TRACE':'/out/'+prefix+'.mcts.csv'},
             'command':['bash','/bundle/seed_guard.sh','/bundle/one_combat','heartoutcomegen','1',str(seed),'/out/'+prefix+'.states.jsonl','on'],
             'modelUse':audit.capture.runtime_contract(audit.REPO/'tools',log.decode(),support,seed)}
    files['.receipt.json']=encode(receipt)
    return refresh(files)


def refresh(files):
    rec=json.loads(files['.receipt.json'])
    rec['files']={f'seed-110180000{s}':audit.digest(v) for s,v in files.items() if s!='.receipt.json'}
    files['.receipt.json']=encode(rec);return files


class ImportTests(unittest.TestCase):
    def verify(self,files):
        with tempfile.TemporaryDirectory() as d:
            return audit.verify_unit(110180000,files,{'environment':{}},{'fixed':'policy'},Path(d)/'state.jsonl')

    def test_valid_complete_source_has_one_source_label(self):
        got=self.verify(payload());self.assertEqual((got['label'],got['states']),(0,1))

    def test_receipt_hash_drift_refused(self):
        files=payload();files['.log']+=b'changed'
        with self.assertRaisesRegex(ValueError,'raw-file hash'):self.verify(files)

    def test_partial_outcome_and_counterfactual_and_bad_schema_refused(self):
        for change in ('partial','counterfactual','schema'):
            files=payload();rows=[json.loads(l) for l in files['.states.jsonl'].splitlines()]
            if change=='partial':rows.pop()
            elif change=='counterfactual':rows[1]['origin']='mcts-particle'
            else:del rows[1]['record']['obs.deck.cards']
            files['.states.jsonl']=lines(rows)
            with self.assertRaises(ValueError):self.verify(refresh(files))

    def test_wrong_producer_or_environment_or_capture_command_refused(self):
        for field,value in [('sourceSha','wrong'),('environment',{}),('command',[])]:
            files=payload();r=json.loads(files['.receipt.json']);r[field]=value;files['.receipt.json']=encode(r)
            with self.assertRaises(ValueError):self.verify(files)

    def test_actual_trace_and_public_observation_alignment(self):
        files=payload();trace=json.loads(files['.trace.jsonl']);trace['pre']['hp']=1
        files['.trace.jsonl']=lines([trace])
        with self.assertRaisesRegex(ValueError,'public observation'):self.verify(refresh(files))

    def test_prior_fallback_or_telemetry_drift_refused(self):
        files=payload();s=json.loads(files['.mcts.csv.support.jsonl']);s['heart1_prior_fallbacks']=5
        files['.mcts.csv.support.jsonl']=lines([s])
        with self.assertRaisesRegex(ValueError,'runtime contract'):self.verify(refresh(files))

    def test_sealed_test_and_partial_never_reach_tar_parser(self):
        for name,split in [('SEALED-test.tar.gz','test'),('SEALED-test.tar.gz','train'),
                           ('SEALED-partial-out.tar.gz','validation')]:
            with patch.object(audit.tarfile,'open') as opened:
                with self.assertRaisesRegex(ValueError,'prohibited'):list(audit.archive_units(Path(name),split,[]))
                opened.assert_not_called()

    def test_recovery_selection_uses_halves_once_without_superseded_workers(self):
        selected=audit.selected_deliveries();self.assertEqual(len(selected),49)
        covered=[]
        for folder,worker,half in selected:
            owned=[s['seed'] for s in audit.capture.assignments() if s['worker']==worker]
            covered+=owned if half is None else owned[half::2]
            if worker in audit.LOST:self.assertTrue(folder.startswith('r'));self.assertIn(half,(0,1))
        self.assertEqual(len(covered),1800);self.assertEqual(len(set(covered)),1800)

    def archive(self,names):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);path=Path(temp.name)/'train.tar.gz'
        with tarfile.open(path,'w:gz') as tar:
            for name in names:
                info=tarfile.TarInfo(name);body=b'{}';info.size=len(body);tar.addfile(info,io.BytesIO(body))
        return path

    def test_archive_refuses_cross_split_unsafe_duplicate_and_partial_sources(self):
        cases=[['../outside'],['validation/seed-110180000.log'],['train/seed-110180001.log'],
               ['train/seed-110180000.log']*2,['train/seed-110180000.log']]
        for names in cases:
            with self.assertRaises(ValueError):list(audit.archive_units(self.archive(names),'train',[110180000]))

    def test_checksum_inventory_rejects_unlisted_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'blob').write_bytes(b'opaque')
            (root/'SHA256SUMS').write_text(audit.digest(b'opaque')+'  ./blob\n')
            self.assertEqual(len(audit.verify_checksums(root)),1)
            (root/'unlisted').write_text('extra')
            with self.assertRaisesRegex(ValueError,'inventory'):audit.verify_checksums(root)


if __name__=='__main__':unittest.main()
