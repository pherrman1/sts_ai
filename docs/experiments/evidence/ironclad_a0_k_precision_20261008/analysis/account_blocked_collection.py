#!/usr/bin/env python3
"""Metadata/cost accounting after dispatch closes; never interprets efficacy."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
E=HERE.parent
SEEDS=list(range(610084200,610084232))
FREEZE_SHA='fc86c6e538618bf9212ffca58d422bda472954aa00f67a9216c3129c1a0df859'
ROLES=('receipt.json','sources.csv','options.csv','labels.csv','map.csv','manifest.json','log','tree.jsonl')
FIELDS={
    'sources.csv':('sourceSeed','decisionIdx','type','trajectoryValid','options','sourceCpuSeconds'),
    'options.csv':('sourceSeed','decisionIdx','type','optionIdx'),
    'labels.csv':('sourceSeed','decisionIdx','type','optionIdx','k','valid','error','cpuSeconds'),
    'map.csv':('sourceSeed','decisionIdx','type','optionIdx','k'),
}
LIMITS=[
    'EXECUTION_BLOCKED is preserved. This accounting is not a clean contract, selection, evaluation or primary efficacy result.',
    'The remaining completed sources do not replace the fixed32 allocation; a timeout is not a valid no-state source and never receives zero primary gain.',
    'CSV tokenization locates metadata columns only. finalWon and other efficacy fields are never interpreted, summarized, ranked or retained.',
    'Reported valid no-state markers are metadata counts only; this helper does not establish the full canonical no-state contract or a primary zero-gain substitution.',
    'Observed source/branch CPU is summed only from finite nonnegative sourceCpuSeconds/cpuSeconds. Missing, invalid and unfinished records are not assigned zero cost; totals can undercount work before termination.',
    'Process-wall sums are resource occupancy, not elapsed time. Receipt-span and dispatch elapsed time are separately reported.',
    'Raw partial outputs remain preserved. Any later use needs a separately authorized protocol that discloses this failed fixed allocation; no retries, replacement sources, retrospective cap changes or efficacy reanalysis are authorized here.'
]


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):digest.update(chunk)
    return digest.hexdigest()


def bind(path,digest=None):
    path=Path(path).resolve();actual=sha(path)
    if digest is not None:require(actual==digest,'changed metadata input: '+str(path))
    return {'path':str(path),'sha256':actual,'bytes':path.stat().st_size}


def load_bound(path,digest):
    record=bind(path,digest)
    return json.loads(Path(path).read_text()),record


def project_csv(path,fields):
    """Return metadata only. Unknown columns, including outcomes, are never indexed."""
    rows=[];issues=[];parsed_to_eof=False;last_record_accepted=False
    with Path(path).open('rb') as raw:
        raw.seek(0,2)
        if raw.tell():raw.seek(-1,2);terminated=raw.read(1)==b'\n'
        else:terminated=False
    try:
        with Path(path).open(newline='') as f:
            reader=csv.reader(f,strict=True)
            header=next(reader,None)
            if header is None:return [],['empty CSV; metadata unavailable']
            require(len(header)==len(set(header)),'duplicate CSV header')
            require(all(field in header for field in fields),'missing metadata column')
            indices={field:header.index(field) for field in fields}
            for line,row in enumerate(reader,2):
                last_record_accepted=False
                if len(row)!=len(header):
                    issues.append(f'incomplete CSV record at logical row {line}')
                    continue
                rows.append({field:row[index] for field,index in indices.items()})
                last_record_accepted=True
            parsed_to_eof=True
    except (csv.Error,ValueError,UnicodeError) as error:
        issues.append(type(error).__name__+': '+str(error))
    if not terminated:
        # A full-width final token such as "2." can parse but still be a
        # truncated write. Only earlier newline-terminated records count.
        if parsed_to_eof and last_record_accepted:rows.pop()
        issues.append('unterminated final logical CSV record excluded; partial cost unavailable')
    return rows,issues


def number(value):
    try:
        value=float(value)
        return value if math.isfinite(value) and value>=0 else None
    except (TypeError,ValueError):return None


def cpu_summary(rows,field,deduplicate_source=False):
    seen={};values=[];invalid=0
    for row in rows:
        value=number(row[field])
        if value is None:invalid+=1;continue
        if deduplicate_source:
            seed=row['sourceSeed']
            if seed in seen:
                if seen[seed]!=value:invalid+=1
                continue
            seen[seed]=value
        values.append(value)
    return {'observed_seconds':sum(values) if values else None,'valid_cost_records':len(values),
            'invalid_cost_records':invalid,'complete_cost_claim':False}


def summarize_tables(tables,seed,futures=32):
    issues=[]
    for role,rows in tables.items():
        if any(row['sourceSeed']!=str(seed) for row in rows):issues.append(role+': unexpected source seed')
    src=tables['sources.csv'];opts=tables['options.csv'];labels=tables['labels.csv'];maps=tables['map.csv']
    states=set();no_state=0;invalid_source=0
    for row in src:
        try:
            decision=int(row['decisionIdx'])
            if decision>=0:states.add((row['sourceSeed'],row['decisionIdx'],row['type']))
            elif decision==-1 and row['type']=='' and row['options']=='0' and row['trajectoryValid']=='1':no_state+=1
            else:issues.append('noncanonical no-state metadata')
        except ValueError:issues.append('invalid source decision index')
        invalid_source+=row['trajectoryValid']!='1'
    keys=lambda rows:[tuple(row[k] for k in ('sourceSeed','decisionIdx','type','optionIdx','k')) for row in rows]
    labelkeys=keys(labels);mapkeys=keys(maps)
    expected={(r['sourceSeed'],r['decisionIdx'],r['type'],r['optionIdx'],str(k)) for r in opts for k in range(futures)}
    source_cpu=cpu_summary(src,'sourceCpuSeconds',True);branch_cpu=cpu_summary(labels,'cpuSeconds')
    return {'source_rows':len(src),'retained_states':len(states),'reported_valid_no_state_marker_rows':no_state,
            'invalid_source_rows':invalid_source,'retained_option_rows':len(opts),'expected_branches_from_option_rows':len(expected),
            'observed_branch_rows':len(labels),'observed_map_rows':len(maps),
            'invalid_or_error_branch_rows':sum(r['valid']!='1' or bool(r['error']) for r in labels),
            'duplicate_branch_identity_rows':len(labelkeys)-len(set(labelkeys)),
            'duplicate_map_identity_rows':len(mapkeys)-len(set(mapkeys)),
            'missing_branch_identities':len(expected-set(labelkeys)),'extra_branch_identities':len(set(labelkeys)-expected),
            'missing_map_identities':len(expected-set(mapkeys)),'extra_map_identities':len(set(mapkeys)-expected),
            'source_cpu':source_cpu,'branch_cpu':branch_cpu,'metadata_issues':issues}


def source_inventory(raw,seed,freeze_sha):
    prefix=raw/f'seed-{seed}';files=[];missing=[];receipt=None;issues=[];tables={}
    for role in ROLES:
        path=Path(str(prefix)+'.'+role)
        if not path.exists():missing.append(role);continue
        if path.is_symlink() or not path.is_file():issues.append(role+': not an ordinary file');continue
        files.append({'role':role}|bind(path))
        if role=='receipt.json':
            try:receipt=json.loads(path.read_text())
            except (ValueError,UnicodeError) as error:issues.append('unreadable receipt: '+str(error))
        elif role in FIELDS:
            tables[role],errors=project_csv(path,FIELDS[role]);issues.extend(role+': '+error for error in errors)
    for role in FIELDS:tables.setdefault(role,[])
    hashes={x['role']:x for x in files}
    if receipt is None:
        status='missing' if 'receipt.json' in missing else 'unreadable';exit_code=None;timing={}
    else:
        status=receipt.get('status','unknown');exit_code=receipt.get('exit_code')
        if receipt.get('source_seed')!=seed or receipt.get('freeze_sha256')!=freeze_sha:issues.append('receipt source/freeze binding mismatch')
        timing={k:number(receipt.get(k)) for k in ('started_epoch','finished_epoch','wall_seconds')}
        if status=='completed' and exit_code!=0:issues.append('completed receipt has nonzero/missing exit')
        for role,record in receipt.get('outputs',{}).items():
            actual=hashes.get(role)
            if actual is None or record.get('path')!=actual['path'] or record.get('sha256')!=actual['sha256'] or record.get('bytes')!=actual['bytes']:
                issues.append('receipt output custody mismatch: '+role)
        if set(receipt.get('outputs',{}))!=set(hashes)-{'receipt.json'}:issues.append('receipt output list differs from files present')
    metadata=summarize_tables(tables,seed)
    return {'source_seed':seed,'status':status,'exit_code':exit_code,'timing':timing,'files':files,
            'missing_outputs':missing,'accounting_issues':issues,'metadata':metadata,
            'completed_game_invocation':status=='completed' and exit_code==0}


def aggregate(records,dispatch):
    require([r['source_seed'] for r in records]==SEEDS,'exact fixed32 accounting order required')
    timings=[r['timing'] for r in records]
    starts=[t['started_epoch'] for t in timings if t.get('started_epoch') is not None]
    finishes=[t['finished_epoch'] for t in timings if t.get('finished_epoch') is not None]
    walls=[t['wall_seconds'] for t in timings if t.get('wall_seconds') is not None]
    source_costs=[r['metadata']['source_cpu']['observed_seconds'] for r in records]
    branch_costs=[r['metadata']['branch_cpu']['observed_seconds'] for r in records]
    dstart=number(dispatch.get('started_epoch'));dfinish=number(dispatch.get('finished_epoch'))
    return {'allocated_sources':32,'receipt_status_counts':dict(Counter(r['status'] for r in records)),
            'completed_game_invocations':sum(r['completed_game_invocation'] for r in records),
            'incomplete_or_failed_source_seeds':[r['source_seed'] for r in records if not r['completed_game_invocation']],
            'sources_with_missing_outputs':[r['source_seed'] for r in records if r['missing_outputs']],
            'observed_retained_states':sum(r['metadata']['retained_states'] for r in records),
            'observed_branch_rows':sum(r['metadata']['observed_branch_rows'] for r in records),
            'expected_branches_from_available_options':sum(r['metadata']['expected_branches_from_option_rows'] for r in records),
            'source_cpu_observed_seconds':sum(x for x in source_costs if x is not None),
            'source_cpu_unavailable_sources':sum(x is None for x in source_costs),
            'branch_cpu_observed_seconds':sum(x for x in branch_costs if x is not None),
            'branch_cpu_unavailable_sources':sum(x is None for x in branch_costs),
            'invocation_wall_seconds_sum':sum(walls),'invocations_with_wall_seconds':len(walls),
            'receipt_span_elapsed_seconds':max(finishes)-min(starts) if starts and finishes else None,
            'dispatcher_elapsed_seconds':dfinish-dstart if dstart is not None and dfinish is not None else None,
            'dispatcher_exit_code':dispatch.get('exit_code'),'cpu_scope':'observed emitted cost fields only; incomplete work may be absent'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('dispatcher-completion','process-closeout'):p.add_argument('--'+key,type=Path,required=True);p.add_argument('--'+key+'-sha',required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    require(not args.output.exists() and not args.output.is_symlink() and args.output.resolve().is_relative_to(HERE),'exclusive owned output required')
    dispatch,drecord=load_bound(args.dispatcher_completion,args.dispatcher_completion_sha)
    closeout,crecord=load_bound(args.process_closeout,args.process_closeout_sha)
    require(dispatch['schema']=='k_precision_dispatch_completion_v1' and dispatch['status'] in ('DISPATCH_COMMAND_COMPLETED','DISPATCH_FAILED_NO_RETRY'),'terminal dispatcher receipt required')
    require(closeout['dispatcher_completed'] is True and closeout['active_game_processes']==0 and closeout['dispatcher_completion_sha256']==drecord['sha256'],'finished dispatcher and no active game process required')
    freeze,frecord=load_bound(E/'freeze.json',FREEZE_SHA)
    require(freeze['source_seeds']==SEEDS and freeze['futures']==32,'fixed collection required')
    authorization_record=bind(E/'dispatch_authorization.json',dispatch['authorization_sha256'])
    dispatch_spec,_=load_bound(freeze['dispatch_spec'],freeze['dispatch_spec_sha256'])
    dispatch_log_record=bind(dispatch_spec['dispatch_log'],dispatch['log_sha256'])
    raw=Path(freeze['raw_directory']).resolve()
    require(raw==ROOT/'build/overnight_20261008/learning/gen2-k-precision-3ed9','fixed raw directory required')
    records=[source_inventory(raw,seed,FREEZE_SHA) for seed in SEEDS]
    summary=aggregate(records,dispatch)
    require(summary['incomplete_or_failed_source_seeds'],'this helper accounts the blocked allocation; it cannot qualify a clean experiment')
    expected={raw/f'seed-{seed}.{role}' for seed in SEEDS for role in ROLES}
    unexpected=[bind(path) for path in sorted(raw.iterdir()) if path.is_file() and not path.is_symlink() and path.resolve() not in expected]
    frozen_artifacts=[bind(ROOT/path,digest) for path,digest in freeze['artifacts'].items()]
    frozen_artifacts.extend(bind(freeze[key],freeze[key+'_sha256']) for key in ('binary','teacher','policy'))
    result={'schema':'k_precision_blocked_metadata_accounting_v1','status':'METADATA_ACCOUNTING_COMPLETE',
            'primary_status':'EXECUTION_BLOCKED','recorded_epoch':time.time(),'summary':summary,'sources':records,
            'unexpected_raw_files':unexpected,'bindings':[frecord,drecord,crecord,authorization_record,dispatch_log_record,bind(__file__)]+frozen_artifacts,
            'allowed_csv_fields':FIELDS,'efficacy_interpreted':False,'selection_or_evaluation_invoked':False,
            'selection_or_evaluation_statement_scope':'This helper invokes neither stage; coordinator separately records campaign-wide nonexecution.',
            'limits':LIMITS}
    with args.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':result['status'],'primary_status':result['primary_status'],'output':str(args.output.resolve()),'sha256':sha(args.output),'summary':summary},indent=2))


if __name__=='__main__':main()
