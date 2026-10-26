#!/usr/bin/env python3
"""Bounded replay/capture using the byte-identical retained #844 executable."""
import argparse
import gzip
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time
from stage_a import HERE, REPO, PIN, SOURCE, git, sha, dump, check

BASE = 'docs/experiments/evidence/combat_infinity_reconstruction_20261024/'
OLD = json.loads(git(SOURCE+'capture/11111.receipt.json'))
BUILD = json.loads(git(SOURCE+'build-result.json'))
RUNTIME = Path(BUILD['binary_path'])
SNAPSHOT = RUNTIME.parents[2]
MANIFEST = Path(OLD['environment']['STS_INFINITY_SKIP_MANIFEST'])
RUNS = REPO/'build/natural-infinity-20261026'


def complete(path):
    if not path.exists():
        return []
    raw=path.read_bytes()
    return [json.loads(v) for v in raw[:raw.rfind(b'\n')+1].splitlines()]


def custody():
    assert sha(RUNTIME.read_bytes()) == BUILD['binary_sha256'] == OLD['binary_sha256']
    assert MANIFEST.read_bytes() == git(SOURCE+'manifests/11111.json')
    plan = json.loads(git(BASE+'source-build-plan.json'))
    changed = {p for p,h in plan['tracked_files_sha256'].items() if sha((SNAPSHOT/p).read_bytes()) != h}
    assert changed == {'apps/one_combat/run_driver.cpp'}, changed
    for p,h in BUILD['patched_file_hashes'].items():
        assert sha((SNAPSHOT/p).read_bytes()) == h
    for m in OLD['models']:
        assert sha(Path(m['path']).read_bytes()) == m['expected_sha256']
    return dict(binary_sha256=sha(RUNTIME.read_bytes()), historical_source_sha=BUILD['historical_source_sha'],
                build_record_sha256=sha(git(SOURCE+'build-result.json')),
                source_plan_sha256=sha(git(BASE+'source-build-plan.json')),
                source_checked_files=len(plan['tracked_files_sha256']), patched_file_hashes=BUILD['patched_file_hashes'],
                manifest_sha256=sha(MANIFEST.read_bytes()), models=OLD['models'])


