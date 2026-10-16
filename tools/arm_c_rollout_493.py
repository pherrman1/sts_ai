"""Frozen §493 rollout comparison; prepare, canary, reviewed cohort. No retries."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import platform

import numpy as np

STUDENT_SHA = 'eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509'
EVIDENCE = Path('docs/experiments/evidence/arm_c_rollout_20261016')
CANARIES = [110161990, 110161991]
SEEDS = list(range(110162000, 110162032))
ARMS = ('chain', 'armc')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def require(ok, message):
    if not ok: raise ValueError(message)


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def read(path): return json.loads(Path(path).read_text())


def status(root, stage, **extra):
    value = {'stage': stage, 'pid': os.getpid(), 'time': time.time(),
             'processStartTicks': Path('/proc/self/stat').read_text().split()[21], **extra}
    temp = root/'status.tmp'
    temp.write_text(json.dumps(value, indent=2)+'\n'); temp.replace(root/'status.json')


def runtime_identity():
    return {'python':sys.version,'executableSha256':sha(Path(sys.executable).resolve()),
            'platform':platform.platform(),'numpy':np.__version__,
            'numpyInitSha256':sha(Path(np.__file__))}


def clean_head(repo, reviewed):
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==reviewed,
            'reviewed source is not HEAD')
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip(),
            'reviewed source must be clean')


def prepare(repo, root, reviewed, model):
    clean_head(repo, reviewed)
    require(sha(model)==STUDENT_SHA, 'wrong Arm C model')
    root.mkdir(parents=True, exist_ok=False); bundle=root/'run'; bundle.mkdir()
    command=['cmake','--build','--preset','linux-gcc-release-ccache-build','--target','one_combat','-j','4']
    with (root/'build.log').open('x') as log:
        subprocess.run(command,cwd=repo,stdout=log,stderr=subprocess.STDOUT,check=True)
    clean_head(repo, reviewed)
    binary=repo/'build/linux-gcc-release-ccache/one_combat'
    write(root/'build-receipt.json',{'reviewedSha':reviewed,'command':command,
          'binarySha256':sha(binary),'logSha256':sha(root/'build.log')})
    shutil.copy2(binary,bundle/'one_combat')
    models=subprocess.check_output(['git','ls-files','models','selfplay/models'],cwd=repo,text=True).splitlines()
    for name in models:
        dest=bundle/name; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(repo/name,dest)
    shutil.copy2(model,bundle/'studentc.bin')
    shutil.copy2('/usr/bin/time',bundle/'measure-time')
    for name in ['tools/arm_c_rollout_493.py','tools/seed_guard.sh','tools/agent/check_benchmark_canary.py']:
        shutil.copy2(repo/name,bundle/Path(name).name)
    shutil.copy2(repo/EVIDENCE/'PROTOCOL.md',bundle/'PROTOCOL.md')
    # Reuse §491's fully specified baseline environment, not its source data.
    original=Path('/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-rollout-distill-20261016-v3-armc/freeze.json')
    require(sha(original)=='c436ef5527f97c2932b83831eac5d043108be1e14eb26e45a6dc26f3a4563bad','baseline freeze changed')
    env=read(original)['environment']
    env.update(STS_EXECUTABLE_GIT_SHA=reviewed,STS_OOC_MCTS_SIMS='8192',
               STS_OOC_MCTS_EARLY_STOP='0',STS_OOC_MCTS_GAP_STOP_20='0',
               STS_OOC_MCTS_CPU_SECONDS='0.25',STS_OOC_MCTS_MERGE_OUTCOMES='1',
               STS_OOC_MCTS_ROLLOUT_SHOP='greedy')
    frozen={'reviewedSha':reviewed,'repo':str(repo),'canaries':CANARIES,'seeds':SEEDS,
            'arms':{'chain':'v4','armc':'heart1'},'workers':3,'unitTimeoutSeconds':900,
            'cohortWallSeconds':14400,'environment':env,'baselineFreezeSha256':sha(original),
            'files':{str(p.relative_to(root)):sha(p) for p in bundle.rglob('*') if p.is_file()},
            'buildReceiptSha256':sha(root/'build-receipt.json'),
            'runtime':runtime_identity()}
    write(root/'freeze.json',frozen)
    write(root/'prepared.json',{'freezeSha256':sha(root/'freeze.json'),'reviewedSha':reviewed})
    status(root,'prepared')


def verify(root):
    frozen=read(root/'freeze.json')
    require(sha(root/'freeze.json')==read(root/'prepared.json')['freezeSha256'],'freeze changed')
    clean_head(Path(frozen['repo']), frozen['reviewedSha'])
    require(sha(root/'run/arm_c_rollout_493.py')==sha(Path(__file__)), 'runner changed')
    require(frozen['runtime']==runtime_identity(),'Python/NumPy runtime changed')
    for name,digest in frozen['files'].items():require(sha(root/name)==digest,'bundle changed: '+name)
    receipt=read(root/'build-receipt.json')
    require(sha(root/'build-receipt.json')==frozen['buildReceiptSha256']
            and sha(root/'build.log')==receipt['logSha256'],'build custody changed')
    require(frozen['canaries']==CANARIES and frozen['seeds']==SEEDS,'cohort changed')
    return frozen


def quantile(values, q):
    ordered=sorted(values);require(bool(ordered),'empty resource sample')
    index=(len(ordered)-1)*q;lo=math.floor(index);hi=math.ceil(index)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(index-lo)


def resource_summary(decisions):
    valid=[d for d in decisions if not d['singleton_bypass'] and not d['aborted']]
    require(valid,'no nontrivial completed searches')
    for d in valid:
        require(d['completed_simulations']>0 and d['executed']
                and any(a['id']==d['selected_action'] for a in d['actions']), 'invalid selected action')
    cpu=[d['thread_cpu_seconds'] for d in valid]
    require(all(math.isfinite(t) and t>=0 for t in cpu),'invalid CPU measurement')
    overshoot=[max(0.,t-.25) for t in cpu]
    stops=sum(bool(d['early_stop_budget']) for d in valid)/len(valid)
    ceiling=sum(d['completed_simulations']==8192 for d in valid)/len(valid)
    result={'validSearches':len(valid),'allRoots':len(decisions),
            'singletons':sum(bool(d['singleton_bypass']) for d in decisions),
            'aborted':sum(bool(d['aborted']) for d in decisions),
            'budgetStoppedFraction':stops,'ceilingHitFraction':ceiling,
            'cpuMedian':quantile(cpu,.5),'cpuP95':quantile(cpu,.95),'cpuMax':max(cpu),
            'overshootP95':quantile(overshoot,.95),'overshootMax':max(overshoot),
            'simulationsMedian':quantile([d['completed_simulations'] for d in valid],.5)}
    result['pass']=stops>=.95 and ceiling<=.01 and result['overshootP95']<=.025 and result['overshootMax']<=.1
    return result


def validate_unit(root,frozen,base,seed,arm):
    bundle=root/'run'; log=base.with_suffix('.log').read_text()
    command=[sys.executable,str(bundle/'check_benchmark_canary.py'),
             '--results',str(base.with_suffix('.csv')),'--meta',str(base.with_suffix('.csv.meta.json')),
             '--log',str(base.with_suffix('.log')),'--expect-backend','native_silver',
             '--expect-seeds','1','--expect-sims','10000','--expect-seed-lo',str(seed),
             '--expect-asc','20','--expect-threads','1','--expect-fair','--no-expect-searcher3',
             '--binary',str(bundle/'one_combat'),'--expect-binary-sha256',frozen['files']['run/one_combat'],
             '--expect-executable-sha',frozen['reviewedSha']]
    check=subprocess.run(command,text=True,capture_output=True)
    require(check.returncode==0,'native benchmark contract: '+check.stdout+check.stderr)
    meta=read(base.with_suffix('.csv.meta.json')); config=meta['config']
    require(config['nativeOoc'] and config['collectKeys'] and config['stopAfterAct']==0 and config['silverExactRootBudgets']
            and not config['silverAdaptiveEnabled'] and config['silverReuseCap']==32768,'Heart/combat contract')
    expected=dict(frozen['environment'],STS_OOC_MCTS_LEAF_POLICY=frozen['arms'][arm])
    env=config['oocPolicy']['ooc_mcts']['environment']
    for key,value in expected.items():
        if key.startswith('STS_OOC_MCTS') and key!='STS_OOC_MCTS':require(env.get(key)==value,'effective control mismatch: '+key)
    artifacts=config['oocPolicy']['model_artifacts']
    require(any(a['role']=='ooc_heart1' and a['sha256']==STUDENT_SHA for a in artifacts),'wrong loaded Arm C artifact')
    require('[heart1] loaded studentc.bin (dim 64, heads 4, hidden 256, layers 2, trim_map 1)' in log
            and ' prior=heart1 ' in log and ' leaf_policy='+frozen['arms'][arm] in log,'Arm C load/activation missing')
    supports=[json.loads(s) for s in base.with_suffix('.mcts.csv.support.jsonl').read_text().splitlines()]
    require(len(supports)==1 and supports[0]['seed']==seed,'support receipt identity')
    support=supports[0]
    for name in ['heart1_prior_nodes','heart1_prior_fallbacks','heart1_leaf_steps','heart1_leaf_fallbacks','prior_leaf_steps']:
        require(type(support[name]) is int and support[name]>=0,'invalid usage counter')
    require(support['heart1_prior_nodes']>0 and support['heart1_prior_nodes']/max(1,support['heart1_prior_nodes']+support['heart1_prior_fallbacks'])>=.9,'Arm C tree prior insufficient')
    require(support['prior_leaf_steps']==0,'unexpected V4 policy-head rollout')
    scored=support['heart1_leaf_steps'];fallback=support['heart1_leaf_fallbacks']
    require((scored==fallback==0) if arm=='chain' else (scored>0 and scored/(scored+fallback)>=.9),'Arm C rollout usage gate')
    profile=[json.loads(line) for line in base.with_suffix('.profile.jsonl').read_text().splitlines()]
    require(all(str(p['seed'])==str(seed) for p in profile),'profile seed mismatch')
    decisions=[p for p in profile if p['kind']=='ooc_decision'];floors=[p for p in profile if p['kind']=='floor']
    require(floors and all(p['cpu_budget_seconds']==.25 for p in decisions),'profile CPU contract')
    # Preserve outcomes in CSV; the canary decision uses only support and cost.
    return {'support':support,'resource':resource_summary(decisions),
            'realCombatCpuSeconds':sum(p['real_combat_cpu_seconds'] for p in floors),
            'floorThreadCpuSeconds':sum(p['thread_cpu_seconds'] for p in floors),
            'processCpuSeconds':sum(read(base.with_suffix('.cpu.json'))[k] for k in ('userSeconds','systemSeconds')),
            'oocCpuSeconds':sum(p['thread_cpu_seconds'] for p in decisions),
            'otherAndFallbackCpuSeconds':sum(p['thread_cpu_seconds']-p['real_combat_cpu_seconds']-p['ooc_cpu_seconds'] for p in floors)}


def verify_unit_custody(root, receipt_path, expected):
    require(sha(root/receipt_path)==expected,'unit receipt changed: '+receipt_path)
    receipt=read(root/receipt_path)
    require(receipt['returncode']==0,'failed unit in accepted set')
    for path,digest in receipt['files'].items():require(sha(root/path)==digest,'post-run artifact changed: '+path)
    return receipt


def verify_custody_set(root, hashes, phase, seeds):
    require(set(hashes)=={f'{phase}-{seed}-{arm}.receipt.json' for seed in seeds for arm in ARMS},
            'receipt set does not match frozen pairs')
    for name,digest in hashes.items():verify_unit_custody(root,name,digest)


def unit(root,frozen,seed,arm,phase,deadline):
    base=root/f'{phase}-{seed}-{arm}'
    require(not list(root.glob(base.name+'.*')),'unit already exists; no retry')
    env=dict(frozen['environment'],STS_OOC_MCTS_LEAF_POLICY=frozen['arms'][arm],
             STS_OOC_MCTS_TRACE=str(base.with_suffix('.mcts.csv')),STS_RUN_PROFILE=str(base.with_suffix('.profile.jsonl')))
    command=['bash',str(root/'run/seed_guard.sh'),str(root/'run/measure-time'),
             '-o',str(base.with_suffix('.cpu.json')),'-f','{"userSeconds":%U,"systemSeconds":%S}',
             str(root/'run/one_combat'),
             'bestbench','10000','1','20',str(seed),str(base.with_suffix('.csv'))]
    started=time.monotonic();receipt={'seed':seed,'arm':arm,'command':command,'environment':env}
    with base.with_suffix('.log').open('x') as log:
        timeout=min(frozen['unitTimeoutSeconds'],deadline-time.monotonic())
        require(timeout>0,'phase deadline reached before launch')
        receipt['effectiveTimeoutSeconds']=timeout
        with subprocess.Popen(command,cwd=root/'run',env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True) as child:
            receipt['childProcessGroup']=child.pid
            try:code=child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                code=124
    receipt.update(returncode=code,seconds=time.monotonic()-started)
    if code==0:
        try:receipt['validation']=validate_unit(root,frozen,base,seed,arm)
        except Exception as error:receipt['validationError']=str(error);receipt['returncode']=65
    receipt['files']={str(p.relative_to(root)):sha(p) for p in root.glob(base.name+'.*')}
    write(base.with_suffix('.receipt.json'),receipt)
    require(receipt['returncode']==0,'unit failed: '+base.name)
    receipt['_savedSha256']=sha(base.with_suffix('.receipt.json'))
    return receipt


def phase(root,which):
    frozen=verify(root)
    if which=='cohort':
        approval=read(root/'canary-reviewed.json')
        require(approval['pass'] is True and approval['canarySha256']==sha(root/'canary-result.json')
                and approval['reviewedSha']==frozen['reviewedSha'],'independent canary review missing')
        canary=read(root/'canary-result.json')
        require(canary['pass'],'canary failed')
        verify_custody_set(root,canary['unitReceiptHashes'],'canary',frozen['canaries'])
    write(root/(which+'-started.json'),{'reviewedSha':frozen['reviewedSha'],'started':time.time()})
    status(root,which,completedPairs=0)
    seeds=frozen['canaries'] if which=='canary' else frozen['seeds']
    deadline=time.monotonic()+frozen['cohortWallSeconds'];stop=threading.Event();all_units=[];errors=[]
    def pair(seed):
        output=[]
        try:
            for arm in (ARMS if seed%2==0 else tuple(reversed(ARMS))):
                require(not stop.is_set() and time.monotonic()<deadline,'cohort stopped/deadline reached')
                output.append(unit(root,frozen,seed,arm,which,deadline))
        except Exception:
            stop.set();raise
        return output
    with ThreadPoolExecutor(max_workers=1 if which=='canary' else frozen['workers']) as pool:
        jobs={pool.submit(pair,s):s for s in seeds}
        for future in as_completed(jobs):
            try:all_units.extend(future.result())
            except Exception as error:errors.append({'seed':jobs[future],'error':str(error)})
            status(root,which,completedPairs=len(all_units)//2,failedPairs=len(errors))
    verify(root)
    if errors:
        write(root/(which+'-result.json'),{'verdict':'INCOMPLETE','pass':False,'errors':errors})
        raise RuntimeError('incomplete cohort; no partial efficacy analysis/retry')
    hashes={f'{which}-{u["seed"]}-{u["arm"]}.receipt.json':u['_savedSha256'] for u in all_units}
    verify_custody_set(root,hashes,which,seeds)
    resources={arm:resource_summary([json.loads(line) for seed in seeds
               for line in (root/f'{which}-{seed}-{arm}.profile.jsonl').read_text().splitlines()
               if json.loads(line)['kind']=='ooc_decision']) for arm in ARMS}
    passed=all(r['pass'] for r in resources.values())
    packet={'pass':passed,'resources':resources,'sources':len(seeds),'units':len(all_units),
            'unitReceiptHashes':hashes}
    if not passed:packet['verdict']='INVALID_RESOURCE_MATCH'
    elif which=='cohort':packet.update(analyze(root,seeds))
    write(root/(which+'-result.json'),packet)
    status(root,'canary-awaiting-review' if which=='canary' and passed else 'complete',verdict=packet.get('verdict'))
    require(passed,'resource gate failed; no adaptive tuning or retry')
    print(json.dumps(packet,indent=2))


def mcnemar(b,c):
    n=b+c
    return min(1.,2*sum(math.comb(n,i) for i in range(min(b,c)+1))/2**n) if n else 1.


def analyze(root,seeds):
    import numpy as np
    values={}
    for arm in ARMS:
        rows=[];receipts=[]
        for seed in seeds:
            base=root/f'cohort-{seed}-{arm}';receipt=read(base.with_suffix('.receipt.json'))
            require(receipt['returncode']==0,'failed unit in analysis')
            for path,digest in receipt['files'].items():require(sha(root/path)==digest,'post-run artifact changed')
            with base.with_suffix('.csv').open() as stream:row=list(csv.DictReader(stream))
            require(len(row)==1 and int(row[0]['seed'])==seed,'paired source mismatch')
            rows.append(row[0]);receipts.append(receipt)
        values[arm]=(rows,receipts)
    baseline=np.array([int(r['won']) for r in values['chain'][0]])
    treatment=np.array([int(r['won']) for r in values['armc'][0]])
    require(np.isin(baseline,[0,1]).all() and np.isin(treatment,[0,1]).all(),'invalid binary outcome')
    delta=treatment-baseline;rng=np.random.default_rng(49320261016)
    ci=np.quantile([rng.choice(delta,len(delta),replace=True).mean() for _ in range(10000)],[.025,.975]).tolist()
    b=int(((treatment==1)&(baseline==0)).sum());c=int(((treatment==0)&(baseline==1)).sum());p=mcnemar(b,c)
    verdict='IMPROVED' if ci[0]>0 and p<.05 else 'WORSE' if ci[1]<0 and p<.05 else 'NOT_SHOWN'
    summary={}
    for arm,(rows,receipts) in values.items():
        summary[arm]={'heartKills':sum(int(r['won']) for r in rows),'sources':len(rows),
          'meanFloor':float(np.mean([float(r['floor']) for r in rows])),
          'meanEndHp':float(np.mean([float(r['hpEnd']) for r in rows])),
          'reachedAct3':sum(int(r['act'])>=3 for r in rows),'reachedAct4':sum(int(r['act'])>=4 for r in rows),
          'meanUnitWallSeconds':float(np.mean([r['seconds'] for r in receipts])),
          **{key:float(np.mean([r['validation'][key] for r in receipts])) for key in
             ['realCombatCpuSeconds','floorThreadCpuSeconds','processCpuSeconds','oocCpuSeconds','otherAndFallbackCpuSeconds']}}
    return {'verdict':verdict,'primary':{'heartKillDifference':float(delta.mean()),'paired95CI':ci,
            'treatmentOnlyWins':b,'controlOnlyWins':c,'exactMcNemarP':p},'arms':summary,
            'runtimePromotion':False,'newDistillationStarted':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','canary','cohort']);parser.add_argument('root',type=Path)
    parser.add_argument('--repo',type=Path);parser.add_argument('--reviewed');parser.add_argument('--model',type=Path)
    args=parser.parse_args();root=args.root.resolve()
    try:
        if args.mode=='prepare':prepare(args.repo.resolve(),root,args.reviewed,args.model.resolve())
        else:phase(root,args.mode)
    except Exception as error:
        if root.exists():
            failure=root/(args.mode+'-failure.json')
            if not failure.exists():write(failure,{'error':str(error),'time':time.time(),'noAutomaticRetry':True})
            status(root,'failed',phase=args.mode,error=str(error))
        raise


if __name__=='__main__':main()
