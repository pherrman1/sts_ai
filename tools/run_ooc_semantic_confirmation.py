#!/usr/bin/env python3
"""Guarded fixed-cohort semantic capture/evaluation on the designated GCP host.

Capture and evaluation are separate stages. Evaluation requires a hash-bound
capture review and frozen analysis tooling; completed validated shards are reused.
"""
from __future__ import annotations
import argparse
import collections
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

START, STOP, SHARDS, PER_SHARD = 992000, 993024, 64, 16
GCP_ROOT = Path('/home/philippherrmann/sts_sweep')
MODELS = {'policy_trees_c.txt':'24793bd39dd1a35c8865035e458c3aa40616ef021cb26b05f914f72fb5e5a321',
          'v_rich_trees.txt':'3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3',
          'v_win_trees.txt':'fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70'}
def verify_evaluated_binding(semantic_doc, combat_doc, captured, captured_path, teacher, producer_sha, binary_hash):
    expected={'path':str(captured_path),'sha256':digest(captured_path)}
    for doc,teacher_key in ((semantic_doc,'combat_teacher'),(combat_doc,'teacher')):
        require(doc['frozen_manifest']==expected,'evaluated output belongs to a different capture')
        require(doc['producer_git_sha']==producer_sha and doc['producer_executable_sha256']==binary_hash,'evaluated producer mismatch')
        require(doc[teacher_key]==teacher,'evaluated teacher mismatch')
    require(semantic_doc['sampling']==captured['sampling'],'evaluated seed block mismatch')

FAMILY = {0:'CAMPFIRE',1:'CAMPFIRE',2:'CAMPFIRE',3:'SHOP',4:'SHOP',5:'EVENT',6:'SELECTOR',7:'REWARDS',8:'TREASURE',9:'BOSS_RELIC'}

def require(ok, message):
    if not ok: raise ValueError(message)

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def save(path, data):
    path=Path(path); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n'); tmp.replace(path)

def load(path): return json.loads(Path(path).read_text())

def capture_distribution(manifests):
    seeds=[]; decisions=[];families=collections.Counter();effects=collections.Counter();sources=collections.Counter();sizes=collections.Counter();compounds=0
    for doc in manifests:
        seeds+=doc['sampling']['sourceSeeds'];decisions+=doc['decisions']
        for d in doc['decisions']:
            sizes[len(d['actions'])]+=1
            family={FAMILY[a['semanticSource']] for a in d['actions']}
            require(len(family)==1,'mixed semantic source family within decision')
            families.update(family)
            for a in d['actions']:
                effects[a['semanticEffect']]+=1;sources[a['semanticSource']]+=1
            compounds+=any(a['semanticPayload']['type']=='transaction' or a['semanticSource'] in (0,2,4) for a in d['actions'])
    require(sorted(seeds)==list(range(START,STOP)),'source seeds must be exact fresh 1024 cohort')
    require(sorted(d['sourceSeed'] for d in decisions)==list(range(START,STOP)),'must capture exactly one decision from every source seed')
    return {'decisions':len(decisions),'action_rows':sum(len(d['actions']) for d in decisions),
            'actions_per_decision':dict(sizes),'families':{f:families[f] for f in sorted(set(FAMILY.values()))},
            'effects':dict(effects),'sources':dict(sources),'compound_containing_decisions':compounds}

