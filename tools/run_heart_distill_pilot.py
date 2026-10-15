"""Frozen local Heart leaf pilot. Called only after independent implementation review.

Usage: python run_heart_distill_pilot.py REPO DATA_ROOT REVIEWED_SHA
Creates an immutable run bundle, canaries, source-disjoint corpus, fit, then one-shot TEST.
Never replaces failed/partial units or extends frozen seeds/time limits.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from heart_rollout_distill import runtime_identity, validate_rows


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v): Path(p).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')


def run(repo,root,reviewed):
    root.mkdir(parents=True,exist_ok=False); bundle=root/'run'; bundle.mkdir()
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()!=reviewed:
        raise ValueError('reviewed source is not HEAD')
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip():
        raise ValueError('source dirty before freeze')
    build_cmd=['cmake','--build','--preset','linux-gcc-release-ccache-build','--target','one_combat','-j2']
    build_start=time.time()
    with (root/'build.log').open('x') as log:
        built=subprocess.run(build_cmd,cwd=repo,stdout=log,stderr=subprocess.STDOUT,timeout=900)
    if built.returncode:raise RuntimeError('reviewed source build failed')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()!=reviewed or subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip():
        raise ValueError('source changed during build')
    binary=repo/'build/linux-gcc-release-ccache/one_combat'
    write(root/'build-receipt.json',{'reviewedSha':reviewed,'command':build_cmd,'returncode':0,
        'seconds':time.time()-build_start,'binarySha256':sha(binary),'logSha256':sha(root/'build.log')})
    shutil.copy2(binary,bundle/'one_combat')
    paths=subprocess.check_output(['git','ls-files','models','selfplay/models'],cwd=repo,text=True).splitlines()
    for rel in paths:
        dst=bundle/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(repo/rel,dst)
    scripts=['tools/heart_rollout_distill.py','tools/heart_record_encoder.py','tools/heart1_leaf_reference.py','tools/run_heart_distill_pilot.py','tools/seed_guard.sh']
    for rel in scripts: shutil.copy2(repo/rel,bundle/Path(rel).name)
    shutil.copy2(repo/'docs/experiments/evidence/heart_rollout_distill_20261016/PROTOCOL.md',bundle/'PROTOCOL.md')
    shutil.copy2(repo/'docs/experiments/evidence/ooc_sibling_leaf_capture64_20261015/tv_within_x2b.json.pt',bundle/'opus490.pt')
    models={p:sha(bundle/p) for p in paths}
    env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'HOME':os.environ['HOME'],
         'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','STS_EXECUTABLE_GIT_SHA':reviewed,
         'STS_FAIR':'1','STS_SILVER_SEARCH':'1','STS_SILVER_EXACT_ROOT_BUDGETS':'1',
         'STS_SILVER_ADAPTIVE':'0','STS_SILVER_LEARNED_STOP':'0','STS_SILVER_VNET_LEAF_DIRECT':'0',
         'STS_SILVER_REUSE_CAP_MODE':'allocated','STS_COLLECT_KEYS':'1','STS_STOP_AFTER_ACT':'0',
         'STS_OOC_STRATEGIC_TOK_NN':'selfplay/models/ooc_strategic_tok_final.native',
         'STS_OOC_STRATEGIC_REST':'1','STS_OOC_STRATEGIC_EVENT':'1','STS_OOC_STRATEGIC_SHOP':'1',
         'STS_OOC_STRATEGIC_TREASURE':'1','STS_OOC_STRATEGIC_BOSS_RELIC':'1','STS_OOC_STRATEGIC_MARGIN':'1.0',
         'STS_REST_WIN':'0','STS_OOC_PUBLIC_FUTURES':'8',
         'STS_OOC_MCTS':'1','STS_OOC_MCTS_SIMS':'512','STS_OOC_MCTS_LEAF_COMBATS':'3',
         'STS_OOC_MCTS_LEAF_VALUE':'native','STS_OOC_MCTS_LEAF_POLICY':'v4','STS_OOC_MCTS_PRIOR':'policy',
         'STS_OOC_MCTS_TREE_RULES':'1','STS_OOC_MCTS_TEMPERATURE':'1','STS_OOC_MCTS_CPUCT':'1.5',
         'STS_OOC_MCTS_WIDEN_K':'4','STS_OOC_MCTS_WIDEN_ALPHA':'0.75','STS_OOC_MCTS_MAX_DEPTH':'32',
         'STS_OOC_MCTS_ROOT_SELECTION':'visits','STS_OOC_MCTS_EARLY_STOP':'1'}
    freeze={'reviewedSha':reviewed,'binarySha256':sha(bundle/'one_combat'),'models':models,'environment':env,
            'splits':{'train':list(range(110160000,110160040)),
                      'validation':list(range(110160040,110160048)),'test':list(range(110160048,110160064))},
            'canarySeeds':[110159998,110159999],'sourceTimeoutSeconds':600,'cohortWallSeconds':14400,
            'workers':3,'repeats':64,'captureEvery':4,'maxLeaves':64,'maxDepth':1,
            'toolHashes':{str(bundle/Path(p).name):sha(bundle/Path(p).name) for p in scripts},
            'protocolSha256':sha(bundle/'PROTOCOL.md'),'runtime':runtime_identity(),
            'buildReceiptSha256':sha(root/'build-receipt.json'),'opus490CheckpointSha256':sha(bundle/'opus490.pt')}
    with (root/'freeze.json').open('x') as f: json.dump(freeze,f,indent=2,sort_keys=True)
    def status(stage,**kw): write(root/'status.json',{'pid':os.getpid(),'stage':stage,'time':time.time(),**kw})
    status('canary')
    def unit(seed,capture=True,tag=None,timeout=600):
        base=root/(tag or f'seed-{seed}'); receipt=base.with_suffix('.receipt.json')
        if receipt.exists() or list(root.glob(base.name+'.*')): raise ValueError('unit output already exists: '+str(base))
        e=dict(env)
        e.update(STS_OOC_MCTS_TRACE=str(base.with_suffix('.mcts.csv')),
                 STS_OOC_DECISION_TRACE=str(base.with_suffix('.trace.jsonl')))
        if capture:
            e.update(STS_OOC_SIBLING_CAPTURE=str(base.with_suffix('.sib.jsonl')),STS_OOC_SIBLING_EVERY='4',
                     STS_OOC_SIBLING_REPEATS='64',STS_OOC_SIBLING_LONG='0',
                     STS_OOC_SIBLING_MAX_DEPTH='1',STS_OOC_SIBLING_MAX_LEAVES='64')
        cmd=['bash',str(bundle/'seed_guard.sh'),str(bundle/'one_combat'),'bestbench','10000','1','20',str(seed),str(base.with_suffix('.csv'))]
        start=time.time(); result={'seed':seed,'capture':capture,'command':cmd,'environment':e,'started':start}
        with base.with_suffix('.log').open('x') as log:
            with subprocess.Popen(cmd,cwd=bundle,env=e,stdout=log,stderr=subprocess.STDOUT,start_new_session=True) as child:
                try: rc=child.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGTERM)
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL); child.wait()
                    rc=124
        result.update(returncode=rc,seconds=time.time()-start)
        cap=base.with_suffix('.sib.jsonl')
        if capture and cap.exists(): result['captureSha256']=sha(cap)
        # Receipts expose only completion/custody, not run outcomes or target values.
        with receipt.open('x') as f: json.dump(result,f,indent=2,sort_keys=True)
        if rc!=0: raise RuntimeError(f'unit {seed} failed rc={rc}')
        return base
    control=unit(110159998,False,'canary-control'); treatment=unit(110159998,True,'canary-capture')
    for suffix in ('.trace.jsonl','.mcts.csv.actions.jsonl'):
        a=Path(str(control)+suffix); b=Path(str(treatment)+suffix)
        if not a.exists() or not b.exists() or a.read_bytes()!=b.read_bytes():
            raise ValueError('canary changed decisions/actions: '+suffix)
    second=unit(110159999,True,'canary-second')
    def canary_coverage(base,seed):
        _,_,coverage=validate_rows((json.loads(line) for line in base.with_suffix('.sib.jsonl').open()),seed)
        return coverage
    cover=[canary_coverage(treatment,110159998),canary_coverage(second,110159999)]
    write(root/'canary.json',{'parity':True,'coverage':cover})
    if any(not c['groups'] or c['accepted']<.8*c['raw'] for c in cover): raise ValueError('canary coverage/support gate')
    status('collecting',completed=0); start=time.monotonic(); completed=[]
    allseeds=sum(freeze['splits'].values(),[])
    # Each worker checks the same fixed global deadline before starting its next unit.
    def bounded_unit(seed):
        if time.monotonic()-start>=14400: raise RuntimeError('cohort wall cap')
        return unit(seed,timeout=min(600,max(1,14400-(time.monotonic()-start))))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(bounded_unit,s):s for s in allseeds}
        failures=[]
        for future in as_completed(futures):
            seed=futures[future]
            try: future.result(); completed.append(seed)
            except Exception as error: failures.append({'seed':seed,'error':str(error)})
            status('collecting',completed=len(completed),failures=failures)
    if failures or len(completed)!=64: raise RuntimeError('INCOMPLETE cohort; no fitting or holdout opening')
    # Recheck bundle identities once before fitting; no mutable repository dependency remains.
    if sha(bundle/'one_combat')!=freeze['binarySha256']: raise ValueError('frozen binary changed')
    for rel,digest in models.items():
        if sha(bundle/rel)!=digest: raise ValueError('frozen model changed: '+rel)
    manifest={'sources':{}}
    for seed in allseeds:
        base=root/f'seed-{seed}';receipt=base.with_suffix('.receipt.json');capture=base.with_suffix('.sib.jsonl')
        r=json.loads(receipt.read_text());digest=sha(capture)
        if r['returncode']!=0 or r['captureSha256']!=digest:raise ValueError('source receipt invalid before corpus freeze')
        manifest['sources'][str(seed)]={'receiptSha256':sha(receipt),'captureSha256':digest}
    with (root/'corpus-manifest.json').open('x') as f:json.dump(manifest,f,indent=2,sort_keys=True)
    status('fitting'); out=root/'fit'
    trainer=[sys.executable,str(bundle/'heart_rollout_distill.py')]
    with (root/'fit.log').open('x') as log:
        r=subprocess.run(trainer+['fit',str(root),str(out)],stdout=log,stderr=subprocess.STDOUT,timeout=1200)
    if r.returncode: raise RuntimeError('fit failed; preserve data and stop')
    if not (out/'selection.json').exists(): status('complete',verdict='INSUFFICIENT'); return
    status('testing')
    with (root/'test.log').open('x') as log:
        r=subprocess.run(trainer+['test',str(root),str(out)],stdout=log,stderr=subprocess.STDOUT,timeout=600)
    if r.returncode: raise RuntimeError('one-shot TEST failed; do not retry')
    result=json.loads((out/'test-result.json').read_text()); status('complete',verdict=result['verdict'])


if __name__=='__main__':
    repo,root,reviewed=Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),sys.argv[3]
    already_existed=root.exists()
    try: run(repo,root,reviewed)
    except BaseException as error:
        if root.exists() and not already_existed: write(root/'failure.json',{'error':str(error),'time':time.time(),'pid':os.getpid()})
        raise
