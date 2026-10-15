#!/usr/bin/env python3
"""One frozen zero-future target preflight. No scheduler or positive futures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[5]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()
def require(ok,reason):
    if not ok: raise ValueError(reason)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--protocol',required=True,type=Path)
    ap.add_argument('--protocol-sha256',required=True)
    a=ap.parse_args()
    require(sha(a.protocol)==a.protocol_sha256,'reviewed protocol hash mismatch')
    p=json.loads(a.protocol.read_text())
    require(p['schema']=='targeted_rest_protocol_v1','wrong protocol schema')
    require(p['source_seed']==610081015 and p['act']==3 and p['floor']==44,'unauthorized target')
    require(sha(p['binary'])==p['binary_sha256'],'binary changed')
    require(sha(p['teacher'])==p['teacher_sha256'],'teacher changed')
    require(sha(p['preflight_target'])==p['preflight_target_sha256'],'target changed')
    teacher=json.loads(Path(p['teacher']).read_text())
    require(teacher['git_sha']==p['source_sha'] and teacher['executable_sha256']==p['binary_sha256'],'teacher producer mismatch')
    env=p['environment']
    require(env==teacher['environment'],'protocol/teacher environment mismatch')
    require(env['STS_FAIR']=='1' and env['STS_STOP_AFTER_ACT']=='3' and env['STS_OOC_PUBLIC_FUTURES']=='8','wrong fair horizon')
    require(env['STS_EXECUTABLE_GIT_SHA']==p['source_sha'],'source environment mismatch')
    require(p['timeout_seconds_per_invocation']==1800,'unexpected timeout')
    for artifact in teacher['model_artifacts']:
        require(sha(ROOT/artifact['path'])==artifact['sha256'],'model changed: '+artifact['role'])
    target=json.loads(Path(p['preflight_target']).read_text())
    require(target=={'schemaVersion':'ooc_cf_target_v1','sourceSeed':p['source_seed'],'act':3,'floor':44,'screen':'REST','optionKeys':[]},'target is not zero-future legal inventory')
    cmd=p['preflight_command']; require(len(cmd)==15,'unexpected command shape')
    prefix=Path(cmd[5]).resolve()
    require(prefix.is_relative_to(ROOT/'build/overnight_20261008'),'output outside campaign raw directory')
    expected=['bash','tools/seed_guard.sh',p['binary'],'ooccfpilotgen','1',str(prefix),str(p['source_seed']),p['teacher'],'0','1','1','2','REST',p['preflight_target'],'0']
    require(cmd==expected,'only exact reviewed zero-future command is supported')
    suffixes=['labels.csv','options.csv','sources.csv','map.csv','manifest.json','target.json','log','receipt.json']
    paths={suffix:Path(str(prefix)+'.'+suffix) for suffix in suffixes}
    require(not any(os.path.lexists(path) for path in paths.values()),'refusing existing invocation outputs')
    require(not list(prefix.parent.glob(prefix.name+'.*')) if prefix.parent.exists() else True,'unknown prior prefix output')
    prefix.parent.mkdir(parents=True,exist_ok=True)
    receipt={'schema':'overnight_targeted_rest_invocation_v1','mode':'ZERO_FUTURE_PREFLIGHT',
             'protocol':str(a.protocol.resolve()),'protocol_sha256':a.protocol_sha256,
             'source_sha':p['source_sha'],'binary_sha256':p['binary_sha256'],
             'teacher_sha256':p['teacher_sha256'],'target_sha256':p['preflight_target_sha256'],
             'command':cmd,'environment':env,'script_sha256':sha(__file__),
             'started_epoch':time.time(),'status':'running','positive_futures':0}
    with paths['receipt.json'].open('x') as f: json.dump(receipt,f,indent=2); f.write('\n')
    started=time.monotonic()
    try:
        with paths['log'].open('x') as log:
            result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        receipt.update(status='completed' if result.returncode==0 else 'failed',exit_code=result.returncode)
    except subprocess.TimeoutExpired:
        receipt.update(status='timeout',exit_code=124)
    except Exception as error:
        receipt.update(status='launcher_error',exit_code=125,error=repr(error))
    receipt.update(wall_seconds=time.monotonic()-started,finished_epoch=time.time())
    # Include every emitted prefix file, even an unexpected one; never drop failures.
    receipt['outputs']={path.name[len(prefix.name)+1:]:{'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}
        for path in sorted(prefix.parent.glob(prefix.name+'.*')) if path!=paths['receipt.json'] and path.is_file()}
    paths['receipt.json'].write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ('status','exit_code','wall_seconds','positive_futures')},indent=2),flush=True)
    return receipt['exit_code']

if __name__=='__main__': raise SystemExit(main())
