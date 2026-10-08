#!/usr/bin/env python3
"""Run one coordinator-authorized, frozen GEN2 source; no scheduling or retries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--freeze',required=True,type=Path)
    p.add_argument('--seed',required=True,type=int)
    p.add_argument('--prefix',required=True,type=Path)
    a=p.parse_args(); f=json.loads(a.freeze.read_text())
    if a.seed not in f['source_seeds']: raise ValueError('unreserved source')
    root=Path(f['root']); binary=Path(f['binary']); teacher=Path(f['teacher'])
    if sha(binary)!=f['binary_sha256'] or sha(teacher)!=f['teacher_sha256']:
        raise ValueError('frozen producer or teacher changed')
    for path,h in f['artifacts'].items():
        if sha(root/path)!=h: raise ValueError('frozen artifact changed: '+path)
    prefix=a.prefix.resolve(); prefix.parent.mkdir(parents=True,exist_ok=True)
    suffixes=['labels.csv','options.csv','sources.csv','map.csv','manifest.json','log','tree.jsonl','receipt.json']
    paths={s:Path(str(prefix)+'.'+s) for s in suffixes}
    if any(os.path.lexists(v) for v in paths.values()): raise ValueError('refusing prior outputs')
    env=dict(json.loads(teacher.read_text())['environment'])
    env['STS_SILVER_TREE_PROFILE']=str(paths['tree.jsonl'])
    cmd=['bash','tools/seed_guard.sh',str(binary),'ooccfpilotgen','1',str(prefix),str(a.seed),str(teacher),
         str(f['futures']),str(f['states_per_seed']),'1','2',','.join(f['types'])]
    receipt={'schema':'overnight_gen2_invocation_v1','freeze':str(a.freeze.resolve()),
             'freeze_sha256':sha(a.freeze),'source_seed':a.seed,'command':cmd,'environment':env,
             'source_sha':f['source_sha'],'binary_sha256':f['binary_sha256'],
             'script_sha256':sha(__file__),'started_epoch':time.time(),'status':'running'}
    with paths['receipt.json'].open('x') as out: json.dump(receipt,out,indent=2)
    started=time.monotonic()
    with paths['log'].open('x') as log:
        try:
            result=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,
                                  timeout=f['timeout_seconds_per_source'])
            receipt.update(exit_code=result.returncode,status='completed' if result.returncode==0 else 'failed')
        except subprocess.TimeoutExpired:
            receipt.update(exit_code=124,status='timeout')
    receipt.update(wall_seconds=time.monotonic()-started,finished_epoch=time.time())
    receipt['outputs']={s:{'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}
                        for s,path in paths.items() if s!='receipt.json' and path.exists()}
    paths['receipt.json'].write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ('source_seed','status','exit_code','wall_seconds')}))
    return receipt['exit_code']

if __name__=='__main__': raise SystemExit(main())
