#!/usr/bin/env python3
"""One fixed preflight, selection or frozen-choice evaluation; no scheduler/reselection."""
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
    ap.add_argument('--stage',choices=('preflight','selection','evaluation'),default='preflight')
    ap.add_argument('--target',type=Path)
    ap.add_argument('--target-sha256')
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
    bound_target_path=Path(p['preflight_target'])
    binding=None
    futures=0
    if a.stage in ('selection','evaluation'):
        require(a.target is not None and a.target_sha256 is not None,'selection requires a hashed bound target')
        require(sha(a.target)==a.target_sha256,'selection target changed')
        bound=json.loads(a.target.read_text())
        preflight_path=Path(str(prefix)+'.target.json')
        preflight_hash='681c6fca6e29d8fc0bd3fa6852bae8273b2c2580a6414ccde63c1499fd04e8c3'
        require(sha(preflight_path)==preflight_hash,'approved target preflight changed')
        preflight=json.loads(preflight_path.read_text())
        keys=[f'ooc:v1:effect=0:source=0:card={i}:misc=0:upgraded=0:bottle=-1:occurrence=0' for i in (234,112,187)]
        choice_binding=None
        if a.stage=='evaluation':
            choice_path=Path(__file__).resolve().parent/'targeted_rest_631f_selection_choice.json'
            choice_sha='c4f8f74597ca5c9b423a4ae40920ab76ca70cf2559965916bd0784712ee000a8'
            require(sha(choice_path)==choice_sha,'frozen choice changed')
            choice=json.loads(choice_path.read_text())
            require(choice['selected_option_key']==keys[0] and choice['baseline_option_key']=='ooc:v1:effect=17:source=1:none','frozen choice identity changed')
            require(choice['source_sha']==p['source_sha'] and choice['binary_sha256']==p['binary_sha256'] and choice['protocol_sha256']==a.protocol_sha256,'frozen choice producer/protocol changed')
            require(choice['selection_k']==list(range(16)) and choice['evaluation_outcomes_opened'] is False,'choice not frozen before evaluation')
            require(p['evaluation_k']==list(range(16,48)),'evaluation protocol changed')
            for artifact in choice['inputs']:
                require(sha(artifact['path'])==artifact['sha256'],'choice input changed')
            keys=[choice['selected_option_key']]
            choice_binding={'path':str(choice_path),'sha256':choice_sha,'frozen_epoch':choice['frozen_epoch'],
                            'selected_option_key':keys[0],'baseline_option_key':choice['baseline_option_key']}
        expected_bound={'schemaVersion':'ooc_cf_target_v1','sourceSeed':p['source_seed'],'act':3,'floor':44,'screen':'REST',
            'decisionIdx':93,'publicStateSha256':'11a1ea6ea301c078ce522c00acd92b8f4cac9e39038d48677ea498117bc7f332',
            'preflightReceiptPath':str(preflight_path),'preflightReceiptSha256':preflight_hash,'optionKeys':keys}
        require(bound==expected_bound,'selection target differs from approved identity/options')
        require(p['selection_k']==list(range(16)) and p['preserve_baseline'] is True,'selection protocol changed')
        require(all(key in preflight['legalOptionKeys'] for key in keys),'requested alternative not legal')
        require(preflight['identity']['chosenKey']=='ooc:v1:effect=17:source=1:none','baseline changed')
        prefix=prefix.parent/a.stage
        bound_target_path=a.target.resolve(); futures=32 if a.stage=='evaluation' else 16
        start=16 if a.stage=='evaluation' else 0
        cmd=list(cmd); cmd[5]=str(prefix); cmd[8]=str(futures); cmd[13]=str(bound_target_path); cmd[14]=str(start)
        binding={'target':str(bound_target_path),'target_sha256':a.target_sha256,
                 'preflight_receipt':str(preflight_path),'preflight_receipt_sha256':preflight_hash,
                 'identity':preflight['identity'],'future_k':list(range(start,start+futures)),
                 'frozen_choice':choice_binding}
    else:
        require(a.target is None and a.target_sha256 is None,'preflight target is protocol-owned')
    suffixes=['labels.csv','options.csv','sources.csv','map.csv','manifest.json','target.json','log','receipt.json']
    paths={suffix:Path(str(prefix)+'.'+suffix) for suffix in suffixes}
    require(not any(os.path.lexists(path) for path in paths.values()),'refusing existing invocation outputs')
    require(not list(prefix.parent.glob(prefix.name+'.*')) if prefix.parent.exists() else True,'unknown prior prefix output')
    prefix.parent.mkdir(parents=True,exist_ok=True)
    receipt={'schema':'overnight_targeted_rest_invocation_v1','mode':a.stage.upper() if futures else 'ZERO_FUTURE_PREFLIGHT',
             'protocol':str(a.protocol.resolve()),'protocol_sha256':a.protocol_sha256,
             'source_sha':p['source_sha'],'binary_sha256':p['binary_sha256'],
             'teacher_sha256':p['teacher_sha256'],'target_sha256':sha(bound_target_path),'target_binding':binding,
             'command':cmd,'environment':env,'script_sha256':sha(__file__),
             'started_epoch':time.time(),'status':'running','positive_futures':futures}
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
