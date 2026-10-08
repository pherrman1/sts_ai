#!/usr/bin/env python3
"""Read only the fixed failed source; never interpret outcome or action-ranking fields."""
import csv
from collections import Counter
from datetime import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[5]
E=ROOT/'docs/experiments/evidence/ironclad_a0_k_precision_20261008'
PREFIX=ROOT/'build/overnight_20261008/learning/gen2-k-precision-3ed9/seed-610084217'
FREEZE_SHA='fc86c6e538618bf9212ffca58d422bda472954aa00f67a9216c3129c1a0df859'
VERIFIER_SHA='64db2d00154a34a8999cb5c9f78a4917d4f26f1e86ea185c41f02a737136e3db'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def require(ok,message):
    if not ok:raise ValueError(message)

def main():
    output=E/'audit/TIMEOUT_610084217_REVIEW.json'
    require(not output.exists(),'refusing overwrite')
    require(sha(E/'freeze.json')==FREEZE_SHA,'changed freeze')
    vp=E/'audit/verify_gen2_k32.py';require(sha(vp)==VERIFIER_SHA,'changed reviewed verifier')
    spec=importlib.util.spec_from_file_location('fixed_timeout_health',vp)
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    receipt_path=Path(str(PREFIX)+'.receipt.json');receipt=v.read_json(receipt_path)
    f=v.read_json(E/'freeze.json')
    require(receipt['status']=='timeout' and receipt['exit_code']==124 and receipt['source_seed']==610084217,'wrong failure source')
    require(receipt['freeze_sha256']==FREEZE_SHA,'receipt freeze mismatch')
    require(receipt['source_sha']==f['source_sha'] and receipt['binary_sha256']==f['binary_sha256'],'producer changed')
    require(receipt['script_sha256']==v.RUNNER_SHA,'runner changed')
    require(receipt['environment']==dict(f['environment'],STS_SILVER_TREE_PROFILE=str(PREFIX)+'.tree.jsonl'),'environment changed')
    expected=['bash','tools/seed_guard.sh',f['binary'],'ooccfpilotgen','1',str(PREFIX),'610084217',f['teacher'],'32','1','1','2','BOSS_RELIC']
    require(receipt['command']==expected,'command changed')
    inputs=[{'path':str(p),'sha256':sha(p)} for p in (E/'freeze.json',vp,Path(__file__),receipt_path)]
    for suffix,record in receipt['outputs'].items():
        p=Path(str(PREFIX)+'.'+suffix)
        require(str(p)==record['path'] and p.stat().st_size==record['bytes'] and sha(p)==record['sha256'],'partial output changed')
        inputs.append({'path':str(p),'sha256':record['sha256'],'bytes':record['bytes'],
                       'mtime_seconds_before_receipt_finish':receipt['finished_epoch']-p.stat().st_mtime})
    require(not Path(str(PREFIX)+'.manifest.json').exists(),'unexpected completed manifest')
    inventory={};rows_by_role={}
    # A CSV parser sees text, but only the explicit metadata/validity/CPU allowlist is retained.
    allowed={'sourceSeed','decisionIdx','type','optionIdx','k','futureSeed','valid','cpuSeconds','error'}
    for suffix in ('labels.csv','options.csv','sources.csv','map.csv'):
        raw=Path(str(PREFIX)+'.'+suffix).read_bytes()
        if not raw:
            inventory[suffix]={'bytes':0,'complete_field_rows':0,'newline_terminated':False};rows_by_role[suffix]=[];continue
        reader=csv.reader(io.StringIO(raw.decode(),newline=''));header=next(reader);rows=list(reader)
        complete=[];bad=[]
        for index,columns in enumerate(rows,2):
            if len(columns)!=len(header):bad.append({'line':index,'column_count':len(columns)});continue
            complete.append({key:columns[i] for i,key in enumerate(header) if key in allowed})
        rows_by_role[suffix]=complete
        inventory[suffix]={'bytes':len(raw),'header_columns':len(header),'data_records':len(rows),
                           'complete_field_rows':len(complete),'malformed_row_shapes':bad,
                           'newline_terminated':raw.endswith(b'\n'),
                           'tail_limit':'Without trailing newline, final field completeness is not certified even if column count matches.'}
    labels=rows_by_role['labels.csv'];require(len(labels)==100,'unexpected saved complete branch count')
    require(all(r['sourceSeed']=='610084217' and r['decisionIdx']=='35' and r['type']=='BOSS_RELIC' for r in labels),'unexpected partial source identity')
    label_keys=[(int(r['optionIdx']),int(r['k'])) for r in labels]
    require(label_keys==[(o,k) for o in range(3) for k in range(32)]+[(3,k) for k in range(4)],'partial progress order changed')
    cpu=sum(float(r['cpuSeconds']) for r in labels)
    byseed={610084217:'source'}
    for k in range(32):
        digest=hashlib.sha256(f'ooc-cf-pilot-v2-future:610084217:35:{k}'.encode()).hexdigest()
        byseed[v.mt19937_64_first(int(digest[:16],16))]=k
    summary=v.empty_health();errors=[];groups=[];seen=set();source_rows=0;last=None
    for lineno,line in enumerate(Path(str(PREFIX)+'.tree.jsonl').open(),1):
        try:
            row=v.HEALTH.parse(line);counts=v.verify_profile_root(row,set(byseed))
            identity=(row['seed'],v.HEALTH.natural(row['combat_id']),v.HEALTH.natural(row['decision']))
            require(identity not in seen,'duplicate real decision');seen.add(identity)
        except (KeyError,TypeError,ValueError) as exc:
            errors.append({'line':lineno,'error':str(exc)});continue
        k=byseed[int(row['seed'])];source_rows+=int(k=='source')
        if not groups or groups[-1]!=k:groups.append(k)
        summary['roots']+=1
        for key in ('completed_simulations','cycle_rollouts'):summary[key]+=row[key]
        summary['singleton_skips']+=int(row['singleton_skip'])
        for key in ('engine_stop','turn_limit'):summary[key]+=counts[key]
        last={key:row[key] for key in ('seed','combat_id','decision','act','floor','encounter','turn','configured_simulations','completed_simulations')}
    summary['fatal_findings']=len(errors)
    require(groups==['source']+list(range(32))*3+list(range(6)),'unexpected sampled-future progress sequence')
    result={'schema':'fixed_source_timeout_audit_v1','status':'EXECUTION_BLOCKED_DIAGNOSIS_COMPLETE','audited_epoch':time.time(),
            'scope':'Only source610084217 provenance, metadata, validity, CPU and health; no outcome counts or ranking/evaluation interpretation.',
            'source_seed':610084217,'freeze_sha256':FREEZE_SHA,'inputs':inputs,'source_sha':f['source_sha'],'binary_sha256':f['binary_sha256'],
            'invocation':{key:receipt[key] for key in ('status','exit_code','started_epoch','finished_epoch','wall_seconds')},
            'local_times':{key:datetime.fromtimestamp(receipt[key],ZoneInfo('Europe/Berlin')).isoformat() for key in ('started_epoch','finished_epoch')},
            'partial_csv_inventory':inventory,'manifest_present':False,
            'persisted_complete_branch_records':len(labels),'validity_flags':dict(Counter(r['valid'] for r in labels)),
            'branch_error_strings':dict(Counter(r['error'] for r in labels)),
            'complete_branch_counts_by_option_index':dict(sorted(Counter(r['optionIdx'] for r in labels).items())),
            'persisted_branch_cpu_seconds':cpu,'persisted_branch_cpu_fraction_of_invocation_wall':cpu/receipt['wall_seconds'],
            'unaccounted_wall_minus_persisted_branch_cpu_seconds':receipt['wall_seconds']-cpu,
            'selected_state_metadata':{'decision_idx':35,'type':'BOSS_RELIC','act':1,'floor':17},
            'progress':{'minimum_retained_options':4,'minimum_allocated_branches':128,'maximum_allowed_branches':192,
                        'last_complete_branch':{'option_idx':3,'k':3},'last_profile_future_k':groups[-1],
                        'profile_group_sequence':groups,'inferred_active_branch':'optionIdx3, k5, conditional on fixed ordered producer loops; profile has no branch-ID field'},
            'health':summary,'profile_failures':errors,'original_source_roots':source_rows,'last_profile_metadata':last,
            'classification':'Observed CPU-heavy continuation cost tail; no recorded engine fault or prolonged stall evidenced. Interrupted/unflushed work is not certified.',
            'limits':['The source trajectory-valid row and source CPU were buffered and unavailable; empty sources.csv cannot establish source validity.',
                      'CSV buffers flush at source completion; partial/missing rows and manifest are expected effects of process timeout, not evidence by themselves of simulator corruption.',
                      'Only100 complete persisted branch records have interpretable CPU/validity metadata; additional completed branches may be buffered.',
                      'The52.64-second residual includes source work, unflushed completed/current branch work and wall/CPU differences; no total process CPU receipt exists.',
                      'Tree profiles flush per root, but the currently executing root/branch at kill is unrecorded. File mtime is filesystem evidence, not a per-root timing series.',
                      'Engine-stop and cycle counts are search diagnostics and do not prove a fatal actual-game fault.',
                      'No complete-cohort inference, retries, replacements, cap changes or partial efficacy analysis are authorized by this audit.'],
            'evaluation_outcomes_reported':False,'games_run_by_auditor':0,'raw_files_mutated':False}
    with output.open('x') as out:json.dump(result,out,indent=2,allow_nan=False);out.write('\n')
    print(json.dumps({'output':str(output),'sha256':sha(output),'status':result['status'],'profile_roots':summary['roots'],'fatal_findings':len(errors)}))

if __name__=='__main__':main()
