import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools.run_ooc_semantic_confirmation import capture_distribution, verify_evaluated_binding, digest, START, STOP, shard_command

class RunnerTests(unittest.TestCase):
    def test_local_shard_uses_frozen_guard_without_host_context(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'producer with spaces'
            (source / 'tools').mkdir(parents=True)
            guard = source / 'tools/seed_guard.sh'
            guard.write_text('exec "$@"\n')
            binary = source / 'one_combat'
            binary.write_text('#!/bin/sh\npwd; printf "%s\\n" "$@"\n')
            binary.chmod(0o755)
            # Fake timer forwards argv; no gameplay or GNU time dependency.
            timer = source / 'timer'
            timer.write_text('#!/bin/sh\nshift 3; exec "$@"\n')
            timer.chmod(0o755)
            args = ['oocsemanticcapture', '16', '992000', 'output with spaces']
            command = shard_command(timer, source, binary, source/'shard', 'capture', args)
            result = subprocess.run(command, cwd=source, env={'PATH': '/usr/bin:/bin'},
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [str(source), *args])

    def test_exact_capture_cohort(self):
        manifests=[]
        for s in range(START,STOP,16):
            manifests.append({'sampling':{'sourceSeeds':list(range(s,s+16))},'decisions':[{'sourceSeed':i,'actions':[{'semanticSource':7,'semanticEffect':5,'semanticPayload':{'type':'reward'}},{'semanticSource':7,'semanticEffect':14,'semanticPayload':{'type':'none'}}]} for i in range(s,s+16)]})
        result=capture_distribution(manifests)
        self.assertEqual((result['decisions'],result['action_rows']),(1024,2048))
        # Evaluation recomputes this gate and compares it to the JSON on disk.
        # Integer counter keys used to make an unchanged gate reject itself.
        self.assertEqual(json.loads(json.dumps(result,sort_keys=True)),result)
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