def timing(path):
    text=Path(path).read_text()
    def value(label):
        m=re.search(r'^\s*'+re.escape(label)+r':\s*([\d.]+)',text,re.M)
        return float(m.group(1)) if m else None
    user=value('User time (seconds)');system=value('System time (seconds)')
    return {'cpu_seconds':user+system if user is not None and system is not None else None,
            'max_rss_kib':value('Maximum resident set size (kbytes)')}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['freeze','capture','gate','evaluate']);p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--producer-sha',required=True);p.add_argument('--workers',type=int,default=16);p.add_argument('--analysis-freeze',type=Path)
    p.add_argument('--capture-review',type=Path);a=p.parse_args()
    require(platform.node()=='sts-test' and Path.cwd()==GCP_ROOT and os.environ.get('STS_GCP_RESEARCH_CONTEXT')=='sts-test','must run through designated GCP launcher')
    require(re.fullmatch('[0-9a-f]{40}',a.producer_sha),'full producer SHA required')
    require(1<=a.workers<=min(20,os.cpu_count() or 1),'invalid worker capacity')
    root=a.run_root.resolve();source=root/'producer';binary=root/'frozen/one_combat'
    timer=root/'tooling/usr/bin/time'
    require(timer.is_file(),'user-local GNU time is required before launching shards')
    sys.path.insert(0,str(source/'tools'))
    import ooc_semantic_pipeline_contract as semantic
    import combat_evaluator_semantic_branch_contract as combat
    (root/'data').mkdir(exist_ok=True)
    for name,h in MODELS.items():require(digest(source/'models'/name)==h,'model hash mismatch '+name)
    freeze_path=root/'corpus-freeze.json';teacher_path=root/'teacher.json'
    env={k:v for k,v in os.environ.items() if not k.startswith(('STS_','STRATEGIC_'))}
    env['OMP_NUM_THREADS']='1'; env['GIT_CEILING_DIRECTORIES']=str(root)
    if a.stage=='freeze':
        require(not freeze_path.exists() and not teacher_path.exists(),'freeze already exists')
        inventory=load(root/'source-inventory.json');require(inventory['producer_sha']==a.producer_sha,'source archive SHA mismatch')
        for name,h in inventory['file_sha256'].items():require(digest(source/name)==h,'producer source changed '+name)
        require('CMAKE_BUILD_TYPE:STRING=Release' in (source/'build/linux-gcc-release-ccache/CMakeCache.txt').read_text(),'Release build required')
        teacher=load(source/'tools/ooc_teacher.example.json');teacher.update(teacher_id='silver-ordinary-fair-exact10k-confirmation-'+a.producer_sha[:12],git_sha=a.producer_sha,executable_sha256=digest(binary))
        teacher['environment'].update(STS_NATIVE_OOC='1',STS_EXECUTABLE_GIT_SHA=a.producer_sha,STS_GCP_RESEARCH_CONTEXT='sts-test')
        teacher['model_artifacts']=[{'role':role,'path':str(source/'models'/name),'sha256':h} for role,(name,h) in zip(('policy','floor','win'),MODELS.items())]
        save(teacher_path,teacher)
        freeze={'producer_sha':a.producer_sha,'binary':str(binary),'executable_sha256':digest(binary),'teacher_sha256':digest(teacher_path),
                'runner_sha256':digest(__file__),'source_inventory_sha256':digest(root/'source-inventory.json'),'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                'source_seeds':list(range(START,STOP)),'shards':SHARDS,'sources_per_shard':PER_SHARD,'OMP_NUM_THREADS':1,
                'development_probe_sha256':digest(source/'tools/train_ooc_semantic_probe.py')}
        save(freeze_path,freeze);print(json.dumps(freeze),flush=True);return
    freeze=load(freeze_path);teacher=load(teacher_path)
    require(freeze['producer_sha']==a.producer_sha and freeze['executable_sha256']==digest(binary),'producer/executable changed after freeze')
    require(freeze['teacher_sha256']==digest(teacher_path) and freeze['runner_sha256']==digest(__file__),'teacher/runner changed after freeze')
    env.update(teacher['environment'])
    def capture_path(i):return root/'data'/f'shard-{i:02d}.capture.json'
    def verify_capture(i):
        doc=load(capture_path(i));semantic.validate_manifest(doc,verify_csv=False)
        require(doc['sampling']['sourceSeeds']==list(range(START+i*PER_SHARD,START+(i+1)*PER_SHARD)),'shard source block mismatch')
        require(doc['combat_teacher']==teacher and doc['producer_git_sha']==a.producer_sha and doc['producer_executable_sha256']==freeze['executable_sha256'],'shard frozen producer mismatch')
        return doc
    def verify_evaluated(i):
        base=root/'data'/f'shard-{i:02d}'
        captured=verify_capture(i)
        sem=load(str(base)+'.semantic.csv.manifest.json'); comb=load(str(base)+'.combat.csv.manifest.json')
        semantic.validate_corpus(sem); combat.validate_manifest(comb)
        verify_evaluated_binding(sem,comb,captured,capture_path(i),teacher,a.producer_sha,freeze['executable_sha256'])
    if a.stage in ('gate','evaluate'):
        manifests=[verify_capture(i) for i in range(SHARDS)]
        distribution=capture_distribution(manifests)
        gate={'distribution':distribution,'captures':{str(capture_path(i)):digest(capture_path(i)) for i in range(SHARDS)},'producer_sha':a.producer_sha,'freeze_sha256':digest(freeze_path)}
        if a.stage=='gate':save(root/'capture-gate.json',gate);print(json.dumps(gate),flush=True);return
        require(load(root/'capture-gate.json')==gate,'capture gate changed')
        require(a.capture_review and a.analysis_freeze,'evaluation needs capture review and frozen analysis manifest')
        review=load(a.capture_review); require(review.get('proceed') is True and review.get('capture_gate_sha256')==digest(root/'capture-gate.json'),'missing/stale capture review')
        analysis=load(a.analysis_freeze)
        require(analysis.get('producer_sha')==a.producer_sha and analysis.get('before_new_labels') is True,'invalid analysis freeze')
        for name,h in analysis['file_sha256'].items():require(digest(name)==h,'analysis tooling changed after freeze')
    def worker(i):
        base=root/'data'/f'shard-{i:02d}';record=Path(str(base)+'.'+a.stage+'.result.json')
        if record.exists():
            r=load(record);require(r['returncode']==0,'failed shard requires explicit investigation; will not rerun')
            if a.stage=='capture':verify_capture(i)
            else:verify_evaluated(i)
            return {'shard':i,'reused':True}
        if a.stage=='capture':
            require(not capture_path(i).exists(),'unrecorded capture exists; inspect before resuming')
            args=['oocsemanticcapture',str(PER_SHARD),str(START+i*PER_SHARD),str(capture_path(i)),str(teacher_path)]
        else:
            verify_capture(i)
            for suffix in ('.semantic.csv','.semantic.csv.partial','.combat.csv','.combat.csv.partial'):
                require(not Path(str(base)+suffix).exists(),'unrecorded output exists; inspect before resuming')
            args=['oocsemanticeval',str(PER_SHARD),str(capture_path(i)),str(base)+'.semantic.csv',str(teacher_path),str(base)+'.combat.csv']
        # Guard parses the explicit one_combat argv before the cwd wrapper executes.
        command=[str(timer),'-v','-o',str(base)+'.'+a.stage+'.time.txt','bash',str(source/'tools/seed_guard.sh'),'--gcp-research',
                 'bash','-c','cd "$1"; shift; exec "$@"','phase-b',str(source),str(binary),*args]
        start=time.monotonic()
        with Path(str(base)+'.'+a.stage+'.log').open('x') as log:
            result=subprocess.run(command,cwd=GCP_ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        r={'shard':i,'stage':a.stage,'argv':command,'returncode':result.returncode,'wall_seconds':time.monotonic()-start,
           **timing(str(base)+'.'+a.stage+'.time.txt')}
        if result.returncode==0:
            if a.stage=='capture':verify_capture(i)
            else:verify_evaluated(i)
        save(record,r);require(result.returncode==0,f'shard {i} failed');return r
    start=time.monotonic();done=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(worker,i) for i in range(SHARDS)]
        try:
            for future in concurrent.futures.as_completed(futures):
                r=future.result();done.append(r);print(json.dumps(r),flush=True)
                save(root/(a.stage+'-progress.json'),{'completed':len(done),'total':SHARDS,'workers':a.workers,'elapsed_seconds':time.monotonic()-start})
        except BaseException:
            for future in futures:future.cancel()
            raise
    save(root/(a.stage+'-complete.json'),{'completed':SHARDS,'workers':a.workers,'wall_seconds':time.monotonic()-start,'shards':done})

if __name__=='__main__':main()
