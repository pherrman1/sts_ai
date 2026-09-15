"""CI checks the tracked deployable V2 artifact without external checkpoints."""
import hashlib,json,os,struct,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ARTIFACT=ROOT/'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
FIXTURES=ROOT/'tests/fixtures/combat_transition_near_full.jsonl'
class Artifact(unittest.TestCase):
    def probe(self):
        binary=os.environ.get('STS_COMBAT_TRANSITION_PROBE')
        if binary:return Path(binary)
        for name in ('linux-gcc-debug-ccache','linux-gcc-debug'):
            p=ROOT/'build'/name/'combat_transition_runtime_probe'
            if p.exists():return p
        self.fail('native probe must be built')
    def test_actual_artifact_and_native_paths(self):
        self.assertEqual(hashlib.sha256(ARTIFACT.read_bytes()).hexdigest(),'22c855e0667a58a73835505672b0ae6d03f12e9fb8d64f08893810199246e94e')
        run=subprocess.run([str(self.probe()),str(ARTIFACT),str(FIXTURES),'near-full'],text=True,capture_output=True,check=True)
        rows=list(map(json.loads,run.stdout.splitlines()));self.assertEqual(len(rows),len(FIXTURES.read_text().splitlines()));unsupported=[r for r in rows if not r['supported']];self.assertEqual(len(unsupported),3);self.assertTrue(all(r['unsupportedNoDraw'] for r in unsupported))
        sampled=0
        for row in rows:
            self.assertEqual(row['expectation']['supported'],row['supported'])
            if not row['supported']:
                self.assertEqual(row['expectation']['death'],0)
                self.assertEqual(row['expectation']['winningHpFraction'],0)
                continue
            self.assertAlmostEqual(row['expectation']['death'],1-row['survival'],places=6)
            self.assertTrue(0 < row['expectation']['winningHpFraction'] <= 1)
            self.assertEqual(len(row['diagnostics']['potion']),64)
            for sample in row['samples']:
                sampled+=1;post=sample['rawPost']
                if sample['outcome']==1:self.assertEqual(sample['wordsUsed'],1);continue
                self.assertTrue(1<=post['curHp']<=post['maxHp']);self.assertEqual(post['potionCount'],sum(p>1 for p in post['potions']));self.assertEqual(post['smokeBombUsed'],sample['outcome']==3)
        self.assertGreater(sampled,0)
    def test_incompatible_qualification_cannot_load(self):
        original=ARTIFACT.read_bytes();magic=b'COMBAT_TRANSITION_RUNTIME_V2\0';version,length=struct.unpack_from('<II',original,len(magic));start=len(magic)+8;header=json.loads(original[start:start+length]);payload=original[start+length:]
        for case in ('qualification','source','cohort'):
            altered=json.loads(json.dumps(header))
            if case=='qualification':altered['qualification']['classification']='FAIL'
            elif case=='source':altered['sources']['HP']='0'*64
            else:altered['supportCensus']['TEST']['supportedIndexSha256']='0'*64
            encoded=json.dumps(altered,sort_keys=True,separators=(',',':')).encode()
            with tempfile.TemporaryDirectory() as folder:
                p=Path(folder)/'incompatible.native';p.write_bytes(magic+struct.pack('<II',version,len(encoded))+encoded+payload);run=subprocess.run([str(self.probe()),str(p),str(FIXTURES)],text=True,capture_output=True);self.assertNotEqual(run.returncode,0,case)
if __name__=='__main__':unittest.main()
