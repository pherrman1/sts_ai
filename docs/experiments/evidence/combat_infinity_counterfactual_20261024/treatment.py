#!/usr/bin/env python3
"""One frozen treatment; optional one identity-checked capture replay, no oracle."""
import argparse
import gzip
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time
from build_runtime import HERE, REPO, RUNTIME, SOURCE, sha, write
from qualify import complete_rows, difference

SEED=111101326
MANIFEST=HERE.parent/'combat_infinity_compression_20261024/INTERVENTIONS.json'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reviewed-sha',required=True)
    parser.add_argument('--capture',action='store_true')
    args=parser.parse_args()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==args.reviewed_sha
    build=json.loads((HERE/'build-result.json').read_text())
    parity=json.loads((HERE/'parity.json').read_text())
    assert parity['qualification_result']=='FLAG_OFF_PARITY_PASS' and parity['binary_sha256']==build['binary_sha256']
    assert parity['reviewed_sha']==args.reviewed_sha
    assert sha(Path(build['binary_path']))==build['binary_sha256']
    assert sha(MANIFEST)==build['manifest_sha256']
    assert all(sha(Path(m['path']))==m['expected_sha256'] for m in parity['models'])
    label='capture' if args.capture else 'treatment'
    target=None
    if args.capture:
        previous=json.loads((HERE/'treatment.json').read_text())
        assert previous['status']=='COMPLETED'
        freeze=json.loads((HERE/'target.json').read_text())
        assert freeze['treatment_receipt_sha256']==sha(HERE/'treatment.json')
        target=freeze['target']
    run=RUNTIME/label;run.mkdir() # Irreversible one-attempt latch, never overwrite/retry.
    bundle=Path('/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-outcome-collection-20261016-v1/bundle')
    for name in ['models','selfplay','studentc.bin']:
        (run/name).symlink_to(bundle/name,target_is_directory=name!='studentc.bin')
    env={k:v for k,v in os.environ.items() if not k.startswith(('STS_','OMP_'))}
    env.update(parity['environment'])
    for key,suffix in [('STS_OOC_DECISION_TRACE','trace.jsonl'),('STS_OOC_MCTS_ROOT_TRACE','roots.jsonl'),('STS_OOC_MCTS_TRACE','mcts.csv'),('STS_OOC_SIBLING_CAPTURE','sib.jsonl')]:
        env[key]=str(run/suffix)
    env.pop('STS_SILVER_PUBLIC_TRACE',None);env.pop('STS_SILVER_PUBLIC_TARGET',None)
    env['STS_INFINITY_SKIP_MANIFEST']=str(MANIFEST)
    if target:
        env['STS_SILVER_PUBLIC_TRACE']=str(run/'public.jsonl')
        env['STS_SILVER_PUBLIC_TARGET']=f"{SEED}:{target['floor']}"
    command=['bash',str(SOURCE/'tools/seed_guard.sh'),build['binary_path'],'heartoutcomegen','1',str(SEED),str(run/'states.jsonl'),'on']
    record={'seed':SEED,'label':label,'reviewed_sha':args.reviewed_sha,'binary_sha256':build['binary_sha256'],'patch_sha256':build['patch_sha256'],'manifest_sha256':sha(MANIFEST),'runtime_identity':'FLAG_OFF_QUALIFIED_RESEARCH_PATCHED_NOT_HISTORICAL','command':command,'cwd':str(run),'environment':{k:v for k,v in env.items() if k.startswith(('STS_','OMP_'))},'models':parity['models'],'wall_limit_seconds':1800,'target':target,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    write(run/'started.json',record)
    start=time.monotonic();usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    status='RUNNING';mismatch=None
    with (run/'stdout.log').open('wb') as out,(run/'stderr.log').open('wb') as err:
        process=subprocess.Popen(command,cwd=run,env=env,stdout=out,stderr=err,start_new_session=True)
        record['pid']=process.pid;write(run/'started.json',record)
        try:
            while process.poll() is None:
                if time.monotonic()-start>1800:status='WALL_LIMIT';break
                time.sleep(0.5)
            else:status='COMPLETED' if process.returncode==0 else 'PROCESS_FAILED'
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    states=complete_rows(run/'states.jsonl');trace=complete_rows(run/'trace.jsonl')
    summaries=[r for r in trace if r.get('kind')=='infinity_skip_summary']
    outcomes=[r for r in states if r.get('type')=='outcome']
    if status=='COMPLETED':
        assert len(summaries)==1 and len(outcomes)==1 and outcomes[0]['complete'] and outcomes[0]['integrityPassed']
        summary=summaries[0]
        assert summary['normal_end'] and summary['manifest_entries']==13 and summary['matched']+summary['not_seen']==13 and summary['failed']==0
        assert summary['matched']==sum(r.get('by')=='infinity_skip' for r in trace)
        assert [{k:v for k,v in e.items() if k not in ['status','error']} for e in summary['entries']]==json.loads(MANIFEST.read_text())['interventions']
        if args.capture:
            for name in ['states.jsonl','trace.jsonl']:
                expected=complete_rows(RUNTIME/'treatment'/name);actual=complete_rows(run/name)
                mismatch=difference(expected,actual,'/'+name)
                if mismatch:status='CAPTURE_REPLAY_DIVERGED';break
    end=resource.getrusage(resource.RUSAGE_CHILDREN)
    record.update({'status':status,'returncode':process.returncode,'first_difference':mismatch,'wall_seconds':time.monotonic()-start,'child_user_seconds':end.ru_utime-usage.ru_utime,'child_system_seconds':end.ru_stime-usage.ru_stime,'summary':summaries,'outcomes':outcomes,'files':{p.name:sha(p) for p in run.iterdir() if p.is_file() and not p.is_symlink()},'finished_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
    write(run/'receipt.json',record);write(HERE/f'{label}.json',record)
    for name in ['states.jsonl','trace.jsonl','stdout.log','stderr.log']+(['public.jsonl'] if args.capture else []):
        if (run/name).exists():(HERE/f'{label}.{name}.gz').write_bytes(gzip.compress((run/name).read_bytes(),mtime=0))
    print(json.dumps({k:record[k] for k in ['status','outcomes','wall_seconds','summary']},indent=2))
    return 0 if status=='COMPLETED' else 1

if __name__=='__main__':raise SystemExit(main())
