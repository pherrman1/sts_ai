import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools.run_ooc_semantic_confirmation import capture_distribution, verify_evaluated_binding, digest, START, STOP

class RunnerTests(unittest.TestCase):
    def test_exact_capture_cohort(self):
        manifests=[]
        for s in range(START,STOP,16):
            manifests.append({'sampling':{'sourceSeeds':list(range(s,s+16))},'decisions':[{'sourceSeed':i,'actions':[{'semanticSource':7,'semanticEffect':5,'semanticPayload':{'type':'reward'}},{'semanticSource':7,'semanticEffect':14,'semanticPayload':{'type':'none'}}]} for i in range(s,s+16)]})
        result=capture_distribution(manifests)
        self.assertEqual((result['decisions'],result['action_rows']),(1024,2048))
        broken=copy.deepcopy(manifests);broken[0]['sampling']['sourceSeeds'][0]+=1
        with self.assertRaises(ValueError):capture_distribution(broken)
        broken=copy.deepcopy(manifests);broken[0]['decisions'].pop()
        with self.assertRaises(ValueError):capture_distribution(broken)

    def test_reused_outputs_must_bind_current_shard_and_producer(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'capture.json';captured={'sampling':{'sourceSeeds':[992000]}};p.write_text(json.dumps(captured))
            teacher={'teacher_id':'frozen'}
            base={'frozen_manifest':{'path':str(p),'sha256':digest(p)},'producer_git_sha':'a'*40,'producer_executable_sha256':'b'*64}
            sem={**base,'sampling':captured['sampling'],'combat_teacher':teacher};comb={**base,'teacher':teacher}
            verify_evaluated_binding(sem,comb,captured,p,teacher,'a'*40,'b'*64)
            for target in (0,1):
                for field,value in [('producer_git_sha','c'*40),('producer_executable_sha256','c'*64),('frozen_manifest',{'path':str(p)+'other','sha256':digest(p)})]:
                    docs=[copy.deepcopy(sem),copy.deepcopy(comb)];docs[target][field]=value
                    with self.assertRaises(ValueError):verify_evaluated_binding(*docs,captured,p,teacher,'a'*40,'b'*64)
            sem['sampling']={'sourceSeeds':[992001]}
            with self.assertRaises(ValueError):verify_evaluated_binding(sem,comb,captured,p,teacher,'a'*40,'b'*64)

if __name__=='__main__':unittest.main()