def run(phase):
    check()
    assert json.loads((HERE/'RESULT.json').read_text())['label'] == 'TARGET_COMBAT_EXHAUSTED_NO_SIGNAL'
    if phase == 'discover12':
        target_floor, target_fight, stop_at_entry = 18, 12, True
    elif phase == 'capture12':
        prior = json.loads((HERE/'discover12.receipt.json').read_text())
        assert prior['status'] == 'NEXT_COMBAT_ENTRY'
        target_floor, target_fight, stop_at_entry = prior['entry']['pre']['floor'], 12, False
    else:
        assert json.loads((HERE/'combat12/RESULT.json').read_text())['label'] in ('TARGET_COMBAT_EXHAUSTED_NO_SIGNAL', 'TARGET_COMBAT_INCONCLUSIVE')
        prior = json.loads((HERE/'capture12.receipt.json').read_text())
        assert prior['status'] == 'NEXT_COMBAT_ENTRY' and prior['entry']['fight'] == 13
        target_floor, target_fight, stop_at_entry = prior['entry']['pre']['floor'], 13, False
    record=custody()
    RUNS.mkdir(parents=True,exist_ok=True)
    folder=RUNS/phase
    folder.mkdir()  # no overwrite/retry
    bundle=Path(OLD['models'][0]['path']).parent
    for name in ('models','selfplay','studentc.bin'):
        (folder/name).symlink_to(bundle/name, target_is_directory=name!='studentc.bin')
    env={k:v for k,v in os.environ.items() if not k.startswith(('STS_','OMP_'))}
    env.update(OLD['environment'])
    outputs={'STS_OOC_DECISION_TRACE':'trace.jsonl','STS_OOC_MCTS_ROOT_TRACE':'roots.jsonl',
             'STS_OOC_MCTS_TRACE':'mcts.csv','STS_OOC_SIBLING_CAPTURE':'sib.jsonl','STS_SILVER_PUBLIC_TRACE':'public.jsonl'}
    for k,v in outputs.items():
        env[k]=str(folder/v)
    env['STS_SILVER_PUBLIC_TARGET']=f'111101032:{target_floor}'
    env['STS_INFINITY_SKIP_MANIFEST']=str(MANIFEST)
    command=['bash',str(REPO/'tools/seed_guard.sh'),str(RUNTIME),'heartoutcomegen','1','111101032',str(folder/'states.jsonl'),'on']
    record.update(phase=phase, command=command, cwd=str(folder), target_floor=target_floor, target_fight=target_fight,
                  stop_at_entry=stop_at_entry, environment={k:v for k,v in env.items() if k.startswith(('STS_','OMP_'))},
                  wall_limit_seconds=900, one_local_lane=True, no_retries=True,
                  stage_a_result_sha256=sha((HERE/'RESULT.json').read_bytes()),
                  wrapper_sha256=sha(Path(__file__).read_bytes()),
                  started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    (HERE/(phase+'.launch.json')).write_text(dump(record))
    expected_trace=[json.loads(v) for v in gzip.decompress(git(SOURCE+'capture/11111.trace.jsonl.gz')).splitlines()]
    expected_states=[json.loads(v) for v in gzip.decompress(git(SOURCE+'capture/11111.states.jsonl.gz')).splitlines()]
    if phase != 'discover12':
        previous='discover12' if phase=='capture12' else 'capture12'
        previous_receipt=json.loads((HERE/(previous+'.receipt.json')).read_text())
        for name in ('trace.jsonl','states.jsonl'):
            data=gzip.decompress((HERE/(previous+'.'+name+'.gz')).read_bytes())
            assert sha(data)==previous_receipt['files'][name]['sha256']
            complete_data=data[:data.rfind(b'\n')+1]
            if name=='trace.jsonl':
                expected_trace=[json.loads(v) for v in complete_data.splitlines()]
            else:
                expected_states=[json.loads(v) for v in complete_data.splitlines()]
    status='RUNNING'; entry=None; prefix_checked=False; latest=None
    start=time.monotonic(); before=resource.getrusage(resource.RUSAGE_CHILDREN)
    with (folder/'stdout.log').open('xb') as out,(folder/'stderr.log').open('xb') as err:
        proc=subprocess.Popen(command,cwd=folder,env=env,stdout=out,stderr=err,start_new_session=True)
        try:
            while True:
                if time.monotonic()-start>900:
                    status='WALL_LIMIT'; break
                trace=complete(folder/'trace.jsonl')
                # Compare every retained prefix record, not only selected states.
                if trace[:min(len(trace),len(expected_trace))] != expected_trace[:min(len(trace),len(expected_trace))]:
                    status='REPLAY_TRACE_DIVERGENCE'; break
                states=complete(folder/'states.jsonl')
                if states[:min(len(states),len(expected_states))] != expected_states[:min(len(states),len(expected_states))]:
                    status='REPLAY_STATE_DIVERGENCE'; break
                prefix_checked=len(trace)>=len(expected_trace) and len(states)>=len(expected_states)
                boundaries=[r for r in trace if r.get('kind')=='infinity_mask_boundary']
                if boundaries:
                    latest=boundaries[-1]
                    if any(not r['integrity_so_far'] for r in boundaries):
                        status='SIMULATOR_HEALTH_FAILURE'; break
                    if latest['pre']['floor']>=18:
                        if latest['pre']['hp']<=0:
                            status='DEATH'; break
                        if latest['pre']['act']>2:
                            status='END_OF_ACT_2'; break
                        if sum(c.rstrip('+')=='Dropkick' for c in latest['pre']['deck'])<2:
                            status='DROPKICK_LOSS'; break
                entry=next((r for r in boundaries if r['pre']['screen']=='BATTLE' and r['fight']>=target_fight+(not stop_at_entry)),None)
                if entry:
                    status='NEXT_COMBAT_ENTRY'; break
                battle=next((r for r in trace if r.get('kind')=='battle' and r['fight']==target_fight),None)
                if not stop_at_entry and battle:
                    if battle['post']['hp']<=0:
                        if proc.poll() is None:
                            time.sleep(.02); continue
                        status='DEATH'; break
                    if target_fight==13:
                        # Complete third combat, then stop before further OOC work.
                        status='THREE_COMBAT_HORIZON'; break
                if proc.poll() is not None:
                    status='NATURAL_PROCESS_EXIT'; break
                progress=folder/'progress.tmp'
                progress.write_text(dump(dict(phase=phase, wall_seconds=time.monotonic()-start,
                    latest_boundary=latest, prefix_checked=prefix_checked)))
                progress.replace(folder/'progress.json')
                time.sleep(.1)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL); proc.wait()
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    record.update(status=status, entry=entry, latest_boundary=latest, prefix_checked=prefix_checked,
                  returncode=proc.returncode, wall_seconds=time.monotonic()-start,
                  child_user_seconds=after.ru_utime-before.ru_utime, child_system_seconds=after.ru_stime-before.ru_stime,
                  raw_folder=str(folder), files={})
    for name in ('public.jsonl','trace.jsonl','states.jsonl','stdout.log','stderr.log'):
        path=folder/name
        if path.exists():
            raw=path.read_bytes(); packed=gzip.compress(raw,mtime=0)
            record['files'][name]=dict(sha256=sha(raw), compressed_sha256=sha(packed))
            (HERE/(phase+'.'+name+'.gz')).write_bytes(packed)
    (HERE/(phase+'.receipt.json')).write_text(dump(record))
    print(dump(dict(phase=phase,status=status,prefix_checked=prefix_checked,entry=entry,wall_seconds=record['wall_seconds'])),flush=True)
    assert prefix_checked and status in ('NEXT_COMBAT_ENTRY','THREE_COMBAT_HORIZON','DEATH','END_OF_ACT_2','DROPKICK_LOSS'), status


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['discover12','capture12','capture13']);a=p.parse_args();run(a.phase)
