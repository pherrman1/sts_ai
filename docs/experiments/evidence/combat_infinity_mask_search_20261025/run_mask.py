#!/usr/bin/env python3
"""One of the31 frozen masks, or the single selected capture replay. No oracle."""
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
from search_logic import locate_stop,assess,sha_value

SEED=111101032

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mask',type=int,choices=range(1,32));parser.add_argument('--reviewed-sha',required=True);parser.add_argument('--capture',action='store_true');args=parser.parse_args()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==args.reviewed_sha
    frozen=json.loads((HERE/'FREEZE.json').read_text());bits=f'{args.mask:05b}';manifest_path=HERE/'manifests'/f'{bits}.json'
    assert sha(manifest_path)==frozen['all_masks_sha256'][bits];manifest=json.loads(manifest_path.read_text())
    assert all(e['enabled']==bool(args.mask&(1<<i)) for i,e in enumerate(manifest['interventions']))
    build=json.loads((HERE/'build-result.json').read_text());parity=json.loads((HERE/'parity.json').read_text())
    assert parity['qualification_result']=='FLAG_OFF_PARITY_PASS' and parity['reviewed_sha']==args.reviewed_sha
    assert parity['binary_sha256']==build['binary_sha256']==sha(Path(build['binary_path']))
    assert all(sha(Path(m['path']))==m['expected_sha256'] for m in parity['models'])
    label=('capture-' if args.capture else 'mask-')+bits;run=RUNTIME/label;run.mkdir() # no retries/overwrites
    target=None;search_result=None;search_public_prefix=None
    if args.capture:
        selection=json.loads((HERE/'SELECTED_MASK.json').read_text());assert selection['gate_pass'] and selection['best_mask']==bits
        search_result=json.loads((HERE/'results'/f'{bits}.json').read_text())
        assert selection['best_result_sha256']==sha(HERE/'results'/f'{bits}.json')
        target=search_result['measurement']['target']
        selected_states=[json.loads(line) for line in gzip.decompress((HERE/'runs'/f'{bits}.states.jsonl.gz').read_bytes()).splitlines()]
        search_public_prefix=[r for r in selected_states if r.get('type')=='header' or (r.get('type')=='state' and r['index']<=target['boundary_index'])]
        assert [r['index'] for r in search_public_prefix if r.get('type')=='state']==list(range(target['boundary_index']+1))
    bundle=Path('/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-outcome-collection-20261016-v1/bundle')
    for name in ['models','selfplay','studentc.bin']:(run/name).symlink_to(bundle/name,target_is_directory=name!='studentc.bin')
    env={k:v for k,v in os.environ.items() if not k.startswith(('STS_','OMP_'))};env.update(parity['environment'])
    for key,name in [('STS_OOC_DECISION_TRACE','trace.jsonl'),('STS_OOC_MCTS_ROOT_TRACE','roots.jsonl'),('STS_OOC_MCTS_TRACE','mcts.csv'),('STS_OOC_SIBLING_CAPTURE','sib.jsonl')]:env[key]=str(run/name)
    env.pop('STS_SILVER_PUBLIC_TRACE',None);env.pop('STS_SILVER_PUBLIC_TARGET',None);env['STS_INFINITY_SKIP_MANIFEST']=str(manifest_path)
    if target:env['STS_SILVER_PUBLIC_TRACE']=str(run/'public.jsonl');env['STS_SILVER_PUBLIC_TARGET']=f"{SEED}:{target['floor']}"
    command=['bash',str(SOURCE/'tools/seed_guard.sh'),build['binary_path'],'heartoutcomegen','1',str(SEED),str(run/'states.jsonl'),'on']
    record={'mask':bits,'numeric_mask':args.mask,'capture_only':args.capture,'seed':SEED,'reviewed_sha':args.reviewed_sha,'binary_sha256':build['binary_sha256'],'manifest_sha256':sha(manifest_path),'frozen_manifest_sha256':frozen['manifest_sha256'],'command':command,'cwd':str(run),'environment':{k:v for k,v in env.items() if k.startswith(('STS_','OMP_'))},'models':parity['models'],'wall_limit_seconds':900,'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    write(run/'started.json',record);usage=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.monotonic();status='RUNNING';endpoint=None;first_difference=None;capture_battle=None;trace=[];canary_checked=False
    expected=json.loads(gzip.decompress((HERE.parent/'combat_infinity_reconstruction_20261024/expected-111101032.json.gz').read_bytes()))
    with (run/'stdout.log').open('wb') as out,(run/'stderr.log').open('wb') as err:
        process=subprocess.Popen(command,cwd=run,env=env,stdout=out,stderr=err,start_new_session=True);record['pid']=process.pid;write(run/'started.json',record)
        try:
            while True:
                if time.monotonic()-start>900:status='WALL_LIMIT';break
                trace=complete_rows(run/'trace.jsonl');endpoint=locate_stop(trace)
                prefix=trace[:endpoint['row']+1] if endpoint else trace
                boundaries=[r for r in prefix if r.get('kind')=='infinity_mask_boundary']
                if any(not r['integrity_so_far'] for r in boundaries):status='SIMULATOR_HEALTH_FAILURE';break
                normal=[r for r in trace if r.get('kind') in ['ooc','battle']]
                if args.mask==1 and not args.capture:
                    forced=next((i for i,r in enumerate(normal) if r.get('by')=='infinity_skip'),None)
                    n=forced if forced is not None else min(len(normal),len(expected['trace']))
                    first_difference=difference(expected['trace'][:n],normal[:n],'/canary_before_first_enabled_skip')
                    if first_difference:status='CANARY_PRE_INTERVENTION_DIVERGED';break
                    canary_checked=forced is not None or endpoint is not None
                if args.capture:
                    if endpoint and endpoint['kind']=='TARGET_REACHED':
                        measurement=assess(args.mask,manifest,trace,endpoint)
                        first_difference=difference(search_result['measurement'],measurement,'/capture_entry_measurement')
                        if first_difference:status='CAPTURE_ENTRY_DIVERGED';break
                        captured_states=complete_rows(run/'states.jsonl')
                        capture_public_prefix=[r for r in captured_states if r.get('type')=='header' or (r.get('type')=='state' and r['index']<=target['boundary_index'])]
                        first_difference=difference(search_public_prefix,capture_public_prefix,'/capture_public_state_prefix')
                        if first_difference:status='CAPTURE_PUBLIC_PREFIX_DIVERGED';break
                        for row in normal:
                            if row['kind']=='battle' and row['fight']==target['fight'] and row['pre']['act']==target['act'] and row['pre']['floor']==target['floor']:
                                capture_battle=row;break
                        if capture_battle:
                            if capture_battle['post']['hp']>0:
                                following=next((r for r in trace if r.get('kind')=='infinity_mask_boundary' and r['index']>target['boundary_index']),None)
                                if following is None and process.poll() is None:time.sleep(0.1);continue
                                if following is None or not following['integrity_so_far']:status='CAPTURE_HEALTH_FAILURE';break
                            else:
                                if process.poll() is None:time.sleep(0.1);continue
                                footer=[r for r in complete_rows(run/'states.jsonl') if r.get('type')=='outcome']
                                if process.returncode!=0 or len(footer)!=1 or not footer[0]['integrityPassed']:status='CAPTURE_HEALTH_FAILURE';break
                            status='CAPTURED';break
                    elif endpoint:status='CAPTURE_NO_TARGET';break
                elif endpoint:
                    if endpoint['kind']=='DEAD':
                        # Let natural terminal integrity/footer and native summary flush.
                        if process.poll() is None:time.sleep(0.1);continue
                        status='VALID' if process.returncode==0 else 'PROCESS_FAILED';break
                    status='VALID';break
                if process.poll() is not None:status='PROCESS_ENDED_BEFORE_STOP';break
                write(run/'progress.json',{'mask':bits,'wall_seconds':time.monotonic()-start,'boundary_count':len(boundaries),'floor':boundaries[-1]['pre']['floor'] if boundaries else None,'pid':process.pid})
                time.sleep(0.1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    trace=complete_rows(run/'trace.jsonl');states=complete_rows(run/'states.jsonl');end_usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    if states and difference(expected['header'],states[0],'/header') is not None:status='HEADER_MISMATCH'
    measurement=None;validation_error=None
    if status in ['VALID','CAPTURED']:
        try:
            assert endpoint is not None
            measurement=assess(args.mask,manifest,trace,endpoint)
            if endpoint['kind']=='DEAD':
                outcomes=[r for r in states if r.get('type')=='outcome'];assert len(outcomes)==1 and outcomes[0]['complete'] and outcomes[0]['integrityPassed']
            if args.mask==1 and not args.capture:assert canary_checked
        except Exception as error:
            status='VALIDATION_FAILED';validation_error=repr(error);measurement=None
    record.update({'status':status,'validation_error':validation_error,'returncode':process.returncode,'first_difference':first_difference,'wall_seconds':time.monotonic()-start,'child_user_seconds':end_usage.ru_utime-usage.ru_utime,'child_system_seconds':end_usage.ru_stime-usage.ru_stime,'stop_endpoint':endpoint,'canary_prefix_pass':canary_checked if args.mask==1 and not args.capture else None,'intentional_prefix_stop':bool(endpoint and endpoint['kind']!='DEAD'),'capture_battle':capture_battle,'files':{p.name:sha(p) for p in run.iterdir() if p.is_file() and not p.is_symlink()},'finished_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
    folder=HERE/('capture' if args.capture else 'runs');folder.mkdir(exist_ok=True)
    for name in ['trace.jsonl','states.jsonl','stdout.log','stderr.log']+(['public.jsonl'] if args.capture else []):
        if (run/name).exists():(folder/f'{bits}.{name}.gz').write_bytes(gzip.compress((run/name).read_bytes(),mtime=0))
    write(run/'receipt.json',record);write(folder/f'{bits}.receipt.json',record)
    results=HERE/'results';results.mkdir(exist_ok=True)
    if not args.capture:write(results/f'{bits}.json',{'status':status,'receipt_sha256':sha(folder/f'{bits}.receipt.json'),'measurement':measurement})
    print(json.dumps({'mask':bits,'status':status,'stop':measurement['stop'] if measurement else None,'engine_complete':measurement['engine_complete'] if measurement else None,'target_deck':measurement['target_deck_size'] if measurement else None,'wall_seconds':record['wall_seconds']},indent=2))
    return 0 if status in ['VALID','CAPTURED'] else 1

if __name__=='__main__':raise SystemExit(main())
