#!/usr/bin/env python3
"""Fixed blocked-cohort custody/metadata/health review, with no efficacy interpretation."""
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[5]
E=ROOT/'docs/experiments/evidence/ironclad_a0_k_precision_20261008'
SEEDS=list(range(610084200,610084232))
FREEZE='fc86c6e538618bf9212ffca58d422bda472954aa00f67a9216c3129c1a0df859'
CLOSE='8aa5e35ba1fe226237c99996fbe8805eb32badf54e9619436e5a68ab78e2780c'
ACCOUNT='f1bd088ec0c1c7fb6cf09b4fffc9926494ecd9861fb0bb70d4eb27a8165c9c39'
CONTRACT='33617a4879dc4ef0d2664e7defb0ef07f9dc7f232bd71b7a1e4ca1878b52ae6b'
ROLES={'labels.csv','options.csv','sources.csv','map.csv','manifest.json','log','tree.jsonl'}
INPUTS={}

def require(ok,message):
    if not ok:raise ValueError(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def bind(path,expected=None):
    path=Path(path).resolve();actual=sha(path)
    require(expected is None or actual==expected,'changed input '+str(path))
    INPUTS[str(path)]={'path':str(path),'sha256':actual,'bytes':path.stat().st_size}
    return path

def read(path,expected=None):return json.loads(bind(path,expected).read_text())

def project(path,fields):
    """Discard outcomes while projecting CSV metadata; exclude unterminated last record."""
    p=Path(path);data=p.read_bytes()
    if not data:return []
    with p.open(newline='') as f:
        reader=csv.reader(f,strict=True);header=next(reader)
        require(len(header)==len(set(header)) and all(k in header for k in fields),'metadata header invalid')
        records=list(reader)
    if not data.endswith(b'\n'):records=records[:-1]
    indices={k:header.index(k) for k in fields}
    return [{k:r[i] for k,i in indices.items()} for r in records if len(r)==len(header)]

def main():
    out=E/'audit/CLOSEOUT_REVIEW.json';require(not out.exists(),'refusing overwrite')
    freeze=read(E/'freeze.json',FREEZE);raw=Path(freeze['raw_directory'])
    close=read(E/'process_closeout.json',CLOSE)
    completion=read(E/'dispatch_completion.json',close['dispatcher_completion_sha256'])
    auth=read(E/'dispatch_authorization.json',completion['authorization_sha256'])
    ready=read(E/'ready_bundle.json',auth['ready_bundle_sha256'])
    for x in ready['inputs']:bind(x['path'],x['sha256'])
    for p,h in freeze['artifacts'].items():bind(ROOT/p,h)
    for k in ('binary','teacher','policy'):bind(freeze[k],freeze[k+'_sha256'])
    for p,h in close['prior_closed_confirmation_hashes'].items():bind(p,h)
    require(auth['freeze_sha256']==FREEZE and auth['reviewed_commit']==ready['reviewed_commit'],'launch binding')
    require(close['all32_receipts_terminal'] and close['source_seeds']==SEEDS and close['active_game_processes']==0 and
            not close['active_owned_controller_processes'] and close['no_retry_replacement_or_extension'],'bad process closeout')
    require(completion['exit_code']==123 and completion['status']=='DISPATCH_FAILED_NO_RETRY','raw dispatcher status changed')
    require(completion['finished_epoch']<freeze['absolute_stop_epoch'] and completion['finished_epoch']-completion['started_epoch']<10800,'dispatch cap violated')
    bind(raw/'dispatch.log',completion['log_sha256'])
    contract=read(E/'audit/contract_receipt.json',CONTRACT)
    invocation=read(E/'audit/contract_invocation.json','70e78a8b382af23111511665c3ffaff280c28a67689595398a5eb8b89f2a1713')
    require(contract['status']=='INVALID' and contract['error']=='source subprocess incomplete/failed' and
            contract['evaluation_outcomes_reported'] is False and contract['freeze_sha256']==FREEZE,'raw contract verdict changed')
    require(invocation['exit_code']==1 and invocation['receipt_sha256']==CONTRACT,'checker failure not preserved')
    bind(E/'audit/contract_check.log',invocation['stdout_stderr_sha256'])
    expected_cmd=[str(ROOT/'.venv/bin/python'),freeze['verifier'],'--freeze',str(E/'freeze.json'),'--out',str(E/'audit/contract_receipt.json')]
    for seed in SEEDS:expected_cmd+=['--prefix',str(raw/f'seed-{seed}')]
    require(invocation['command']==expected_cmd,'wrong verifier allocation')
    accounting=read(E/'analysis/blocked_accounting.json',ACCOUNT)
    require(accounting['primary_status']=='EXECUTION_BLOCKED' and accounting['efficacy_interpreted'] is False and accounting['selection_or_evaluation_invoked'] is False,'accounting scope drift')
    for x in accounting['bindings']:bind(x['path'],x['sha256'])
    vp=bind(freeze['verifier'],freeze['verifier_sha256']);spec=importlib.util.spec_from_file_location('closeout_health',vp)
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    require(set(raw.glob('*.receipt.json'))=={raw/f'seed-{s}.receipt.json' for s in SEEDS},'receipt inventory changed')
    records=[];events=[];sum_source_cpu=0.;sum_branch_cpu=0.;sum_wall=0.;total_labels=0;observed_states=0
    all_health=v.empty_health();all_findings=[];timeout_location=None;expected_raw={raw/'dispatch.log'}
    for seed in SEEDS:
        prefix=raw/f'seed-{seed}';rp=Path(str(prefix)+'.receipt.json');r=read(rp);expected_raw.add(rp)
        expected_status='timeout' if seed==610084217 else 'completed';expected_exit=124 if seed==610084217 else 0
        require(r['status']==expected_status and r['exit_code']==expected_exit and r['source_seed']==seed,'source terminal status mismatch')
        require(r['freeze_sha256']==FREEZE and Path(r['freeze'])==E/'freeze.json' and r['source_sha']==freeze['source_sha'] and
                r['binary_sha256']==freeze['binary_sha256'] and r['script_sha256']==freeze['runner_sha256'],'source custody mismatch')
        require(r['environment']==dict(freeze['environment'],STS_SILVER_TREE_PROFILE=str(prefix)+'.tree.jsonl'),'source environment mismatch')
        cmd=['bash','tools/seed_guard.sh',freeze['binary'],'ooccfpilotgen','1',str(prefix),str(seed),freeze['teacher'],'32','1','1','2','BOSS_RELIC']
        require(r['command']==cmd,'source command mismatch')
        require(set(r['outputs'])==(ROLES-{'manifest.json'} if seed==610084217 else ROLES),'source output inventory mismatch')
        for suffix,x in r['outputs'].items():
            p=Path(str(prefix)+'.'+suffix);require(x['path']==str(p) and p.stat().st_size==x['bytes'],'source output path/size mismatch')
            bind(p,x['sha256']);expected_raw.add(p)
        require(freeze['frozen_epoch']<=r['started_epoch']<=r['finished_epoch']<=completion['finished_epoch'],'source timeline mismatch')
        if seed!=610084217:require(r['wall_seconds']<=1800,'completed source exceeded cap')
        events.extend([(r['started_epoch'],1),(r['finished_epoch'],-1)]);sum_wall+=r['wall_seconds']
        options=project(Path(str(prefix)+'.options.csv'),('sourceSeed','decisionIdx','type','optionIdx'))
        sources=project(Path(str(prefix)+'.sources.csv'),('sourceSeed','decisionIdx','type','trajectoryValid','options','sourceCpuSeconds'))
        labels=project(Path(str(prefix)+'.labels.csv'),('sourceSeed','decisionIdx','type','act','floor','optionIdx','k','futureSeed','valid','error','cpuSeconds'))
        maps=project(Path(str(prefix)+'.map.csv'),('sourceSeed','decisionIdx','type','optionIdx','k'))
        require(all(x['sourceSeed']==str(seed) for x in options+sources+labels+maps),'metadata source mismatch')
        require(all(x['valid']=='1' and x['error']=='' for x in labels),'observed branch validity failure')
        keys=lambda rows:{(x['decisionIdx'],x['type'],x['optionIdx'],x['k']) for x in rows}
        require(len(keys(labels))==len(labels) and len(keys(maps))==len(maps),'duplicate metadata branch identity')
        for row in labels:
            digest=hashlib.sha256(f"ooc-cf-pilot-v2-future:{seed}:{row['decisionIdx']}:{row['k']}".encode()).hexdigest()
            require(int(row['futureSeed'])==int(digest[:16],16),'branch future identity mismatch')
            require(math.isfinite(float(row['cpuSeconds'])) and float(row['cpuSeconds'])>=0,'invalid observed branch CPU')
        cpu=sum(float(x['cpuSeconds']) for x in labels);sum_branch_cpu+=cpu;total_labels+=len(labels)
        if seed!=610084217:
            require(len(sources)==1 and sources[0]['trajectoryValid']=='1','source trajectory metadata invalid')
            scpu=float(sources[0]['sourceCpuSeconds']);require(math.isfinite(scpu) and scpu>=0,'invalid source CPU');sum_source_cpu+=scpu
            require(sources[0]['type']=='BOSS_RELIC' and int(sources[0]['decisionIdx'])>=0,'unexpected completed no-state source')
            observed_states+=1
            require(len(options)==int(sources[0]['options']) and len(labels)==32*len(options),'completed retained branch count mismatch')
            expected={(o['decisionIdx'],o['type'],o['optionIdx'],str(k)) for o in options for k in range(32)}
            require(keys(labels)==keys(maps)==expected,'completed MAP/branch identity coverage')
            manifest=read(Path(str(prefix)+'.manifest.json'))
            require(manifest['producerGitSha']==freeze['source_sha'] and manifest['producerExecutableSha256']==freeze['binary_sha256'] and
                    manifest['teacherManifestSha256']==freeze['teacher_sha256'],'completed manifest producer mismatch')
            require(manifest['integrity']['selectedStates']==1 and manifest['integrity']['labelRows']==manifest['integrity']['validLabelRows']==len(labels),'completed manifest validity/count mismatch')
            for suffix,h in manifest['outputs'].items():require(h==r['outputs'][suffix]['sha256'],'manifest/receipt hash mismatch')
        else:
            require(not sources and len(labels)==100,'failed source shape changed')
            location={(x['decisionIdx'],x['type'],x['act'],x['floor']) for x in labels}
            require(location=={('35','BOSS_RELIC','1','17')},'timeout public source location mismatch')
            timeout_location={'source':'labels.csv explicit act/floor columns in100 newline-terminated complete records','decision_idx':35,'type':'BOSS_RELIC','act':1,'floor':17,'inference':False,'path':str(prefix)+'.labels.csv','sha256':r['outputs']['labels.csv']['sha256']}
        allowed=v.expected_profile_seeds(seed,labels,32);health=v.empty_health();findings=[];seen=set()
        with Path(str(prefix)+'.tree.jsonl').open() as tree:
            for line,rawline in enumerate(tree,1):
                try:
                    row=v.HEALTH.parse(rawline);counts=v.verify_profile_root(row,allowed)
                    identity=(row['seed'],v.HEALTH.natural(row['combat_id']),v.HEALTH.natural(row['decision']))
                    require(identity not in seen,'duplicate profile identity');seen.add(identity)
                    health['roots']+=1
                    for k in ('completed_simulations','cycle_rollouts'):health[k]+=row[k]
                    health['singleton_skips']+=int(row['singleton_skip'])
                    for k in ('engine_stop','turn_limit'):health[k]+=counts[k]
                except (ValueError,KeyError,TypeError) as exc:findings.append({'source_seed':seed,'line':line,'error':str(exc)})
        health['fatal_findings']=len(findings);all_findings.extend(findings)
        for key in all_health:all_health[key]+=health[key]
        records.append({'source_seed':seed,'status':r['status'],'receipt_sha256':sha(rp),'saved_branch_rows':len(labels),
                        'saved_map_rows':len(maps),'observed_branch_cpu_seconds':cpu,'health':health,
                        'interrupted_work_uncertified':seed==610084217})
        print(json.dumps({'checked_source':seed,'saved_roots':health['roots'],'fatal_findings':len(findings)}),flush=True)
    require(set(raw.iterdir())==expected_raw,'unexpected raw file or attempt')
    occupancy=maximum=0
    for epoch,delta in sorted(events):occupancy+=delta;maximum=max(maximum,occupancy)
    require(occupancy==0 and maximum==6,'concurrency mismatch')
    expected_summary=accounting['summary']
    for key,value in [('source_cpu_observed_seconds',sum_source_cpu),('branch_cpu_observed_seconds',sum_branch_cpu),('invocation_wall_seconds_sum',sum_wall)]:
        require(math.isclose(expected_summary[key],value,abs_tol=1e-8,rel_tol=0),'accounting arithmetic mismatch '+key)
    require(expected_summary['observed_branch_rows']==total_labels and expected_summary['observed_retained_states']==observed_states,'accounting count mismatch')
    for ar,record in zip(accounting['sources'],records):
        require(ar['source_seed']==record['source_seed'] and ar['metadata']['observed_branch_rows']==record['saved_branch_rows'] and
                ar['metadata']['observed_map_rows']==record['saved_map_rows'],'accounting per-source metadata mismatch')
        for x in ar['files']:require(INPUTS[x['path']]['sha256']==x['sha256'],'accounting raw hash mismatch')
    forbidden=[]
    for path in (E/'analysis').glob('*.json'):
        j=json.loads(path.read_text())
        if j.get('schema') in ('k_precision_choices_v1','k_precision_evaluation_v1') or j.get('status') in ('CHOICES_FROZEN','CONDITIONAL_EVALUATION_COMPLETE'):forbidden.append(str(path))
    require(not forbidden and close['selection_invoked'] is False and close['evaluation_invoked'] is False,'unexpected selector/evaluation artifact')
    workers=[]
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:argv=[x.decode(errors='replace') for x in path.read_bytes().split(b'\0') if x]
        except (OSError,ProcessLookupError):continue
        if not argv:continue
        executable=Path(argv[0]).name
        if executable=='one_combat' or (executable in ('timeout','xargs') and str(E/'jobs.txt') in argv):workers.append({'pid':path.parent.name,'executable':executable})
    require(not workers,'game/controller still active')
    result={'schema':'k_precision_independent_closeout_review_v1','status':'PASS_BLOCKED_CLOSEOUT','primary_status':'EXECUTION_BLOCKED',
            'review_epoch':time.time(),'freeze_sha256':FREEZE,'process_closeout_sha256':CLOSE,'contract_receipt_sha256':CONTRACT,
            'accounting_sha256':ACCOUNT,'raw_dispatcher_exit_code':123,'raw_verifier_exit_code':1,'contract_raw_status':'INVALID',
            'contract_raw_error':'source subprocess incomplete/failed','allocated_source_seeds':SEEDS,'source_attempts':32,
            'receipt_status_counts':{'completed':31,'timeout':1},'timed_out_source':610084217,'maximum_concurrency':maximum,
            'active_workers_at_independent_check':workers,'raw_inventory_files':len(expected_raw),'saved_branch_records':total_labels,
            'completed_sources_branch_records':total_labels-100,'observed_source_cpu_seconds':sum_source_cpu,
            'observed_branch_cpu_seconds':sum_branch_cpu,'observed_total_cpu_core_hours':(sum_source_cpu+sum_branch_cpu)/3600,
            'invocation_wall_seconds_sum':sum_wall,'dispatcher_elapsed_seconds':completion['finished_epoch']-completion['started_epoch'],
            'saved_profile_health':all_health,'profile_findings':all_findings,'sources':records,
            'timeout_state_location_provenance':timeout_location,'old_closed_confirmation_hashes_unchanged':close['prior_closed_confirmation_hashes'],
            'selection_evaluation_artifact_scan':{'directory':str(E/'analysis'),'forbidden_artifacts':forbidden,'coordinator_nonexecution_receipt_bound':True},
            'efficacy_interpreted':False,'efficacy_analyzer_invoked_by_reviewer':False,'games_run_by_reviewer':0,
            'limits':['PASS concerns execution custody and correct blocked disposition; the32-source scientific contract is INVALID.',
                      'Completed-source metadata/health checks do not create a31-source substitute primary. Timed-out217 cannot be treated as a valid no-state source.',
                      'Observed CPU includes only persisted complete records and remains censored; source217 source CPU/current work is unavailable.',
                      'Profile health covers saved roots only. Interrupted or buffered work remains uncertified; profiles do not attribute coverage to every branch.',
                      'Cycle fallbacks and engine/turn safety endpoints are diagnostics, not new efficacy thresholds.',
                      'No selector/evaluation artifacts were found and coordinator nonexecution is bound; this is filesystem and receipt evidence, not a complete OS execution trace.'],
            'inputs':list(INPUTS.values())}
    bind(__file__);result['inputs']=list(INPUTS.values())
    with out.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':result['status'],'output':str(out),'sha256':sha(out),'health':all_health}),flush=True)

if __name__=='__main__':main()
